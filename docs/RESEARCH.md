# Research findings (2026-09-12) — what was verified and what it changed

Three research passes (Moodle access rules and market; EU/Lithuanian law; payments, trials and free hosting) plus the
architecture collaboration round with the other company's flagship (run 5d128ed9). Every claim below carries its source;
"unverified" is written where a fact could not be confirmed. §1 and §3 are from the completed passes; §2 (law) is filled
in from the legal pass in docs/LEGAL.md.

## 1. Moodle: how a third party may read a student's own account

**Token without a password (Route A).** `POST /login/token.php` with `username`, `password`, `service=moodle_mobile_app`
returns `{token, privatetoken}`; GET is refused; it sends `Access-Control-Allow-Origin: *` ([login/token.php](https://raw.githubusercontent.com/moodle/moodle/main/public/login/token.php)).
On SSO sites the official app opens `/admin/tool/mobile/launch.php?service=…&passport=<random>&urlscheme=<scheme>`; after
`require_login()` Moodle mints a token and redirects to `<scheme>://token=<base64(md5(wwwroot+passport):::token[:::privatetoken])>`
([launch.php](https://raw.githubusercontent.com/moodle/moodle/main/public/admin/tool/mobile/launch.php)). A default install
forces the scheme to `moodlemobile` (`tool_mobile/forcedurlscheme`), and a web page can never receive a custom scheme
(`registerProtocolHandler` only allows `web+`) — so the token flow needs the extension or a desktop helper, which is what
`extension/background.js` (observes the redirect) and `connector/` do. Students may mint mobile tokens themselves
(`moodle/webservice:createmobiletoken`, archetype user), tokens last 12 weeks by default, and the Security keys page
never shows the token value (so "paste your token" does not work on modern Moodle). `enablemobilewebservice = 0` (the
owner's school, measured 2026-09-08) disables both `token.php` and `launch.php` with `servicenotavailable`.

**REST is CORS-open.** `webservice/rest/server.php` sends `Access-Control-Allow-Origin: *` (MDL-47545, fixed in 2.8) and
so does `webservice/pluginfile.php`; there is no preflight handler, so calls must be `application/x-www-form-urlencoded`
([rest/locallib.php](https://raw.githubusercontent.com/moodle/moodle/main/public/webservice/rest/locallib.php)). On
mobile-service-ON sites a browser page can therefore talk to Moodle directly with the token — `collect.MoodleToken` uses
form-encoded POSTs for that reason.

**Session route (Route B) when the mobile service is OFF.** `lib/ajax/service.php` serves only functions declaring
`ajax => true`, requires a logged-in session AND a sesskey, and grants CORS only to `service-nologin.php` — so a
cross-origin web page cannot use it, an extension running in the student's own browser can. Available there:
`core_course_get_enrolled_courses_by_timeline_classification`, `core_calendar_get_action_events_by_timesort`,
`core_courseformat_get_state` (Moodle 4.x), `core_message_*`, `message_popup_get_popup_notifications`; NOT available:
`core_course_get_contents`, `mod_assign_get_assignments`, `mod_quiz_get_quizzes_by_courses`, grades — those come from
the HTML pages, exactly as the personal `tools/moodle.py` proved at the school ([external_api.php](https://raw.githubusercontent.com/moodle/moodle/main/public/lib/external/classes/external_api.php)).

**Trademark — the name may not contain "Moodle".** TRADEMARK.txt: "You can't use 'Moodle' in the name of your software
(including Mobile apps)", nor in a domain or company name or ad keywords; describing software that integrates with
Moodle™ is permitted ([TRADEMARK.txt](https://raw.githubusercontent.com/moodle/moodle/main/TRADEMARK.txt)). Hence the
working name Planas and the line "Works with Moodle™. Not affiliated with or endorsed by Moodle Pty Ltd."

**Terms.** No Moodle HQ rule forbids third-party clients — the dev docs document `login/token.php` and ship client
samples ([Creating a web service client](https://docs.moodle.org/dev/Creating_a_web_service_client)). The constraint is the
school's acceptable-use policy, which typically bans sharing passwords AND tokens and "automated use of a service intended
for human interaction" (Edinburgh, UT Austin, Purdue); the breach lands on the student. Canvas explicitly bans asking users
to generate tokens for third-party apps; Moodle does not. Design consequence: never ask for a password, never log in on
the student's behalf, tell students their school policy governs (Terms §3). No Lithuanian AUP text was obtained.

**Market.** Moodle's third-party student scene is tiny (Moodle Buddy ~6k users, Moodle Downloader ~10k, both session
extensions; moodle-dl CLI); Canvas's is huge because students self-generate tokens (BetterCampus ~2M) and has seen blocks
(a district-wide ban, Cornell and UW-Madison ending self-service tokens, mass token revocation after Instructure's 2026
breach). Paid planners syncing Moodle: Shovel 9.79 $/mo or 39 $/yr; MyStudyLife+ 4.99 $/mo; AI study tools (StudyFetch
7.99–11.99 $/mo) integrate only through institution LTI. Edinburgh never enabled the mobile service — such schools are
Route-B-only.

## 2. Law — see docs/LEGAL.md (settled points summarised there with article numbers and the practical checklist)

## 3. Payments, trials, hosting, AI (verified 2026-09-12)

**Payments (5 € ticket, Lithuanian sole trader).** Creem (Estonian MoR): 3.9 % + **0.40 $** (advertised in dollars;
≈ 0.37 € — decision review 2026-09-12 caught the currency) ≈ 0.57 € on a 5 € charge, accepts natural persons, Lithuania
supported, 24–48 h approval, 50 € payout floor ([pricing](https://www.creem.io/pricing), [countries](https://docs.creem.io/merchant-of-record/supported-countries)).
Stripe Managed Payments: files VAT in 80+ countries incl. LT, ≈ 0.54 € all-in on EEA cards, eligibility review, no custom
checkout domain ([managed payments](https://stripe.com/managed-payments)). Polar ≈ 0.78 €; Lemon Squeezy ≈ 0.80 € (status
after the Stripe acquisition only from secondary sources); Paddle: products under 10 $ "contact us", 100 € payout floor;
Gumroad 10 % + 0.50 $ ≈ 1 € on a 5 € sale; Paysera 0.9 % + 0.10–0.40 € but no MoR (we would file EU OSS VAT ourselves;
LT OSS threshold 10 000 € EU-wide, domestic VAT threshold 45 000 € per [quaderno](https://quaderno.io/guides/lithuania/vat/)).
Stripe Billing alone is 0.7 %, but VAT filing (Stripe Tax Complete) costs 80 €/month. **Recommendation: Creem first,
Stripe Managed Payments applied in parallel.**

**Trials.** Card-required trials convert 3–5× better (opt-in 8.9 % vs opt-out 31.4 %, ChartMogul/ProductLed survey, secondary)
but cut sign-ups 40–60 %; Stripe measured 6.2× more abusive trials Nov 2025→Feb 2026 ([Stripe](https://stripe.com/resources/more/free-trial-abuse)).
Free defences: Cloudflare Turnstile, MIT disposable-domain lists, ThumbmarkJS (MIT) fingerprinting, per-IP/e-mail rate
limits, one trial per verified school identity. Implemented: e-mail + Moodle-identity hash + IP cap in `api/`; card-required
trial at the MoR; Turnstile pending.

**Hosting (free, hard stop, never bills).** Cloudflare Workers 100k req/day, 10 ms CPU; KV 100k reads + 1k writes/day; D1
5 M row reads/day, 5 GB; Pages/static assets unlimited bandwidth ([limits](https://developers.cloudflare.com/workers/platform/limits/)).
GitHub Pages: public repo, 1 GB, 100 GB/month soft — and **"not intended for or allowed to be used as … providing commercial
software as a service"** ([Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits))
→ demo and landing only. Vercel Hobby forbids commercial use; Supabase Free pauses after a week idle; Render free spins down;
Fly.io has no free tier; Oracle Always Free needs a card for identity (2 OCPU/12 GB Ampere, idle reclaim after 7 days).
**Long jobs (browser, ffmpeg, whisper) fit nowhere free except an Oracle VM or public-repo GitHub Actions** — which is why
processing stays on the student's device (and the owner's PC as a worker is a later, opt-in tier).

**E-mail and push.** Resend 100/day + 3 000/month free; Brevo 300/day; Gmail app password 500/day; Mailgun free plan now
100/day; SendGrid free plan retired May 2025. Web Push (VAPID) is free; iOS needs Add to Home Screen.

**Geo-IP.** `request.cf.country` works on the Cloudflare free plan (`XX` unknown, `T1` Tor, no accuracy SLA); ip-api.com is
non-commercial only, ipapi.co bans production use ([Cloudflare](https://developers.cloudflare.com/network/ip-geolocation/)).
Implemented as `/geo` in `api/`: returns the country and a language, stores nothing.

**Extensions.** Chrome: one-time developer fee (amount not published by Google; 5 $ by community sources); Edge Add-ons free
(≤ 7 business days); Firefox AMO free (~24 h); Safari needs the 99 $/yr Apple program. Store-free installs are dead for
consumers on Chrome/Edge/Safari; Firefox self-hosted signed XPI is the only exception. → ship Edge + Firefox first.

**Local and cloud AI.** Ollama is MIT; commercially safe multilingual models: Gemma 4 (Apache 2.0), Qwen 3/3.5 (Apache
2.0), EuroLLM 9B (Apache 2.0, all 24 EU languages); Lithuanian needs ≥ 9B (Belebele LT: Gemma 2 27B 0.861 vs Phi-3 3B
0.435, [arXiv 2501.03952](https://arxiv.org/html/2501.03952v1)); ~0.6 GB VRAM per 1B at 4-bit. faster-whisper/whisper.cpp
MIT, Tesseract Apache 2.0 (`lit` pack). Cheapest capable cloud models per 1M tokens in/out: gpt-5-nano 0.05/0.40 $,
gpt-5-mini 0.25/2 $, Gemini Flash-Lite ~0.10–0.30 $ in (row disputed — recheck before budgeting), DeepSeek 0.30/1.20 $,
Claude Haiku 4.5 1/5 $; batch −50 % everywhere.

**Answer to "tokenless scanning".** Scanning, mirroring, deadlines, notifications, extraction, video frames and local
transcription need NO model tokens — they are deterministic (`collect.py`, `notify.py`, vendored `extract.py`/`video.py`).
Only the digest (ranking probable questions, writing explanations, cards, quizzes) needs a model: the free tier ships the
tokenless baseline (headings → questions, definitions → cards, figures → numbers) and Ollama on the student's PC; the paid
tier pays for a cloud model (docs/PRICING.md). Ollama is the answer for a free, private, offline digest — with the honest
caveat that Lithuanian-quality output needs a 9B+ model and a PC with ~6 GB of VRAM.
