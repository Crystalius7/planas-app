#!/usr/bin/env python
"""Regression tests for tools/plan.py (2026-09-10): fair imitation for tests sharing one day, the afternoon start, online tests
as learning milestones, a done slot surviving a same-day replan, and the live deadline file the published page reads from Drive.

    python tools/test_plan.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan  # noqa: E402

TODAY = dt.date(2026, 9, 10)
PATHS = ("ROOT", "STUDY", "ASSESS", "PLAN", "PAGE", "GRADES", "PROGRESS", "DEADLINES", "QUEUE", "SUBJECTS", "SCHEDULE", "LIVE", "NOTIFY_STATE")


def topic(tid: str, subject: str, nq: int = 20, nquiz: int = 30, ncard: int = 20) -> dict:
    units = [{"id": f"{tid}:q{i}", "type": "question", "sec": 70, "w": round(0.9 - i * 0.01, 3)} for i in range(nq)]
    units += [{"id": f"{tid}:z{i}", "type": "quiz", "sec": 45, "w": 0.8} for i in range(nquiz)]
    units += [{"id": f"{tid}:c{i}", "type": "card", "sec": 25, "w": 0.7} for i in range(ncard)]
    return {"topic": tid, "subject": subject, "title": tid, "page": f"study/{subject}/{tid}.html", "rooms": [], "mnemonics": [],
            "seconds": sum(u["sec"] for u in units), "units": units}


def assess(aid: str, subject: str, date: str, topics: list[str], kind: str = "test", review: int = 2) -> dict:
    return {"id": aid, "subject": subject, "subjectName": subject, "title": aid, "kind": kind, "date": date,
            "confidence": "estimated", "topics": topics, "waiting": [], "reviewDays": review}


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        study = root / "study"
        study.mkdir()
        self.saved = {k: getattr(plan, k) for k in PATHS}
        plan.ROOT, plan.STUDY = root, study
        plan.ASSESS, plan.PLAN, plan.PAGE = study / "assessments.json", study / "plan.json", study / "planas.html"
        plan.GRADES, plan.PROGRESS, plan.DEADLINES = study / "grades.json", study / "progress.json", study / "deadlines.json"
        plan.QUEUE, plan.SUBJECTS, plan.SCHEDULE = root / "homework" / "queue.json", study / "subjects.json", study / "schedule.json"
        plan.LIVE, plan.NOTIFY_STATE = study / "planas-live.json", root / ".notify-state.json"
        self.study = study

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(plan, k, v)
        self.tmp.cleanup()

    def write(self, name: str, data):
        p = self.study / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def units(self, t: dict):
        self.write(f"{t['subject']}/{t['topic']}.units.json", t)

    @staticmethod
    def parts(p: dict, aid: str) -> list[tuple[str, str, dict]]:
        return [(d["date"], s["slot"], part) for d in p["days"] for s in d["slots"] for part in s["parts"] if part["assessment"] == aid]

    def test_five_tests_on_one_day_all_get_imitation(self):
        reg = []
        for s in ("biologija", "matematika", "lietuviu", "anglu", "geografija"):
            t = topic(f"{s}-t", s)
            self.units(t)
            reg.append(assess(f"{s}-isk", s, "2026-11-23", [t["topic"]]))
        self.write("assessments.json", {"assessments": reg})
        p = plan.Planner(TODAY).run()
        for a in p["assessments"]:
            self.assertTrue([x for x in self.parts(p, a["id"]) if x[2]["phase"] == "imitation"], f"{a['id']} got no imitation slot")
            self.assertGreater(a["coverage"]["imitationPlaced"], 0, a["id"])
        morning = [x for d, sl, x in ((d, s, part) for d in p["days"] if d["date"] == "2026-11-23" for s in d["slots"] if s["slot"] == "rytas" for part in s["parts"])]
        self.assertTrue(morning and all(x["phase"] == "pretest" for x in morning), "the test morning must be the recap only")

    def test_start_in_the_afternoon(self):
        t = topic("bio-t", "biologija")
        self.units(t)
        self.write("assessments.json", {"assessments": [assess("bio-isk", "biologija", "2026-11-23", ["bio-t"])]})
        self.write("schedule.json", {"start": "2026-09-10", "startSlot": "diena"})
        self.write("plan.json", {"days": [{"date": "2026-09-09", "dow": "Tr", "slots": [
            {"slot": "rytas", "parts": [], "items": [{"u": "bio-t:q0", "mode": "new"}], "phase": "learn", "sec": 70}]}]})
        p = plan.Planner(TODAY).run()
        self.assertEqual(p["days"][0]["date"], "2026-09-10", "a day before the start must not stay as history")
        first = {s["slot"]: s for s in p["days"][0]["slots"]}
        self.assertEqual(first["rytas"]["phase"], "before-start")
        self.assertEqual(first["rytas"]["items"], [])
        self.assertNotEqual(first["diena"]["phase"], "before-start")
        self.assertTrue(first["diena"]["items"])
        taught = {it["u"] for d in p["days"] for s in d["slots"] for it in s["items"] if it.get("mode") == "new"}
        self.assertIn("bio-t:q0", taught, "a unit from before the start was treated as already learned")
        self.assertEqual((p["start"], p["startSlot"]), ("2026-09-10", "diena"))

    def test_worked_practice_reaches_test_imitation(self):
        t = topic("math-drills", "matematika", nq=0, nquiz=0, ncard=0)
        t["units"] = [{"id": "math-drills:p0", "type": "practice", "sec": 100,
                       "w": 0.75, "q": "Solve x + 2 = 5", "a": "x = 3", "steps": ["Subtract 2."]}]
        t["seconds"] = 100
        self.units(t)
        self.write("assessments.json", {"assessments": [
            assess("math-isk", "matematika", "2026-11-23", ["math-drills"])]})
        p = plan.Planner(TODAY).run()
        items = [it for d in p["days"] for s in d["slots"] for it in s["items"]]
        self.assertTrue(any(it["u"] == "math-drills:p0" and it["mode"] == "test" for it in items))
        self.assertEqual(p["assessments"][0]["coverage"]["imitationTotal"], 1)
        self.assertEqual(p["assessments"][0]["coverage"]["imitationPlaced"], 1)

    def test_paragraph_chain_is_complete_and_in_separate_ordered_slots(self):
        self._check_paragraph_chain('2026-11-23', True)

    def test_paragraph_chain_is_not_started_if_it_cannot_finish(self):
        self.write('schedule.json', {'start':'2026-09-10','startSlot':'diena'})
        self._check_paragraph_chain('2026-09-11', False)

    def test_replan_after_missed_or_completed_paragraph_start(self):
        for completed in range(4):
            with self.subTest(completed_stages=completed):
                self.write('plan.json', {'days':[]})
                self.write('progress.json', {'done':{},'doneItems':{},'rec':{}})
                self._check_paragraph_chain('2026-11-23', True)
                first=plan.Planner(TODAY).run()
                stages=[(d,s) for d in first['days'] for s in d['slots'] if any(it['u'].startswith('lt-chain:p') for it in s['items'])]
                day,slot=stages[max(0,completed-1)]
                self.write('plan.json',first)
                self.write('progress.json',{'done':{d['date']+'|'+s['slot']:1 for d,s in stages[:completed]},'doneItems':{},'rec':{}})
                rebuild_day=plan.s2d(day['date'])+(dt.timedelta(days=1) if not completed else dt.timedelta())
                again=plan.Planner(rebuild_day).run()
                self.assertTrue(any(d['date']==day['date'] for d in again['days']),'history lost')
                done_keys={d['date']+'|'+s['slot'] for d,s in stages[:completed]}
                future=[it['u'] for d in again['days'] if plan.s2d(d['date'])>=rebuild_day for s in d['slots'] if d['date']+'|'+s['slot'] not in done_keys for it in s['items'] if it['u'].startswith('lt-chain:p')]
                self.assertEqual(future,[f'lt-chain:p{i}' for i in range(completed+1,4)])

    def test_completed_paragraph_boundary_is_per_topic(self):
        """Reviewer 2026-09-10: a spelling-only test before a combined įskaita must not restart the PROSE paragraph already
        written, while the SPELLING paragraph written before that test is practised again; an online milestone resets nothing."""
        for tid in ('lt-prose', 'lt-spell'):
            t = topic(tid, 'lietuviu', nq=1, nquiz=3, ncard=0)
            t['units'] += [{'id': f'{tid}:p{i}', 'type': 'practice', 'sec': 180 if i == 1 else 240, 'w': .75,
                            'chain': 'paragraph', 'stage': i, 'q': 'Write next part', 'a': 'Check'} for i in (1, 2, 3)]
            t['seconds'] = sum(u['sec'] for u in t['units'])
            self.units(t)
        self.write('assessments.json', {'assessments': [
            assess('lt-spell-test', 'lietuviu', '2026-10-01', ['lt-spell']),
            assess('lt-online', 'lietuviu', '2026-10-05', ['lt-prose'], kind='online-test', review=0),
            assess('lt-isk', 'lietuviu', '2026-11-23', ['lt-prose', 'lt-spell'])]})
        written = dt.datetime(2026, 9, 20, 18).timestamp() * 1000
        self.write('progress.json', {'done': {}, 'rec': {}, 'doneItems': {f'{tid}:p{i}': written for tid in ('lt-prose', 'lt-spell') for i in (1, 2, 3)}})
        p = plan.Planner(dt.date(2026, 9, 25)).run()
        tests = [(it['assessment'], it['u']) for d in p['days'] for s in d['slots'] for it in s['items'] if it.get('mode') == 'test']
        self.assertFalse([u for _, u in tests if u.startswith('lt-prose:p')], 'a prose paragraph already written was restarted')
        self.assertFalse([u for aid, u in tests if aid == 'lt-spell-test' and u.startswith('lt-spell:p')])
        self.assertEqual([u for aid, u in tests if aid == 'lt-isk' and u.startswith('lt-spell:p')], ['lt-spell:p1', 'lt-spell:p2', 'lt-spell:p3'])

    def test_slots_stretch_only_when_an_in_person_test_needs_it(self):
        """Owner 2026-09-10 ("Up to 20 min/day"): a test whose posted units cannot all be taught in 3 x 5 min stretches its days,
        never past 20 min; material that fits and an online milestone leave every slot at 5 min."""
        self.units(topic("bio-t", "biologija"))
        self.write("assessments.json", {"assessments": [assess("bio-isk", "biologija", "2026-11-23", ["bio-t"])]})
        p = plan.build_plan(TODAY)
        self.assertFalse([s for d in p["days"] for s in d["slots"] if "cap" in s], "nothing needed stretching")
        self.units(topic("bio-big", "biologija", nq=55, nquiz=0, ncard=0))
        self.write("assessments.json", {"assessments": [assess("bio-soon", "biologija", "2026-09-16", ["bio-big"], review=1)]})
        self.assertLess(plan.Planner(TODAY).run()["assessments"][0]["coverage"]["weighted"], 1, "the case must not fit in 15 min")
        p = plan.build_plan(TODAY)
        self.assertEqual(p["assessments"][0]["coverage"]["weighted"], 1)
        self.assertTrue([s for d in p["days"] for s in d["slots"] if s.get("cap", plan.SLOT_SEC) > plan.SLOT_SEC])
        for d in p["days"]:
            self.assertLessEqual(sum(s["sec"] for s in d["slots"]), 1200, d["date"])
        self.write("assessments.json", {"assessments": [assess("bio-online", "biologija", "2026-09-16", ["bio-big"], kind="online-test", review=0)]})
        p = plan.build_plan(TODAY)
        self.assertFalse([s for d in p["days"] for s in d["slots"] if "cap" in s], "an online milestone stretched a day")

    def test_unit_an_earlier_test_could_not_fit_is_learned_for_the_exam(self):
        self.units(topic("bio-big", "biologija", nq=120, nquiz=0, ncard=0))
        self.write("assessments.json", {"assessments": [assess("bio-soon", "biologija", "2026-09-13", ["bio-big"], review=1),
                                                         assess("bio-vbe", "biologija", "2026-12-01", ["bio-big"], kind="exam", review=3)]})
        soon, vbe = plan.build_plan(TODAY)["assessments"]
        self.assertLess(soon["coverage"]["weighted"], 1)
        self.assertEqual(vbe["coverage"]["weighted"], 1, "units the early test could not fit were never taught for the exam")

    def test_every_practice_skill_gets_a_variant_before_repeats(self):
        """Reviewer 2026-09-10: what imitation leaves out must be extra variants, never a whole skill."""
        self.write("assessments.json", {"assessments": []})
        p = plan.Planner(TODAY)
        drills = [{"id": f"x:pA{i}", "type": "practice", "sec": 100, "w": .75, "topic": "x", "t": "A"} for i in range(5)]
        drills.append({"id": "x:pB", "type": "practice", "sec": 100, "w": .75, "topic": "x", "t": "B"})
        out = p.split_imitation({"id": "x-isk", "kind": "test", "_r": 1, "_imit": drills}, [("2026-09-20", 0)])
        placed = [it["u"] for it in out["2026-09-20"][0]]
        self.assertEqual(len(placed), (plan.SLOT_SEC - plan.IMIT_REVIEW_SEC) // 100)   # the slot keeps IMIT_REVIEW_SEC for due reviews (2026-09-12)
        self.assertIn("x:pB", placed, "skill B lost to extra variants of skill A")

    def test_priority_cards_are_learned_daily_not_left_to_the_last_weeks(self):
        """Owner 2026-09-10 ("Priority cards only"): a card marked `learn` is taught in the learning window like a question and
        is not dealt again as imitation; an unmarked card stays final-weeks practice."""
        t = topic("en-t", "anglu", nq=10, nquiz=2, ncard=4)
        for u in t["units"]:
            if u["id"] == "en-t:c0":
                u["learn"] = True
        self.units(t)
        self.write("assessments.json", {"assessments": [assess("en-isk", "anglu", "2026-11-23", ["en-t"])]})
        p = plan.build_plan(TODAY)
        modes: dict[str, set] = {}
        for d in p["days"]:
            for s in d["slots"]:
                for it in s["items"]:
                    modes.setdefault(it["u"], set()).add(it["mode"])
        self.assertIn("new", modes.get("en-t:c0", set()), "a priority card was not taught as daily material")
        self.assertNotIn("test", modes.get("en-t:c0", set()), "a priority card was also dealt as imitation")
        self.assertNotIn("new", modes.get("en-t:c1", set()), "an ordinary card became daily material")
        self.assertEqual(p["assessments"][0]["coverage"]["unitsTotal"], 11)

    def test_online_milestone_never_uses_stretched_time(self):
        """Reviewer 2026-09-10 (round 4): the stretch is decided per in-person test, so a milestone part must fit inside the
        normal 5 minutes of its slot even when that slot is stretched for another test."""
        self.units(topic("geo-t", "geografija", nq=40, nquiz=0, ncard=0))
        self.units(topic("bio-big", "biologija", nq=55, nquiz=0, ncard=0))
        self.write("assessments.json", {"assessments": [
            assess("geo-online", "geografija", "2026-09-18", ["geo-t"], kind="online-test", review=0),
            assess("bio-soon", "biologija", "2026-09-16", ["bio-big"], review=1)]})
        p = plan.build_plan(TODAY)
        self.assertTrue([s for d in p["days"] for s in d["slots"] if s.get("cap", plan.SLOT_SEC) > plan.SLOT_SEC], "the case must stretch")
        for d in p["days"]:
            for s in d["slots"]:
                before = 0
                for part in s["parts"]:
                    if part["assessment"] == "geo-online":
                        self.assertLessEqual(before + part["sec"], plan.SLOT_SEC + 20, (d["date"], s["slot"]))
                    before += part["sec"]

    def _check_paragraph_chain(self, date, fits):
        t=topic('lt-chain','lietuviu',nq=1,nquiz=3,ncard=0)
        t['units'] += [{'id':f'lt-chain:p{i}','type':'practice','sec':180 if i==1 else 240,
                       'w':.75,'chain':'paragraph','stage':i,'q':'Write next part','a':'Check'} for i in (1,2,3)]
        t['seconds']=sum(u['sec'] for u in t['units'])
        self.units(t)
        self.write('assessments.json',{'assessments':[assess('lt-isk','lietuviu',date,['lt-chain'])]})
        p=plan.Planner(TODAY).run()
        self.assertEqual(p['assessments'][0]['coverage']['imitationTotal'],6)
        placed=[(d['date'],s['slot'],it['u']) for d in p['days'] for s in d['slots'] for it in s['items'] if it['u'].startswith('lt-chain:p')]
        if fits:
            self.assertEqual([x[2] for x in placed],['lt-chain:p1','lt-chain:p2','lt-chain:p3'])
            self.assertEqual(len({x[:2] for x in placed}),3)
        else:
            self.assertEqual(placed,[])
        quiz=[it for d in p['days'] for s in d['slots'] for it in s['items'] if it['u'].startswith('lt-chain:z')]
        self.assertTrue(quiz,'paragraph reservation hid every quiz')

    def test_large_drill_bank_does_not_starve_other_subjects(self):
        reg = []
        for s in ("biologija", "matematika", "lietuviu", "anglu", "geografija"):
            t = topic(s + "-t", s, nq=2, nquiz=3, ncard=3)
            if s == "lietuviu":
                t["units"] += [{"id": f"{s}:p{i}", "type": "practice", "sec": 100,
                                "w": .75, "q": "Prompt", "a": "Answer"} for i in range(120)]
                t["seconds"] = sum(u["sec"] for u in t["units"])
            self.units(t)
            reg.append(assess(s + "-isk", s, "2026-11-23", [t["topic"]]))
        self.write("assessments.json", {"assessments": reg})
        p = plan.Planner(TODAY).run()
        for a in p["assessments"]:
            self.assertGreater(a["coverage"]["imitationPlaced"], 0, a["id"])
        selected = {it['u'] for d in p['days'] for s in d['slots'] for it in s['items'] if it['mode']=='test'}
        for s in ("biologija", "matematika", "lietuviu", "anglu", "geografija"):
            self.assertTrue(any(uid.startswith(s+'-t:z') for uid in selected), s+' got no quiz')
        self.assertTrue(any(uid.startswith('lietuviu:p') for uid in selected), 'worked practice vanished')
        for d in p["days"]:
            for slot in d["slots"]:
                if slot["phase"] == "imitation":
                    self.assertLessEqual(slot["sec"], plan.SLOT_SEC)

    def test_online_test_is_a_learning_milestone(self):
        t = topic("geo-t", "geografija", nq=20, nquiz=10, ncard=10)
        self.units(t)
        self.write("assessments.json", {"assessments": [
            assess("geo-online", "geografija", "2026-09-28", ["geo-t"], kind="online-test", review=0),
            assess("geo-isk", "geografija", "2026-11-23", ["geo-t"])]})
        p = plan.Planner(TODAY).run()
        new_day = {it["u"]: d["date"] for d in p["days"] for s in d["slots"] for it in s["items"] if it.get("mode") == "new"}
        for u in t["units"]:
            if u["type"] == "question":
                self.assertLess(new_day.get(u["id"], "9999-12-31"), "2026-09-28", f"{u['id']} taught after its online test")
        self.assertFalse([x for x in self.parts(p, "geo-online") if x[2]["phase"] in ("imitation", "pretest")])
        self.assertTrue([x for x in self.parts(p, "geo-isk") if x[2]["phase"] == "imitation"])
        online = next(a for a in p["assessments"] if a["id"] == "geo-online")
        self.assertTrue(online["milestone"])
        self.assertEqual(online["coverage"]["imitationDays"], 0)

    def test_done_slot_today_survives_a_replan(self):
        t = topic("bio-t", "biologija")
        self.units(t)
        self.write("assessments.json", {"assessments": [assess("bio-isk", "biologija", "2026-11-23", ["bio-t"])]})
        first = plan.Planner(TODAY).run()
        self.write("plan.json", first)
        diena = next(s for d in first["days"] if d["date"] == "2026-09-10" for s in d["slots"] if s["slot"] == "diena")
        self.assertTrue(diena["items"])
        self.write("progress.json", {"done": {"2026-09-10|diena": 1757500000000}, "rec": {}, "doneItems": {}})
        t2 = topic("bio-t2", "biologija")   # new material lands the same afternoon -> replan
        self.units(t2)
        self.write("assessments.json", {"assessments": [assess("bio-isk", "biologija", "2026-11-23", ["bio-t", "bio-t2"])]})
        again = plan.Planner(TODAY).run()
        diena2 = next(s for d in again["days"] if d["date"] == "2026-09-10" for s in d["slots"] if s["slot"] == "diena")
        self.assertEqual(diena2["items"], diena["items"], "a slot the owner finished was rewritten")
        studied = {it["u"] for it in diena["items"] if it.get("mode") == "new"}
        later = {it["u"] for d in again["days"] for s in d["slots"] if not (d["date"] == "2026-09-10" and s["slot"] == "diena")
                 for it in s["items"] if it.get("mode") == "new"}
        self.assertFalse(studied & later, "units finished today were scheduled as new again")

    def test_live_file_rewrites_only_on_change(self):
        self.write("assessments.json", {"assessments": [assess("bio-isk", "biologija", "2026-11-23", [])]})
        plan.NOTIFY_STATE.write_text(json.dumps({"checkedAt": dt.datetime(2026, 9, 10, 11, 5).timestamp()}), encoding="utf-8")
        self.assertEqual(plan.live_export(), "updated")
        data = json.loads(plan.LIVE.read_text(encoding="utf-8"))
        self.assertEqual((data["v"], data["assessments"][0]["date"], data["checkedAt"]), (1, "2026-11-23", "2026-09-10T11:05"))
        self.assertEqual(plan.live_export(), "unchanged")
        self.write("deadlines.json", {"events": [{"id": 1, "courseId": 23, "course": "Biologija", "name": "K-1 turi būti pateikta",
                                                 "module": "assign", "eventtype": "due", "due": "2026-09-30T23:59",
                                                 "url": "https://moodle.ksjmc.lt/mod/assign/view.php?id=5"}]})
        self.assertEqual(plan.live_export(), "updated")
        self.assertEqual(json.loads(plan.LIVE.read_text(encoding="utf-8"))["deadlines"][0]["time"], "23:59")
        plan.NOTIFY_STATE.write_text(json.dumps({"checkedAt": dt.datetime(2026, 9, 10, 12, 5).timestamp()}), encoding="utf-8")
        self.assertEqual(plan.live_export(), "unchanged", "an hour-later check must not churn Drive")
        plan.NOTIFY_STATE.write_text(json.dumps({"checkedAt": dt.datetime(2026, 9, 10, 16, 5).timestamp()}), encoding="utf-8")
        self.assertEqual(plan.live_export(), "updated", "the check time must move on so the page can tell a dead PC")

    # ---- audit 2026-09-12 -------------------------------------------------------------------------------------------------
    def test_reviews_continue_inside_the_imitation_window(self):
        """budget = 0 in an imitation slot used to silence every spaced review for the weeks before an įskaita."""
        t = topic("bio-t", "biologija", nq=100, nquiz=150, ncard=60)   # learning runs to early October and a big test bank opens a two-week window, like the real November
        self.units(t)
        self.write("assessments.json", {"assessments": [assess("bio-isk", "biologija", "2026-10-20", ["bio-t"], review=2)]})
        p = plan.build_plan(TODAY)
        a = p["assessments"][0]
        imit_days = [d for d in p["days"] if a["coverage"]["learnEnd"] < d["date"] < "2026-10-20"]
        self.assertGreaterEqual(len(imit_days), 7, "the case must have a long imitation window")
        reviews = sum(1 for d in imit_days for s in d["slots"] for it in s["items"] if it["mode"] == "review")
        self.assertGreater(reviews, 0, "no spaced review inside the imitation window")
        for d in imit_days:
            for s in d["slots"]:
                self.assertLessEqual(s["sec"], s.get("cap", plan.SLOT_SEC) + 20, (d["date"], s["slot"]))

    def test_review_share_and_slack_are_per_slot(self):
        reg = []
        for s in ("biologija", "matematika", "lietuviu"):
            t = topic(f"{s}-t", s, nq=40, nquiz=0, ncard=0)
            self.units(t)
            reg.append(assess(f"{s}-isk", s, "2026-11-23", [t["topic"]]))
        self.write("assessments.json", {"assessments": reg})
        p = plan.build_plan(TODAY)
        for d in p["days"]:
            for s in d["slots"]:
                if s["phase"] in ("free", "before-start", "imitation", "pretest"):
                    continue
                rev = sum(1 for it in s["items"] if it["mode"] == "review") * plan.REVIEW_SEC
                self.assertLessEqual(rev, s.get("cap", plan.SLOT_SEC) * plan.REVIEW_SHARE + 1e-9, (d["date"], s["slot"], "reviews over the slot share"))
                self.assertLessEqual(s["sec"], s.get("cap", plan.SLOT_SEC) + 20, (d["date"], s["slot"], "more than one 20-s slack"))

    def test_every_imitation_unit_is_seen_once_before_the_final_window(self):
        """309 of 893 real units were shown exactly once, in the last three weeks; with capacity to spare the early practice pass
        shows every quiz/card once earlier, and the coverage says so."""
        t = topic("geo-t", "geografija", nq=10, nquiz=60, ncard=40)
        self.units(t)
        self.write("assessments.json", {"assessments": [assess("geo-isk", "geografija", "2026-11-23", ["geo-t"])]})
        p = plan.build_plan(TODAY)
        a = p["assessments"][0]
        self.assertEqual(a["coverage"]["imitationSeen"], a["coverage"]["imitationTotal"])
        exposed = {it["u"] for d in p["days"] for s in d["slots"] for it in s["items"] if it["mode"] == "test"}
        self.assertEqual(len(exposed), 100)
        early = [d["date"] for d in p["days"] for s in d["slots"] for part in s["parts"] if part["phase"] == "practice"]
        self.assertTrue(early and min(early) <= a["coverage"]["learnEnd"], "early practice never ran")
        new_days = sorted(d["date"] for d in p["days"] for s in d["slots"] for it in s["items"] if it["mode"] == "new")
        self.assertLessEqual(new_days[-1], min(early), "early practice must wait until the topic's core is complete (glance round 7)")

    def test_stale_progress_refuses_a_build(self):
        self.write("schedule.json", {"start": "2026-09-01", "startSlot": "rytas"})
        self.write("progress.json", {"done": {}, "rec": {}, "doneItems": {}})
        self.assertEqual(plan.progress_stale(TODAY), "")
        old = (dt.datetime.now() - dt.timedelta(hours=plan.PROGRESS_STALE_H + 5)).timestamp()
        os.utime(plan.PROGRESS, (old, old))
        self.assertIn("pulled", plan.progress_stale(TODAY))
        self.assertEqual(plan.progress_stale(dt.date(2026, 8, 20)), "", "before the start nothing is stale")
        plan.PROGRESS.unlink()
        self.assertIn("missing", plan.progress_stale(TODAY), "a missing file after the start must ask for a pull (glance round 13)")
        self.write("progress.json", {"done": {}, "rec": {}, "doneItems": {}})
        os.utime(plan.PROGRESS, (old, old))   # stale again for the refusal below
        t = topic("bio-t", "biologija", nq=6, nquiz=0, ncard=0)
        self.units(t)
        self.write("assessments.json", {"assessments": [assess("bio-isk", "biologija", "2026-11-23", ["bio-t"])]})
        first = plan.Planner(dt.date(2026, 9, 8)).run()
        self.write("plan.json", first)
        taught = {it["u"] for d in first["days"] if d["date"] < "2026-09-10" for s in d["slots"] for it in s["items"] if it["mode"] == "new"}
        self.assertTrue(taught)
        with self.assertRaises(SystemExit):
            plan.cmd_plan(TODAY)
        again = plan.cmd_plan(TODAY, assume_done=True)   # glance 2026-09-12: the override must really treat the untracked slots as done
        retaught = {it["u"] for d in again["days"] if d["date"] >= "2026-09-10" for s in d["slots"] for it in s["items"] if it["mode"] == "new"}
        self.assertFalse(taught & retaught, "--assume-done still re-taught units of the untracked days")

    def test_completed_exposure_does_not_return_to_the_first_pass(self):
        """Glance 2026-09-12: a quiz shown in test mode before a rebuild must not be dealt again as early practice."""
        t = topic("geo-t", "geografija", nq=4, nquiz=30, ncard=0)
        self.units(t)
        self.write("assessments.json", {"assessments": [assess("geo-isk", "geografija", "2026-11-23", ["geo-t"])]})
        first = plan.build_plan(TODAY)
        self.write("plan.json", first)
        early = [(d["date"], s["slot"], it["u"]) for d in first["days"] for s in d["slots"] for part in s["parts"] if part["phase"] == "practice" for it in part["items"]]
        self.assertTrue(early, "the case must have early practice")
        day, slot, uid = early[0]
        self.write("progress.json", {"done": {f"{day}|{slot}": 1}, "rec": {}, "doneItems": {}})
        again = plan.build_plan(plan.s2d(day) + dt.timedelta(days=1))
        later = [it["u"] for d in again["days"] if d["date"] > day for s in d["slots"] for part in s["parts"] if part["phase"] == "practice" for it in part["items"]]
        self.assertNotIn(uid, later, "a completed exposure was dealt again as a first pass")
        cov = again["assessments"][0]["coverage"]
        self.assertGreaterEqual(cov["imitationSeen"], 1)

    def test_a_failed_unit_restarts_its_intervals(self):
        t = topic("bio-t", "biologija", nq=5, nquiz=0, ncard=0)
        self.units(t)
        self.write("assessments.json", {"assessments": [assess("bio-isk", "biologija", "2026-11-23", ["bio-t"])]})
        first = plan.Planner(TODAY).run()
        self.write("plan.json", first)
        learned = next(d["date"] for d in first["days"] for s in d["slots"] for it in s["items"] if it["u"] == "bio-t:q0" and it["mode"] == "new")
        later = plan.s2d(learned) + dt.timedelta(days=9)   # after the +1/+3/+7 reviews, before the +14 one
        done = {f"{d['date']}|{s['slot']}": 1 for d in first["days"] if plan.s2d(d["date"]) < later for s in d["slots"] if s["items"]}
        failed_at = dt.datetime.combine(later - dt.timedelta(days=1), dt.time(20)).timestamp() * 1000
        self.write("progress.json", {"done": done, "doneItems": {}, "rec": {"bio-t:q0": {"ok": 1, "bad": 2, "last": failed_at, "lastOk": False}}})
        again = plan.Planner(later).run()
        nxt = next((d["date"] for d in again["days"] if plan.s2d(d["date"]) >= later for s in d["slots"] for it in s["items"]
                    if it["u"] == "bio-t:q0" and it["mode"] == "review"), None)
        self.assertEqual(nxt, plan.d2s(later), "a unit failed yesterday must come back today, not at +14 d")
        # glance 2026-09-12: the restart must survive the next rebuild - after the remedial review the ladder continues at +1/+3, not +30
        self.write("plan.json", again)
        done2 = {f"{d['date']}|{s['slot']}": 1 for d in again["days"] if plan.s2d(d["date"]) <= later for s in d["slots"] if s["items"]}
        self.write("progress.json", {"done": done2, "doneItems": {}, "rec": {"bio-t:q0": {"ok": 1, "bad": 2, "last": failed_at, "lastOk": False}}})
        third = plan.Planner(later + dt.timedelta(days=1)).run()
        nxt2 = next((d["date"] for d in third["days"] if plan.s2d(d["date"]) > later for s in d["slots"] for it in s["items"]
                     if it["u"] == "bio-t:q0" and it["mode"] == "review"), None)
        self.assertEqual(nxt2, plan.d2s(later + dt.timedelta(days=plan.INTERVALS[1])), "the restarted ladder was lost on the next rebuild")
        # and when the remedial answer was CORRECT (glance 2026-09-12 round 5): the ladder still continues from the restart, not from lifetime counts
        ok_at = dt.datetime.combine(later, dt.time(20)).timestamp() * 1000
        self.write("progress.json", {"done": done2, "doneItems": {}, "rec": {"bio-t:q0": {"ok": 2, "bad": 2, "last": ok_at, "lastOk": True}}})
        fourth = plan.Planner(later + dt.timedelta(days=1)).run()
        nxt3 = next((d["date"] for d in fourth["days"] if plan.s2d(d["date"]) > later for s in d["slots"] for it in s["items"]
                     if it["u"] == "bio-t:q0" and it["mode"] == "review"), None)
        self.assertEqual(nxt3, plan.d2s(later + dt.timedelta(days=plan.INTERVALS[1])), "a correct remedial answer restored the long interval")

    def test_failure_during_a_scheduled_review_keeps_its_restart(self):
        """Glance 2026-09-12 round 6: a failure judged on the day of a scheduled review must restart the ladder from that day,
        survive a correct remedial answer and another rebuild."""
        t = topic("bio-t", "biologija", nq=5, nquiz=0, ncard=0)
        self.units(t)
        self.write("assessments.json", {"assessments": [assess("bio-isk", "biologija", "2026-11-23", ["bio-t"])]})
        first = plan.Planner(TODAY).run()
        self.write("plan.json", first)
        reviews = sorted(d["date"] for d in first["days"] for s in d["slots"] for it in s["items"] if it["u"] == "bio-t:q0" and it["mode"] == "review")
        fail_day = plan.s2d(reviews[2])   # the +7 review is the one that fails
        done = {f"{d['date']}|{s['slot']}": 1 for d in first["days"] if plan.s2d(d["date"]) <= fail_day for s in d["slots"] if s["items"]}
        failed_at = dt.datetime.combine(fail_day, dt.time(20)).timestamp() * 1000
        self.write("progress.json", {"done": done, "doneItems": {}, "rec": {"bio-t:q0": {"ok": 2, "bad": 1, "last": failed_at, "lastOk": False}}})
        second = plan.Planner(fail_day + dt.timedelta(days=1)).run()
        nxt = next((d["date"] for d in second["days"] if plan.s2d(d["date"]) > fail_day for s in d["slots"] for it in s["items"] if it["u"] == "bio-t:q0" and it["mode"] == "review"), None)
        self.assertEqual(nxt, plan.d2s(fail_day + dt.timedelta(days=1)), "the failed review did not restart the ladder")
        self.write("plan.json", second)
        rem = fail_day + dt.timedelta(days=1)
        done2 = {f"{d['date']}|{s['slot']}": 1 for d in second["days"] if plan.s2d(d["date"]) <= rem for s in d["slots"] if s["items"]}
        ok_at = dt.datetime.combine(rem, dt.time(20)).timestamp() * 1000
        self.write("progress.json", {"done": done2, "doneItems": {}, "rec": {"bio-t:q0": {"ok": 3, "bad": 1, "last": ok_at, "lastOk": True}}})
        third = plan.Planner(rem + dt.timedelta(days=1)).run()
        nxt2 = next((d["date"] for d in third["days"] if plan.s2d(d["date"]) > rem for s in d["slots"] for it in s["items"] if it["u"] == "bio-t:q0" and it["mode"] == "review"), None)
        self.assertEqual(nxt2, plan.d2s(rem + dt.timedelta(days=plan.INTERVALS[1])), "the restart was lost after a correct remedial answer")

    def test_build_order_catches_a_generated_file_older_than_its_source(self):
        """2026-09-12: units.json was rebuilt AFTER plan.json, so the published hub kept old content. Each link of the chain
        <topic>.json -> .html -> .units.json -> plan.json -> planas.html must be caught, and backups must be ignored."""
        t = topic("lt-t", "lietuviu", nq=2, nquiz=2, ncard=0)
        self.units(t)
        src = self.study / "lietuviu" / "lt-t.json"
        page = self.study / "lietuviu" / "lt-t.html"
        units = self.study / "lietuviu" / "lt-t.units.json"
        backup = self.study / "lietuviu" / "lt-t.lt-backup.json"   # no .html sibling: must never be reported
        for p, txt in ((src, "{}"), (page, "<html>"), (backup, "{}")):
            p.write_text(txt, encoding="utf-8")
        self.write("assessments.json", {"assessments": [assess("lt-isk", "lietuviu", "2026-11-23", ["lt-t"])]})
        plan.PLAN.write_text("{}", encoding="utf-8")
        plan.PAGE.write_text("<html>", encoding="utf-8")
        now = dt.datetime.now().timestamp()
        for i, p in enumerate((src, page, units, plan.PLAN, plan.PAGE)):   # correct order: each newer than the last
            os.utime(p, (now + i * 10, now + i * 10))
        self.assertEqual(plan.build_order_problems(), [], "a correctly ordered chain must be silent")
        os.utime(units, (now, now))   # the real 2026-09-12 case: units older than the page it came from
        problems = plan.build_order_problems()
        self.assertTrue(any("lt-t.units.json is older than" in x for x in problems), problems)
        self.assertTrue(any("units.py extract" in x for x in problems), problems)
        os.utime(units, (now + 20, now + 20))
        os.utime(plan.PLAN, (now, now))   # plan older than the units it should have read
        self.assertTrue(any("plan.json is older than" in x for x in plan.build_order_problems()))
        os.utime(plan.PLAN, (now + 30, now + 30))
        os.utime(plan.PAGE, (now, now))   # page older than the plan
        self.assertTrue(any("planas.html is older than" in x for x in plan.build_order_problems()))
        os.utime(plan.PAGE, (now + 40, now + 40))
        os.utime(page, (now - 20, now - 20))   # html older than its content JSON (src sits at `now`)
        self.assertTrue(any("topic.py build" in x for x in plan.build_order_problems()))
        self.assertFalse([x for x in plan.build_order_problems() if "lt-backup" in x], "a backup JSON must be ignored")
        os.utime(page, (now + 10, now + 10))
        self.assertEqual(plan.build_order_problems(), [], "restored chain must be silent again")

        # glance round 4, finding 1: a MISSING output must be reported, not silently accepted
        units.rename(units.with_suffix(".bak"))
        self.assertTrue(any("lt-t.units.json is missing" in x and "units.py extract" in x for x in plan.build_order_problems()))
        units.with_suffix(".bak").rename(units)
        os.utime(units, (now + 20, now + 20))
        plan.PAGE.unlink()
        self.assertTrue(any("planas.html is missing" in x for x in plan.build_order_problems()))
        plan.PAGE.write_text("<html>", encoding="utf-8"); os.utime(plan.PAGE, (now + 40, now + 40))
        fresh = self.study / "lietuviu" / "lt-new.json"   # a topic JSON (title + questions) whose page was never built
        fresh.write_text(json.dumps({"title": "Nauja", "questions": []}), encoding="utf-8")
        self.assertTrue(any("lt-new.html is missing" in x and "topic.py build" in x for x in plan.build_order_problems()))
        fresh.unlink()
        archive = self.study / "lietuviu" / "vbe-archive.json"   # an archive (no title/questions, no page) is never reported
        archive.write_text(json.dumps({"tasks": []}), encoding="utf-8")
        self.assertEqual(plan.build_order_problems(), [], "an archive JSON must not be mistaken for an unbuilt topic")

        # glance round 4, finding 2: shared rendering inputs inlined into the pages are dependencies
        tools = plan.ROOT / "tools"; tools.mkdir(exist_ok=True)
        css = tools / "board.css"; css.write_text("/* */", encoding="utf-8")
        os.utime(css, (now + 5, now + 5))   # older than everything: silent
        self.assertEqual(plan.build_order_problems(), [])
        os.utime(css, (now + 100, now + 100))   # edited after the pages were built
        problems = plan.build_order_problems()
        self.assertTrue(any("lt-t.html is older than tools" in x and "board.css" in x and "topic.py build" in x for x in problems), problems)
        self.assertTrue(any("planas.html is older than tools" in x and "plan.py page" in x for x in problems), problems)

        # glance round 5: study/settings.json (the association switch) is an input of topic pages and of a hand page's units
        hand = self.study / "biologija" / "hand.html"; hand.parent.mkdir(exist_ok=True)
        hand_units = hand.with_name("hand.units.json")
        hand.write_text("<html>", encoding="utf-8"); hand_units.write_text("{}", encoding="utf-8")
        os.utime(hand, (now + 110, now + 110)); os.utime(hand_units, (now + 120, now + 120))
        os.utime(css, (now + 5, now + 5))
        settings = self.study / "settings.json"; settings.write_text(json.dumps({"association": False}), encoding="utf-8")
        os.utime(settings, (now + 200, now + 200))   # the switch flipped after everything was built
        problems = plan.build_order_problems()
        self.assertTrue(any("lt-t.html is older than" in x and "settings.json" in x and "topic.py build" in x for x in problems), problems)
        self.assertTrue(any("hand.units.json is older than" in x and "settings.json" in x and "units.py extract" in x for x in problems), problems)

    def test_a_failure_followed_by_a_correct_hub_repeat_still_restarts(self):
        """Glance 2026-09-12 round 8: "Nemoku", then the hub's remedial repeat answered correctly BEFORE the rebuild (lastOk true):
        the page's failAt stamp still restarts the ladder."""
        t = topic("bio-t", "biologija", nq=5, nquiz=0, ncard=0)
        self.units(t)
        self.write("assessments.json", {"assessments": [assess("bio-isk", "biologija", "2026-11-23", ["bio-t"])]})
        first = plan.Planner(TODAY).run()
        self.write("plan.json", first)
        learned = next(d["date"] for d in first["days"] for s in d["slots"] for it in s["items"] if it["u"] == "bio-t:q0" and it["mode"] == "new")
        later = plan.s2d(learned) + dt.timedelta(days=9)
        done = {f"{d['date']}|{s['slot']}": 1 for d in first["days"] if plan.s2d(d["date"]) < later for s in d["slots"] if s["items"]}
        fail_at = dt.datetime.combine(later - dt.timedelta(days=1), dt.time(19)).timestamp() * 1000
        ok_at = fail_at + 3600 * 1000
        self.write("progress.json", {"done": done, "doneItems": {}, "rec": {"bio-t:q0": {"ok": 2, "bad": 1, "last": ok_at, "lastOk": True, "failAt": fail_at}}})
        again = plan.Planner(later).run()
        nxt = next((d["date"] for d in again["days"] if plan.s2d(d["date"]) >= later for s in d["slots"] for it in s["items"]
                    if it["u"] == "bio-t:q0" and it["mode"] == "review"), None)
        self.assertEqual(nxt, plan.d2s(later), "a failure followed by a correct repeat lost its restart")

    def test_early_practice_exposes_a_shared_unit_once_per_period(self):
        """Glance 2026-09-12: an įskaita and the VBE on the same topic must not each deal the same quiz row before the įskaita."""
        t = topic("mat-t", "matematika", nq=6, nquiz=30, ncard=0)
        self.units(t)
        self.write("assessments.json", {"assessments": [assess("mat-isk", "matematika", "2026-11-23", ["mat-t"]),
                                                         assess("mat-vbe", "matematika", "2027-06-04", ["mat-t"], kind="exam", review=3)]})
        p = plan.build_plan(TODAY)
        seen: dict[str, int] = {}
        for d in p["days"]:
            if d["date"] >= "2026-11-23":
                break
            for s in d["slots"]:
                for part in s["parts"]:
                    if part["phase"] == "practice":
                        for it in part["items"]:
                            seen[it["u"]] = seen.get(it["u"], 0) + 1
        self.assertTrue(seen, "no early practice before the įskaita")
        self.assertEqual(max(seen.values()), 1, "a unit was dealt twice as early practice before the įskaita")

    def test_early_practice_waits_for_each_topic(self):
        """Glance 2026-09-12: a two-topic įskaita must not deal the second topic's quiz rows before that topic is half learned."""
        a_t = topic("lt-a", "lietuviu", nq=6, nquiz=20, ncard=0)
        b_t = topic("lt-b", "lietuviu", nq=6, nquiz=20, ncard=0)
        self.units(a_t); self.units(b_t)
        self.write("assessments.json", {"assessments": [assess("lt-isk", "lietuviu", "2026-11-23", ["lt-a", "lt-b"])]})
        p = plan.build_plan(TODAY)
        learned_b = sorted(d["date"] for d in p["days"] for s in d["slots"] for it in s["items"] if it["mode"] == "new" and it["u"].startswith("lt-b:"))
        early_b = [d["date"] for d in p["days"] for s in d["slots"] for part in s["parts"] if part["phase"] == "practice" for it in part["items"] if it["u"].startswith("lt-b:")]
        self.assertTrue(early_b, "topic B never got early practice")
        self.assertGreaterEqual(min(early_b), learned_b[-1], "topic B was practised before its core was complete")


if __name__ == "__main__":
    unittest.main(verbosity=2)
