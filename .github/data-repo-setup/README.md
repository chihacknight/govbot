# Searchable descriptions for the 56 data repositories

Search engines and AI assistants read a repository's **description, website link and topics** before
anything else. The 56 `govbot-data/<code>-legislation` repositories still carry the placeholder
"🏛️ IL legislative data pipeline" and only the pipeline's own status topics. `set_repo_metadata.py`
replaces that with one clear sentence per repository, the Govbot website link and shared topics.

## For an organization admin (about five minutes)

1. Install the [GitHub CLI](https://cli.github.com/) and sign in: `gh auth login` (an account that can edit the `govbot-data` repositories).
2. From a clone of this repository, look first. This changes nothing:
   `python3 .github/data-repo-setup/set_repo_metadata.py`
3. Happy with it? Make the change: `python3 .github/data-repo-setup/set_repo_metadata.py --apply`
   (or name a few first, e.g. `... --apply il mn usa`).

Safe to re-run, and a second run reports "already done". It only:
- replaces a description that is still the placeholder (a hand-written one is left alone),
- fills the website link when it is empty,
- **adds** topics. The pipeline's `govbot-scraper-*` and `govbot-session-*` topics are kept.

The README inside each data repository is not touched: the pipeline-manager writes those from templates.

Example result for `govbot-data/il-legislation`:

> Illinois legislation as plain files you can clone: every bill with its sponsors, actions and full text. Open data from Govbot, by Chi Hack Night. CC BY 4.0.
> Topics: legislation, legislative-data, open-data, government-data, civic-tech, bills, govbot, openstates, illinois

Offline check of the wording and the safety rules: `python3 .github/data-repo-setup/test_set_repo_metadata.py`

## Also by hand, on the main repository (chihacknight/govbot)

Repository page → About → ⚙ → Topics: `legislation`, `legislative-data`, `open-data`, `government-data`,
`civic-tech`, `civic-data`, `bills`, `congress`, `state-legislatures`, `duckdb`, `git`, `ai`.
Settings → General → Social preview: upload a 1280×640 image (the Govbot robot mark on the dark civic background works).
