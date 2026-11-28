# 🏛️ Texas (90R) Open States Scraper (Paused)

Scheduled scraping is paused — Texas (90R) is currently out of session.

The workflow can still be triggered manually via workflow_dispatch when needed.

It has no schedule because its session in
[`jurisdictions.yml`](https://github.com/chihacknight/govbot/blob/main/actions/pipeline-manager/jurisdictions.yml)
says `schedule: manual`. Give the session a schedule there and re-run `jurisdictions.py` to
turn scheduled scraping back on.
