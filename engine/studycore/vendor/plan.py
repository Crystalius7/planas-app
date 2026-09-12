#!/usr/bin/env python
"""plan.py - the daily study planner: 3 x 5 minutes a day, only for IN-PERSON tests and exams.

WHY. Owner 2026-09-09: "calculate the total needed material to pass in-person tests and exams, and based on
the test dates split them into tiny parts depending on how many days I have left ... morning, afternoon and
evening, 5 min three times a day ... at least 90 % learned ... leave a couple of days before the test for
cards and test-imitation exercises, split too ... one day can have more than one subject".
Owner 2026-09-10: "let's start studying from today. this afternoon will be the start" and "make sure you automatically
update the deadlines when new ones appear".

    python tools/plan.py plan  [--today YYYY-MM-DD]   # study/plan.json from study/assessments.json + study/*/*.units.json
    python tools/plan.py page                        # study/planas.html from study/plan.json + tools/planas.template.html
    python tools/plan.py build [--today ...]         # both (and the live file)
    python tools/plan.py report                      # coverage per assessment, days, free slots
    python tools/plan.py live                        # study/planas-live.json: deadlines + dates the published page re-reads from Drive
    python tools/plan.py hook                        # one line when the plan is stale / coverage below 90 % (prompt hook)

HOW IT SPLITS (all constants below are named so a reviewer can argue with them):
  * every day has three slots of SLOT_SEC seconds; a unit costs the seconds in its *.units.json;
  * the plan starts where the owner started (study/schedule.json: start date + first slot); earlier slots are
    "before-start" - never planned, never missed, never filled with catch-up;
  * for each upcoming assessment the LEARNING window runs from today to the day before its first imitation slot;
    IMITATION slots (quiz items, real VBE tasks, card sweeps) are dealt BACKWARDS from the test days, each slot to the
    test with the most practice seconds still unplaced, at most IMIT_MAX_DAYS back (imitation_calendar); the test
    morning itself is a short "pries testa" recap (mnemonics + numbers);
  * an online test the owner sits from home (kind "online-test") is a MILESTONE (owner 2026-09-10, question window:
    "Topic ready before each test"): it owns the learning of its topics so they are learned before its date, but gets
    no imitation and no recap of its own - the in-person įskaita keeps those, and no extra study time exists for it;
  * new material is spread over the learning window: quota per slot = total seconds still to learn
    (known units + a reservation for topics the teacher has not posted yet) / learning slots left, floored at
    MIN_NEW_SEC so every slot teaches at least one real thing, capped at the slot;
  * everything learned comes back for spaced retrieval after INTERVALS days (Cepeda et al. 2006), as short
    recall items, before new material in the slot;
  * when several assessments compete, the slot goes to the one with the highest pressure = seconds still
    needed / slots left before its window closes; leftover seconds go to the next one (mixed-subject slots);
  * coverage = weighted share of units that got a learning slot; below TARGET the hook says so and by how much;
  * STRETCH (owner 2026-09-10, question window "Up to 20 min/day"): when 3 x 5 minutes cannot give every posted unit of an
    IN-PERSON assessment its learning slot, the slots of that assessment's learning window grow a little (build_plan: the
    missing seconds spread evenly, doubled each round) up to SLOT_MAX_SEC; an online milestone never stretches a day;
  * a unit an earlier assessment could not fit is never dropped: the next one that examines it learns it (roll_over);
  * every day tab also lists the deadlines falling on it and the next ones, each with its clock time (load_deadlines);
    the same list goes to study/planas-live.json, which the PUBLISHED page re-reads from Google Drive, so a new Moodle
    deadline reaches the page without a republish (live_export).
Progress lives in the page (localStorage + the artifact db). With study/progress.json (the db doc pulled by the agent) a
past slot counts only when the owner marked it, and a slot already marked done TODAY is kept unchanged by a same-day
replan. Without it the planner assumes past slots were done; the page carries missed items forward itself. Days before
today are copied from the previous plan.json unchanged (they are history).
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import sys
from pathlib import Path

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

ROOT = Path(__file__).resolve().parent.parent
STUDY = ROOT / "study"
ASSESS = STUDY / "assessments.json"
PLAN = STUDY / "plan.json"
PAGE = STUDY / "planas.html"
TEMPLATE = ROOT / "tools" / "planas.template.html"
GRADES = STUDY / "grades.json"
PROGRESS = STUDY / "progress.json"   # optional: the artifact db doc progress/main, pulled by the agent
DEADLINES = STUDY / "deadlines.json"  # Moodle calendar action events with clock times, written by tools/moodle.py save_deadlines()
QUEUE = ROOT / "homework" / "queue.json"
SUBJECTS = STUDY / "subjects.json"
SCHEDULE = STUDY / "schedule.json"    # where the owner started: {"start": "YYYY-MM-DD", "startSlot": "rytas|diena|vakaras"}
LIVE = STUDY / "planas-live.json"     # what the published page re-reads from Google Drive (live_export)
NOTIFY_STATE = ROOT / ".notify-state.json"

SLOTS = ["rytas", "diena", "vakaras"]
SLOT_SEC = 300              # the normal slot: 3 x 5 minutes a day
SLOT_MAX_SEC = 380          # owner 2026-09-10 "Up to 20 min/day": a stretched slot plus fill_slot's 20-s packing tolerance stays <= 400 s
GROW_ROUNDS = 6             # build_plan() re-plans at most this many times while stretching
MIN_NEW_SEC = 70            # at least one ranked question (or two hooks) of new material per learning slot
REVIEW_SEC = 15             # one spaced-recall item
REVIEW_SHARE = 0.5          # at most half a slot is review, counted for the WHOLE slot (audit 2026-09-12: per part, two subjects filled slots with reviews alone)
IMIT_REVIEW_SEC = 60        # every imitation slot keeps this much (4 recalls) for due reviews of the learned core (audit 2026-09-12: "budget = 0" silenced reviews for 3 weeks); a paragraph chain stage may still take the whole slot
EARLY_MIN_SEC = 25          # the early practice pass: leftover slot seconds show each imitation unit once BEFORE the final window (audit 2026-09-12: 309 units seen once)
PROGRESS_STALE_H = 20       # progress.json older than this once studying has started = not pulled from the page's db; a build refuses (collab 2026-09-12: freshness = the pull time)
INTERVALS = [1, 3, 7, 14, 30, 60, 90, 120]
TARGET = 0.90
NEW_TYPES = ("question", "hook", "number")
DEFAULT_TOPIC_SEC = 8000    # reservation for a topic whose material is not on Moodle yet (~ the digestion topic)
IMIT_MAX_DAYS = 21          # how far back imitation for a test day may reach when several tests share the days before it
IMIT_MARGIN = 1.15          # bucket packing loses a little to fragmentation (90-s VBE tasks into 300-s slots)
LIVE_REFRESH_H = 4          # an unchanged live file is rewritten only when the Moodle check time moved on by this much
LT_DOW = ["Pr", "An", "Tr", "Kt", "Pn", "Št", "Sk"]


def d2s(d: dt.date) -> str:
    return d.isoformat()


def s2d(s: str) -> dt.date:
    return dt.date.fromisoformat(s[:10])


def read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (ValueError, OSError):
        return {}


def load_units() -> dict[str, dict]:
    topics = {}
    for f in sorted(STUDY.glob("*/*.units.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        topics[d["topic"]] = d
    return topics


def priority_order(units: list[dict]) -> list[dict]:
    """Questions by probability, each followed by the hooks it cites; then the remaining hooks in room order; then numbers."""
    by_kw = {u["kw"]: u for u in units if u["type"] == "hook"}
    out, seen = [], set()
    # owner 2026-09-12 ("base all math learning around calculators"): the calculator routines are learned FIRST, one after
    # each of the top task types, so the keys are in the fingers before the tasks that need them
    calc = [u for u in units if u.get("kind") == "calc"]
    for q in sorted((u for u in units if u["type"] == "question"), key=lambda u: -u["w"]):
        out.append(q); seen.add(q["id"])
        for kw in q.get("hooks", []):
            h = by_kw.get(kw)
            if h and h["id"] not in seen:
                out.append(h); seen.add(h["id"])
        if calc:
            c = calc.pop(0); out.append(c); seen.add(c["id"])
    for c in calc:
        out.append(c); seen.add(c["id"])
    for h in (u for u in units if u["type"] == "hook"):
        if h["id"] not in seen:
            out.append(h); seen.add(h["id"])
    for n in sorted((u for u in units if u["type"] == "number"), key=lambda u: -u["w"]):
        out.append(n); seen.add(n["id"])
    # owner 2026-09-10, question window "Priority cards only": a card marked `learn` (the teachers' own lists - spelling
    # dictation, translation-test words, quotes, spelling rules) is daily material, spread evenly through the order above
    learn = [u for u in units if u["type"] == "card" and u.get("learn") and u["id"] not in seen]
    if learn:
        step = max(1, len(out) // len(learn))
        mixed = []
        for i, u in enumerate(out):
            mixed.append(u)
            if (i + 1) % step == 0 and learn:
                mixed.append(learn.pop(0))
        out = mixed + learn
    return out


def load_deadlines(assessments: list[dict]) -> list[dict]:
    """Every dated deadline a day tab shows, with its clock time (owner 2026-09-10: "always show deadlines with times in each
    learning day"). Sources: study/deadlines.json (Moodle's calendar, exact times), homework/queue.json (a home task the agent
    does, and when it will send it) and study/assessments.json (tests and exams; `time` where a source states it or last year's
    real schedule approximates it - the page prints an estimated one as ~HH:MM).
    A Moodle due time of 00:00 belongs to the PREVIOUS evening: it is listed as 24:00 on the day before, because a student who
    opens the 5th's tab and reads "00:00" has already missed it."""
    def when(iso: str) -> tuple[str, str]:
        t = dt.datetime.fromisoformat(iso)
        if (t.hour, t.minute) == (0, 0):
            return d2s(t.date() - dt.timedelta(days=1)), "24:00"
        return d2s(t.date()), f"{t:%H:%M}"

    subjects = {str(s.get("courseId")): s for s in read_json(SUBJECTS).get("subjects", [])}
    queue = {str(it["cmid"]): it for it in read_json(QUEUE).get("items", []) if it.get("cmid")}
    out, used, cal_cm = [], set(), set()
    for e in read_json(DEADLINES).get("events", []):
        m = re.search(r"[?&]id=(\d+)", e.get("url") or "")
        if m and (e.get("eventtype") or "") != "open":   # an opening event must not hide the estimated deadline
            cal_cm.add(m.group(1))
        q = queue.get(m.group(1)) if (m and e.get("module") == "assign") else None
        s = subjects.get(str(e.get("courseId")), {})
        day, clock = when(e["due"])
        out.append({"id": f"moodle-{e['id']}", "date": day, "time": clock, "due": e["due"],
                    "subject": s.get("slug", ""), "subjectName": s.get("name", e.get("course", "")),
                    "title": re.sub(r"\s+turi būti pateikta$", "", e.get("name", "")),
                    "kind": "quiz-open" if (e.get("eventtype") or "") == "open" else (e.get("module") or "moodle"),
                    "confidence": "confirmed", "url": e.get("url", ""),
                    "who": "sistema" if q else "tu", "sendAt": (q or {}).get("sendAt"), "status": (q or {}).get("status")})
        if q:
            used.add(str(q["cmid"]))
    for cm, q in queue.items():   # a home task the last calendar fetch did not return still gets its row
        if cm in used or not q.get("due"):
            continue
        day, clock = when(q["due"])
        out.append({"id": q["id"], "date": day, "time": clock, "due": q["due"], "subject": q.get("subject", ""),
                    "subjectName": q.get("subjectName", ""), "title": q.get("title", ""), "kind": q.get("kind", "assign"),
                    "confidence": "confirmed", "url": q.get("url", ""), "who": "sistema",
                    "sendAt": q.get("sendAt"), "status": q.get("status")})
    for a in assessments:
        if a.get("cmid") and str(a["cmid"]) in cal_cm:
            continue   # Moodle now carries this quiz's real deadline: the calendar row is authoritative, the estimate must not show twice
        out.append({"id": a["id"], "date": a["date"][:10], "time": a.get("time"), "subject": a["subject"],
                    "subjectName": a["subjectName"], "title": a["title"], "kind": a["kind"],
                    "confidence": a.get("confidence", "estimated"), "who": "tu"})
    out.sort(key=lambda x: (x["date"], x["time"] or "99:99", x["subject"]))
    return out


