# Pipeline Manager

Manages all 57 scraper repos and 57 format repos via a declarative config + template system.

## jurisdictions.yml and jurisdictions.py (since 2026-11)

**`jurisdictions.yml` is the single source of truth** for every jurisdiction: its settings, its
session pairs (`sessions:`) and its old one-repo-per-state repos (`old_repos:`). Each session is a
pair `govbot-openstates-scrapers/<st>-<id>-scraper` + `govbot-data/<st>-<id>`.

```bash
python3 jurisdictions.py plan --session tx-90r    # dry run: names, workflows, secrets; reads GitHub only
python3 jurisdictions.py render                   # render every pair (offline)
python3 jurisdictions.py apply --session tx-90r   # create or update that pair
```

It replaces `apply.py`. It never deletes a repo, never writes to `old_repos` (history or manual),
creates repos public, and only after `moved.py`'s `refuse_to_create` confirms a 404. Tests:
`python3 test_jurisdictions.py` (`--report` prints the field-by-field check against the old configs).

The old configs below are kept only for readers that still use them (the CLI's state list, the
fleet monitor); nothing writes to them, and `apply-templates.yml`, `close-session.yml` and
`check-sessions.yml` no longer run. They go away once every reader uses `jurisdictions.yml`.

## Config files

- `chn-openstates-scrape.yml` — scraper repos (`govbot-openstates-scrapers/{state}-legislation`)
- `chn-openstates-files.yml` — format repos (`govbot-data/{state}-legislation`)

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

## Moved repos (`moved_to`)

When a locale's repo moves out of the org a config manages (e.g. to `govbot-history` in the
Nov 2026 repo reorganisation), keep the locale in the config and mark it:

```yaml
  wy:
    template: openstates-to-ocd-files-paused
    moved_to: govbot-history/wy-legislation-data
```

GitHub keeps redirecting the old address only while no new repo takes the old name. So
`apply.py` skips a moved locale (no create, no template push through the redirect), the fleet
monitor emits no record for it, and `close_session.py` / `rebuild_data_repos.py` refuse it.
Don't delete the locale instead: `govbot clone all` is generated from `chn-openstates-files.yml`.

`apply.py`'s `create_repo` also refuses any name GitHub doesn't confirm is free (a 404): a name
that redirects is never re-created, marked or not (`moved.py`). Tests: `python3 test_moved.py`.

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

## apply.py — Flags reference

| Flag | Description |
|------|-------------|
| `-c CONFIG` / `--config CONFIG` | Required. Config file (`chn-openstates-scrape.yml` for scraper repos, `chn-openstates-files.yml` for format/data repos) |
| `--all-states` | Process all states in the config |
| `--test-states wy,nv` | Comma-separated list of states to process (no spaces). Default test states: al, ak, de, wy, sd |
| `--no-delete` | Skip deletion of repos not in config at all (config drift cleanup). Doesn't affect `--test-states`/`--all-states` scoping. |
| `--dry-run` | Show what would change without making any changes |

### Deletion safety

`apply.py` only ever proposes deleting a repo that isn't in the config **at all** — a
`--test-states wy` run will never propose deleting `il-legislation` or any other
configured-but-out-of-scope repo, regardless of `--no-delete`. Deletion candidates are
computed against the full, unfiltered config (`get_all_expected_repo_names()`), not the
scoped subset a given run happens to be processing.

`--no-delete` still matters for the case it's meant for: real config drift, e.g. a locale
was removed or renamed and its old repo is still sitting in GitHub. **Still pass
`--no-delete`** for routine/test runs — it's the difference between "review this
before deleting" and "delete genuinely orphaned repos automatically" — but you no longer
need to worry that testing on a handful of states will threaten every other real, still-
configured repo. (This was a real near-miss caught via `--dry-run` before it ran for
real — see the `fix: apply.py's --test-states no longer treats out-of-scope repos as
deletable` commit for the full story.)
