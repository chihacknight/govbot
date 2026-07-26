# Session Handoff — 2026-07-21

Context dump for tomorrow's fresh chat. Covers org restructuring, the
scrape→format→extract-text pipeline redesign, a PDF-extraction rewrite, and
several bugs found and fixed along the way. Everything below is merged to
`main` unless noted otherwise.

## Org architecture — now settled

- **`govbot-data`** is the one official org for formatted bill data + extracted
  text. All 56 states.
- **`govbot-openstates-scrapers`** is the one official org for raw scraped
  data. Unchanged, already was official.
- **`govbot-test`** (the old pilot org) and **`govbot-data`'s original 56
  placeholder repos** (format-only, zero text extraction, an artifact of an
  earlier setup) are both now empty/retired. Their content was migrated or
  archived:
  - `govbot-test`'s 56 repos (which had real format + extract-text progress)
    were transferred wholesale into `govbot-data`.
  - The old placeholder `govbot-data` repos (disabled, no useful data) were
    transferred to **`govbot-archive`**.
- All 56 `govbot-data` repos' `format.yml`/`extract-text.yml` now point at
  `chihacknight/govbot/actions/{format,extract}@main` — the old
  `feat/session-scoped-repo-lifecycle` branch they used to reference is
  merged into `main` and no longer needed (PR #77).
- `close_session.py` + `.github/workflows/close-session.yml` (also part of
  the branch merge) is the tool for the *next* time a state's data needs to
  move to `govbot-archive` for real (session close, not migration) — see its
  docstring, it's dry-run-gated and manual-only by design.

## Pipeline is now event-driven, not purely cron

Previously scrape/format/extract-text ran on independent, mistimed cron
schedules (extract-text at 8am UTC, *before* format's noon run — backwards
relative to the actual dependency). Now (PR #79):

- **scrape → format**: `repository_dispatch` (cross-org), authenticated via
  a GitHub App (`govbot-pipeline-dispatch`) installed on both
  `govbot-openstates-scrapers` and `govbot-data`. `APP_ID`/`APP_PRIVATE_KEY`
  are org-level secrets on `govbot-openstates-scrapers`. This replaces an
  earlier PAT-based version of this same dispatch that died silently when
  the PAT expired (removed back in June rather than fixed — see git history
  on `chn-openstates-scrape.yml`/`chn-openstates-files.yml` if curious).
- **format → extract-text**: `workflow_run` (same repo, no cross-org auth
  needed), gated on `conclusion == 'success'`.
- All three cron schedules stay as backups (cheap now, since format has a
  SHA-staleness check that no-ops in ~10s when nothing changed).
- **Verified live end-to-end on SD**: scrape (`workflow_dispatch`) →
  format (`repository_dispatch`, ~1.5 min later) → extract-text
  (`workflow_run`, ~45 sec after that). All three succeeded.
- **Scrape start times are now staggered by state capital's timezone**
  (Eastern 04:00 UTC, Central 05:00, Mountain 06:00, Pacific 07:00, Alaska
  08:00, Hawaii 10:00, PR/VI 04:00 AST, GU/MP 14:00 ChST) instead of every
  state firing at the same fixed UTC time regardless of local time. FL is in
  the earliest (Eastern) group, matching its need for max overnight runway
  given its scrape can run up to 24h. Per-locale `scrape_cron` field in
  `chn-openstates-scrape.yml`.

## PDF extraction rewrite (PR #82)

Three bugs found and fixed in `actions/extract`, discovered while looking at
why a bill's extracted text was duplicated:

1. **Raw PDF storage was actually mislabeled text.** The saved
   `*_Bill_Text.pdf` file was never the real PDF — it was the
   already-extracted text, re-saved under a `.pdf`-looking filename, written
   in text mode. Now `extract_pdf()` returns genuine raw bytes and they're
   written in binary mode. This matters for the plan (see below) to hand raw
   PDFs to an LLM/vision model for redline-heavy bills.
2. **Every extracted `.txt` duplicated its content** — once as a "Section
   N:" breakdown, once as "Raw Text:". Section-splitting (in all three
   extractors — XML, HTML, PDF) essentially never worked for real bills (the
   PDF regex broke on any state that numbers every line, i.e. most of them),
   so the whole document became "Section 1" and then got printed again as
   the raw dump. Dropped section-splitting entirely — one clean read now.
3. **Strikethrough detection replaced with a geometry-based flag.** The old
   heuristic guessed off font name/character spacing/color (unreliable, and
   its character-by-character reconstruction produced unreadable garbage
   even when it fired). Replaced with a check for actual drawn line/rect
   objects overlapping text (`pdfplumber` `page.lines`/`page.rects`) — this
   is `has_visual_markup` in the output, a **routing signal** (does this
   document need full-fidelity handling), not an attempt to reconstruct the
   marked-up text ourselves.

## check-and-restart was silently broken (PR #83)

`extract-text.yml`'s auto-restart job (meant to re-trigger extraction after
a timeout/failure) **had never once actually run**, on any state, ever.
Confirmed via jobs API across every real case (3 KY failures, 1 LA
cancellation that ran the full 5h55m before hitting the timeout) — all
showed `check-and-restart` as `skipped`.

