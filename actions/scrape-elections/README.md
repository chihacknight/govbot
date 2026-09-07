# scrape-elections — Illinois & Chicago elections feed

Builds the **Elections Happening in IL** dashboard feed: every office on upcoming Chicago
and Illinois ballots, with the candidates running for each.

Powers `docs/src/dashboard/elections.html`. Output validates against
`schemas/govbot.elections.schema.json`.

## What it covers

| Office group | Races | Ballot | Candidate source |
|---|---|---|---|
| Chicago citywide | Mayor, City Clerk, City Treasurer | 2027 municipal | Chicago Board of Elections |
| City Council | Alderperson, Wards 1–50 | 2027 municipal | Chicago Board of Elections |
| CPS Board | President (citywide) + Subdistricts 1A…10B | **Nov 3, 2026** | ISBE "Who Is Running" |
| Police District Council | 3 seats × 22 police districts | 2027 municipal | Chicago Board of Elections |
| Cook County / suburban / judicial / statewide | *(future)* | — | Cook County Clerk / ISBE |

## How it works — structure vs. candidates

The **race structure** (which offices/districts are on the ballot, their dates,
and a plain-English *"why this race exists"* note) is stable and lives in a
committed seed: [`elections_seed.json`](./elections_seed.json). The scrapers
only **populate candidates** into those races.

- `parse_isbe_candidates(text)` — ISBE's delimited "Who Is Running" candidate
  list (tab/pipe/space-delimited); header-driven, so column order can change.
- `parse_chicago_boe(html)` — the Chicago Board of Elections candidate-list
  HTML table; a link in the name cell is kept as the candidate website.
- `parse_cook_clerk(...)` — placeholder for suburban Cook (returns nothing until
  the seed carries those races).

A candidate is attached to a race only when its office + district resolve
**unambiguously** (`race_id_for`). Anything that can't be placed is counted and
dropped with a warning — **we never invent a race or a candidate.** A race with
no confirmed candidate keeps an empty list plus a link to its official source.

> **Best-effort live parsing.** ISBE and the Chicago BOE reshape their pages
> between cycles, so a live fetch/parse can fail. When it does, the build falls
> back to the committed seed (real structure, empty rosters) rather than
> crashing, and the parsers stay validated offline against the fixtures below.
> The exact live endpoints in `main.py` may need re-pointing against a real page
> snapshot as a cycle opens.

## Springfield side feed — "the rules of the game"

Beyond candidates, the build attaches a top-level `springfield` list: **Illinois
bills that shape how these elections work** — the elected CPS board and its
2026–27 transition, ward & runoff rules, campaign finance, school governance.
`build_springfield()` reads govbot's legislation dataset
(`--legislation docs/src/dashboard/data.json`), keeps IL bills tagged
`elections & voting` or `education`, and cross-references
`--hearings docs/src/dashboard/hearings.json` so a bill on an upcoming ILGA
committee calendar carries its hearing + witness-slip link. This is **context
beside the races, never mixed into candidate lists**. It degrades to an empty
list when the dataset is unavailable. On the deploy, `data.json` and
`hearings.json` are both built earlier in the same job, so this reads the fresh
copies.

## Campaign money — Illinois SBE (D2 filings)

Each candidate can carry a `money` summary (receipts, spending, cash on hand)
from their committee's latest **D2** filing. It uses the SBE's reliable **ID
crosswalk**, never fuzzy dollar matching:

```
our candidate name → Candidates.txt (ID) → CmteCandidateLinks (CommitteeID)
                   → Committees.txt (Name) → D2Totals (latest filing, max ID)
```

A candidate is enriched only when their normalized *First Last* resolves to
**exactly one** SBE candidate record; ambiguous names are skipped, not guessed.
Figures across multiple linked committees are summed; the committee with the most
cash on hand is shown as primary.

Because the SBE bulk files are large (~70 MB), enrichment is a **separate,
gated** step — the deploy downloads the files and runs it only when candidates
are present:

```bash
python3 actions/scrape-elections/main.py \
  --enrich-money docs/src/dashboard/elections.json --money-dir /path/to/sbe-files
```

where the directory holds `Candidates.txt`, `CmteCandidateLinks.txt`,
`Committees.txt`, and `D2Totals.txt` from
elections.il.gov/campaigndisclosuredatafiles/.

## Usage

```bash
# Live (what the Pages deploy runs):
python3 actions/scrape-elections/main.py \
  --output docs/src/dashboard/elections.json \
  --rss docs/src/dashboard/elections.xml \
  --rss-feeds-dir docs/src/dashboard/elections

# Offline, deterministic — rebuild from fixtures:
python3 actions/scrape-elections/main.py \
  --from-fixtures actions/scrape-elections/__snapshots__/raw \
  --now 2026-09-07T00:00:00Z --output -
```

## RSS

- `elections.xml` — the whole ballot, one item per race.
- `elections/group-<group>.xml` — one feed per office group (all aldermanic, all
  CPS board, …).
- `elections/springfield.xml` — the "rules of the game" IL bills (when present).
- `elections/race-<id>.xml` — one feed per race, so a resident can follow just
  their ward, their CPS subdistrict, or the mayor's race.

## Tests (offline)

```bash
python3 actions/scrape-elections/test_scrape_elections.py
```

Pure parsers run against `__snapshots__/raw/`; the whole build is diffed against
`__snapshots__/expected_elections.json`. Regenerate that snapshot after an
intentional change with `./render-snapshots.sh`, then review the diff.
