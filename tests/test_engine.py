"""Engine adapter tests - run: python product/tests/test_engine.py (plain asserts, no pytest needed)."""
from __future__ import annotations

import datetime as dt
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "engine"))
from studycore import digest, grades, notify, planner, subjects  # noqa: E402
from studycore.workspace import Workspace  # noqa: E402


def make_ws() -> Workspace:
    root = Path(tempfile.gettempdir()) / "planas-test-ws"
    shutil.rmtree(root, ignore_errors=True)
    ws = Workspace(root)
    ws.update_settings(gradeScale="lt10", targetGrade="8", minutesPerDay=15, maxMinutesPerDay=20)
    units = []
    for i in range(40):
        units.append({"id": f"t1:q:{i}", "type": "question", "w": round(0.95 - i * 0.02, 2), "sec": 70, "q": f"Q{i}?", "a": f"A{i}"})
    for i in range(20):
        units.append({"id": f"t1:n:{i}", "type": "number", "w": 0.5, "sec": 20, "q": f"N{i}", "a": str(i)})
    for i in range(60):
        units.append({"id": f"t1:c:{i}", "type": "card", "w": 0.5, "sec": 25, "q": f"C{i}", "a": "x"})
    for i in range(30):
        units.append({"id": f"t1:t:{i}", "type": "quiz", "w": 0.5, "sec": 45, "s": f"S{i}", "o": ["a", "b", "c", "d"], "r": 0, "e": "e"})
    (ws.study / "fizika").mkdir(exist_ok=True)
    (ws.study / "fizika" / "kinematika.units.json").write_text(json.dumps(
        {"topic": "t1", "subject": "fizika", "title": "Kinematika", "page": "study/fizika/kinematika.html", "rooms": [], "palaceSvg": "",
         "mnemonics": [], "subroom": {}, "units": units}), encoding="utf-8")
    ws.write("assessments.json", {"assessments": [{"id": "fiz-1", "subject": "fizika", "subjectName": "Fizika", "title": "Kinematikos kontrolinis",
                                                   "kind": "test", "date": "2026-10-05", "confidence": "confirmed", "source": "test", "topics": ["t1"]}]})
    ws.write("schedule.json", {"start": "2026-09-14", "startSlot": "rytas"})
    return ws


def test_grades():
    assert grades.coverage_for("lt10", "8") == 0.85
    assert grades.coverage_for("de6", "2") == 0.91
    assert grades.scale_for_country("pl") == "pl6"
    e = grades.estimate("lt10", 0.85)
    assert e["grade"] == "8" and e["estimate"] is True and e["low"] <= e["grade"] <= e["high"]
    assert grades.grade_index("lt10", "8") == 2 and grades.grade_index("lt10", "10") == 0


def test_subjects():
    cases = {"Matematika 12 klasė": ("math", "procedural"), "Physics 101": ("physics", "procedural"), "Chemia klasa 8": ("chemistry", "procedural"),
             "Lietuvių kalba 12 klasė": ("literature", "literary"), "Anglų kalba 12 klasė": ("language", "language"), "Geografija": ("geography", "factual"),
             "Biología 4º ESO": ("biology", "factual"), "Русская литература": ("literature", "literary"), "Kūno kultūra": ("pe", "mixed"),
             "Something odd": ("unknown", "mixed")}
    for name, (fam, shape) in cases.items():
        c = subjects.classify(name)
        assert (c["family"], c["shape"]) == (fam, shape), (name, c)


def test_sliders_and_plan():
    ws = make_ws()
    today = dt.date(2026, 9, 14)
    w = planner.workload(ws, today)
    assert w["minMinutes"] >= 5 and w["assessments"][0]["daysLeft"] == 21
    low = planner.estimate(ws, minutes=5, today=today)
    ok = planner.estimate(ws, minutes=15, today=today)
    assert low["forced"] is True and low["minutesForced"] == low["minMinutes"] and low["gradeDropSteps"] >= 1
    assert ok["forced"] is False and ok["gradeDropSteps"] == 0 and ok["estimate"]["grade"] == "8"
    assert planner.estimate(ws, minutes=15, target_grade="10", today=today)["minMinutes"] >= planner.estimate(ws, minutes=15, target_grade="4", today=today)["minMinutes"]
    plan = planner.build(ws, today)
    assert len(plan["days"]) > 20 and plan["sliders"]["scale"] == "lt10"
    cov = [(a.get("coverage") or {}).get("weighted") for a in plan["assessments"]]
    assert cov and cov[0] and cov[0] >= 0.85
    first = [d for d in plan["days"] if d["date"] == "2026-09-15"][0]
    assert all(s["sec"] <= 320 for s in first["slots"]) and any(s["phase"] == "learn" for s in first["slots"])
    a = planner.mark_done(ws, "fiz-1")
    assert a["done"] is True and a["doneAt"]
    assert planner.workload(ws, today)["assessments"] == []   # a done test needs no minutes
    a = planner.set_date(ws, "fiz-1", "2026-10-07", "09:30")
    assert a["date"] == "2026-10-07" and a["time"] == "09:30" and a["confidence"] == "confirmed"
    try:
        planner.set_date(ws, "fiz-1", "2026-13-40")
        raise AssertionError("bad date accepted")
    except ValueError:
        pass


def test_notify_and_baseline():
    ws = make_ws()
    c = ws.courses / "5-fizika"
    c.mkdir(parents=True, exist_ok=True)
    (c / "manifest.json").write_text(json.dumps({"id": 5, "fullname": "Fizika", "sections": [{"title": "Kinematika", "summary": ""}],
                                                 "modules": [{"id": 1, "module": "resource", "name": "Skaidrės", "section": "Kinematika", "files": ["a.pdf"]}]}), encoding="utf-8")
    assert notify.watch(ws)["baseline"] is True
    (c / "manifest.json").write_text(json.dumps({"id": 5, "fullname": "Fizika", "sections": [{"title": "Kinematika", "summary": "new goals"}],
                                                 "modules": [{"id": 1, "module": "resource", "name": "Skaidrės", "section": "Kinematika", "files": ["a.pdf", "b.pdf"]},
                                                             {"id": 2, "module": "quiz", "name": "Testas", "section": "Kinematika", "files": []}]}), encoding="utf-8")
    kinds = sorted(ch["kind"] for ch in notify.watch(ws)["changes"])
    assert kinds == ["file", "module", "section"], kinds
    assert len(notify.unread(ws)) == 3
    notify.mark_read(ws)
    assert notify.unread(ws) == []
    b = digest.baseline("t1", "fizika", "Kinematika", "Fizika",
                        "# Greitis\nGreitis yra kelio ir laiko santykis, matuojamas metrais per sekunde ir rodo kaip greitai juda kunas.\n"
                        "# Pagreitis\nPagreitis yra greicio pokytis per laika, matuojamas m/s2 ir aprasomas antruoju Niutono desniu.\n",
                        [], subjects.classify("Fizika"))
    assert b["baseline"] is True and len(b["questions"]) == 2 and b["corrections"] == []


if __name__ == "__main__":
    import traceback
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except Exception:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"{failed} failed")
    raise SystemExit(1 if failed else 0)