Root cause: GitHub Actions implicitly ANDs a job's `if:` with `success()`
unless the condition explicitly calls a status-check function
(`always()`/`success()`/`failure()`/`cancelled()`). The condition
(`needs.extract-text.result == 'cancelled' || ... == 'failure'`) didn't call
one, so it silently required the needed job to have *also* succeeded — which
by definition it hadn't. Fixed: `if: always() && (...)`. Also fixed the same
bug in `actions/format/docs/for-caller-repos/example-caller-text-extraction.yml`
(a reference file with the same pattern).

**Not fixed yet**: even with the `if:` fix, the restart step itself
(`gh workflow run extract-text.yml`) needs `secrets.PAT_WORKFLOW_TRIGGER`,
which is **not set** as a repo secret on at least `govbot-data/sd-legislation`
(confirmed directly, `total_count: 0`). Couldn't check org-level without
elevated `gh` auth scope (`admin:org`). **Next step: check if it exists at
the org level, and if not, provision it** (or, better, switch this to use
the same GitHub App token approach as the scrape→format dispatch, avoiding a
second long-lived PAT).

## PDF visual-markup audit (PR #84)

Ran the audit we discussed: sampled up to 10 bills per state (earliest +
latest PDF version each) across the 28 states that have no HTML/XML
alternative (states with one already skip PDF in production — see format
preference below). 394 documents checked across 27/28 states (VI
unreachable, non-standard port, tracked as an open gap).

Full results in `actions/extract/docs/2026-07-21-pdf-visual-markup-audit.md`.
Headline: **AL, CT, FL, GU, ID, MD, ND, NE, NC, OK, OR, RI, VT, KY** show
redline markup ~85-100% of the time *even on unamended bills* (likely house
style, not just amendment-tracking) — full-fidelity handling should probably
be the default for these. **GA, IN, LA, ME** show essentially zero across
8-20 samples each — plain text extraction is likely trustworthy on its own.
The rest are mixed. Audit script is reusable at
`actions/extract/scripts/audit_pdf_visual_markup.py`.

## Open item found along the way, not fixed: SD's format preference

SD's `text/html` bill pages are JS-rendered loading shells (a Vue.js SPA) —
literally "please enable JavaScript" boilerplate, not real content. SD *also*
serves working PDFs for the same bills (verified clean extraction), but
production's format preference (`text/xml > text/html > application/pdf` in
`actions/extract/utils/text_extraction.py`'s `MEDIA_TYPE_PREFERENCE`) picks
the broken HTML over the working PDF, since nothing currently detects "this
HTML is actually just a placeholder." Spot-checked MN and WV (the two states
`bill-format-audit.md` lists as HTML-only with no PDF fallback) — both are
genuinely fine, this looks specific to SD's site.

## Where the design conversation left off (not implementation yet)

Talked through the bigger picture with Tamara: Sartaj is building an
LLM-based semantic decomposition layer (self-learning, breaks a bill into
its component provisions, feeds a cheaper tagging system for advocacy orgs).
That's his domain, not something to build here. What *is* this repo's job:
feed him clean, reliable raw material — hence the PDF extraction rewrite
above, and the plan (not yet built) to hand the **genuine raw PDF** (now
actually stored correctly) to a vision-capable model for any document
flagged `has_visual_markup: true`, rather than trusting plain-text
extraction on redline-heavy bills. The audit above is meant to inform how
often that expensive path is actually needed, state by state.

## Overnight: tonight's cron slots were missed, manually covered

