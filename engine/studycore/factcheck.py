"""factcheck.py - the "certain facts beat the material" switch, OFF by default in the product.

The personal rule (owner 2026-09-12): a 100 %-certain fact replaces a wrong or outdated teacher fact everywhere, with the
teacher's version kept in the provenance field and every change recorded in `corrections` {was, now, where, basis}. In the
product this is a per-user switch because a student who is marked against the teacher's key may prefer the teacher's
wording (a school marks what it taught). The switch changes two things: the digest prompt (digest.py) and what the page
shows - with the switch OFF, `corrections` is emptied before rendering; with it ON, the page lists every correction with
its basis so the student can see what was changed and why.
"""
from __future__ import annotations

import json
from pathlib import Path

from .workspace import Workspace


def enabled(ws: Workspace) -> bool:
    return bool(ws.settings.get("factCheck"))


def set_enabled(ws: Workspace, on: bool) -> bool:
    ws.update_settings(factCheck=bool(on))
    return bool(on)


def apply(ws: Workspace, content: dict) -> dict:
    """Return the content as it should be rendered for this user."""
    out = dict(content)
    if not enabled(ws):
        out["corrections"] = []
        out["teacherVersion"] = True
    return out


def corrections(ws: Workspace) -> list[dict]:
    """Every correction on every built topic, for the settings page (what the switch would change)."""
    rows = []
    for cp in sorted(ws.study.glob("*/*.json")):
        if cp.name in ("settings.json",) or cp.name.endswith(".units.json") or cp.name.endswith(".build.json"):
            continue
        try:
            d = json.loads(cp.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if not isinstance(d, dict) or not d.get("topic"):
            continue
        for c in d.get("corrections", []) or []:
            rows.append({"topic": d["topic"], "subject": d.get("subject"), **{k: c.get(k) for k in ("was", "now", "where", "basis")}})
    return rows
