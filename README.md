# Planas (working name) — a study assistant that works with Moodle™

Every test, every deadline, every new file from a student's own Moodle in one place, and a short daily plan to be ready
for the next in-person test or exam. Any subject, any language. The student's Moodle password never reaches our servers.

> Status: **unpublished local pilot.** Nothing is sold yet; `release.json` says `finished: false`.
> Demo (sample data, no account): https://crystalius7.github.io/planas-app/ · Code: https://github.com/Crystalius7/planas-app
> Not affiliated with or endorsed by Moodle Pty Ltd. "Moodle" is a trademark of Moodle Pty Ltd.

## What is in this repository

| Folder | What it is |
|---|---|
| `engine/studycore/` | The study engine (Python). `vendor/` holds one-way synced copies of the owner's personal study tools; the rest are thin adapters: sliders, grade scales, subject shapes, collectors, digest, notifications, rendering. |
| `connector/` | The local app: a small HTTP API on 127.0.0.1 that the web app and the browser extension talk to. Everything runs and stays on the student's computer, with one disclosed exception: the optional paid cloud digest sends the selected material text to a model provider (privacy policy §3). |
| `extension/` | MV3 browser extension: collects courses, deadlines and files from the Moodle tab the student is logged into and hands them to the connector. |
| `web/` | The web app (static): landing page, dashboard, daily study hub, translations, legal pages. Runs in demo mode without an account. |
| `api/` | The hosted API for accounts, trials, subscriptions and encrypted per-user blobs: one Cloudflare Worker on the free plan. Not deployed yet. |
| `docs/` | Architecture, research (Moodle rules, law, payments, hosting), security model, features, pricing, launch checklist, portfolio automation. |
| `tests/` | Engine tests (`python tests/test_engine.py`). |
| `tools/` | `sync_engine.py` (engine export), `look.py` (screenshots), `hub_strings.py` (chrome translation list), `release.py` (finished switch + portfolio hand-off), `repo.ps1`. |

## Run it locally

```
python tests/test_engine.py                 # engine tests
python connector/cli.py serve               # local app on http://127.0.0.1:8765
python -m http.server 8080 -d web           # then open http://localhost:8080/app/  (demo mode if the connector is off)
python tools/look.py                        # screenshots of the pages at 1280 and 390 px
```

Requirements: Python 3.12, `requests`; optional `playwright` (screenshots), `faster-whisper` + `ffmpeg` (video lessons),
`anthropic` (cloud digest), Ollama (local digest).

## How the pieces fit

Collect (extension or token, on the student's side) → mirror into a per-user workspace → inventory + extraction (documents,
slides, video frames and local transcripts) → digest into study content (baseline without a model; Ollama locally; a cloud
model on the paid tier) → topic pages + study units → the planner packs them into short daily sessions with spaced review
and test rehearsal, under the two sliders (minutes per day with a forced minimum; grade target with an estimate band) → the
web app shows the calendar, the material ledger, notifications and the daily hub.

## Licence

All rights reserved for now (pilot). The vendored personal tools remain the owner's.