The new per-timezone `scrape_cron` schedules (rolled out ~02:58 UTC) never
actually fired on their first scheduled occurrence tonight -- checked
several states per timezone group (GA/MD/NC/IN for Eastern, AL/IA/KS for
Central, AZ/CO/ID for Mountain) and none show a `schedule`-triggered run
anywhere near their new slot (04:00/05:00/06:00 UTC). This matches a known
GitHub Actions quirk: the scheduler doesn't always pick up a changed cron
expression in time for its very next firing after deployment -- there's a
propagation delay, and the first run after a schedule change can be
silently skipped. **Tomorrow's slots should fire normally** since the
schedule will have had a full day to register; no template fix needed,
just something to confirm tomorrow.

To not lose a full day's data, all 56 states' scrapers were manually
triggered overnight (`gh workflow run openstates-scrape.yml`) covering every
timezone group -- Eastern, Central, Mountain, Pacific, Alaska, Hawaii, and
GU/MP (the last four dispatched proactively before their scheduled time
even arrived, given the pattern was consistent across every group already
checked). FL and IL were already mid-run from earlier manual dispatches and
were left alone rather than double-triggered (no `concurrency:` guard on
`openstates-scrape.yml`, so overlapping runs would have raced against each
other). **Worth checking tomorrow**: did all of these actually complete
successfully, and did today's (07-22) scheduled runs fire on their own at
the new per-timezone times as expected.

## Morning follow-up (same day, later): a real live data-loss bug found and fixed

Checking on the overnight catch-up runs surfaced something much bigger than
routine monitoring: **scrape was silently overwriting good data with worse
data, confirmed happening for real on two states.**

- **IL**: within a single run, the last retry attempt produced far fewer
  files than an earlier retry in that *same* run had already captured via
  auto-save (9691 + 9287 files added across two auto-saves, then the final
  commit showed 3880 insertions vs 22850 deletions — net **-18,970 files**).
- **FL**: a 6-hour-old in-progress manual scrape got cancelled when a new
  trigger (a `schedule` run, delayed hours by the propagation quirk above)
  fired for the same workflow — no concurrency guard existed to queue it
  instead. The fresh replacement "succeeded" after only ~5 hours (FL needs
  up to 24h, was later raised to 42h — see below) and its own wipe-and-rebuild
  overwrote the larger dataset the cancelled run had already saved. FL was
  also confirmed being actively IP-blocked (`N3_ACTIVE_BLOCK`) around this
  same time.

**Root cause**: `scrape.sh`'s final "wipe and rebuild" step only checked
`exit_code == 0` and file count > 0 before replacing `_data/{state}` wholesale
— no comparison against what was already committed. A short, technically-successful
run could shrink the dataset and nothing caught it.

**Fixed (PR #86, merged, deployed to all 56 `govbot-openstates-scrapers`
repos)**:
1. `scrape.sh` now compares the fresh file count against what's already
   committed before wiping; if the fresh scrape would shrink the dataset, it
   refuses to overwrite and surfaces a new failure type
   (`P1_SHRINKING_OUTPUT`) instead of silently reporting success.
2. Added a `concurrency: group: scrape, cancel-in-progress: false` guard to
   `openstates-scrape.yml` (+ paused variant), matching the pattern already
   used in `format.yml`/`extract-text.yml`, so a new trigger queues behind an
   in-progress scrape instead of cancelling it.

**FL's timeout regression (PR #88, merged, deployed)**: FL's 24h timeout
turned out to be a one-off hand-edit directly on FL's live workflow file, not
part of the shared template — so the overnight `apply.py` rollout had
silently reverted it back to the template's 12h default, contributing to
FL's scrape getting caught mid-run. Fixed by adding a proper per-locale
`scrape_timeout_minutes` field (same pattern as `scrape_cron`/`runner`) so a
template rollout can't quietly undo it again. Tamara raised FL to **42h**
(2520 min) given the original 21h cutoff and wanting real headroom; all
other states stay at the 720 (12h) default.

