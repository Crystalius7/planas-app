"""Guard tests for the glance findings of 2026-09-12 - run: python product/tests/test_guards.py"""
from __future__ import annotations

import base64
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "engine"))
sys.path.insert(0, str(HERE.parent / "connector"))
from studycore import collect, notify  # noqa: E402
from studycore.workspace import Workspace  # noqa: E402
from server import DEFAULT_ORIGINS, origin_allowed  # noqa: E402


def test_origin_allowed():
    assert origin_allowed(None, DEFAULT_ORIGINS)                                  # a local non-browser client
    assert origin_allowed("http://127.0.0.1:8080", DEFAULT_ORIGINS)
    assert origin_allowed("http://localhost:5173", DEFAULT_ORIGINS)
    assert origin_allowed("https://crystalius7.github.io", DEFAULT_ORIGINS)
    assert origin_allowed("chrome-extension://abcdefghijklmnop", DEFAULT_ORIGINS)
    assert not origin_allowed("https://evil.example", DEFAULT_ORIGINS)
    assert not origin_allowed("https://crystalius7.github.io.evil.example", DEFAULT_ORIGINS)
    assert not origin_allowed("http://127.0.0.1.evil.example", DEFAULT_ORIGINS)
    assert origin_allowed("https://evil.example", ["*"])


def test_safe_names_and_within():
    assert collect.safe_name("../../etc/passwd") == "passwd"
    assert collect.safe_name("..\\..\\x.txt") == "x.txt"
    assert collect.safe_name("..") == "file"
    assert collect.safe_name("C:\\Windows\\win.ini") == "win.ini"
    assert collect.safe_name("a<b>:c|d?.pdf") == "abcd.pdf"
    assert collect.safe_id("29") == "29" and collect.safe_id("../3") == "0" and collect.safe_id(None) == "0"
    base = Path(tempfile.gettempdir()) / "planas-within"
    base.mkdir(exist_ok=True)
    assert collect.within(base, base / "a" / "b.txt")
    try:
        collect.within(base, base / ".." / "escape.txt")
        raise AssertionError("escape accepted")
    except ValueError:
        pass


def test_import_bundle_traversal():
    root = Path(tempfile.gettempdir()) / "planas-bundle-ws"
    shutil.rmtree(root, ignore_errors=True)
    ws = Workspace(root)
    bundle = {"site": "https://moodle.example", "userid": 5, "courses": [
        {"id": "../../7", "fullname": "bad id", "modules": []},
        {"id": 7, "fullname": "Physics", "sections": [{"title": "S1", "summary": ""}], "modules": [
            {"id": 11, "module": "resource", "name": "Slides", "section": "S1", "files": [{"name": "../../../../evil.txt", "b64": base64.b64encode(b"x").decode()}]},
            {"id": "12; rm", "module": "page", "name": "ignored", "section": "S1", "text": "t"},
        ]}]}
    res = collect.import_bundle(ws, bundle)
    assert len(res) == 1 and res[0]["id"] == 7
    written = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()]
    assert not (root.parent / "evil.txt").exists()
    assert any(p.endswith("evil.txt") for p in written) and all(p.startswith("courses") or p.startswith("study") or p.startswith("state") for p in written)
    assert len(res[0]["modules"]) == 1   # the module with a non-numeric id was dropped


def test_mark_read_items():
    root = Path(tempfile.gettempdir()) / "planas-notify-ws"
    shutil.rmtree(root, ignore_errors=True)
    ws = Workspace(root)
    log = {"items": [{"at": "t1", "kind": "file", "courseId": 7, "text": "a.pdf", "read": False}, {"at": "t1", "kind": "file", "courseId": 7, "text": "b.pdf", "read": False}]}
    (ws.state / "notifications.json").write_text(json.dumps(log), encoding="utf-8")
    notify.mark_read_items(ws, [("t1", "file", 7, "a.pdf")])
    left = notify.unread(ws)
    assert len(left) == 1 and left[0]["text"] == "b.pdf"


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
