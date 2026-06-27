# TX Backfill Runbook

How to backfill Texas legislative data for sessions that OpenStates marks `active: False`.

## When to use this

The standard daily scrape uses `openstates/scrapers:latest`, which only scrapes sessions
marked `active: True` in the official OpenStates scraper. When a TX session ends, OpenStates
marks it inactive. If we missed it while it was active, we need a backfill.

**You do NOT need this for current/ongoing sessions** — those are already active in the
official image and the self-hosted runner handles them automatically.

## Background

Texas blocks GitHub Actions IP ranges at the firewall level. All TX scrapes must run on the
self-hosted runner on Tamara's laptop. The runner is at `~/actions-runner/` and the repo is
`govbot-openstates-scrapers/tx-legislation` (`runs-on: self-hosted`).

## Step-by-step

### 1. Find the session identifier

Check the [Texas Legislature website](https://capitol.texas.gov) for the session name (e.g.
`89(1) - 2025`). The OpenStates identifier drops the parentheses: `891`, `892`, `89R`, etc.

### 2. Fork and patch the scraper

```bash
# Fork openstates/openstates-scrapers into govbot-openstates-scrapers org via GitHub UI
# Then clone your fork
git clone -b main https://github.com/govbot-openstates-scrapers/openstates-scrapers.git ~/tx-scraper-build
cd ~/tx-scraper-build
git checkout -b fix/tx-SESSIONID-backfill
```

In `scrapers/tx/__init__.py`, find the session block and flip `active: False` → `active: True`
for the target session only. Leave all other sessions as False.

```bash
# Verify only the right session is active
grep -A6 '"identifier": "SESSIONID"' scrapers/tx/__init__.py | grep active
```

### 3. Build the Docker image locally

The fork's GHCR package will be private (GitHub blocks visibility changes on forks) so build locally:

```bash
docker build -t openstates/scrapers:tx-SESSIONID-backfill ~/tx-scraper-build/
```

Takes ~15 minutes on first build; subsequent sessions are fast (Docker caches layers).

### 4. Update the tx-legislation workflow

```bash
FILE_SHA=$(gh api "repos/govbot-openstates-scrapers/tx-legislation/contents/.github/workflows/openstates-scrape.yml" --jq '.sha')

NEW_CONTENT=$(gh api "repos/govbot-openstates-scrapers/tx-legislation/contents/.github/workflows/openstates-scrape.yml" \
  --jq '.content' | base64 -d | \
  sed 's|docker-image: .*|docker-image: openstates/scrapers:tx-SESSIONID-backfill|')

gh api -X PUT "repos/govbot-openstates-scrapers/tx-legislation/contents/.github/workflows/openstates-scrape.yml" \
  --field message="fix: use tx-SESSIONID-backfill image" \
  --field content="$(echo "$NEW_CONTENT" | base64)" \
  --field sha="$FILE_SHA" \
  --jq '.commit.sha'
```

If this is the first time adding `docker-image:` to the workflow, add it under `branch: main`:

```yaml
          branch: main
          docker-image: openstates/scrapers:tx-SESSIONID-backfill
          api-keys: |
```

### 5. Make sure Docker Desktop is running and trigger the run

```bash
gh workflow run openstates-scrape.yml --repo govbot-openstates-scrapers/tx-legislation
gh run list --repo govbot-openstates-scrapers/tx-legislation --limit 1 --json databaseId,status,url --jq '.'
```

Watch Docker Desktop — a container should appear within ~30 seconds.

**Special sessions** (~600 bills): 30–60 minutes  
**Regular sessions** (~12,000 bills): 3–4 hours

### 6. If the GitHub Actions job dies but Docker keeps running

This is normal — the runner process can time out while Docker continues. The data is safe.

```bash
# Wait for the container to finish
docker wait CONTAINER_NAME

# Find where the data landed
docker inspect CONTAINER_NAME --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'

# Copy data to the git workspace and push manually
WORKSPACE=/Users/tamara/actions-runner/_work/tx-legislation/tx-legislation
DATA_SRC=<source path from inspect above>/tx

rm -rf "$WORKSPACE/_data/tx"
mkdir -p "$WORKSPACE/_data/tx"
rsync -a "$DATA_SRC/" "$WORKSPACE/_data/tx/"

git -C "$WORKSPACE" config --local user.email "action@github.com"
git -C "$WORKSPACE" config --local user.name "GitHub Action"
git -C "$WORKSPACE" config --local http.postBuffer 524288000
git -C "$WORKSPACE" add "_data/tx/"
git -C "$WORKSPACE" commit -m "🕷️ Scrape data for tx - $(date -u +'%Y-%m-%d %H:%M:%S UTC') [SESSIONID backfill]"
git -C "$WORKSPACE" push origin main
```

### 7. Reset the workflow back to the default image

After the backfill is done, update the workflow to remove the custom `docker-image:` input
(or set it back to `openstates/scrapers:latest`) so daily runs use the official image again.

### 8. Clean up

```bash
# Remove local build directory
rm -rf ~/tx-scraper-build

# Remove custom Docker images
docker rmi openstates/scrapers:tx-SESSIONID-backfill

# Delete the fork from GitHub (need delete_repo scope)
gh auth refresh -h github.com -s delete_repo
gh repo delete govbot-openstates-scrapers/openstates-scrapers --yes
```

## Session history

| Session | Name | Bills scraped | Date | Notes |
|---------|------|--------------|------|-------|
| 89R | 89th Legislature, Regular Session (2025) | 12,195 | 2026-06-27 | ~3.5 hr run; job died but Docker kept going — salvaged manually |
| 891 | 89th Legislature, 1st Called Session (2025) | 592 | 2026-06-27 | ~45 min run; completed cleanly |
| 892 | 89th Legislature, 2nd Called Session (2025) | 696 | 2026-06-26 | Included in 89R run |

## Notes

- TX scrapes ONLY work from the self-hosted runner (laptop) due to IP blocking
- Keep Docker Desktop open and prevent laptop sleep during long scrapes
- GHCR packages on forked repos cannot be made public — always build locally
- The `http.postBuffer 524288000` setting is required for large pushes (12k+ files hit HTTP 400 without it)
- After a backfill, update `error-tracking.md` with the session coverage
