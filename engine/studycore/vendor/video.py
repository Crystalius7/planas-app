#!/usr/bin/env python
"""video.py - turn the teachers' VIDEO LESSONS into text and pictures the study system can use.

WHY. Owner 2026-09-09: "if there're videos we must watch, find a way to transcribe them and scan frames
for the info presented visually too, so you can add it to our efficient learning system, you also must
discern from those videos what's most likely to be in the tests and exams."  Several topics (Lithuanian
~40 videopamokos on Loom/YouTube, maths ~15 YouTube lessons) exist ONLY as video, so they are invisible
to the study pages today.  This tool mirrors them as TEXT + SLIDE FRAMES beside the course.

    python tools/video.py list [<course-dir>] [--probe]        # inventory -> videos/index.json
    python tools/video.py fetch <id|url> [--frames N]          # one video -> videos/<id>.md + frames
    python tools/video.py scan <course-dir> [--limit N]        # everything not yet fetched, resumable
    python tools/video.py transcribe <course> [--section "Topic 8"] [--model small]
    python tools/video.py status [<course-dir>]                # what is transcribed / frames-only / failed

ZERO SPEND, free routes only: yt-dlp subtitles/auto-captions, Loom's own public transcript record,
ffmpeg keyframe scene detection.  No paid API, no key.  A video with no free transcript route is marked
"needs-audio" in index.json and stays visible there until something (a local model, a teacher enabling
captions) fixes it - it is never silently dropped.

Artefacts NEVER go into the mirrored files/ tree; they live in courses/<id>-<slug>/videos/.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
if sys.stderr:
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

ROOT = Path(__file__).resolve().parent.parent
COURSES = ROOT / "courses"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

URL_RE = re.compile(
    r"https?://(?:"
    r"youtu\.be/(?P<yt1>[\w-]{6,})"
    r"|(?:www\.)?youtube\.com/watch\?(?:[^\s)\"'<>]*&)?v=(?P<yt2>[\w-]{6,})"
    r"|(?:www\.)?(?:use)?loom\.com/share/(?P<loom>[0-9a-f]{16,})"
    r")[^\s)\"'<>\]]*"
)
# INDEX.md rows look like:  - **1 videopamoka. J. Aputis** (url) -> https://...
ROW_RE = re.compile(r"^\s*-\s+\*\*(?P<title>.*?)\*\*\s*\((?P<kind>[\w-]+)\)")
HEAD_RE = re.compile(r"^##\s+(?P<head>.+?)\s*$")


# ---------------------------------------------------------------- helpers
def course_dirs(arg):
    if arg:
        p = Path(arg)
        if not p.is_absolute():
            p = (ROOT / arg) if (ROOT / arg).exists() else (COURSES / arg)
        if not p.exists():
            sys.exit("no such course dir: " + str(arg))
        return [p]
    return sorted(d for d in COURSES.iterdir() if d.is_dir() and re.match(r"^\d+-", d.name))


def vid_id(url):
    """-> (id, source, canonical url)"""
    m = URL_RE.search(url)
    if not m:
        raise ValueError("not a known video url: " + url)
    if m.group("loom"):
        n = m.group("loom")
        return "loom-" + n[:12], "loom", "https://www.loom.com/share/" + n
    n = m.group("yt1") or m.group("yt2")
    return "yt-" + n, "youtube", "https://www.youtube.com/watch?v=" + n


def videos_dir(course):
    d = course / "videos"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_index(course):
    f = videos_dir(course) / "index.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"course": course.name, "videos": {}}


def save_index(course, idx):
    idx["course"] = course.name
    idx["updated"] = time.strftime("%Y-%m-%d %H:%M")
    (videos_dir(course) / "index.json").write_text(
        json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")


def run(cmd, timeout=900):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def ytdlp(args, timeout=900):
    return run([sys.executable, "-m", "yt_dlp", "--no-warnings", "--no-playlist"] + args, timeout)


# ---------------------------------------------------------------- 1. list
def collect(course):
    """Walk INDEX.md and pages/*.md, return {id: record}. Module title = the teacher's own wording."""
    found = {}

    def add(url, title, section, where):
        try:
            i, src, canon = vid_id(url)
        except ValueError:
            return
        rec = found.setdefault(i, {
            "id": i, "source": src, "url": canon, "title": (title or "").strip(),
            "section": (section or "").strip(), "found_in": where, "state": "new",
        })
        if not rec.get("title") and title:
            rec["title"] = title.strip()

    index = course / "INDEX.md"
    if index.exists():
        section = ""
        pending = ""  # title of the most recent bullet, so a url on the same line keeps its wording
        for line in index.read_text(encoding="utf-8").splitlines():
            h = HEAD_RE.match(line)
            if h:
                section = h.group("head")
                continue
            r = ROW_RE.match(line)
            if r:
                pending = r.group("title")
            for m in URL_RE.finditer(line):
                add(m.group(0), pending if r else "", section, "INDEX.md")

    pages = sorted((course / "pages").glob("*.md")) if (course / "pages").exists() else []
    for page in pages:
        text = page.read_text(encoding="utf-8", errors="replace")
        head = text.splitlines()[0].lstrip("# ").strip() if text else page.stem
        for m in URL_RE.finditer(text):
            add(m.group(0), head, head, "pages/" + page.name)
    return found


def cmd_list(args):
    for course in course_dirs(args.course):
        found = collect(course)
        if not found and not (course / "INDEX.md").exists():
            continue
        idx = load_index(course)
        for i, rec in found.items():
            old = idx["videos"].get(i)
            if old is None:
                idx["videos"][i] = rec
            else:
                for k, v in rec.items():
                    if k != "state":
                        old[k] = v
        if args.probe:
            for i, rec in idx["videos"].items():
                if rec.get("reachable") is None or args.reprobe:
                    ok, note = probe(rec["url"])
                    rec["reachable"], rec["probe_note"] = ok, note
                    print("  probe %-18s %s %s" % (i, "OK  " if ok else "DEAD", note[:70]))
            save_index(course, idx)
        save_index(course, idx)
        print("\n== %s  (%d videos)" % (course.name, len(idx["videos"])))
        print("%-18s %-8s %-12s section / title" % ("id", "src", "state"))
        for i, r in sorted(idx["videos"].items(), key=lambda kv: (kv[1].get("section", ""), kv[0])):
            reach = "" if r.get("reachable") is None else ("  " if r["reachable"] else " [DEAD]")
            print("%-18s %-8s %-12s%s %s / %s" % (
                i, r["source"], r.get("state", "new"), reach,
                r.get("section", "")[:26], r.get("title", "")[:52]))


def probe(url):
    """Cheap metadata-only reachability check - never downloads the video."""
    p = ytdlp(["-J", "--skip-download", "--socket-timeout", "20", url], timeout=120)
    if p.returncode == 0 and p.stdout.strip():
        try:
            d = json.loads(p.stdout)
            caps = sorted(set(list(d.get("subtitles") or {}) + list(d.get("automatic_captions") or {})))
            return True, "%ss caps=%s %s" % (d.get("duration") or "?",
                                             ",".join(caps[:4]) or "none", (d.get("title") or "")[:34])
        except Exception:
            return True, "metadata ok"
    err = (p.stderr or "").strip().splitlines()
    return False, err[-1][:160] if err else "no metadata"


# ---------------------------------------------------------------- 2. fetch
def find_record(key):
    i = key
    if URL_RE.search(key):
        i = vid_id(key)[0]
    for course in course_dirs(None):
        idx = load_index(course)
        if i in idx["videos"]:
            return course, idx["videos"][i]
    if URL_RE.search(key):
        i, src, canon = vid_id(key)
        return course_dirs(None)[0], {"id": i, "source": src, "url": canon,
                                      "title": "", "section": ""}
    sys.exit("unknown video id %r - run `video.py list` first" % key)


def meta(url):
    p = ytdlp(["-J", "--skip-download", url], timeout=180)
    if p.returncode != 0 or not p.stdout.strip():
        raise RuntimeError((p.stderr or "yt-dlp failed").strip().splitlines()[-1][:200])
    return json.loads(p.stdout)


def clean_vtt(vtt):
    """VTT -> plain text: dedup rolling auto-caption lines, one traceable timestamp every ~30 s."""
    out, seen, last_stamp, cur = [], [], -999.0, 0.0
    for raw in vtt.splitlines():
        line = raw.strip()
        if not line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE", "STYLE")):
            continue
        m = re.match(r"(\d+):(\d\d):(\d\d)[.,](\d+)\s*-->", line)
        if m:
            h, mi, s, _ = m.groups()
            cur = int(h) * 3600 + int(mi) * 60 + int(s)
            continue
        if re.match(r"^\d+$", line):
            continue
        line = re.sub(r"<[^>]+>", "", line).strip()
        if not line or line in seen[-6:]:
            continue
        seen.append(line)
        if cur - last_stamp >= 30:
            out.append("\n[%02d:%02d] " % (int(cur) // 60, int(cur) % 60))
            last_stamp = cur
        out.append(line + " ")
    return re.sub(r"[ \t]+\n", "\n", "".join(out)).strip()


def get_subs(url, out_dir, vid):
    """Free route 1: yt-dlp manual subs, then auto-captions. -> (vtt_path, text, source_label)"""
    for old in out_dir.glob(vid + ".*.vtt"):
        old.unlink()
    for auto, label in ((False, "manual"), (True, "auto-caption")):
        args = ["--skip-download", "--sub-langs", "lt.*,en.*", "--convert-subs", "vtt",
                "-o", str(out_dir / (vid + ".%(ext)s")), url]
        args = (["--write-auto-subs"] if auto else ["--write-subs"]) + args
        ytdlp(args, timeout=300)
        got = sorted(out_dir.glob(vid + ".*.vtt"))
        if got:
            f = got[0]
            lang = f.name[len(vid) + 1:-4]
            return str(f), clean_vtt(f.read_text(encoding="utf-8", errors="replace")), \
                "%s (%s)" % (label, lang)
    return None, None, "none"


def loom_transcript(url, out_dir, vid):
    """Free route 2: Loom keeps its transcript in the public share page's Apollo state, when one exists."""
    try:
        import requests
    except Exception:
        return None, None, "none"
    try:
        html = requests.get(url, headers={"User-Agent": UA}, timeout=30).text
    except Exception as e:
        return None, None, "none (loom fetch failed: %s)" % e
    k = html.find("fetchVideoTranscript(")
    if k < 0:
        return None, None, "none"
    blob = html[k:k + 200000]
    if "No transcript associated" in blob[:400] or "InvalidRequestWarning" in blob[:400]:
        return None, None, "none (loom: no transcript record)"
    segs = re.findall(r'\\"text\\":\\"(.*?)\\".{0,80}?\\"start_?time\\":\s*([\d.]+)', blob)
    if not segs:
        segs = re.findall(r'"text":"(.*?)".{0,80}?"start_?time":\s*([\d.]+)', blob)
    if not segs:
        return None, None, "none (loom: transcript present but unparsable)"
    lines, last = [], -999.0
    for text, start in segs:
        t = float(start)
        if "\\u" in text:
            try:
                text = text.encode("utf-8").decode("unicode_escape")
            except Exception:
                pass
        if t - last >= 30:
            lines.append("\n[%02d:%02d] " % (int(t) // 60, int(t) % 60))
            last = t
        lines.append(text.strip() + " ")
    txt = "".join(lines).strip()
    p = out_dir / (vid + ".loom.txt")
    p.write_text(txt, encoding="utf-8")
    return str(p), txt, "loom transcript"


def download_low(url, tmpdir):
    """Pull the smallest usable copy to disk before touching ffmpeg.

    Measured 2026-09-09: seeking into a remote googlevideo/Loom CDN url stalls (one frame timed out
    after 300 s) and full-stream scene detection over HTTP took 20 min for one 44 min lesson, while the
    same video downloads at 480p in seconds and is then instant to sample. The copy is deleted again -
    nothing large is left in the workspace.
    """
    out = os.path.join(tmpdir, "v.%(ext)s")
    p = ytdlp(["-f", "bv*[height<=480]/b[height<=480]/bv*[height<=720]/b", "--no-part",
               "-o", out, url], timeout=1800)
    files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.startswith("v.")]
    if not files:
        raise RuntimeError((p.stderr or "download failed").strip().splitlines()[-1][:200])
    return max(files, key=os.path.getsize)


def stream_url(url):
    """A low-resolution direct/HLS url, so frame scanning costs a fraction of the full video."""
    p = ytdlp(["-g", "-f", "bv*[height<=480]/b[height<=480]/bv*[height<=720]/b", url], timeout=180)
    if p.returncode != 0 or not p.stdout.strip():
        raise RuntimeError((p.stderr or "no stream url").strip().splitlines()[-1][:200])
    return p.stdout.strip().splitlines()[0]


def probe_video_seconds(src):
    """Duration of the VIDEO stream alone (ffprobe), or None."""
    p = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=duration", "-of", "default=nk=1:nw=1", src], timeout=180)
    try:
        return float((p.stdout or "").strip().splitlines()[0])
    except Exception:
        return None


def grab_frames(src, out_dir, vid, n, duration, scene=False):
    """Slide frames for one lesson.

    Default = SEEK GRID: n separate ffmpeg seeks spread over the lesson. Measured 2026-09-09 this is
    the difference between seconds and many minutes per video, because scene detection has to pull and
    decode the whole stream. --scene turns the slower, more faithful keyframe scene detection back on
    (worth it for a fast-moving lesson; a slide talk gains almost nothing).
    """
    fdir = out_dir / (vid + "-frames")
    fdir.mkdir(parents=True, exist_ok=True)
    for old in fdir.glob("*.jpg"):
        old.unlink()
    if not scene:
        dur = float(duration or 600)
        # Some Loom recordings (measured 2026-09-09 on the 2020 useloom lessons) store 40 min of AUDIO
        # over only a few seconds of VIDEO, so a grid over the container duration lands past the end and
        # silently produces nothing. Trust the video stream's own duration when it is much shorter.
        vd = probe_video_seconds(src)
        if vd and vd < dur * 0.9:
            print("   NOTE: video stream is only %.1f s of a %.0f s recording - sampling the video part"
                  % (vd, dur))
            dur = vd
        out = []
        for i in range(max(1, n)):
            t = dur * (i + 0.5) / max(1, n)
            f = fdir / ("g%03d.jpg" % (i + 1))
            run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-ss", "%.2f" % t,
                 "-i", src, "-frames:v", "1", "-vf", "scale=1280:-1,format=yuvj420p", "-q:v", "4", str(f)],
                timeout=300)
            if f.exists() and f.stat().st_size > 0:
                out.append({"file": f.name, "at": "%02d:%02d" % (int(t) // 60, int(t) % 60)})
        if out:
            return out
        print("   seek grid produced nothing - falling back to scene detection")
    p = run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "info", "-skip_frame", "nokey",
             "-i", src, "-vf", "select='gt(scene,0.25)',scale=1280:-1,format=yuvj420p,showinfo",
             "-vsync", "vfr", "-q:v", "4", str(fdir / "s%03d.jpg")], timeout=2400)
    times = [float(t) for t in re.findall(r"pts_time:([\d.]+)", p.stderr or "")]
    shots = sorted(fdir.glob("s*.jpg"))
    # A slide lesson often changes too slowly for scene detection to yield enough shots; then an even
    # time grid across the whole lesson is the honest sampling. Measured 2026-09-09: a 42 min Loom
    # lesson produced only 2 scene shots, so anything under half the cap falls back.
    if len(shots) < max(3, n // 2):
        for f in fdir.glob("*.jpg"):
            f.unlink()
        shots = []
    if not shots:  # scene detection found nothing usable - fall back to an even time grid
        step = max(1.0, (duration or 600) / max(1, n))
        run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", src,
             "-vf", "fps=1/%.3f,scale=1280:-1,format=yuvj420p" % step, "-frames:v", str(n), "-q:v", "4",
             str(fdir / "t%03d.jpg")], timeout=2400)
        shots = sorted(fdir.glob("t*.jpg"))
        times = [i * step for i in range(len(shots))]
    if len(shots) > n:  # evenly spread the cap across the whole lesson, never just the first N
        keep = sorted({int(round(i * (len(shots) - 1) / (n - 1))) for i in range(n)}) if n > 1 else [0]
        for j, f in enumerate(shots):
            if j not in keep:
                f.unlink()
        times = [times[j] for j in keep if j < len(times)]
        shots = [shots[j] for j in keep]
    out = []
    for j, f in enumerate(shots):
        t = times[j] if j < len(times) else None
        out.append({"file": f.name,
                    "at": ("%02d:%02d" % (int(t) // 60, int(t) % 60)) if t is not None else "?"})
    return out


def write_md(course, rec, m, tsrc, text, frames):
    d = videos_dir(course)
    dur = m.get("duration")
    lines = [
        "# " + (rec.get("title") or m.get("title") or rec["id"]),
        "",
        "- video id: `%s` (%s)" % (rec["id"], rec["source"]),
        "- url: " + rec["url"],
        "- course section: " + str(rec.get("section", "")),
        "- moodle title (teacher's own wording): " + str(rec.get("title", "")),
        "- youtube/loom title: " + str(m.get("title", "")),
        ("- duration: %d min %d s" % (int(dur) // 60, int(dur) % 60)) if dur else "- duration: unknown",
        "- transcript source: " + tsrc,
        "- frames: %d in `%s-frames/`" % (len(frames), rec["id"]),
        "- fetched: " + time.strftime("%Y-%m-%d %H:%M"),
        "",
        "## Frames (slides) - READ THESE BY EYE",
        "",
    ]
    for j, f in enumerate(frames, 1):
        lines.append("%d. `%s-frames/%s` at %s" % (j, rec["id"], f["file"], f["at"]))
    if not frames:
        lines.append("_none extracted_")
    lines += ["", "## Transcript", ""]
    lines.append(text if text else
                 "_No free transcript route for this video (marked `needs-audio` in index.json). "
                 "The frames above are the only text currently available._")
    p = d / (rec["id"] + ".md")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def fetch_one(course, rec, nframes, do_frames=True, scene=False):
    d = videos_dir(course)
    print("-- %s %s" % (rec["id"], rec.get("title", "")[:60]))
    try:
        m = meta(rec["url"])
    except Exception as e:
        rec["state"], rec["error"], rec["reachable"] = "unreachable", str(e), False
        print("   UNREACHABLE: %s" % e)
        return rec
    rec["reachable"] = True
    for stale in ("frames_error", "error"):
        rec.pop(stale, None)
    rec["duration"] = m.get("duration")
    rec["video_title"] = m.get("title")

    vttp, text, tsrc = get_subs(rec["url"], d, rec["id"])
    if not text and rec["source"] == "loom":
        vttp, text, tsrc = loom_transcript(rec["url"], d, rec["id"])
    rec["transcript_source"] = tsrc
    rec["transcript_file"] = os.path.basename(vttp) if vttp else None

    frames = []
    if do_frames:
        tmp = tempfile.mkdtemp(prefix="video-" + rec["id"] + "-")
        try:
            local = download_low(rec["url"], tmp)
            rec["mb_downloaded"] = round(os.path.getsize(local) / 1048576.0, 1)
            frames = grab_frames(local, d, rec["id"], nframes, m.get("duration"), scene)
        except Exception as e:
            rec["frames_error"] = str(e)
            print("   frames failed: %s" % e)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    rec["frames"] = len(frames)
    rec["md"] = rec["id"] + ".md"
    rec["state"] = "transcribed" if text else ("frames-only" if frames else "needs-audio")
    rec["needs_audio"] = not bool(text)
    write_md(course, rec, m, tsrc, text, frames)
    print("   %s  transcript=%s  frames=%d" % (rec["state"], tsrc, len(frames)))
    return rec


def cmd_fetch(args):
    course, rec = find_record(args.key)
    idx = load_index(course)
    rec = fetch_one(course, rec, args.frames, not args.no_frames, args.scene)
    idx["videos"][rec["id"]] = rec
    save_index(course, idx)
    if rec.get("md"):
        print("\nwrote %s" % (videos_dir(course) / rec["md"]))
    else:
        print("\nnothing written - state=%s (%s)" % (rec.get("state"), rec.get("error", "")[:120]))


# ---------------------------------------------------------------- 3. scan
def cmd_scan(args):
    for course in course_dirs(args.course):
        found = collect(course)
        idx = load_index(course)
        for i, r in found.items():
            idx["videos"].setdefault(i, r)
        todo = [i for i, r in idx["videos"].items()
                if args.refetch or r.get("state", "new") in ("new", "")]
        if args.limit:
            todo = todo[:args.limit]
        print("== %s: %d to fetch of %d" % (course.name, len(todo), len(idx["videos"])))
        for i in todo:
            idx["videos"][i] = fetch_one(course, idx["videos"][i], args.frames,
                                        not args.no_frames, args.scene)
            save_index(course, idx)  # resumable after every single video
        save_index(course, idx)
        summarise(course, idx)


# ---------------------------------------------------------------- 4. transcribe (local, free)
def download_audio(url, tmpdir):
    """Audio only - a fraction of the video's bytes, which is all speech-to-text needs."""
    out = os.path.join(tmpdir, "a.%(ext)s")
    p = ytdlp(["-f", "bestaudio[ext=m4a]/bestaudio/best", "--no-part", "-o", out, url], timeout=2400)
    files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.startswith("a.")]
    if not files:
        raise RuntimeError((p.stderr or "audio download failed").strip().splitlines()[-1][:200])
    return max(files, key=os.path.getsize)


_MODELS = {}


def whisper_model(size, threads):
    """One model instance per process - loading costs ~10 s and it is reused for every lesson."""
    if size not in _MODELS:
        from faster_whisper import WhisperModel
        _MODELS[size] = WhisperModel(size, device="cpu", compute_type="int8", cpu_threads=threads)
    return _MODELS[size]


def transcribe_one(course, rec, size="small", threads=4, lang="lt", refetch=False):
    """Speech -> text on this PC, for free.

    WHY. Measured 2026-09-09: the teachers' lessons carry no captions anywhere (YouTube auto-captions
    missing on 54 of 55, Loom answers "No transcript associated with video"), so the only route to what
    they SAY is a local model. faster-whisper `small`, int8, 6 threads on the owner's i7-10750H ran at
    6.9x realtime - a 44 min lesson costs about 6 min of background CPU and nothing in money.
    """
    d = videos_dir(course)
    dest = d / (rec["id"] + ".lt.txt")
    if dest.exists() and not refetch:
        print("-- %s already transcribed" % rec["id"])
        return rec, False
    if rec.get("reachable") is False:
        print("-- %s unreachable, skipped" % rec["id"])
        return rec, False
    print("-- %s %s" % (rec["id"], (rec.get("title") or "")[:58]))
    tmp = tempfile.mkdtemp(prefix="audio-" + rec["id"] + "-")
    try:
        t0 = time.time()
        raw = download_audio(rec["url"], tmp)
        wav = os.path.join(tmp, "a16.wav")
        run(["ffmpeg", "-y", "-nostdin", "-loglevel", "error", "-i", raw,
             "-ac", "1", "-ar", "16000", wav], timeout=1800)
        if not os.path.exists(wav):
            raise RuntimeError("ffmpeg produced no wav")
        dl = time.time() - t0
        t0 = time.time()
        model = whisper_model(size, threads)
        segs, info = model.transcribe(wav, language=lang, beam_size=1, vad_filter=True)
        lines, last = [], -999.0
        for sg in segs:
            if sg.start - last >= 30:
                lines.append("\n[%02d:%02d] " % (int(sg.start) // 60, int(sg.start) % 60))
                last = sg.start
            lines.append(sg.text.strip() + " ")
        text = "".join(lines).strip()
        el = time.time() - t0
        dur = rec.get("duration") or 0
        dest.write_text(text, encoding="utf-8")
        rec["transcript_source"] = "local-whisper-" + size
        rec["transcript_file"] = dest.name
        rec["transcribed_at"] = time.strftime("%Y-%m-%d %H:%M")
        rec["needs_audio"] = False
        rec["state"] = "transcribed"
        m = {"duration": rec.get("duration"), "title": rec.get("video_title")}
        frames = []
        for j in range(1, int(rec.get("frames") or 0) + 1):
            frames.append({"file": "s%03d.jpg" % j, "at": "?"})
        md = d / (rec["id"] + ".md")
        if md.exists():
            old = md.read_text(encoding="utf-8")
            head, sep, _ = old.partition("## Transcript")
            head = head.replace("- transcript source: none", "- transcript source: local-whisper-" + size)
            head = re.sub(r"- transcript source: .*", "- transcript source: local-whisper-" + size, head, count=1)
            md.write_text(head + "## Transcript\n\n" + text + "\n", encoding="utf-8")
        else:
            write_md(course, rec, m, rec["transcript_source"], text, frames)
        print("   ok  %d chars  (audio %.0fs, asr %.0fs%s)"
              % (len(text), dl, el, ", %.1fx realtime" % (dur / el) if dur and el else ""))
        return rec, True
    except Exception as e:
        rec["transcribe_error"] = str(e)[:300]
        print("   FAILED: %s" % str(e)[:200])
        return rec, False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cmd_transcribe(args):
    ids = [x.strip() for x in (args.ids or "").split(",") if x.strip()]
    done = 0
    for course in course_dirs(args.course):
        if not (course / "videos" / "index.json").exists():
            continue
        idx = load_index(course)
        todo = []
        for i, r in idx["videos"].items():
            if ids and i not in ids:
                continue
            if args.section and str(r.get("section", "")) != args.section:
                continue
            if r.get("state") == "unreachable" or r.get("reachable") is False:
                continue
            if r.get("transcript_source", "").startswith("local-whisper") and not args.refetch:
                continue
            todo.append(i)
        if args.limit:
            todo = todo[:args.limit]
        print("== %s: %d lesson(s) to transcribe with %s" % (course.name, len(todo), args.model))
        for i in todo:
            idx["videos"][i], ok = transcribe_one(course, idx["videos"][i], args.model,
                                                  args.threads, args.lang, args.refetch)
            save_index(course, idx)  # resumable after every single lesson
            done += bool(ok)
        save_index(course, idx)
        summarise(course, idx)
    print("\ntranscribed %d lesson(s)" % done)


def summarise(course, idx=None):
    idx = idx or load_index(course)
    by = {}
    for i, r in idx["videos"].items():
        by.setdefault(r.get("state", "new"), []).append(i)
    print("\n-- %s" % course.name)
    for k in ("transcribed", "frames-only", "needs-audio", "unreachable", "new"):
        if by.get(k):
            print("   %-12s %3d   %s%s" % (k, len(by[k]), ", ".join(sorted(by[k])[:6]),
                                           " ..." if len(by[k]) > 6 else ""))


def cmd_status(args):
    for course in course_dirs(args.course):
        if (course / "videos" / "index.json").exists():
            summarise(course)


# ---------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("list", help="inventory video urls in the mirrored courses")
    p.add_argument("course", nargs="?")
    p.add_argument("--probe", action="store_true", help="metadata-only reachability check (no download)")
    p.add_argument("--reprobe", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("fetch", help="transcript + frames for one video")
    p.add_argument("key", help="video id from `list`, or a url")
    p.add_argument("--frames", type=int, default=12)
    p.add_argument("--no-frames", action="store_true")
    p.add_argument("--scene", action="store_true", help="slow keyframe scene detection instead of a seek grid")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("scan", help="fetch everything not yet fetched (resumable)")
    p.add_argument("course", nargs="?")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--frames", type=int, default=12)
    p.add_argument("--no-frames", action="store_true")
    p.add_argument("--scene", action="store_true", help="slow keyframe scene detection instead of a seek grid")
    p.add_argument("--refetch", action="store_true")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("transcribe", help="local speech-to-text (faster-whisper, free, no key)")
    p.add_argument("course", nargs="?")
    p.add_argument("--ids", help="comma-separated video ids (default: every reachable lesson)")
    p.add_argument("--section", help="only this course section, e.g. \"Topic 8\"")
    p.add_argument("--model", default="small", help="tiny|base|small|medium|large-v3 (small = 6.9x realtime here)")
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--lang", default="lt")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--refetch", action="store_true")
    p.set_defaults(func=cmd_transcribe)

    p = sub.add_parser("status", help="what is transcribed / frames-only / still needs audio")
    p.add_argument("course", nargs="?")
    p.set_defaults(func=cmd_status)

    args = ap.parse_args()
    if not getattr(args, "func", None):
        ap.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
