#!/usr/bin/env python
"""units.py - turn a topic study page into machine-readable LEARNING UNITS for the daily planner.

WHY. Owner 2026-09-09: study only for in-person tests/exams, 5 minutes three times a day, everything split
into tiny parts by the days left. The planner (tools/plan.py) cannot split an HTML page; it splits UNITS.
A topic page built before 2026-09-09 keeps its data as JS constants (ROOMS, Q, S, C, T, VBE, O); this tool
evaluates those constants with node and writes study/<subject>/<topic>.units.json beside the page.
A page built after that date may ship its *.units.json directly - this is the bridge, not a requirement.

    python tools/units.py extract study/biologija/virskinimas.html [--topic bio-virskinimas]
    python tools/units.py list                      # every *.units.json with unit counts and seconds

Unit types and the seconds one takes in a 5-minute slot (measured against the biology page, 2026-09-09):
    question  70 s  ranked probable question: recall -> reveal -> "Kaip isiminti" (room + hooks + sentence)
    hook      35 s  keyword-method flip card: term -> funny word + bizarre image
    number    20 s  picture-number tile
    card      25 s  plain flashcard (used for review sweeps and the test-imitation phase)
    quiz      45 s  multiple-choice item with instant feedback (test imitation)
    vbe       90 s  a REAL past exam task with its marking-scheme answer (exam imitation)
    quiz/rule 20 s  'Kuria taisykle taikysi?' - strategy choice built from practice `rule` labels (maths, 2026-09-10)
    quiz/error 45 s 'Rask klaida' - an erroneous handwritten worked example from the page's `mistakes`
question/practice units keep a `board` (handwritten step-by-step solution, tools/board.js) when the page has one.
Weights (0..1) rank what must be learned first: a question carries its probability, a hook the highest
probability of the questions that cite it, numbers 0.6, cards 0.5, quiz/vbe are imitation material.
"""
from __future__ import annotations

import json
import os
import re
import calc
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

ROOT = Path(__file__).resolve().parent.parent
STUDY = ROOT / "study"
SEC = {"question": 70, "hook": 35, "number": 20, "card": 25, "quiz": 45, "vbe": 90, "practice": 100, "mistake": 45, "rule": 20}
CONSTS = ["ROOMS", "Q", "S", "C", "T", "VBE", "O", "P", "M", "SUBROOM"]


def board_seconds(board: list[dict], prompt: str) -> int:
    """Estimated seconds to work through a handwritten board: write wipes (70 ms/char, 0.42-2.6 s a line) + marks, reading
    `do/why/mind` at ~17 chars/s (~200 wpm) plus a tap per step, 6 s per prediction question, and reading the task.
    Glance round 5 (2026-09-11): a boarded unit must be costed from its board, not from the pre-board constant."""
    clean = lambda t: re.sub(r"<[^>]+>|\$|\\f|[{}^_\[\]#~]", "", str(t))
    sec = len(clean(prompt)) / 17.0 + 3
    for st in board:
        lines = [st["w"]] if isinstance(st.get("w"), str) else (st.get("w") or [])
        sec += sum(max(0.42, min(2.6, len(clean(l).replace(" ", "")) * 0.07)) + 0.3 for l in lines) + 0.5 * len(st.get("marks") or [])
        sec += sum(len(clean(st.get(k, ""))) for k in ("do", "why", "mind")) / 17.0 + 1.5
        if st.get("ask"):
            sec += 6 + sum(len(str(o)) for o in st["ask"].get("o", [])) / 17.0
        if st.get("calc"):
            sec += calc.calc_seconds(st["calc"])     # reading the strip and pressing it once on the real calculator
    return int(sec + 0.999)


