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

## MP

- **PR:** [openstates/openstates-scrapers#5744](https://github.com/openstates/openstates-scrapers/pull/5744) — "MP: fix blank-title crash and bill_id spacing on cnmileg.net"
- **Issue:** [openstates/issues#1394](https://github.com/openstates/issues/issues/1394) — filed
  2026-07-26, referencing #5744
- **Status:** OPEN (filed 2026-07-26)
- **Fix verified:** confirmed via a *real GitHub Actions run* on a self-built Docker image, not
  just local — 321 bills, `SCRAPE_EXIT_CODE: 0`, zero tracebacks, zero `KeyError`. See
  `pending-branches.md` for full detail (including a correction: the doc originally claimed a
  second commit already existed for the bill_id-spacing fix — it didn't, had to be added before
  this PR could honestly be filed).
- **Ran `poetry run black scrapers/mp/bills.py`** before considering the PR done — reformatted
  the new code plus two pre-existing blank-line nits elsewhere in the file (commit `4a3e96db2`).
- **Currently pointed at:** `ghcr.io/tamara-builds/openstates-scrapers:mp-fix-test`, set in
  `govbot-openstates-scrapers/mp-legislation/.github/workflows/openstates-scrape.yml:81`
  (`docker-image:` input) — **stays pointed at this custom image until #5744 merges**, same
  pattern as AZ. Reverting to the default image now would put MP back to failing every run.
- **When #5744 merges:**
  1. Confirm a new `openstates/scrapers:latest` image has actually been cut with the merge
     (merged ≠ live — upstream only rebuilds on their own release cadence).
  2. Edit `mp-legislation`'s workflow: remove the `docker-image: ghcr.io/tamara-builds/openstates-scrapers:mp-fix-test` line (or set it to the default).
  3. Trigger a manual run, confirm MP scrapes clean on the official image.
  4. Delete/stop publishing `ghcr.io/tamara-builds/openstates-scrapers:mp-fix-test`.
  5. Update `not-working.md` — MP moves out of the "not working" bucket.
