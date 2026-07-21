# Historical session backfill — inventory across all sources (2026-07-14)

**Status:** working reference, not final. All 3 legacy sources now checked (`govbot-data`,
`windy-civi-pipelines`, `windy-civi-pipelines-V1-archived`) — see the V1-archived section below,
added last.

## Why

Going forward, the live `govbot-data` repos will only hold **active** sessions — once a session
closes, its repo gets transferred to a dedicated old-sessions archive org and frozen (per
[[project-govbot-immutability-principle]]: still a source of truth, just no longer updated).
Before that cutover, we need to know what historical session data already exists across our
older orgs, so nothing gets lost and we know what to actively backfill into the archive.

**Sources being compared:**

| Source | Org | Role |
|---|---|---|
| `govbot-test` | github.com/govbot-test | Pilot branch's active-session baseline — what we already have, on `feat/session-scoped-repo-lifecycle` |
| `govbot-data` | github.com/govbot-data | Current production repos (just restarted, no text-extraction data yet) |
| `windy-civi-pipelines` | github.com/windy-civi-pipelines | Second-oldest org, 56 `{state}-data-pipeline` repos (+ 4 non-state repos excluded: `.github`, `windy-civi-bluesky-bots`, `windy-civi-template-pipeline`, `wy-data-pipeline-sample2`), disabled 2026-06-27. Has real text-extraction data. |
| `windy-civi-pipelines-V1-archived` | github.com/windy-civi-pipelines-V1-archived | **Oldest** org, pre-dates the current path schema. 90 repos, genuinely messy — see its own section below. |

## Method

For each repo in each org:

```
git clone --filter=blob:none --depth=1 --no-checkout <repo-url>
git ls-tree -r --name-only HEAD
```

Blobless clone — full path listing, no file *contents* ever downloaded, so it's fast even for
huge states. Parsed `country:us/state:{code}/sessions/{session}/bills/{bill_id}/...` paths to
get, per session: bill count, and (where text exists) whether each bill has a populated
`files/` folder.

Both `govbot-data` and `windy-civi-pipelines` turned out to use the **same current path layout**
as `govbot-test` — no schema-translation needed. One caveat: a handful of filenames with accented
characters (é, í, ó, ñ) get quoted/octal-escaped by `git ls-tree`, which the parser doesn't
match — confirmed this only affects states already fully covered elsewhere (il, ma, mn, pr, wa),
so it doesn't change any number below.

Scripts (not yet committed to the repo — ask if these should move into
`actions/pipeline-manager/scripts/`): `fetch_trees.sh` / `parse_audit.py` (govbot-test),
`fetch_trees_data_org.sh` / `parse_data_org_sessions.py` (govbot-data),
`fetch_trees_wcp.sh` / `parse_wcp.py` (windy-civi-pipelines) — all in the working session's
scratchpad.

## Master inventory — sessions needing backfill

**28 state/session combinations exist in at least one older org but not in `govbot-test`.**
Bill counts shown per source where that source has the session at all.

| State | Session | govbot-data | windy-civi-pipelines | Note |
|---|---|---:|---:|---|
| ar | 2025 | 1,928 | 1,928 | agree |
| co | 2025B | 35 | 70 | **mismatch — see below** |
| ct | 2025 | 4,076 | — | govbot-data only |
| fl | 2026 | 1,916 | 649 | **mismatch — see below** |
| fl | 2026D | 6 | — | govbot-data only |
| ga | 2025_26 | 5,480 | 2,860 | **mismatch — see below** |
| hi | 2025 | 4,704 | 4,704 | agree |
| id | 2025 | 790 | 790 | agree |
| ky | 2025RS | 1,441 | 1,441 | agree (file-level: wcp shows 28 bills missing `files/`) |
| la | 2025s1 | 12 | 10 | **mismatch — see below** |
| md | 2025 | 2,617 | 2,617 | agree |
| mn | 2025s1 | 48 | 48 | agree (wcp shows all 48 missing `files/` — extraction never ran for this session) |
| mo | 2025S2 | 15 | 15 | agree |
| ms | 20251E | 106 | 106 | agree |
| nh | 2025 | 1,072 | 1,072 | agree (file-level: wcp shows 553/1,072 missing `files/`) |
| nj | 221 | 11,795 | 11,446 | **mismatch — see below** |
| nm | 2025S1 | — | 11 | windy-civi-pipelines only |
| nm | 2025S2 | 2 | — | govbot-data only (different session than the row above, not a duplicate) |
| nv | 83 | — | 1,210 | windy-civi-pipelines only |
| ok | 2025 | 3,257 | 3,257 | agree (file-level: wcp shows 2 bills missing `files/`) |
| or | 2025S1 | 3 | 3 | agree |
| ri | 2025 | 2,595 | 2,595 | agree |
| sd | 2025s | 2 | 2 | agree |
| tx | 892 | 692 | 692 | agree |
| tx | 89R | 11,503 | — | govbot-data only |
| ut | 2025S1 | 18 | 18 | agree |
| wv | 2025 | 2,709 | 2,709 | agree (file-level: wcp shows 1 bill missing `files/`) |
| wy | 2025 | 556 | 556 | agree |

