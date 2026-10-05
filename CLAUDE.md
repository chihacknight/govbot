# CLAUDE.md

This file provides senior engineering-level guidance for Claude Code when working on this codebase.

## Project Overview

This is **govbot** - a monorepo for distributed data analysis of government updates. Git repos function as datasets, including legislation from 56 jurisdictions (50 states, federal, DC and 4 territories). The `actions/` folder contains self-contained modules that can run as shell scripts or GitHub Actions.

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
  openstates-scrape-audits/  # Weekly/daily checks that catch OpenStates scraper failures a green checkmark hides
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
- Database saved to `./govbot_data/govbot.duckdb` (under the directory you run govbot from, or `$GOVBOT_DIR`)

**Usage**:
```bash
govbot clone all                    # First, get the data
govbot load                         # Load into DuckDB
govbot load --memory-limit 32GB     # For large datasets
duckdb --ui govbot_data/govbot.duckdb   # Open in browser UI
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
"civic institution" per the design brief in `tamara-notes/`. **Brand colour = a lively green ("Spring"),
not gold** (chosen on the "Govbot Green" Design canvas): `govbot.css` defines `--gb-primary` (dark
`#3DDC84` / light `#0B7D45`), `--gb-primary-hi` (`#7CEBB0` / `#075C33`), `--gb-on-primary` (text on a
primary fill: `#04140B` dark / white light) and `--gb-glow-primary`, and **`--gb-gold`, `--gb-gold-hi` and
`--gb-glow-gold` are now aliases of them** — so wherever this document says "gold" for a brand accent
(buttons, overlines, pulses, the mini-date band, map bases, stat numerals…) it renders green. Role map:
brand + Hearings = green; Legislation = blue; **Illinois Elections = amber** (`--gb-amber` /
`--gb-amber-hi`: its menu accent, homepage slide and Chicago-map selection outline); the per-race
**locator mini-maps keep the classic look — a GOLD outline/base with the GREEN highlighted district** —
via their own `--rm-gold` (the pre-rebrand gold, `#D6A84F` dark / `#A9791F` light, set on `.race-map`),
since `--gb-gold` is now green; "live" / "comment open" status marks stay `--gb-green`. The Liberty
(`liberty-hero.png`), White House (`whitehouse-hero.png`) and **Illinois Capitol**
(`il-capitol-building.png`, deepened with a CSS `brightness`/`saturate` filter in light mode so the line
art stays crisp; the waving flag overlay is unchanged) heroes were recoloured to green in place
(a hue remap of their gold pixels, keeping value + alpha; the gold originals are in git history), the
legislation US heat-map ramp is green, and the gavel favicon (now also on the mdbook docs pages) is green.
On the light-mode homepage the statue stands in a deep-green "night" panel (`.gl-art`) because her pale
line-art highlights wash out on a light page. Shared design system lives in
`docs/src/dashboard/assets/govbot.css` (dark-first tokens + components; legacy token names like
`--page`/`--series-N` are aliased to the civic palette so unmigrated inline page CSS reskins
automatically) and `docs/src/dashboard/assets/govbot-shell.js` (theme toggle with dark default,
mobile nav drawer, back-to-top, global search, and the global-nav mega-menu dropdowns).
The shared CSS also provides designed **state** components — `.gb-state` (empty / no-results /
`.gb-state--error`, with an icon, message and a recovery action) and `.gb-loading` + `.gb-spinner`
— used for the loading/empty/error states on the legislation, elections and hearings pages
(the empty state's "Clear filters" button reuses each page's `#f-clear`), and a **mega-menu**
(`.gb-nav-item`/`.gb-mega`) on the Homepage nav (Explore / Follow / Data dropdowns, hover on
desktop + click, Escape/outside-click to close; the mobile drawer stays a flat link list). `docs/src/dashboard/index.html` **was** the
**Homepage** — it is now a redirect to the site root, and the pieces described below (the Liberty hero,
the live recent-activity / hearings / election cards with sponsor chips, and the firehose animation) were
ported to the root landing (`docs/src/readme.md` + `docs/theme/landing.js`, see "The site root…" below).
As originally built it was the landing page (a realistic golden wireframe Lady Liberty raster hero, `assets/liberty-hero.png`, its background keyed to true transparency — the low-alpha (~10–22) background pixels were zeroed so no faint grey box composites onto the light hero; behind her a soft dark halo `.liberty::before` (deeper in light mode) plus a radial edge-mask on the image keep the gold statue **prominent in light mode** and drop cleanly onto the dark hero; the robot mark `assets/govbot-mark.png` is the header logo; "What do you want to know?" cards,
live "What's happening now" fetched fail-soft from `data.json`/`hearings.json`/`elections.json`).
The homepage's **"Recent legislative activity"** card shows **one bill per state** (up to 4) as rich
`.activity-row.rich` rows — each row's head line carries the **state + bill number** (`.tag`) and
the **bill's title on the same line** (`.ar-idtitle` wraps the `.tag` + `.ar-title`, the title
`Title-Cased` by a shared `titleCase()` helper so ALL-CAPS legislative titles like "AN ACT
CONCERNING…" read as "An Act Concerning…", minor words kept lowercase, existing acronyms preserved
in mixed-case titles), with the latest recorded action demoted to a secondary muted `.desc` line
beneath (falling back to the action as the title when a bill has no title), and each is an
**alternating card**
(on the root landing, consecutive rows alternate a full 4-sided **green / gold** border — green
`--gb-primary`, gold the landing-only true-gold `--gl-fgold` (the brand `--gb-gold` is green) — via a
per-row `--ar-c` set on `:nth-of-type(even)`, with a faint matching tint and a 16px gap between
rows, so bills read as distinct blocks) that **links to that exact
bill's card** via `legislation.html#bill=<state~session~id>` (a plain `#q=<id>` would surface every
state's same-numbered bill; the unique key opens just the one — `billKey` here matches `billKey` +
the `#bill=` branch of `applyDeepLink` in legislation.html, which calls `openDetails` on the
matching bill). Each row carries the bill's topic tags (`.ar-topic` chips) plus its sponsors as
**sponsor avatar chips** (`.ar-av`, name + party letter, first 3 then
"+N more"). Every sponsor that resolves to a real legislator (or that has a vendored photo) is
pictured: a **vendored headshot** when we have one, otherwise a **party-tinted initials monogram**
(`initialsOf` = first + last initial, in the party-colored circle). The headshot `<img>` overlays
the initials, so a runtime image error just drops the `<img>` and reveals the initials underneath
(the sponsor chip stays). An unresolved non-person string (e.g. a committee) with no photo is skipped
(still counted in "+N more", which counts resolved sponsors beyond the 3 shown). The card just shows
the newest bill per state (no photographed-bill preference); a state whose sponsors have no photo
shows their initials monograms + name + party. Party + full name are resolved from `people.json` with the same matcher
legislation.html uses (`matchLeg`, surname-only / "Surname, F" / "First Last", never guessing an
ambiguous surname). **Photos are vendored at deploy, never committed** by
`scripts/fetch_sponsor_photos.py` (deploy-docs.yml, "Vendor sponsor photos for on-screen bills",
after `data.json` is built) — only for the sponsors of the on-screen bills (newest 1/state, small
cap), **including federal**: the `data/us` Congress roster is aliased to `usa` (data.json's federal
state code) and those entries are keyed in the manifest by the **raw sponsor name** and aliased to the
roster full name (people.json now carries Congress under `usa`, so the landing's `photoPath` tries the
resolved full name, then the raw name); the Wikipedia guard, which needs a
state for state bills, instead requires a distinctly-federal congressional role phrase for `usa`. Into
`docs/src/dashboard/assets/legislators/` + a manifest `legislator_images.json`
(`{"<state>:<full name lower>": "assets/legislators/<file>"}` — the frontend's lookup key). Both the
image dir and the manifest are **`.gitignore`d build artifacts** — fetched during the Pages build,
published by mdbook with the site, so no photo dump lands in git. It tries **three public sources in
order, falling back if the last found none**: (1) the Open States CC0 `image:` URL (a **hardened**
retrying downloader — `default_fetch` sends a same-origin `Referer` + an image `Accept` so the
hotlink-averse legislature/CMS hosts that serve most of these URLs return the photo instead of a 403,
and rejects a non-image body via `is_image_bytes` magic-number sniffing, so an HTML block/login page
returned with a 200 is discarded and the next source is tried rather than a broken "photo" written),
then (2) a **Wikipedia** article page thumbnail, accepted only when the page summary confidently
ties the person to that state's legislature (`wiki_thumbnail` → `_wiki_thumb_if_confident`: a
legislative-role word *and* the state name must appear, the person's **surname** must appear, and it
must not be a disambiguation page — federal uses a distinctly-congressional role phrase instead of a
state — otherwise no photo, so a namesake's face is never attached). The Wikipedia step does **two**
guarded lookups: the exact `Full_Name` page, then — since many legislators live at a disambiguated
title like "Jane Roe (politician)" the exact lookup misses — Wikipedia's own **search API**
(`rest.php/v1/search/page` for the name + state + a legislature/congress hint; a real API, not
screen-scraping), guarding each of the top hits with the same confidence gate. Then (3) a **Wikimedia
Commons image search** (`commons_thumbnail`: the Commons `list=search` API over the File namespace,
`commons.wikimedia.org/w/api.php`, iiurlwidth thumbnail) — a real keyless image-search API, **not** a
scrape of a search engine's results page — which reaches the many state legislators who have a
Commons portrait but **no Wikipedia article**. A Commons hit is kept only when the file's **own
metadata** (title + description + categories) carries **both name tokens (given + surname)** *and* a
state/legislature signal (the state name or a legislative role word; federal: a congressional role
phrase), and only for raster files (`_RASTER_MIMES` — an SVG signature or a PDF is skipped) — the same
"never attach the wrong face" gate. Together, the Wikipedia + Commons searches are the TOS-safe form of
"search the web for the sponsor's photo": every source is a documented public API, never a scraped
search-engine result page (which would break constantly and violate ToS, the same rule the elections
pipeline follows in using Google News' public RSS rather than scraping). Reuses the
`/tmp/openstates-people` checkout from the roster step; fully fail-soft (no checkout / every source
fails → that sponsor just isn't pictured).
Offline-tested with injected fetch/wiki/commons functions: `python3 scripts/test_fetch_sponsor_photos.py`.

**Illinois bill synopses ("What this bill is about").** Illinois is the one jurisdiction whose
dashboard bills read badly: the stored `title` is the ILGA cryptic short-code ("$DFPR-TECH",
"URBAN PROBLEMS-TECH") and govbot's metadata carries **no abstract** (unlike CA/FL/CO/MD/… which
already ship a readable title), so the plain-language synopsis is missing. `scripts/build_il_summaries.py`
fills the gap: for each IL bill it reads the bill's **full-text PDF** (the `versions[].links[]` PDF in
that bill's `metadata.json`), extracts it with `pdftotext` (poppler, the same tool the elections BOE
step uses), and pulls out the official **"SYNOPSIS AS INTRODUCED"** — dropping the leading run of bare
statute citations ("New Act", "30 ILCS 105/5.10 new") and keeping the prose (`extract_synopsis`, a pure
offline-tested function; the synopsis-extraction idea is adapted from the same author's
`frankies2727/CHN-SocialMedia-Govbot-Main` `bill_text.py`). Output is
`docs/src/dashboard/il_summaries.json` = `{"il~<session>~<id>": "<synopsis>"}`, the same `billKey`
the frontend builds. **Bounded + incremental:** a bill's "as introduced" synopsis never changes, so a
summarized bill is cached and never re-fetched; each run summarizes at most `--cap` (1500) new bills, so
the ~12.8k IL backlog backfills over successive twice-daily deploys and steady state costs only the
day's new bills. The cache is carried between runs by `actions/cache` (deploy-docs.yml, "Cache/Build
Illinois bill synopses", after `data.json` is built); the file is a **`.gitignore`d build artifact**
(never committed). **Fail-soft with transient-vs-permanent caching:** a bill with no PDF link or with
extractable text but no synopsis is cached as `""` (a confirmed no-synopsis, not retried), but a
*transient* failure (metadata/PDF unreachable, or `pdftotext` unavailable → empty extraction) is left
**uncached** so it retries next run — an outage never poisons the backlog. The frontend keeps the
official short-code as the `title` and shows the synopsis as the plain-language summary: the legislation
bill modal's "What is this bill about" (`plainSummary`'s fallback chain: `il_summaries.json[billKey]`
→ the metadata **abstract** → the longest descriptive **`other_titles`** entry (Open States frequently
stores the plain "AN ACT relating to…" description there while `title` is a short name like Wyoming's
"Fast Track Permits Act." — this was the biggest source of previously-empty summaries) → the bill's
own **title** when it reads like a description (not an Illinois cryptic short-code, via
`looksDescriptive`) → the record's **`subject`** tags → else a "see the official source" note. A
shouty ALL-CAPS title is title-cased for readability by `prettyTitle`, but **only** when it carries no
lowercase letters at all — so a title with case-sensitive statute citations like "§ 26603(d)(5)(B)" is
left verbatim rather than risk corrupting subsection case), and a synopsis line on the elections page's
"Recent Illinois legislative activity"
(`.ilrc-syn`) and Springfield (`.sf-syn`) cards. All fetched fail-soft (absent before the first backfill
→ the pages fall back). Offline-tested against real extracted IL bill text in
`scripts/__snapshots__/il_fulltext/`: `python3 scripts/test_build_il_summaries.py`.

