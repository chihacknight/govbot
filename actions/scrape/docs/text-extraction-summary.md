# Text Extraction Pilot Summary

Results from running `actions/format` + `actions/extract` (full-text extraction) against
real scraper data for all 56 jurisdictions, in an isolated test org (`govbot-test`) before
cutting the real `govbot-data` repos over.

Last updated: **2026-07-13** (evening pass — several real bugs found and fixed since the
first version of this doc: errors were silently not failing the run, per-bill error detail
was written to a folder that was never committed so it just vanished, and download errors
showed a generic message instead of the real one. All fixed; see the git log on
`feat/session-scoped-repo-lifecycle` for the individual commits.)

---

## TODO: turn on Slack error notifications

`actions/extract` already supports posting to Slack when a run has errors (state, error
count, up to 20 failed bills with their real error messages, and a link to the run) --
it's just waiting on a webhook URL. To make it live:

1. **Get an Incoming Webhook URL** for the govbot Slack channel from someone at Chi Hack
   Night who manages the workspace (Slack → that workspace's App Management →
   "Incoming Webhooks" → Add to Slack → pick the channel → copy the webhook URL).
2. **Add it as an org-level secret** named `SLACK_WEBHOOK_URL` — same pattern as
   `PAT_WORKFLOW_TRIGGER`:
   `github.com/organizations/{org}/settings/secrets/actions` → New organization secret →
   name `SLACK_WEBHOOK_URL` → paste the webhook URL → visibility "All repositories" (or
   select the jurisdiction repos specifically).
   - For continued pilot testing: add it to the `govbot-test` org.
   - For production: add it to whichever org ends up hosting the real `govbot-data`
     repos.
3. **That's it — no code or template changes needed.** `extract-text.yml`'s template
   already passes `secrets.SLACK_WEBHOOK_URL` through to the action; it silently does
   nothing while the secret is unset, and starts posting automatically once it exists.
4. If the workflow template hasn't been synced to the target org's repos yet (i.e. this
   step happened after the last `apply.py` run), sync it:
   ```
   cd actions/pipeline-manager
   python3 apply.py --config <the relevant config file> --all-states --no-delete
   ```
5. To confirm it's working: trigger `extract-text.yml` manually on a state known to have
   errors (e.g. `govbot-test/co-legislation`, `govbot-test/pr-legislation`) and check the
   Slack channel for the message.

---

## Summary