def apply_calendar_dates(assessments: list[dict]) -> list[dict]:
    """An online test whose Moodle quiz (`cmid`) now has a calendar deadline is PLANNED for that date, not for the
    estimate (reviewer 2026-09-10, round 5) - the deadline strip, the assessment cards and the study schedule must agree.
    Topics and everything else stay; the date becomes confirmed and the source says where it came from."""
    due: dict[str, list[str]] = {}
    for e in read_json(DEADLINES).get("events", []):
        m = re.search(r"[?&]id=(\d+)", e.get("url") or "")
        if m and e.get("due") and (e.get("eventtype") or "") != "open":   # a quiz's OPENING time is not a deadline (reviewer round 6)
            due.setdefault(m.group(1), []).append(e["due"])
    for a in assessments:
        cm = str(a.get("cmid") or "")
        if cm in due:
            last = max(due[cm])   # a quiz can carry open and close events: the latest one is the deadline
            t = dt.datetime.fromisoformat(last)
            midnight = (t.hour, t.minute) == (0, 0)
            a["date"] = d2s(t.date() - dt.timedelta(days=1)) if midnight else d2s(t.date())
            a["time"] = "24:00" if midnight else f"{t:%H:%M}"
            a["confidence"] = "confirmed"
            a["source"] = (a.get("source") or "") + f" Moodle kalendorius: {last}."
    return assessments


