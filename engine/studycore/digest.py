"""digest.py - mirrored material -> a topic content JSON (the personal page schema) through a model adapter.

Where the personal system's orchestrator authors a topic by hand, the product authors it here:

  provider "none"      TOKENLESS BASELINE. No model. Cards from Moodle glossaries and quiz question banks the student can
                       already see, 'questions' from the material's own headings with the paragraph under each as the answer,
                       numbers from figures in the text, the material ledger. Honest and cheap; the page says "baseline".
  provider "ollama"    the student's own PC (free, private): POST http://127.0.0.1:11434/api/chat, JSON mode.
  provider "anthropic" the official SDK (cloud tier; the subscription pays for it).
  provider "openai"    chat completions with response_format json_object (cloud tier alternative).

The model receives the material chunks, the subject shape, the language of the material and the exact content contract
(CONTRACT below) and must answer with ONE JSON object; the result goes through vendor/topic.py check_content() before it
is rendered, so a page is never built from a malformed or invented structure. Ranked probabilities produced by a model
are labelled estimates on the page (CLAUDE.md: a number with no real source is an estimate).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from . import subjects
from .workspace import Workspace

CONTRACT = """You write the study content for ONE topic. Answer with ONE JSON object and nothing else.
Language: write every answer the student must memorise in the LANGUAGE OF THE MATERIAL, exactly as a teacher would mark it.
Keys:
 topic (id), subject (id), title, eyebrow (subject name), lead (2 sentences: what the test will most likely ask),
 questionsIntro,
 questions: [{p: probability 0-100 (an ESTIMATE), t: question type/category (2-4 words), q: the question,
              a: the answer as HTML (<ul><li>...</li></ul>, bold the words that score), w: why this is probable, citing the source
              (file name, page/slide, video + timestamp), c: "calc" | "head" | "both" (procedural subjects only)}],
 numbers: [[what, value], ...] (figures worth memorising),
 cards: [[front, back], ...] (one fact per card, 60-120 cards for a chapter; a card front is a question),
 quiz: [{s: stem, o: [4 options], r: index of the right option, e: explanation citing the source}],
 table: {title, head: [cols], rows: [[...]]} (the one-glance comparison the shape asks for: mechanisms, works, rules, formulas),
 practice (procedural subjects): [{q: task, a: answer, sec: 60-180, steps: [[what I do, why]]}] worked task variants,
 mistakes (procedural): [{s: task, fix: correct last line ending with the answer, e: what is wrong}],
 corrections: [] (leave empty unless FACT CHECK is on; then {was, now, where, basis} for each certain correction),
 sources: [{name, kind, used: true|false, note}] - every material item you were given, with a verdict.