| Status | Count |
|--------|------:|
| ✅ Working (clean run, 0 errors) | 37 |
| ⚠️ Partial (real errors surfaced — now visible thanks to tonight's fixes) | 8 |
| 🔄 In progress (extraction still running as of this doc) | 5 |
| ❌ No data (known scraper issue, pre-existing) | 5 |
| ❌ Problem child (extraction itself won't complete) | 1 (MA) |
| **Total** | **56** |

Several of the ⚠️ Partial states (HI, CO) were previously miscategorized as either
"in progress" or falsely "✅ Yes" — their errors were real all along, just hidden by the
exit-code bug fixed tonight. Nothing about the underlying data changed; visibility did.

---

## How this data was gathered

- **Session(s)**: subfolder names under `country:us/state:{code}/sessions/` in each state's
  `govbot-test` repo (i.e. the session(s) the formatter actually wrote data for, not what's
  theoretically active).
- **Bills**: `Total bills` reported by the extract-text run (count of `metadata.json` files
  present in the repo at run time) — this is the repo's current bill inventory, not
  necessarily how many were newly formatted in one run.
- **File Type(s)**: file extensions found in one bill's `files/` folder (excludes
  `_extracted.txt`, which is our own output, not the source format). Empty means that bill
  had no downloadable version links, not that the format is unknown.
- **Successful / Skipped / Errors**: from the extract-text run's own summary line.
  "Skipped" means the incremental logic determined that bill/version was already extracted
  in a prior run — see [[project overview]] on the per-version file-existence skip.
- **Working?**: ✅ clean run, ⚠️ ran but with real errors or an open question worth
  checking, 🔄 extraction was still in progress when this doc was generated (numbers will
  change), ❌ no bill data to extract from in the first place (a scraper problem, not an
  extraction problem).

---

## Table

| State | Name | Session(s) | Bills | File Type(s) | Working? | Successful | Skipped | Errors | Notes |
|---|---|---|---:|---|:---:|---:|---:|---:|---|
| AK | Alaska | 34 | 514 | html | ✅ Yes | 4 | 510 | 0 | — |
| AL | Alabama | 2026rs | 1507 | pdf | ✅ Yes | 0 | 1507 | 0 | — |
| AR | Arkansas | — | — | — | ❌ No | — | — | — | No bill data -- known scraper issue, active session but 0 bills produced |
| AZ | Arizona | — | — | — | ❌ No | — | — | — | No bill data -- Sucuri WAF blocks setsession.php POST |
| CA | California | 20252026, 20252026 Special Session 1 | — | — | 🔄 In progress | — | — | — | Extraction still running as of doc creation |
| CO | Colorado | 2026A | 714 | html | ⚠️ Partial | 1 | 697 | 16 | 16 real errors, all `403 Client Error: Forbidden` from Colorado's S3-hosted bill files (beta.leg.colorado.gov). Worth flagging to whoever owns CO's scraper -- may need different auth/headers for that S3 bucket. |
| CT | Connecticut | 2026 | 1283 | pdf | ✅ Yes | 178 | 1105 | 0 | — |
| DC | District of Columbia | 26 | 1725 | — | ✅ Yes | 0 | 1725 | 0 | — |
| DE | Delaware | 153 | 1289 | html | ✅ Yes | 490 | 799 | 0 | — |
| FL | Florida | 2026F | 5 | pdf | ✅ Yes | 0 | 5 | 0 | — |
| GA | Georgia | 2026_ss | 176 | pdf | ✅ Yes | 0 | 176 | 0 | — |
| GU | Guam | 38th | 277 | pdf | ⚠️ Partial | 8 | 268 | 1 | 1 errors during extraction |
| HI | Hawaii | 2026 | 6640 | pdf | ⚠️ Partial | 1 | 6634 | 5 | 5 real 404s (data.capitol.hawaii.gov dead links, e.g. SB883_.HTM not found) out of 6,640 bills -- clean otherwise. Was WAF-blocked per the old audit; that's clearly resolved now (real data flowing), this is a separate, minor issue. |
| IA | Iowa | 2025-2026 | 3744 | pdf | ✅ Yes | 959 | 2785 | 0 | — |
| ID | Idaho | 2026 | 1 | pdf | ✅ Yes | 0 | 1 | 0 | — |
| IL | Illinois | — | — | — | ❌ No | — | — | — | No bill data in scraper repo -- **regression**: bill-format-audit.md (2026-07-02) showed IL had real bill data with html+pdf formats. Something broke since then. |
| IN | Indiana | 2026 | 40 | pdf | ✅ Yes | 0 | 40 | 0 | — |
| KS | Kansas | 2025-2026 | 1483 | pdf | ✅ Yes | 1 | 1482 | 0 | — |
| KY | Kentucky | 2026RS | 74 | pdf | ⚠️ Partial | 0 | 72 | 2 | 2 errors during extraction |
| LA | Louisiana | 2026 | 7 | — | ✅ Yes | 0 | 7 | 0 | — |
| MA | Massachusetts | 194th | — | — | ❌ Problem | — | — | 2 | PROBLEM CHILD -- extract-text run repeatedly cancelled (5x, ~11-30min each, "runner received a shutdown signal" / exit 143 = SIGTERM). Leading theory: malegislature.gov blocks Azure-hosted (GitHub) runner IPs -- same reason its **scrape** step already needs `runner: self-hosted`. `extract-text.yml`'s template now supports the same runner-override mechanism (built 2026-07-13), but MA's config in `chn-openstates-test.yml` deliberately doesn't set it yet -- `govbot-test` is throwaway pilot infra, not worth registering a runner to. Real fix: register a self-hosted runner to whichever org runs this for real, then set `locales.ma.runner: self-hosted`. |
| MD | Maryland | 2026 | 531 | pdf | ✅ Yes | 0 | 531 | 0 | — |
| ME | Maine | 132 | 2451 | — | ✅ Yes | 87 | 2364 | 0 | — |
| MI | Michigan | 2025-2026 | 2360 | htm, pdf | ✅ Yes | 0 | 2360 | 0 | — |
| MN | Minnesota | 2025-2026 | 9808 | html | ✅ Yes | 4917 | 4891 | 0 | — |
| MO | Missouri | 2026 | 3159 | pdf | ✅ Yes | 0 | 3159 | 0 | — |
| MP | Northern Mariana Islands | 24 | 127 | pdf | ⚠️ Partial | 0 | 124 | 3 | 3 errors during extraction |
| MS | Mississippi | 2026 | 2991 | htm | ✅ Yes | 92 | 2899 | 0 | — |
| MT | Montana | 2025 | — | — | 🔄 In progress | — | — | — | Extraction still running as of doc creation |
| NC | North Carolina | 2025 | 1794 | pdf | ✅ Yes | 677 | 1117 | 0 | — |
| ND | North Dakota | 69 | 1101 | pdf | ✅ Yes | 0 | 1101 | 0 | — |
| NE | Nebraska | 109 | 1037 | pdf | ✅ Yes | 0 | 1037 | 0 | — |
| NH | New Hampshire | — | — | — | ❌ No | — | — | — | No bill data -- known issue, audit noted "no version links" for bills |
| NJ | New Jersey | 222 | 7661 | htm | ⚠️ Partial | 2401 | 5256 | 4 | 4 errors during extraction |
| NM | New Mexico | — | — | — | ❌ No | — | — | — | No bill data -- FTP directory listing regex mismatch in scraper |
| NV | Nevada | 2025Special36 | 27 | pdf | ✅ Yes | 0 | 27 | 0 | — |
| NY | New York | 2025-2026 | — | — | 🔄 In progress | — | — | — | Extraction still running as of doc creation |
| OH | Ohio | 136 | 1538 | html | ✅ Yes | 0 | 1538 | 0 | — |
| OK | Oklahoma | 2026 | 6000 | pdf | ✅ Yes | 0 | 6000 | 0 | — |
| OR | Oregon | 2026R1 | 264 | pdf | ✅ Yes | 0 | 264 | 0 | — |
| PA | Pennsylvania | 2025-2026 | 3578 | html | ✅ Yes | 15 | 3563 | 0 | — |
| PR | Puerto Rico | 2025-2028 | 5106 | pdf | ⚠️ Partial | 522 | 2373 | 2211 | Very high error count (2211/5106, ~43%) -- needs real investigation. bill-format-audit.md notes PR's primary format is `msword`, not currently in the extractor's supported media types (`text/xml`, `text/html`, `application/pdf`, `text/plain`) -- worth checking whether these are PDF-specific parsing failures or a msword-support gap |
| RI | Rhode Island | 2026 | 3011 | pdf | ✅ Yes | 0 | 3011 | 0 | — |
| SC | South Carolina | 2025-2026 | 2244 | htm | ✅ Yes | 1227 | 1017 | 0 | — |
| SD | South Dakota | 2026 | 666 | html, pdf | ✅ Yes | 666 | 0 | 0 | — |
| TN | Tennessee | 114, 114S1 | — | pdf | 🔄 In progress | — | — | — | Extraction still running as of doc creation |
| TX | Texas | 891 | 592 | htm | ✅ Yes | 1 | 591 | 0 | — |
| USA | United States | 119 | 11317 | xml | ✅ Yes | 3132 | 8185 | 0 | — |
| UT | Utah | 2025S2, 2026 | 8 | xml | ✅ Yes | 0 | 8 | 0 | — |
| VA | Virginia | 2026S1 | 0 | — | ⚠️ Partial | 0 | 0 | 0 | Session folder exists but 0 bills inside -- audit noted a session-kwarg fix was in progress, re-check status |
| VI | U.S. Virgin Islands | 36 | — | — | 🔄 In progress | — | — | — | Extraction still running as of doc creation |
| VT | Vermont | 2025-2026 | 898 | pdf | ✅ Yes | 1 | 897 | 0 | — |
| WA | Washington | 2025-2026 | 3411 | htm | ✅ Yes | 1336 | 2075 | 0 | — |
| WI | Wisconsin | 2025, 2026S1 | 1626 | html | ✅ Yes | 0 | 1626 | 0 | — |
| WV | West Virginia | 2026 | 39 | — | ✅ Yes | 0 | 39 | 0 | — |
| WY | Wyoming | 2026 | 23 | pdf | ✅ Yes | 0 | 23 | 0 | — |

---

## Priority follow-ups (roughly in order)

1. **MA** — problem child, extraction can't complete on a GitHub-hosted runner
   (`malegislature.gov` blocking Azure IPs, matching its known scrape-side issue). The
   template now supports a self-hosted runner override (built 2026-07-13) — remaining
   work is registering an actual self-hosted runner to whichever org runs this for real,
   then setting `locales.ma.runner: self-hosted`.
2. **PR** — 43% error rate, highest of any working state. Check whether it's a
   PDF-parsing issue or a missing msword code path.
3. **IL** — real regression (had data 2026-07-02, has none now). Different from the
   other zero-bill states, which were already known-broken at audit time.
4. **AR / AZ / NH / NM** — pre-existing known scraper issues, unchanged since the audit.
5. **VA** — 0 bills despite a session folder existing; worth a quick re-check now that
   its session-kwarg fix was reportedly in progress.
6. **CO** — 16 real 403s from Colorado's S3-hosted bill files, worth flagging to
   whoever owns that scraper (may need different auth/headers for that bucket).
7. **HI** — 5 real 404s (dead links on `data.capitol.hawaii.gov`) out of 6,640 bills,
   otherwise clean. Minor, low priority.
8. **GU / KY / MP / NJ** — smaller error counts (1-4), lowest priority, worth a look
   when time allows.

Five states (CA, MT, NY, TN, VI) were still extracting when this doc was last generated —
re-run the data-gathering pass once they finish.

## What got fixed tonight (non-state-specific, worth knowing about)

- **Exit codes now actually reflect errors.** `main.py`'s `return 1` on errors did nothing
  — Click doesn't propagate a command function's return value to the process exit code.
  Every run with real errors has always shown a green checkmark in the Actions UI. Fixed;
  this alone is why several states above only just started showing their real error counts.
- **Error detail is now visible instead of silently discarded.** Per-bill error files were
  written to `data_not_processed/`, a path `action.yml`'s commit step never adds to git —
  created on the ephemeral runner, gone when the job ended. Failed bills (with the real
  underlying error, not a generic message) now show up in the run's own GitHub Step
  Summary instead.
- **A scheduled trigger could cancel an in-progress run outright.** `extract-text.yml` had
  no `concurrency:` group, so the daily 8AM UTC cron landing mid-run killed the manual run
  instead of queuing behind it. Fixed for both `extract-text.yml` and `format.yml`.
- **`apply.py --test-states` could threaten to delete every other real, configured repo.**
  Deletion candidates are now computed against the full config, not just the scoped subset
  a given run happens to be processing. Caught via `--dry-run` before it ran for real.
- **Slack notifications are built, just need a webhook URL** — see the TODO at the top of
  this doc.
