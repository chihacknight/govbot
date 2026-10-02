# 🏛️ Puerto Rico legislation file tree (Paused)

Scheduled formatting and text extraction are paused — Puerto Rico is currently out of
session.

Both `format.yml` and `extract-text.yml` can still be triggered manually via
`workflow_dispatch`. `format.yml` also still listens for a `repository_dispatch` from the
scraper repo, so manually re-dispatching scrape for this locale will still trigger a
format (and, in turn, extract-text) pass even while paused.

Unlike the scrape-paused template, there is currently no automated resume for this one —
`check-sessions.py` only manages `chn-openstates-scrape.yml`, not `chn-openstates-files.yml`.
Flip this locale back to the `openstates-to-ocd-files` template by hand once the state's next
session begins, and re-run `apply.py`.
