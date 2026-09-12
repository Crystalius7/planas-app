"""collect.py - Moodle collectors that never see the student's password.

Route A  MoodleToken   - the site's own mobile web service (REST, form-encoded, CORS-open per MDL-47545). The token is
                         minted by Moodle itself: /login/token.php on username/password sites (the connector posts the
                         password straight to the SCHOOL and keeps only the token), or the mobile launch flow on SSO sites
                         (the student logs in in a window we open; the site redirects to moodlemobile://token=<base64>,
                         which the desktop connector or the extension reads). Only the token is stored, encrypted.
Route B  MoodleSession - a logged-in browser session (cookies + sesskey) for sites with the mobile service OFF, like the
                         owner's school (measured 2026-09-08). Uses lib/ajax/service.php for the ajax-enabled functions
                         and plain HTML pages for course contents - the same calls tools/moodle.py proved at the school.
                         Runs inside the student's browser (extension) or a local connector; never on our servers.
Bundle   import_bundle  - the extension collects with Route B in the browser and hands the connector one JSON bundle.

All three normalise to the personal mirror layout: courses/<id>-<slug>/{INDEX.md, manifest.json, pages/*.md, files/}.
"""
from __future__ import annotations

import base64
import hashlib
import html as htmlmod
import json
import re
import time
from pathlib import Path
from typing import Any

import requests

try:  # many school sites serve an incomplete TLS chain; the OS trust store resolves it (like Chrome), certifi does not
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

from .workspace import Workspace

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StudyProduct/0.1"
TEXT_MODS = ("page", "assign", "quiz", "forum", "lesson", "h5pactivity", "book", "glossary", "wiki", "label", "choice", "feedback")


# ----------------------------------------------------------------------------------------------- helpers
def slug(t: str) -> str:
    t = re.sub(r"[^\w\s-]", "", (t or "").lower(), flags=re.UNICODE)
    return re.sub(r"[\s_-]+", "-", t).strip("-")[:60] or "x"


def safe_name(name: str | None, fallback: str = "file") -> str:
    """A file name from Moodle, a header or an extension bundle becomes ONE path component: no directories, no dot-dot,
    no drive letters, no control characters (glance 2026-09-12, P1: an imported name could escape the workspace)."""
    n = (name or "").replace("\\", "/").split("/")[-1]
    n = re.sub(r"[\x00-\x1f<>:\"|?*]", "", n).strip(" .")
    if n in ("", ".", ".."):
        return fallback
    return n[:150]


def safe_id(value, fallback: str = "0") -> str:
    """Course/module ids from a client become digits only."""
    s = str(value if value is not None else "")
    return s if re.fullmatch(r"\d{1,12}", s) else fallback


def within(base: Path, target: Path) -> Path:
    """Resolve `target` and refuse anything outside `base`."""
    b, t = base.resolve(), target.resolve()
    if b != t and b not in t.parents:
        raise ValueError(f"path escapes its folder: {target}")
    return t


