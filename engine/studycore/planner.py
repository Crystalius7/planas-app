"""planner.py - the two sliders on top of the vendored planner.

Slider 1: minutes per day. Slider 2: the grade the student wants (on the workspace's grade scale). The engine plans
`minutesPerDay` in `slotsPerDay` slots and may stretch a day to `maxMinutesPerDay` when posted material does not fit
(vendor plan.py Planner.grow). What the product adds:

* the FORCED ADAPTABLE MINIMUM (owner 2026-09-12: "we will force the minimum time in case the learning material is too
  much to fit into this time per day spent until the next exam/test"): `workload()` computes, per upcoming in-person
  assessment, the seconds the core (at the grade target's coverage), its spaced reviews and one exposure of every
  test-format unit need, spreads each over the days left, sums the overlapping windows per day and reports the highest
  day as the minimum minutes per day. The minutes slider cannot go below it; lowering the grade target lowers it.
* the readout (owner 2026-09-12: "show by how much the grade drops and how much time gets saved"): `estimate()` turns
  the minutes actually chosen into the coverage the plan can reach and maps it to the grade scale as an ESTIMATE band
  (partner DISAGREE 3: never a prediction), next to the minutes saved per day and in total.

Every figure is arithmetic on unit costs and days left, the same numbers the plan itself uses; nothing here is validated
against real grades, and the UI says so.
"""
from __future__ import annotations

import datetime as dt
import math
from pathlib import Path

from . import grades
from .workspace import Workspace

CORE_TYPES = ("question", "hook", "number")
REVIEW_SEC = 15
INTERVALS = [1, 3, 7, 14, 30, 60, 90, 120]
IMIT_MARGIN = 1.15


def _units_by_topic(ws: Workspace) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    import json
    for f in sorted(ws.study.glob("*/*.units.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        out[d.get("topic", f.stem)] = d.get("units", [])
    return out


def _core(units: list[dict]) -> list[dict]:
    core = [u for u in units if u.get("type") in CORE_TYPES or (u.get("type") == "card" and u.get("learn"))]
    return sorted(core, key=lambda u: -(u.get("w") or 0))


def _imitation(units: list[dict]) -> list[dict]:
    return [u for u in units if u.get("type") in ("quiz", "practice", "vbe", "mistake", "rule")]


def _take_coverage(core: list[dict], coverage: float) -> tuple[list[dict], float]:
    """Top units by weight until the weighted share reaches `coverage`; returns (taken, share reached)."""
    total = sum(u.get("w") or 0 for u in core) or 1.0
    taken, acc = [], 0.0
    for u in core:
        if acc / total >= coverage - 1e-9:
            break
        taken.append(u)
        acc += u.get("w") or 0
    return taken, acc / total


def _reviews_before(days_left: int) -> int:
    return sum(1 for k in INTERVALS if k <= max(0, days_left - 1))


def workload(ws: Workspace, today: dt.date | None = None, coverage: float | None = None) -> dict:
    """Per-assessment needs and the per-day demand curve at the given (or the settings') coverage."""
    today = today or dt.date.today()
    s = ws.settings
    cov = coverage if coverage is not None else grades.coverage_for(s.get("gradeScale") or "pct", s.get("targetGrade"))
    reg = ws.read("assessments.json").get("assessments", [])
    sched = ws.read("schedule.json")
    try:
        start = dt.date.fromisoformat(sched["start"]) if sched.get("start") else today
    except ValueError:
        start = today
    first = max(today, start)
    by_topic = _units_by_topic(ws)
    per_day: dict[str, int] = {}
    rows = []
    for a in sorted(reg, key=lambda a: a.get("date", "")):
        if a.get("kind") not in ("test", "exam", "iskaita", "in-person") and a.get("kind") != "online-test":
            continue
        if a.get("done"):
            continue
        try:
            date = dt.date.fromisoformat(a["date"][:10])
        except (KeyError, ValueError):
            continue
        if date <= first:
            continue
        days_left = (date - first).days
        units = [u for t in a.get("topics", []) for u in by_topic.get(t, [])]
        core = _core(units)
        taken, reached = _take_coverage(core, cov)
        core_sec = sum(u.get("sec") or 0 for u in taken)
        review_sec = len(taken) * _reviews_before(days_left) * REVIEW_SEC
        milestone = a.get("kind") == "online-test"
        imit = [] if milestone else _imitation(units)
        imit_sec = int(sum(u.get("sec") or 0 for u in imit) * IMIT_MARGIN)
        total = core_sec + review_sec + imit_sec
        need_per_day = total / days_left
        row = {"id": a.get("id"), "title": a.get("title"), "subject": a.get("subject"), "date": a["date"], "daysLeft": days_left,
               "milestone": milestone, "coreUnits": len(core), "coreTaken": len(taken), "coverageReached": round(reached, 3),
               "coreSec": core_sec, "reviewSec": review_sec, "imitationUnits": len(imit), "imitationSec": imit_sec,
               "totalSec": total, "minutesPerDay": math.ceil(need_per_day / 60 * 10) / 10}
        rows.append(row)
        for n in range(days_left):
            d = (first + dt.timedelta(days=n)).isoformat()
            per_day[d] = per_day.get(d, 0) + int(need_per_day)
    peak = max(per_day.values()) if per_day else 0
    return {"today": today.isoformat(), "coverage": cov, "assessments": rows, "perDaySec": per_day,
            "minMinutes": math.ceil(peak / 60) if peak else 0, "peakDay": max(per_day, key=per_day.get) if per_day else None}


def estimate(ws: Workspace, minutes: int | None = None, target_grade: str | None = None, today: dt.date | None = None) -> dict:
    """The slider readout. `minutes` = the value the user is dragging to; `target_grade` = the grade slider."""
    s = ws.settings
    key = s.get("gradeScale") or "pct"
    grade = target_grade if target_grade is not None else (s.get("targetGrade") or grades.scale(key)["good"])
    minutes = int(minutes if minutes is not None else s.get("minutesPerDay") or 15)
    cov = grades.coverage_for(key, grade)
    w = workload(ws, today, cov)
    full = workload(ws, today, 1.0)
    min_minutes = w["minMinutes"]
    ideal_minutes = full["minMinutes"]
    forced = max(minutes, min_minutes)
    # coverage reachable with `minutes`: the peak day scales the core share linearly (reviews and practice keep their share)
    ratio = 1.0 if min_minutes == 0 else min(1.0, minutes / min_minutes)
    reached = cov * ratio
    est_target = grades.estimate(key, cov)
    est_chosen = grades.estimate(key, reached)
    est_full = grades.estimate(key, 1.0)
    drop = grades.grade_index(key, est_chosen["grade"]) - grades.grade_index(key, est_target["grade"])
    horizon = max((r["daysLeft"] for r in w["assessments"]), default=0)
    return {
        "scale": key, "targetGrade": str(grade), "coverageForTarget": cov,
        "minutesChosen": minutes, "minMinutes": min_minutes, "minutesForced": forced, "forced": forced > minutes,
        "idealMinutes": ideal_minutes,
        "estimate": est_chosen, "estimateAtTarget": est_target, "estimateAtFull": est_full,
        "gradeDropSteps": max(0, drop),
        "minutesSavedPerDay": max(0, ideal_minutes - forced), "minutesSavedTotal": max(0, ideal_minutes - forced) * horizon,
        "daysHorizon": horizon, "assessments": w["assessments"], "note": "estimate",
    }


def build(ws: Workspace, today: dt.date | None = None, assume_done: bool = False) -> dict:
    """Run the vendored planner for this workspace at its sliders (the minutes are raised to the forced minimum first)."""
    today = today or dt.date.today()
    est = estimate(ws, today=today)
    if est["forced"]:
        ws.update_settings(minutesPerDay=est["minutesForced"], maxMinutesPerDay=max(int(ws.settings.get("maxMinutesPerDay") or 0), est["minutesForced"] + 5))
    mods = ws.bind()
    plan_mod = mods["plan"]
    plan = plan_mod.build_plan(today, assume_done)
    plan["sliders"] = {k: est[k] for k in ("scale", "targetGrade", "minutesChosen", "minMinutes", "minutesForced", "idealMinutes", "estimate", "gradeDropSteps", "minutesSavedPerDay", "minutesSavedTotal")}
    import json
    plan_mod.PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=0), encoding="utf-8")
    try:
        plan_mod.live_export()
    except Exception:  # noqa: BLE001 - the live file is a convenience; the plan is the product
        pass
    return plan


def mark_done(ws: Workspace, assessment_id: str, done: bool = True, when: dt.date | None = None) -> dict:
    """The 'done' button (owner 2026-09-12): the assessment is marked completed and moves to the completed list; the next
    assessment of that subject owns the subject's learning from now on (roll-over is the engine's own rule)."""
    reg = ws.read("assessments.json")
    hit = None
    for a in reg.get("assessments", []):
        if a.get("id") == assessment_id:
            a["done"] = bool(done)
            a["doneAt"] = (when or dt.date.today()).isoformat() if done else None
            hit = a
    if hit is None:
        raise KeyError(assessment_id)
    ws.write("assessments.json", reg)
    return hit


def set_date(ws: Workspace, assessment_id: str, date: str, time: str | None = None, confidence: str = "confirmed") -> dict:
    """Manual date/time edit (owner 2026-09-12: users edit the times and dates of their tests/exams)."""
    dt.date.fromisoformat(date)
    if time:
        dt.time.fromisoformat(time)
    reg = ws.read("assessments.json")
    for a in reg.get("assessments", []):
        if a.get("id") == assessment_id:
            a["date"], a["confidence"] = date, confidence
            a["time"] = time
            a["source"] = f"set by the student on {dt.date.today().isoformat()}"
            ws.write("assessments.json", reg)
            return a
    raise KeyError(assessment_id)