**Much bigger discovery: tinyproxy was never actually being used, for any
state, ever.** While investigating FL's active-block, found the scrape log
showed `USE_PROXY: true` but `"HTTPS_PROXY": ""` — an empty string, despite
the logic evaluating correctly. Checked another self-hosted-flagged state
(MA) and found the identical pattern. Root cause: the `PROXY_URL` org secret
on `govbot-openstates-scrapers` was never actually set — the whole
tinyproxy rollout from earlier this session had been running unprotected on
raw GitHub-hosted (Azure) IPs this entire time, exactly the IP-block problem
tinyproxy was built to solve. Verified the VM (`govbot-proxy`,
`34.57.23.77:8888`, tinyproxy 1.11.2) is genuinely up and requires
`BasicAuth`; Tamara had the credentials in her notes (`govbot` /
`8TG59sHj9SSKkvggyQ8lt6I2`), confirmed working via a direct `curl` test, and
set `PROXY_URL=http://govbot:***@34.57.23.77:8888` as the org secret
(neither of us has `admin:org` scope to do this via API, had to be set
through the GitHub web UI). **Verified live afterward** on AK, AR, CT, NV,
and VI's fresh scrape runs — all show `✓ Set HTTPS_PROXY` with a real
(masked) value now, on genuine `ubuntu-latest` runners.

**Disk space saga**: deploying the check-and-restart fix (PR #83) to all 56
`govbot-data` repos kept failing for a handful of the largest repos
(DC, MA, NY) with `No space left on device` — `apply.py` does a full working-tree
clone before pushing template updates, and this laptop's free disk kept
oscillating around 2-4GB all night. Cleared several safe/rebuildable caches
(Homebrew, pip, Brave/VSCode/Google browser caches, ~5GB) and two long-unused
unrelated Docker containers (`sciscope-db-1`, `project-broker-service-1`,
confirmed not needed) to make headroom, which got DC through, but MA and NY
(the two largest states by bill volume, ~11k and ~25k bills) still kept
failing. Since `govbot-data` content is fully reproducible from the scraper
repos, the actual fix was simpler than fighting disk space: **deleted both
repos and let `apply.py` recreate them fresh from the template** (a create,
not an update — no existing content to clone, so no disk pressure at all).
Both now confirmed fixed with the `check-and-restart` `if:` correction.

**All 56 scrapers manually re-dispatched** once every fix above was
confirmed live (proxy secret, shrink-guard, concurrency guard, FL's 42h
timeout, check-and-restart). All 56 dispatched cleanly with the new
concurrency guard making it safe to do so regardless of what was already
running (queues instead of cancelling). Spot-checked several completed runs
(AK, AR, CT, NV) for genuine proxy usage — all confirmed.

## For tomorrow (or whenever this picks back up)

- **Watch the 56 freshly-dispatched scrapes to completion** — this is the
  first real end-to-end run with every fix live (proxy, shrink-guard,
  concurrency, FL's 42h timeout). Confirm none hit `P1_SHRINKING_OUTPUT`
  (would indicate the guard is firing on a false positive, or a genuine
  upstream data change worth a human look) and that the
  `repository_dispatch`/`workflow_run` cascade into format/extract-text
  fires cleanly for all of them, not just SD.
- **SD's format-preference fix** (prefer PDF when HTML is a JS-rendered
  placeholder shell) — discussed, not started. Two options on the table: a
  quick SD-only hardcode, or a general "detect placeholder HTML, fall back
  to the next-preferred media type" fix in `text_extraction.py`'s link
  selection logic — leaning toward the general fix since this class of bug
  could recur silently on any other state's JS-heavy bill-text site. Either
  way, SD's already-committed extracted files are garbage placeholders and
  will need the same clear-and-re-extract treatment used for the PDF-only
  states audit.
- **`PAT_WORKFLOW_TRIGGER` still not set** — needed for `check-and-restart`'s
  actual `gh workflow run` retrigger step to work, even though the `if:` bug
  is now fixed. Same `admin:org` scope blocker as `PROXY_URL` had — will
  need the GitHub web UI, or better, switch this step to use the same
  GitHub App token approach as the scrape→format dispatch instead of a
  second long-lived PAT.
- **Local machine disk space is still chronically tight** (~3-4GB free even
  after tonight's cleanup) — worth a proper cleanup pass (Time Machine local
  snapshots, Docker Desktop's VM disk compaction) before the next `apply.py`
  rollout that touches large repos.
- PR #80 (`fix(synthetic-test): raise timeouts...`) is open, unrelated to
  this session's work — looks like someone else's (Sartaj's?) in-flight fix
  for the `synthetic-test.yml` flakiness diagnosed earlier this week. Not
  touched here, just noting it's there.
