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

## Official candidates — Chicago BOE Candidate List (PDF)

The Board of Elections publishes the authoritative candidate roster only as a
**PDF** (`Candidate List_<date>.pdf`, linked from
`chicagoelections.gov/getting-ballot/candidates`). `--enrich-candidates-boe`
auto-discovers the newest one, extracts it with the `pdftotext` **system tool**
(poppler-utils — shelled out like DuckDB, so no Python dependency is added), and
merges the candidates into the matching races:

```bash
python3 actions/scrape-elections/main.py \
  --enrich-candidates-boe docs/src/dashboard/elections.json
# or point at a specific source (URL, local .pdf, or extracted .txt for testing):
#   --boe-pdf "https://…/Candidate List_20260904-1_0.pdf"
```

`parse_boe_candidate_list(text)` is a pure parser over the `pdftotext -layout`
output. A candidate is kept only when its office header **resolves to a
Chicago-seed race** (`_boe_office_race` → `race_id_for`); the statewide / federal
/ judicial / county offices on the same ballot are ignored. Two guards keep that
honest:

- `race_id_for` requires an **education signal** for the CPS board, so a generic
  "…Board president" (the **Cook County Board president**, Preckwinkle et al.)
  never resolves to the CPS president.
- `_boe_office_race` requires the word **"City"** for the treasurer/clerk, so the
  statewide *Treasurer* is never misread as the Chicago City Treasurer.

On the Nov 2026 ballot this yields exactly the CPS races (president + 20
subdistricts 1a–10b — 42 candidates). It's **forward-compatible**: when the 2027
municipal candidate list is published, the same parser will populate
mayor / alderperson wards / police district councils / city clerk & treasurer
(there's no 2027 official roster yet — filing is Nov 2026). Pure/deterministic
and offline-tested against `__snapshots__/raw/boe_candidate_list.txt` (which
includes statewide + municipal examples); only the fetch wrapper touches the
network / shells out to `pdftotext`. Fail-soft: no poppler or no PDF leaves
rosters untouched. The deploy runs this before the money step (so committees can
match) and before the feeds are rebuilt; the committed sample ships empty.

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

## Results — post-Election-Night (scaffold)

Each race can carry a `results` block (per-candidate votes, %, winner, precincts
reporting) attached from the authority's results export after Election Night —
Chicago Board of Elections, or the Cook County Clerk for suburban races. It's
**inert until results exist**: `parse_results_rows()` is header-driven (CSV/TSV)
and `attach_results()` maps rows to a race by office+district, counting **every
reported candidate** (official results are authoritative — our roster isn't).
Winners are flagged only when the source marks them; nothing is ever projected.

```bash
python3 actions/scrape-elections/main.py \
  --enrich-results docs/src/dashboard/elections.json \
  --results-file results.csv --results-url https://chicagoelections.gov/...
```

The deploy runs this only when the `ELECTION_RESULTS_URL` repo variable/secret is
set (so it does nothing before an election).

## Potential candidates — unofficial, from news coverage

Long before filing opens, outlets report who's running, exploring, or rumored.
`--enrich-potential` surfaces those names per race into a **separate**
`potential_candidates` list — a rumor/coverage signal, kept strictly apart from
the official `candidates`. They appear in the **per-race** RSS feeds as items
prefixed **`[UNOFFICIAL]`** and linked to a source article (so a rumor can't be
mistaken for a ballot record); the aggregate feeds don't carry them.

Once a name is confirmed on the official list, it **graduates out** of potential:
`build_potential` drops any name already present in that race's official
`candidates` (populated earlier by `--enrich-candidates-boe`), so a filed
candidate never double-lists as both official and "rumored." When the 2027
municipal roster publishes, each race's confirmed names move cleanly from the
amber "potential" block into the official list.

It reads **Google News' public RSS search** (an aggregator over the press — the
"internet" source; raw social-platform scraping is neither TOS-safe nor reliable,
so it's out). A name is attached **only** when a headline both:

1. names a person next to a candidacy verb (`announces` / `to run` / `enters` →
   *announced*; `mulls` / `weighing` / `rumored` → *exploring*; `candidate NAME`
   → *reported*; appointed/`confirmed as … Alderperson` or `…'s pick, NAME,` →
   *incumbent*), and
2. references the race — its office keyword, plus the **district token** for a
   district race (word-boundary matched, so "5th ward" never matches "25th ward").

For the *incumbent* (mid-term appointment) case the appointee is captured, never
the owner of the pick (e.g. the mayor) or the outgoing member (`to replace …`);
and appointment patterns run only for seat-specific district races, so a ward
appointee is never misfiled under a citywide race whose office word ("mayor") was
merely a title in the headline.

Leading honorifics are stripped (`Rep. Mike Quigley` → `Mike Quigley`) so one
person doesn't split in two, office/place/calendar words are rejected as names,
and every surfaced name carries the article(s) it came from (headline, link,
publisher, date). Nothing is invented; a name with no source is dropped.

Queries: one **pooled query per office group** for cross-cutting coverage, plus a
**per-race query for every district race** (`Chicago alderman "45th ward"
candidate 2027`, …) so each ward / CPS subdistrict / police district gets its own
coverage pool — a single pooled query can't cover 50 wards. The bigger pool never
loosens the match: the strict office + district gating is unchanged, so a name
still attaches only when a headline names the person with a candidacy verb *and*
references that race. Because of that, **most down-ballot races legitimately stay
empty** until candidates actually surface in the press (2027 filing opens Nov
2026) — the lists fill in on the twice-daily refresh as coverage grows, never by
guessing. Fully fail-soft — sources down leaves the lists empty.

```bash
python3 actions/scrape-elections/main.py \
  --enrich-potential docs/src/dashboard/elections.json
```

The deploy runs this right after the base build (independent of whether official
candidates exist yet), twice daily. The committed sample ships empty lists.

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

Every feed carries an `<?xml-stylesheet href="feed.xsl">` processing instruction
so a browser renders it as a readable page (`docs/src/dashboard/feed.xsl`) rather
than a raw XML tree; feed readers ignore it. Root feeds reference `feed.xsl`,
granular feeds `../feed.xsl` (via `_feed_xml(..., xsl_href=…)`).

## Tests (offline)

```bash
python3 actions/scrape-elections/test_scrape_elections.py
```

Pure parsers run against `__snapshots__/raw/`; the whole build is diffed against
`__snapshots__/expected_elections.json`. Regenerate that snapshot after an
intentional change with `./render-snapshots.sh`, then review the diff.
