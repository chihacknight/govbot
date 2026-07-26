---
name: scraper-debugging-onboarding
description: Start-here doc for a new chat picking up state-scraper investigation work -- what context to load, the fastmode gotcha, and the standard reproduce-fix-test-upstream workflow.
metadata:
  type: project
---

# Scraper Debugging — Start Here

If you're picking up a "this state's scraper is broken" investigation in a fresh chat, read
this first. It's the distilled version of lessons learned across AZ, FL, MT, and others —
not a replacement for the state-specific detail in `state-problems.md`.

## Read these first, in order

1. **`docs/src/state-status-reference.md`** — one row per jurisdiction: scrape/extraction
   health, session timing, bill-text format. The "Hosting Path History" table at the bottom
   tells you what's actually been tried (Tinyproxy / self-hosted / plain GitHub-hosted) and
   what worked, per state — check this before re-trying a hosting fix that's already been
   ruled out.
2. **`tamara-notes/state-problems.md`** — the working notes behind that table. Only states
   that have actually been investigated get an entry here; if a state isn't in this file,
   nothing beyond the one-line status has been verified yet.
3. **`tamara-notes/scraper-fix-plan.md`** — "what's been tried / what to try next" per state,
   if it's still current when you read this (it's a point-in-time planning doc, not
   continuously maintained).
4. **Don't trust `tamara-notes/archived_docs/*`** without re-checking against current code —
   that's exactly the scattered, sometimes-contradictory pre-cleanup state `state-problems.md`
   was created to replace.

## The `--fastmode` gotcha (found investigating AZ, 2026-07-24)

**`actions/scrape/scrape.sh` always passes `--fastmode` to every scraper invocation.** This
flag's actual purpose, per OpenStates' own CLI help text: `"use cache and turn off
throttling"` — it's a **local dev/iteration convenience flag**, not something meant for
production scraping. It's been in `scrape.sh` since its earliest commit with no rationale on
record; almost certainly just copied from an OpenStates example command.

What it actually does (`openstates/scrape/base.py`): sets `requests_per_minute = 0` (no rate
limiting) and, critically, `cache_write_only = False` — which enables scrapelib's `FileCache`
to **serve GET responses from disk**, keyed purely on URL (cookies, headers, and method are
not part of the cache key).

**Why this matters for debugging:** if a scraper's flow does something like "GET a page →
POST to mutate server-side state (set a session, log in, apply a filter) → GET the same URL
again expecting it to reflect the change," fastmode's cache can silently serve the *first*
GET's stale response for the second call — a bug that's 100% reproducible in CI, on every
network path, and **invisible if you test locally without `--fastmode`** (which is exactly
what OpenStates maintainers do — see AZ PR #5722, where the maintainer couldn't reproduce our
failure at all, because their repro command omitted the flag).

**Practical takeaway:** if a scraper fails consistently regardless of hosting path (Tinyproxy,
self-hosted, plain GitHub-hosted all fail identically) — that symmetry is itself a clue it's
*not* network/WAF-related. Before chasing a network theory, try reproducing **without
`--fastmode`** first. If it passes clean without the flag, suspect cache poisoning from a
GET-mutate-GET pattern, not IP blocking. AZ's actual root cause turned out to be exactly this
(see `state-problems.md` for the full writeup) after weeks of network-focused investigation
on the wrong trail.

## Standard workflow: reproduce → fix → test → upstream

This is the pattern used for both FL (2026-07-23/24, see
`tamara-notes/fl-single-bill-failure-handoff.md`) and AZ (2026-07-24). Repeat it for any new
state-specific scraper bug:

1. **Reproduce locally first**, outside CI, using the real image:
   ```
   docker run --rm --dns 8.8.8.8 --dns 1.1.1.1 \
     -v "$(pwd)/_working/_data":/opt/openstates/openstates/_data \
     -v "$(pwd)/_working/_cache":/opt/openstates/openstates/_cache \
     openstates/scrapers:latest \
     <state> bills --scrape --fastmode
   ```
   Use a **fresh, empty `_cache` dir** unless you're deliberately testing cache-related
   behavior. To dig into scrapelib/requests behavior directly (cookies, cache hits, raw
   response bytes), `--entrypoint bash` into the image and run a small Python script against
   the venv's `python3` (`/root/.cache/pypoetry/virtualenvs/openstates-scrapers-*/bin/python3`)
   rather than guessing from logs alone.