class Planner:
    def __init__(self, today: dt.date, caps: dict | None = None, use_progress: bool = True):
        """`use_progress=False` (plan.py build --assume-done, glance 2026-09-12): the stale progress file is ignored entirely, so
        every past slot counts as done - exactly what the planner assumes when no file exists."""
        self.today = today
        self.caps: dict[tuple[str, int], int] = caps if caps is not None else {}   # (date, slot index) -> seconds; stretched slots only
        reg = json.loads(ASSESS.read_text(encoding="utf-8"))
        self.assessments = sorted(apply_calendar_dates(reg["assessments"]), key=lambda a: a["date"])
        sched = read_json(SCHEDULE)
        try:
            self.start = s2d(sched["start"]) if sched.get("start") else None
        except ValueError:
            self.start = None
        self.start_si = SLOTS.index(sched["startSlot"]) if sched.get("startSlot") in SLOTS else 0
        self.topics = load_units()
        self.units: dict[str, dict] = {}
        for t in self.topics.values():
            for u in t["units"]:
                self.units[u["id"]] = {**u, "topic": t["topic"], "subject": t["subject"]}
        self.prev = read_json(PLAN) or {"days": []}
        # REAL progress, when the agent pulled the page's db doc (Artifact read_db progress/main -> study/progress.json):
        # a past slot then counts as done only if the owner marked it, and its unfinished units return to the pool with
        # no age cutoff (reviewer 2026-09-09). Without the file the planner assumes past slots were done (the page
        # carries missed items forward on its own).
        self.progress = json.loads(PROGRESS.read_text(encoding="utf-8")) if (PROGRESS.exists() and use_progress) else None
        done = (self.progress or {}).get("done", {})
        self.seen_test: set[str] = set()   # units already shown in test mode (early practice or a final window) in counted history
        self.seen_test_day: dict[str, dt.date] = {}
        self.learned: dict[str, dt.date] = {}      # unit id -> day it was first taught
        self.completed_practice: dict[str, dt.date] = {}
        self.reviews_done: dict[str, int] = {}     # unit id -> reviews already placed in history
        self.next_review: dict[str, dt.date] = {}
        last_review: dict[str, dt.date] = {}
        review_days: dict[str, list[dt.date]] = {}
        restart_day: dict[str, dt.date] = {}
        self.restart_uids: set[str] = set()   # ladders restarted THIS build: their first review item gets the marker "r"
        self.history = [d for d in self.prev.get("days", []) if s2d(d["date"]) < today and not (self.start and s2d(d["date"]) < self.start)]
        # a slot the owner already finished TODAY stays exactly as it was studied when the plan is rebuilt the same day
        # (the page keys "done" by date|slot; new material or a new date can trigger a replan in the middle of the day)
        self.frozen: dict[str, dict] = {}
        if self.progress is not None:
            for d in self.prev.get("days", []):
                if d["date"] == d2s(today):
                    for sl in d["slots"]:
                        if (done.get(f"{d['date']}|{sl['slot']}") or 0) > 0 and sl.get("items"):
                            self.frozen[sl["slot"]] = sl
        for uid, ts in ((self.progress or {}).get("doneItems") or {}).items():   # catch-up items the page marked done (ms epoch, >0)
            if uid in self.units and isinstance(ts, (int, float)) and ts > 0:
                self.learned.setdefault(uid, dt.date.fromtimestamp(ts / 1000))
                if self.units[uid].get('chain'):
                    self.completed_practice[uid] = dt.date.fromtimestamp(ts / 1000)
        counted: list[tuple[str, dict]] = []
        for d in self.history:
            for sl in d["slots"]:
                if self.progress is not None and not (done.get(f"{d['date']}|{sl['slot']}") or 0) > 0:
                    continue   # never done: its new units stay unlearned and are rescheduled
                counted.append((d["date"], sl))
        counted += [(d2s(today), sl) for sl in self.frozen.values()]
        for date, sl in counted:
            for it in sl["items"]:
                if it['u'] in self.units and self.units[it['u']].get('chain'):
                    self.completed_practice[it['u']] = s2d(date)
                if it.get("mode") == "new" and it["u"] in self.units:
                    self.learned.setdefault(it["u"], s2d(date))
                elif it.get("mode") == "test" and it["u"] in self.units:
                    self.seen_test.add(it["u"])   # glance 2026-09-12: a completed exposure must not return to the "first pass" pool
                    self.seen_test_day[it["u"]] = max(self.seen_test_day.get(it["u"], dt.date.min), s2d(date))
                elif it.get("mode") == "review":
                    self.reviews_done[it["u"]] = self.reviews_done.get(it["u"], 0) + 1
                    last_review[it["u"]] = s2d(date)
                    review_days.setdefault(it["u"], []).append(s2d(date))
                    if it.get("r"):   # the first remedial review after a failure carries the restart marker (persisted in plan.json)
                        restart_day[it["u"]] = max(restart_day.get(it["u"], dt.date.min), s2d(date))
        for uid, day in self.learned.items():
            k = min(self.reviews_done.get(uid, 0), len(INTERVALS) - 1)
            base = last_review.get(uid, day)   # same calculation as place_review(): interval counts from the last review
            self.next_review[uid] = base + dt.timedelta(days=INTERVALS[k])
        self.review_k = {uid: self.reviews_done.get(uid, 0) for uid in self.learned}
        # adaptive spacing (audit 2026-09-12: intervals were fixed whatever the owner answered): a unit judged "Nemoku" AFTER its
        # last placed review restarts its ladder - due today, then +1/+3/+7 again - instead of waiting for the +14/+30 step
        rec = (self.progress or {}).get("rec") or {}
        for uid in list(self.learned):
            r = rec.get(uid) or {}
            fresh = None   # a failure judged AFTER the last placed review = a new restart
            # the page stamps every "Nemoku" as rec.failAt (glance round 8: a correct hub repeat before the rebuild flips lastOk back
            # to true, so the failure must be remembered on its own); older records without failAt fall back to lastOk + last
            fail_ms = r.get("failAt") if isinstance(r.get("failAt"), (int, float)) and (r.get("failAt") or 0) > 0 else \
                (r.get("last") if r.get("lastOk") is False and (r.get("bad") or 0) > 0 and isinstance(r.get("last"), (int, float)) and r["last"] > 0 else None)
            if fail_ms:
                failed_on = dt.date.fromtimestamp(fail_ms / 1000)
                if failed_on >= last_review.get(uid, self.learned[uid]):
                    fresh = failed_on
            marker = restart_day.get(uid)
            if not fresh and not marker:
                continue
            # the ladder restarts at the failure and is rebuilt from the reviews SINCE the restart, whatever the latest answer was
            # (glance 2026-09-12: counting lifetime reviews - or only while lastOk stayed false - restored the long interval later);
            # the restart survives rebuilds through the "r" marker on the first remedial review item in plan.json. A review on the
            # failure day itself is the one that FAILED, so it counts as before the restart (glance round 6).
            if fresh and (marker is None or fresh >= marker):
                since = [d for d in review_days.get(uid, []) if d > fresh]
                anchor = fresh
            else:
                since = [d for d in review_days.get(uid, []) if d >= marker]
                anchor = marker
            k = min(len(since), len(INTERVALS) - 1)
            self.review_k[uid] = k
            base = max(since) if since else anchor
            self.next_review[uid] = max(today, base + dt.timedelta(days=INTERVALS[k] if since else 1))
            if not since:
                self.restart_uids.add(uid)
        self.reviews_scheduled: dict[str, int] = dict(self.reviews_done)

    def before_start(self, day: dt.date, si: int) -> bool:
        return self.start is not None and (day < self.start or (day == self.start and si < self.start_si))

    def cap(self, day: dt.date, si: int) -> int:
        return self.caps.get((d2s(day), si), SLOT_SEC)

    # ---- per-assessment bookkeeping ------------------------------------------------------------------
    def prepare(self):
        self.upcoming = []
        owned: set[str] = set()
        for a in self.assessments:
            date = s2d(a["date"])
            if date < self.today:
                a["status"] = "past"; continue
            a["status"] = "upcoming"
            a["_milestone"] = a.get("kind") == "online-test"
            days_left = (date - self.today).days
            if a["_milestone"]:
                r = 0
            else:
                r = min(a.get("reviewDays", 2), max(0, days_left - 1)) if days_left >= 2 else 0
            a["_r"] = r   # imitation_calendar() moves it for every test that really gets imitation slots
            a["_imit_start"] = date - dt.timedelta(days=r)          # first imitation day
            a["_learn_end"] = a["_imit_start"] - dt.timedelta(days=1)  # last learning day
            units = [self.units[u["id"]] for t in a.get("topics", []) if t in self.topics for u in self.topics[t]["units"]]
            # the EARLIEST upcoming assessment that covers a unit owns its learning; later ones (the exam) only review it
            a["_new"] = [u for u in priority_order(units) if u["id"] not in self.learned and u["id"] not in owned]
            owned.update(u["id"] for u in a["_new"])
            a["_all_new"] = [u for u in units if u["type"] in NEW_TYPES or (u["type"] == "card" and u.get("learn")) or u.get("kind") == "calc"]
            usable = [u for u in units if u["type"] in ("practice", "quiz", "vbe", "card") and not (u.get("unmarked") or u.get("needsFigure") or u.get("learn") or u.get("hold") or u.get("kind") == "calc")]
            completed = {u['id'] for u in usable if u.get('chain') and
                         self.last_in_person_before(u['topic'], date) < self.completed_practice.get(u['id'], dt.date.min) <= self.today}
            a['_imit_completed'] = len(completed) if not a['_milestone'] else 0
            usable = [u for u in usable if u['id'] not in completed]
            a["_imit"] = [] if a["_milestone"] else usable
            a["_imit_skipped"] = 0 if a["_milestone"] else sum(1 for u in units if u["type"] == "vbe" and (u.get("unmarked") or u.get("needsFigure")))
            a["_covered"] = set(u["id"] for u in a["_all_new"] if u["id"] in self.learned)
            # the reservation for a topic the teacher has not posted yet is sized like the NEW share of the posted topics (audit
            # 2026-09-12: 0.6 x a whole topic's seconds reserved 2.6-7.9x too much, so learning ended by mid-October and then idled)
            tids = [tid for tid in a.get("topics", []) if tid in self.topics]
            new_known = sum(u["sec"] for tid in tids for u in self.topics[tid]["units"]
                            if u["type"] in NEW_TYPES or (u["type"] == "card" and u.get("learn")) or u.get("kind") == "calc")
            avg = (new_known / len(tids)) if tids and new_known else DEFAULT_TOPIC_SEC * 0.3
            a["_reserve_sec"] = len(a.get("waiting", [])) * avg
            # the early practice pass (audit 2026-09-12): once an in-person test's core is learned, leftover slot seconds show each of
            # its imitation units ONCE before the final window - a unit the final window cannot fit gets its exposure here
            # an exposure counts for this assessment only when it came after the previous in-person test of THAT UNIT's own topic
            # (glance round 10: one boundary from topics[0] dropped valid exposures of a multi-topic įskaita's other topics)
            seen = {u["id"] for u in a["_imit"] if u["id"] in self.seen_test and not u.get("chain")
                    and self.learned_test_after(u["id"], self.last_in_person_before(u["topic"], date))}
            a["_early"] = [] if a["_milestone"] else sorted((u for u in a["_imit"] if not u.get("chain") and u["id"] not in seen), key=lambda u: -u["w"])
            a["_early_placed"] = set() if a["_milestone"] else set(seen)
            a["_imit_ids"] = set()
            self.upcoming.append(a)

    def learned_test_after(self, uid: str, since: dt.date) -> bool:
        return self.seen_test_day.get(uid, dt.date.min) > since

    def last_in_person_before(self, topic: str, before: dt.date) -> dt.date:
        """A written paragraph counts for an assessment only when it came after the last earlier IN-PERSON test of THAT unit's
        own topic (reviewer 2026-09-10): a spelling-only test must not restart a prose paragraph already written, and an online
        milestone, which has no practice of its own, resets nothing."""
        return max((s2d(o["date"]) for o in self.assessments if s2d(o["date"]) < before
                    and o.get("kind") != "online-test" and topic in o.get("topics", [])), default=dt.date.min)

    def roll_over(self, day: dt.date):
        """A unit an earlier assessment could not fit before its learning window closed is not dropped: the next upcoming
        assessment that examines the same unit learns it first (owner 2026-09-10: "make sure you don't miss any learning material
        for each test/exam"). Before this, a unit an įskaita left over was never taught for the VBE either."""
        for i, a in enumerate(self.upcoming):
            if not a["_new"] or day <= a["_learn_end"]:
                continue
            for b in self.upcoming[i + 1:]:
                if day > b["_learn_end"]:
                    continue
                ids = {u["id"] for u in b["_all_new"]}
                take = [u for u in a["_new"] if u["id"] in ids]
                if take:
                    have = {u["id"] for u in b["_new"]}
                    b["_new"] = [u for u in take if u["id"] not in have] + b["_new"]
                    a["_new"] = [u for u in a["_new"] if u["id"] not in ids]
                if not a["_new"]:
                    break

    def grow(self, rnd: int) -> bool:
        """After a run: stretch the learning slots of every IN-PERSON assessment that left posted units untaught (owner 2026-09-10,
        question window "Up to 20 min/day"). The missing seconds are spread evenly over the slots of its learning window, doubled
        each round, never past SLOT_MAX_SEC; a slot before the start, a slot already finished today and an online milestone never
        stretch. Returns True when a cap moved, so build_plan() plans again."""
        grew = False
        first = max(self.today, self.start or self.today)
        for a in self.upcoming:
            if a["_milestone"] or a["_learn_end"] < first:
                continue
            need = sum(u["sec"] for u in a["_all_new"] if u["id"] not in a["_covered"])
            if not need:
                continue
            window = [(d, si) for n in range((a["_learn_end"] - first).days + 1) for d in [first + dt.timedelta(days=n)]
                      for si in range(len(SLOTS)) if not self.before_start(d, si) and not (d == self.today and SLOTS[si] in self.frozen)]
            if not window:
                continue
            inc = max(5, math.ceil(need * 2 ** rnd / len(window) / 5) * 5)
            for d, si in window:
                key = (d2s(d), si)
                new = min(SLOT_MAX_SEC, self.caps.get(key, SLOT_SEC) + inc)
                if new > self.caps.get(key, SLOT_SEC):
                    self.caps[key] = new
                    grew = True
        return grew

    def learn_slots_left(self, a: dict, day: dt.date, slot_i: int) -> int:
        if day > a["_learn_end"]:
            return 0
        return (a["_learn_end"] - day).days * len(SLOTS) + (len(SLOTS) - slot_i)

    def due_reviews(self, a: dict, day: dt.date) -> list[dict]:
        ids = {u["id"] for u in a["_all_new"]}
        due = [uid for uid, nd in self.next_review.items() if uid in ids and nd <= day]
        due.sort(key=lambda uid: (self.next_review[uid], -self.units[uid]["w"]))
        return [self.units[uid] for uid in due]

    def place_review(self, uid: str, day: dt.date):
        k = self.review_k.get(uid, 0) + 1
        self.review_k[uid] = k
        self.reviews_scheduled[uid] = self.reviews_scheduled.get(uid, 0) + 1
        if k < len(INTERVALS):
            self.next_review[uid] = day + dt.timedelta(days=INTERVALS[k])
        else:
            self.next_review.pop(uid, None)

    # ---- the loop ---------------------------------------------------------------------------------------
    def run(self) -> dict:
        self.prepare()
        horizon = max([s2d(a["date"]) for a in self.upcoming], default=self.today)
        days = []
        day = self.today
        cal = self.imitation_calendar()
        imit_plan = {a["id"]: self.split_imitation(a, cal[a["id"]]) for a in self.upcoming}
        while day <= horizon:
            self.roll_over(day)
            slots = []
            for si, name in enumerate(SLOTS):
                if self.before_start(day, si):
                    slots.append({"slot": name, "parts": [], "sec": 0, "phase": "before-start", "items": []})
                elif day == self.today and name in self.frozen:
                    slots.append(self.frozen[name])
                else:
                    slots.append(self.fill_slot(day, si, name, imit_plan))
            days.append({"date": d2s(day), "dow": LT_DOW[day.weekday()], "slots": slots})
            day += dt.timedelta(days=1)
        return self.assemble(days)

    def imitation_calendar(self) -> dict[str, list[tuple[str, int]]]:
        """ONE shared calendar, dealt BACKWARDS from the test days: each slot goes to the test with the most imitation seconds
        still unplaced among those whose day is ahead and at most IMIT_MAX_DAYS away, so tests that share a day share the
        days before it in proportion to their material. 2026-09-10: the old deal gave slot i of a day to owners[i % n]
        with i only 0..2, so with five įskaitos on one day the 4th and 5th never got a slot (English planned 0/56 items).
        A test day's morning slot is its recap, never imitation, and slots before the plan's start are skipped."""
        cal: dict[str, list[tuple[str, int]]] = {a["id"]: [] for a in self.upcoming}
        cands = [a for a in self.upcoming if a["_imit"]]
        if not cands:
            return cal
        left = {}
        for a in cands:
            must = [u for u in a["_imit"] if u["type"] != "vbe" or a["kind"] == "exam"]
            left[a["id"]] = sum(u["sec"] for u in must) * IMIT_MARGIN
        demand = dict(left)
        recap_days = {a["date"][:10] for a in self.upcoming if a.get("topics") and not a["_milestone"]}
        day = max(s2d(a["date"]) for a in cands) - dt.timedelta(days=1)
        while day >= self.today and any(v > 0 for v in left.values()):
            for si in reversed(range(len(SLOTS))):
                if day == self.today and self.frozen and si <= max(SLOTS.index(s) for s in self.frozen):
                    continue
                if (si == 0 and d2s(day) in recap_days) or self.before_start(day, si):
                    continue
                live = [a for a in cands if left[a["id"]] > 0 and day < s2d(a["date"]) and (s2d(a["date"]) - day).days <= IMIT_MAX_DAYS]
                if not live:
                    continue
                # Equalise the fraction of practice served, so a large essay bank cannot
                # consume the whole shared window before a smaller subject gets one slot.
                a = max(live, key=lambda x: (left[x["id"]] / max(1, demand[x["id"]]), -s2d(x["date"]).toordinal()))
                cal[a["id"]].append((d2s(day), si))
                left[a["id"]] -= self.cap(day, si)
            day -= dt.timedelta(days=1)
        for a in cands:
            if cal[a["id"]]:
                cal[a["id"]].sort()
                first = s2d(cal[a["id"]][0][0])
                a["_imit_start"] = first
                a["_r"] = (s2d(a["date"]) - first).days
                a["_learn_end"] = first - dt.timedelta(days=1)
        return cal

    def split_imitation(self, a: dict, slots: list[tuple[str, int]]) -> dict[str, dict[int, list[dict]]]:
        """Imitation material split evenly over the slots this assessment really owns; returns {date: {slot_i: items}}."""
        r = a["_r"]
        if r == 0 or not a["_imit"] or not slots:
            a["_imit_placed"], a["_imit_total"] = a.get('_imit_completed',0), len(a["_imit"])+a.get('_imit_completed',0)
            return {}
        nslots = len(slots)
        quiz = sorted((u for u in a["_imit"] if u["type"] == "quiz"), key=lambda u: -u["w"])
        vbe = sorted((u for u in a["_imit"] if u["type"] == "vbe"), key=lambda u: -u["points"] if isinstance(u.get("points"), (int, float)) else 0)
        cards = sorted((u for u in a["_imit"] if u["type"] == "card"), key=lambda u: -u["w"])
        drills = sorted((u for u in a["_imit"] if u["type"] == "practice"), key=lambda u: -u["w"])
        # Cycle through each topic and question type before taking more variants.
        # A large worked-drill bank must not hide every quiz or a smaller topic.
        banks = {}
        for group in ((vbe, drills, quiz) if a["kind"] == "exam" else (drills, quiz)):
            for u in group:
                banks.setdefault((u["type"], u.get("topic", "")), []).append(u)
        for key, bank in banks.items():   # inside a bank, one variant of every skill (`t`) before any second one (reviewer 2026-09-10)
            seen: dict[str, int] = {}
            ranked = []
            for n, u in enumerate(bank):
                k = seen.get(u.get("t", ""), 0)
                seen[u.get("t", "")] = k + 1
                ranked.append((k, n, u))
            banks[key] = [u for _, _, u in sorted(ranked, key=lambda x: (x[0], x[1]))]
        order = [bank[i] for i in range(max((len(b) for b in banks.values()), default=0))
                 for bank in banks.values() if i < len(bank)]
        if a["kind"] != "exam":
            cards = cards + vbe   # real exam tasks are a bonus after the cards in a trimester test
        budgets = [self.cap(s2d(d), si) for d, si in slots]   # chains first against the whole slot; the reserve for reviews is taken after them
        buckets: list[list[dict]] = [[] for _ in range(nslots)]
        chains = {}
        for u in drills:
            if u.get('chain'):
                chains.setdefault((u.get('topic', ''), u['chain']), []).append(u)
        for chain in chains.values():
            chain.sort(key=lambda u: u['stage'])
            trial = budgets.copy(); placed = []; after = 0
            for u in chain:
                j = next((j for j in range(after, nslots) if trial[j] >= u['sec']), None)
                if j is None:
                    break
                trial[j] -= u['sec']; placed.append((j,u)); after = j + 1
            if len(placed) == len(chain):
                budgets = trial
                for j,u in placed:
                    buckets[j].append({'u':u['id'], 'mode':'test'})
        # Incomplete paragraph sequences are omitted as a whole, never orphaned.
        order = [u for u in order if not u.get('chain')]
        # the rest of the slot keeps IMIT_REVIEW_SEC for due reviews of the learned core (audit 2026-09-12); the reserve comes off what
        # is LEFT after the chain stage, so a chain slot cannot be filled to the brim by other exercises (glance round 12)
        budgets = [max(0, b - IMIT_REVIEW_SEC) for b in budgets]
        i = 0
        for u in order:  # round-robin so every slot mixes forms
            for _ in range(nslots):
                j = i % nslots; i += 1
                if budgets[j] >= u["sec"]:
                    buckets[j].append({"u": u["id"], "mode": "test"}); budgets[j] -= u["sec"]; break
        for u in cards:
            placed = False
            for _ in range(nslots):
                j = i % nslots; i += 1
                if budgets[j] >= u["sec"]:
                    buckets[j].append({"u": u["id"], "mode": "test"}); budgets[j] -= u["sec"]; placed = True; break
            if not placed:
                break
        a["_imit_placed"] = sum(len(b) for b in buckets)+a.get('_imit_completed',0)
        a["_imit_total"] = len(a["_imit"])+a.get('_imit_completed',0)
        a["_imit_ids"] = {it["u"] for b in buckets for it in b}
        out: dict[str, dict[int, list[dict]]] = {}
        for (date, si), bucket in zip(slots, buckets):
            out.setdefault(date, {})[si] = bucket
        return out

    def fill_slot(self, day: dt.date, si: int, name: str, imit_plan: dict) -> dict:
        cap = self.cap(day, si)
        slot = {"slot": name, "parts": []}
        if cap != SLOT_SEC:
            slot["cap"] = cap
        budget = cap
        # 1. test day: a morning recap for whoever is examined today (an online milestone gets none)
        examined = [a for a in self.upcoming if s2d(a["date"]) == day and a.get("topics") and not a["_milestone"]]
        if examined and si == 0:
            share = cap // len(examined)   # several tests the same morning share the one recap slot
            for a in examined:
                items, used = [], 0
                for it in self.pretest_items(a):
                    cost = self.units[it["u"]]["sec"] // 2 if it["u"] in self.units else 20
                    if used + cost > share:
                        break
                    items.append(it); used += cost
                if items:
                    slot["parts"].append({"assessment": a["id"], "subject": a["subject"], "phase": "pretest", "items": items, "sec": used})
            budget = 0
        # 2. imitation windows own their slots - minus IMIT_REVIEW_SEC kept for due reviews of the learned core (audit 2026-09-12:
        #    "budget = 0" here silenced every spaced review for the three weeks before each įskaita)
        reviews_only = False
        if budget > 0:
            for a in self.upcoming:
                items = imit_plan.get(a["id"], {}).get(d2s(day), {}).get(si)
                if items:
                    sec = sum(self.units[i["u"]]["sec"] for i in items)
                    slot["parts"].append({"assessment": a["id"], "subject": a["subject"], "phase": "imitation", "items": items, "sec": sec})
                    budget = max(0, min(budget - sec, IMIT_REVIEW_SEC))
                    reviews_only = True

        # 2b. pre-test refresh (reviewer 2026-09-09: material was coldest right before the imitation days): five days before an
        #     assessment's learning window closes, every unit whose next review lies beyond the window is pulled into those days
        if si == 0:
            for a in self.upcoming:
                if a["_r"] and day == a["_learn_end"] - dt.timedelta(days=4):
                    ids = [u["id"] for u in a["_all_new"] if u["id"] in self.learned]
                    for n, uid in enumerate(ids):
                        nr = self.next_review.get(uid)
                        if nr is None or nr > a["_learn_end"]:
                            self.next_review[uid] = day + dt.timedelta(days=n % 5)
        # 3. learning / review by pressure - ONE review budget and ONE packing slack for the whole slot (audit 2026-09-12)
        tried = set()
        rev_cap = budget if reviews_only else cap * REVIEW_SHARE
        rev_used = 0
        slacked = False
        floor = REVIEW_SEC if reviews_only else MIN_NEW_SEC
        while budget >= floor:
            best, best_p = None, 0.0
            for a in self.upcoming:
                if a["id"] in tried:
                    continue
                left = self.learn_slots_left(a, day, si)
                due = self.due_reviews(a, day)
                need = sum(u["sec"] for u in a["_new"]) + len(due) * REVIEW_SEC
                if reviews_only:
                    if not due or s2d(a["date"]) <= day:
                        continue
                    p = len(due) * REVIEW_SEC / 1.0
                elif left <= 0 or (not a["_new"] and not due):
                    if due and left <= 0 and s2d(a["date"]) > day:  # reviews still due inside the imitation window: keep them alive
                        p = len(due) * REVIEW_SEC / 1.0
                    else:
                        continue
                else:
                    p = need / left
                # Pure pressure, milestones included. Ranking in-person tests first in stretched slots (tried 2026-09-10 after a
                # round-5 review note) left geography's online test 1 at 0 % learned before its date, because nearly every
                # September slot is stretched. The milestone clamp below already reserves the stretched seconds for the tests.
                if p > best_p:
                    best, best_p = a, p
            if not best:
                break
            tried.add(best["id"])
            # an online milestone never spends stretched time (reviewer 2026-09-10, round 4): the stretch is decided per in-person
            # assessment, so a milestone may use only what is left of the normal 5-minute slot
            room = budget - max(0, cap - SLOT_SEC) if best["_milestone"] else budget
            if room < floor:
                continue
            items = []
            used = 0
            for u in self.due_reviews(best, day):
                # Reviews may use half of the (possibly stretched) slot - slot-wide. Capping them at half of 300 s instead (reviewer
                # note, round 6) was tried 2026-09-10: geography's online test 1 fell to 68/69 learned before its date, so it was reverted.
                if rev_used + REVIEW_SEC > rev_cap or used + REVIEW_SEC > room:
                    break
                it = {"u": u["id"], "mode": "review"}
                if u["id"] in self.restart_uids and self.review_k.get(u["id"], 0) == 0:
                    it["r"] = 1   # restart marker: the ladder is counted from here on every later rebuild
                    self.restart_uids.discard(u["id"])
                items.append(it); used += REVIEW_SEC; rev_used += REVIEW_SEC
                self.place_review(u["id"], day)
            left = self.learn_slots_left(best, day, si)
            if not reviews_only and left > 0 and best["_new"]:
                need_new = sum(u["sec"] for u in best["_new"]) + best["_reserve_sec"]
                quota = max(MIN_NEW_SEC, min(SLOT_SEC if best["_milestone"] else cap, need_new / left))
                new_used = 0
                slack = 0 if ((best["_milestone"] and cap > SLOT_SEC) or slacked) else 20   # a milestone never eats into a stretched slot's extra; one 20-s tolerance per slot
                while best["_new"] and new_used < quota and used + best["_new"][0]["sec"] <= room + slack:
                    u = best["_new"].pop(0)
                    items.append({"u": u["id"], "mode": "new"}); used += u["sec"]; new_used += u["sec"]
                    self.learned[u["id"]] = day
                    self.review_k[u["id"]] = 0
                    self.next_review[u["id"]] = day + dt.timedelta(days=INTERVALS[0])
                    for a2 in self.upcoming:
                        if any(x["id"] == u["id"] for x in a2["_all_new"]):
                            if day < s2d(a2["date"]):   # learned FOR a2 only when taught before it (roll_over teaches late units for a later test)
                                a2["_covered"].add(u["id"])
                            if a2 is not best:
                                a2["_new"] = [x for x in a2["_new"] if x["id"] != u["id"]]
                if used > room:
                    slacked = True
            if items:
                phase = "learn" if any(i["mode"] == "new" for i in items) else "review"
                slot["parts"].append({"assessment": best["id"], "subject": best["subject"], "phase": phase, "items": items, "sec": used})
                budget -= used
        # 4. early practice: what the slot still has room for goes to one exposure of the nearest test's imitation material
        if not reviews_only and not (examined and si == 0):
            self.early_practice(slot, day, si, budget, imit_plan)
        slot["sec"] = sum(p["sec"] for p in slot["parts"])
        slot["phase"] = slot["parts"][0]["phase"] if slot["parts"] else "free"
        slot["items"] = [dict(i, assessment=p["assessment"]) for p in slot["parts"] for i in p["items"]]
        return slot

    def early_practice(self, slot: dict, day: dt.date, si: int, budget: int, imit_plan: dict):
        """Leftover seconds of a learning slot show imitation units (quiz rows, cards, practice tasks) of an in-person test ONCE
        before its final window, starting when that test's core is learned (audit 2026-09-12: the test-format material was one-shot
        crammed in the last three weeks and the idle late-October slots stayed free). Units the final window will not fit come
        first; paragraph chains stay in the final window."""
        while budget >= EARLY_MIN_SEC:
            # a test joins once half of its core is learned (its top-ranked questions come first, so the quiz rows and cards
            # shown early belong to material already taught); the subject with the largest UNSEEN SHARE goes first, so one big
            # bank (Lithuanian, 290 units) cannot take every leftover second from the others
            cands = [a for a in self.upcoming if a["_early"] and day < a["_imit_start"] and not a["_milestone"]]
            if not cands:
                return

            def pressure(a: dict) -> tuple[float, float]:
                total = len(a["_early"]) + len(a["_early_placed"])
                slots = max(1, (a["_imit_start"] - day).days * len(SLOTS) - si)
                return (len(a["_early"]) / max(1, total), sum(u["sec"] for u in a["_early"]) / slots)
            placed_any = False
            for a in sorted(cands, key=pressure, reverse=True):
                # per TOPIC, not per assessment, and only once THAT topic's core is COMPLETE (glance 2026-09-12 rounds 4 and 7: a
                # quiz row has no explicit prerequisite links, so nothing short of the whole core proves its rules were taught)
                per_topic: dict[str, list[int]] = {}
                for u in a["_all_new"]:
                    t = per_topic.setdefault(u["topic"], [0, 0])
                    t[1] += 1
                    if u["id"] in self.learned:
                        t[0] += 1
                ready = {t for t, (c, n) in per_topic.items() if c >= n}
                # one exposure per unit per period, shared by every assessment that examines it (glance 2026-09-12: an įskaita and
                # the VBE on the same topic each had their own pool and could deal one unit twice, even in one slot)
                # a later assessment's practice period opens only AFTER the preceding in-person test of that unit's topic (glance round
                # 6: the VBE pool re-dealt September exposures because September lay before the November įskaita)
                def allowed(u: dict) -> bool:
                    since_u = self.last_in_person_before(u["topic"], s2d(a["date"]))
                    return day > since_u and self.seen_test_day.get(u["id"], dt.date.min) <= since_u
                order = sorted((u for u in a["_early"] if (u["topic"] in ready or u["topic"] not in per_topic) and allowed(u)),
                               key=lambda u: (u["id"] in a["_imit_ids"], -u["w"]))
                items, used = [], 0
                for u in order:
                    if used + u["sec"] > budget:
                        continue
                    items.append({"u": u["id"], "mode": "test"}); used += u["sec"]
                    self.seen_test_day[u["id"]] = day
                    for b in self.upcoming:   # every assessment whose current period this exposure serves counts it as seen
                        if any(x["id"] == u["id"] for x in b["_early"]) and day > self.last_in_person_before(u["topic"], s2d(b["date"])) and day < s2d(b["date"]):
                            b["_early_placed"].add(u["id"])
                            b["_early"] = [x for x in b["_early"] if x["id"] != u["id"]]
                if not items:
                    continue
                slot["parts"].append({"assessment": a["id"], "subject": a["subject"], "phase": "practice", "items": items, "sec": used})
                budget -= used
                placed_any = True
                break
            if not placed_any:
                return

    def pretest_items(self, a: dict) -> list[dict]:
        items = []
        for t in a.get("topics", []):
            for i, _ in enumerate(self.topics.get(t, {}).get("mnemonics", [])[:6]):
                items.append({"u": f"{t}:m:{i}", "mode": "pretest"})
        nums = sorted((u for u in a["_all_new"] if u["type"] == "number"), key=lambda u: -u["w"])[:8]
        items += [{"u": u["id"], "mode": "pretest"} for u in nums]
        qs = sorted((u for u in a["_all_new"] if u["type"] == "question"), key=lambda u: -u["w"])[:3]
        items += [{"u": u["id"], "mode": "pretest"} for u in qs]
        return items

    def assemble(self, days: list[dict]) -> dict:
        used_ids = set()
        for d in self.history + days:
            for sl in d["slots"]:
                for it in sl["items"]:
                    used_ids.add(it["u"])
        out_assess = []
        for a in self.assessments:
            o = {k: v for k, v in a.items() if not k.startswith("_")}
            o["daysLeft"] = (s2d(a["date"]) - self.today).days
            o["milestone"] = a.get("kind") == "online-test"
            if a["status"] == "upcoming":
                total_w = sum(u["w"] for u in a["_all_new"]) or 0
                cov_w = sum(self.units[i]["w"] for i in a["_covered"]) if total_w else 0
                two_rev = sum(1 for u in a["_all_new"] if self.reviews_scheduled.get(u["id"], 0) >= 2)
                rec = (self.progress or {}).get("rec", {})
                mastered = sum(1 for u in a["_all_new"] if rec.get(u["id"], {}).get("ok", 0) >= 2 and rec.get(u["id"], {}).get("lastOk"))
                o["coverage"] = {
                    "weighted": round(cov_w / total_w, 3) if total_w else None,
                    "measured": round(mastered / len(a["_all_new"]), 3) if (self.progress is not None and a["_all_new"]) else None,
                    "imitationSkipped": a.get("_imit_skipped", 0),
                    "units": len(a["_covered"]), "unitsTotal": len(a["_all_new"]),
                    "reviewedTwice": two_rev,
                    "imitationPlaced": a.get("_imit_placed", 0), "imitationTotal": a.get("_imit_total", 0),
                    "imitationSeen": len(a.get("_imit_ids", set()) | a.get("_early_placed", set())) + a.get("_imit_completed", 0),
                    "imitationDays": a["_r"], "learnEnd": d2s(a["_learn_end"]),
                }
            out_assess.append(o)
        topics = {}
        for tid, t in self.topics.items():
            topics[tid] = {k: t[k] for k in ("topic", "subject", "title", "page", "rooms", "palaceSvg", "mnemonics", "subroom") if k in t}
            for i, mn in enumerate(t.get("mnemonics", [])):
                used_ids.add(f"{tid}:m:{i}")
        units = {}
        for uid in sorted(used_ids):   # a set's order changes per process: sorted keeps two builds of the same plan byte-identical (2026-09-12)
            if uid in self.units:
                units[uid] = self.units[uid]
            else:
                m = re.match(r"(.+):m:(\d+)$", uid)
                if m and m.group(1) in self.topics:
                    b, s = self.topics[m.group(1)]["mnemonics"][int(m.group(2))]
                    units[uid] = {"id": uid, "type": "mnemonic", "topic": m.group(1), "subject": self.topics[m.group(1)]["subject"], "b": b, "s": s, "sec": 20, "w": 0.7}
        grades = json.loads(GRADES.read_text(encoding="utf-8")) if GRADES.exists() else []
        return {"generatedAt": dt.datetime.now().isoformat(timespec="seconds"), "today": d2s(self.today), "slotSec": SLOT_SEC, "slotMaxSec": SLOT_MAX_SEC,
                "slots": SLOTS, "intervals": INTERVALS, "target": TARGET, "assessments": out_assess,
                "start": d2s(self.start) if self.start else None, "startSlot": SLOTS[self.start_si],
                "days": self.history + days, "topics": topics, "units": units, "grades": grades,
                "deadlines": load_deadlines(self.assessments)}