**Official summaries for MI / TN / ID / LA.** In many states govbot's metadata has no abstract, so
"What this bill is about" used to just restate the title. Four of those legislatures publish a
nonpartisan summary of each bill that Open States already links in the bill's `documents`:
Michigan's House/Senate Fiscal Agency analyses (`SUMMARY:` / `CONTENT`), Tennessee's fiscal note
(`SUMMARY OF BILL:`), Idaho's Statement of Purpose, and Louisiana's digest (its `Abstract:` unless it
only restates the title, else the "Proposed/New law" paragraphs). `scripts/build_bill_summaries.py`
reads them (HTML preferred, PDFs via `pdftotext`) into **`docs/src/dashboard/summaries/<state>.json`**
= `{billKey: [summary, source document URL]}` — a **`.gitignore`d build artifact** carried between runs
by `actions/cache` (deploy-docs.yml, "Cache/Build official bill summaries", and in the fast-path
built-data cache). **Never the wrong bill:** a summary is kept only when the document's header names
that bill's number (`mentions_bill`) — Open States sometimes links another bill's document (a TN HB
linked to a different SB's fiscal note). Same bounded/incremental/fail-soft model as the IL synopses
(cap per run, newest activity first, round-robin across states; a definitive miss is cached
`["",""]`, a transient failure retries). Its User-Agent is `chihacknight-civic-data/1.0`: Michigan's
site returns 403 for any UA containing "bot" or a URL. The legislation modal loads only the opened
bill's state file (`SUMMARY_STATES` in legislation.html — keep in sync with the script's `STATES`),
shows the summary (bullet lines kept, `.m-plain.is-lines`) with a **"Read the official summary ↗"**
link (the shard's source URL, else any summary-type document in the record — analyses, digests,
bill reports — so CA/FL/OH get the link too). When the only text left would repeat the title, the
modal says instead that the legislature hasn't published a plain-language summary and links the
full bill text — only when the record loaded (a failed fetch never claims that). Offline-tested
against real documents in `scripts/__snapshots__/bill_summaries/`:
`python3 scripts/test_build_bill_summaries.py`.