def rule_drills(topic: str, practice: list[dict]) -> list[dict]:
    """'Kuria taisykle taikysi?' - 20-second strategy-selection quiz units (interleaved practice, Rohrer, Dedrick & Stershic 2015).
    Only a practice task that carries `near` - three HAND-PICKED look-alike rules its own solution does not use - gets a drill.
    Three glance rounds (2026-09-10/11) showed that word-overlap distractors either offer a rule the task also needs (a right
    answer marked wrong) or, once filtered, only far-away rules (a topic-recognition question): judgement, not stems, picks them."""
    known = {x["rule"] for x in practice if x.get("rule")}
    out = []
    for i, x in enumerate(practice):
        r, near = x.get("rule"), x.get("near") or []
        if not r or len(near) != 3 or r in near or any(n not in known for n in near):
            continue
        opts = near[: i % 4] + [r] + near[i % 4:]
        out.append({"id": f"{topic}:r:{i}", "type": "quiz", "kind": "rule", "w": 0.5, "sec": SEC["rule"],
                    "s": "Kurią taisyklę taikysi? " + strip(x.get("q", "")), "o": opts, "r": opts.index(r),
                    "e": strip(f"{r}." + (f" {x['hint']}" if x.get("hint") else ""))})
    return out


def js_constants(html: str, names: list[str]) -> dict:
    """Evaluate `const NAME = ...;` literals from the page's script with node (they are JS, not JSON)."""
    js = re.search(r"<script>(.*)</script>", html, re.S)
    if not js:
        return {}
    js = js.group(1)
    segs = []
    for n in names:
        m = re.search(r"\n(?:const|let|var) %s\s*=\s*" % re.escape(n), js)
        if not m:
            continue
        start = m.end()
        m2 = re.search(r"\n(?=(?:const|let|var|function) |document\.|window\.|\(function|for\(|if\()", js[start:])
        seg = js[start:start + m2.start()] if m2 else js[start:]
        segs.append((n, seg.rstrip().rstrip(";")))
    if not segs:
        return {}
    code = "\n".join(f"const {n}={seg};" for n, seg in segs) + "\nconsole.log(JSON.stringify({" + ",".join(n for n, _ in segs) + "}));"
    fd, p = tempfile.mkstemp(suffix=".js")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(code)
    try:
        r = subprocess.run(["node", p], capture_output=True, text=True, encoding="utf-8", timeout=60)
    finally:
        os.unlink(p)
    if r.returncode != 0:
        raise SystemExit("node could not evaluate the page constants: " + r.stderr[:400])
    return json.loads(r.stdout)


def palace_svg(html: str) -> str:
    sec = re.search(r'<section id="rumai">(.*?)</section>', html, re.S)
    if not sec:
        return ""
    m = re.search(r"<svg.*?</svg>", sec.group(1), re.S)
    return m.group(0) if m else ""


def mnemonics(html: str) -> list[list[str]]:
    sec = re.search(r'<section id="mnemonikos">(.*?)</section>', html, re.S)
    if not sec:
        return []
    return [[strip(b), strip(s)] for b, s in re.findall(r"<div><b>(.*?)</b><span>(.*?)</span></div>", sec.group(1), re.S)]


def strip(h: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h)).strip()


