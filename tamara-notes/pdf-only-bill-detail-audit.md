# PDF-Only States — What Bill Detail Does the Scraper Give Us?

Last run: **2026-09-30** · Script: [`pdf-only-bill-detail-audit.py`](pdf-only-bill-detail-audit.py) (re-runnable, ~30s)

Companion to [`archived_docs/bill-format-audit.md`](archived_docs/bill-format-audit.md), which found 28 states whose
bill **text** is PDF-only. This audit asks: without opening the PDF, what structured "about the bill" detail is in
the scraped JSON (`govbot-openstates-scrapers/{st}-legislation`, `_data/{st}/bill_*.json`)?

## Method

- Random sample of 300 bill files per state (all files if fewer), fixed seed.
- Kept only **substantive bills**: `classification == ["bill"]` (drops resolutions, memorials, joint assemblies
  like VT JRS 43) and titles not matching procedural patterns (rules, adjourn, honoring, congratulating,
  designating a day/week, per diem, legislative expenses, …). "n" below is what survived.
- Numbers are **% of substantive bills where the field is non-empty**.

## TL;DR

- **Your hunch is right about `extras`: it holds no description of the bill in any state.** Where it's populated it's
  IDs and bookkeeping: `AL_BILL_ID`, `BDR` (KY/NV), `guid` (GA), `ld_number` (ME), `date_effective` (MD),
  `effective_date`/`chapter` (WY), `NE_REF_COM` (NE referral committee), and `scrape_warnings` (FL).
- **`abstracts` is the field that matters, and 10 of 28 PDF-only states have a real plain-language summary in it:**
  CO, FL, GA, IN, KY, MO (38%), ND, OR, RI, WY.
- Two states only look like they have abstracts: **AL**'s "abstract" is just a subject label (avg 18 chars, e.g.
  "Crimes & Offenses"), and **MA**'s is filing boilerplate ("By Representative X of Y, a petition…").
- **Many states without abstracts link a short summary document instead.** It's usually a PDF, but short and
  plain-language, so it's a much cheaper extraction target than the full bill text: LA *Digest*, ID *Statement of
  Purpose*, NE *Statement of Intent*, CT *Bill Analysis*, MD *Fiscal and Policy Note*, MO *Bill Summary*,
  WY *Bill Digest*.
- **Title only, nothing else:** GU, MP, VI, VT, MA, DC, OK, NV. These need the bill PDF itself.

## Field Coverage (% of substantive bills)

| St | n | abstracts | subject | extras | other_titles | documents | citations | related | sponsors | avg actions | avg title len |
|----|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| AL | 206 | 100* | 100 | 100 | 0 | 62 | 0 | 20 | 100 | 12.5 | 127 |
| CO | 287 | 93 | 98 | 0 | 0 | 94 | 65 | 0 | 100 | 11.1 | 42 |
| CT | 259 | 0 | 100 | 0 | 0 | 63 | 0 | 0 | 85 | 9.1 | 99 |
| DC | 125 | 0 | 0 | 14 | 0 | 69 | 0 | 0 | 100 | 7.3 | 72 |
| FL | 272 | 100 | 100† | 77 | 0 | 50 | 71 | 0 | 100 | 14.0 | 38 |
| GA | 100 | 100 | 10 | 100 | 0 | 0 | 1 | 0 | 100 | 8.2 | 73 |
| GU | 299 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 98 | 0.0 | 254 |
| IA | 241 | 0 | 100 | 0 | 0 | 19 | 14 | 0 | 100 | 6.4 | 149 |
| ID | 263 | 0 | 100 | 0 | 100 | 100 | 50 | 0 | 100 | 11.1 | 136 |
| IN | 249 | 100 | 100 | 0 | 0 | 100 | 0 | 0 | 98 | 8.6 | 30 |
| KY | 222 | 97 | 97 | 100 | 0 | 41 | 0 | 0 | **0** | 7.6 | 54 |
| LA | 205 | 0 | 0 | 0 | 0 | 99 | 0 | 0 | 100 | 14.1 | 111 |
| MA | 243 | 90* | 0 | 0 | 0 | 0 | 0 | 85 | 99 | 6.4 | 78 |
| MD | 299 | 0 | 3 | 98 | 0 | 96 | 0 | 68 | 100 | 8.7 | 80 |
| ME | 277 | 0 | 97 | 98 | 0 | 78 | 0 | 0 | 97 | 18.6 | 97 |
| MO | 292 | 38 | 58 | 38 | 100 | 63 | 0 | 0 | 100 | 8.6 | 84 |
| MP | 215 | 0 | 0 | 0 | 0 | 0 | 7 | 0 | 100 | 2.8 | 155 |
| NC | 296 | 0 | 100 | 0 | 0 | 0 | 0 | 0 | 100 | 8.4 | 38 |
| ND | 279 | 88 | 0 | 0 | 0 | 52 | 0 | 0 | 100 | 13.6 | 256 |
| NE | 223 | 0 | 0 | 93 | 0 | 96 | 0 | 0 | 100 | 11.7 | 105 |
| NV | 24 | 0 | 0 | 100 | 100 | 62 | 0 | 0 | 100 | 5.5 | 83 |
| OK | 289 | 0 | 0 | 0 | 0 | 42 | 0 | 0 | 100 | 10.0 | 118 |
| OR | 282 | 100 | 0 | 0 | 0 | 61 | 0 | 0 | 56 | 13.0 | 60 |
| RI | 248 | 100 | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 5.7 | 83 |
| TN | 160 | 0 | 100 | 0 | 0 | 89 | 0 | 98 | 100 | 14.0 | 348 |
| VI | 127 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 93 | 4.6 | 231 |
| VT | 221 | 0 | 0 | 0 | 0 | 100 | 0 | 0 | 100 | 8.4 | 74 |
| WY | 300 | 100 | 0 | 100 | 100 | 100 | 0 | 0 | 100 | 11.2 | 40 |