# ---- the live file: what the published page re-reads from Google Drive ------------------------------------------------------
def live_payload() -> dict:
    reg = apply_calendar_dates(read_json(ASSESS).get("assessments", []))
    keep = ("id", "subject", "subjectName", "title", "kind", "date", "time", "confidence")
    return {"v": 1, "deadlines": load_deadlines(reg), "assessments": [{k: a.get(k) for k in keep} for a in reg]}


def live_export(now: dt.datetime | None = None) -> str:
    """The page cannot be republished without a Claude session, so it READS this file live from Google Drive (the artifact's
    mcp capability) - owner 2026-09-10: "make sure you automatically update the deadlines when new ones appear". Called by
    `plan.py build`, every StudyAgent tick (30 min) and every MoodleWatch pass (2 h); no model, no network.
    Written IN PLACE (Drive keeps the file id) and only when the deadlines/dates changed or the last Moodle check moved on by
    LIVE_REFRESH_H, so Drive is not churned. `checkedAt` = the last completed MoodleWatch pass; the page warns when it is
    old, because a PC that is off checks nothing. Returns "updated" or "unchanged"."""
    now = now or dt.datetime.now()
    data = live_payload()
    ts = read_json(NOTIFY_STATE).get("checkedAt")
    checked = dt.datetime.fromtimestamp(ts).isoformat(timespec="minutes") if isinstance(ts, (int, float)) and ts > 0 else None
    old = read_json(LIVE)
    if old.get("deadlines") == data["deadlines"] and old.get("assessments") == data["assessments"]:
        prev = old.get("checkedAt")
        try:
            moved = bool(checked) and (not prev or dt.datetime.fromisoformat(checked) - dt.datetime.fromisoformat(prev) >= dt.timedelta(hours=LIVE_REFRESH_H))
        except ValueError:
            moved = True
        if not moved:
            return "unchanged"
    data["checkedAt"] = checked
    data["writtenAt"] = now.isoformat(timespec="minutes")
    with open(LIVE, "w", encoding="utf-8", newline="\n") as f:   # in place, never a temp-file replace: Drive would mint a new id
        f.write(json.dumps(data, ensure_ascii=False, indent=1))
    return "updated"


