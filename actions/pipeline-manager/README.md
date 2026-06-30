# Pipeline Manager

Manages all 57 scraper repos and 57 format repos via a declarative config + template system.

## Config files

- `chn-openstates-scrape.yml` — scraper repos (`govbot-openstates-scrapers/{state}-legislation`)
- `chn-openstates-files.yml` — format repos (`chn-openstates-files/{state}-legislation`)

## Scripts

| Script | Purpose |
|--------|---------|
| `render.py` | Renders templates for all locales into `generated/` |
| `apply.py` | Pushes generated files to GitHub repos via `gh` CLI |
| `check-sessions.py` | Queries OpenStates API, flips scraper repos between active and paused templates |

## Templates

Templates live in `templates/` and use `✏️{ variable }✏️` substitution syntax:

- `openstates-scrape/` — active scraper (daily cron at 8 AM UTC)
- `openstates-scrape-paused/` — paused scraper (workflow_dispatch only, for out-of-session states)
- `openstates-to-ocd-files/` — format/transform pipeline

## Session management

`check-sessions.py` runs daily via `.github/workflows/check-sessions.yml`. It queries the OpenStates v3 API for each of the 56 jurisdictions and flips `chn-openstates-scrape.yml` between `openstates-scrape` and `openstates-scrape-paused` based on whether a legislative session is currently active.

- **Weekdays**: applies changes only for locales whose template actually changed
- **Sundays**: applies all 56 repos as a full reconciliation pass

## Common commands

```bash
# Render templates without pushing
python3 render.py -c chn-openstates-scrape.yml

# Push template changes for specific test states
python3 apply.py --config chn-openstates-scrape.yml --test-states al,ak,wy

# Push to all 56 scraper repos
python3 apply.py --config chn-openstates-scrape.yml --all-states --no-delete

# Check session status (dry run — no writes)
OPENSTATES_API_KEY=your_key python3 check-sessions.py --dry-run

# Check specific states only
OPENSTATES_API_KEY=your_key python3 check-sessions.py --dry-run --only nc,pa,dc
```