\* Not a real summary: AL = subject label, MA = petition boilerplate.
† FL's top "subject" is the literal string `"subject index"` (182 bills), which is scraper noise.

## State Tiers

**Tier 1: real plain-language summary in `abstracts` (usable now, no PDF needed)**

| St | Abstract note | Avg len | Example |
|----|---|--:|---|
| CO | summary | 1444 | "On or before December 1, 2026, … the act requires each transportation broker…" |
| MO | abstract (38% of bills) | 1503 | "SS/SB 917 - This act creates provisions relating to a post-consumer paint recycling program…" |
| IN | Digest | 651 | "Makes wearing a mask at a public assembly a Class C misdemeanor…" |
| KY | Summary of Original Version | 579 | "Direct local school districts to provide a one-time payment of $2,000…" |
| OR | summary | 574 | "Allows the City of Eugene to annex noncontiguous land…" |
| GA | description (long title) | 857 | "A BILL to be entitled an Act to provide a homestead exemption from Walker County…" |
| FL | (short + summary) | — | "Medical Debt; Defining the terms 'medical debt collector'…" |
| RI | summary | 173 | "Creates a new category of residential solar energy generation…" |
| ND | summary | 153 | "Relating to employee leave for rest and worship; and to provide a penalty." (closer to a long title) |
| WY | (long title) | — | "AN ACT relating to corporations…; modifying the duties of registered agents…" |

**Tier 2: no abstract, but a summary-type document is linked (extract this short PDF instead of the bill)**