# ---- commands ---------------------------------------------------------------------------------------------
def build_plan(today: dt.date, assume_done: bool = False) -> dict:
    """Plan at 3 x 5 minutes; while an in-person assessment leaves posted units untaught, stretch its learning slots a little and
    plan again (Planner.grow). At SLOT_MAX_SEC the last plan stands and the report/hook say what still does not fit.
    `assume_done` ignores the progress file (every past slot counts as done)."""
    caps: dict[tuple[str, int], int] = {}
    use = not assume_done
    planner = Planner(today, caps, use)
    out = planner.run()
    for rnd in range(GROW_ROUNDS):
        if not planner.grow(rnd):
            break
        planner = Planner(today, caps, use)
        out = planner.run()
    if caps:
        # SHRINK (reviewer 2026-09-10, round 6): growth doubles per round and adds per assessment, so it can overshoot. The
        # owner's minutes are the scarce resource: keep the smallest share of the extra seconds that loses no covered unit.
        def covered(p: dict) -> dict[str, int]:
            return {a["id"]: (a.get("coverage") or {}).get("units", 0) for a in p["assessments"] if a.get("status") == "upcoming"}
        full = covered(out)
        for share in (0.25, 0.5, 0.75):
            trial = {k: SLOT_SEC + math.ceil((v - SLOT_SEC) * share / 5) * 5 for k, v in caps.items()}
            cand = Planner(today, trial, use).run()
            if all(covered(cand).get(k, 0) >= n for k, n in full.items()):
                return cand
    return out


