# Committee Hearings Dashboard

**[Open the dashboard →](./dashboard/index.html)**

A static, client-side page listing **upcoming committee hearings and witness-slip
windows** for Illinois and Washington — where the public can weigh in on a bill. It
is plain HTML/JS with no external dependencies, deployed as part of this docs site
by the existing GitHub Pages workflow.

## What it shows

- **Committee hearings & witness slips** — upcoming hearings (Illinois & Washington),
  grouped by state, each with its date/time, location, the bills on the agenda
  (with witness-slip counts where available), a link to that bill and to the
  committee's official page, and a deep link to the official portal to file a slip /
  sign in to testify.
- Only **upcoming** hearings are shown; an "Updated" stamp gives the build time, and
  a **Subscribe (RSS)** link offers the same list as a feed.
- **Weigh in — by state** — a directory of every U.S. jurisdiction with how the public
  participates there (witness slip, Request to Speak, position letter, written
  testimony, public comment, committee testimony, …) and a link to the official
  portal. Illinois & Washington are the two states with live hearings above; the rest
  are directory entries. Data: `docs/src/dashboard/participation.json` (static
  reference, schema `schemas/govbot.participation.schema.json`).

## Where the data comes from

The page reads a single `hearings.json`, produced by the
[`scrape-hearings`](https://github.com/chihacknight/govbot/blob/main/actions/scrape-hearings/)
action. Committee hearings are live artifacts each statehouse publishes on its own
machine-readable endpoint — govbot does *not* get them from OpenStates — and they
describe near-future activity, not point-in-time bill metadata.

Sources, per [`schemas/govbot.hearings.schema.json`](https://github.com/chihacknight/govbot/blob/main/schemas/govbot.hearings.schema.json):

| Jurisdiction | Source | Public participation |
|---|---|---|
| Illinois | `ilga.gov` Hearings JSON API | witness slip |
| Washington | `leg.wa.gov` CommitteeMeetingService (SOAP/XML) | committee sign-in |

Only **upcoming** hearings are shown (anything before today is dropped). Each
committee links to its official page — Illinois to the committee roster, Washington
to the committee's `leg.wa.gov` page, resolved from that site's own committee index
(and every link is checked before it ships, so a wrong guess is never published).

**Witness-slip counts are best-effort.** Many capitols only expose slip totals while
a slip window is open (a canceled hearing's slip page returns an error), so
`bills[].slips` is optional and usually absent; the reliable signal is the hearing
itself plus the deep link to file. The Pages deploy rebuilds `hearings.json` on the
**twice-daily** schedule (08:00 and 20:00 UTC), keeping the last-good committed
sample if a scrape produces nothing.

> This page is hearings-only; the Pages deploy no longer builds the bill dataset.
> The bill-tagging tooling still lives in the repo (`scripts/build_dashboard_data.py`,
> `scripts/govbot-dashboard.yml`, `govbot tag`) and can be run manually — it is just
> no longer part of this deploy.

### Subscribe by feed (RSS)

The same run also writes `hearings.xml`, an RSS 2.0 feed of the upcoming hearings
(one item per hearing, with the committee, date, bills, and a link to participate).
Anyone can subscribe to
`https://chihacknight.github.io/govbot/dashboard/hearings.xml` in a feed reader to
follow hearings without opening the dashboard; the panel links it as "Subscribe (RSS)".

```bash
# Live (writes both the dashboard JSON and the RSS feed):
python3 actions/scrape-hearings/main.py --jurisdictions il,wa \
  --output docs/src/dashboard/hearings.json \
  --rss docs/src/dashboard/hearings.xml

# Offline, from fixtures (no network) — also how the snapshot test runs:
python3 actions/scrape-hearings/main.py \
  --from-fixtures actions/scrape-hearings/__snapshots__/raw \
  --now 2026-08-28T00:00:00Z -o -
python3 actions/scrape-hearings/test_scrape_hearings.py
```

Adding a jurisdiction means adding its source endpoint + parser to
`actions/scrape-hearings/main.py` and an entry to `JURISDICTIONS` there; the schema
and dashboard panel already generalize across jurisdictions.
