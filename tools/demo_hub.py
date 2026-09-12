#!/usr/bin/env python
"""demo_hub.py - build web/app/demo-hub.html: the real daily hub rendered from sample data with English chrome.
    python product/tools/demo_hub.py
"""
import sys, json, datetime as dt
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'engine')); sys.path.insert(0, str(HERE.parent / 'tests'))
from test_engine import make_ws
from studycore import planner, render
ws = make_ws()
units = []
Q = [("What is velocity?", "Displacement divided by time; a vector (m/s)."), ("What is acceleration?", "Change of velocity per unit time (m/s²)."), ("Free-fall acceleration on Earth?", "g ≈ 9.8 m/s² downward, independent of mass (no air)."), ("Equation for distance with constant acceleration?", "s = v₀t + at²/2"), ("Difference between speed and velocity?", "Speed is a scalar (how fast); velocity adds direction."), ("What does the slope of a v–t graph show?", "Acceleration."), ("What does the area under a v–t graph show?", "Displacement."), ("Newton's first law in one sentence?", "A body keeps its velocity unless a net force acts on it.")]
for i, (q, a) in enumerate(Q):
    units.append({"id": f"kin:q:{i}", "type": "question", "w": round(0.9 - i * 0.07, 2), "sec": 70, "q": q, "a": a, "t": "Definition"})
for i, (q, a) in enumerate([("Unit of acceleration", "m/s²"), ("g on Earth", "9.8 m/s²"), ("Speed of sound in air", "≈ 343 m/s")]):
    units.append({"id": f"kin:n:{i}", "type": "number", "w": 0.5, "sec": 20, "q": q, "a": a})
for i, (q, a) in enumerate([("Scalar or vector: displacement?", "Vector"), ("Scalar or vector: distance?", "Scalar"), ("v = ?", "Δs / Δt"), ("a = ?", "Δv / Δt"), ("Uniform motion means…", "constant velocity, a = 0")]):
    units.append({"id": f"kin:c:{i}", "type": "card", "w": 0.5, "sec": 25, "q": q, "a": a})
for i in range(4):
    units.append({"id": f"kin:t:{i}", "type": "quiz", "w": 0.5, "sec": 45, "s": f"A car goes from 0 to 20 m/s in {4+i} s. Its acceleration is…", "o": [f"{20/(4+i):.1f} m/s²", "20 m/s²", f"{4+i} m/s²", "0.2 m/s²"], "r": 0, "e": "a = Δv/Δt"})
(ws.study / 'fizika' / 'kinematika.units.json').write_text(json.dumps({"topic": "t1", "subject": "fizika", "title": "Kinematics", "page": "study/fizika/kinematika.html", "rooms": [], "palaceSvg": "", "mnemonics": [], "subroom": {}, "units": units}), encoding='utf-8')
today = dt.date.today()
ws.write('assessments.json', {"assessments": [
  {"id": "phys-1", "subject": "fizika", "subjectName": "Physics 11", "title": "Kinematics test", "kind": "test", "date": (today + dt.timedelta(days=9)).isoformat(), "time": "09:00", "confidence": "confirmed", "source": "demo", "topics": ["t1"]},
  {"id": "bio-1", "subject": "biologija", "subjectName": "Biology 11", "title": "Cell biology", "kind": "test", "date": (today + dt.timedelta(days=16)).isoformat(), "confidence": "estimated", "source": "demo", "topics": []}]})
ws.write('schedule.json', {"start": today.isoformat(), "startSlot": "rytas"})
ws.update_settings(gradeScale='lt10', targetGrade='8', minutesPerDay=15, maxMinutesPerDay=20, uiLang='en')
planner.build(ws, today)
pm = ws.bind()['plan']
html = Path(pm.cmd_page()).read_text(encoding='utf-8')
html = render.apply_chrome(html, 'en')
html = html.replace("title = 'planas-live.json' and parentId = '1b7oghPlrWbQpZNVOKG35kUCzb-pUw2E1'", "title = 'planas-live.json' and parentId = 'demo'")
out = HERE.parent / 'web' / 'app' / 'demo-hub.html'
out.write_text(html, encoding='utf-8')
print('demo hub', len(html), 'bytes ->', out)