def progress_stale(today: dt.date) -> str:
    """Why study/progress.json cannot be trusted for this build, or ''. The file is the page's db doc as the agent last PULLED it
    (Artifact read_db progress/main); the pull moment is its mtime. Collab 2026-09-12: an old updatedAt inside the doc proves
    nothing (an owner who did nothing writes nothing), so freshness is the pull time, never the doc's own timestamp. Audit
    2026-09-12: a rebuild with the stale copy re-taught every unit of the untracked days as new."""
    sched = read_json(SCHEDULE)
    try:
        start = s2d(sched["start"]) if sched.get("start") else None
    except ValueError:
        start = None
    if start is None or today < start:
        return ""
    if not PROGRESS.exists():   # glance round 13: a missing file after the start must not silently mean "everything was done"
        return "study/progress.json is missing - Artifact read_db progress/main -> study/progress.json, then build (or plan.py build --assume-done)"
    age_h = (dt.datetime.now() - dt.datetime.fromtimestamp(PROGRESS.stat().st_mtime)).total_seconds() / 3600
    if age_h > PROGRESS_STALE_H:
        return (f"study/progress.json was pulled {age_h / 24:.1f} d ago - Artifact read_db progress/main -> study/progress.json, "
                f"then build (or plan.py build --assume-done to treat the untracked slots as done)")
    return ""