| St | Document | Coverage |
|----|---|---|
| ID | Statement of Purpose / Fiscal Note | 100% |
| NE | Statement of Intent (+ Committee Statement) | ~93% |
| LA | Digest (Original / Engrossed / Resume) | ~70%+ |
| CT | Bill Analysis for File Copy | ~68% (the bills that got out of committee) |
| MD | Fiscal and Policy Note | ~96% |
| MO | Bill Summary (Introduced) | ~59% (fills MO's abstract gap) |
| TN | Fiscal Note (title itself is a long summary: "As enacted, revises present law relative to constables…") | 89% |

**Tier 3: title + subject tags only** (subject gives a topic but nothing describes what the bill does)
AL, IA, ME, NC. TN and ID titles are fairly descriptive. LA titles carry a topic prefix ("SCHOOLS: Provides for…").

**Tier 4: title only.** These need the bill PDF.
GU, MP, VI (territories, no subjects, no documents), VT (docs are only witness lists and meeting pages),
MA (abstract is boilerplate), DC, OK (committee reports only), NV.

## Other Findings / Scraper Quirks

- **KY: 0% sponsorships** on substantive bills, which looks like a scraper bug worth filing upstream.
- **OR: sponsors on only 56%** of bills.
- **GU: 0 actions** on every bill, so there's no history at all.
- **FL `subject`**: contains the junk value `"subject index"` and `"(vetoed)"`.
- **CT / KY / TN** document links have an empty `media_type` (they are still PDFs).
- **VT** documents are HTML, but just witness lists and meeting schedules, nothing about bill content.

## Caveats

- **GA**: only the `2026_ss` special session is in the repo (100 bills, mostly local homestead-tax bills), so it's not
  representative of a regular session.
- **NV**: only 24 bills (36th Special Session).
- The procedural filter is keyword-based, so some non-policy items slip through (e.g. DC contract modifications).
- Coverage is from a sample of ≤300 per state; percentages are approximate.

## Spot-Check: What Does the Official Site Have That the Scraper Misses?

One sample bill per weak state, checked against the legislature's own bill page (2026-09-30).

| St | Sample bill | Scraper is missing… | Where it lives |
|----|---|---|---|
| **MA** | H2294 | **Full bill text as HTML**, so MA isn't actually PDF-only. The scraper only links `H2294.pdf`. | `malegislature.gov/Bills/194/H2294/House/Bill/Text` |
| **NV** | SB4 (36th Special) | Long title ("AN ACT relating to state financial administration; making supplemental appropriations…"), a **Digest** field (empty on this special-session bill; regular-session bills normally have the Legislative Counsel's Digest), and fiscal-effect flags ("Effect on Local Government: No / Effect on the State: …"). The scraper stores only the short summary as the title. | NELIS overview AJAX: `/App/NELIS/REL/{session}/Bill/FillSelectedBillTab?selectedTab=Overview&billKey={id}` |
| **OK** | HB1025 | A **Bill Summary PDF** with a plain-language "Fiscal Analysis" paragraph ("HB1025 creates in the State Treasury … the Prison Rodeo Revolving Fund…"). The scraper collects committee reports but not this. | `cf_pdf/{session} SUPPORT DOCUMENTS/BILLSUM/{House\|Senate}/{BILL} INT BILLSUM.PDF`, listed on the BillInfo page under "Bill Summaries/Fiscal Impact" |
| **GU** | B 276-38 | **All actions and documents.** The bill list links Referral, Fiscal Note Request, Fiscal Note (waiver), Committee Report and a Status PDF, but the scraper has 0 actions / 0 documents on every GU bill. The links have no dates; dates live in the Status PDF. | `guamlegislature.gov/bills-page3/` row → `Committee_Reports_38th/CR Bill No. …pdf`, `Fiscal_Notes_38th/…`, `Bill_History_38th/STATUS …pdf` |
| **VT** | H.724 | Nothing extra on the status page. But **every introduced bill PDF opens with "Statement of purpose of bill as introduced: This bill proposes to…"**, a 1–3 sentence summary on page 1 that's easy to extract. | First page of the "As Introduced" PDF the scraper already links |
| **MP** | SB 24-67 | Nothing. The site itself only has subject/title, author, date and empty status fields. Sparse at the source, not a scraper gap. | — |
| **DC** | B26-0006 | Not verified. The LIMS site is a JS app and `LegislationDetails` returns `401 Valid Access Token required`. The scraper uses the bulk API; worth checking whether the API has a synopsis field the scraper drops. | LIMS API (token) |
| **VI, AL** | — | Not verified (JS-app sites). AL's "abstract" being a subject label (`note: "full subject"`) is likely a mislabel in the scraper. | — |

**Takeaways:**
- **MA:** the bill text is machine-readable HTML. Small upstream fix: add the `/Bill/Text` link as an HTML version.
- **NV, OK, GU:** the scraper is leaving real data on the table. These are good upstream issue/PR candidates
  (see `reference-openstates-contrib`).
- **VT:** no scraper change needed. Extracting the "Statement of purpose" from page 1 of the PDF we already
  link works like `build_il_summaries.py`'s synopsis extraction.
- **MP:** sparse at the source; only the PDF itself will help.

## Suggested Next Step

Before building full-bill PDF extraction, use the existing **`abstracts`** (Tier 1) and target the **short summary
PDFs** (Tier 2). That covers about 17 of 28 states with much less parsing than the full bill text, the same idea as
`scripts/build_il_summaries.py`, which pulls only the synopsis.
