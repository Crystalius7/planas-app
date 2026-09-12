"""server.py - the local connector: one small HTTP API on 127.0.0.1 that the web app and the browser extension talk to.

Everything stays on the student's machine (collab consensus 2026-09-12: connector-backed dashboard first; the cloud API in
api/ offers the same routes for the hosted tier). Standard library only, no third-party server.

    python product/connector/cli.py serve [--port 8765] [--workspace <dir>] [--origin https://<app origin>]

Routes (JSON):
  GET  /status                      what is connected, settings, last scan, unread count
  POST /connect                     {site, route: token|password|session, token?|username+password?|cookies?}
  POST /scan                        mirror every course, save deadlines, diff for notifications
  POST /bundle                      the extension's collected bundle (import + deadlines + diff)
  GET  /assessments                 upcoming + completed (done) with dates, confidence, topics
  POST /assessments                 {op: add|edit|done|undone|delete, id?, title?, subject?, date?, time?, kind?, topics?}
  GET  /material                    every digested material item with its verdict
  GET  /notifications  POST /notifications/read
  GET  /settings       POST /settings           (sliders, language, fact-check switch, consent, digest provider)
  GET  /estimate?minutes=&grade=    the slider readout
  POST /plan                        build the plan;  GET /plan  the plan JSON;  GET /hub  the daily hub page
  POST /digest {topic|course, sections?}   build/extend a topic from the mirrored material
  POST /material/add                fold unread new material into the topics it belongs to (smart add)
  POST /report {kind, text, page?}  bug / feature report - stored locally, forwarded only with consent
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "engine"))
from studycore import collect, digest, factcheck, notify, planner, render, subjects  # noqa: E402
from studycore.workspace import Workspace  # noqa: E402

VERSION = "0.1.0"
LOCK = threading.Lock()


class Connector:
    def __init__(self, root: Path):
        self.ws = Workspace(root)
        self.secret_p = self.ws.secrets / "moodle.json"

    # ---- moodle credentials (token or session cookies; never a password) -------------------------------------------
    def creds(self) -> dict:
        try:
            return json.loads(self.secret_p.read_text(encoding="utf-8")) if self.secret_p.exists() else {}
        except (ValueError, OSError):
            return {}

    def save_creds(self, d: dict):
        self.secret_p.write_text(json.dumps(d), encoding="utf-8")
        try:
            import os
            os.chmod(self.secret_p, 0o600)
        except OSError:
            pass

    def client(self):
        c = self.creds()
        if c.get("route") == "token":
            return collect.MoodleToken(c["site"], c["token"])
        if c.get("route") == "session":
            return collect.MoodleSession(c["site"], c.get("cookies", []))
        return None

    # ---- routes ---------------------------------------------------------------------------------------------------
    def status(self) -> dict:
        c = self.creds()
        st = self.ws.read("../state/scan.json") if (self.ws.state / "scan.json").exists() else {}
        return {"version": VERSION, "workspace": str(self.ws.root), "moodle": {"site": c.get("site"), "route": c.get("route"), "connected": bool(c)},
                "settings": self.ws.settings, "lastScan": st, "unread": len(notify.unread(self.ws)),
                "courses": [json.loads(m.read_text(encoding="utf-8")).get("fullname") for m in self.ws.courses.glob("*/manifest.json")]}

    def connect(self, body: dict) -> dict:
        site = (body.get("site") or "").strip().rstrip("/")
        if not re.match(r"^https://[^/\s]+", site):
            raise ValueError("site must be an https:// address")
        route = body.get("route")
        if route == "password":
            mt = collect.MoodleToken.from_password(site, body["username"], body["password"])   # password goes to the school only
            info = mt.site_info()
            self.save_creds({"site": site, "route": "token", "token": mt.token, "userid": info.get("userid"), "fullname": info.get("fullname"), "fp": collect.fingerprint(site, info.get("userid"))})
        elif route == "token":
            mt = collect.MoodleToken(site, body["token"])
            info = mt.site_info()
            self.save_creds({"site": site, "route": "token", "token": body["token"], "userid": info.get("userid"), "fullname": info.get("fullname"), "fp": collect.fingerprint(site, info.get("userid"))})
        elif route == "launch":
            # the extension observed the mobile launch redirect (<scheme>://token=<base64>); verify it was minted for this site
            tok = collect.decode_launch_token(body["launchUrl"], site, body.get("passport") or "")
            mt = collect.MoodleToken(site, tok["token"])
            info = mt.site_info()
            self.save_creds({"site": site, "route": "token", "token": tok["token"], "userid": info.get("userid"), "fullname": info.get("fullname"), "fp": collect.fingerprint(site, info.get("userid"))})
        elif route == "session":
            ms = collect.MoodleSession(site, body.get("cookies", []))
            p = ms.probe()
            if not p.get("loggedIn"):
                raise ValueError("the session is not logged in")
            self.save_creds({"site": site, "route": "session", "cookies": body.get("cookies", []), "userid": p.get("userid"), "fp": collect.fingerprint(site, p.get("userid") or 0)})
        else:
            raise ValueError("route must be token, password or session")
        return {"ok": True, "site": site, "route": self.creds()["route"], "probe": collect.public_config(site) if body.get("probe") else None}

    def scan(self) -> dict:
        cl = self.client()
        if cl is None:
            raise ValueError("not connected")
        courses = cl.courses()
        mirrored = []
        for c in courses:
            cid, name = int(c["id"]), c.get("fullname") or c.get("displayname") or str(c["id"])
            m = collect.mirror_token(self.ws, cl, cid, name) if isinstance(cl, collect.MoodleToken) else collect.mirror_session(self.ws, cl, cid, name)
            mirrored.append({"id": cid, "name": name, "modules": len(m.get("modules", [])), "shape": subjects.classify(name)})
        collect.save_deadlines(self.ws, cl.calendar(180))
        self._register_courses(mirrored)
        n = notify.watch(self.ws)
        st = {"at": n["at"], "courses": mirrored, "changes": len(n["changes"]), "baseline": n["baseline"]}
        (self.ws.state / "scan.json").write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
        return st

    def bundle(self, body: dict) -> dict:
        res = collect.import_bundle(self.ws, body)
        mirrored = [{"id": m["id"], "name": m["fullname"], "modules": len(m.get("modules", [])), "shape": subjects.classify(m["fullname"])} for m in res]
        self._register_courses(mirrored)
        if body.get("site") and body.get("userid") and not self.creds():
            self.save_creds({"site": body["site"], "route": "extension", "userid": body["userid"], "fp": collect.fingerprint(body["site"], body["userid"])})
        n = notify.watch(self.ws)
        st = {"at": n["at"], "courses": mirrored, "changes": len(n["changes"]), "baseline": n["baseline"], "via": "extension"}
        (self.ws.state / "scan.json").write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
        return st

    def _register_courses(self, mirrored: list[dict]):
        """Every course becomes a subject in topics.json (state not-built) so the material ledger and the digest know it."""
        t = self.ws.read("topics.json")
        subs = t.setdefault("subjects", {})
        for c in mirrored:
            key = collect.slug(c["name"])[:24] or str(c["id"])
            s = subs.setdefault(key, {"name": c["name"], "courseId": c["id"], "shape": c["shape"]["shape"], "family": c["shape"]["family"], "topics": []})
            s["courseId"], s["name"] = c["id"], c["name"]
        t["updated"] = time.strftime("%Y-%m-%d")
        self.ws.write("topics.json", t)

    def assessments(self) -> dict:
        reg = self.ws.read("assessments.json").get("assessments", [])
        return {"upcoming": [a for a in reg if not a.get("done")], "completed": [a for a in reg if a.get("done")]}

    def assessment_op(self, body: dict) -> dict:
        op = body.get("op")
        if op in ("done", "undone"):
            return planner.mark_done(self.ws, body["id"], op == "done")
        reg = self.ws.read("assessments.json")
        items = reg.setdefault("assessments", [])
        if op == "delete":
            reg["assessments"] = [a for a in items if a.get("id") != body["id"]]
            self.ws.write("assessments.json", reg)
            return {"ok": True}
        if op == "add":
            aid = body.get("id") or f"{collect.slug(body.get('subject') or 'x')}-{int(time.time())}"
            a = {"id": aid, "subject": body.get("subject"), "subjectName": body.get("subjectName") or body.get("subject"), "title": body.get("title") or "Test",
                 "kind": body.get("kind") or "test", "date": body["date"], "time": body.get("time"), "confidence": "confirmed",
                 "source": f"added by the student on {time.strftime('%Y-%m-%d')}", "topics": body.get("topics") or []}
            items.append(a)
            self.ws.write("assessments.json", reg)
            return a
        if op == "edit":
            a = planner.set_date(self.ws, body["id"], body["date"], body.get("time")) if body.get("date") else None
            reg = self.ws.read("assessments.json")
            for x in reg["assessments"]:
                if x["id"] == body["id"]:
                    for k in ("title", "kind", "topics", "subject"):
                        if body.get(k) is not None:
                            x[k] = body[k]
                    a = x
            self.ws.write("assessments.json", reg)
            return a or {}
        raise ValueError("op must be add|edit|done|undone|delete")

    def estimate(self, q: dict) -> dict:
        m = q.get("minutes")
        return planner.estimate(self.ws, minutes=int(m[0]) if m else None, target_grade=(q.get("grade") or [None])[0])

    def plan(self) -> dict:
        p = planner.build(self.ws)
        return {"ok": True, "days": len(p["days"]), "sliders": p["sliders"], "assessments": [{"id": a["id"], "coverage": a.get("coverage")} for a in p["assessments"]]}

    def hub(self) -> str:
        mods = self.ws.bind()
        plan_mod = mods["plan"]
        page = plan_mod.cmd_page() if hasattr(plan_mod, "cmd_page") else None
        p = Path(page) if page else plan_mod.PAGE
        html = p.read_text(encoding="utf-8")
        lang = self.ws.settings.get("uiLang") or "en"
        html = render.apply_chrome(html, lang)
        # the personal hub re-reads deadlines from the owner's Google Drive; the product hub gets them from the connector
        return html.replace("title = 'planas-live.json' and parentId = '1b7oghPlrWbQpZNVOKG35kUCzb-pUw2E1'", "title = 'planas-live.json' and parentId = 'connector'")

    def digest_topic(self, body: dict) -> dict:
        t = self.ws.read("topics.json")
        sid, subj = None, None
        for k, s in t.get("subjects", {}).items():
            if str(s.get("courseId")) == str(body.get("course")) or k == body.get("subject"):
                sid, subj = k, s
        if subj is None:
            raise ValueError("unknown course/subject")
        cdir = next(iter(self.ws.courses.glob(f"{subj['courseId']}-*")), None)
        if cdir is None:
            raise ValueError("course not mirrored yet - scan first")
        tid = body.get("topic") or f"{sid}-{collect.slug(body.get('title') or 'topic')}"
        title = body.get("title") or (body.get("sections") or ["Topic"])[0]
        content = digest.Digest(self.ws).run(tid, sid, title, subj["name"], cdir, body.get("sections"), lang=self.ws.settings.get("contentLang"))
        content = factcheck.apply(self.ws, content)
        d = self.ws.study / sid
        d.mkdir(exist_ok=True)
        cp = d / f"{collect.slug(title)}.json"
        cp.write_text(json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8")
        ledger = {"topic": tid, "items": [{"id": s.get("name"), "name": s.get("name"), "verdict": "used" if s.get("used") else "checked", "note": s.get("note", "")} for s in content.get("sources", [])]}
        (self.ws.study / "material" / f"{tid}.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding="utf-8")
        topics = subj.setdefault("topics", [])
        if not any(x.get("id") == tid for x in topics):
            topics.append({"id": tid, "title": title, "state": "built", "sections": body.get("sections") or [], "page": str(cp.with_suffix('.html'))})
        self.ws.write("topics.json", t)
        built = render.build_topic(self.ws, cp)
        return {"topic": tid, "content": str(cp), "baseline": content.get("baseline", False), "built": built}

    def material_add(self) -> dict:
        routed = notify.new_material_for_topics(self.ws)
        done = []
        for r in [x for x in routed if x["routed"]]:
            done.append(self.digest_topic({"course": r["courseId"], "topic": r["topic"], "title": r["topic"], "sections": [r["section"]]}))
        notify.mark_read(self.ws)
        return {"routed": len(done), "unrouted": [x for x in routed if not x["routed"]]}

    def report(self, body: dict) -> dict:
        p = self.ws.state / "reports.json"
        log = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"items": []}
        rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": body.get("kind", "bug"), "text": (body.get("text") or "")[:4000], "page": body.get("page"), "forwarded": False}
        log["items"].append(rec)
        p.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
        return {"ok": True, "stored": str(p), "forwardedWithConsent": bool(self.ws.settings.get("shareData"))}


def make_handler(cx: Connector, origin: str):
    class H(BaseHTTPRequestHandler):
        def _send(self, code: int, body, ctype="application/json"):
            data = body.encode("utf-8") if isinstance(body, str) else json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Vary", "Origin")
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self._send(204, "")

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 200_000_000:
                raise ValueError("body too large")
            raw = self.rfile.read(n) if n else b"{}"
            return json.loads(raw.decode("utf-8") or "{}")

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            try:
                with LOCK:
                    if u.path == "/status":
                        return self._send(200, cx.status())
                    if u.path == "/assessments":
                        return self._send(200, cx.assessments())
                    if u.path == "/material":
                        return self._send(200, {"items": render.digested_material(cx.ws)})
                    if u.path == "/notifications":
                        return self._send(200, {"items": notify.unread(cx.ws)})
                    if u.path == "/settings":
                        return self._send(200, cx.ws.settings)
                    if u.path == "/estimate":
                        return self._send(200, cx.estimate(q))
                    if u.path == "/plan":
                        return self._send(200, cx.ws.read("plan.json"))
                    if u.path == "/hub":
                        return self._send(200, cx.hub(), "text/html")
                    if u.path == "/corrections":
                        return self._send(200, {"items": factcheck.corrections(cx.ws)})
                return self._send(404, {"error": "no such route"})
            except Exception as e:  # noqa: BLE001
                return self._send(400, {"error": f"{type(e).__name__}: {e}"})

        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            try:
                body = self._body()
                with LOCK:
                    if u.path == "/connect":
                        return self._send(200, cx.connect(body))
                    if u.path == "/scan":
                        return self._send(200, cx.scan())
                    if u.path == "/bundle":
                        return self._send(200, cx.bundle(body))
                    if u.path == "/assessments":
                        return self._send(200, cx.assessment_op(body))
                    if u.path == "/notifications/read":
                        notify.mark_read(cx.ws, body.get("before"))
                        return self._send(200, {"ok": True})
                    if u.path == "/settings":
                        return self._send(200, cx.ws.update_settings(**{k: v for k, v in body.items() if not k.startswith("_")}))
                    if u.path == "/plan":
                        return self._send(200, cx.plan())
                    if u.path == "/digest":
                        return self._send(200, cx.digest_topic(body))
                    if u.path == "/material/add":
                        return self._send(200, cx.material_add())
                    if u.path == "/report":
                        return self._send(200, cx.report(body))
                return self._send(404, {"error": "no such route"})
            except Exception as e:  # noqa: BLE001
                return self._send(400, {"error": f"{type(e).__name__}: {e}"})

        def log_message(self, fmt, *args):   # never log bodies; one line per request
            sys.stderr.write("%s %s\n" % (self.command, self.path.split("?")[0]))

    return H


def serve(root: Path, port: int = 8765, origin: str = "*"):
    cx = Connector(root)
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(cx, origin))
    print(f"connector {VERSION} on http://127.0.0.1:{port}  workspace={root}  origin={origin}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
