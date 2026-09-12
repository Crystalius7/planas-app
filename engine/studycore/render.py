"""render.py - build a topic page and its units in ANY interface language (wraps vendor/topic.py and vendor/units.py).

The personal topic.py renders Lithuanian chrome and swaps English through EN_CHROME (owner 2026-09-12). The product needs
every language, so this adapter: (1) lets `lang` be any code (the vendored check refuses codes other than lt/en - that
line is filtered here, an engine improvement to carry into the personal tool later), (2) applies the product's own chrome
table (web/i18n/chrome.<lang>.json, generated from web/i18n/<lang>.json) after the page is built, (3) keeps the content's
own language untouched - the answers are in the language of the material, exactly as the teacher would mark them.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .workspace import Workspace

I18N = Path(__file__).resolve().parents[2] / "web" / "i18n"


def chrome_table(lang: str) -> list[tuple[str, str]]:
    """Lithuanian chrome phrase -> the UI language, longest phrase first. web/i18n/<lang>.json carries the pairs under
    `chrome` (tools/hub_strings.py lists the phrases the vendored hub template uses); a language without its own table
    falls back to English chrome."""
    p = I18N / f"{lang}.json"
    if not p.exists() or lang == "lt":
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    pairs = [(lt, tr) for lt, tr in (d.get("chrome") or {}).items() if tr and not lt.startswith("_")]
    if not pairs and lang != "en":
        return chrome_table("en")
    return sorted(pairs, key=lambda x: -len(x[0]))


_LETTER = "A-Za-zÀ-ÖØ-öø-ÿĀ-žΑ-ωА-я"


def apply_chrome(html: str, lang: str) -> str:
    """Replace every hub chrome phrase with letter boundaries, so 'per' never touches 'perskaityk' and 'iš' never touches
    'išmokta'. Content (answers, titles) stays in the language of the material."""
    for lt, tr in chrome_table(lang):
        tr = tr.replace("'", "’")   # a straight apostrophe would end a JS string literal in the template
        pat = re.compile(rf"(?<![{_LETTER}]){re.escape(lt)}(?![{_LETTER}])")
        html = pat.sub(lambda m, tr=tr: tr, html)
    return html


def build_topic(ws: Workspace, content_path: Path, ui_lang: str | None = None) -> dict:
    """Content JSON -> study/<subject>/<topic>.html (+ .units.json). Returns {page, units, problems}."""
    mods = ws.bind()
    topic, units = mods["topic"], mods["units"]
    content = json.loads(content_path.read_text(encoding="utf-8"))
    lang = ui_lang or ws.settings.get("uiLang") or "en"
    content_lang = content.get("lang")
    problems = [p for p in topic.check_content(content) if not p.startswith("`lang` must be")]
    if problems:
        return {"page": None, "units": None, "problems": problems}
    # the vendored builder reads the file itself; hand it a copy whose lang is one it accepts and fix the chrome after
    tmp = content_path.with_suffix(".build.json")
    build_content = dict(content)
    build_content["lang"] = "en" if content_lang not in (None, "lt") else content_lang
    tmp.write_text(json.dumps(build_content, ensure_ascii=False), encoding="utf-8")
    try:
        page = topic.build(tmp) if hasattr(topic, "build") else None
        if page is None:   # older vendored entry point: main([...]) writes the page next to the JSON
            topic.main(["build", str(tmp)])
            page = tmp.with_suffix(".html")
        page = Path(page)
        final = content_path.with_suffix(".html")
        html = page.read_text(encoding="utf-8")
        if lang not in ("lt", "en"):
            html = apply_chrome(html, lang)
        html = html.replace(f'lang="{build_content["lang"]}"', f'lang="{content_lang or lang}"', 1)
        final.write_text(html, encoding="utf-8")
        if page != final:
            page.unlink(missing_ok=True)
    finally:
        tmp.unlink(missing_ok=True)
    units_path = units.extract(final, content.get("topic")) if hasattr(units, "extract") else None
    return {"page": str(final), "units": str(units_path) if units_path else None, "problems": []}


def digested_material(ws: Workspace) -> list[dict]:
    """Every material item the student can check (owner 2026-09-12: "show every learning material that's been digested so
    users can check there if everything is there"): the ledgers written per topic + every module of every mirrored course
    with its verdict (used / checked / skipped / unreachable / not yet)."""
    verdicts: dict[str, dict] = {}
    for lf in sorted((ws.study / "material").glob("*.json")):
        try:
            d = json.loads(lf.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for it in d.get("items", []):
            verdicts[str(it.get("id") or it.get("name"))] = {**it, "topic": d.get("topic", lf.stem)}
    out = []
    for mf in sorted(ws.courses.glob("*/manifest.json")):
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for x in m.get("modules", []):
            v = verdicts.get(str(x.get("id"))) or verdicts.get(x.get("name") or "")
            out.append({"course": m.get("fullname"), "courseId": m.get("id"), "section": x.get("section"), "id": x.get("id"),
                        "name": x.get("name"), "module": x.get("module"), "files": x.get("files") or [],
                        "verdict": (v or {}).get("verdict", "not-yet"), "topic": (v or {}).get("topic"), "note": (v or {}).get("note", "")})
    return out