(Sessions already in `govbot-test` — ak/34, al/2026rs, de/153, gu/38th, ia/2025-2026, il/104th,
ks/2025-2026, ma/194th, me/132, mi/2025-2026, mn/2025-2026, mp/24, mt/2025, nc/2025, nd/69,
ne/109, nv/2025Special36, oh/136, pa/2025-2026, pr/2025-2028, sc/2025-2026, tn/114, tn/114S1,
usa/119, vi/36, vt/2025-2026, wa/2025-2026, wi/2025 — excluded from the table above, no action
needed.)

## Cross-source discrepancies — union, not winner-take-all

Five sessions above show **different bill counts between `govbot-data` and
`windy-civi-pipelines` for the same session** (co/2025B, fl/2026, ga/2025_26, la/2025s1, nj/221).
Checked two of these by diffing actual bill IDs (not just counts), and found the failure mode
differs per case — **neither "pick the bigger source" nor "pick the newer source" is a safe
general rule**:

- **co/2025B**: `govbot-data`'s 35 bills are a clean *subset* of `windy-civi-pipelines`'s 70 —
  windy-civi-pipelines alone would be sufficient here.
- **fl/2026**: genuinely split. 644 bills in both, 1,272 unique to `govbot-data` (expected — it
  kept scraping after this org was retired), but **5 bills exist only in
  `windy-civi-pipelines` and are missing from govbot-data**: `SPB7000, SPB7002, SPB7004,
  SPB7006, SPB7008`. Likely dropped by the already-documented wholesale-overwrite scraper bug
  (see [[project-govbot-scraper-overwrite-problem]]) — a thin/failed re-scrape silently deleting
  previously-captured bills.

**Conclusion**: the backfill needs to **union bill IDs per session across every source**, then
for any bill present in multiple sources, take the most complete/most recent version of *that
bill's* data — not just pick one repo wholesale per session. `ga/2025_26`, `la/2025s1`, and
`nj/221` haven't been diffed at the bill-ID level yet; same check should be run on those three
before deciding a merge approach.

## `windy-civi-pipelines-V1-archived` — the oldest, messiest org

90 repos total, pre-dating the current path schema (`data_output/data_processed/country:us/...`
instead of today's `country:us/...` at repo root — see `DATA_STRUCTURES.md`'s migration guide).
Tamara: "we lost to repeat repos while I was trying to update things" — many states have 2-8
candidate repos from repeated setup attempts, not all of them real.

### Triage before cloning anything

**Excluded outright (non-state/template, 10 repos):** `.github`, `STATE-windy-civi-data-pipeline`,
`USA-pipeline-sample`, `dev-repo-sync`, `template-data-pipeline-NSD`, `template-data-pipeline-v1`,
`template-data-pipeline-with-saved-scraper-data`, `test-pipeline`,
`windy-civi-template-no-scraper-data`, `windy-civi-template-pipeline-split-action1`.

**Excluded as near-empty placeholders (repo size 7-50KB, no real data):** `dc-data-pipeline`,
`dc-data-pipeline-with-text`, `gu-data-pipeline-old`, `il-data-pipeline_old`,
`nm-data-pipeline-old`, `ok-data-pipeline`, `tx-data-pipeline_old`.

