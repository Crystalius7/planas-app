#!/usr/bin/env python
"""cli.py - the local connector command line (Route C: everything on the student's own machine).

    python product/connector/cli.py serve   [--port 8765] [--workspace DIR] [--origin ORIGIN]
    python product/connector/cli.py probe   <https://moodle.site>        # can Route A (token) work here? how does it log in?
    python product/connector/cli.py connect <site> --route password|token|session [...]
    python product/connector/cli.py scan    [--workspace DIR]             # mirror courses, deadlines, notifications diff
    python product/connector/cli.py plan    [--workspace DIR]             # build the plan at the sliders
    python product/connector/cli.py estimate --minutes N [--grade G]
    python product/connector/cli.py digest  --course ID --title T [--sections "A,B"]
    python product/connector/cli.py status

Workspace default: %LOCALAPPDATA%/StudyProduct/workspace (Windows) or ~/.studyproduct/workspace.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "engine"))

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]


def default_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.studyproduct")
    return Path(base) / "StudyProduct" / "workspace"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="connector")
    ap.add_argument("cmd", choices=["serve", "probe", "connect", "scan", "plan", "estimate", "digest", "status"])
    ap.add_argument("site", nargs="?")
    ap.add_argument("--workspace", default=str(default_root()))
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--origin", default="app", help="allowed browser origins, comma-separated; 'app' = the demo site, localhost and the extension schemes; '*' only for local experiments")
    ap.add_argument("--route", choices=["password", "token", "session"])
    ap.add_argument("--username")
    ap.add_argument("--token")
    ap.add_argument("--cookies", help="path to a JSON cookie export")
    ap.add_argument("--minutes", type=int)
    ap.add_argument("--grade")
    ap.add_argument("--course")
    ap.add_argument("--title")
    ap.add_argument("--sections")
    a = ap.parse_args(argv)
    root = Path(a.workspace)
    from server import Connector, serve
    from studycore import collect
    if a.cmd == "serve":
        serve(root, a.port, a.origin)
        return 0
    cx = Connector(root)
    if a.cmd == "probe":
        print(json.dumps(collect.public_config(a.site), ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "connect":
        body = {"site": a.site, "route": a.route}
        if a.route == "password":
            import getpass
            body["username"] = a.username or input("username: ")
            body["password"] = getpass.getpass("password (sent to the school only, never stored): ")
        elif a.route == "token":
            body["token"] = a.token
        elif a.route == "session":
            body["cookies"] = json.loads(Path(a.cookies).read_text(encoding="utf-8"))
        r = cx.connect(body)
        print(json.dumps({k: v for k, v in r.items() if k != "token"}, ensure_ascii=False))
        return 0
    if a.cmd == "scan":
        print(json.dumps(cx.scan(), ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "plan":
        print(json.dumps(cx.plan(), ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "estimate":
        q = {}
        if a.minutes is not None:
            q["minutes"] = [str(a.minutes)]
        if a.grade:
            q["grade"] = [a.grade]
        print(json.dumps(cx.estimate(q), ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "digest":
        print(json.dumps(cx.digest_topic({"course": a.course, "title": a.title, "sections": [s.strip() for s in (a.sections or "").split(",") if s.strip()] or None}), ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "status":
        print(json.dumps(cx.status(), ensure_ascii=False, indent=1))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
