# Upstream PR follow-ups

States running on a custom Docker image while waiting on an OpenStates PR to merge. Once a
PR merges and a new `openstates/scrapers:latest` image is cut with it, switch that state's
workflow back to the default and cross it off. Check back periodically — no automated ping.

## AZ

- **PR:** [openstates/openstates-scrapers#5742](https://github.com/openstates/openstates-scrapers/pull/5742) — "AZ: fix cache-poisoning bug where `--fastmode` masks the session-setting POST"
- **Status:** OPEN (filed 2026-07-24)
- **Fix verified:** tested locally against a self-built Docker image, confirmed working
- **Currently pointed at:** `ghcr.io/tamara-builds/openstates-scrapers:az-fix-test`, set in
  `govbot-openstates-scrapers/az-legislation/.github/workflows/openstates-scrape.yml:81`
  (`docker-image:` input)
- **When #5742 merges:**
  1. Confirm a new `openstates/scrapers:latest` image has actually been cut with the merge
     (upstream only rebuilds the image on their own release cadence — merged ≠ live).
  2. Edit `az-legislation`'s workflow: change `docker-image: ghcr.io/tamara-builds/openstates-scrapers:az-fix-test` back to the default (remove the line, or set `openstates/scrapers:latest`).
  3. Trigger a manual run, confirm AZ scrapes clean on the official image (no `S3_SESSION_CONFIG` regression).
  4. Delete/stop publishing `ghcr.io/tamara-builds/openstates-scrapers:az-fix-test`.
  5. Update `not-working.md` — AZ moves out of the "not working" bucket.
  6. Update `tamara-notes/archived_docs/openstates-responses.md`'s AZ section to close the loop.

- **Note:** the *earlier* AZ PR, [#5722](https://github.com/openstates/openstates-scrapers/pull/5722)
  ("preserve session cookies across setsession.php POST"), is already **MERGED** — that fixed a
  different bug. #5742 is a follow-on issue found after #5722 landed, not a duplicate.
