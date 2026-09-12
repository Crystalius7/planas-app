# Security and privacy model (v1, 2026-09-12)

Owner's bar: "privacy, no sensitive info escaping (mine too) and cybersecurity, especially for payments is on the highest
level possible." The design principle that delivers it: **the sensitive things never exist on our side.**

## 1. What we never hold

| Thing | Where it lives | Why we never see it |
|---|---|---|
| Moodle password | The student's browser / the school's own login page | The extension reads the logged-in session; the password route posts to the SCHOOL's `login/token.php` from the student's device and keeps only the token. Our API has no route that accepts a password. |
| Moodle session cookies, sesskey, web-service token | The student's device (connector `secrets/moodle.json`, file mode 0600; or the extension's own storage) | The hosted API has no field for them; the connector serves 127.0.0.1 only. |
| Course files, teacher materials, video frames, transcripts | The student's workspace folder on their computer | Copyright: private study copies stay private (docs/RESEARCH.md §2). Remote processing is OFF (`ENABLE_JOBS=0`) until the pilot proves the boundary; when it comes it is opt-in, described explicitly, and never a silent default (collab 2026-09-12, partner DISAGREE 2). |
| Card numbers | The merchant of record's checkout page | We integrate a hosted checkout (Creem / Stripe Managed Payments per docs/RESEARCH.md §3). No card data touches our pages or servers; we receive signed webhook events only. |
| The owner's own data | His personal workspace (`../study`, `../courses`, `../secrets`) | The product folder is a separate git repository; `.gitignore` excludes every workspace path, `secscan.ps1` runs on every turn, and the engine export manifest allowlists files - it never copies secrets, study content or the tools that act in his name. |

## 2. What the hosted API holds (Cloudflare Worker, free plan)

Accounts (e-mail, plan, trial dates), a hashed Moodle identity used only as a trial-abuse signal, per-user **ciphertext**
blobs (the web app encrypts plan/progress/settings with AES-GCM under a key derived on the device before upload; the
server cannot read them), bug reports (free text the user typed), push subscriptions, and the job table (empty while jobs
are disabled). D1 schema: `api/schema.sql`.

Provider limits and what happens at the limit (partner IMPROVE 5): Workers 100k requests/day and 10 ms CPU - requests
fail with 429/1015, nothing is billed; KV 1k writes/day - writes fail, reads continue (sessions and magic links are KV
writes: at most ~1000 sign-ins a day on the free plan, which is the signal to move up); D1 5 M row reads/day, 5 GB; Resend
100 e-mails/day (magic links) - a 101st sign-in that day waits for tomorrow, and the page says so. Nothing in this stack
converts a limit into a bill (owner hard rule: zero spend without a green light).

## 3. Controls

- **Transport:** HTTPS only; HSTS; `SameSite=Lax; HttpOnly; Secure` session cookie signed with HMAC-SHA256; CSRF is
  limited by CORS allow-list + credentials mode + JSON bodies.
- **CSP on every page:** `default-src 'self'`, no inline scripts, connect-src limited to the connector and the API, no
  third-party scripts or fonts at all. The landing page has no JavaScript.
- **Auth:** magic links (15-minute single-use tokens), no passwords of our own to leak; rate limits per IP and per e-mail;
  disposable e-mail domains refused for trials.
- **Payments:** hosted checkout at the merchant of record; webhooks verified with a shared secret (timing-safe compare) and
  made idempotent by event id; plan state only ever derives from verified events.
- **Trial abuse:** one trial per verified e-mail AND per hashed Moodle identity, per-IP daily cap, Turnstile on sign-up
  (free), card-required trial through the merchant of record (docs/RESEARCH.md §3: 3-5x fewer abusive trials).
- **Extension:** MV3; host permission requested per Moodle site by the student at first use (optional_host_permissions),
  no remote code, no third-party endpoints, posts only to 127.0.0.1; token capture only OBSERVES the site's own launch
  redirect and never initiates a login.
- **Connector:** binds 127.0.0.1 only; CORS origin allow-list; request bodies capped; never logs bodies; credentials file
  mode 0600.
- **Secrets hygiene:** `secscan.ps1` (shared) runs on every turn in this workspace; the repo has no `.env`; `wrangler.toml`
  carries placeholders only; secrets go in through `wrangler secret put`.
- **Deletion:** `/account/delete` removes the account, blobs and push subscriptions in one batch; local data is a folder
  the student can delete; backups: D1 point-in-time recovery keeps 30 days on the free plan - the privacy policy says so.
- **Minors:** the age gate asks the year of birth; under the country's digital-consent age (14 in Lithuania) the sign-up
  asks for a parent's e-mail and sends the consent link there (docs/RESEARCH.md §1). No profiling, no ads, no tracking.
- **Telemetry:** off by default; when the user opts in, only event names, counts and error classes - never content, names,
  school, grades or Moodle identity - and the switch is one click to turn off (owner 2026-09-12).

## 4. Threats considered

| Threat | Mitigation |
|---|---|
| Our API is breached | Nothing usable is there: no credentials, no course files, blobs are ciphertext, e-mails are the only personal data. |
| Extension is compromised through the store | Reviewed store builds only; the extension has no update channel of its own; host permissions are per site; it talks only to 127.0.0.1. |
| A student's PC is compromised | Out of our control; the connector's token file is 0600 and the token is revocable in Moodle (Security keys page). |
| Trial farming | e-mail + Moodle identity + IP + card-required trial + Turnstile; each is one signal, none is proof (partner IMPROVE 4). |
| Webhook forgery | Signature check, idempotency, plan derived from verified events only. |
| Cross-tenant data access | Every blob/job query is scoped by the session's user id; no admin route exists in v1. |
| School objects to automated access | We use the student's own session or the school's own mobile-app token, the same paths the official app uses; students are told their school policy governs (RESEARCH §1). |

## 5. What is NOT done yet (honest list)

Client-side blob encryption in the web app (the API stores what it gets; the encryption helper is next), Turnstile wiring,
the age gate UI, the parent-consent mail, web push sending (subscriptions are stored; the sender needs VAPID keys), a
penetration test before launch, and the DPIA document (RESEARCH §1 says one is prudent for minors at scale).
