# scrape-hearings

Fetches **upcoming committee hearings** — and best-effort **witness-slip counts** —
for the jurisdictions govbot surfaces on the Pages dashboard, and writes one
document matching [`schemas/govbot.hearings.schema.json`](../../schemas/govbot.hearings.schema.json).

Committee hearings are *live* artifacts each statehouse publishes on its own
endpoint; govbot does **not** get them from OpenStates. This action taps the
sources directly:

| Jurisdiction | Source | Notes |
|---|---|---|
| Illinois (`il`) | `ilga.gov` Hearings JSON API | per chamber, date range; bills parsed from the subject line |
| Washington (`wa`) | `leg.wa.gov` CommitteeMeetingService (SOAP/XML) | agenda items fetched per meeting for bill ids |

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

## Usage

```bash
# Live (what the Pages deploy runs, twice daily):
python3 main.py --jurisdictions il,wa --output docs/src/dashboard/hearings.json

# Also emit RSS: one whole-calendar feed plus one feed per bill, so a reader
# can follow a single bill's hearings instead of the entire calendar. Per-bill
# feeds are named <jurisdiction>-<NORMALIZED_ID>.xml (e.g. il-HB1643.xml); the
# hearings page recomputes that name to link each bill to its feed.
python3 main.py --jurisdictions il,wa \
  --output docs/src/dashboard/hearings.json \
  --rss docs/src/dashboard/hearings.xml \
  --rss-bills-dir docs/src/dashboard/hearings

# Attempt best-effort slip-count enrichment (opt-in; IL totals endpoint is
# currently unreliable, so counts are usually absent):
python3 main.py --slips -o -

# Offline, deterministic — rebuild from fixtures (no network):
python3 main.py --from-fixtures __snapshots__/raw --now 2026-08-28T00:00:00Z -o -
```

As a composite GitHub Action, see [`action.yml`](./action.yml).

## Tests & snapshots

Pure parsers (`parse_il_hearings`, `parse_slip_counts`, `parse_wa_meetings`,
`parse_wa_items`) take raw text and are covered offline by fixtures in
`__snapshots__/raw/`. The whole offline build is diffed against
`__snapshots__/expected_hearings.json`.

```bash
python3 test_scrape_hearings.py     # run tests (no network)
./render-snapshots.sh               # regenerate the snapshot after an intended change
```

## Failure mode

Fail loudly, recover gracefully (per `CLAUDE.md`): a source outage yields zero
hearings for that jurisdiction and a warning, never a crash. The deploy workflow
keeps the committed sample `hearings.json` when a run produces an empty document.
