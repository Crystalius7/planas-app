# Portfolio automation (owner 2026-09-12)

> "we will add this to our portfolio website only when we finish this product, add automatically there once we finish,
> it will be clickable and will lead to this product."

The portfolio site belongs to the Lojalumas workspace (`tools/portfolio/projects.json` → `portfolio-build.js` →
`public/portfolio/` → `https://projektai777.github.io/portfolio/`). Its feed follows client income; a product entry is a
manual entry. A foreign workspace is never edited from here (shared rule 2026-09-08), so the hand-off is automatic but
travels through the broadcast channel every agent already watches:

1. `python product/tools/release.py finish --url <app> --repo <github>` - refuses while `docs/LAUNCH-CHECKLIST.md` has an
   unchecked MUST item; otherwise sets `release.json finished:true`, writes `product/portfolio-entry.json` in the feed's
   own shape (`status: done`, `category: ai`, `product: true`, lt/en/ru title + summary, `url`, `since`) and drops
   `~\.claude\broadcast\notices\<date>-planas-portfolio.md` with `SCOPE: ALL`.
2. Every workspace prints `BROADCAST (unapplied ...)` on its next prompt; all ack at once except Lojalumas, whose agent
   copies the entry into `projects.json` (with a `manual: true` guard so the income-driven sync never drops it), makes the
   card link to the app, rebuilds, verifies, looks, and publishes through its autosync. Then acks.
3. `release.py status` shows what is still unchecked; nothing reaches the portfolio before that.

The card text is written to fit the portfolio's copy rules (first person singular elsewhere is untouched; the product card
may be named and linked because the owner asked for exactly that).
