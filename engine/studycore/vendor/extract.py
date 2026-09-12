#!/usr/bin/env python
"""extract.py - turn mirrored course files (DOCX, PDF, PPTX, TXT) into plain text + images under pages/files/.

    python tools/extract.py courses/<id>-<slug>          # every file under files/ -> pages/files/<name>.md (+ <name>-images/)

A teacher's DOCX is often SCREENSHOTS ONLY (measured 2026-09-08: two Biology files held 14 PNGs and about ten
words), so every embedded image is dumped beside the text, in document order, for the agent to READ by eye.
Text is what the study pages are built from; the binary stays as the source of truth.
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

if sys.stdout:  # pythonw (scheduled task) has no console streams
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]


def docx_media(p: Path, dest: Path) -> list[str]:
    """Dump word/media/* in the order the document embeds them (rels id -> target, body r:embed order)."""
    with zipfile.ZipFile(p) as z:
        names = [n for n in z.namelist() if n.startswith("word/media/")]
        if not names:
            return []
        rels = z.read("word/_rels/document.xml.rels").decode("utf-8", "ignore")
        idmap = dict(re.findall(r'Id="([^"]+)"[^>]*Target="media/([^"]+)"', rels))
        idmap.update({k: v for v, k in re.findall(r'Target="media/([^"]+)"[^>]*Id="([^"]+)"', rels)})
        body = z.read("word/document.xml").decode("utf-8", "ignore")
        order = [idmap[i] for i in re.findall(r'r:embed="([^"]+)"', body) if i in idmap]
        ordered = list(dict.fromkeys(order + [Path(n).name for n in names]))
        dest.mkdir(parents=True, exist_ok=True)
        out = []
        for k, fname in enumerate(ordered, 1):
            data = z.read(f"word/media/{fname}")
            new = f"{k:02d}-{fname}"
            (dest / new).write_bytes(data)
            out.append(new)
        return out


def docx_text(p: Path) -> str:
    import docx
    d = docx.Document(str(p))
    out = []
    for para in d.paragraphs:
        if para.text.strip():
            style = (para.style.name or "").lower()
            prefix = "# " if style.startswith("heading 1") or style == "title" else "## " if style.startswith("heading") else ""
            out.append(prefix + para.text.strip())
    for tb in d.tables:
        out.append("")
        for row in tb.rows:
            out.append("| " + " | ".join(c.text.strip().replace("\n", " ") for c in row.cells) + " |")
    return "\n".join(out)


def pdf_text(p: Path) -> str:
    from pypdf import PdfReader
    return "\n\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)


def pptx_text(p: Path) -> str:
    """Slide text WITHOUT python-pptx: read the slide XML out of the zip, keep <a:t> runs and OMML <m:t> maths.

    Measured 2026-09-09: python-pptx is not installed on this PC, so every mirrored .pptx had been extracted as the
    string "(python-pptx not installed)" - and the maths teacher's formula examples live in exactly those slides.
    """
    try:
        from pptx import Presentation  # noqa: F401  (kept: if it IS installed, its reading order is better)
        return _pptx_text_lib(p)
    except ImportError:
        pass
    out = []
    with zipfile.ZipFile(p) as z:
        names = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                       key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)))
        for i, n in enumerate(names, 1):
            xml = z.read(n).decode("utf-8", "ignore")
            xml = xml.replace("</a:p>", "\n")
            # exactly <a:t>/<m:t> - NOT <a:tabLst>, which an [^>]* pattern swallows along with all the markup after it
            runs = re.findall(r"<(?:a|m):t(?:\s[^>]*)?>(.*?)</(?:a|m):t>", xml, re.S)
            txt = "".join(runs)
            txt = (txt.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                      .replace("&quot;", '"').replace("&apos;", "'"))
            txt = re.sub(r"[ \t]+", " ", txt).strip()
            out.append(f"## Slide {i}\n{txt}" if txt else f"## Slide {i}\n(be teksto - tik paveikslai)")
    return "\n\n".join(out)


def _pptx_text_lib(p: Path) -> str:
    from pptx import Presentation
    out = []
    for i, slide in enumerate(Presentation(str(p)).slides, 1):
        out.append(f"## Slide {i}")
        for sh in slide.shapes:
            if sh.has_text_frame and sh.text_frame.text.strip():
                out.append(sh.text_frame.text.strip())
    return "\n".join(out)


def pptx_media(p: Path, dest: Path) -> list[str]:
    """Dump ppt/media/* - most teacher slides are screenshots, so the picture IS the content."""
    with zipfile.ZipFile(p) as z:
        names = [n for n in z.namelist() if n.startswith("ppt/media/") and not n.endswith("/")]
        if not names:
            return []
        dest.mkdir(parents=True, exist_ok=True)
        out = []
        for k, n in enumerate(sorted(names, key=lambda x: (len(x), x)), 1):
            new = f"{k:02d}-{Path(n).name}"
            (dest / new).write_bytes(z.read(n))
            out.append(new)
        return out


def main(argv):
    root = Path(argv[0]) if argv else None
    if not root or not (root / "files").exists():
        print(__doc__)
        return
    dest = root / "pages" / "files"
    dest.mkdir(parents=True, exist_ok=True)
    for f in sorted((root / "files").rglob("*")):
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        fn = {".docx": docx_text, ".pdf": pdf_text, ".pptx": pptx_text,
              ".txt": lambda p: p.read_text(encoding="utf-8", errors="replace")}.get(ext)
        if not fn:
            continue
        try:
            txt = fn(f)
        except Exception as e:  # noqa: BLE001
            txt = f"(extraction failed: {e})"
        stem = f.relative_to(root / "files").as_posix().replace("/", "__")
        out = dest / (stem + ".md")
        media = []
        if ext in (".docx", ".pptx"):
            try:
                media = (docx_media if ext == ".docx" else pptx_media)(f, dest / (stem + "-images"))
            except Exception as e:  # noqa: BLE001
                txt += "\n\n(image extraction failed: " + str(e) + ")"
        if media:
            txt += "\n\n## Images inside the document, in order (READ them - the text above may be nearly empty)\n" + \
                   "\n".join(f"- {stem}-images/{m}" for m in media)
        out.write_text(f"# {f.name}\n\n{txt}", encoding="utf-8")
        print(f"{f.relative_to(root)} -> {out.relative_to(root)} ({len(txt)} chars, {len(media)} images)")


if __name__ == "__main__":
    main(sys.argv[1:])
