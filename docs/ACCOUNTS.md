# Accounts and setup (owner 2026-09-13: free accounts approved; one shared domain later; no Chrome fee yet)

Everything here is free-tier with a hard stop. The owner creates the accounts (they need his e-mail and login); the agent
fills the configs and deploys. Nothing below enters a payment method.

## 1. Cloudflare (the hosted API + later the production front-end)
1. Sign up at dash.cloudflare.com (free plan, no card). Then in a terminal in `product/api/`:
   ```
   npx wrangler login
   npx wrangler kv namespace create KV            # paste the id into wrangler.toml [[kv_namespaces]]
   npx wrangler d1 create planas                  # paste the id into wrangler.toml [[d1_databases]]
   npx wrangler d1 execute planas --file=schema.sql
   npx wrangler secret put ACCESS_SECRET          # 32+ random chars: python -c "import secrets;print(secrets.token_hex(32))"
   npx wrangler secret put RESEND_KEY             # from step 2
   npx wrangler secret put BILLING_WEBHOOK_SECRET # from step 3
   npx wrangler deploy                            # prints https://planas-api.<account>.workers.dev
   ```
2. Put the worker origin into `wrangler.toml` `API_ORIGIN`, the app origin(s) into `APP_ORIGIN`/`APP_ORIGINS`, and set
   `data-api="https://planas-api.<account>.workers.dev"` on the `<html>` tag of `web/app/index.html` so `/geo` and sign-in work.
3. Free limits: 100 000 requests/day, KV 1 000 writes/day (≈ sign-ins/day), D1 5 M row reads/day. Over the limit = errors,
   never a bill. The production front-end later: Workers static assets (`wrangler.toml` `[assets] directory = "../web"`).

## 2. Resend (magic-link e-mails)
Sign up at resend.com (free: 100 e-mails/day, 3 000/month). Until the shared domain exists, sending works only from
`onboarding@resend.dev` to the owner's own address (Resend's rule for unverified domains) - enough for the pilot with the
owner as the first user. After the domain: add it in Resend, set the DNS records in Cloudflare, put `MAIL_FROM` in
`wrangler.toml`.

## 3. Payments - Creem first, Stripe Managed Payments in parallel (owner 2026-09-13)
- **Creem** (creem.io): sign up as an individual (natural persons accepted), Lithuania, IBAN for payouts; approval 24-48 h.
  Create ONE product "Plus" with two prices (4.99 €/month, 39 €/year), a 7-day trial that requires a card; copy the
  checkout links into `web/app/app.js` (`CHECKOUT` constants, to be added on connect) and the webhook URL
  `https://planas-api.<account>.workers.dev/billing/webhook` with its signing secret → `BILLING_WEBHOOK_SECRET`.
  Fees: 3.9 % + 0.40 $ per charge; payout floor 50 €.
- **Stripe Managed Payments** (stripe.com/managed-payments): apply with the same business details; eligibility review;
  when approved, the same product + trial; its webhook goes to the same route (the handler reads either signature header).
- Never Stripe Tax Complete (80 €/month) and never Paddle at this price point (docs/PRICING.md).

## 4. Extension stores (free)
- **Microsoft Edge Add-ons**: partner.microsoft.com → Edge extensions → free developer account; upload `product/extension/`
  as a zip; review ≤ 7 business days.
- **Firefox AMO**: addons.mozilla.org developer hub → free; upload the same zip (the `browser_specific_settings.gecko.id`
  must be a real e-mail-like id before submission - set it when the name is final); review usually ~1 day.
- **Chrome Web Store: not necessary for the pilot.** Chrome cannot install an unpacked extension for ordinary users, so
  Chrome-only students would wait; Edge is Chromium and installs the same build. When the first Chrome-only student asks,
  the one-time developer fee (community sources: 5 $) is the whole cost - the owner's green light then.

## 5. Domain (later, shared with the portfolio site)
Build without one: the demo stays on GitHub Pages, the API on workers.dev. When the owner buys the shared domain:
`app.<domain>` → Workers static assets, `api.<domain>` → the worker route, `MAIL_FROM` on the domain, `APP_ORIGINS` and
`API_ORIGIN` updated, `DEFAULT_ORIGINS` in `connector/server.py` extended with the new origin, Terms/Privacy addresses
filled in. Nothing else moves.

## 6. What the agent does the moment the accounts exist
Fill the ids and origins, deploy, run the smoke (`/geo`, `/auth/start` to the owner's e-mail, `/me`), wire the checkout
links, test the webhook with the provider's test event, tick the checklist lines, commit.
