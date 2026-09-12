#!/usr/bin/env python
"""look.py - headless screenshots of the web app at desktop (1280) and phone (390) widths, read back before presenting.

    python product/tools/look.py [--out product/.look] [pages...]      default pages: index, app, demo hub

Serves product/web on a free local port with http.server (the app fetches ../i18n/*.json, so file:// is not enough),
renders each page with Playwright Chromium, prints height + horizontal-overflow per shot, writes PNGs to --out.
"""
from __future__ import annotations

import argparse
import http.server
import socket
import socketserver
import sys
import threading
from functools import partial
from pathlib import Path

HERE = Path(__file__).resolve().parent
WEB = HERE.parent / "web"
PAGES = {"index": "/index.html", "app": "/app/index.html", "hub": "/app/demo-hub.html", "terms": "/legal/terms.html", "privacy": "/legal/privacy.html"}


def serve() -> tuple[socketserver.TCPServer, int]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(WEB))
    handler.log_message = lambda *a, **k: None  # type: ignore[attr-defined]
    srv = socketserver.TCPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, port


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pages", nargs="*", default=list(PAGES))
    ap.add_argument("--out", default=str(HERE.parent / ".look"))
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    srv, port = serve()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            for name in a.pages:
                path = PAGES.get(name, name)
                for w in (1280, 390):
                    pg = b.new_page(viewport={"width": w, "height": 900 if w > 400 else 844}, device_scale_factor=1)
                    errors: list[str] = []
                    pg.on("pageerror", lambda e: errors.append(str(e)))
                    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                    pg.goto(f"http://127.0.0.1:{port}{path}", wait_until="networkidle")
                    pg.wait_for_timeout(600)
                    h = pg.evaluate("document.documentElement.scrollHeight")
                    overflow = pg.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
                    f = out / f"{name}-{w}.png"
                    pg.screenshot(path=str(f), full_page=True)
                    print(f"{f.name}: height {h}px, overflow {'YES' if overflow else 'no'}, errors {len(errors)}" + (f" -> {errors[:3]}" if errors else ""))
                    pg.close()
            b.close()
    finally:
        srv.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
