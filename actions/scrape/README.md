# OpenStates Scraper

We purposely don't run the snapshots as a test because we don't want live data here.

## Which session and which scrapers

- **`session`** (input, e.g. `90R`, `2025_26`): passed to every scraper as `session=<id>`. Empty
  means whatever OpenStates' code marks "active", which silently drops a session once it stops
  being active. A per-session repo always sets it (pipeline-manager config `scrape_session`; a
  manual run can override it). OpenStates still needs the state to have *some* active session.
- **`scrapers`** (input, e.g. `bills votes`): empty means `bills`. CT, IA, KS, MA, MD, NM, OR, PR
  and TX keep roll calls in a separate `votes` scraper; without it their scrapes have no votes.
  CA runs only its own bills path (`scrape-ca.sh`).

Both are recorded in `scrape-summary.json` and the release manifest. Offline test (fake docker):
`bash test_scrape_args.sh`.