2. **Find the fix in `~/tad_code.nosync/current/openstates-scrapers`** (Tamara's clone,
   remotes: `origin` = `tamara-builds/openstates-scrapers`, `upstream` =
   `openstates/openstates-scrapers`).
   - **Always confirm your branch before editing** — branch drift (silently ending up back on
     `main` or someone else's feature branch) has already cost real debugging time twice.
     `git branch --show-current` first, every time.
   - **Check for uncommitted work on whatever branch you're on before switching** — don't
     lose someone's in-progress fix. Commit or stash it first.
   - Branch off latest `upstream/main` for a new fix: `git checkout main && git fetch upstream
     main && git merge --ff-only upstream/main`, then `git checkout -b fix/<short-name>`.

3. **Build and push an amd64 test image** (your Mac is arm64; GitHub-hosted runners and the
   production image are amd64 — a native build silently produces the wrong architecture):
   ```
   docker buildx build --platform linux/amd64 \
     -t ghcr.io/tamara-builds/openstates-scrapers:<state>-fix-test --push .
   ```

4. **Verify the fix actually landed in the built image before trusting it** — this is the
   step that catches branch-drift mistakes:
   ```
   docker pull ghcr.io/tamara-builds/openstates-scrapers:<state>-fix-test
   docker run --rm --entrypoint /bin/bash ghcr.io/tamara-builds/openstates-scrapers:<state>-fix-test \
     -c "grep -n '<something unique from your fix>' /opt/openstates/openstates/scrapers/<state>/bills.py"
   ```

5. **Test end-to-end against the real site** before touching any live workflow — run the
   actual `<state> bills --scrape --fastmode` command against the fixed image locally, same
   as step 1, and confirm it produces real bill data.

6. **Dispatch a real test run** by pointing the state's live workflow at the custom image
   (`docker-image: ghcr.io/tamara-builds/openstates-scrapers:<state>-fix-test` in
   `govbot-openstates-scrapers/<state>-legislation/.github/workflows/openstates-scrape.yml`),
   preferring Tinyproxy over self-hosted where the workflow supports it (Tinyproxy doesn't
   need your laptop on — see `scraper-fix-plan.md`'s priority rule). Check for a concurrency
   conflict first: `gh run list -R govbot-openstates-scrapers/<state>-legislation -w
   openstates-scrape.yml -L 3`.

7. **Once confirmed working end-to-end**, push the same commit to the PR branch (this is
   separate from the docker image — rebuilding the image doesn't update the PR, and pushing
   to the branch doesn't redeploy the image, you need both) and open the upstream PR. See
   `[[reference-openstates-contrib]]` — or the equivalent section in this repo's memory — for
   the file-a-PR-plus-linked-issue process and label conventions.

8. **Revert the live workflow's `docker-image` override** back to the default
   (`openstates/scrapers:latest`) once the upstream PR merges and a new official image is
   built — don't leave state repos permanently pointed at a personal `ghcr.io` image.

## Infra you'll likely need

- **Two GitHub orgs**: `govbot-openstates-scrapers` (scraper repos, one per jurisdiction) and
  `govbot-data` (format/output repos). `pipeline-manager` in this repo manages both via
  `chn-openstates-scrape.yml` / `chn-openstates-files.yml` + `apply.py`.
- **Tinyproxy**: a GCP VM proxying GitHub-hosted runner traffic through a stable non-Azure IP
  — the first thing to try for any state that looks network-blocked, before self-hosted.
- **Self-hosted runners**: Tamara's MacBook(s), registered at the `govbot-openstates-scrapers`
  org level. Requires the laptop on and `./run.sh` running — last resort, not first choice.
- **`check-sessions.py`** is currently **disabled org-wide** (its OpenStates-API session dates
  were repeatedly wrong and caused false "frozen" alarms) — don't assume a quiet repo is
  correctly paused; verify manually.