The **"Next hearings open to comment"** card renders each date as a little
**calendar figure** (`.mini-date`: a gold month band with two binding rings, a big day numeral, and
the weekday + year, e.g. "Sun · 2026") and labels each hearing's jurisdiction with its **full
name, never an abbreviation** (a shared code→name `JURIS` map + `jurisName()` helper, `us` →
"USA (Federal)"). The homepage's **closing section** ("From the firehose to
the point.", `#stream`, no sub-copy under the heading) is a self-contained **canvas animation**
("chaos becomes understandable"): a
chaotic stream of raw government records (bills, hearings, votes, ballots, filings — muted, tilted
scraps) flows in from the left into the **Govbot hub** (the robot mark, keyed transparent as
`assets/govbot-bot.png` so it drops onto the dark panel, overlaid as a DOM `.stream-bot` centred on
the canvas hub and captioned with a gold **"Govbot"** wordmark, `.stream-bot-name`, positioned out
of flow so the robot stays dead-centre on the hub), which emits clean colour-coded packets
into orderly labeled **topic lanes** on the right (AI + data centers, education, housing, healthcare,
labor, transportation, …and more). Palette read live from the CSS tokens (re-read on theme flip),
`prefers-reduced-motion` renders a single static composed frame, an IntersectionObserver + the tab's
visibility gate the rAF loop, and a `SPEED` factor (0.7) scales `dt` so the whole flow runs a bit
slower. The **mobile** branch keeps the same desktop framing — chaos on the left, hub near the
middle-left (not tucked hard against the edge), the sorted topic lanes with their full labels on the
right, and **both bottom captions** ("Raw government activity" / "Understandable topics") kept visible
— on a **taller** figure (440px under 620px) with the lanes stopping higher (laneTop/laneBottom) so
the captions have room and nothing is cropped. `assets/govbot-bot.png` is the robot mark with its
baked beige background flood-filled to transparent (borders → inward, stopping at the robot's outline).
The "What do you want to know?" section header carries no sub-copy (the "One clear next step…" aside
was removed).
Pages migrate to the shared system one at a time; the old per-page "New Design" skins + toggle
are retired as each page is migrated. `legislation.html` opens with an **"Explore by place" entry**
(`#explore-entry`, `renderExplore()`): a **Map view / List view** toggle over the whole country. The
**map** is a geographic **US heat-map choropleth** — real per-state SVG paths from
`assets/us-states.json` (50 states + DC, Alaska/Hawaii insets; committed, fetched fail-soft), each
state **shaded by its real bill count** from `countBillsByState()` bucketed into gold tiers by
quantile, gold outlines, the selected state **pulsing** (`.ee-st.is-sel` / `@keyframes ee-pulse`),
and a **diagonal-hatch** `<pattern>` for jurisdictions not in the current dataset — those
untracked states (e.g. Texas) are **clickable too**: their detail card shows just the state name
(`eeNameFor` falls back to the map's own name, since `stateNames` only holds tracked states), the
"Not yet tracked" pill and a **"Coming soon..."** block (`#ee-d-soon`), hiding the count, recent
activity and "Open bills" button. It has **zoom + pan**
(± / reset buttons, wheel-zoom, drag-to-pan with clamping; the zoom controls sit inside the pan
surface so their `pointerdown` is skipped by the pan handler) and a live zoom-%. **Federal (USA) and
the four territories** (Guam, PR, USVI, N. Mariana) ride as clickable heat chips below the map (the
50-state geography can't hold them). Clicking any state/chip previews it in a **detail card** —
jurisdiction name, its **bill count**, and its **recent legislative activity** (real bills for that
code, newest→oldest, click → bill modal) — and "Open all N bills" (or a list-card click) applies
`state.filters.states` and switches the page into **results mode** (see below). The map's pan is
capture-free (an `eeDidDrag` threshold flag distinguishes a drag from a click) so **selecting a state
works while zoomed in**; switching to **list view** hides the map column entirely (`eeSetView` toggles
`#ee-mapcol[hidden]`; a `.ee-mapcol[hidden]{display:none}` rule is required — the author `display:flex`
would otherwise beat `[hidden]` and leave the map visible in list view). The
**list view** is a
flag-forward grid of jurisdiction cards (committed `flags/<code>.png`, `us.png` for federal), click →
same filter. A **Sort dropdown** (`#ee-sort`, `eeSort`, top-right of the list panel) reorders the cards:
**A–Z (Federal first)** — the default, USA pinned first then everything alphabetical — plus Z–A, Most
bills, Fewest bills (`eeBuildList` re-runs on change). A single **"N bills Govbot is tracking"**
scorecard sits in the head.
The whole entry uses the shared `govbot.css` tokens so it adapts light/dark (the map viewport stays a
fixed dark surface in both themes so the heat encoding reads); fail-soft — if the paths file doesn't
load the entry stays hidden and the rest of the page is unaffected. Below it, the classic
"Recent activity" card strip remains
(`#recent-list`, newest recorded actions, unfiltered, click → bill modal — capped at
`RECENT_PER_STATE` (2) per jurisdiction so one busy state can't monopolize the strip, up to
`RECENT_MAX` (12) cards; each card shows the state badge · bill id · relative date · title · latest
action · the bill's **topic chips** (`.rc-tags`, colored dots from `state.tagColor`, omitted when a
bill has no tags); a gold `.recent-toggle` "Show / Hide recent activity" pill in the section
head **is always visible and toggles the strip open/closed at any time** (`toggleRecent()` flips a
`recentPref` override that beats the default), so a reader can collapse it even without searching.
Its **default** is expanded while browsing and **collapsed while a search query is active** (an
unfiltered strip that would compete with the results); `syncRecentCollapse()` reads that default and
resets `recentPref` whenever the search state flips, so a fresh search starts collapsed and clearing
it restores the expanded default, while the pill's explicit choice sticks in between. While searching
the **whole section header** (`.recent-toggleable .section-head-lite`) is also a click target (the
pill `stopPropagation`s so it isn't double-toggled). Below Recent activity, above the analytics, sits **one** search-and-filter block
(`.explore-search`): a single search box (`#f-search`, "Search bills, sponsors, topics…", the
page's only bill search — the old top hero search and the per-table search box were consolidated
into this one). The **`#filters` block** (Topic multiselect `#f-tags` + Session/Chamber/date behind a
"More filters" `<details>` + Clear) **was moved out of `.explore-search` and into the results popup**
so a reader can filter one state's catalog in place (see the results-popup paragraph below). **There
is no State dropdown** — jurisdiction is picked from the map / list entry above; it drives
`state.filters.states`, which stays the underlying filter (`syncMultiSelects` guards for the removed
`#f-states`). The redundant
`.explore-hint` copy under the search box was removed (the placeholder already conveys it). **This
`.explore-search` block is currently `hidden`** (per request; it now holds only `#f-search`) — the
map's "Open all bills" flow drives the results — but its elements stay in the DOM so the search JS
keeps working. The
**"Overview & charts"** analytics block (tiles + jurisdiction/topic/month charts) was **removed**.
Clicking **"Open all N bills"** (or a list-card) **pops the filtered bills up as a card** over the
current screen rather than switching the page inline: `setMode()` (called from `render()`) toggles a
body-level **`#results-overlay`** (a `.results-overlay` mirroring the bill modal — `position:fixed`,
dimmed + `backdrop-filter` blur, `z-index:90`, `.results-overlay[hidden]{display:none}`) whenever a
filter/search is active, and adds `body.results-open` to lock scroll; the map entry + Recent activity
stay on screen as the dimmed backdrop. The popped `#results-card` (`.results-modal`) animates in with
`@keyframes results-pop`, carries an **X close button** (`#results-x`, top-right) and a
jurisdiction-named title (`resultsTitle` → "Wyoming bills (N)"). **Every sortable column header
carries a persistent sort arrow** — a muted up/down glyph (`.arrow.is-idle`, "⇅") when idle so the
column reads as sortable, and a bright single caret (`.arrow.is-active`, gold ▲/▼) plus `aria-sort`
on the actively-sorted column (the old "Click a column header to sort" subtitle was removed as
redundant). The card carries a sticky
**in-card search box** (`#results-search`) directly under its title that filters within the popped-up
catalog (e.g. just that one state's bills — the same `state.filters.search`, so the count in the title
tracks it live); it and the hidden hero box `#f-search` mirror each other via `reflectSearch()` (both
share one debounced input handler, each skipping the box being typed in so the cursor doesn't jump).
**Below the in-card search the catalog carries its own filter row** (the `#filters` block — Topic
multiselect `#f-tags`, plus Session / Chamber / Last-action-date behind a "More filters" `<details>`,
and a "Clear filters" `#f-clear` button; styled `.results-modal .filters` with a hairline under it).
It was moved out of the hidden `.explore-search` block into the results popup so a reader can narrow
one state's bills by topic/session/chamber/date; it drives the same `state.filters` as before and the
title count tracks it live. **Clear is jurisdiction-aware** (`clearBillFilters(keepState)` +
`inOpenCatalog()`): inside an open state catalog, Clear (the `#f-clear` button and the empty-state
"Clear filters") resets the catalog's own filters — topic/session/chamber/date **and** search — but
**keeps** `state.filters.states` so the popup stays open on that state (only clearing the state closes
back to the map); outside a catalog it's a full reset. `#f-clear`'s enabled state follows the context
(`catalogFiltersActive()` in a catalog, `anyFilterActive()` otherwise).
Opening a state (`eeApplyFilter`) starts its catalog fresh (clears topic/session/chamber/date/search);
Closing it — the X, a click on the
backdrop, or **Escape** (deferred to the bill modal when that is open above it) — calls `eeBackToMap`,
which clears `state.filters.states` (and the in-card search) so `setMode` hides the overlay. Its Title + latest-action cell
text is `--text-primary` (full-contrast, not dimmed). The "No bills match" empty state (`#empty`) now shows
**only when a filter/search is active and nothing matches** — `renderTable` hides it unless
`anyFilterActive()`. Both `.gb-state` and `.gb-loading` set `display:flex`, which (author CSS)
beats the UA `[hidden]{display:none}`, so the shared `govbot.css` now carries a
`.gb-state[hidden], .gb-loading[hidden] { display:none }` rule that re-asserts `[hidden]` for both
state components everywhere — without it the legislation empty state showed under a full table, the
**elections** page kept a *forever* "Loading Illinois & Chicago races…" spinner (its
`$("loading").hidden = true` never took) and a stray "No races match" box, and the hearings empty
state was a bare dashed box. **Opening a bill plays a book-open flourish** (`playBookOpen`): an open book
drawn **entirely in CSS** (no raster — so no stray grey box, and the wordmark never clips) — a navy
gold-trimmed cover, two splayed cream page-faces around a spine valley, **colourful fore-edges down BOTH
sides** (`.side-l`/`.side-r`, the seven-colour blocks tilted with `rotateY(±30deg)`), **big colourful
sparkles** rising off the spread (`.spark`, `@keyframes book-twinkle`), and the full gold **"Govbot"**
wordmark below (`.book-wordmark`), with a soft warm halo (`.halo`) standing in for the old grey
backdrop — with **five cream pages** flipping over its spread in a
slow, staggered riffle (`.book-fx .pages > .page` p1–p5, hinged at the spine, a one-shot
`@keyframes book-page-flip` −14°→−166°; the veil holds ~2.4s so the whole
riffle plays before the card reveals), all over a dark veil (`.book-fx`, appended to `<body>` at a
z-index above both the bill modal and the results overlay so it always reads on top), then the details
card swings open
like a cover (`.book-open-in` → `@keyframes card-book-open`, a `rotateY` reveal). It's decorative —
skipped entirely under `prefers-reduced-motion` (the card just fades in) and guarded by `modalKey` so
a superseding open never disturbs the new card. The bill modal shows the topics (section heading
**"TOPIC(S)"**) as **colour-coded tags** (`.m-topic` — each tinted in its topic's `state.tagColor`
series colour with a matching dot, so a topic reads the same colour as in the table/recent strip)
**above** the Status section (moved up from below the sponsors). Below the topics it
leads with an inferred **status timeline** (Introduced → Committee → Passed House → Senate →
Governor, `billStageIndex`/`stageTimeline`, using the shared `.gb-timeline` component; its
**current** node — the bill's latest recorded stage — pulses via `@keyframes gb-node-pulse` (a
clearly visible grow, `transform: scale` up to 1.28 so it doesn't reflow the label, plus an
expanding gold halo), off under `prefers-reduced-motion`, so the eye lands on where the bill is now).
**Opening a bill makes the URL a shareable deep link**: `openDetails` pushes `#bill=<billKey>` (via
`history.pushState`, a `modalPushed` flag guarding it — no push when the modal was opened *from* a
`#bill=` link, and a `replaceState` swap when jumping straight from one bill to another so history
doesn't stack), so the address bar / "Share this bill" link is always copyable and bookmarkable, and
**browser Back closes the modal** (a `popstate` listener). `closeDetails(fromPop)` pops that entry
(Back == close) or strips a deep-link hash it didn't push, and cleans up only when the close didn't
come from the pop; the ✕ handler calls `closeDetails()` with no argument so the click event isn't
mistaken for `fromPop`.
`elections.html` has been reframed **ballot-first**: a Capitol hero — `#hero-flag` (populated by
`renderElectionHero`) shows `assets/il-capitol-building.png`, the **Illinois State Capitol** as gold
line-art (keyed to a transparent background so it drops onto the dark hero in both themes), with a
separate **waving Illinois flag** SVG (`.cap-flag`/`.ilwave`, a CSS `@keyframes capflag`, off under
`prefers-reduced-motion`) overlaid on the building's flagpole so the flag animates. This replaced the
earlier flag-on-a-pole SVG and its JS ripple; the old mouse-following "flag cursor" flourish is also
gone. Copy: "Illinois Elections" / "Know who's on
your ballot before you vote." / a dynamic "Next election" line (the earlier "Explore races" CTA
button was removed)) and an **"Important Dates"** panel
(`#ballot-picker` / `#ballot-cards`, one card per distinct `ballot_date` with its stage label +
office/candidate counts, `renderElectionHero`). These cards are **informational only** — plain
`<div>`s, not buttons, with no click/hover/focus and **no ballot filtering** (all races are shown by
default — `init()` calls `revealAllSections()` unconditionally at the end of load, so the bottom
"Browse by office" grid shows on **every** load including a first-time direct visit with no `#race=`
deep link and no saved view, not only when a deep link or the map/finder reveals sections); the
earlier "click a ballot to filter" behaviour was removed. The rich race engine (groups, five drawers, calendar,
Springfield, picker) is unchanged. The office-card area's **stat scorecards (`#tiles` /
`renderTiles`) and the ballot-date / "Only races with candidates" / Clear / "Follow every race"
controls were removed** — the `#filters` bar now holds **only the search box** (`#f-search`,
placeholder "Search races & candidates…", widened to fill its row so the placeholder isn't
clipped). The ballot-date filter is still driven by the hero ballot cards + calendar (its removed
`#f-ballot`/`#f-hascands`/`#f-clear`/`#rss-all` refs are null-guarded; `#rss-pop`/`openRss` stay for
the per-race and Springfield feeds), and the empty-state "Clear filters" button calls a null-safe
`clearFilters()`. **The standalone Illinois county finder (`#bfinder`,
`renderBallotFinder`) was removed** — the Explore Chicago map below (retitled "Find your ballot")
is the single ballot entry now, so the redundant second IL map + county/ward picker are gone. The
`renderBallotFinder`/`resolveBallot` functions and the `#bf-*` guards remain defined but uncalled
(and `cmOpenWardBallot` still guards `#bf-ward-sel`/`#bf-chips`), so nothing throws. What that finder
used to be (kept here for context): a **"Find your ballot"** map-first
entry (`#bfinder`, `renderBallotFinder`): a geographic **Illinois county choropleth** — all 102
county paths + the state outline from the committed `assets/il-counties.json` (generated from US
Census county geometry, equirectangular north-up with a cos(lat) correction; fetched fail-soft, so
the whole finder stays hidden if it doesn't load), rendered on the same dark viewport as
legislation's map with gold county borders, **Cook County (Chicago) highlighted and gently pulsing** (`.bf-cty.is-cook`, marking the covered area),
a gold glow outline, and the selected county pulsing (`.bf-cty.is-sel`). The map SVG is sized with
`height: 100%`, so `.bf-viewport` must carry a **definite `height`** (not just `min-height`) — a
percentage height resolves to 0 in WebKit/iOS Safari when the flex-item parent's height is
indefinite, which rendered the whole map as a **black square on mobile**; the viewport is 300px
(260px under 760px) — deliberately kept small since the detailed Chicago exploration lives in the
separate **Explore Chicago** map below. (Legislation's US map avoids the same bug via `aspect-ratio`
on `.ee-mapwrap`.) A **place picker** beside it (Chicago /
Elsewhere-in-Illinois chips + a Chicago **ward** `<select>`) and clicking a county both resolve a voter to their ballot
(`resolveBallot`): Chicago → the city groups (citywide, council, cps_board,
police_district_council) **plus** the statewide/federal groups, with the 50-ward Alderperson list
narrowed to the chosen ward via a new `state.filters.ward` (matches `r.district === "Ward "+N`, only
on the `council` group); any other county → statewide + federal only, with a note that local races
for that county aren't tracked yet. The **coverage scope** is stated in the hero as an `.el-cov` line ("**Live now:** local races for
Chicago & Cook County, plus every Illinois statewide & federal race. Local races for the rest of
Illinois are coming soon." — only "Live now:" bold); **Cook County pulses** on the map to mark the
covered area, and the "Elsewhere in Illinois" chip sets a matching "coming soon" status. (The earlier
inline `.bf-coverage` note, the map legend, and the corner "click a county" hint were removed to keep
the finder clean.) It drives the same `state.view` Set + `applyView()` the picker
uses (so the sections reveal and the page scrolls to `#groups`), and `#f-clear` also drops the ward
and the finder's selection. The lookup is **map + picker only** (no address/ZIP geocoding) so it is
fully offline and deterministic. The page's ballot entry is the **"Find your ballot"** section
(`#chimap`, `renderChicagoMap`, titled "Find your ballot" / "Pick where you live and we'll show
every race you can vote in."): a **colorful, zoomable geographic choropleth of Chicago** with a
**Wards (50) / Neighborhoods (77) toggle** (`cm-seg`). The detail card (`.cm-detail`) is a **fixed
height matching the map (560px; auto/stacked under 820px) and scrolls internally** so a long ballot
list doesn't unbalance the row (`.cm-body` is `align-items: start`). A small **Illinois locator inset** (`.cm-locator`,
`cmBuildLocator` — the `state_d` outline + Cook County from `il-counties.json`, a gold Chicago dot at
Cook's centroid) sits to the left with **two dashed callout lines** (`.cm-connect`, `cmDrawConnector`)
fanning from the Chicago dot to the big map's corners — the classic magnifier/"you-are-here" device;
it's anchored to element rects (redrawn on resize) and hidden under 820px (the finder already shows
Illinois on phones). Geometry is the committed `assets/chicago-map.json`, generated
by **`scripts/build_chicago_map.py`** — it fetches the two authoritative boundary sets from the City
of Chicago open-data portal (the 50 City Council **wards**, dataset `p293-wvbd`, and the 77
**community areas**/neighborhoods, dataset `igwz-8jzy`), projects BOTH into one shared SVG space (so
ward and neighborhood polygons overlay exactly), Douglas-Peucker-simplifies each ring, and — crucially
— computes the **neighborhood↔ward correspondence by spatially sampling a dense grid** (each point's
community area and ward found by point-in-polygon, co-occurrence tallied), so every area carries its
ranked overlapping wards and vice-versa (validated: Loop→42, Lincoln Park→43/32/2, Lakeview→44/32/47/46,
Hyde Park→5/4, O'Hare→41). Pure stdlib (no geo deps), `--self-test` for the geometry helpers; fail-soft
(a portal outage leaves the committed asset in place). The map has **zoom + pan** (± / reset buttons,
wheel-zoom about the cursor, drag-to-pan with clamping, a `cmDidDrag` flag so a drag isn't a click; the
zoom buttons / `.cm-zpct` / `.cm-hint` carry **fixed light colors**, not theme tokens, since they sit on
the always-dark map viewport and would otherwise go dark-on-dark and vanish in light mode) and
each region is a `.cm-reg` filled from a vivid `CM_PALETTE`; the selected region has a **large, high-contrast pulse** (`@keyframes cm-pulse` grows the gold outline 2.5→6.5px and the glow to 26px) as a low-vision aid. The
`.cm-mapwrap` carries a **definite height** (560px; 440px under 820px) so the `svg{height:100%}` isn't
the WebKit black-square bug. Clicking a region fills a **detail card** (`.cm-detail`, styled like
legislation's `.ee-detail`): a **ward** shows "Ward N", the neighborhoods it covers, then the **actual races on that ballot as
expandable rectangle bars** (`cmRaceItem`): the ward's Alderperson race (`cmWardRace`, `r.district ===
"Ward "+N`) plus every race that's the same for all Chicago voters (`cmCommonRaces` — citywide offices,
CPS Board President, the Illinois statewide `il_exec` offices and the U.S. Senate seat). Clicking a bar
expands it in place to the full details (`cmRaceDetails` — each candidate with party, petition status,
money and an official-source link), and a single boxed `cmDistrictNote` (`.cm-more`) warns
**"⚠️ Address-specific races — CPS subdistrict, police district council, Illinois Senate & House, and
U.S. House. Open the other ballots below to see them."** (the earlier "See Ward N's full ballot →"
button was removed; `cmOpenWardBallot` remains defined but uncalled, so nothing throws); a
**neighborhood** shows its name (`cmNiceName`
title-cases, fixes O'Hare/Lakeview/McKinley Park), how many wards it spans, the same expandable common-race bars, and **tappable ward chips** (→ switch to ward view, select +
`cmFocusRegion` zooms to it, since the alderperson varies by ward). Below Explore Chicago sits a
**2026 federal-midterm callout**
(`#midterm-banner`, "The 2026 midterms decide control of Congress") — shown only when the federal
races are present; clicking it (`revealFederal`) adds the `us_senate` + `us_house` groups to the
view and scrolls to the U.S. Senate section (each race `<section>` now carries an `id="grp-<group>"`
anchor). The federal races themselves (Illinois's U.S. Senate seat + all 17 U.S. House districts on
the Nov 3, 2026 ballot) were already in the data; the callout just surfaces them.
The default view was **decluttered** (it had too many overlapping entry points): the finder's
duplicate "Coming up" list, the **"Build your view" section-picker UI** (`#picker` / `#picker-empty`
— the `state.view` / `applyView` machinery and its `picker-all` button stay in the DOM, hidden, so
`revealAllSections()` and the ballot cards still reveal the right sections) and the big "Two big
ballots ahead" intro paragraph were all removed, leaving a clean stack: Hero → **Find your ballot**
(map + place picker, vertically centered) → midterm callout → the two **"What's on your ballot?"**
date cards → the revealed races → the sources cabinet (now collapsed). The **election calendar**
(`#calendar`) is now **always shown** (ungated — visible whenever `#cal-grid` has cards) with the
**current/next timeline milestone pulsing** (`.tl-item.next .tl-dot` → `@keyframes tl-pulse`, a **big** scale-1.32 + wide-ring pulse for low-vision readers).
The standalone **"Recent Illinois legislative activity"** section was **removed and merged into the
Springfield "rules of the game" section** (see below): the general recent-activity feed now rides that
section's **"Other"** tab. `loadIlRecent()` still fetches the legislation `data.json` fail-soft
(`state==="il"`, newest recorded action first) to populate `state.ilBills` + the shared
`state.ilTagColor`, but instead of its own section it feeds the "Other" tab and re-renders Springfield.
The **"Explore entire catalog of IL bills ↗"** button (`#ilr-explore`, `legislation.html#state=il` in a
new tab, via the `#state=<code>` deep link → `eeApplyFilter`) was relocated to the bottom of the
Springfield section.
`hearings.html` has been reframed **participation-first**: an "Have your say." hero (overline
"Hearings & Public Comment", tagline "Government isn't just something you watch — you can
participate."), and a
detailed gold White House line-art (`assets/whitehouse-hero.png`, a transparent-background raster
so it drops onto the dark hero in both themes); the America-250 `250th` fireworks
brandbar is kept. (The earlier "See upcoming hearings" CTA button was removed.) **Below** the hero
sits a `.hh-below` strip carrying two things: the live metrics as a row of **gold civic stat tiles**
(`.hh-stats` / `.hh-stat` — theme-aware, gold display numerals on `--surface-1` glass with a
gold-tinted border: **two** tiles, "N upcoming hearings and open to public comment" (the count that
are both upcoming and comment-open) and "N jurisdictions"), and a **jump-to-jurisdiction nav**
(`.hh-jump`, `#hh-jump`) — a "Jump to" label plus one pill chip per jurisdiction (its full name +
a `.jn-count` count) linking to that section's `#hg-<code>` anchor (each `.hgroup` gets
`id="hg-<code>"` in `renderHearings`, ordered federal-first like the groups; `.hgroup` has
`scroll-margin-top` so the sticky header doesn't cover the target). **Each pill is a coloured chip**
wearing its jurisdiction's section accent (`--jc`, set per pill in JS from the same `HG_ACCENTS`
palette + group order the section borders use) — coloured text + matching border over a faint tint —
so a reader recognises a state by colour and the pill matches the section it jumps to. The nav is hidden with fewer
than two jurisdictions. Each hearing still makes participation obvious: a green **"Public comment open"**
badge on the date column and the witness-slip/comment action elevated into a filled green
`.file-link` pill. The `<title>` was also corrected (it had been a stray "Legislation Dashboard").
The hearing/participation render engine is otherwise unchanged.
`architecture.html` is retitled **"How Govbot Works"** and now opens with a nontechnical layer: a
plain-English six-stage overview pipeline (`.gw-pipeline`: Government sources → Govbot pipelines →
Validate + normalize → AI topic tagging → Open data → Your dashboards) and a "How it stays
trustworthy" card strip (`.gw-trust`: twice-daily refresh, source lineage, fail-soft, open RSS,
open source, known limits), with the existing detailed per-pipeline diagrams kept below as the
"full picture" (progressive disclosure). Stale product labels were updated to the new names.
All six pages (including `search.html`) share a single **browser-tab favicon**: an inline SVG data-URI of a **gold gavel**
(flared drum head with a gold center band, a turned handle, and a sound block) on the dark rounded
civic tile, crisp at 16px — replacing the earlier robot-face and per-page torch/pinwheel icons.

**The site root is the civic landing (the main homepage), not a dashboard page.** The whole site —
the mdbook text docs *and* the dashboards — now wears one civic shell. The root
`https://chihacknight.github.io/govbot/` is rendered by **mdbook** from `docs/src/readme.md`, the
civic landing (`.gb-landing`, designed on the "Govbot Landing Revamp" Design canvas). Top to bottom:
a hero with the big green **Liberty** (`dashboard/assets/liberty-hero.png`, a soft green glow behind her
in dark mode, a deep-green rounded "night" panel in light mode so she stays prominent; the square sparks once baked into the PNG were erased and replaced by live **rising embers** — a `.gl-embers` canvas in `landing.js`, positioned in the image's own 520×1000 pixel space, flickering up off the torch and past the crown, a still scatter under reduced motion; the "Open civic data · Government Transparency" overline has a rule on **both** sides; **on phones (≤620px) she stands inside the hero beside the headline**, not stacked below it — absolutely positioned full-height on the right with a left-edge fade, the copy at 62% width over her with a text-shadow, the overline on its own full-width line above her torch, and in light mode the phone hero becomes the same deep-green night panel (dark-token overrides on `.gl-hero`); tablets (621–860px) keep narrower side-by-side columns); a **"By the numbers"** strip
(56 jurisdictions · < 1 min to clone · $0 to tag · 2×/day refresh); a **"Built together" band** (`.gl-crew`, designed on the "Govbot Contributors Opener" Design canvas) right above Projects — the copy "Govbot is built by people who believe government information should be open to everyone." (one subheadline-size block, full-contrast) + an "18 contributors · Meet them ↗" button (→ the GitHub contributors graph), over a dotted workspace of real Govbot pieces (a terminal of real `govbot` commands, a `govbot.yml` excerpt, the merged PR #192 card, `hearings.xml`), with the project's **contributors as live multiplayer cursors** (`landing.js`: coloured arrow + avatar + `@handle` label, a soft-spring glide between spots that never park on — or glide across — the copy, an occasional click ring; half of them on screen at once — 9 desktop / 4 phone — handing over as they pause so all 18 pass through; cursors keep their name tags clear of each other (`crowded()` steers each new resting spot away from other cursors' positions/targets, a gentle vertical separation nudge pushes overlapping tags apart, and `@sartaj` — `.is-lead` — always draws on top); the name tag and chat bubble are `width: max-content` because they sit inside a 22px cursor box — without it Safari shrink-wrapped the tag and clipped names ("@sart"); `@sartaj` is always on screen and, every so often when he pauses, types **"government data as Git"** letter by letter in a Figma-style cursor-chat bubble (`.gl-cur-chat`, held a moment then cleared; shown whole under reduced motion); between wanders the cursors **do real work in the workspace**, one task of each kind at a time — **type a real `govbot` command** into the terminal's live prompt (it then joins the 5-line history), **rewrite the `govbot.yml` topic** (backspace + retype the key and two description lines, excerpts of the real `scripts/govbot-dashboard.yml` descriptions, the edited span tinted in the editor's colour), **stick a note** (`.gl-crew-note`, a short to-do signed "— @handle", fades after ~7s, ≤2 at once) or **drag a selection box** (`.gl-crew-marq`) — notes/boxes only where `freeSpot` finds open canvas clear of the copy and every window (so phones, with no free canvas, skip them); rAF gated by IntersectionObserver + tab visibility, a still scatter under reduced motion). The contributor list (people only, bots left out) is hard-coded in `landing.js` with avatars vendored in `dashboard/assets/contributors/` — refresh both as people join. Below 1180px the copy sits on top and the two code windows go below it (PR/RSS cards hidden); **"Projects built on Govbot"**, a
**carousel** (a CSS `scroll-snap` row so swipe/scroll work without JS; prev/next + named tab chips +
"n / 5" counter driven by `landing.js`; the row's height **follows the active slide** (`fitHeight` → `--car-h`, re-fit by a ResizeObserver as live cards load) so a short slide leaves no empty band, peeking neighbours are capped to that height with a bottom fade, and the chip row auto-centres the active chip with edge fades) of five slides — Legislation (live **recent activity**, one bill
per state up to 4, with the **sponsor avatar chips**: vendored headshot over a party-tinted initials
monogram, first 3 then "+N more", non-person sponsors skipped), Hearings (live calendar-figure rows),
Illinois elections (next ballot date + countdown + what's on it + the ballot after, from
`elections.json`), **Social bots** ("Track legislation wherever you scroll.": the 13 topics, four green platform buttons — Bluesky → `@govboteducation.bsky.social`, Twitter (X logo), Threads, Instagram — and a **live auto-scrolling feed of the bots' real posts**, designed on the "Govbot Bots Feed" Design canvas: `landing.js` fetches, fail-soft and only once the carousel nears the screen, the bot repo's own dashboard data `frankies2727.github.io/CHN-SocialMedia-Govbot-Main/data.json` (its `feed`: exact post text + URL + `posted_at` for Twitter/Threads/Instagram, the chip from the record's `date` + `action`) and Bluesky's public AppView API (`getAuthorFeed` for the 13 topic accounts; each shown post's dated action line is read from the bot's own reply via `getPostThread` — none → no chip, never guessed); the newest 5 per platform are interleaved (20 posts), each showing "Posted: <date>" (Central time), a **gold** action chip / topic / "View post ↗" via the landing-only true-gold `--gl-fgold` (the brand `--gb-gold` is green), the list rendered twice so the rAF scroll wraps (copy `aria-hidden`, untabbable), paused on hover/focus/touch and while the slide isn't active, static under reduced motion), and a dashed
"Your project" slide; **"Build your own"** (install / run / clone steps with copy buttons + the
"ask an AI" `llms.txt` prompt); **"Our story"** timeline (2022→2026, linking the History pages; the current 2026 point pulses big — a growing glow core plus an expanding ring; then a dashed line runs to a hollow **"Next · On the roadmap"** node: four linked cards distilled from the open GitHub issues — MCP/ChatGPT-Claude #25, easier installs #19, more of government #28, fresher data #111 — plus a "Pick a good first issue ↗" link led by a GitHub mark in the same green outline chip as the footer social icons (`.gl-gh`); refresh them as issues close) +
**Questions** FAQ; and the **"From the firehose to the point."** canvas animation as the finale, its heading followed by `.gl-finale-sub`: "Govbot is an open-source infrastructure and data system that turns U.S. government legislative activity into structured, version-controlled, AI-processable data that anyone can build on." (its old "Democracy happens every day…" overline moved up into the "Built together" band as new copy). The
behaviour lives in **`docs/theme/landing.js`** (`book.toml` `additional-js`; a no-op on every page
without `.gb-landing`). Its live cards and the firehose canvas are **ported verbatim from the retired
dashboard homepage** — only the fetch/link paths gained a `dashboard/` prefix (including the
`legislator_images.json` photo paths) — and the old made-up placeholder rows were replaced by the shared
`.gb-loading` / `.gb-state` (error + recovery link) components. It also **swallows ←/→ on the landing**
(capture phase) because mdbook's `book.js` maps them to previous/next chapter; inside the carousel
they move between slides (doc pages keep chapter navigation). The landing uses `<span class="gl-mono">`
/ `.gl-code-t`, never `<code>`, because `book.js` runs highlight.js over every `<code>` element; and
mdbook wraps every `<h1>`–`<h3>` (raw HTML too) in an `a.header` anchor, which the landing CSS
neutralises. mdbook's `.content a:link` colour out-ranks plain class rules, so the landing pins its
button/card/timeline link colours with `!important`. The full project reference (install, commands,
DuckDB, data catalogs, contributing, history, FAQ) is `docs/src/about.md`, kept in sync with
`README.md` (linked as "All commands & SQL" / "Govbot docs ↗"). mdbook wears the civic skin via a custom theme in **`docs/theme/`**:
`index.hbs` injects the shared `.gb-header`/`.gb-drawer`/`.gb-footer` (all nav/asset hrefs prefixed
`{{ path_to_root }}`, pointing into `dashboard/…`; brand → `{{ path_to_root }}` = the landing) and
loads `dashboard/assets/govbot.css` + `govbot-shell.js`; `head.hbs` is the pre-paint
`localStorage['govbot-theme']` snippet; `mdbook-civic.css` (via `book.toml` `additional-css`) maps
mdbook's own CSS vars onto the civic tokens (`!important`, beating mdbook's `html.rust`/`html.coal`
theme classes), offsets the sticky header, hides mdbook's 3-way theme picker (the civic
`[data-gb-theme-toggle]` drives theme), and holds the `.gl-*` landing styles (plus the ported
`.activity-row`/`.ar-*`/`.mini-date`/`.stream-*` rules, scoped to the landing) +
`body:has(.gb-landing)` full-bleed rules (sidebar/menu-bar hidden on the landing only). The landing
HTML in `readme.md` keeps **each `<section>` as one unindented block with no internal blank lines** —
CommonMark ends an HTML block at a blank line and would render the next indented lines as a code
block. The **old dashboard homepage `docs/src/dashboard/index.html` is retired to a tiny redirect to
`../`** (the root landing, preserving any hash), so there's one homepage; the five dashboard pages'
brand/home link now points to `../` and their "Govbot docs ↗" footer/hero links to `../about.html`.
Because this touched `docs/theme/**` + `docs/book.toml` (neither `dashboard/**` nor `*.md`), the
migration merge ran one full ~40-min build; later landing/doc tweaks (only `*.md` or `dashboard/**`)
stay on the fast path. The shell/search/nav details below still describe the dashboards.

The Pages site has a **civic landing homepage (mdbook root) plus three dashboards plus a
How-Govbot-Works page plus a global search page**:
`docs/src/readme.md` → the site root (the **civic landing / Homepage**),
`docs/src/dashboard/index.html` (**redirect** → `../`, the old dashboard homepage retired),
`docs/src/dashboard/legislation.html` (**Explore Legislation** — the legislation dashboard,
formerly `index.html`; deep links are `legislation.html#q=<billid>`),
`docs/src/dashboard/hearings.html` (**Hearings & Public Comment**),
`docs/src/dashboard/elections.html` (**Illinois Elections**),
`docs/src/dashboard/architecture.html` (**How Govbot Works** — a static, no-data explainer of all
three backend pipelines), and
`docs/src/dashboard/search.html` (**Search** — the site-wide search page).

**Global search is cross-site.** The shared header/drawer `.gb-search` boxes (wired in
`govbot-shell.js`) route to `search.html#q=<query>` (not `legislation.html` any more). `search.html`
shares the standard shell and, on load or `#q=`/`?q=` change, fetches `data.json`, `elections.json`,
`hearings.json` and `people.json` (all fail-soft) and searches them in-browser, rendering **five
categorized result groups** — **Bills** (id/title/sponsors/tags → `legislation.html#bill=<key>`),
**Legislators & sponsors** (the whole `people.json` roster, name/party/area, party-coloured →
`legislation.html#q=<name>`, which filters bills by that sponsor), **Election candidates** (official
+ potential, each tagged → the race, see below), **Races & offices** (office/district/ballot →
the race), and **Hearings** (title/committee/bill → `hearings.html#hg-<code>`). Each group shows a
count, caps the list at 60 with a "refine" note, and there are jump chips + a live result total.
The page is `search.html` is authored by assembling the shared shell (favicon, header, drawer,
footer) with the page's own hero + `#s-results`; input is debounced and mirrored into the hash.
Candidate/race results deep-link as **`elections.html#race=<id>`** (or `#office=<group>`): the
elections page tags each race card with `data-race-id`, and `applyElectionsDeepLink()` reveals every
section, then `alignDeepRace()` (called at the end of every `render()`, so late maps/incumbent
fetches don't lose the place) scrolls to and briefly flashes (`.race-flash`) that race.

**Every page now wears the same shell as the Homepage** — the old
per-page tab bar + brandbar (logo + 3-button light/auto/dark theme pill) have been **retired**.
All six pages (the five flagships plus the utility `search.html`) share, byte-for-byte, the global-nav header (`.gb-header`: the `assets/govbot-mark.png`
robot logo linking to the Homepage, the Projects / Data mega-menus + How Govbot Works /
**GitHub Repo** plain links (the "GitHub Repo ↗" link → the repo, in a new tab; formerly labelled
"About"), the global `.gb-search`, and a single `[data-gb-theme-toggle]` icon button), the
mobile `.gb-drawer` (hamburger → flat link list + search), the civic `.gb-footer` — **the header, mobile drawer and footer are each one template for the whole site**: `docs/theme/header.html` (header + drawer) and `docs/theme/footer.html` are the single sources, written into `docs/theme/index.hbs` (homepage + doc pages) and every `docs/src/dashboard/*.html` page by `python3 docs/theme/sync_shell.py` (`--check` reports drift); edit the templates, never a page copy. Placeholders: `{ROOT}` site-root folder, `{HOME}` the homepage (`index.html` on mdbook pages, whose `path_to_root` is empty at the top level), `{DASH}` the dashboard folder. The current page's nav/drawer link gets `aria-current` at runtime in `govbot-shell.js` (a same-site path match), not in the markup; search forms carry `action="{DASH}search.html"` so they work from any page. **Header nav:** **Projects ▾** (only things built on Govbot: Legislation, Hearings & Public Comment, Illinois Elections, + "All projects" → the homepage carousel) · Data ▾ (the Follow ▾ menu and the homepage's "Follow along" RSS slide were removed; RSS feeds stay linked from each dashboard) · How Govbot Works · About · GitHub Repo ↗; between 861–1180px the search box collapses to a search icon (`.gb-search-btn`) so the nav never wraps. Its headings are `div.gb-footer-h[role=heading]`, not `<h4>`, because mdbook turns every `<h4>` into a self-link; all footer copy is full-contrast `--gb-text` with green headings (a 30%-black
mix of the page colour in dark mode, the plain `--gb-surface` in light mode so it isn't a grey slab; the
`assets/govbot-mark.png` robot logo + brand blurb + a `.gb-social` row of gold-outline social chips —
Bluesky / Threads / X / Instagram, styled in `govbot.css` off the `--gb-gold` tokens so they adapt
per theme — plus Explore / Transparency / Community columns), and the floating `.gb-to-top` liquid-glass "Back to Top" pill —
all wired by the shared `assets/govbot-shell.js` (so every page also loads that script). The active
section is marked `aria-current="page"` in the header's Explore mega-menu (and the top-level How
Govbot Works link on architecture) + the drawer. Each flagship keeps its own **signature hero**
below that shared header: legislation's search hero, elections' waving Illinois flag, architecture's
plain-English pipeline, and hearings' self-contained "night sky" hero panel — the America-250
`250th` fireworks canvas (`#fw-canvas`) relocated out of the retired brandbar into `.hh-hero` (dark
in both themes so the bursts read). The per-hero "govbot docs · GitHub repo" links were dropped from
hearings and elections (the footer already carries them). **External-link convention:** any link that
leaves the dashboard (`github.com`, `chihacknight.org`, official-source sites, and the mdBook docs at
`../index.html`/`../dashboard-guide.md` — anything outside `github.io/govbot/dashboard/`) opens in a
new tab (`target="_blank" rel="noopener"`) and carries a trailing `↗`; links that stay within
`/dashboard/` (the sibling pages, in-page anchors, RSS `.xml` feeds, deep links) stay same-tab with no
arrow. **Every generated RSS feed** (both
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
from" cabinet is **expanded by default** (`<details open>`). The hearings
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

**`deploy-docs.yml` fast path (frontend- and docs-only changes).** The full data pipeline (~40 min) runs
on the twice-daily **schedule**, on **manual dispatch**, and on any **push to main that touches a file
the data pipeline reads** — `actions/**`, `scripts/**`, `schemas/**`, **this workflow file**, seeds, … A
push to main touching **only site files** — anything under **`docs/**`** (the landing, docs pages, the
civic theme `docs/theme/**`, `book.toml`, images, the dashboards, and any future sub-site at
`docs/src/<name>/` → `github.io/govbot/<name>/`), Markdown docs anywhere (`*.md`), the root `llms.txt` /
`catalog.json`, `tamara-notes/**`, or `.github/**` other than `deploy-docs.yml` — and **every pull
request**, take a **fast path**: a `Determine build scope` step (`git diff` of the pushed range — it strips
those paths, and full-refreshes only if anything else remains; PRs always skip) sets `refresh=false`, and the
pipeline steps are all guarded `if: steps.gate.outputs.refresh == 'true'`, so they're skipped and mdbook
builds + deploys with the committed data. Markdown docs never feed the data pipeline, so a docs-only
change (updating this file included) stays fast; mdbook still rebuilds so any published `.md` page
updates. Everything is committed with real data **except** `data.json` (a tiny sample) and the
two `.gitignore`d artifacts (`il_summaries.json`, `legislator_images.json` + `assets/legislators/`), so a
full build snapshots those four into a rolling `actions/cache` (`govbot-built-data-<run_id>`, restore-key
`govbot-built-data-`) and the fast path **restores** them. Safety valve: on a push to main, if that cache
is missing or holds only the sample `data.json` (< 100 KB), the run **falls back to a full refresh** —
so a frontend deploy never publishes stale/sample bills. PRs never deploy, so they just build-check.

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
races (`ballot_stage: "general"`, ballot date 2026-11-03); each statewide/federal district now has a
locator on an Illinois-outline silhouette (see the scrape-maps paragraph — `buildRaceMap` picks the
space from `maps.json`), and the
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
Dashboard's Bill column is plain text (the official-source link lives in the details card, labelled
by whose site it is — "Official Michigan Legislature site ↗", "Official U.S. Congress site ↗",
"Official D.C. Council site ↗"). Each
bill row also has a **"Share"** button beside "Details" (and a **"Share this bill"** pill in the bill
modal, placed **above the Status section** — `.m-sharerow`, not in Sources) that copies the **exact-bill deep link** `legislation.html#bill=<state~session~id>`
(`billShareUrl` → `billKey`); opening it lands straight on that bill's modal (`applyDeepLink`'s
`#bill=` branch → `openDetails`). `#q=<billid>` deep links still work (id lowercased, punctuation
stripped, e.g. `#q=sb813`): they pre-filter the search — which matches ids ignoring
spaces/punctuation — and a `hashchange` listener re-applies the `#q=` filter live. The details card lists each **sponsor/co-sponsor with their current party — the party spelled
out in full and color-coded (`partyTag`: Democratic blue, Republican red, others neutral; a faint tint
of the party color fills the pill) — and seat** (chamber + district, e.g. "Senate District 39"),
resolved from the `people.json` roster: `scripts/build_people_roster.py` emits `[given, full, party, area]`
per legislator (from the Open States people repo — the current party role and current legislative seat;
name fields keep their positions so resolution is unchanged, party/area degrade to "" when
unknown). **Congress is included** (Open States `data/us` → the `usa` key, data.json's federal code)
with federal seat labels from `_federal_area` — "U.S. House · NY-7", "U.S. House · ND at-large" (from
"ND-AL"), "U.S. Senate · Indiana" — so federal sponsors show party + seat too. Offline-tested in
`scripts/test_build_people_roster.py`. The frontend matcher (`matchLegislator`)
resolves a sponsor to that roster entry robustly: it strips a trailing generational **suffix**
("Marcus C. Evans, Jr.", "Joseph P. Addabbo Jr.", "Emil Jones, III") so the surname isn't read as the
suffix, and falls back to a **two-word surname** key ("Ochoa Bogh", "Avila Farias") when the last word
alone doesn't resolve — both were dropping the party on a lot of sponsors across states — while still
refusing to guess an ambiguous bare surname (several "Smith"s → no party rather than a wrong one). It also attaches a top-level
`springfield` list — the **"rules of the game"**: IL bills from the legislation
`data.json` tagged `elections & voting` or `education` (the elected CPS board, ward/runoff
rules, campaign finance), cross-referenced with `hearings.json` for upcoming ILGA hearings,
shown on the page as context *beside* the races (never mixed into candidate lists) plus a
`springfield.xml` feed. The section is **always shown** when there's any Illinois content
(`revealSpringfield`, ungated like the calendar) and carries **three filter tabs — Elections & voting
/ Education / Other** (the old "All" tab was removed; default is Elections & voting). Elections & voting
and Education merge the curated `springfield` list (which carries ILGA hearing info) with the IL bills
from data.json tagged with that topic (deduped by id, so the tabs stay filled even when the curated list
is empty); **Other**
is the general recent IL activity merged in from the retired standalone section — `state.ilBills` (all
tracked IL bills) minus anything already tagged elections/education, newest recorded action first. **Every
tab shows only bills with activity in the last 6 months (`SF_RECENT_DAYS`, newest first) and is capped
at `SF_MAX_PER_TAB` (9)** to stay scannable. The one `#sf-search` box (its own full-width
row so its placeholder isn't clipped) filters within the active tab (id/title/sponsor/action/tags). Each
Springfield bill card (`renderSpringfieldBill`) leads with an **"IL" badge before the bill id**, its
**topic tags as colored-dot chips** (`sfTagColor` → the shared `ilTagColor`, so a topic reads the same
color as on the legislation site — Other bills carry general topics like housing/healthcare), and a
trailing **"↗"** marking that it opens in a new tab, and is **clickable** — the
whole card opens that bill's **full details** (its modal on the legislation dashboard, via
`legislation.html#bill=il~<session>~<id>`) in a **new tab** so it doesn't replace the elections page
(the inline "View on Legislation Dashboard" / "Bill
page ↗" links were removed, and the witness-slip link `stopPropagation`s so it doesn't also open the
bill). `deploy-docs.yml` runs this after `data.json`+`hearings.json` are
built so it reads the fresh copies. Fail-soft: with sources down the seed's structure still
ships (empty rosters/springfield), and the deploy keeps the committed sample unless the
fresh run produced candidates or Springfield bills. Parsers are offline-snapshot-tested:
`python3 actions/scrape-elections/test_scrape_elections.py`.

Per-race **locator maps** come from a separate action, `actions/scrape-maps/`. It builds
`docs/src/dashboard/maps.json` in **two coordinate spaces**: a **`chicago`** space (ward
`p293-wvbd` + police-district `24zt-jpfn` boundaries from the City of Chicago Portal, keyed to the
ward / police-council races) and an **`illinois`** space (a statewide silhouette from Census
TIGERweb — the IL state outline, plus the **IL Senate/House 2026** (`SLDU`/`SLDL`, Legislative
layers 1/2) and **U.S. House 120th** (`CD120`, layer 0) districts, keyed to the `il-senate-NN` /
`il-house-NNN` / `us-house-il-NN` races; the Chicago space also carries the **CPS board subdistricts
1A–10B**, keyed to `cps-board-member-Nx`). Each district is tagged with the places it covers, in two
lists: the **Chicago neighborhoods it touches** — Census community areas (`igwz-8jzy`) matched by
grid-sampling the district's Chicago overlap (`district_neighborhoods`), so a statewide/downstate
district carries an empty list — **and the Illinois counties it covers** (the non-Chicago "hoods"),
from Census TIGERweb **Counties** (`State_County` layer 1, `NAME` = "Cook County", …) matched by
grid-sampling the district's own bbox (`district_counties`/`build_county_index`, **not** clipped to
Chicago, so a downstate district still names its counties). A Chicago-area district thus carries both
lists (e.g. a Chicago U.S. House district names its neighborhoods **and** Cook/Will/…); a downstate
one carries only counties. Output: `{view, context, il_view, il_context,
districts:{<id>:{kind,label,space,paths,neighborhoods,counties}}}`. Everything is projected +
Douglas-Peucker-simplified at build time (TIGERweb also trims server-side via `maxAllowableOffset`) so
the file stays ~170 KB and the browser just draws SVG paths. **No government authority publishes the CPS subdistrict boundaries, so those 20 polygons come
from Chalkbeat's public 2026 CPS-board-map GeoJSON (`districts-20-centroids.geojson`, `sub` property)
— the one non-government source, used because it's the sole published geometry; a fetch failure just
leaves CPS races map-less (geometry is never invented).** The frontend
`renderRaceMap`/`buildRaceMap` pick the space from `entry.space`, draw the highlighted **pulsing**
district (`.map-dist`), list **all** the places it touches under two **titled categories** — a
**"Chicago neighborhoods"** group and a **"Counties"** group (`.map-hoods`), each with its category
label (`.mh-label`) as a **highlighted gold, bold, uppercase title on its own line** above the list
(the values stay full-contrast), and extra vertical gap between the two categories — each complete (no
"+N more" truncation; the old "Boundary: City of Chicago" caption was removed), and give the tall IL silhouette
a taller SVG (`.race-map--il`). The maps use one accessible **gold-base / green-highlight** scheme in
both themes: the base silhouette (state or city wards, `.map-ctx`) is filled/edged in **gold**
(`--gb-gold`) with a gold panel border, and the highlighted district (`.map-hi`) is
**green** (`--series-4`) — independent of the per-office `--gc` colour — so the highlight always
pops against the gold base in light and dark mode. On the statewide silhouette a single IL Senate/House/congressional
district is only a few px, so `buildRaceMap` thickens the IL highlight stroke (`.race-map--il .map-hi`
~18u) and **pulses it 16→30u** (`@keyframes rm-pulse-il`) so even a small district reads. **No locator
ring is drawn on any statewide map** — U.S. House, IL Senate and IL House all rely on that thick pulsing
green highlight (the earlier `.map-loc` ring + `pathsCenter` centroid helper were removed per request;
the thick pulse keeps a small district findable without a circle).
**These locator SVGs are built lazily**: because the base outline (city wards, or the IL silhouette)
is redrawn inside every map, eagerly rendering all revealed races' maps was the dominant DOM/paint
cost on mobile — so `renderRaceMap` returns a sized placeholder (`.race-map-ph`) that a shared
`IntersectionObserver` (`_mapObserver`, 400px margin) swaps for the real `buildRaceMap` SVG only when
the card scrolls near the viewport (renderGroups unobserves discarded placeholders; no-IO browsers
build eagerly). Relatedly, the several data files that land at load (maps/people/il_summaries)
re-render through a **rAF-coalesced `scheduleRender()`** so a burst of arrivals is one rebuild, not
several. Fail-soft: a portal/TIGERweb outage leaves the committed `maps.json` in place. Pure helpers
(projection, `point_in_rings`, `district_neighborhoods`, `district_counties`, the id mappers) are
offline-tested: `python3 actions/scrape-maps/main.py --self-test`.

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
frontend renders it as a collapsed, dashed-amber block under each race, headed just "💭 Potential
candidates" — the old "Unofficial · from news / N names" subtitle and the disclaimer paragraph were
removed as clutter, since every name already carries its own status chip ("Announced" …) and source
links. A potential candidate also carries an optional **`party`**, shown as the same color-coded
`partyPill` the official candidates use — but **only when the source text stated it right next to the
name** ("Democrat Jane Doe", "Jane Doe (D-Chicago)", "Jane Doe, a Republican"): `extract_party_near`
reads a party label that *touches* the name and never infers one from a party word elsewhere; a
curated `party` seeded in `elections_seed.json` (or carried from a prior run) is preserved. `deploy-docs.yml` runs it right after the base elections build
(independent of official candidates), twice daily. Parsers are offline-tested in
`test_scrape_elections.py`.

**Party display.** The **"Partisan / Non-partisan" race badge was removed** (the Chicago municipal
races are only nominally nonpartisan). Every candidate's party now shows as a **color-coded
`partyPill`** — the party name itself, no "Party:" label — placed **next to the name** (Democratic
blue / Republican red / else neutral, `partyClass`). The same pill is used for official candidates
(`renderCand`), the current-incumbent box, and potential candidates (when the source stated a party).

**No dupes with the side panel.** The Chicago-map "On this ballot" side panel already shows a
voter's citywide + statewide (`il_exec`) + U.S. Senate + CPS-**president** ballot in full — **plus
their Alderperson** (the map resolves the `council` race per ward via `cmWardRace`) — so all of those
are **omitted from the bottom race sections** (`inSidePanel(r)` filters them out of `render()`'s race
list; `council` is included). The remaining address-specific district races — `il_senate`/`il_house`,
`us_house`, CPS subdistricts, police district councils — can't be pinned from a ward alone, so they
still browse below (the map's `cmDistrictNote` "open the full ballot below" note points at them). A
global-search `#race=<id>` deep link to a side-panel-only race (which is no longer in `#groups`) falls
back to scrolling to the "Find your ballot" map (`#chimap`) once, so the reader can pick their ward and
see it there.

**Browse by office → race popup.** The bottom of the page is a **grid of office cards** (`.office-cards`,
`renderGroups` → `officeCard`): one card per office group in view (CPS Board of Education, Police District
Councils, IL Senate, IL House, U.S. House). Each card shows the office icon/name, its **race + candidate
counts**, a short **blurb** (`GROUP_BLURB[g]` — each explains what the body does and **why the office
exists**: e.g. the elected CPS board's role over the schools, "22 police districts × 3-seat councils =
66 seats", the IL Senate/House as the Springfield chambers, the U.S. House as Congress's lower chamber)
and the office's **full election timeline** (the shared
`renderTimeline` `.tl` component with the pulsing current node — every race in a group shares its ballot
cycle, so the first race's `timeline` is used), plus a "View full details and candidates →" affordance.
Each office card carries a **full 4-sided border in its office colour** (`.office-card` `border: 2px
solid var(--gc)`, not just a top stripe) so it's distinguishable by more than a thin line
(accessibility).
A **legibility rule at the end of the stylesheet** (so it wins by source order) sets these to full
contrast (`--text-primary`), not dimmed: the office-card descriptions (`.oc-blurb`), the Chicago-map
"Click a ward…" hint (`.cm-empty`), the election-calendar card copy (`.calendar` `.cal-*`/`.tl-*`), and
all body text in the Springfield ("rules of the game") and "Where the data comes from" cabinet sections. The card/popup
title comes from `GROUP_CARD_LABEL[g]` when set, else `GROUP_META[g].label`: the CPS card is titled
**"CPS Board — Subdistrict Members"** because it holds only the 20 district seats — the board
**president** is a separate citywide (at-large) race shown in the ballot side panel, not a subdistrict
office — while the shared `GROUP_META` label stays "CPS Board of Education" for the side panel/search.
Clicking a card
(a real `<button id="grp-<g>">`) **opens a popup** (`openGroupModal` → a body-level `.group-overlay`
`role="dialog"` built once by `ensureGroupOverlay`, `body.gm-open` locks scroll, Escape / ✕ / backdrop
close, focus returns to the opener) listing **every race in that office** as a flat card
(`renderRace(r, meta, {hideTimeline:true, hideWhy:true})` — the office card already carries the timeline
and blurb, so the per-race timeline and `why_note` are suppressed). Offices with
many races get an in-popup filter (`#gm-search`, gated by `SECTION_SEARCH_MIN`) that matches **almost
anything about a race** (`raceHaystack`): office/district, every candidate & potential candidate (name
+ party + status), the current incumbent, the **Chicago neighborhoods and Illinois counties** the
district covers (from `state.maps`), the "why this race" note and the ballot stage/date — so a reader
can filter a big office by a candidate, a neighborhood or a county name. `renderGroups` keeps an
open popup in sync with the current filters (`fillGroupModal`) or closes it if its office drops out.
Some offices also carry official **"find your district by address" source links** at the top of the
popup (under the search, `.gm-sources` from a per-group `GROUP_SOURCES` map, external → new tab + ↗):
the **CPS Board** popup links the official CPS Board member map, the **Police District Councils**
popup links CPD's "Find Your District" address tool and the City Data Portal police-district boundary
dataset, the **U.S. House** popup links the official House.gov "find your representative" district
lookup, the **IL Senate** popup links the ISBE District Locator (ArcGIS), and the **IL House** popup
links the ISBE "find your elected officials" address search — the in-popup map is approximate, so
these are the authoritative address lookups. When an office has such a top source, the **per-race
"Official source ↗" link is dropped from each race card** in that popup (`hideSourceLink` passed from
`fillGroupModal`), leaving just the "Follow this race (RSS)" button — the source on top makes it
redundant; the Chicago-map "On this ballot" side panel still shows the per-race source link. (For
reference: there are **22** police district councils, one per active Chicago police district — the
numbering runs 1–25 but skips the long-closed districts 13/21/23 — three seats each = 66 members; and
the O'Hare-area districts genuinely straddle the county line, so CPS subdistrict 1A and police district
16 correctly list **Cook + DuPage** counties in `maps.json`. The **IL Senate shows 39 of 59
districts** on purpose — under the staggered term schedule only 39 seats are up in 2026; the other 20
(districts 1, 4, 7, 10, …, 58) are mid-term, next up 2028. This exact set of 39 was verified against
the "2026 Illinois Senate election" Wikipedia district sections, and the IL Senate source-link note
states it so a reader doesn't read the gaps as missing races.)
Inside the office popup **all body copy reads at full contrast** — a legibility rule promotes the
office-card timeline (`.oc-tl`) and every popup race's dimmed text (`.gm-body` — timeline
labels/notes/future dates, the map caption, the neighborhoods & counties, the "why" note, the
candidate money/committee/mini lines) to `--text-primary`, leaving only meaning-colour (party/status
pills, money value, links, the pulsing timeline dot) tinted.
**Popup scroll perf:** the overlay uses a solid dim (no `backdrop-filter: blur`, which re-rasters every
scroll frame and janked desktop), the race cards get `content-visibility:auto` (off-screen cards with
their Chicago SVG maps are skipped), and the highlighted-district pulse animates `stroke-width` only (an
animated `drop-shadow` filter re-rastered each map every frame).
Deep links open the popup: `alignDeepRace` maps `#office=<group>` / `#race=<id>` to the office, opens its
popup once (`state._deepModalOpened`), then scrolls + flashes the specific race inside `#gm-body`; a
side-panel race (citywide/statewide/U.S. Senate/CPS-president/alderman) still falls back to the "Find your
ballot" map. `.group-overlay` sets `display:flex`, so a `.group-overlay[hidden]{display:none}` rule
re-asserts `[hidden]` (same pitfall as `.gb-state`).

**Race-card detail** (`renderRace(r, meta, opts)`, shared by the office popup and the "On this ballot"
map panel — it renders **flat**: office/district, badges, map, candidates/incumbent, potential candidates,
and — unless `opts.hideTimeline` (the office popup) — the timeline, then sources. Each locator **map
highlights the race's real district** (`buildRaceMap`, from the committed `maps.json` geometry) — a
Chicago ward/police district on the city map, or an IL Senate/House/U.S. House district on the
statewide silhouette — with a **pulsing** highlight (`.map-dist` → `@keyframes rm-pulse`, off under
`prefers-reduced-motion`) and the **Chicago neighborhoods** it touches beneath it (see the scrape-maps
paragraph above); so every office card's races now carry a map — police councils, IL Senate/House,
U.S. House and the CPS subdistricts (the last from Chalkbeat's published 2026 board map).
Each card leads with a **"👥 N candidates"** badge (the confirmed-candidate count),
and for a race with **no confirmed candidates** shows the
**current incumbent** with a "CURRENT INCUMBENT" tag, resolved from whichever source covers the seat:
- **Chicago aldermen (`council`)** — from the race's own `incumbent` field, populated at deploy by
  the pipeline (see below). Chicago City Council is nonpartisan, so no party pill.
- **IL Senate/House** — from the shared people roster: the elections page fetches `people.json`
  fail-soft and indexes `il` by area, so `"Senate District N"` / `"House District N"` match a
  legislator exactly (with party).

The frontend prefers `race.incumbent` (data) over the roster lookup. CPS board / police district
councils have no published roster, and federal races already carry candidates, so those show no
separate incumbent box.

**Incumbents enrichment** (`main.py --enrich-incumbents docs/src/dashboard/elections.json`): the only
Chicago office with a clean, current, authoritative roster is the City Council, so this pass attaches
`incumbent {name, party:"", source}` to each `council` race from the **City Data Portal "Ward
Offices" dataset** (`htai-wnw4`, the same portal the maps action uses) — `parse_ward_offices` maps
each ward to its sitting alderperson, flipping the dataset's `"Last, First"` to natural order. Added
to the elections schema as an optional per-race `incumbent`. `deploy-docs.yml` runs it right after the
Wikipedia-nominee step, fully fail-soft (a portal outage attaches nothing; committed sample carries
none). Offline-tested with an injected roster in `test_scrape_elections.py`.

**Party enrichment from Wikidata** (`main.py --enrich-party docs/src/dashboard/elections.json`): the
Chicago municipal offices are legally **nonpartisan**, so no official/City dataset carries a party.
Wikidata is the one documented, structured public source (its `P102` "member of political party" —
the same kind of keyless public API the photo pipeline uses, never a scrape). This step fills a blank
`party` two safe ways and **never guesses**: (1) **aldermen** — a SPARQL enumeration of the *current
holders of the "Chicago Alderman" office* (`Q47500326`), joined to our known ward roster by name
(`parse_wikidata_alderman_parties` → `{name_key: party}`; enumerating by office means no name-match
risk); (2) **citywide candidates** (`_PARTY_PER_NAME_GROUPS`) — a strict per-name gate
(`wikidata_party_for_name`) that keeps a party only when a **single** Wikidata entity confidently
matches: a human (`P31=Q5`) whose label carries the surname AND whose English description carries a
place/office signal (`chicago`/`alderman`/`city council`/`illinois`) — so the "Pat Dowell → Illinois
House namesake" and "John Smith → three different people" traps resolve to nothing. Partisan races
already carry official party and are skipped; CPS-subdistrict / police-council candidates are obscure
and effectively never in Wikidata, so they aren't looked up (no wasted calls). `_norm_party` maps a
Wikidata label to the site's short form ("Democratic Party"/"Democratic Socialist…" → "Democratic",
etc.). Coverage is only as good as Wikidata (today a handful of aldermen), so it fills in over time.
`_wikidata_json` retries 429/503 with backoff and stays polite; the whole pass is fully fail-soft (the
Wikidata query service being down — as during its 2026 WDQS outage — attaches nothing, never a wrong
party) and runs right after the incumbents step in `deploy-docs.yml`. Offline-tested with injected
search/entity/SPARQL fetchers in `test_scrape_elections.py`.

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
