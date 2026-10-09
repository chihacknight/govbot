# Illinois field audit — govbot-data/il-legislation vs ilga.gov

Run 2026-10-09 with `internal/il_field_audit.py` (all 12,809 bills in the 104th session; 217
bill pages on ilga.gov checked, stratified across every bill type and over time; 0 unreachable).
Raw numbers: `il_field_audit.json`; one row per bill × check: `il_field_audit.csv`.

Follow-up to a volunteer's ilga.gov scan (see `tamara-notes/state-specific/il.md`), answering its
three next steps.

## Headline

- **Recent bills missing:** expected, not a data bug. Illinois is out of session and the scrapers are paused on purpose during the migration to a new system. Our newest Illinois action is **2026-09-24**; newer bills come in once scraping resumes.
- **Basic facts are accurate:**
  - **Titles:** 217 of 217 match ilga.gov.
  - **Sponsors:** 211 of 217 match. The 6 that differ are a name variant (5) or the pause (1).
  - **Latest action:** 215 of 217 match.
  - **Public Act numbers:** 13 of 13 match.
- **Two things ilga.gov shows that we never store:**
  - **The synopsis.** ilga.gov had one for all 217 bills, and our `abstracts` is empty for every bill.
  - **The statutes a bill amends.** ilga.gov listed them for 115 of 217, and our `citations` is empty for every bill.

  The Open States `il` scraper doesn't read either one. That's the main improvement left.

## 1. Which fields are empty, and is the gap ours?

| Field | Empty in our data | On ilga.gov? (217-bill sample) | Verdict |
|---|---|---|---|
| `title` | 0% | short description; 217/217 identical | ✅ complete |
| `sponsorships` | 0% | House/Senate sponsors | ✅ complete |
| `actions` | 0% | Actions table | ✅ complete |
| `sources` | 0% | (the bill-status URL) | ✅ complete |
| `versions` (bill text) | 5.5%: all 707 appointment messages (AM) + 2 SRs | Full Text tab (not fetched) | ✅ for bills; AM text not checked |
| votes (separate `*.vote_event.*.json` files) | 4,651 bills have at least one | Votes tab | ✅ captured (only bills that reached a vote have one) |
| `documents` | 93.3% | Public Act link, fiscal/other notes | 🟡 mostly expected (only enacted bills have a Public Act) |
| **`abstracts` (synopsis)** | **100%** | **"Synopsis As Introduced" on 217/217** | ❌ **our gap** |
| **`citations` (statutes amended)** | **100%** | **"Statutes Amended" on 115/217** (the other 102 have none) | ❌ **our gap** |
| `subject` | 100% | no such field on ilga.gov | ➖ nothing to capture |
| `other_titles` | 100% | no such field | ➖ nothing to capture |
| `related_bills` | 100% | no such field | ➖ nothing to capture |

The dashboard already fills in the synopsis for its own pages (`scripts/build_il_summaries.py` reads
"SYNOPSIS AS INTRODUCED" out of each bill's PDF into `il_summaries.json`). But it isn't in the
`il-legislation` data repo itself, so anyone using the data directly doesn't get it.

## 2. What ilga.gov shows that we never capture

| ilga.gov bill page | In our data? |
|---|---|
| Synopsis As Introduced | ❌ no (`abstracts` empty) |
| Statutes Amended In Order of Appearance | ❌ no (`citations` empty) |
| Amendment synopses (16 of 217 sampled bills had them) | ❌ no (the amendment text is in `versions`, the summary isn't) |
| Public Act number | 🟡 only inside an action's text ("Public Act . . . 104-0166") and a `documents` link, not as a field |
| Effective date | 🟡 only inside an action's text ("Effective Date January 1, 2026") |
| "Chief Co-Sponsor" role | 🟡 recorded as a plain `cosponsor` (the chief/regular co-sponsor distinction is lost) |
| Witness slips tab | ❌ no (the hearings dashboard links ILGA witness slips separately) |
| Votes tab | ✅ yes, as vote-event files |
| Full Text tab | ✅ yes, `versions` |

## 3. Values that differ

| Check | Match | Differ | What the differences are |
|---|---|---|---|
| Title vs. short description | 217 | 0 | — |
| Sponsor names | 211 | 6 | 5× the same person under two names ("Dan Ugaste" in our data, "Daniel J. Ugaste" on ilga.gov); 1× HB5786: 3 co-sponsors added after the pause |
| Chief sponsor | 216 | 1 | the Ugaste name variant |
| Number of actions | 216 | 1 | HB5786: ilga.gov has 3 actions from after the pause |
| Latest action | 215 | 2 | HB5786 (pause); **HB2783**: ilga.gov's latest is a 2026-07-01 "Rule 19(b) / Re-referred to Rules Committee" we don't have, though the scraper was running in July (cause not confirmed) |
| Public Act number | 13 | 0 | — |

## Recommendations

1. **Nothing to do for the missing recent bills.** HB5817–5819, HR1037–1044 and HB5786's newer actions should arrive when scraping resumes on the new system; re-check then.
2. **Capture the synopsis and statutes upstream.** Open States' `scrapers/il/bills.py` would need to read "Synopsis As Introduced" into `abstracts` and "Statutes Amended" into `citations`. An upstream PR (like the one filed for the USA scraper) benefits every Open States user. Until then, the dashboard's PDF-based synopsis covers the website.
3. **Look at HB2783's missing July 1 action** as a one-off (re-check after the next run). If more bills show it, it points at how the scraper refreshes already-seen bills.
4. **Leave the name variants alone.** "Dan" vs "Daniel J." Ugaste is the same legislator. The site resolves sponsors by surname, so nothing on the website is affected.

## Executive Orders and Joint Session Resolutions

These are not collected, by design. The Open States `il` scraper only covers bills,
resolutions, joint resolutions, constitutional amendments and appointment messages. Executive
Orders are the Governor's orders filed for the record (not legislation), and Joint Session
Resolutions are procedural. See `tamara-notes/state-specific/il.md`.
