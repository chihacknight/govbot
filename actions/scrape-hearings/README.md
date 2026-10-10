# scrape-hearings

Fetches **upcoming committee hearings** — and best-effort **witness-slip counts** —
for the jurisdictions govbot surfaces on the Pages dashboard, and writes one
document matching [`schemas/govbot.hearings.schema.json`](../../schemas/govbot.hearings.schema.json).

Committee hearings are *live* artifacts each statehouse publishes on its own
endpoint; govbot does **not** get them from OpenStates. This action taps the
sources directly:

| Jurisdiction | Source | Notes |
|---|---|---|
| USA (`us`) | `federalregister.gov` API (documents open for comment) | every published proposed rule / rule whose comment period is still open (~200), keyless, one request; leads the list. Only the soonest-closing 12% (`FEDERAL_SHOW_SHARE`, in `assemble`) is kept — the federal jurisdiction entry carries `open_total` + `full_list_url` (the Federal Register's own search for the same set) for the page's "See all N" button. Notices (~800 announcements that ask for comments without being a rule) come from a second query; each is sorted into a plain kind by title (`NOTICE_CATEGORIES`: requests for ideas, environment, permits, meetings, privacy, forms & paperwork (~70%), other) and only the 3 closing soonest per kind (`NOTICES_PER_CATEGORY`) ship, with `notice_total` / `notice_categories` / `notice_list_url` on the federal entry |
| Illinois (`il`) | `ilga.gov` Hearings JSON API | per chamber, date range; bills parsed from the subject line |
| Washington (`wa`) | `leg.wa.gov` CommitteeMeetingService (SOAP/XML) | agenda items fetched per meeting for bill ids |
| Massachusetts (`ma`) | `malegislature.gov` Hearings JSON API | list of events + per-hearing detail; committee, location, and agenda bills; keyless |
| Alaska (`ak`) | `akleg.gov` BASIS meetings JSON API | one document per legislature; committee, date, room, chamber, status; keyless. No bill agenda in the feed, so Alaska hearings carry no bills. Bump `AK_SESSION` each biennium |

**Federal (`us`) is keyless.** It used the Regulations.gov API, whose shared
`DEMO_KEY` is rate-limited (it answered 429), so the page fell back to a placeholder
seed that had expired. The Federal Register's public API lists the same open comment
periods without a key, each with its Regulations.gov comment link. A failed fetch
yields no federal rows (never placeholders); the offline snapshot uses a trimmed real
response, `__snapshots__/raw/fr_documents.json`.

## Why not the dashboard's bill pipeline?

`docs/src/dashboard/data.json` is point-in-time **bill metadata** rebuilt daily
from git-repos-as-datasets. Hearings are a **rolling near-future window** of
committee activity that the bill snapshot cannot express, so they live in a
separate `hearings.json` the dashboard fetches alongside `data.json`.

## Witness-slip counts are best-effort

Many capitols only expose slip totals **while a slip window is open** — a canceled
hearing's slip page returns an error page. So `bills[].slips` is optional per the
schema and is usually `null`; the reliable, always-useful signal is the hearing
itself plus `witness_slip_url`, a deep link to the official portal to file. Count
enrichment is bounded and parallel, and any failure simply leaves `slips` null.

## One link per hearing, straight to it

Each hearing row has a single link. `witness_slip_url` is where to take part in
**that** hearing; when there's none, the row links the hearing's own page
(`details_url`, labelled "Hearing details").

| Source | `witness_slip_url` |
|---|---|
| IL | the first bill's Bill Status page (its Witness Slips button); a hearing with no bills → its hearing page |
| WA | Committee Sign-In opened on this meeting (`/csi/<Senate\|House\|Joint>?selectedCommittee=<Committee Id>&selectedMeeting=<AgendaId>` — CSI preselects both and lists the bills). Only meetings with a public hearing on bills; interim work sessions aren't in CSI, so `null` |
| MA | the hearing page (written testimony is submitted there) |
| AK | `null` — Alaska's only comment tool is its general POMS form, so the row links the meeting page |
| Federal | the rule's Regulations.gov "comment on" form, else its Federal Register page |

## Usage

```bash
# Live (what the Pages deploy runs, twice daily):
python3 main.py --jurisdictions il,wa,ma,ak,us --output docs/src/dashboard/hearings.json

# Also emit RSS: one whole-calendar feed (--rss) plus granular feeds
# (--rss-feeds-dir) so a reader can follow a single bill, a whole state, or one
# hearing instead of the entire calendar. Filenames the hearings page recomputes:
#   per bill:        <jurisdiction>-<NORMALIZED_ID>.xml   (e.g. il-HB1643.xml)
#   per jurisdiction: <code>.xml                          (e.g. wa.xml)
#   per hearing:     hearing-<id>.xml                     (e.g. hearing-wa-other-33551.xml)
python3 main.py --jurisdictions il,wa,ma,ak,us \
  --output docs/src/dashboard/hearings.json \
  --rss docs/src/dashboard/hearings.xml \
  --rss-feeds-dir docs/src/dashboard/hearings
# Every feed carries an <?xml-stylesheet href="feed.xsl"> PI so a browser renders
# it as a readable page (docs/src/dashboard/feed.xsl) instead of a raw XML tree;
# feed readers ignore it. Root feed -> feed.xsl, granular feeds -> ../feed.xsl.

# Attempt best-effort slip-count enrichment (opt-in; IL totals endpoint is
# currently unreliable, so counts are usually absent):
python3 main.py --slips -o -

# Offline, deterministic — rebuild from fixtures (no network):
python3 main.py --from-fixtures __snapshots__/raw --now 2026-08-28T00:00:00Z -o -
```

As a composite GitHub Action, see [`action.yml`](./action.yml).

## Tests & snapshots

Pure parsers (`parse_il_hearings`, `parse_slip_counts`, `parse_wa_meetings`,
`parse_wa_items`, `parse_ma_hearing_list`, `parse_ma_hearing`, `parse_ak_meetings`) take raw text and
are covered offline by fixtures in `__snapshots__/raw/`. The whole offline build is diffed against
`__snapshots__/expected_hearings.json`.

```bash
python3 test_scrape_hearings.py     # run tests (no network)
./render-snapshots.sh               # regenerate the snapshot after an intended change
```

## Failure mode

Fail loudly, recover gracefully (per `CLAUDE.md`): a source outage yields zero
hearings for that jurisdiction and a warning, never a crash. The deploy workflow
keeps the committed sample `hearings.json` when a run produces an empty document.
