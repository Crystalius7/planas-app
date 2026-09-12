"""notify.py - what is new since the last scan (the personal notify.py's diff, without the e-mail and without acting).

The product must tell the student when new material, a new deadline, a notification or an announcement appears (owner
2026-09-12: "the notifications when new moodle material has been posted has to be there"). This module only DIFFS and
records; delivery (web push, e-mail through the API) is the app's job, and nothing is ever sent in the student's name.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .workspace import Workspace


def snapshot(ws: Workspace) -> dict:
    """Everything the student could notice: course ids, module ids per course, file names, section summaries, deadlines."""
    courses = {}
    for mf in sorted(ws.courses.glob("*/manifest.json")):
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        courses[str(m.get("id"))] = {
            "name": m.get("fullname"),
            "modules": {str(x["id"]): {"name": x.get("name"), "module": x.get("module"), "files": sorted(x.get("files") or []), "section": x.get("section")}
                        for x in m.get("modules", [])},
            "sections": {s.get("title", ""): (s.get("summary") or "")[:2000] for s in m.get("sections", [])},
        }
    deadlines = {str(d.get("id") or d.get("when", "") + (d.get("title") or "")): d for d in ws.read("deadlines.json").get("deadlines", [])}
    return {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "courses": courses, "deadlines": deadlines}


def diff(prev: dict, cur: dict) -> list[dict]:
    """Human-readable change records, newest scan first; kinds: course, module, file, section, deadline, deadline-moved."""
    out = []
    pc, cc = prev.get("courses", {}), cur.get("courses", {})
    for cid, c in cc.items():
        if cid not in pc:
            out.append({"kind": "course", "course": c["name"], "text": c["name"], "courseId": cid})
            continue
        p = pc[cid]
        for mid, m in c["modules"].items():
            if mid not in p["modules"]:
                out.append({"kind": "module", "course": c["name"], "courseId": cid, "moduleId": mid, "module": m["module"], "text": m["name"], "section": m.get("section")})
            else:
                new_files = sorted(set(m["files"]) - set(p["modules"][mid]["files"]))
                for f in new_files:
                    out.append({"kind": "file", "course": c["name"], "courseId": cid, "moduleId": mid, "text": f, "section": m.get("section")})
        for title, summary in c["sections"].items():
            if summary and summary != p["sections"].get(title, ""):
                out.append({"kind": "section", "course": c["name"], "courseId": cid, "text": title, "section": title})
    pd, cd = prev.get("deadlines", {}), cur.get("deadlines", {})
    for k, d in cd.items():
        if k not in pd:
            out.append({"kind": "deadline", "course": d.get("course"), "courseId": d.get("courseId"), "text": d.get("title"), "when": d.get("when"), "url": d.get("url")})
        elif pd[k].get("when") != d.get("when"):
            out.append({"kind": "deadline-moved", "course": d.get("course"), "courseId": d.get("courseId"), "text": d.get("title"), "when": d.get("when"), "was": pd[k].get("when"), "url": d.get("url")})
    return out


def watch(ws: Workspace) -> dict:
    """Take a snapshot, diff it against the last one, append the changes to state/notifications.json. First run = baseline."""
    state_p = ws.state / "notify-state.json"
    log_p = ws.state / "notifications.json"
    prev = json.loads(state_p.read_text(encoding="utf-8")) if state_p.exists() else None
    cur = snapshot(ws)
    changes = diff(prev, cur) if prev is not None else []
    state_p.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")
    log = json.loads(log_p.read_text(encoding="utf-8")) if log_p.exists() else {"items": []}
    stamp = cur["at"]
    for ch in changes:
        ch["at"] = stamp
        ch["read"] = False
    log["items"] = (changes + log["items"])[:500]
    log_p.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"baseline": prev is None, "changes": changes, "at": stamp}


def unread(ws: Workspace) -> list[dict]:
    log_p = ws.state / "notifications.json"
    if not log_p.exists():
        return []
    return [i for i in json.loads(log_p.read_text(encoding="utf-8")).get("items", []) if not i.get("read")]


def mark_read(ws: Workspace, before: str | None = None):
    log_p = ws.state / "notifications.json"
    if not log_p.exists():
        return
    log = json.loads(log_p.read_text(encoding="utf-8"))
    for i in log.get("items", []):
        if before is None or i.get("at", "") <= before:
            i["read"] = True
    log_p.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")


def mark_read_items(ws: Workspace, keys: list[tuple]):
    """Mark only the listed changes read: keys are (at, kind, courseId, text) tuples (glance 2026-09-12: never acknowledge
    a change that was not incorporated)."""
    log_p = ws.state / "notifications.json"
    if not log_p.exists() or not keys:
        return
    wanted = {tuple(str(x) for x in k) for k in keys}
    log = json.loads(log_p.read_text(encoding="utf-8"))
    for i in log.get("items", []):
        if (str(i.get("at")), str(i.get("kind")), str(i.get("courseId")), str(i.get("text"))) in wanted:
            i["read"] = True
    log_p.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")


def new_material_for_topics(ws: Workspace) -> list[dict]:
    """The 'add new material' button (owner 2026-09-12: "dynamically add the new material in a smart way, nicely fitting
    into what's already there"): unread module/file changes routed to the topic whose section they belong to, so the
    digest can EXTEND that topic instead of rebuilding it; anything unroutable is listed for the material map."""
    topics = ws.read("topics.json").get("subjects", {})
    by_section: dict[tuple[str, str], str] = {}
    for sid, s in topics.items():
        for t in s.get("topics", []):
            for sec in t.get("sections", []) or []:
                by_section[(str(s.get("courseId")), sec)] = t["id"]
    out = []
    for ch in unread(ws):
        if ch["kind"] not in ("module", "file", "section"):
            continue
        tid = by_section.get((str(ch.get("courseId")), ch.get("section") or ""))
        out.append({**ch, "topic": tid, "routed": tid is not None})
    return out