**Method for the remaining multi-candidate states**: rather than clone every variant, pulled each
candidate's first and last commit date via `gh api repos/{org}/{repo}/commits --paginate -f
per_page=100 --jq '.[].commit.committer.date'`, then cloned only the **oldest-first-commit** and
**newest-last-commit** variant per state and diffed their bill-ID sets (normalized: whitespace
stripped, uppercased, since old-format bill IDs sometimes have spaces — e.g. `"HB 1"` vs `"HB1"`).
This cut ~29 candidate repos down to 18 actual clones. Confirmed pattern held everywhere tested:
**the newest variant is a superset of the oldest — no case found where the older repo had bills
missing from the newer one within this org.**

### Two real bugs found during triage (not just naming noise)

- **`tx-data-pipeline` is mislabeled** — despite the name, its `country:us/state:*` paths are all
  `state:id` (Idaho), not Texas. `tx-data-pipeline-old` is the only genuine TX repo in this org.
- **`gu-data-pipeline`** has no processed/formatted data at all — only raw unformatted
  `_data/gu/bill_*.json` (pre-`format`-stage scraper output). Nothing to compare for GU from this
  org; would need a full `format` run to become usable.

### USA — special case, resolved fully

Per your suggestion: checked just the oldest-first-commit variant (`usa-data-pipeline2`, first
commit 2025-07-28) against the newest-last-commit one (`usa-data-pipeline_3`, last commit
2026-03-28) rather than diffing all 8 USA variants. Result: **clean chain, zero orphans anywhere**
— `usa-data-pipeline2` (8,440 bills) ⊂ `usa-data-pipeline_3` (10,383 bills) ⊂ current
`govbot-test` (17,329 bills for session 119). None of the 8 USA repos in this org hold anything
`govbot-test` doesn't already have.

### Results — oldest vs. newest, then vs. current `govbot-test`

| State | Old repo bills | New repo bills | Orphans (old→new) | vs. current `govbot-test` |
|---|---:|---:|---:|---|
| il (104th) | 8,079 | 8,494 | 0 | 0 orphans (test has 12,753 — clean superset) |
| ok (2025≈test's 2026) | 3,254 | 3,254 | 0 | **2 real orphans**: `HB9001`, `HB9002` missing from test's 6,000-bill session (99.9% overlap otherwise — confirmed same real session, just renamed at some point) |
| tn (114 + 114S1) | 4,560 | 4,570 | 0 | 0 orphans on both sessions (test has 9,092 + 20) |
| wi (2025) | 925 | 1,256 | 0 | 0 orphans (test has 1,624 — clean superset) |
| wy (2025) | 556 | 556 | 0 | matches windy-civi-pipelines' already-known wy/2025 finding exactly (556) — no new info |
| dc | 699 | — (single candidate) | n/a | 0 orphans — same session as test's "26", just under its old full name (`26th Council Period (2025-2026)`) |
| tx (892) | 311 (single candidate, `-old`) | — | n/a | clean subset of windy-civi-pipelines' already-known tx/892 (692 bills) — no new info, not test's "891" (a genuinely different TX session, wrong comparison to make) |
| md (2025 Regular Session) | 2,617 | 2,617 (identical, `-NSD` variant is a duplicate) | 0 | **not in `govbot-test` at all** — confirms the already-known missing session from the other two orgs, no new info |
| nm (2025 Regular Session) | 1,328 | — (only in `nm-data-pipeline`, the `-older` variant only has session `2025S1`) | n/a | **NEW FINDING — not previously captured**: only 60.4% bill-ID overlap with test's "2026" session (802/1,328) — this is a genuinely different, additional NM session missing from the master inventory, not a rename. See update to master table below. |
| nm (2025S1) | 11 (only in `-older` variant) | — | n/a | matches windy-civi-pipelines' already-known nm/2025S1 (11 bills) — no new info |
| gu | — no processed data | — | n/a | nothing to compare |

### Update to the master inventory

Add one row not previously found by the other two orgs:

| State | Session | Bills | Source |
|---|---|---:|---|
| nm | 2025 Regular Session | 1,328 | `windy-civi-pipelines-V1-archived/nm-data-pipeline` only |

And one small real data-loss note for the reconciliation list (separate from "needs backfill" —
this is a session we already have, just missing 2 bills):

- **ok / 2026 (called "2025" in older sources)**: missing `HB9001`, `HB9002` that exist in the
  V1-archived snapshot. Small, but worth folding into whatever process ends up doing the
  bill-level union merge.

## Next steps

1. Run the same bill-ID-level diff (not just counts) on `ga/2025_26`, `la/2025s1`, `nj/221`
   (from the `windy-civi-pipelines` org, not yet done) to confirm whether they're subset cases
   (like co) or split cases (like fl) needing a real union.
2. Decide and build the actual merge/union logic for backfilling a session from multiple
   sources — not yet designed. Should also cover the tiny `ok` 2-bill gap found above.
3. Decide what to do with `gu-data-pipeline`'s raw-only data (needs a `format` run to become
   usable) and the mislabeled `tx-data-pipeline` (Idaho content under a Texas name — worth a
   heads-up to whoever else might reference that repo name).
4. Decide whether `fetch_trees*.sh` / `parse_*.py` scripts should be committed into
   `actions/pipeline-manager/scripts/` as reusable tools (they generalize cleanly to "diff two
   `country:us/...`-shaped trees," including the old pre-migration schema, for any future
   backfill/reconciliation need).
5. Raw CSVs and tree dumps backing every table above live in the working session's scratchpad
   (`audit_summary.csv`, `data_org_sessions.csv`, `wcp_sessions.csv`,
   `master_session_inventory.csv`, `trees_v1archived/`) — ask if these should be copied into the
   repo alongside this doc for permanence.
