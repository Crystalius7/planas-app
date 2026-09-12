#!/usr/bin/env python
"""release.py - the finished switch and the portfolio hand-off.

    python product/tools/release.py status
    python product/tools/release.py finish --url https://<app> --repo https://github.com/<owner>/<repo> [--demo <url>]

Owner 2026-09-12: "we will add this to our portfolio website only when we finish this product, add automatically there once we
finish, it will be clickable and will lead to this product." The portfolio lives in ANOTHER workspace (Lojalumas,
tools/portfolio/projects.json rendered by portfolio-build.js) and a foreign workspace is never edited from here (shared rule
2026-09-08), so `finish`:
  1. refuses while docs/LAUNCH-CHECKLIST.md has an unchecked "- [ ]" item in its MUST section;
  2. sets release.json finished=true with the URLs;
  3. writes product/portfolio-entry.json in the portfolio feed's own shape (status done, category ai, lt/en/ru title and
     summary, url, since) - the Lojalumas agent copies it into projects.json as a manual product entry;
  4. drops a SCOPE: ALL broadcast notice (~\\.claude\\broadcast\\notices) that names the Lojalumas workspace as the one to act,
     every other workspace acks it at once; the notice prints on every prompt there until acked.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRODUCT = HERE.parent
RELEASE = PRODUCT / "release.json"
CHECKLIST = PRODUCT / "docs" / "LAUNCH-CHECKLIST.md"
ENTRY = PRODUCT / "portfolio-entry.json"


def load() -> dict:
    return json.loads(RELEASE.read_text(encoding="utf-8"))


def unchecked_must() -> list[str]:
    if not CHECKLIST.exists():
        return ["docs/LAUNCH-CHECKLIST.md is missing"]
    text = CHECKLIST.read_text(encoding="utf-8")
    must = text.split("## MUST", 1)[1].split("\n## ", 1)[0] if "## MUST" in text else text
    return [l.strip()[6:] for l in must.splitlines() if l.strip().startswith("- [ ]")]


def entry(rel: dict) -> dict:
    return {
        "id": "planas-product",
        "status": "done",
        "category": "ai",
        "product": True,
        "title": {"lt": "Planas – mokymosi planas iš Moodle testų ir terminų",
                  "en": "Planas – a study plan built from your Moodle tests and deadlines",
                  "ru": "Planas – план учёбы из тестов и сроков вашего Moodle"},
        "summary": {"lt": "Programa mokiniams: visi Moodle testai, egzaminai, terminai ir nauja medžiaga vienoje vietoje, o kiekvienam testui – 15 min per dieną planas su kartojimu. Slaptažodis niekada nepatenka į mūsų serverius.",
                    "en": "An app for students: every Moodle test, exam, deadline and new file in one place, and a 15-minute-a-day plan with spaced review for each test. The password never reaches our servers.",
                    "ru": "Приложение для учеников: все тесты, экзамены, сроки и новые материалы из Moodle в одном месте и план на 15 минут в день с повторением к каждому тесту. Пароль никогда не попадает на наши серверы."},
        "url": rel.get("url"),
        "demoUrl": rel.get("demoUrl"),
        "repo": rel.get("repo"),
        "name": "Planas",
        "named": True,
        "namedProof": "own product - no client consent needed",
        "since": (rel.get("finishedAt") or "")[:7],
    }


def notice(rel: dict) -> Path:
    root = Path(os.environ.get("USERPROFILE", "~")).expanduser() / ".claude" / "broadcast" / "notices"
    root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d")
    p = root / f"{stamp}-planas-portfolio.md"
    p.write_text(f"""# BROADCAST: the Planas product is FINISHED - Lojalumas adds it to the portfolio; every other workspace acks at once
SCOPE: ALL

APPLIES TO: the Lojalumas workspace only (C:\\Users\\igdau\\Desktop\\Lojalumas). Every other workspace: ack immediately, nothing to do.

What happened: release.py finish ran in MokymasisSuAjajum/product on {stamp}. The owner's standing instruction (2026-09-12):
"add this to our portfolio website only when we finish this product, add automatically there once we finish, it will be
clickable and will lead to this product."

Lojalumas agent, THIS TURN:
1. Read {ENTRY} - the entry in the feed's own shape (status done, category ai, product true, lt/en/ru title + summary, url).
2. Add it to tools/portfolio/projects.json as a manual product entry (portfolio-sync.js must keep it: it is not income-driven;
   give manual entries a `manual: true` guard in the sync so a client-feed rebuild never drops it), make the card CLICKABLE to
   entry.url, rebuild (node tools/portfolio-build.js), verify (node tools/portfolio-verify.js), look, publish through autosync.
   The owner's 2026-09-12 wording rules for the portfolio copy still apply (no "our product" boasting in the service copy);
   this entry is the owner's explicit exception: it may be named and linked as a finished product.
3. Ack: create ~\\.claude\\broadcast\\acks\\{p.stem}__Lojalumas.done

Everyone else: create ~\\.claude\\broadcast\\acks\\{p.stem}__<YourProjectFolderName>.done and move on.
""", encoding="utf-8")
    return p


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["status", "finish"])
    ap.add_argument("--url")
    ap.add_argument("--repo")
    ap.add_argument("--demo")
    a = ap.parse_args(argv)
    rel = load()
    if a.cmd == "status":
        left = unchecked_must()
        print(f"{rel['name']} {rel['version']}: finished={rel['finished']} url={rel.get('url')} repo={rel.get('repo')}")
        print(f"launch checklist MUST items left: {len(left)}")
        for l in left:
            print("  - [ ] " + l)
        return 0
    if not a.url or not re.match(r"^https://", a.url):
        print("finish needs --url https://... (the product's public address)")
        return 2
    left = unchecked_must()
    if left:
        print(f"REFUSED: {len(left)} MUST item(s) of docs/LAUNCH-CHECKLIST.md are unchecked:")
        for l in left:
            print("  - [ ] " + l)
        return 1
    rel.update({"finished": True, "finishedAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "url": a.url, "repo": a.repo or rel.get("repo"), "demoUrl": a.demo or rel.get("demoUrl")})
    RELEASE.write_text(json.dumps(rel, ensure_ascii=False, indent=1), encoding="utf-8")
    ENTRY.write_text(json.dumps(entry(rel), ensure_ascii=False, indent=1), encoding="utf-8")
    p = notice(rel)
    print(f"FINISHED: release.json updated, {ENTRY.name} written, broadcast notice {p} - the Lojalumas agent adds the portfolio card on its next prompt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
