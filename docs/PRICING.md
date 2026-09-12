# Pricing and payments (proposal, 2026-09-12; owner decides)

## Price

| Tier | Price | What is included | Our cost per user |
|---|---|---|---|
| Free (local) | 0 | The full engine on the student's own computer: calendar, notifications, material ledger, plan, baseline digest (no AI) or Ollama (their own PC). | ~0 (no server work; a few API calls for the account) |
| Plus | **4.99 €/month** or 39 €/year (tax included, shown in the buyer's currency at checkout) | Cloud digest of the material (model run on our side), web push + e-mail notifications, cross-device sync, priority support. | model spend: a 12-grade subject month is roughly 150-400k tokens of material; with a cheap capable model at 0.25-1 $/M input (docs/RESEARCH.md §7) that is 0.05-0.40 $ per subject-month, ~0.30-2 $ per student-month; plus MoR fees ~0.60 € per 5 € charge |

Why 4.99: Shovel charges 9.79 $/month for LMS sync without study content; MyStudyLife+ 4.99 $/month for a planner only
(RESEARCH §4). A student budget tolerates 5 €; below it the merchant-of-record fee (0.40 € + 3.9 %) eats the margin.
The yearly price front-loads cash and halves churn handling.

## Provider (recommendation)

**Creem** (merchant of record: they collect VAT everywhere, we invoice nobody; 3.9 % + 0.40 €; natural persons accepted;
Lithuania supported; 24-48 h approval; 50 € payout floor) - and apply to **Stripe Managed Payments** in parallel (cheaper
per EEA card, also files VAT, eligibility review). Not Paddle (products under 10 $ need a special deal, 100 € payout floor),
not Gumroad (about 20 % of a 5 € sale), not Stripe Billing alone (we would file EU OSS VAT ourselves; Stripe Tax filing
costs 80 €/month). Sources and figures: docs/RESEARCH.md §3.

## Trial

7 days, every Plus feature, **card required at the merchant of record** (3-5x fewer abusive trials; a reminder e-mail two
days before the first charge is sent by the MoR and by us). One trial per verified e-mail, one per hashed Moodle identity,
three per IP per day, Turnstile on sign-up, disposable domains refused. The Free tier stays free without a card, so a
student who does not want to enter a card still gets the product.

## Costs that need the owner's green light before they exist

Chrome Web Store developer fee (one-time, community sources say 5 $), a domain (~10 €/year), any model API key with a
spending limit, Apple Developer Program (99 $/year, only if a Safari extension is ever wanted). Everything else in the
stack is free-tier with hard stops (RESEARCH §3).