def extract(page: Path, topic: str | None) -> Path:
    html = page.read_text(encoding="utf-8")
    subject = page.parent.name
    if not topic:
        # A page built by tools/topic.py has its content JSON beside it: its own `topic` id is the one assessments.json
        # names. The old filename-derived default ("lie-rasyba" for study/lietuviu/rasyba.html) silently dropped two
        # rebuilt Lithuanian topics out of the plan on 2026-09-10, because nothing matched "lt-rasyba".
        try:
            sib = page.with_suffix(".json")
            topic = json.loads(sib.read_text(encoding="utf-8")).get("topic") if sib.exists() else None
        except (ValueError, OSError):
            topic = None
    topic = topic or f"{subject[:3]}-{page.stem}"
    content: dict = {}
    try:
        sib = page.with_suffix(".json")
        content = json.loads(sib.read_text(encoding="utf-8")) if sib.exists() else {}
    except (ValueError, OSError):
        content = {}
    lang = content.get("lang") or "lt"
    title = strip(re.search(r"<title>(.*?)</title>", html, re.S).group(1)) if "<title>" in html else page.stem
    d = js_constants(html, CONSTS)
    rooms = d.get("ROOMS", [])
    units: list[dict] = []
    hook_w: dict[str, float] = {}
    for i, q in enumerate(d.get("Q", [])):
        m = q.get("m", {}) or {}
        for kw in m.get("h", []):
            hook_w[kw] = max(hook_w.get(kw, 0), q.get("p", 50) / 100)
        units.append({"id": f"{topic}:q:{i}", "type": "question", "w": round(q.get("p", 50) / 100, 2), "sec": SEC["question"],
                      "q": q.get("q", ""), "a": q.get("a", ""), "t": q.get("t", ""), "why": q.get("w", ""),
                      "rooms": m.get("r", []), "hooks": m.get("h", []), "s": m.get("s", ""), "steps": q.get("st", []) or []})
        if q.get("board"):
            units[-1]["board"] = q["board"]      # the handwritten step-by-step solution (tools/board.js)
            units[-1]["sec"] = min(300, max(SEC["question"], board_seconds(q["board"], q.get("q", ""))))
        if q.get("c"):
            units[-1]["c"] = q["c"]              # calc = the calculator does it, head = needs your head, both
    from topic import association_on   # one settings loader for both generators (collab 2026-09-12)
    assoc = association_on()
    if not assoc:   # owner 2026-09-12: no palace, hooks or first-letter sentences - drop them from question units, emit no hook units
        for x in units:
            for k in ("rooms", "hooks", "s"):
                x.pop(k, None)
        rooms = []
    for ri, r in enumerate(rooms):
        for hi, h in enumerate(r.get("hooks", [])):
            term, kw, img = (h + ["", "", ""])[:3]
            units.append({"id": f"{topic}:h:{ri}:{hi}", "type": "hook", "w": round(hook_w.get(kw, 0.5), 2), "sec": SEC["hook"],
                          "term": term, "kw": kw, "img": img, "room": ri})
    for i, (label, value) in enumerate(d.get("S", [])):
        units.append({"id": f"{topic}:n:{i}", "type": "number", "w": 0.6, "sec": SEC["number"], "label": label, "value": value})
    for i, c in enumerate(d.get("C", [])):
        u = {"id": f"{topic}:c:{i}", "type": "card", "w": 0.5, "sec": SEC["card"], "q": c[0], "a": c[1]}
        extra = c[2] if len(c) > 2 and isinstance(c[2], dict) else {}
        if extra.get("hold"):
            u["hold"] = True    # an answer no teacher key confirms: shown on the page, never scheduled (reviewer 2026-09-10)
        elif extra.get("learn"):
            u["learn"] = True   # a teacher's own list: daily material in the plan, not only final-weeks practice (owner 2026-09-10)
        units.append(u)
    for i, t in enumerate(d.get("T", [])):
        u = {"id": f"{topic}:t:{i}", "type": "quiz", "w": 0.5, "sec": SEC["quiz"], "s": t.get("s", ""), "o": t.get("o", []) or [], "r": t.get("r", 0), "e": t.get("e", "")}
        if not u["o"]:
            u["fill"] = True          # fill-in item: the page shows a reveal + self-judgement instead of options
        units.append(u)
    for i, x in enumerate(d.get("P", [])):
        duration = x.get("sec", SEC["practice"])
        if isinstance(duration, bool) or not isinstance(duration, int) or not 30 <= duration <= 300:
            raise ValueError(f"practice {i}: sec must be an integer from 30 to 300; split longer work")
        u = {"id": f"{topic}:p:{i}", "type": "practice", "w": 0.75, "sec": duration,
             "q": x.get("q", ""), "a": x.get("a", ""), "steps": x.get("st", []), "t": x.get("t", ""), "hint": x.get("hint", "")}
        if x.get("chain"):
            u.update(chain=x["chain"], stage=x["stage"])
        if x.get("board"):
            u["board"] = x["board"]          # the handwritten step-by-step solution (tools/board.js)
            u["sec"] = min(300, max(duration, board_seconds(x["board"], x.get("q", ""))))
        if x.get("rule"):
            u["rule"] = x["rule"]
        units.append(u)
    units += rule_drills(topic, d.get("P", []))
    for i, it in enumerate(content.get("calcCard", {}).get("items", [])):
        # calculator routines (owner 2026-09-12): core practice, scheduled like a practice task - "get 125 on your calculator"
        # owner 2026-09-12 (second note): the strip is stepped ONE KEY AT A TIME by hand, "without rushing" - 1.5 s a key, not 0.6
        units.append({"id": f"{topic}:k:{i}", "type": "practice", "kind": "calc", "w": 0.8, "sec": int(10 + 1.5 * len(it["calc"]["k"])),
                      "q": it["t"], "a": " ".join(map(str, it["calc"]["k"])) + " → " + str(it["calc"]["d"]), "calc": it["calc"], "n": it.get("n", ""),
                      "steps": [], "t": "Skaičiuotuvas", "hint": ""})
    for i, x in enumerate(d.get("M", [])):
        # "Rask klaida": an erroneous worked example (Grosse & Renkl 2007) - a quiz-type unit, so the planner interleaves it
        units.append({"id": f"{topic}:e:{i}", "type": "quiz", "kind": "error", "w": 0.6, "sec": SEC["mistake"], "s": strip(x.get("s", "")),
                      "o": [], "r": 0, "e": x.get("e", ""), "tip": x.get("tip", ""), "t": x.get("t", ""),
                      "board": x.get("board", []), "bad": x.get("bad", 1), "fix": x.get("fix", "")})
    for i, v in enumerate(d.get("VBE", [])):
        q_txt, a_txt = v.get("question", ""), v.get("answer", "")
        unmarked = bool(re.search(r"(?i)nepublikuot|instrukcijos nėra|nėra instrukcijos", a_txt)) or not a_txt.strip()
        needs_figure = bool(re.search(r"(?i)paveiksl|\bpav\.|schem|grafik|diagram|brėžin", q_txt))
        u = {"id": f"{topic}:v:{i}", "type": "vbe", "w": 0 if (unmarked or needs_figure) else min(1.0, 0.4 + 0.1 * float(v.get("points", 1) or 1)), "sec": SEC["vbe"],
             "year": v.get("year"), "session": v.get("session", ""), "number": v.get("number", ""), "points": v.get("points", 1), "form": v.get("form", ""),
             "subtopic": v.get("subtopic", ""), "question": q_txt, "answer": a_txt, "source": v.get("source", "")}
        if unmarked:
            u["unmarked"] = True      # no published marking scheme: cannot be a self-test
        if needs_figure:
            u["needsFigure"] = True   # refers to a figure the page does not carry
        if re.search(r"(?i)maket", v.get("source", "") + " " + str(v.get("session", ""))):
            u["session"] = "maketas"
        units.append(u)
    if lang != "lt":
        for x in units:
            x["lang"] = lang          # the hub shows this unit's own chrome (buttons, instructions) in the lesson's language
    out = {
        "topic": topic, "subject": subject, "title": title, "lang": lang, "page": page.relative_to(ROOT).as_posix().replace("\\", "/"),
        "rooms": [{"n": r.get("n", ""), "scene": r.get("scene", ""), "hooks": r.get("hooks", [])} for r in rooms],
        "palaceSvg": palace_svg(html) if rooms else "", "mnemonics": mnemonics(html), "subroom": d.get("SUBROOM", {}) if rooms else {},
        "units": units, "seconds": sum(u["sec"] for u in units),
    }
    dest = page.with_name(page.stem + ".units.json")
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    counts = {}
    for u in units:
        counts[u["type"]] = counts.get(u["type"], 0) + 1
    skipped = sum(1 for u in units if u["type"] == "vbe" and (u.get("unmarked") or u.get("needsFigure")))
    print(f"{dest.relative_to(ROOT)}: {len(units)} units, {skipped} VBE tasks excluded from self-tests (no marking scheme / need a figure); ({', '.join(f'{k} {v}' for k, v in counts.items())}), {out['seconds'] // 60} min of new material, {len(rooms)} rooms, palace svg {'yes' if out['palaceSvg'] else 'NO'}, {len(out['mnemonics'])} mnemonics")
    return dest


def cmd_list():
    for f in sorted(STUDY.glob("*/*.units.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        print(f"{d['topic']:<22} {f.relative_to(ROOT).as_posix():<45} {len(d['units']):>4} units {d['seconds'] // 60:>4} min")


def main(argv: list[str]):
    if not argv or argv[0] == "list":
        return cmd_list()
    if argv[0] == "extract":
        topic = argv[argv.index("--topic") + 1] if "--topic" in argv else None
        return extract(Path(argv[1]).resolve() if Path(argv[1]).is_absolute() else ROOT / argv[1], topic)
    print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
