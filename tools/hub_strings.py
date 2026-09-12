#!/usr/bin/env python
"""hub_strings.py - list every Lithuanian chrome fragment of the vendored hub template, so web/i18n/<lang>.json `chrome`
can translate all of them (render.chrome_table applies them longest-first). Run after every engine sync:

    python product/tools/hub_strings.py            # prints fragments missing from en.json chrome
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "engine" / "studycore" / "vendor" / "planas.template.html"
EN = HERE.parent / "web" / "i18n" / "en.json"

LT = re.compile(r"[ąčęėįšųūžĄČĘĖĮŠŲŪŽ]")
STOP = re.compile(r"(?<![A-Za-z])(ir|kai|tada|dabar|liko|per|dalys|dalių|dalis|testas|planas|rytas|diena|vakaras|nauja|naujas|moku|nemoku|"
                  r"pakartok|atlikta|terminai|tema|temos|jau|dar|visi|visos|tik|arba|kartojimas|kartojimo|pilnos|sugeneruotas|intervalai|"
                  r"laukia|imitacija|pamatuota|suplanuota|medžiaga|medžiagos|atsakymas|atsakyk|spausk|pažymėk|rask|klaidą|sprendimas|"
                  r"užduotis|uždaviniai|pratybos|išmokta|aprėptis|tikslai|artimiausi|įvertis|pirma|mintyse|paskelbtos)(?![A-Za-z])", re.I)


def fragments(text: str) -> list[str]:
    out: set[str] = set()
    pats = [r"`((?:[^`\\]|\\.)*)`", r"'((?:[^'\\\n]|\\.)*)'", r'"((?:[^"\\\n]|\\.)*)"']
    for pat in pats:
        for m in re.finditer(pat, text):
            for part in re.split(r"\$\{[^}]*\}", m.group(1)):
                for piece in re.split(r"<[^>]+>|&[a-z]+;|\\n", part):
                    p = piece.strip(" ·:,;()[]{}|/\\\t")
                    if 2 <= len(p) <= 100 and (LT.search(p) or STOP.search(p)) and not re.search(r"^[\w-]+=|function|=>|\.\w+\(|^[a-z]+:\s*\[", p):
                        out.add(p)
    for m in re.finditer(r">([^<>{}]{2,100})<", text):
        p = m.group(1).strip(" ·:,;")
        if p and (LT.search(p) or STOP.search(p)):
            out.add(p)
    return sorted(out, key=lambda s: (-len(s), s))


BOARD = TEMPLATE.parent / "board.js"
DEMO = HERE.parent / "web" / "app" / "demo-hub.html"


def main() -> int:
    text = TEMPLATE.read_text(encoding="utf-8") + "\n" + (BOARD.read_text(encoding="utf-8") if BOARD.exists() else "")
    frags = fragments(text)
    chrome = json.loads(EN.read_text(encoding="utf-8")).get("chrome", {})
    missing = [f for f in frags if f not in chrome and not any(f in k for k in chrome)]
    print(f"{len(frags)} fragments (template + board.js), {len(missing)} missing from en.json chrome")
    for f in missing:
        print(json.dumps(f, ensure_ascii=False) + ": \"\",")
    if DEMO.exists() and "--demo" in sys.argv:
        html = DEMO.read_text(encoding="utf-8")
        left = sorted(set(re.findall(r"[A-Za-zĄČĘĖĮŠŲŪŽąčęėįšųūž]*[ąčęėįšųūžĄČĘĖĮŠŲŪŽ][A-Za-zĄČĘĖĮŠŲŪŽąčęėįšųūž]*", html)))
        print(f"demo hub: {len(left)} Lithuanian-letter words left: {left}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