def build_order_problems() -> list[str]:
    """Every generated file must be NEWER than what it is generated from, or the published hub silently carries old content.
    Measured 2026-09-12: the build chain rebuilt xxa-proza.units.json two seconds AFTER plan.json, so Version 23 of the hub kept
    the Katiliškis wording a reviewer had already rejected while the topic page carried the corrected text. The chain is
    <topic>.json -> <topic>.html -> <topic>.units.json -> plan.json -> planas.html; a content JSON is one that HAS an .html
    sibling, so backups (.lt-backup, .casio, .pre-calc) and the VBE archives are skipped on their own."""
    def older(a: Path, b: Path) -> bool:
        return a.exists() and b.exists() and a.stat().st_mtime + 1 < b.stat().st_mtime

    def rel(p: Path) -> str:
        return str(p.relative_to(ROOT))

    tools = ROOT / "tools"
    # shared RENDERING inputs are inlined into the outputs, so they are dependencies too (glance 2026-09-12 round 4); generator code
    # (topic.py, plan.py, units.py, calc.py) is deliberately NOT tracked - every code edit would otherwise demand a full rebuild
    board = [tools / "board.css", tools / "board.js"]
    settings = STUDY / "settings.json"   # the association switch changes what topic.py renders and what units.py emits (glance round 5)
    topic_deps = [tools / "topic.template.html", settings] + board
    hub_deps = [tools / "planas.template.html"] + board

    def is_content(src: Path) -> bool:
        """A topic content JSON: no dot in the stem and either a page beside it or the topic.py contract (title + questions)."""
        if src.name.endswith(".units.json") or "." in src.stem:
            return False     # a generated units file, or a backup/variant such as *.lt-backup.json / *.casio.json
        if src.with_suffix(".html").exists():
            return True
        try:
            d = json.loads(src.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return isinstance(d, dict) and "title" in d and "questions" in d   # an archive (vbe-*.json) has neither

    out = []
    newest_units: Path | None = None
    pages_with_json: set[Path] = set()
    for src in sorted(STUDY.glob("*/*.json")):
        if not is_content(src):
            continue
        page = src.with_suffix(".html")
        units = src.with_name(src.stem + ".units.json")
        pages_with_json.add(page)
        if not page.exists():   # a MISSING output is a stale output too (glance round 4: older() is silent when a file is absent)
            out.append(f"{rel(page)} is missing - run: python tools/topic.py build {rel(src)}")
            continue
        if older(page, src):
            out.append(f"{rel(page)} is older than {rel(src)} - run: python tools/topic.py build {rel(src)}")
        for dep in topic_deps:
            if older(page, dep):
                out.append(f"{rel(page)} is older than {rel(dep)} - run: python tools/topic.py build {rel(src)}")
                break
    for page in sorted(STUDY.glob("*/*.html")):   # every topic page, including a hand-built one with no content JSON (biology)
        if "." in page.stem:
            continue          # a kept variant such as *.with-palace.html
        units = page.with_name(page.stem + ".units.json")
        if not units.exists():
            out.append(f"{rel(units)} is missing - run: python tools/units.py extract {rel(page)}")
            continue
        if older(units, page):
            out.append(f"{rel(units)} is older than {rel(page)} - run: python tools/units.py extract {rel(page)}")
        elif page not in pages_with_json and older(units, settings):
            # a hand-built page (no content JSON) is never rebuilt, so a settings change reaches only its units
            out.append(f"{rel(units)} is older than {rel(settings)} - run: python tools/units.py extract {rel(page)}")
        if newest_units is None or units.stat().st_mtime > newest_units.stat().st_mtime:
            newest_units = units
    if newest_units is not None:
        if not PLAN.exists():
            out.append("study/plan.json is missing - run: python tools/plan.py build")
        elif older(PLAN, newest_units):
            out.append(f"study/plan.json is older than {rel(newest_units)} - run: python tools/plan.py build")
    if PLAN.exists():
        if not PAGE.exists():
            out.append("study/planas.html is missing - run: python tools/plan.py page, then republish")
        elif older(PAGE, PLAN):
            out.append("study/planas.html is older than study/plan.json - run: python tools/plan.py page, then republish")
        else:
            for dep in hub_deps:
                if older(PAGE, dep):
                    out.append(f"study/planas.html is older than {rel(dep)} - run: python tools/plan.py page, then republish")
                    break
    return out


def cmd_plan(today: dt.date, assume_done: bool = False) -> dict:
    why = progress_stale(today)
    if why and not assume_done:
        print("STUDY PLAN REFUSED: " + why)
        raise SystemExit(2)
    plan = build_plan(today, assume_done)
    PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=0), encoding="utf-8")
    report(plan)
    try:
        print("study/planas-live.json:", live_export())
    except Exception as e:  # noqa: BLE001
        print(f"study/planas-live.json: FAILED {type(e).__name__}: {e}")
    return plan