Rules: nothing invented - every question, card and quiz item must be traceable to the material; probabilities are
estimates ranked highest first; questions cover the whole material at the test's level, most probable first; no memory
palace, no mnemonics, no first-letter sentences. Write concentrated, exam-ready wording."""


class Digest:
    def __init__(self, ws: Workspace):
        self.ws = ws
        cfg = ws.settings.get("digest") or {}
        self.provider = (cfg.get("provider") or "none").lower()
        self.model = cfg.get("model")
        self.endpoint = cfg.get("endpoint")

    # ---- material -------------------------------------------------------------------------------------------------
    def material(self, course_dir: Path, sections: list[str] | None = None, max_chars: int = 400_000) -> tuple[str, list[dict]]:
        """Text of a course (or of the named INDEX sections): page texts + extracted files + video transcripts/frame notes."""
        mods = self.ws.bind()
        extract = mods["extract"]
        chunks, items = [], []
        index = (course_dir / "INDEX.md").read_text(encoding="utf-8") if (course_dir / "INDEX.md").exists() else ""
        keep_all = not sections
        cur = None
        for line in index.splitlines():
            if line.startswith("## "):
                cur = line[3:].strip()
                continue
            if not line.startswith("- **") or (not keep_all and cur not in (sections or [])):
                continue
            m = re.match(r"^- \*\*(.+?)\*\* \((\w+)\)(?: → (.+))?$", line)
            if not m:
                continue
            name, kind, target = m.group(1), m.group(2), (m.group(3) or "")
            item = {"name": name, "kind": kind, "section": cur, "target": target, "chars": 0}
            for t in [x.strip() for x in target.split(",") if x.strip()]:
                p = course_dir / t
                text = ""
                if p.exists() and p.is_file():
                    if p.suffix.lower() == ".md":
                        text = p.read_text(encoding="utf-8", errors="replace")
                    else:
                        try:
                            text = extract.extract_text(p) if hasattr(extract, "extract_text") else ""
                        except Exception as e:  # noqa: BLE001 - a broken file is reported in the ledger, never crashes a digest
                            item["error"] = f"{type(e).__name__}: {e}"
                elif t.startswith("http"):
                    for vt in course_dir.glob(f"videos/*{_vid_key(t)}*.txt"):
                        text += vt.read_text(encoding="utf-8", errors="replace")
                    item["video"] = t
                if text:
                    chunks.append(f"\n\n===== {cur} / {name} ({kind}) [{t}] =====\n{text}")
                    item["chars"] += len(text)
            items.append(item)
        joined = "".join(chunks)
        return joined[:max_chars], items

    # ---- providers ------------------------------------------------------------------------------------------------
    def run(self, topic_id: str, subject_id: str, title: str, course_name: str, course_dir: Path, sections: list[str] | None = None,
            lang: str | None = None, fact_check: bool | None = None) -> dict:
        text, items = self.material(course_dir, sections)
        shape = subjects.classify(course_name)
        fc = self.ws.settings.get("factCheck") if fact_check is None else fact_check
        if self.provider == "none" or not text.strip():
            content = baseline(topic_id, subject_id, title, course_name, text, items, shape)
        else:
            prompt = self._prompt(topic_id, subject_id, title, course_name, text, items, shape, lang, bool(fc))
            raw = self._complete(prompt)
            content = _parse_json(raw)
            content.setdefault("topic", topic_id)
            content.setdefault("subject", subject_id)
            content.setdefault("title", title)
            content["shape"] = shape["shape"]
            content["digest"] = {"provider": self.provider, "model": self.model, "chars": len(text), "items": len(items)}
        if not fc:
            content["corrections"] = []
        content["sources"] = content.get("sources") or [{"name": i["name"], "kind": i["kind"], "used": i["chars"] > 0, "note": i.get("error") or ""} for i in items]
        return content

    def _prompt(self, topic_id, subject_id, title, course_name, text, items, shape, lang, fact_check) -> str:
        fc = ("FACT CHECK ON: when you are 100 % certain (textbook-level, authoritative) that a statement in the material is wrong "
              "or outdated, use the correct fact in every answer and list each change in `corrections` with its basis and date. "
              if fact_check else "FACT CHECK OFF: keep the material's own statements even where you would disagree; `corrections` stays empty. ")
        return (f"{CONTRACT}\n\nTopic id: {topic_id}\nSubject id: {subject_id}\nTitle: {title}\nCourse: {course_name}\n"
                f"Subject shape: {shape['shape']} (family {shape['family']}; calculator strips: {shape['calc']})\n"
                f"Material language: {lang or 'the language of the material below'}\n{fc}\n"
                f"Material items ({len(items)}): " + json.dumps([{k: v for k, v in i.items() if k != 'target'} for i in items], ensure_ascii=False) +
                f"\n\nMATERIAL:\n{text}\n\nAnswer with the JSON object only.")

    def _complete(self, prompt: str) -> str:
        if self.provider == "ollama":
            import requests
            url = (self.endpoint or "http://127.0.0.1:11434").rstrip("/") + "/api/chat"
            r = requests.post(url, json={"model": self.model or "gemma3:12b", "messages": [{"role": "user", "content": prompt}],
                                         "format": "json", "stream": False, "options": {"temperature": 0.2, "num_ctx": 32768}}, timeout=3600)
            r.raise_for_status()
            return r.json()["message"]["content"]
        if self.provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic()   # ANTHROPIC_API_KEY or the ant CLI profile
            with client.messages.stream(model=self.model or "claude-opus-5", max_tokens=64000,
                                        thinking={"type": "adaptive"}, output_config={"effort": "medium"},
                                        messages=[{"role": "user", "content": prompt}]) as stream:
                msg = stream.get_final_message()
            if msg.stop_reason == "refusal":
                raise RuntimeError("the model declined this material")
            return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        if self.provider == "openai":
            import requests
            key = os.environ.get("OPENAI_API_KEY")
            if not key:
                raise RuntimeError("OPENAI_API_KEY is not set")
            r = requests.post((self.endpoint or "https://api.openai.com/v1").rstrip("/") + "/chat/completions",
                              headers={"Authorization": f"Bearer {key}"},
                              json={"model": self.model or "gpt-5-mini", "messages": [{"role": "user", "content": prompt}],
                                    "response_format": {"type": "json_object"}}, timeout=3600)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        raise RuntimeError(f"unknown digest provider {self.provider}")


# ----------------------------------------------------------------------------------------------- tokenless baseline
def baseline(topic_id: str, subject_id: str, title: str, course_name: str, text: str, items: list[dict], shape: dict) -> dict:
    """No model: headings become questions, the paragraph under each becomes the answer, figures become numbers, and
    glossary/quiz banks become cards. Labelled `baseline` so the page and the plan say what it is."""
    questions, numbers, cards = [], [], []
    seen = set()
    for block in re.split(r"\n(?=#+ |=====)", text):
        lines = [l for l in block.strip().splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        head = re.sub(r"^[#=\s]+|[=\s]+$", "", lines[0]).strip()
        head = re.sub(r"\s*\(\w+\)\s*\[.*?\]\s*$", "", head)
        if not head or len(head) > 120 or head.lower() in seen:
            continue
        body = " ".join(lines[1:])[:600]
        if len(body) < 40:
            continue
        seen.add(head.lower())
        questions.append({"p": max(20, 90 - 5 * len(questions)), "t": "baseline", "q": head if head.endswith("?") else f"{head}?",
                          "a": f"<p>{_esc(body)}</p>", "w": "baseline: heading and the text under it (no model was used)"})
        if len(questions) >= 40:
            break
    for m in re.finditer(r"([A-ZĄČĘĖĮŠŲŪŽ][^.\n]{10,80}?)\s(\d[\d\s.,]*\s?(?:%|km|m|kg|g|°C|mln|mlrd|million|billion|years|metų))", text):
        numbers.append([m.group(1).strip(), m.group(2).strip()])
        if len(numbers) >= 30:
            break
    for m in re.finditer(r"(?m)^\s*([^\n:]{3,60}):\s+([^\n]{10,200})$", text):
        cards.append([m.group(1).strip() + "?", m.group(2).strip()])
        if len(cards) >= 80:
            break
    return {"topic": topic_id, "subject": subject_id, "title": title, "eyebrow": course_name, "shape": shape["shape"],
            "lead": "Baseline content built without a model: the material's own headings, definitions and figures. Turn on a digest "
                    "provider for ranked probable questions and explanations.",
            "questionsIntro": "Headings of the material, most likely first (baseline order = the material's own order).",
            "questions": questions, "numbers": numbers, "cards": cards, "quiz": [], "corrections": [], "baseline": True,
            "digest": {"provider": "none", "chars": len(text), "items": len(items)}}


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _vid_key(url: str) -> str:
    m = re.search(r"(?:v=|/)([A-Za-z0-9_-]{8,})", url)
    return m.group(1)[:16] if m else "nomatch"


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError("the model did not answer with a JSON object")
    return json.loads(m.group(0))
