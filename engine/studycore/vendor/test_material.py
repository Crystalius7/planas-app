#!/usr/bin/env python
"""Regression tests for tools/material.py (2026-09-10): a module next to a skipped notice is UNMAPPED, not silently skipped
(reviewer: blanket skip rules would swallow a revision sheet posted later), and a citation alone is CITED - unverified - until
a ledger verdict exists, while a known `missing` gap stays unaccounted.

    python tools/test_material.py
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import material  # noqa: E402

INDEX = """# Course
## Kurso reikalavimai
- **Skelbimai** (forum) → pages/1-skelbimai.md
- **Kartojimo lapas** (resource) → files/kartojimas.pdf
## I Skyrius
- **Skaidrės** (resource) → files/virskinimas.pptx
- **1 videopamoka** (url) → https://youtu.be/abcdefghijk
- **2 videopamoka** (url) → https://youtu.be/bcdefghijkl
"""
PATHS = ("ROOT", "STUDY", "COURSES", "MAP", "TOPICS", "ASSESS", "LEDGER", "KNOWN")


class MaterialTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = root = Path(self.tmp.name)
        self.saved = {k: getattr(material, k) for k in PATHS}
        material.ROOT, material.STUDY, material.COURSES = root, root / "study", root / "courses"
        material.MAP, material.TOPICS, material.ASSESS = root / "study/material-map.json", root / "study/topics.json", root / "study/assessments.json"
        material.LEDGER = root / "study/material"
        material.KNOWN = root / "study/material-known.json"
        course = root / "courses/1-bio"
        (course / "videos").mkdir(parents=True)
        (root / "study/bio").mkdir(parents=True)
        material.LEDGER.mkdir()
        (course / "INDEX.md").write_text(INDEX, encoding="utf-8")
        self.w("courses/1-bio/videos/index.json", {"videos": {"yt-abcdefghijk": {"id": "yt-abcdefghijk", "state": "transcribed"}}})
        self.w("study/material-map.json", {"courses": {"1": {"dir": "1-bio", "rules": [
            {"section": "Kurso reikalavimai", "kind": "forum", "match": "^Skelbimai$", "skip": "notices"},
            {"section": "I Skyrius", "topic": "bio-t"}]}}})
        self.w("study/topics.json", {"subjects": {"bio": {"topics": [{"id": "bio-t", "state": "built", "page": "study/bio/t.html", "feeds": ["bio-isk"]}]}}})
        self.w("study/bio/t.json", {"sources": "Skaidrės virskinimas.pptx; video yt-abcdefghijk 03:10"})
        self.w("study/assessments.json", {"assessments": [{"id": "bio-isk", "date": "2099-11-23", "topics": ["bio-t"], "subjectName": "Bio", "title": "t", "kind": "test"}]})
        self.w("study/material-known.json", {"courses": {"1": sorted({material.item_key(it) for it in material.parse_index(course)})}})

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(material, k, v)
        self.tmp.cleanup()

    def w(self, rel: str, data):
        (self.root / rel).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_new_module_next_to_a_skipped_notice_is_unmapped(self):
        _, unmapped = material.collect()
        self.assertEqual([u["name"] for u in unmapped], ["Kartojimo lapas"])

    def test_module_posted_after_accept_is_unmapped_until_checked(self):
        """Reviewer 2026-09-10 (round 5): a module appended under an existing section or label must surface instead of silently
        inheriting that section's route; accept records it once its route has been checked."""
        p = self.root / "courses/1-bio/INDEX.md"
        p.write_text(p.read_text(encoding="utf-8") + "- **Naujas kartojimas** (resource) → files/naujas.pdf\n", encoding="utf-8")
        _, unmapped = material.collect()
        self.assertEqual(sorted(u["name"] for u in unmapped), ["Kartojimo lapas", "Naujas kartojimas"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            material.cmd_accept()
        _, unmapped = material.collect()
        self.assertEqual([u["name"] for u in unmapped], ["Kartojimo lapas"], "a module no rule covers must stay unmapped after accept")

    def test_skip_without_a_reason_is_not_accounted(self):
        """Reviewer 2026-09-10 (round 6): a skip or checked verdict must say what was inspected and why."""
        by_topic, _ = material.collect()
        meta = material.topic_meta()["bio-t"]
        key = "video:yt-bcdefghijkl"
        st = lambda: {r["key"]: r["status"] for r in material.account("bio-t", by_topic["bio-t"], meta)}[key]  # noqa: E731
        self.w("study/material/bio-t.json", {"items": {key: {"verdict": "skip"}}})
        self.assertEqual(st(), "UNACCOUNTED")
        self.w("study/material/bio-t.json", {"items": {key: {"verdict": "skip", "note": "course notice about the timetable, no content"}}})
        self.assertEqual(st(), "skip")

    def test_citation_alone_is_not_accounted(self):
        by_topic, _ = material.collect()
        meta = material.topic_meta()["bio-t"]
        status = lambda: {r["key"]: r["status"] for r in material.account("bio-t", by_topic["bio-t"], meta)}  # noqa: E731
        self.assertEqual(status(), {"file:virskinimas.pptx": "CITED", "video:yt-abcdefghijk": "CITED", "video:yt-bcdefghijkl": "UNACCOUNTED"})
        self.w("study/material/bio-t.json", {"items": {"video:yt-abcdefghijk": {"verdict": "used"}, "video:yt-bcdefghijkl": {"verdict": "missing"}}})
        st = status()
        self.assertEqual(st["video:yt-abcdefghijk"], "used")
        self.assertEqual(st["video:yt-bcdefghijkl"], "UNACCOUNTED", "a known gap must stay unaccounted until the page teaches it")

    def test_dead_video_without_a_replacement_stays_unresolved(self):
        """Reviewer 2026-09-10: 'unreachable, no replacement' must not vanish from the outstanding count."""
        by_topic, _ = material.collect()
        meta = material.topic_meta()["bio-t"]
        key = "video:yt-bcdefghijkl"
        self.w("study/material/bio-t.json", {"items": {key: {"verdict": "unreachable", "note": "video deleted"}}})
        self.assertEqual({r["key"]: r["status"] for r in material.account("bio-t", by_topic["bio-t"], meta)}[key], "UNREACHABLE")
        st = lambda: {r["key"]: r["status"] for r in material.account("bio-t", by_topic["bio-t"], meta)}[key]  # noqa: E731
        self.w("study/material/bio-t.json", {"items": {key: {"verdict": "unreachable", "replacement": "files/virskinimas.pptx slides 4-9"}}})
        self.assertEqual(st(), "UNREACHABLE", "free text is not a checked replacement (reviewer round 3)")
        self.w("study/material/bio-t.json", {"items": {key: {"verdict": "unreachable", "replacement": ["file:virskinimas.pptx"]}}})
        self.assertEqual(st(), "UNREACHABLE", "a replacement that is only cited, never verified, clears nothing")
        self.w("study/material/bio-t.json", {"items": {key: {"verdict": "unreachable", "replacement": ["file:virskinimas.pptx"]},
                                                       "file:virskinimas.pptx": {"verdict": "used"}}})
        self.assertEqual(st(), "unreachable")

    def test_broken_required_input_is_loud(self):
        """Reviewer 2026-09-10 (rounds 2-3): a malformed, deleted or structurally empty map or register must not turn into silence."""
        for rel, text in (("study/material-map.json", "{broken"), ("study/material-map.json", None),
                          ("study/material-map.json", "{}"), ("study/assessments.json", "{}"),
                          ("courses/1-bio/videos/index.json", None), ("study/material-known.json", None)):
            with self.subTest(file=rel, content=text):
                p = self.root / rel
                keep = p.read_text(encoding="utf-8")
                if text is None:
                    p.unlink()
                else:
                    p.write_text(text, encoding="utf-8")
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    material.cmd_hook()
                p.write_text(keep, encoding="utf-8")
                self.assertIn("MATERIAL INPUT BROKEN", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
