# CLAUDE.md

This file provides senior engineering-level guidance for Claude Code when working on this codebase.

## Project Overview

This is **govbot** - a monorepo for distributed data analysis of government updates. Git repos function as datasets, including legislation from 47+ states/jurisdictions. The `actions/` folder contains self-contained modules that can run as shell scripts or GitHub Actions.

**AI-readable catalog access**: `llms.txt` (repo root) is a plain-language guide that
teaches any AI assistant to read the `govbot-data/{code}-legislation` catalogs directly
over HTTPS — no CLI, phone-friendly — and `catalog.json` (repo root) is the
machine-readable directory of every jurisdiction repo plus the bill path pattern. Keep
both in sync with the real data layout (the authoritative per-repo pattern lives in each
repo's own `data.json`); the README's "Read it from an AI assistant" section links them.

## Senior Engineering Prompts

Use these meta-prompts to guide architectural decisions and code quality.

### Architecture & Design

- **"What are the second-order effects of this change?"** - Before implementing, consider how changes propagate through the system. Changes to schemas affect downstream consumers. Changes to data formats affect all pipelines.

- **"Does this belong here, or does it belong closer to the data?"** - Prefer transformations at the source. If scraping logic can filter data early, don't defer filtering to format/extract stages.

- **"What's the failure mode?"** - For every external dependency (APIs, file systems, network), define what happens when it fails. Government data sources are notoriously unreliable.

- **"Can this run without network access?"** - Prioritize offline-first design. Snapshots exist for a reason - they enable testing and development without live data.

### Code Quality

- **"Would this work in a fresh clone?"** - No implicit state. All dependencies must be explicitly declared. All paths must be relative or configurable.

- **"Can I understand this in 6 months?"** - Prefer explicit over clever. Government data has edge cases - document them inline, not in external docs that drift.

- **"What's the smallest change that solves this?"** - Resist scope creep. A bug fix is not a refactor opportunity. A new feature doesn't require rewriting adjacent code.

- **"Is this tested by snapshots?"** - If a change affects output, update or add snapshots. Snapshots are the source of truth for expected behavior.

### Data Pipeline Principles

- **"Schema-first thinking"** - Define the shape of data before writing transformation code. Use `/schemas` folder. JSON Schema enables cross-language validation.

- **"Idempotency is non-negotiable"** - Running a pipeline twice should produce the same result. No side effects that accumulate.

- **"Trace data lineage"** - Every output should be traceable to its source. Include metadata about when and how data was fetched.

- **"Fail loudly, recover gracefully"** - Validation errors should halt pipelines. Missing optional data should not.

### Performance & Scale

- **"What happens with 10x the data?"** - Current scale is ~47 jurisdictions. Consider: What if we add counties? Cities? Federal agencies?

- **"Can this be parallelized?"** - State-level operations are inherently parallel. Pipelines should support concurrent execution.

- **"Memory vs. streaming"** - Large datasets should be processed as streams, not loaded entirely into memory.

### Contribution Guidelines

- **"Does this have an `action.yml`?"** - New actions must be GitHub Actions-compatible.

- **"Where are the snapshots?"** - Each action manages snapshots via `render-snapshots.sh`. Add test data in `__snapshots__/`.

- **"CLI-first, API-second"** - Prefer shell-composable tools. Unix pipe friendliness enables automation.

## Monorepo Structure

```
actions/
  extract/      # Data extraction utilities
  fleet-monitor/     # Observability for the scraper and data-repo fleets
  format/       # Data transformation and formatting
  govbot/       # CLI tool for interacting with government data
  pipeline-manager/  # Orchestrates data pipelines
  report-publisher/  # Generates reports
  scrape/       # Web scraping for government data sources
schemas/        # Shared JSON schemas for data validation
scripts/        # Repository-level utility scripts
```

## Key Conventions

1. **Snapshots as Tests**: `__snapshots__/` folders contain real outputs used for validation
2. **Schema Validation**: Use JSON Schema from `/schemas` for type definitions
3. **Multi-language**: Actions can be Python, Bash, Rust, or TypeScript
4. **Portable by Default**: Everything should run as basic scripts with args

## Common Commands

```bash
govbot init          # Create govbot.yml config
govbot clone all     # Download all state legislation datasets
govbot clone wy il   # Download specific states
govbot logs          # Stream legislative activity as JSON Lines
govbot logs | govbot tag  # Process and tag data
govbot load          # Load bill metadata into DuckDB
govbot build         # Generate RSS feeds
```

## DuckDB Integration

The `govbot load` command loads bill metadata into a DuckDB database for SQL analysis.

**Prerequisites**: DuckDB CLI must be installed (`brew install duckdb` or see https://duckdb.org/docs/installation/)

**How it works**:
- Shells out to `duckdb` binary (not a Rust library dependency)
- Reads all `metadata.json` files from cloned repos
- Creates `bills` table and `bills_summary` view
- Database saved to `~/govbot_data/govbot.duckdb`

**Usage**:
```bash
govbot clone all                    # First, get the data
govbot load                         # Load into DuckDB
govbot load --memory-limit 32GB     # For large datasets
duckdb --ui ~/govbot_data/govbot.duckdb # Open in browser UI
```

See `actions/govbot/DUCKDB.md` for query examples and schema documentation.

## Testing with Mock Data

Mock legislative data is available for offline development:
- Location: `actions/govbot/mocks/govbot_data/repos/`
- Contains: Wyoming (wy) and Guam (gu) sample data
- Usage: `govbot logs --govbot-dir ./actions/govbot/mocks/govbot_data`

## Pages Dashboard

The GitHub Pages dashboard's topic taxonomy lives in `scripts/govbot-dashboard.yml`
(the canonical `tags:` config the deploy workflow runs `govbot tag` against). Its topic
names must stay in sync with the keyword fallback in `scripts/dashboard_tags.json`. See
`docs/src/dashboard-guide.md` for the data flow; tagging in CI is incremental via
`scripts/filter_new_bills.py` + `scripts/tag_dashboard_repo.sh`.

**Civic redesign (in progress).** The dashboard is being revamped into a dark-mode-first
"civic institution" per the design brief in `tamara-notes/`. Shared design system lives in
`docs/src/dashboard/assets/govbot.css` (dark-first tokens + components; legacy token names like
`--page`/`--series-N` are aliased to the civic palette so unmigrated inline page CSS reskins
automatically) and `docs/src/dashboard/assets/govbot-shell.js` (theme toggle with dark default,
mobile nav drawer, back-to-top, global search, and the global-nav mega-menu dropdowns).
The shared CSS also provides designed **state** components — `.gb-state` (empty / no-results /
`.gb-state--error`, with an icon, message and a recovery action) and `.gb-loading` + `.gb-spinner`
— used for the loading/empty/error states on the legislation, elections and hearings pages
(the empty state's "Clear filters" button reuses each page's `#f-clear`), and a **mega-menu**
(`.gb-nav-item`/`.gb-mega`) on the Homepage nav (Explore / Follow / Data dropdowns, hover on
desktop + click, Escape/outside-click to close; the mobile drawer stays a flat link list). `docs/src/dashboard/index.html` is now the
**Homepage** landing page (a realistic golden wireframe Lady Liberty raster hero, `assets/liberty-hero.png`, luminance-keyed to a transparent background so it drops cleanly onto the hero in both themes; the robot mark `assets/govbot-mark.png` is the header logo; "What do you want to know?" cards,
live "What's happening now" fetched fail-soft from `data.json`/`hearings.json`/`elections.json`).
Pages migrate to the shared system one at a time; the old per-page "New Design" skins + toggle
are retired as each page is migrated. `legislation.html` has had its content redesigned
**search-first**: a prominent search hero, State + Topic as primary browse with Session/Chamber/
date behind a "More filters" `<details>`, a "Recent activity" card strip (`#recent-list`, newest
recorded actions, unfiltered, click → bill modal), the charts/tiles collapsed under an
"Overview &amp; charts" `<details>`, and the dense sortable table kept below. The bill modal now
leads with an inferred **status timeline** (Introduced → Committee → Passed House → Senate →
Governor, `billStageIndex`/`stageTimeline`, using the shared `.gb-timeline` component).
`elections.html` has been reframed **ballot-first**: an Illinois-flag hero (the accurate flag
asset `assets/il-flag.png` rippled by an animated SVG turbulence/`feDisplacementMap` "wave" with a
gold edge — a static `<img>` under `prefers-reduced-motion`; "Illinois Elections" / "Know who's on
your ballot before you vote." / a dynamic "Next election" line / an "Explore races" CTA) and a "What's on your ballot?" selector
(`#ballot-cards`, one card per distinct `ballot_date` with its stage label + office/candidate
counts) that drives the existing `#f-ballot` filter, reveals the sections, and scrolls to
`#groups` (`renderElectionHero`). The rich race engine (groups, five drawers, calendar,
Springfield, picker) is unchanged.
`hearings.html` has been reframed **participation-first**: an "Have your say." hero (overline
"Hearings & Public Comment", tagline "Government isn't just something you watch — you can
participate.", a dynamic "N upcoming · N open to public comment · N jurisdictions" line, a gold
detailed gold White House line-art (`assets/whitehouse-hero.png`, a transparent-background raster
so it drops onto the dark hero in both themes), and a "See upcoming hearings" CTA; the America-250 `250th` fireworks
brandbar is kept). Each hearing now makes participation obvious: a green **"Public comment open"**
badge on the date column and the witness-slip/comment action elevated into a filled green
`.file-link` pill. The `<title>` was also corrected (it had been a stray "Legislation Dashboard").
The hearing/participation render engine is otherwise unchanged.
`architecture.html` is retitled **"How Govbot Works"** and now opens with a nontechnical layer: a
plain-English six-stage overview pipeline (`.gw-pipeline`: Government sources → Govbot pipelines →
Validate + normalize → AI topic tagging → Open data → Your dashboards) and a "How it stays
trustworthy" card strip (`.gw-trust`: twice-daily refresh, source lineage, fail-soft, open RSS,
open source, known limits), with the existing detailed per-pipeline diagrams kept below as the
"full picture" (progressive disclosure). Stale product labels were updated to the new names.
All five pages share a single **browser-tab favicon**: an inline SVG data-URI of the Govbot robot
face (dark rounded tile, silver dome, gold antenna + eyes, green mouth bar) in the civic palette,
crisp at 16px — replacing the old per-page torch/pinwheel icons.

The Pages site has a **Homepage plus three dashboards plus a How-Govbot-Works page**:
`docs/src/dashboard/index.html` (the **Homepage**),
`docs/src/dashboard/legislation.html` (**Explore Legislation** — the legislation dashboard,
formerly `index.html`; deep links are `legislation.html#q=<billid>`),
`docs/src/dashboard/hearings.html` (**Hearings & Public Comment**),
`docs/src/dashboard/elections.html` (**Illinois Elections**), and
`docs/src/dashboard/architecture.html` (**How Govbot Works** — a static, no-data explainer of all
three backend pipelines). **Every page now wears the same shell as the Homepage** — the old
per-page tab bar + brandbar (logo + 3-button light/auto/dark theme pill) have been **retired**.
All five pages share, byte-for-byte, the global-nav header (`.gb-header`: the `assets/govbot-mark.png`
robot logo linking to the Homepage, the Explore / Follow / Data mega-menus + How Govbot Works /
About plain links, the global `.gb-search`, and a single `[data-gb-theme-toggle]` icon button), the
mobile `.gb-drawer` (hamburger → flat link list + search), the civic `.gb-footer` (Explore /
Transparency / Community columns), and the floating `.gb-to-top` liquid-glass "Back to Top" pill —
all wired by the shared `assets/govbot-shell.js` (so every page also loads that script). The active
section is marked `aria-current="page"` in the header's Explore mega-menu (and the top-level How
Govbot Works link on architecture) + the drawer. Each flagship keeps its own **signature hero**
below that shared header: legislation's search hero, elections' waving Illinois flag, architecture's
plain-English pipeline, and hearings' self-contained "night sky" hero panel — the America-250
`250th` fireworks canvas (`#fw-canvas`) relocated out of the retired brandbar into `.hh-hero` (dark
in both themes so the bursts read). **Every generated RSS feed** (both
the hearings and elections pipelines) carries an `<?xml-stylesheet type="text/xsl"
href="feed.xsl"?>` processing instruction pointing at the shared stylesheet
`docs/src/dashboard/feed.xsl`, so a browser renders a feed as a readable page (title, subscribe
callout with the feed URL, entry list) instead of a raw "no style information" XML tree — while
feed readers ignore the PI and parse the RSS as usual. Whole-ballot/whole-calendar feeds at the
dashboard root reference `feed.xsl`; granular feeds one directory down reference `../feed.xsl`
(the feed builders in both `main.py`s take an `xsl_href` for exactly this). All four product
pages now link the shared `assets/govbot.css` (dark-mode-first; the legacy `--page`/`--series-N`
tokens are aliased to the civic palette so the existing chart/table CSS reskins automatically) and
share the single shell theme toggle (`[data-gb-theme-toggle]` in `govbot-shell.js`, on the
`localStorage['govbot-theme']` key; each page still inlines the tiny pre-paint snippet in `<head>`
to avoid a flash). The old per-page **"New Design"** skins + toggle (Stripe/Robinhood/Polymarket)
and the per-page 3-button light/auto/dark theme pills have been **retired** — the civic dark-first
design is the single default. On elections and hearings, the long list
sections scroll inside capped-height boxes (`.group .races`, `.sf-list`, `.hgroup-rows`,
`.participation-grid`) so the homepage isn't enormous; the elections "Where the data comes
from" cabinet is `open` by default. The hearings
page is a *separate* pipeline: `actions/scrape-hearings/` taps ilga.gov, leg.wa.gov,
malegislature.gov, and akleg.gov directly (not OpenStates), plus **USA (Federal)** open comment periods from the
Regulations.gov API (needs `REGULATIONS_GOV_API_KEY`; falls back to the committed
`actions/scrape-hearings/federal_seed.json` when unset/unreachable) — federal leads the
list, above the states. It writes `docs/src/dashboard/hearings.json` + a whole-calendar
RSS `hearings.xml` + granular RSS feeds under `docs/src/dashboard/hearings/` — per bill
(`<jurisdiction>-<NORMALIZED_ID>.xml`), per jurisdiction (`<code>.xml`), and per hearing
(`hearing-<id>.xml`) — so a reader can follow one bill, a whole state, or a single hearing
(schema `schemas/govbot.hearings.schema.json`), plus a static 56-jurisdiction participation
directory `docs/src/dashboard/participation.json` (schema
`schemas/govbot.participation.schema.json`). Passing `--participation <file>` also emits an
empty placeholder `<code>.xml` for every participation state with no live hearings yet, so
each "Weigh in — by state" card carries a "Follow this state (RSS)" link that starts empty
and fills when that state opens (its filter box has a colored border + search icon). `deploy-docs.yml` rebuilds both the bill
`data.json` and the hearings feed on the twice-daily schedule. Hearings parsers are
offline-snapshot-tested: `python3 actions/scrape-hearings/test_scrape_hearings.py`.

The **Elections Happening in IL** page is a *third* pipeline: `actions/scrape-elections/` builds
`docs/src/dashboard/elections.json` (schema `schemas/govbot.elections.schema.json`) — every
office on upcoming Chicago/Illinois ballots (citywide, Alderperson wards 1–50, CPS board
president + subdistricts 1A–10B, and 22 Police District Councils) **plus the Nov 3, 2026
Illinois general election** — U.S. Senate, all 17 U.S. House districts, Governor and the
statewide constitutional officers (Attorney General, Secretary of State, Comptroller,
Treasurer), the 39 Illinois Senate seats up this cycle, and all 118 Illinois House seats.
Those ride five office groups — `us_senate`, `us_house`, `il_exec`, `il_senate`, `il_house`
(added to the schema enum, the frontend `GROUP_META`/`GROUP_ORDER`, and `OFFICE_GROUP_LABEL`)
— and render as their own sections like the Chicago groups. They're `partisan` general-election
races (`ballot_stage: "general"`, ballot date 2026-11-03); the locator map is Chicago-only, so
statewide/federal races show none (gated on `jurisdiction` in the frontend), and the
news-sourced *potential-candidate* pass is Chicago-only too (`POTENTIAL_GROUPS`) since these
offices already have official post-primary nominees. The ballot *structure*
(offices, districts, ballot dates, and a "why this race exists" note) is a committed seed,
`actions/scrape-elections/elections_seed.json`; the scrapers only *populate candidates* onto
it from official candidate lists (Chicago Board of Elections; Illinois SBE "Who Is Running";
Cook County Clerk, future). A candidate attaches to a race only when office+district resolve
exactly (`race_id_for` — which now also resolves the statewide/federal/General-Assembly offices,
guarded so a bare "Treasurer"/"Senator"/"Representative" still means the Chicago office, never a
statewide one) — unplaceable rows are dropped, never invented, and a race with no
confirmed candidate keeps an empty list + a source link. It also writes a whole-ballot RSS
`elections.xml` + granular feeds under `docs/src/dashboard/elections/` (per office group
`group-<group>.xml`, per ballot date `ballot-<YYYY-MM-DD>.xml`, per race `race-<id>.xml`).
Feed-item titles are **self-describing** (`Mayor · on the Feb 23, 2027 ballot · 3 candidates`)
so a title-only reader/widget conveys the facts; the **per-race** feeds additionally expand into
**one item per official candidate**, the `[UNOFFICIAL]` potential-candidate items, and **one item
per dated election-calendar milestone** (`🗓 Filing deadline — Mayor · Nov 23, 2026 (expected)`,
date in the title, pubDate kept at build time so readers don't hide the future date) — aggregate
feeds stay one item per race. All feed dates (both pipelines) are published in **Central time
(CST/CDT)** via a shared `America/Chicago` `FEED_TZ` + `_to_822`/`_date_822` helpers.
The page has an "On this page" table of contents; every RSS control reads "Follow this
race (RSS)" in red; each major section carries a thick colored top border; the Legislation
Dashboard's Bill column is plain text (the official-source link lives in the details card). Each
bill row also has a **"Share"** button beside "Details" (and a "Share this bill" link in the
details card's Sources) that copies a deep link `legislation.html#q=<billid>` (id lowercased, punctuation
stripped, e.g. `#q=sb813`); opening it lands the dashboard pre-filtered to that bill — the search
filter now also matches ids ignoring spaces/punctuation, and a `hashchange` listener re-applies the
`#q=` filter live. The details card lists each **sponsor/co-sponsor with their current party (a
tinted D/R/other tag) and seat** (chamber + district, e.g. "Senate District 39"), resolved from the
`people.json` roster: `scripts/build_people_roster.py` now emits `[given, full, party, area]` per
legislator (from the Open States people repo — the current party role and current legislative seat;
name fields keep their positions so resolution is unchanged, party/area degrade to "" when
unknown). Offline-tested in `scripts/test_build_people_roster.py`. It also attaches a top-level
`springfield` list — the **"rules of the game"**: IL bills from the legislation
`data.json` tagged `elections & voting` or `education` (the elected CPS board, ward/runoff
rules, campaign finance), cross-referenced with `hearings.json` for upcoming ILGA hearings,
shown on the page as context *beside* the races (never mixed into candidate lists) plus a
`springfield.xml` feed. `deploy-docs.yml` runs this after `data.json`+`hearings.json` are
built so it reads the fresh copies. Fail-soft: with sources down the seed's structure still
ships (empty rosters/springfield), and the deploy keeps the committed sample unless the
fresh run produced candidates or Springfield bills. Parsers are offline-snapshot-tested:
`python3 actions/scrape-elections/test_scrape_elections.py`.

Per-race **locator maps** come from a separate action, `actions/scrape-maps/`: it fetches
ward (`p293-wvbd`) + police-district (`24zt-jpfn`) boundaries from the City of Chicago Data
Portal, projects + Douglas-Peucker-simplifies them at build time, and writes a compact
`docs/src/dashboard/maps.json` (`{view, context, districts}` keyed by race id). The elections
page draws each race's ward/police polygon as an inline-SVG locator inside a light city
outline (citywide offices tint all of Chicago); CPS subdistricts have no published polygon
so their map is omitted. Fail-soft: a portal outage leaves the committed `maps.json` in
place. Geometry helpers are offline-tested: `python3 actions/scrape-maps/main.py --self-test`.

**Official candidates** are populated from the Chicago Board of Elections' authoritative
**Candidate List PDF** (linked from `chicagoelections.gov/getting-ballot/candidates`; the BOE
publishes the roster only as a PDF). `deploy-docs.yml` installs `poppler-utils` and
`main.py --enrich-candidates-boe docs/src/dashboard/elections.json` auto-discovers the newest
`Candidate List_<date>.pdf`, extracts it with the `pdftotext` **system tool** (shelled out like
DuckDB — no Python dep, so the stdlib-only rule holds), and merges candidates. The pure
`parse_boe_candidate_list(text)` keeps a candidate only when its office header resolves to a
Chicago-seed race (`_boe_office_race` → `race_id_for`); the statewide/federal/judicial/county
offices on the same ballot are ignored. Two guards make that safe: `race_id_for` requires an
education signal for the CPS board (so the **Cook County Board president** never resolves to the
CPS president), and `_boe_office_race` requires the word "City" for the treasurer/clerk (so the
**statewide Treasurer** is never misread as the Chicago City Treasurer). On the Nov 2026 ballot
this yields exactly the CPS races (president + 20 subdistricts 1a–10b, 42 candidates); it's
forward-compatible, so when the **2027 municipal** candidate list publishes it will populate
mayor / alderperson wards / police district councils / city clerk & treasurer the same way (no
2027 official roster exists yet — filing is Nov 2026). Offline-tested against
`__snapshots__/raw/boe_candidate_list.txt` (`pdftotext -layout` text incl. statewide + municipal
examples; the shell-out lives only in the fetch wrapper). Runs before the money step (so
committees can match) and before the RSS feeds are rebuilt. Fail-soft: no poppler / no PDF leaves
rosters as they were; committed sample empty.

**General-election nominees** (the 2026 statewide / U.S. Senate & House / General Assembly races)
are populated by `main.py --enrich-candidates-wiki docs/src/dashboard/elections.json` from
**Wikipedia's per-office election pages** (`WIKI_NOMINEE_PAGES`). ISBE has no bulk candidate
download, so this reads the certified nominees off the structured wiki markup — statewide/U.S.
Senate from the election infobox (`_wiki_infobox_nominees`), U.S. House from each district's
general-election infobox (`parse_wiki_ushouse`, so independents are included), and the General
Assembly from each district's "General election results" box, else the winner of each party
primary, else a *confirmed* "incumbent … running for re-election" narrative
(`parse_wiki_legislature`) — and each nominee carries the page it came from as its `source`
(the pages themselves cite the ISBE candidate list, preserving lineage). Attachment is by seed
`race_id` (a district not up in 2026, or one Wikipedia hasn't filled in, simply stays empty —
never guessed), dedup by name, flips the race to `on_ballot`. `deploy-docs.yml` runs it right
after the base build (before the BOE step, the money step so committees can match, and the feed
rebuild). Pure parsers are offline-snapshot-tested against `__snapshots__/raw/wiki_*.txt`;
fetching is fail-soft (an unreachable/edited page — or a rate-limit — contributes nothing).

**Campaign money** (Illinois SBE) attaches to each candidate via the SBE ID crosswalk
(candidate name → `Candidates.txt` ID → `CmteCandidateLinks` → `Committees` → latest
`D2Totals` row): receipts, spending, cash on hand. Only unambiguous name matches are kept
(never fuzzy dollar matching). Because the SBE bulk files are ~70MB, `deploy-docs.yml`
runs it as a **separate step gated on candidates being present** —
`main.py --enrich-money docs/src/dashboard/elections.json --money-dir <sbe-files>` — so the
committed sample (empty rosters) carries no money. Parsers/aggregation are offline-tested
in `test_scrape_elections.py`.

**Results** (post–Election Night) are scaffolded: each race can carry a `results` block
(per-candidate votes/%/winner, precincts reporting) attached by
`main.py --enrich-results <elections.json> --results-file <csv>` from the authority's
results export (Chicago BOE / Cook County Clerk). Header-driven + fail-soft; it counts every
reported candidate (official results are authoritative) and flags a winner only when the
source does — never projected. The deploy step runs only when the `ELECTION_RESULTS_URL`
repo variable/secret is set, so it is inert until an election happens. This completes the
"five drawers" per race: map · candidates · money · results · context (Springfield).

**Potential candidates** (unofficial) attach a *separate* `potential_candidates` list per
race — names the press reports as running/exploring/rumored before filing opens, kept strictly
apart from the official `candidates` list. They surface in the **per-race RSS feeds** as items
prefixed **`[UNOFFICIAL]`** and linked to a source article (a rumor can't be mistaken for a
ballot record), but are kept out of the whole-ballot/group/ballot aggregate feeds. Once a name
is confirmed on the official list it **graduates out** of potential — `build_potential` drops
any name already in that race's official `candidates` (populated earlier in the deploy by
`--enrich-candidates-boe`), so a filed candidate never double-lists as both official and rumored.
`main.py --enrich-potential <elections.json>` reads **Google News' public RSS search** (the
"internet"; raw social-platform scraping is not TOS-safe/reliable, so it is out) and attaches a
name only when a headline both names a person beside a candidacy verb (→ status
`announced`/`exploring`/`reported`) *and* references the race — its office keyword plus, for a
district race, its district token (word-boundary matched, so "5th ward" ≠ "25th ward").
It also recognizes a **mid-term appointment/confirmation** to a seat (→ status `incumbent`):
the appointee is captured (e.g. "Mayor Brandon Johnson's pick, **Anthony Quezada**, to replace
… 35th Ward Alderman …" → Anthony Quezada), never the owner of the pick (the mayor) nor the
outgoing member ("to replace …"). Appointment patterns run only for seat-specific district
races — not citywide ones, where a bare "mayor"/"clerk"/"treasurer" is usually just a title —
so a ward appointee never leaks into the mayor's race.
Honorifics are stripped ("Rep. Mike Quigley" → "Mike Quigley"), office/place/calendar words are
rejected as names, and every name carries its source article(s) {title, url, publisher, date};
a sourceless name is dropped — nothing is invented. Extraction is tuned for real local-outlet
headlines: verbs match case-insensitively (title-case "… Launches …", "… Running …"), an adverb
between the name and the verb is skipped ("Aida Flores **Again** Running"), and names are gated
against truncation (a trailing initial or split particle like "Matthew J. O" / "Daniel La") and
against verb/event words captured as a name. A **negated** candidacy is dropped, not surfaced
("… O'Shea **Won't** Seek Reelection", "will not run") — the check is local to each match, so a
compound headline naming a retiring incumbent *and* a real challenger keeps only the challenger. Queries: one pooled query per office group
for cross-cutting coverage, **plus a per-race query for every district race** (`Chicago alderman
"45th ward" candidate 2027`, etc.) so each ward/subdistrict/police district gets its own coverage
pool, plus one per citywide office. A bigger pool never loosens the match — the strict office +
district gating is unchanged, so most down-ballot races legitimately stay empty until candidates
actually appear in the press (2027 filing opens Nov 2026); the lists fill in on the twice-daily
refresh as coverage grows. Fail-soft (sources down → empty lists), committed sample empty.

**Article bodies** are parsed too (on by default; `--no-article-bodies` opts out), because a
headline often omits the candidate's name while the prose states it ("Meet the 28-year-old
lawyer running to represent the 23rd Ward" → *Leonardo Rojas-Banda* is only in the body). For a
few race-relevant articles per race (headline references the race **and** reads like candidacy
coverage — capped per race and per run), `enrich_potential` resolves the Google News link to the
publisher URL via Google's `batchexecute` endpoint (`resolve_gnews_url`; the RSS `<link>` is an
opaque token, so a plain GET only yields Google's interstitial), fetches the article, and reduces
it to text (`html_to_text`). `extract_candidacy_body` then runs the **same** strict
name+candidacy-verb gate as headlines — plus a prose-only appositive pattern ("Name, a <role>,
<verb>", anchored on a/an/the) — but keeps a name only when (1) the race is referenced within a
short window of the match and (2) the surname recurs in the article (a real subject, not a passing
mention). Every step is fail-soft (a 403/parse failure just skips that body); `build_potential`
takes the fetched bodies as an argument so it stays pure and offline-testable, and the fetchers
are injectable. A curated, news-sourced `potential_candidates` entry may also be **seeded** in
`elections_seed.json` (preserved by `assemble()`, merged forward by `--enrich-potential`) as a
durable backstop for a name the automated pass can't reliably catch. The
frontend renders it as a collapsed, dashed-amber "💭 Potential candidates · Unofficial · from
news" block under each race. `deploy-docs.yml` runs it right after the base elections build
(independent of official candidates), twice daily. Parsers are offline-tested in
`test_scrape_elections.py`.

## govbot Development

```bash
cd actions/govbot
just setup           # Install Rust toolchain and dependencies
just test            # Run snapshot tests
just review          # Review snapshot changes (insta)
just govbot logs     # Run CLI in dev mode (uses mocks/govbot_data)
just mocks wy il     # Update mock data for testing
```

## When in Doubt

1. Check existing snapshots for expected behavior
2. Look at similar actions for patterns
3. Prefer explicit failure over silent corruption
4. Keep changes minimal and focused
5. Consider the data pipeline as a whole, not just isolated components
