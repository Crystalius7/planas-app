# Features (v1 scope, 2026-09-12)

## Asked for by the owner (2026-09-12) and where each lives

| Feature | Where | State |
|---|---|---|
| All Moodle info in one place: courses, tests, exams, deadlines, notifications | collect.py (token + session + bundle), notify.py, dashboard "Today" + "Tests & exams" | built (local pilot) |
| Study efficiently for the next in-person test/exam, video lessons transcribed and frames scanned | vendor plan.py/units.py/video.py through workspace.bind(); digest.py | built (engine); video route needs ffmpeg + faster-whisper installed on the student's PC |
| Minutes-per-day slider with a FORCED adaptable minimum | planner.workload()/estimate(); dashboard sliders | built |
| Grade-target slider; show the grade drop and the time saved | grades.py + planner.estimate(); readout tiles | built (labelled estimates) |
| "Done" button per test/exam; completed ones grey, nearby | planner.mark_done(); "Completed" collapsible list | built |
| Manual editing of test/exam dates and times | planner.set_date(); Edit form | built |
| Notifications when new material is posted | notify.watch() + bell drawer; extension re-collects every 3 h | built (delivery beyond the app: web push + e-mail pending) |
| Smart "add the new material" button | notify.new_material_for_topics() + Connector.material_add() | built (routes by course section; unrouted items listed) |
| Show every digested material item so the user can check nothing is missing | render.digested_material(); "Material" tab with verdicts | built |
| Any subject worldwide; science/maths style for physics, chemistry | subjects.py families + shapes; digest contract per shape | built (classifier); page shapes reuse the personal topic.py sections |
| Any language; default by IP; switchable to most relevant languages | i18n/*.json (en + lt reviewed; 8 more planned), /geo on the API, language switcher (40 languages listed, English fallback) | built (en, lt); hub chrome translated through `chrome` tables |
| Fact checker as a switch, OFF by default | factcheck.py; settings switch; corrections list | built |
| Consent to share non-sensitive data for improvement | settings switch → /consent; telemetry off by default | built (switch); telemetry events not yet emitted |
| Bug / feature button that does not obstruct the UI | floating button → dialog → /report (local + hosted) | built |
| No automatic assignment completion, no automatic messages | engine manifest excludes homework.py, outlook.py, agent_runner.py | enforced by the export allowlist |
| 1-week free trial, abuse-resistant | /trial/claim (e-mail + Moodle fingerprint + IP cap) + card-required trial at the merchant of record | API built; provider account pending |
| Cheapest payments | Creem (MoR) first, Stripe Managed Payments in parallel - docs/RESEARCH.md §3 | decision pending owner |
| Legal protection from grade blame | Terms (no guarantee of results, liability limits within EU consumer law), disclaimer in the footer of every page | drafted (web/legal) |
| Host on GitHub; portfolio card when finished | repo.ps1 (git dir outside Drive), GitHub Pages for the demo; release.py finish → portfolio entry + broadcast to Lojalumas | built |
| Privacy and payment security at the highest level | docs/SECURITY.md | designed; items in §5 pending |

## Features I would add (my recommendations, not built unless marked)

1. **"What will be on the test" confidence view** - per assessment, the ranked questions with their source citations and an
   honest split: from the teacher's own quizzes / from the textbook / from the national exam archive / estimated. Students
   trust a plan they can audit; it also makes the "estimate" label meaningful. (engine has the data: `w` + `why`.)
2. **Teacher-quiz replay** - Moodle quizzes the student has already attempted expose their questions in the review page;
   mirroring those (with the student's own answers) is the single most predictive test-track source. Route B can read them.
3. **Exam-archive packs per country** - the personal system mirrors NŠA VBE papers; the product needs one pack per country
   (LT VBE, PL matura, DE Abitur, UK GCSE/A-level, ...) as optional downloads, each tagged by topic. Start with LT and PL.
4. **Study streak and "5-minute now" push** - a web-push at the student's chosen slot times with one tap into the hub;
   the plan's three slots already exist, the push is the missing nudge.
5. **Parent/teacher read-only link** - an opt-in share link showing only the calendar and the streak (no content), which
   is what parents ask for and what schools tolerate.
6. **Offline PWA** - the hub already works offline (localStorage); a manifest + service worker makes it installable and
   enables iOS push.
7. **Calendar export (ICS)** - every assessment and deadline as an .ics feed for the phone calendar; near-zero effort, high
   perceived value.
8. **"Explain like the teacher" toggle per subject** - keep the teacher's wording (default) or a plainer rewrite; pairs
   naturally with the fact-checker switch.
9. **Group study codes** - classmates on the same course share ONE digest (one model run per class instead of per student)
   with per-student plans; cuts the cloud-tier cost by the class size and is a viral loop.
10. **A "nothing missed" report per test** - the material ledger summarised per assessment ("18 items: 16 used, 1 skipped
    (archive), 1 unreachable video - replacement found"), sent the day the plan is built.

## Risky to port for all users (found while porting; all handled)

- **The homework/e-mail automation** acts in the owner's name under his explicit authorisation only - excluded from the
  export manifest (never copied), and the product's connector has no route to Moodle write actions.
- **The certain-facts rule** rewrites teacher content - a student marked by the teacher's key could lose points; shipped as
  an OFF-by-default switch with every correction listed.
- **Memory-palace / keyword hooks / acrostics** - personal preference of the owner (turned off 2026-09-12) and culturally
  specific ("a walk through your flat"); the product forces `association: false`.
- **Lithuanian-only chrome and lt/en-only content check** - generalised through chrome tables and the render adapter; the
  engine improvement (a real i18n dictionary in the hub template) is queued for the personal tool.
- **Grade scale and probability wording** - LT 1-10 assumptions replaced by per-country scales; every figure labelled an
  estimate (partner DISAGREE 3).
- **Estimated test dates from last year's school pattern** - the personal system approximates dates from the owner's
  school; the product only approximates when the user asks ("~" tag) and lets them edit.
- **The personal Google Drive live-deadline route** - replaced by the connector/API; the demo hub has the Drive query
  neutralised so it never contacts the owner's Drive.
- **Storing the school SSO session** - the personal system keeps Microsoft cookies for headless re-login; the product never
  logs in on the student's behalf (the extension only reads an already-open session).
- **GitHub Pages for a commercial SaaS** - prohibited by GitHub's terms; Pages hosts only the demo/landing, production
  front-end goes to Cloudflare Workers static assets (free).