def strip_tags(h: str) -> str:
    h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", h or "")
    h = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>|</tr>", "\n", h)
    return re.sub(r"\n{3,}", "\n\n", htmlmod.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def fingerprint(site: str, userid: int | str) -> str:
    """ONE trial-abuse signal among several (partner IMPROVE 4: client-reported ids are unverified; Route A ids are
    verified server-side through core_webservice_get_site_info). Never reversible, never stored with the site name."""
    return hashlib.sha256(f"{site.rstrip('/').lower()}|{userid}".encode()).hexdigest()


def public_config(site: str) -> dict:
    """tool_mobile_get_public_config needs no token: tells whether Route A is possible and how the site logs in."""
    r = requests.post(f"{site.rstrip('/')}/lib/ajax/service-nologin.php?info=tool_mobile_get_public_config",
                      data=json.dumps([{"index": 0, "methodname": "tool_mobile_get_public_config", "args": {}}]),
                      headers={"Content-Type": "application/json", "User-Agent": UA}, timeout=30)
    j = r.json()[0]
    if j.get("error"):
        return {"available": False, "error": j.get("exception", {}).get("message", "error")}
    d = j["data"]
    return {"available": True, "enablemobilewebservice": bool(d.get("enablemobilewebservice")), "typeoflogin": d.get("typeoflogin"),
            "launchurl": d.get("launchurl"), "identityproviders": d.get("identityproviders", []), "sitename": d.get("sitename"),
            "lang": d.get("lang"), "mfa": bool(d.get("tool_mfa_enabled"))}


def decode_launch_token(url: str, site: str, passport: str) -> dict:
    """The mobile launch flow's redirect: <scheme>://token=<base64(md5(wwwroot+passport):::token[:::privatetoken])>."""
    m = re.search(r"token=([A-Za-z0-9+/=]+)", url)
    if not m:
        raise ValueError("no token in launch redirect")
    parts = base64.b64decode(m.group(1)).decode().split(":::")
    if len(parts) < 2:
        raise ValueError("malformed launch token")
    expect = hashlib.md5((site.rstrip("/") + passport).encode()).hexdigest()
    if parts[0] != expect:
        raise ValueError("launch token was not minted for this site + passport")
    return {"token": parts[1], "privatetoken": parts[2] if len(parts) > 2 else None}


# ----------------------------------------------------------------------------------------------- Route A: token
class MoodleToken:
    def __init__(self, site: str, token: str):
        self.site, self.token = site.rstrip("/"), token
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA

    @classmethod
    def from_password(cls, site: str, username: str, password: str) -> "MoodleToken":
        """The password goes to the SCHOOL only (login/token.php, POST) and is discarded; only the token is kept."""
        r = requests.post(f"{site.rstrip('/')}/login/token.php", data={"username": username, "password": password, "service": "moodle_mobile_app"},
                          headers={"User-Agent": UA}, timeout=30)
        j = r.json()
        if "token" not in j:
            raise RuntimeError(j.get("error") or j.get("errorcode") or "token refused")
        return cls(site, j["token"])

    def call(self, function: str, **args: Any) -> Any:
        data = {"wstoken": self.token, "wsfunction": function, "moodlewsrestformat": "json"}
        data.update(_flatten(args))
        r = self.s.post(f"{self.site}/webservice/rest/server.php", data=data, timeout=60)
        j = r.json()
        if isinstance(j, dict) and j.get("exception"):
            raise RuntimeError(f"{function}: {j.get('message')}")
        return j

    def site_info(self) -> dict:
        return self.call("core_webservice_get_site_info")

    def courses(self) -> list[dict]:
        info = self.site_info()
        return self.call("core_enrol_get_users_courses", userid=info["userid"])

    def contents(self, courseid: int) -> list[dict]:
        return self.call("core_course_get_contents", courseid=courseid)

    def calendar(self, days: int = 180) -> list[dict]:
        now = int(time.time())
        out, after = [], None
        for _ in range(20):
            args = {"timesortfrom": now - 86400, "timesortto": now + days * 86400, "limitnum": 50}
            if after:
                args["aftereventid"] = after
            page = self.call("core_calendar_get_action_events_by_timesort", **args).get("events", [])
            out += page
            if len(page) < 50:
                break
            after = page[-1]["id"]
        return out

    def notifications(self, userid: int) -> list[dict]:
        return self.call("message_popup_get_popup_notifications", useridto=userid, limit=50, offset=0).get("notifications", [])

    def download(self, fileurl: str, dest: Path) -> Path | None:
        sep = "&" if "?" in fileurl else "?"
        r = self.s.get(f"{fileurl}{sep}token={self.token}", timeout=120, stream=True)
        if r.status_code != 200:
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(65536):
                f.write(chunk)
        return dest


def _flatten(args: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in args.items():
        key = f"{prefix}[{k}]" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        elif isinstance(v, list):
            for i, x in enumerate(v):
                out.update(_flatten({str(i): x}, key) if not isinstance(x, (dict, list)) else _flatten(x, f"{key}[{i}]"))
        else:
            out[key] = v
    return out


# ----------------------------------------------------------------------------------------------- Route B: session
class MoodleSession:
    """A logged-in browser session (cookie jar exported by the extension or a local browser profile)."""

    def __init__(self, site: str, cookies: list[dict]):
        self.site = site.rstrip("/")
        host = re.sub(r"^https?://", "", self.site).split("/")[0]
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        for c in cookies:
            if host.endswith(c.get("domain", "").lstrip(".")):
                self.s.cookies.set(c["name"], c["value"], domain=c["domain"].lstrip("."), path=c.get("path", "/"))
        self._sk: str | None = None
        self._uid: int | None = None

    def probe(self) -> dict:
        r = self.s.get(self.site + "/my/", timeout=30)
        sk = re.search(r'"sesskey":"([^"]+)"', r.text)
        uid = re.search(r'"userId":(\d+)', r.text)
        self._sk, self._uid = (sk.group(1) if sk else None), (int(uid.group(1)) if uid else None)
        return {"loggedIn": bool(sk), "userid": self._uid}

    @property
    def sesskey(self) -> str:
        if not self._sk:
            self.probe()
        if not self._sk:
            raise RuntimeError("not logged in (no sesskey)")
        return self._sk

    def ajax(self, method: str, args: dict) -> Any:
        r = self.s.post(f"{self.site}/lib/ajax/service.php?sesskey={self.sesskey}&info={method}",
                        data=json.dumps([{"index": 0, "methodname": method, "args": args}]),
                        headers={"Content-Type": "application/json"}, timeout=60)
        j = r.json()[0]
        if j.get("error"):
            raise RuntimeError(f"{method}: {j.get('exception', {}).get('message', j)}")
        return j["data"]

    def courses(self) -> list[dict]:
        return self.ajax("core_course_get_enrolled_courses_by_timeline_classification",
                         {"offset": 0, "limit": 0, "classification": "all", "sort": "fullname"}).get("courses", [])

    def calendar(self, days: int = 180) -> list[dict]:
        now = int(time.time())
        out, after = [], None
        for _ in range(20):
            args = {"timesortfrom": now - 86400, "timesortto": now + days * 86400, "limitnum": 50}
            if after:
                args["aftereventid"] = after
            page = self.ajax("core_calendar_get_action_events_by_timesort", args).get("events", [])
            out += page
            if len(page) < 50:
                break
            after = page[-1]["id"]
        return out

    def notifications(self) -> list[dict]:
        uid = self._uid or self.probe().get("userid") or 0
        return self.ajax("message_popup_get_popup_notifications", {"useridto": uid, "limit": 50, "offset": 0}).get("notifications", [])

    def course_state(self, cid: int) -> dict | None:
        try:
            return json.loads(self.ajax("core_courseformat_get_state", {"courseid": cid}))
        except Exception:  # noqa: BLE001 - Moodle < 4.0 has no format state; the HTML fallback takes over
            return None

    def get(self, url: str, **kw) -> requests.Response:
        return self.s.get(url, timeout=kw.pop("timeout", 60), **kw)

    def download(self, url: str, dest_dir: Path, hint: str = "") -> Path | None:
        r = self.s.get(url, timeout=120, stream=True, allow_redirects=True)
        if r.status_code != 200 or "text/html" in r.headers.get("Content-Type", ""):
            return None
        name = None
        cd = r.headers.get("Content-Disposition", "")
        m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd)
        if m:
            name = requests.utils.unquote(m.group(1))
        name = safe_name(name or Path(requests.utils.urlparse(r.url).path).name, slug(hint) + ".bin")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = within(dest_dir, dest_dir / name)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(65536):
                f.write(chunk)
        return dest


# ----------------------------------------------------------------------------------------------- mirror (either route)
def mirror_session(ws: Workspace, ms: MoodleSession, cid: int, fullname: str) -> dict:
    """Route B mirror - the personal mirror_course() made site-agnostic (host from the session, not hard-coded)."""
    site = ms.site
    host = re.escape(re.sub(r"^https?://", "", site).split("/")[0])
    cdir = ws.courses / f"{cid}-{slug(fullname)}"
    r0 = ms.get(f"{site}/course/view.php?id={cid}")
    if "enrol/index.php" in r0.url:
        return {"id": cid, "enrolled": False}
    h = r0.text
    cdir.mkdir(parents=True, exist_ok=True)
    sections, cms = [], {}
    state = ms.course_state(cid)
    if state:
        cms = {str(c["id"]): c for c in state.get("cm", [])}
        for sec in state.get("section", []):
            sections.append({"title": sec.get("title") or f"Section {sec.get('number')}", "number": sec.get("number"),
                             "summary": strip_tags(sec.get("summary", "") or ""), "cmlist": [str(x) for x in sec.get("cmlist", [])]})
    else:
        for m in re.finditer(r'(?is)<li[^>]+id="section-(\d+)"[^>]*>(.*?)(?=<li[^>]+id="section-\d+"|</ul>\s*</div>\s*</div>\s*$)', h):
            body = m.group(2)
            t = re.search(r'(?is)<h3[^>]*class="[^"]*sectionname[^"]*"[^>]*>(.*?)</h3>', body)
            ids = re.findall(r'id="module-(\d+)"', body)
            sections.append({"title": strip_tags(t.group(1)) if t else f"Section {m.group(1)}", "number": int(m.group(1)), "summary": "", "cmlist": ids})
            for i in ids:
                mm = re.search(rf'(?is)<li[^>]+id="module-{i}"[^>]*class="[^"]*modtype_(\w+)[^"]*"(.*?)</li>', body)
                nm = re.search(r'(?is)<span class="instancename">(.*?)</span>', mm.group(2)) if mm else None
                cms[i] = {"id": int(i), "module": mm.group(1) if mm else "?", "name": strip_tags(nm.group(1)).strip() if nm else f"module {i}",
                          "url": f"{site}/mod/{mm.group(1) if mm else 'x'}/view.php?id={i}"}
    html_summaries = {}
    for m in re.finditer(r'(?is)<li[^>]+id="section-(\d+)"[^>]*data-sectionname="([^"]*)"(.*?)(?=<li[^>]+id="section-\d+"|$)', h):
        b = re.search(r'(?is)class="[^"]*summarytext[^"]*"[^>]*>(.*?)</div>\s*</div>', m.group(3))
        if b and strip_tags(b.group(1)).strip():
            html_summaries[int(m.group(1))] = strip_tags(b.group(1))
    for sec in sections:
        if not sec.get("summary") and sec.get("number") in html_summaries:
            sec["summary"] = html_summaries[sec["number"]]
    modules = []
    for sec in sections:
        for i in sec["cmlist"]:
            cm = cms.get(i)
            if not cm:
                continue
            mod, name = cm.get("module", "?"), cm.get("name", "")
            url = cm.get("url") or f"{site}/mod/{mod}/view.php?id={i}"
            entry = {"id": int(i), "module": mod, "name": name, "url": url, "section": sec["title"], "files": [], "text": None}
            try:
                if mod == "label":
                    pass
                elif mod in ("resource", "file"):
                    p = ms.download(f"{site}/mod/resource/view.php?id={i}&redirect=1", cdir / "files", name)
                    if p:
                        entry["files"].append(p.name)
                elif mod == "folder":
                    fh = ms.get(f"{site}/mod/folder/view.php?id={i}").text
                    for fu in dict.fromkeys(re.findall(rf'href="(https://{host}/pluginfile\.php/\d+/mod_folder/[^"]+)"', fh)):
                        p = ms.download(htmlmod.unescape(fu), cdir / "files" / slug(name))
                        if p:
                            entry["files"].append(f"{slug(name)}/{p.name}")
                elif mod == "url":
                    uh = ms.get(f"{site}/mod/url/view.php?id={i}", allow_redirects=False)
                    ext = uh.headers.get("Location") or (re.search(r'class="urlworkaround">.*?href="([^"]+)"', uh.text, re.S) or [None, None])[1]
                    if not ext:
                        m2 = re.search(rf'href="(https?://(?!{host})[^"]+)"', uh.text)
                        ext = m2.group(1) if m2 else "?"
                    entry["external"] = htmlmod.unescape(ext)
                else:
                    ph = ms.get(url).text
                    txt = strip_tags(_main_region(ph))
                    tp = cdir / "pages" / f"{i}-{slug(name)}.md"
                    tp.parent.mkdir(exist_ok=True)
                    tp.write_text(f"# {name} ({mod})\n{url}\n\n{txt}", encoding="utf-8")
                    entry["text"] = tp.name
                    for fu in dict.fromkeys(re.findall(rf'href="(https://{host}/pluginfile\.php/\d+/mod_[^"]+)"', _main_region(ph))):
                        p = ms.download(htmlmod.unescape(fu), cdir / "files" / slug(name))
                        if p:
                            entry["files"].append(f"{slug(name)}/{p.name}")
            except Exception as e:  # noqa: BLE001 - one broken module never stops the mirror; it is listed as broken
                entry["error"] = f"{type(e).__name__}: {e}"
            modules.append(entry)
    return _write_mirror(ws, cdir, cid, fullname, sections, modules)


def mirror_token(ws: Workspace, mt: MoodleToken, cid: int, fullname: str) -> dict:
    """Route A mirror from core_course_get_contents (files carry their download URLs; text modules carry descriptions)."""
    cdir = ws.courses / f"{cid}-{slug(fullname)}"
    cdir.mkdir(parents=True, exist_ok=True)
    sections, modules = [], []
    for sec in mt.contents(cid):
        s = {"title": sec.get("name") or f"Section {sec.get('section')}", "number": sec.get("section"),
             "summary": strip_tags(sec.get("summary") or ""), "cmlist": [str(m["id"]) for m in sec.get("modules", [])]}
        sections.append(s)
        for m in sec.get("modules", []):
            entry = {"id": m["id"], "module": m.get("modname"), "name": m.get("name", ""), "url": m.get("url"), "section": s["title"], "files": [], "text": None}
            desc = strip_tags(m.get("description") or "")
            for c in m.get("contents", []) or []:
                if c.get("type") == "file" and c.get("fileurl"):
                    p = mt.download(c["fileurl"], within(cdir, cdir / "files" / slug(m.get("name", "")) / safe_name(c.get("filename"))))
                    if p:
                        entry["files"].append(f"{slug(m.get('name', ''))}/{p.name}")
                elif c.get("type") == "url":
                    entry["external"] = c.get("fileurl")
            if desc or m.get("modname") in TEXT_MODS:
                tp = cdir / "pages" / f"{m['id']}-{slug(m.get('name', ''))}.md"
                tp.parent.mkdir(exist_ok=True)
                tp.write_text(f"# {m.get('name', '')} ({m.get('modname')})\n{m.get('url') or ''}\n\n{desc}", encoding="utf-8")
                entry["text"] = tp.name
            modules.append(entry)
    return _write_mirror(ws, cdir, cid, fullname, sections, modules)


def import_bundle(ws: Workspace, bundle: dict) -> list[dict]:
    """The extension's bundle: {site, userid, courses: [{id, fullname, sections: [...], modules: [{id, module, name, url,
    section, text?, files: [{name, b64?}], external?}], calendar: [...], notifications: [...]}. Files arrive base64 (small)
    or are fetched later by the connector through the session the extension exported."""
    out = []
    for c in bundle.get("courses", []):
        cid = safe_id(c.get("id"))
        if cid == "0":
            continue   # a course without a numeric id is not a Moodle course
        cdir = within(ws.courses, ws.courses / f"{cid}-{slug(c.get('fullname', ''))}")
        cdir.mkdir(parents=True, exist_ok=True)
        modules = []
        for m in c.get("modules", []):
            mid = safe_id(m.get("id"))
            if mid == "0":
                continue
            mslug = slug(m.get("name", ""))
            entry = {"id": int(mid), "module": re.sub(r"[^a-z0-9_]", "", str(m.get("module") or "")), "name": str(m.get("name", ""))[:300], "url": m.get("url"), "section": str(m.get("section", ""))[:300], "files": [], "text": None}
            if m.get("text"):
                tp = within(cdir, cdir / "pages" / f"{mid}-{mslug}.md")
                tp.parent.mkdir(exist_ok=True)
                tp.write_text(f"# {entry['name']} ({entry['module']})\n{m.get('url') or ''}\n\n{str(m['text'])[:400000]}", encoding="utf-8")
                entry["text"] = tp.name
            for f in m.get("files", []) or []:
                if f.get("b64"):
                    p = within(cdir, cdir / "files" / mslug / safe_name(f.get("name")))
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(base64.b64decode(f["b64"]))
                    entry["files"].append(f"{mslug}/{p.name}")
                elif f.get("url"):
                    entry.setdefault("pending", []).append(str(f["url"])[:2000])
            if m.get("external"):
                entry["external"] = str(m["external"])[:2000]
            modules.append(entry)
        out.append(_write_mirror(ws, cdir, int(cid), str(c.get("fullname", ""))[:300], c.get("sections", []), modules))
    if bundle.get("calendar") is not None:
        save_deadlines(ws, bundle["calendar"])
    return out


def save_deadlines(ws: Workspace, events: list[dict]) -> str:
    """Moodle's calendar action events -> study/deadlines.json (the day tabs show them with clock times)."""
    rows = []
    for e in events:
        ts = e.get("timesort") or e.get("timestart")
        if not ts:
            continue
        rows.append({"id": e.get("id"), "when": time.strftime("%Y-%m-%dT%H:%M", time.localtime(ts)), "title": e.get("name"),
                     "course": (e.get("course") or {}).get("fullname"), "courseId": (e.get("course") or {}).get("id"),
                     "module": e.get("modulename"), "cmid": (e.get("instance") if e.get("modulename") else None), "url": e.get("url"),
                     "action": (e.get("action") or {}).get("name")})
    rows.sort(key=lambda r: r["when"])
    ws.write("deadlines.json", {"deadlines": rows, "checkedAt": time.strftime("%Y-%m-%dT%H:%M:%S")})
    return f"{len(rows)} deadlines"


def _main_region(h: str) -> str:
    m = re.search(r'(?is)<div[^>]+role="main"[^>]*>(.*?)<footer', h)
    return m.group(1) if m else h


def _write_mirror(ws: Workspace, cdir: Path, cid: int, fullname: str, sections: list[dict], modules: list[dict]) -> dict:
    index = [f"# {fullname}", f"course id {cid} · mirrored {time.strftime('%Y-%m-%d %H:%M')}", ""]
    by_sec: dict[str, list[dict]] = {}
    for m in modules:
        by_sec.setdefault(m.get("section", ""), []).append(m)
    for sec in sections:
        index.append(f"## {sec['title']}")
        if sec.get("summary"):
            index.append(sec["summary"])
        for m in by_sec.get(sec["title"], []):
            line = f"- **{m['name']}** ({m['module']})"
            if m.get("files"):
                line += " → " + ", ".join(f"files/{f}" for f in m["files"])
            elif m.get("text"):
                line += f" → pages/{m['text']}"
            elif m.get("external"):
                line += f" → {m['external']}"
            if m.get("error"):
                line += f"  !! {m['error']}"
            index.append(line)
        index.append("")
    (cdir / "INDEX.md").write_text("\n".join(index), encoding="utf-8")
    manifest = {"id": cid, "fullname": fullname, "mirroredAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "sections": sections, "modules": modules}
    (cdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest
