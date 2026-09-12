"""workspace.py - one student's workspace: the personal layout (study/, courses/) made per-user and language-neutral.

A Workspace binds the vendored engine modules to ITS paths and ITS settings before any engine call, so the same
plan.py/topic.py/units.py that serve the owner serve every user (collab 2026-09-12: one engine, thin adapters).
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

VENDOR = Path(__file__).resolve().parent / "vendor"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

DEFAULT_SETTINGS = {
    "_doc": "Per-user settings. minutesPerDay is the slider; maxMinutesPerDay the stretch ceiling the planner may use when "
            "posted material does not fit (the forced adaptable minimum is computed, never below what the core needs); "
            "targetGrade is on gradeScale; association stays false (memory-palace techniques are off in the product); "
            "factCheck is the certain-facts switch (off by default: the material's wording is kept unless the user opts in).",
    "minutesPerDay": 15,
    "maxMinutesPerDay": 20,
    "slotsPerDay": 3,
    "targetGrade": None,
    "gradeScale": "pct",
    "country": None,
    "uiLang": "en",
    "contentLang": None,
    "association": False,
    "factCheck": False,
    "shareData": False,
    "digest": {"provider": "none", "model": None, "endpoint": None},
}

STUDY_FILES = {
    "assessments.json": {"_doc": "in-person tests and exams (kind test|exam), online tests as milestones (kind online-test)", "assessments": []},
    "topics.json": {"_doc": "every subject split into topics with its Moodle location and state", "updated": None, "subjects": {}},
    "schedule.json": {"start": None, "startSlot": "rytas"},
    "deadlines.json": {"deadlines": [], "checkedAt": None},
    "material-map.json": {"_doc": "INDEX.md section -> topic (or a reasoned skip)", "rules": []},
}

SLOT_NAMES = ["rytas", "diena", "vakaras", "s4", "s5", "s6"]   # internal keys; the UI translates them


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.study = self.root / "study"
        self.courses = self.root / "courses"
        self.secrets = self.root / "secrets"
        self.state = self.root / "state"
        for d in (self.study, self.courses, self.secrets, self.state, self.study / "material"):
            d.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.study / "settings.json"
        if not self.settings_path.exists():
            self.settings_path.write_text(json.dumps(DEFAULT_SETTINGS, ensure_ascii=False, indent=1), encoding="utf-8")
        for name, default in STUDY_FILES.items():
            p = self.study / name
            if not p.exists():
                p.write_text(json.dumps(default, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- settings -------------------------------------------------------------------------------------------------
    @property
    def settings(self) -> dict:
        try:
            s = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            s = {}
        out = dict(DEFAULT_SETTINGS)
        out.update({k: v for k, v in s.items() if not k.startswith("_")})
        out["association"] = False   # the product never renders the association techniques
        return out

    def update_settings(self, **changes) -> dict:
        s = self.settings
        for k, v in changes.items():
            if k not in DEFAULT_SETTINGS:
                raise KeyError(f"unknown setting {k}")
            s[k] = v
        s["_doc"] = DEFAULT_SETTINGS["_doc"]
        self.settings_path.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
        return s

    def read(self, name: str) -> dict:
        p = self.study / name
        try:
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        except (ValueError, OSError):
            return {}

    def write(self, name: str, data: dict):
        (self.study / name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- binding the vendored engine to this workspace ----------------------------------------------------------------
    def bind(self) -> dict:
        """Point every vendored module's path constants at this workspace and apply the sliders. Returns the modules."""
        mods = {n: importlib.import_module(n) for n in ("plan", "units", "material", "topic", "video", "extract", "calc")}
        p = mods["plan"]
        p.ROOT, p.STUDY = self.root, self.study
        p.ASSESS, p.PLAN, p.PAGE = self.study / "assessments.json", self.study / "plan.json", self.study / "planas.html"
        p.GRADES, p.PROGRESS, p.DEADLINES = self.study / "grades.json", self.study / "progress.json", self.study / "deadlines.json"
        p.QUEUE = self.root / "no-homework-queue.json"          # the product never does assignments (owner 2026-09-12)
        p.SUBJECTS, p.SCHEDULE, p.LIVE = self.study / "subjects.json", self.study / "schedule.json", self.study / "planas-live.json"
        p.NOTIFY_STATE = self.state / "notify-state.json"
        p.TEMPLATE = VENDOR / "planas.template.html"
        s = self.settings
        slots = max(1, min(6, int(s.get("slotsPerDay") or 3)))
        p.SLOTS = SLOT_NAMES[:slots]
        p.SLOT_SEC = max(60, round(int(s.get("minutesPerDay") or 15) * 60 / slots))
        p.SLOT_MAX_SEC = max(p.SLOT_SEC, round(int(s.get("maxMinutesPerDay") or s.get("minutesPerDay") or 15) * 60 / slots) - 20)
        from . import grades   # late import: grades has no engine dependency
        p.TARGET = grades.coverage_for(s.get("gradeScale") or "pct", s.get("targetGrade"))
        u = mods["units"]
        u.ROOT, u.STUDY = self.root, self.study
        m = mods["material"]
        m.ROOT, m.STUDY, m.COURSES = self.root, self.study, self.courses
        m.MAP, m.TOPICS, m.ASSESS = self.study / "material-map.json", self.study / "topics.json", self.study / "assessments.json"
        m.LEDGER, m.KNOWN = self.study / "material", self.study / "material-known.json"
        t = mods["topic"]
        t.ROOT, t.STUDY, t.SETTINGS = self.root, self.study, self.settings_path
        v = mods["video"]
        v.ROOT, v.COURSES = self.root, self.courses
        return mods

    @property
    def modules(self) -> dict:
        return self.bind()
