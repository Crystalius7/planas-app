# Launch checklist

`python product/tools/release.py finish` refuses while a MUST item below is unchecked. Tick an item only with evidence
(a URL, a screenshot in `.look/`, a test run). The OWNER items need the owner's account or green light.

## MUST

- [ ] OWNER: product name chosen (never contains "Moodle"; three candidates in the hand-over) and the brand set in `web/i18n/*.json` `app.name`, `extension/manifest.json`, `release.json`
- [ ] OWNER: merchant-of-record account approved (Creem first; Stripe Managed Payments applied in parallel) - see docs/PRICING.md
- [ ] OWNER: green light for the one-time costs that cannot be avoided (domain; Chrome Web Store fee if Chrome is wanted; Edge and Firefox are free)
- [ ] OWNER: Cloudflare account for the free Worker (api/) + KV + D1 created; `wrangler.toml` ids and origins filled; secrets set with `wrangler secret put`
- [ ] OWNER: transactional e-mail sender (Resend free tier, 100/day) verified for the domain; `MAIL_FROM` set
- [ ] Route B proved at the owner's school END TO END through the extension into the connector (engine path PROVED 2026-09-12 with the saved session: probe, 5 courses, calendar, notifications, geography mirrored 21 sections / 58 modules / 50 files / 0 errors in 17 s; `tool_mobile_get_public_config` confirms the mobile service is off there); expired-session and missing-capability paths still to test (collab consensus 2026-09-12)
- [ ] Route A proved on a Moodle site with the mobile service ON (token minted by the site, only the token stored)
- [ ] Production front-end deployed on Cloudflare Workers static assets (GitHub Pages hosts the demo only - its terms forbid commercial SaaS)
- [ ] Client-side blob encryption in the web app (AES-GCM, device-derived key) before any user blob is uploaded
- [ ] Trial protections wired end to end: e-mail verification, Moodle-identity fingerprint, IP cap, Turnstile, card-required trial at the MoR, disposable-domain list
- [ ] Billing webhook tested with the provider's test events (signature, idempotency, plan transitions incl. cancel/refund)
- [ ] Legal pages final (Terms, Privacy, AI notice) reviewed once by a Lithuanian lawyer or a legal template service; consent texts in every shipped language
- [ ] Age gate + parental consent flow for users under the country's digital-consent age (14 in Lithuania)
- [ ] Records of processing + DPIA written (minors at scale, profiling of study behaviour) - docs/LEGAL.md
- [ ] Extension published on Edge Add-ons and Firefox AMO (free); Chrome only after the fee is approved
- [ ] Engine tests green (`python product/tests/test_engine.py`) and `python product/tools/sync_engine.py --check` clean
- [ ] Every shipped page looked at (desktop + phone) after the last change; no console errors; no horizontal overflow
- [ ] Security review of api/ and extension/ by the shared review router (glance) with findings closed
- [ ] Bug-report route verified end to end (local store + hosted table)
- [ ] `release.json` url/repo/demoUrl filled by the finish command (never by hand)

## SHOULD (before marketing, not blocking the portfolio card)

- [ ] Translations reviewed by a native speaker for lt, ru, pl, de, es, fr, pt, it, uk (agent-drafted 2026-09-12)
- [ ] Web push sending (VAPID keys) and e-mail digests of new material
- [ ] Ollama local digest tested on one real course (Gemma/Qwen ≥ 9B for Lithuanian)
- [ ] Exam-archive pack for Lithuania (VBE) packaged as an optional download
- [ ] Group study codes (one digest per class) designed
