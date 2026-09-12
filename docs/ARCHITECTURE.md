# Architecture (proposal v1, 2026-09-12)

Working name: **StudyRadar** (placeholder; never "Moodle" in the product name - Moodle is a trademark;
"works with Moodle" is allowed as descriptive use). Folder `product/` inside the MokymasisSuAjajum
workspace; own git repository (git dir kept OUTSIDE Google Drive via a `.git` gitdir file, see
`product/tools/repo.ps1`) published to GitHub; the web app is served from GitHub Pages.

## One engine, two products

```
personal system (this workspace)          product/ (SaaS)
 tools/plan.py, units.py, material.py,     engine/studycore/  <- one-way synced copies of the
 calc.py, board.js, extract.py, video.py,     personal tools (tools/sync_engine.py, manifest +
 topic.py + templates                          drift report) + thin adapters that parametrise
                                                paths, slots, intervals, language, subject shape
 study/ (one student, Lithuanian)          per-user workspace dir (same file layout, any language)
 Claude authors content JSON by hand       digest.py authors content JSON through a model adapter
                                             (ollama | anthropic | openai | none = tokenless baseline)
 homework.py, outlook.py, agent_runner     NOT ported (owner: no automatic assignments, no messages)
```

The personal system stays the source of truth for the engine; the product never edits the copies
by hand. A product-only change goes into an adapter or, when it is an engine improvement, into the
personal tool first and then syncs.

## Where things run (privacy by design, zero fixed cost)

1. **Collector** - runs where the student's Moodle session already is:
   - Route A: Moodle web-service token obtained through the site's own mobile launch flow (only the
     token is stored, encrypted per user; the password is never seen). Works on sites with the
     mobile service ON.
   - Route B: browser extension (MV3, Chrome/Edge/Firefox) - runs inside the student's logged-in
     browser, reads courses/contents/calendar/notifications through Moodle's own session AJAX,
     never sees the password, works with ANY SSO and with the mobile service OFF (the owner's school).
   - Route C: local connector (Python CLI, the personal system generalised) for self-hosting.
   - NEVER: storing the student's Moodle password on our side.
2. **Engine** - Python `studycore`: inventory -> extract (docx/pdf/pptx/html) -> video frames +
   local whisper -> digest -> topic pages -> units -> plan (sliders) -> live JSON.
   Runs in the local connector, or in a "home worker" (a PC of ours pulling encrypted jobs) for
   cloud-tier users; later on any server.
3. **API** - one Cloudflare Worker on the free plan: magic-link auth, account + subscription state
   (payment-provider webhooks), trial registry keyed by hash(moodle site + user id), per-user
   encrypted blob store (plan, progress, settings, overrides), job queue, /geo (CF-IPCountry ->
   default language), /report (bug/feature), /consent, opt-in telemetry, web push.
4. **Web app** - static (GitHub Pages): landing + dashboard + daily study hub (the personal hub
   template generalised and translated). Works in demo mode without any account.

## Sliders (the adaptable minimum time ceiling)

For each assessment: material seconds at coverage c(target) = units sorted by probability weight,
taken until the weighted share reaches c; required seconds/day R = (learn + reviews + imitation) /
days left. The minutes slider cannot go below ceil(R/60) for that target ("forced minimum"); moving
the grade slider changes the minimum; moving the minutes slider below the ideal shows the estimated
grade (weighted coverage -> the country's grade scale) and the minutes saved per day x days left.
Every number is labelled an estimate.

## Not ported on purpose (owner 2026-09-12)

Automatic assignment writing/submission, automatic teacher letters, anything acting in the user's
name on Moodle. The fact-checker ("certain facts beat the material") ships as a per-user switch,
OFF by default, and every correction it makes is listed with its basis.