def report(plan: dict):
    print(f"plan {plan['today']}: {len(plan['days'])} days, {len(plan['units'])} units in play, start {plan.get('start')} {plan.get('startSlot')}")
    for a in plan["assessments"]:
        if a["status"] != "upcoming":
            print(f"  PAST     {a['subjectName']} - {a['title']} ({a['date']})"); continue
        c = a.get("coverage") or {}
        cov = c.get("weighted")
        meas = "-" if c.get("measured") is None else f"{c['measured'] * 100:.0f}%"
        if a.get("milestone"):
            cov_s = "no material yet" if cov is None else f"MILESTONE (online, no extra time): {cov * 100:.0f}% of its topics learned before it ({c['units']}/{c['unitsTotal']} units)"
        else:
            cov_s = "no material yet" if cov is None else f"{cov * 100:.0f}% of posted material planned ({c['units']}/{c['unitsTotal']} units, {c['reviewedTwice']} reviewed 2+), measured {meas}, imitation {c['imitationPlaced']}/{c['imitationTotal']} over {c['imitationDays']} d, seen at least once {c.get('imitationSeen', 0)}/{c['imitationTotal']} ({c.get('imitationSkipped', 0)} VBE tasks unusable)"
        flag = "" if cov is None or cov >= TARGET else "  <-- BELOW TARGET"
        clock = f" {a['time']}" if a.get("time") else ""
        print(f"  {a['daysLeft']:>3} d  {a['subjectName']} - {a['title']} ({a['date']}{clock}, {a['confidence']}): {cov_s}{flag}")
    free = sum(1 for d in plan["days"] if s2d(d["date"]) >= s2d(plan["today"]) for s in d["slots"] if s["phase"] == "free")
    busy = sum(1 for d in plan["days"] if s2d(d["date"]) >= s2d(plan["today"]) for s in d["slots"] if s["phase"] not in ("free", "before-start"))
    print(f"  slots ahead: {busy} planned, {free} free")
    long_days = [sum(s["sec"] for s in d["slots"]) for d in plan["days"] if s2d(d["date"]) >= s2d(plan["today"]) and any(s.get("cap", SLOT_SEC) > SLOT_SEC for s in d["slots"])]
    if long_days:
        print(f"  stretched (owner: up to 20 min/day): {len(long_days)} days, longest {max(long_days) / 60:.1f} min")


def cmd_page() -> Path:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    tpl = TEMPLATE.read_text(encoding="utf-8")
    data = json.dumps(plan, ensure_ascii=False).replace("</", "<\\/")
    from topic import inline_board   # the handwritten maths board, shared with the topic pages
    html = inline_board(tpl).replace("/*__PLAN__*/null", data)
    PAGE.write_text(html, encoding="utf-8")
    print(f"{PAGE.relative_to(ROOT)}: {len(html) // 1024} KB")
    return PAGE


def cmd_hook():
    """Cheap, offline: one line when the plan must be rebuilt or a target is missed."""
    try:
        if not PLAN.exists():
            print("STUDY PLAN: no plan yet - run: python tools/plan.py build"); return
        plan = json.loads(PLAN.read_text(encoding="utf-8"))
        newest = max([ASSESS.stat().st_mtime] + [f.stat().st_mtime for f in STUDY.glob("*/*.units.json")]
                     + [p.stat().st_mtime for p in (DEADLINES, QUEUE, SCHEDULE) if p.exists()])   # queue: send time / status shown on day tabs
        stale = plan.get("today") != d2s(dt.date.today()) or newest > PLAN.stat().st_mtime + 1
        if stale:
            print("STUDY PLAN: stale (new day or new material/assessment) - read progress (Artifact read_db progress/main -> study/progress.json), run: python tools/plan.py build, then republish study/planas.html")
        why = progress_stale(dt.date.today())
        if why:
            print("STUDY PLAN: progress stale - " + why)
        for p in build_order_problems():   # a generated file older than its source = the hub carries old content (2026-09-12)
            print("STUDY PLAN: BUILD ORDER - " + p)
        for a in plan["assessments"]:
            c = a.get("coverage") or {}
            if a["status"] != "upcoming":
                continue
            if c.get("weighted") is not None and c["weighted"] < TARGET:
                print(f"STUDY PLAN: {a['subjectName']} {a['title']}: only {c['weighted'] * 100:.0f}% of the POSTED material fits (in-person tests already stretched up to 20 min/day, online milestones never) - shorten units or tell the owner")
            if not a.get("milestone") and c.get("imitationTotal") and c.get("imitationSeen", 0) / c["imitationTotal"] < 0.75:
                print(f"STUDY PLAN: {a['subjectName']} {a['title']}: only {c.get('imitationSeen', 0)}/{c['imitationTotal']} test-format units get an exposure before the test (imitation window + early practice) - more free slots or fewer variants")
            if c.get("measured") is not None and a["daysLeft"] <= 14 and c["measured"] < TARGET:
                print(f"STUDY PLAN: {a['subjectName']} {a['title']} in {a['daysLeft']} d: MEASURED mastery {c['measured'] * 100:.0f}% < 90% - tell the owner, add recall of the weak units")
    except Exception as e:  # noqa: BLE001
        print(f"STUDY PLAN hook failed: {type(e).__name__}: {e}")


def main(argv: list[str]):
    cmd = argv[0] if argv else "report"
    today = dt.date.today()
    if "--today" in argv:
        today = s2d(argv[argv.index("--today") + 1])
    assume = "--assume-done" in argv
    if cmd == "plan":
        cmd_plan(today, assume)
    elif cmd == "page":
        cmd_page()
    elif cmd == "build":
        cmd_plan(today, assume); cmd_page()
    elif cmd == "report":
        report(json.loads(PLAN.read_text(encoding="utf-8")))
    elif cmd == "live":
        print("study/planas-live.json:", live_export())
    elif cmd == "hook":
        cmd_hook()
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
