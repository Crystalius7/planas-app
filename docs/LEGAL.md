# Law: what applies and what it changes (research 2026-09-12, not legal advice)

Legend: **[S]** settled law · **[I]** inference · **[U]** unverified. Sources were fetched 2026-09-12; article numbers as
cited. A Lithuanian lawyer reviews this once before the first subscription is sold (LAUNCH-CHECKLIST).

## 1. Data protection (GDPR + Lithuanian Law No XIII-1426)

- **Basis [S]:** Art 6(1)(b) — performing the contract with the student — covers reading their Moodle for them, building the
  plan and service notifications. Marketing e-mail needs ePrivacy consent; using content to train models would need its
  own basis (we do not).
- **Age [S]:** Lithuania's digital-consent age is **14** (Art 8(1) derogation) ([Lex Mundi](https://www.lexmundi.com/guides/data-privacy-guide/jurisdictions/europe/lithuania/)).
  **[I]** Art 8 formally bites only for consent-based processing, but capacity to contract (§6) and regulator expectations
  mean: under 14 → parental consent with reasonable verification (Art 8(2)). → age gate + parent e-mail (SECURITY §3).
- **DPIA [S/I]:** Art 35 with the WP248 criteria — vulnerable subjects (children), evaluation/scoring, large scale, innovative
  technology; two suffice, so a DPIA is effectively mandatory; VDAI's Art 35(4) list names innovative technology + vulnerable
  subjects ([EDPB register](https://www.edpb.europa.eu/our-work-tools/consistency-findings/register-decisions/2019/lithuania-sas-list-kind-processing_en)). → LAUNCH-CHECKLIST MUST.
- **DPO [I]:** Art 37(1)(b) only if large-scale systematic monitoring is a core activity; at pilot scale probably not —
  document the assessment.
- **Records [S]:** Art 30(5)'s small-company exemption does not apply (processing is not occasional and concerns
  children) → keep a record of processing. No registration with VDAI exists. Breach: Art 33 (VDAI, 72 h), Art 34 (users).
- **Transfers [S]:** the EU–US Data Privacy Framework stands (General Court dismissed *Latombe* on 3 Sep 2025, appeal
  pending) ([IAPP](https://iapp.org/news/a/european-general-court-dismisses-latombe-challenge-upholds-eu-us-data-privacy-framework));
  Cloudflare relies on DPF with SCCs as fallback. **[U]** GitHub's transfer mechanism not checked (GitHub holds only code
  and the demo, no user data).

## 2. Copyright (ATGTĮ, InfoSoc 2001/29, DSM 2019/790)

- **[S]** ATGTĮ **Art 20**: a natural person may make one copy of a published work for personal use without commercial
  purpose (= InfoSoc Art 5(2)(b)); **Art 29** = transient copies (Art 5(1)) ([infolex](https://www.infolex.lt/ta/23542:str20)).
- **[I] The central risk:** Art 20 is the *student's* privilege. Copies made by OUR server would be our commercial
  reproductions — "one copy", "no commercial purpose", "natural person" all fail; Art 29 covers transit, not a mirror.
- **[S]** DSM Art 4 / ATGTĮ Art 22² allows commercial text-and-data mining on lawfully accessible works unless rights are
  reserved (machine-readable for online content); it legitimises the input copy only. **[I]** Outputs infringe only where
  protected expression is recognisably reproduced; facts and restructured ideas are not protected — a factual summary is
  normally fine, a reproduced slide is not.
- **Design consequence (implemented):** collection in the student's browser; source files stay on the student's device;
  the server keeps only derived data; no pooling of one teacher's material across students; delete on cancellation;
  honour TDM reservations; a takedown channel (the bug/feedback route until a dedicated address exists).

## 3. EU AI Act (Reg. 2024/1689, as amended by the 2026 omnibus)

- **[S]** Annex III(3)(b) covers systems that evaluate learning outcomes or steer the learning process **in educational
  institutions**; the draft Commission guidelines read "institutions" broadly ([Annex III](https://artificialintelligenceact.eu/annex/3/)).
  **[I]** A consumer tool bought by the student and not deployed by a school arguably sits outside, and Art 6(3) exempts
  narrow preparatory tasks — genuinely uncertain; the largest regulatory exposure. Never sell to schools for grading; never
  build proctoring (Annex III(3)(d)).
- **[S] Timing:** the Digital Omnibus (Reg. (EU) 2026/1744, in force 27 Jul 2026) moved stand-alone Annex III duties to
  **2 Dec 2027**; **Art 50 transparency applies from 2 Aug 2026** → shipped as web/legal/ai.html. As a GPAI *deployer* we
  carry no provider duties (Arts 51–56).

## 4. Consumer law

- **[S]** CRD 2011/83: Art 6(1) pre-contractual information, Art 8(2) an order button that says "order with obligation to
  pay", Art 8(7) confirmation on a durable medium; Art 16(m) removes withdrawal only with express prior consent +
  acknowledgement + confirmation (strictly construed, C-641/19) → Terms §6.
- **[S] New:** Directive (EU) 2023/2673 inserted **Art 11a — a withdrawal (cancel) function** for online distance contracts,
  applicable from **19 June 2026** → a "cancel subscription" function in the app, not only at the merchant of record.
  Lithuania: CK 6.228¹⁰, 6.228¹². The Digital Fairness Act (renewal reminders, trial-conversion consent) is still a
  proposal — we send the pre-charge reminder voluntarily.
- **[S]** Unfair Terms Directive 93/13 Annex 1(a)–(b): no exclusion of liability for death/personal injury, no gutting of
  statutory rights. **[I] Enforceable wording:** "no guarantee of any grade or result" (defines the service rather than
  excluding liability); exclude indirect/consequential loss; cap at 12 months' fees; preserve statutory rights and
  liability for intent and gross negligence → Terms §4 and §9.
- **[S]** Digital Content Directive 2019/770 Arts 6–8: objective conformity and update duties that cannot be waived;
  Art 12(2) puts the burden of proof on us during continuous supply.

## 5. Selling from Lithuania

- **[S]** *Individuali veikla pagal pažymą* carries unlimited personal liability; a **mažoji bendrija (MB)** ring-fences it;
  the 2026 break-even is roughly 25–30 k€ profit ([15min](https://www.15min.lt/verslas/naujiena/finansai/buhalteriu-ir-auditoriu-asociacija-lietuva-skatina-keisti-individualia-veikla-pereinant-prie-mazosios-bendrijos-662-2479830)).
  **Recommendation:** an MB before taking minors' money — the owner decides.
- **[S] VAT:** VMI states the domestic threshold is **45 000 €** per calendar year (since 1 May 2025) ([VMI](https://www.vmi.lt/evmi/kada-atsiranda-prievole-registruotis-pvm-moketoju-));
  **[U]** trade press reports 60 000 € from 2026 — confirm with VMI. Cross-border B2C digital services: above 10 000 €
  EU-wide the customer's Member State rate applies through OSS. **A merchant of record is the legal seller and absorbs VAT**
  — the reason for the payments recommendation. SAF-T only on request above ~300 k€; i.SAF only if VAT-registered.
  **[U]** invoice requisites for individuali veikla not read in full.

## 6. Minors as buyers, marketing

- **[S]** CK **Art 2.8**: 14–18-year-olds contract with parental consent; independently only small everyday transactions
  and their own earnings; unconsented transactions can be cured by later approval. **[I]** A card subscription is rarely
  "own earnings" → **contract with the adult payer** (Terms §2, §6).
- **[S]** UCPD Annex I point 28 bans direct exhortations to children to buy; Lithuania's Law on the Protection of Minors
  extends its restrictions to advertising. **[U]** Advertising Law Art 8 wording not retrieved. → no "buy now" copy aimed at
  children; the landing page addresses the student's planning, prices are shown neutrally.

## 7. Moodle and the school

- **[S]** The school is the controller of its Moodle. **[I]** With the student's own access we are a separate controller —
  no Art 28 processor agreement with the school. Art 20 portability covers only data the student provided, not teacher
  materials (Art 20(4)). The real exposure is the school's acceptable-use policy on credential sharing and automated
  access — contract risk on the student's side, not GDPR; a browser extension in the student's own session is materially
  safer than any stored-credential login (RESEARCH §1).

## Practical checklist (folded into LAUNCH-CHECKLIST.md)

1. MB, not individuali veikla, before taking minors' money (owner decision).
2. DPIA and a record of processing before launch; age gate at 14, parental consent below.
3. Contract with the adult payer; child-friendly privacy notice (Arts 12/13).
4. Files stay on the student's device; the server stores derived units only.
5. Delete on cancellation; publish retention periods and a takedown channel.
6. Never sell to schools for grading; never build proctoring.
7. Art 50 AI disclosure now (done); diary the Annex III review for Dec 2027.
8. Art 11a cancel function (applies since 19 June 2026), Art 8(2) order-button wording, Art 8(7) confirmation e-mail.
9. Keep the 14-day withdrawal for trial users; pre-charge reminder.
10. Merchant of record first; otherwise watch the 10 000 € OSS and the 45 000 € (possibly 60 000 €) thresholds.
