# Pipeline Manager

Every jurisdiction's scraper and data repos, from one config file.

## jurisdictions.yml

**The single source of truth** for every jurisdiction (schema: `jurisdictions.schema.json`).
Per state:

- **settings:** `name`, `scrape_cron` (its daily time, UTC), `labels` (`working` = in
  `govbot clone all`), and where they differ from `defaults`: `runner` (`github` /
  `proxy` = GitHub-hosted through tinyproxy / `self-hosted`), `scrapers` (e.g. `bills votes`),
  `scrape_timeout_minutes`, `docker_image`, `toolkit_branch`; `repo_secrets` lists the repo-level
  secrets a new pair's scraper repo needs set by hand.
- **`sessions:`** one entry per legislative session, each a pair of repos:
  `govbot-openstates-scrapers/<st>-<id>-scraper` + `govbot-data/<st>-<id>` (the id lower-cased;
  characters outside `[a-z0-9._-]` become `-`). `schedule` defaults to the state's `scrape_cron`;
  `manual` = no schedule. Anything else on a session overrides the state's settings.
- **`old_repos:`** the one-repo-per-state pair from before the 2026-11 reorg: `history` (moved to
  `govbot-history`, read-only) or `manual` (still running in the live orgs, managed by hand: dc gu
  mi mp nj oh pa usa vi).

Readers: the govbot CLI (`just generate` builds its state and repo list from this file), the site
build (`scripts/data_repos.py`, `scripts/build_catalog.py`), the fleet monitor and the audits.

## jurisdictions.py

```bash
python3 jurisdictions.py plan --session tx-90r    # dry run: names, workflows, secrets; reads GitHub only
python3 jurisdictions.py render                   # render every pair (offline)
python3 jurisdictions.py apply --session tx-90r   # create or update that pair
```

It renders `templates/openstates-scrape` (`openstates-scrape-paused` for a `manual` schedule) for
the scraper repo and `templates/openstates-to-ocd-files` for the data repo, with `render.py`.

- It never deletes a repo (there is no delete code).
- It never writes to `old_repos` (history or manual).
- It creates repos public, and only after `moved.py`'s `refuse_to_create` confirms a 404: a name
  that redirects to a moved repo is never taken.
- It updates a repo only when GitHub answers with exactly that name. An update replaces `.github/`
  with the rendered files; data is untouched.
- `apply` needs explicit `--session`s; nothing runs it automatically.

Workflow names include the session ("OpenStates Scrape for tx 90R").

## Finishing a session

Give the session `schedule: manual` (or remove its schedule) and re-run `jurisdictions.py apply`
for it. Moving a finished pair to `govbot-archive` and archiving it is a separate, by-hand step;
the pattern is in the repo-reorg notes (`govbot-archive/wy-2026`).

## Tests

```bash
python3 test_jurisdictions.py   # the file against its schema, and the tool (offline)
python3 test_moved.py           # the redirect guard (offline)
./render-snapshots.sh           # every pair into __snapshots__/jurisdictions/
```

## Other scripts

- `legiscan-audit.py`: cross-checks our bill counts against LegiScan (reads `jurisdictions.yml`).
- `scripts/`: older one-off maintenance scripts, mostly for the retired `windy-civi-pipelines`
  org; not part of the current pipeline.
