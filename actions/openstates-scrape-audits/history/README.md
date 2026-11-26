# State history scanner

Replays a state's whole raw scrape history (every commit to `_data/<st>/` in its raw scraper repo)
into one SQLite database, to find what silently went wrong, when, and for how long. This is the
measuring step of the state history analysis; the state auditor is built on it later. Brief and
decisions: `tamara-notes/processes/workstreams/shared-docs/history-analysis-plan.md`.

Standard library Python plus `git`. Everything it reads is read-only (`git ls-tree`,
`git cat-file --batch`; no checkout or fetch).

```bash
python3 scan.py wy ky ar                 # scan, then write <out>/<st>/report.md
python3 scan.py --jobs 4 ca de il ma     # four states at a time
python3 report.py wy                     # rewrite a report from the database, no re-scan
python3 check_known.py wy ky ar          # does the database reproduce the known numbers?
python3 profiles.py --all                # each state's normal -> <out>/profiles/<st>.json (Q15)
python3 replay.py                        # replay the candidate checks over the year -> <out>/replay-profile.md (Q16)
python3 replay.py --uniform              # the same with one threshold for every state, to compare
python3 freeze.py                        # freeze the settings before a held-out test -> <out>/frozen-settings.json
python3 replay.py --frozen <file> ak al  # score held-out states; refuses if the settings changed since -> replay-heldout.md
python3 replay.py --mode after-tuning-heldout ak al   # any other run, under its own name -> replay-<mode>.md
python3 test_scan.py                     # offline tests (builds tiny git repos)
```

Hand commits under `_data/` (07-21's "chore: clear duplicate-accumulated scrape data", "Delete
_data/sd directory", NH's restore) are scanned like any commit, but every check leaves them out
(`daily.is_scrape`).

`known_events.py` holds the failures we already know about (the replay's answer key, also left
out when a normal is measured) and `CAVEATS`, the ways a state's raw history misleads (FL most of
all). `daily.py` holds the session calendar, every raw repo's commit times and the day-by-day view
both scripts share. Profiles and replays are derived data on the SSD, like the database.

Defaults (the SSD): raw repos `/Volumes/govbot-data/raw-scrapers/<st>-legislation`, data repos
`/Volumes/govbot-data/govbot_data/full/`, archive clones `/Volumes/govbot-data/govbot-archive/`,
output `/Volumes/govbot-data/scratch/history-analysis/` (`history.sqlite` and `<st>/report.md`).
Each can be changed with a flag (`--raw-root`, `--data-root`, `--archive-root`, `--out`, `--db`).

| Table | One row per |
|---|---|
| `scrapes` | state and scrape: file counts, bills, bills new/gone/back, actions and votes new/gone/reworded, roll-call problems, unreadable files, duplicates, examples |
| `scrape_fields` | state, scrape and field: bills that have it, lost it (and got it back later), gained it, changed it (whitespace only) |
| `bad_files` | unreadable file (conflict markers, invalid JSON, empty), with the bill when it can be found |
| `bills` | state and bill: first and last scrape, absences, changes, actions and votes that never came back, last scrape each field was filled |
| `sessions` | state and session: raw history vs data repo vs both govbot-archive copies |
| `fields` | state and field: the field inventory (latest and best share, unusual fields, `extras` keys) |
| `runs` | state: lineage (scanner commit, repo HEADs, when, how long, last scrape read) |

Every column is described in the `CREATE TABLE` statements at the top of `scan.py`. Re-scanning a
state replaces its rows in one transaction, and gives the same contents.

How files are compared: raw file names are random per scrape and every bill file has a fresh
`scraped_at` and `_id`, so bills are matched by session + identifier, votes by bill + roll-call
id + date + motion + chamber, and contents by a hash with those volatile keys left out. A field
"lost" means filled in the bill's last-seen version and empty now (the same rule as option C's
`field_loss.py`, which `check_known.py --field-loss-dir` compares row for row).
