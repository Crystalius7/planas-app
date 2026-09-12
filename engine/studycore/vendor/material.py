#!/usr/bin/env python
"""material.py - nothing on Moodle is missed: every module and video that feeds a test or exam is accounted for.

WHY. Owner 2026-09-10: "make sure you don't miss any learning material for each test/exam, including video."

    python tools/material.py audit [--all]      # upcoming assessments -> their topics -> modules/videos accounted or not
    python tools/material.py items TOPIC        # every item of one topic with its verdict and the local file to read
    python tools/material.py unmapped           # modules no rule covers, or posted since the last accept
    python tools/material.py accept             # after checking new modules' routes: record every mapped module as known
    python tools/material.py hook               # one line when material for an upcoming assessment is unaccounted

HOW
  * study/material-map.json maps course sections (and, in a one-section course, the label a module sits under) to topic ids
    of study/topics.json, or to a `skip` reason for what is deliberately not studied (A lygis, a VBE the owner does not sit,
    course notices). First matching rule wins. A module no rule covers is UNMAPPED, so a newly posted module cannot slip by.
  * courses/<course>/INDEX.md lists every module in course order (## section; a label line acts as a sub-heading);
    courses/<course>/videos/index.json gives each video's id, state and reachability; a video embedded in a page belongs to
    that page's topic.
  * a BUILT topic (study/topics.json state "built") accounts for an item ONLY when study/material/<topic>.json holds a
    verdict written after reading the item against the page: used | checked (nothing examinable beyond the page) | skip
    (why) | unreachable WITH `replacement` = item keys of the same topic, each carrying a used/checked verdict, that cover the
    lost lesson (a free-text or unchecked replacement leaves it UNREACHABLE = unresolved). `missing` (a gap still to fold into
    the page) stays unaccounted. A required input that is missing, malformed or structurally empty stops the check loudly
    ("MATERIAL INPUT BROKEN"), never reads as nothing to report.
    Material filed under the wrong section is routed to its real topic by a map rule, never just skipped with a note.
    A citation in the content JSON (video id, file name, page id or the module's full name) alone is only CITED: the page's
    author used the item, but whether ALL its examinable content reached the page is unverified (reviewer 2026-09-10: a
    source list can name a 30-minute video one timestamp was taken from).
  * a topic in any other state is NOT BUILT: all its items wait for its page; the audit names the first assessment it feeds.
No network, no model: it reads the mirror only, so it is cheap enough for the per-prompt hook.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

ROOT = Path(__file__).resolve().parent.parent
STUDY = ROOT / "study"
COURSES = ROOT / "courses"
MAP = STUDY / "material-map.json"
TOPICS = STUDY / "topics.json"
ASSESS = STUDY / "assessments.json"
LEDGER = STUDY / "material"
KNOWN = STUDY / "material-known.json"   # modules a human has seen routed; anything newer is UNMAPPED (python tools/material.py accept)

MOD = re.compile(r"^- \*\*(.+?)\*\* \((\w+)\)(?: → (.+))?$")
HOOK_HORIZON_DAYS = 100     # the hook names unbuilt topics whose first test is this close; later exams are only counted


def read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (ValueError, OSError):
        return {}


class InputError(Exception):
    """A required input is missing or malformed: the check must say so, never look like 'nothing to report'."""


def read_required(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise InputError(f"{p}: {type(e).__name__}: {e}") from e


def replacement_keys(v: dict) -> list[str]:
    """An `unreachable` item's `replacement`: item keys of the SAME topic (exactly as `items` prints them) that cover the lost
    lesson. It clears the item only when every key exists and itself carries a used/checked verdict (reviewer 2026-09-10,
    round 3: a free-text or unchecked replacement could hide the gap)."""
    r = v.get("replacement")
    keys = [r] if isinstance(r, str) else (r if isinstance(r, list) else [])
    return [k.strip() for k in keys if isinstance(k, str) and k.strip()]


def norm(s: str) -> str:
    s = re.sub(r"<[^>]+>|&nbsp;|&[a-z]+;", " ", s or "")
    s = re.sub(r"[\"'„“”‘’«»(),.:;!?\-–—_/\\]+", " ", s.casefold())
    return re.sub(r"\s+", " ", s).strip()


def video_id(url: str) -> str | None:
    m = re.search(r"(?:youtu\.be/|[?&]v=|/embed/)([\w-]{11})", url or "")
    if m:
        return "yt-" + m.group(1)
    m = re.search(r"loom\.com/(?:share|embed)/([0-9a-f]{12})", url or "")
    return "loom-" + m.group(1) if m else None


def parse_index(cdir: Path) -> list[dict]:
    """Every module of a mirrored course in course order, with its section and the label it sits under."""
    out, sec, label = [], None, None
    p = cdir / "INDEX.md"
    if not p.exists():
        raise InputError(f"{p}: a mapped course has no INDEX.md (mirror missing?)")
    for ln in p.read_text(encoding="utf-8").splitlines():
        if ln.startswith("## "):
            sec, label = ln[3:].strip(), None
            continue
        m = MOD.match(ln.strip()) if ln.lstrip().startswith("- **") else None
        if not m or sec is None:
            continue
        name, kind, target = m.group(1).strip(), m.group(2), (m.group(3) or "").strip()
        if kind == "label":
            label = name
            continue
        out.append({"section": sec, "label": label, "name": name, "kind": kind, "target": target})
    return out


def load_videos(cdir: Path) -> dict[str, dict]:
    p = cdir / "videos" / "index.json"
    d = read_required(p) if p.exists() else {}
    items = d.get("videos", d) if isinstance(d, dict) else {}
    items = list(items.values()) if isinstance(items, dict) else items
    return {v["id"]: v for v in items if isinstance(v, dict) and v.get("id")}


def item_key(it: dict) -> str:
    t = it["target"]
    vid = video_id(t)
    if vid:
        return "video:" + vid
    if t.startswith("files/"):
        return "file:" + t[6:]
    m = re.match(r"pages/(\d+)-", t)
    if m:
        return f"{it['kind']}:{m.group(1)}"
    if t.startswith("http"):
        return "url:" + t
    return f"{it['kind']}:{norm(it['name'])[:60]}"


def rule_for(it: dict, rules: list[dict]) -> dict | None:
    for r in rules:
        if norm(r["section"]) != norm(it["section"]):
            continue
        if r.get("label") and not norm(it["label"] or "").startswith(norm(r["label"])):
            continue
        if r.get("match") and not (re.search(r["match"], it["name"], re.I) or re.search(r["match"], it["target"], re.I)):
            continue
        if r.get("kind") and not re.fullmatch(r["kind"], it["kind"]):
            continue
        return r
    return None


def collect() -> tuple[dict[str, list[dict]], list[dict]]:
    """topic id -> its items (modules + videos); and the unmapped modules."""
    mp = read_required(MAP)
    courses = mp.get("courses")
    if not isinstance(courses, dict) or not courses or not all(
            isinstance(c, dict) and isinstance(c.get("dir"), str) and isinstance(c.get("rules"), list) and c["rules"] for c in courses.values()):
        raise InputError(f"{MAP}: needs a non-empty `courses` object whose entries have `dir` and non-empty `rules`")
    if not KNOWN.exists():
        raise InputError(f"{KNOWN}: missing - check every module's route, then run python tools/material.py accept")
    known = read_required(KNOWN).get("courses")
    if not isinstance(known, dict):
        raise InputError(f"{KNOWN}: needs a `courses` object")
    by_topic: dict[str, list[dict]] = {}
    unmapped = []
    for cid, c in mp.get("courses", {}).items():
        cdir = COURSES / c["dir"]
        known_keys = set(known.get(cid, []))
        videos = load_videos(cdir)
        mods = parse_index(cdir)
        if not (cdir / "videos" / "index.json").exists() and any(video_id(m["target"]) for m in mods):
            raise InputError(f"{cdir / 'videos' / 'index.json'}: missing while the course links videos (run tools/video.py list)")
        page_topic: dict[str, str] = {}
        for it in mods:
            it["course"], it["cdir"] = cid, c["dir"]
            it["key"] = item_key(it)
            r = rule_for(it, c.get("rules", []))
            # a module posted after the last accept surfaces even when a section or label rule would route it (reviewer
            # 2026-09-10 round 5: the maths course's last label would silently swallow every newly appended module)
            if r is None or it["key"] not in known_keys:
                it["why"] = "no rule" if r is None else f"new since the last accept - rule would route it to {r.get('topic') or 'skip'}"
                unmapped.append(it)
                continue
            if r.get("skip"):
                continue
            vid = it["key"][6:] if it["key"].startswith("video:") else None
            if vid:
                v = videos.get(vid, {})
                it["video"] = {k: v.get(k) for k in ("state", "reachable", "transcript_file", "md", "probe_note")}
            by_topic.setdefault(r["topic"], []).append(it)
            m = re.match(r"(pages/\d+)-", it["target"])
            if m:
                page_topic[m.group(1)] = r["topic"]
        for v in videos.values():   # a video embedded in a page belongs to that page's topic
            m = re.match(r"(pages/\d+)-", v.get("found_in") or "")
            if m and m.group(1) in page_topic:
                t = page_topic[m.group(1)]
                key = "video:" + v["id"]
                if not any(x["key"] == key for x in by_topic[t]):
                    by_topic[t].append({"course": cid, "cdir": c["dir"], "section": v.get("section"), "label": None,
                                        "name": v.get("title") or v["id"], "kind": "video-in-page", "target": v.get("url", ""),
                                        "key": key, "video": {k: v.get(k) for k in ("state", "reachable", "transcript_file", "md", "probe_note")}})
    return by_topic, unmapped


def topic_meta() -> dict[str, dict]:
    out = {}
    subjects = read_required(TOPICS).get("subjects")
    if not isinstance(subjects, dict) or not subjects:
        raise InputError(f"{TOPICS}: needs a non-empty `subjects` object")
    for sj, s in subjects.items():
        for t in s.get("topics", []):
            out[t["id"]] = {**t, "subject": sj}
    return out


def content_text(meta: dict) -> str:
    """The content JSON a topic's page is generated from: study/topics.json `content` when the name differs (biology's
    virskinimas.html is built from vbe-virskinimas.json), else <page stem>.json."""
    page = meta.get("page") or ""
    src = meta.get("content") or (page[:-5] + ".json" if page.endswith(".html") else page)
    p = ROOT / src if src else None
    try:
        return p.read_text(encoding="utf-8") if p and p.exists() else ""
    except OSError:
        return ""


def cited(it: dict, raw: str, ntext: str) -> bool:
    kind, _, val = it["key"].partition(":")
    if kind == "video":
        return val in raw
    if kind == "file":
        stem = val.rsplit(".", 1)[0]
        near = lambda s: re.search(r"(?<![0-9a-z])" + re.escape(s) + r"(?![0-9a-z])", ntext) is not None  # noqa: E731  (lesson1 != lesson16)
        return near(norm(val)) or (len(norm(stem)) >= 6 and near(norm(stem)))
    if val.isdigit() and re.search(r"(?:\bid|pages?/|cmid|quiz|assign)\W{0,3}" + val + r"\b", raw):
        return True
    n = norm(it["name"])
    return len(n) >= 12 and n in ntext


def verdicts(topic: str) -> dict[str, dict]:
    p = LEDGER / f"{topic}.json"
    return read_required(p).get("items", {}) if p.exists() else {}


def account(topic: str, items: list[dict], meta: dict) -> list[dict]:
    """Each item with `status`: used (cited) | a ledger verdict | UNACCOUNTED | NOT BUILT."""
    built = meta.get("state") == "built"
    raw = content_text(meta) if built else ""
    ntext = norm(raw)
    led = verdicts(topic)
    out = []
    for it in items:
        v = led.get(it["key"], {})
        if not built:
            st = "NOT BUILT"
        elif v.get("verdict") == "used" or (v.get("verdict") in ("checked", "skip") and len(str(v.get("note") or "").strip()) >= 10):
            st = v["verdict"]   # checked/skip must say what was inspected and why (reviewer 2026-09-10, round 6)
        elif v.get("verdict") == "unreachable":
            st = "UNREACHABLE"
        elif cited(it, raw, ntext):
            st = "CITED"
        else:
            st = "UNACCOUNTED"
        out.append({**it, "status": st, "note": v.get("note", ""), "verdict": v.get("verdict")})
    verified = {r["key"] for r in out if r["status"] in ("used", "checked")}
    for r in out:
        reps = replacement_keys(led.get(r["key"], {}))
        if r["status"] == "UNREACHABLE" and reps and all(k in verified for k in reps):
            r["status"] = "unreachable"
    return out


def upcoming(today: dt.date, include_all: bool = False) -> list[dict]:
    reg = read_required(ASSESS).get("assessments")
    if not isinstance(reg, list):
        raise InputError(f"{ASSESS}: needs an `assessments` list")
    tm = topic_meta()
    out = []
    for a in sorted(reg, key=lambda x: x["date"]):
        if not include_all and a["date"][:10] < today.isoformat():
            continue
        ids = list(dict.fromkeys(list(a.get("topics", [])) + list(a.get("readyIds", [])) +
                                 [tid for tid, t in tm.items() if a["id"] in (t.get("feeds") or [])]))
        out.append({**a, "_topics": ids})
    return out


def summarise(rows: list[dict]) -> dict[str, int]:
    c: dict[str, int] = {}
    for r in rows:
        c[r["status"]] = c.get(r["status"], 0) + 1
    return c


def cmd_audit(include_all: bool):
    by_topic, unmapped = collect()
    tm = topic_meta()
    today = dt.date.today()
    for a in upcoming(today, include_all):
        print(f"\n{a['date']} {a['subjectName']} - {a['title']} [{a['kind']}]")
        for tid in a["_topics"]:
            meta = tm.get(tid, {"state": "unknown"})
            rows = account(tid, by_topic.get(tid, []), meta)
            vids = [r for r in rows if r["key"].startswith("video:")]
            dead = sum(1 for r in vids if (r.get("video") or {}).get("reachable") is False)
            c = summarise(rows)
            print(f"  {tid:<24} {meta.get('state', '?'):<8} items {len(rows):>3} (videos {len(vids)}, dead {dead}) " +
                  " ".join(f"{k} {v}" for k, v in sorted(c.items())))
    if unmapped:
        print(f"\nUNMAPPED modules: {len(unmapped)}")
        for it in unmapped[:40]:
            print(f"  [{it['cdir'][:12]}] {it['section'][:30]} | {(it['label'] or '')[:20]} | {it['kind']} | {it['name'][:60]} | {it.get('why', '')}")


def cmd_items(topic: str):
    by_topic, _ = collect()
    meta = topic_meta().get(topic, {})
    for r in account(topic, by_topic.get(topic, []), meta):
        vid = r.get("video") or {}
        local = ""
        if r["key"].startswith("video:"):
            vdir = f"courses/{r['cdir']}/videos/"
            local = " | ".join(x for x in (vdir + vid["md"] if vid.get("md") else "", vdir + vid["transcript_file"] if vid.get("transcript_file") else "") if x)
            local = local or f"state={vid.get('state')} reachable={vid.get('reachable')}"
        elif r["target"].startswith(("pages/", "files/")):
            local = f"courses/{r['cdir']}/{r['target']}"
        else:
            local = r["target"]
        print(f"{r['status']:<11} {r['key']} | {r['kind']} | {r['name'][:70]} | {local}" + (f" | note: {r['note']}" if r["note"] else ""))


def cmd_unmapped():
    _, unmapped = collect()
    for it in unmapped:
        print(f"[{it['cdir']}] {it['section']} | {it['label'] or ''} | {it['kind']} | {it['name']} | {it['target']} | {it.get('why', '')}")
    print(f"{len(unmapped)} unmapped")


def cmd_accept():
    """Record every module that a rule maps (topic or skip) as known. Run it only after checking the route of each module the
    audit listed as new; modules no rule covers stay unmapped and are listed."""
    mp = read_required(MAP)
    out, no_rule = {}, []
    for cid, c in mp.get("courses", {}).items():
        keys = set()
        for it in parse_index(COURSES / c["dir"]):
            if rule_for(it, c.get("rules", [])) is None:
                no_rule.append(f"[{c['dir']}] {it['section']} | {it['kind']} | {it['name']}")
            else:
                keys.add(item_key(it))
        out[cid] = sorted(keys)
    KNOWN.write_text(json.dumps({"_doc": "Modules whose route a human checked (tools/material.py accept); a module missing here is UNMAPPED.",
                                 "acceptedAt": dt.datetime.now().isoformat(timespec="minutes"), "courses": out},
                                ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"accepted {sum(len(v) for v in out.values())} modules")
    if no_rule:
        print(f"{len(no_rule)} modules still match no rule - add rules:", *no_rule, sep="\n  ")


def cmd_hook():
    try:
        if not MAP.exists():
            raise InputError(f"{MAP}: missing")
        by_topic, unmapped = collect()
        tm = topic_meta()
        today = dt.date.today()
        gaps: dict[str, int] = {}
        unbuilt: dict[str, str] = {}   # topic -> date of the first assessment it feeds
        for a in upcoming(today):
            for tid in a["_topics"]:
                meta = tm.get(tid, {})
                rows = account(tid, by_topic.get(tid, []), meta)
                if meta.get("state") == "built":
                    n = sum(1 for r in rows if r["status"] in ("UNACCOUNTED", "CITED", "UNREACHABLE"))
                    if n:
                        gaps[tid] = n
                elif rows and tid not in unbuilt:
                    unbuilt[tid] = a["date"][:10]
        parts = []
        if gaps:
            parts.append(f"{sum(gaps.values())} Moodle items/videos of built topics not yet checked against their pages (" +
                         ", ".join(f"{k} {v}" for k, v in sorted(gaps.items(), key=lambda x: -x[1])) + ")")
        horizon = (today + dt.timedelta(days=HOOK_HORIZON_DAYS)).isoformat()
        near = sorted((d, t) for t, d in unbuilt.items() if d <= horizon)
        later = len(unbuilt) - len(near)
        if near:
            parts.append(f"posted but no page yet, needed within {HOOK_HORIZON_DAYS} d: " + ", ".join(f"{t} (test {d})" for d, t in near) +
                         (f"; {later} more topics for later exams" if later else ""))
        elif later:
            parts.append(f"{later} topics for later exams have material but no page yet")
        if unmapped:
            parts.append(f"{len(unmapped)} modules have no checked route - new on Moodle or no rule (python tools/material.py unmapped, then accept)")
        if parts:
            full = "MATERIAL: " + "; ".join(parts) + " - python tools/material.py audit"
            # through the shared digest (hook budget 2026-09-11): the full line only when it changed for this session
            try:
                import sys as _sys
                from pathlib import Path as _Path
                _sys.path.insert(0, str(_Path.home() / ".claude" / "tools"))
                from hookdigest import emit as _emit
                # the short line still names every outstanding risk (glance 2026-09-11): unmapped modules included
                _emit("material", full, f"MATERIAL: {sum(gaps.values())} items unchecked, {len(unbuilt)} topics unbuilt, {len(unmapped)} modules unmapped - unchanged (python tools/material.py audit)")
            except Exception as exc:  # fail open, but say why on stderr so a broken digest is not silent
                print(full)
                print(f"material hook digest unavailable: {type(exc).__name__}: {exc}", file=sys.stderr)
    except InputError as e:
        print(f"MATERIAL INPUT BROKEN: {e} - the nothing-missed check is NOT running until this file is fixed")
    except Exception as e:  # noqa: BLE001
        print(f"MATERIAL hook failed: {type(e).__name__}: {e}")


def main(argv: list[str]):
    try:
        run(argv)
    except InputError as e:
        print(f"MATERIAL INPUT BROKEN: {e}")
        sys.exit(1)


def run(argv: list[str]):
    cmd = argv[0] if argv else "audit"
    if cmd == "audit":
        cmd_audit("--all" in argv)
    elif cmd == "items" and len(argv) > 1:
        cmd_items(argv[1])
    elif cmd == "unmapped":
        cmd_unmapped()
    elif cmd == "accept":
        cmd_accept()
    elif cmd == "hook":
        cmd_hook()
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
