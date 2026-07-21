# govbot-test extraction backfill audit — 2026-07-14

**Status:** snapshot taken ~20:35 UTC, several repos still running. Re-run the audit script
(below) before acting on any number here as final.

## Why

Before merging `feat/session-scoped-repo-lifecycle` to `main`, we needed a real picture of
what's actually in the 56 `govbot-test` repos (all pointed at that branch) — bill counts per
session, and whether each bill's `files/` folder (original doc + extracted text) actually got
populated. Bill count alone doesn't tell you that; a repo can have thousands of bills and still
be missing text extraction for most of them.

## Method

For each of the 56 `govbot-test/{code}-legislation` repos:

```
git clone --filter=blob:none --depth=1 --no-checkout https://github.com/govbot-test/{code}-legislation.git
git ls-tree -r --name-only HEAD   # full path listing, no file contents ever downloaded
```

Then parsed paths matching `country:us/state:{code}/sessions/{session}/bills/{bill_id}/...` to
count, per state/session: total bills, bills with a non-empty `files/` folder, bills missing
one, and total file count. Blobless clone means this never downloads bill text/PDF content —
only the tree structure — so it's fast and cheap even for large states (usa, ny, il).

Script + parser: `/private/tmp/.../scratchpad/govbot-test-audit/` (fetch_trees.sh,
parse_audit.py) — not yet committed to the repo; ask if these should move into
`actions/pipeline-manager/scripts/` or `actions/extract/docs/` as a reusable tool, similar to
the existing staleness-audit script.

## Initial findings (before any re-dispatch)

Interactive table: **https://claude.ai/code/artifact/7700d13e-368d-4f80-a13a-edf53ed27a8d**

- 56 jurisdictions, ~200K bills total, ~430K extracted files
- **34 sessions had a real missing-`files/` backlog** (i.e. `bills_missing_files > 0`)
- Worst gaps: **WV** (2,975 bills, 39 with files), **MA** (11,026 bills, 720 with files),
  **LA** (2,616 bills, 365 with files), **MT** (77.9% missing), **PR** (59.7% missing)
- **AZ**: 0 bills at all — known scraper bug (Sucuri WAF), not an extraction problem
- **VI**: 148 bills, 0 files — extraction had simply never run
- Fully clean (0% missing): CA, TN, OK, RI, MO, IA, and 11 more

## Action taken

Tamara had already manually re-dispatched `extract-text.yml` for **IL** and **MA** before this
round. Dispatched the same workflow for the remaining **32 repos** with a missing-files backlog:

```
wv (tested first), then:
ak co dc de gu hi in ks ky la me mi mn mp ms mt nc ne nh nj nm ny oh pa pr sc tx usa vi vt wa
```

All target repos already had `extract-text.yml` present (verified from the same tree dumps), and
its `concurrency: { group: extract-text, cancel-in-progress: false }` setting meant a re-dispatch
into an already-running job just queues behind it rather than colliding — safe to fire all at
once.

## Results as of this snapshot (20:35 UTC)

| Status | States |
|---|---|
| ✅ Completed, success | dc, de, ks, me, mn, ms, nh, tx, wa |
| 🔄 Still running | ak, in, mi, mt, nc, ne, ny, oh, pa, sc, vi, vt, wv, il, la (pending→running), usa (pending→running) |
| ⚠️ Completed "failure" — trivial, dead links only | gu (1), ky (2), mp (3), nj (4), nm (3), hi (5) |
| ⚠️ Completed "failure" — real, already-known cause | **co**: 16× `403 Forbidden` from `beta.leg.colorado.gov`'s S3 bucket (needs different auth/headers, not a timeout) &middot; **pr**: 2,211 errors, matches the already-documented msword-format gap in `actions/extract` (unsupported media type) |
| ❌ Cancelled, needs different fix | **ma**: see below |

**Important context on the "failure" ones**: `extract-text.yml` currently marks the whole job
`failure` if even one bill errors, even when hundreds/thousands succeeded. This is the same
design gap already spec'd (not yet built) in
[`error-log-design-note.md`](../docs/error-log-design-note.md) — decouple "job completed" from
"zero errors." None of the failures above are new problems; they're the workflow being noisy
about problems we already knew about (or trivial one-off dead links).

### MA — not a time-window issue, looks like a persistent Azure-IP block

Checked MA's last 7 `extract-text` runs (scheduled + manual) across two days:

```
2026-07-14 20:14 UTC — cancelled
2026-07-14 10:03 UTC — cancelled
2026-07-13 19:41 UTC — cancelled
2026-07-13 13:55 UTC — cancelled
2026-07-13 11:18 UTC — cancelled
2026-07-13 05:26 UTC — cancelled
2026-07-13 05:22 UTC — cancelled
```

Every hour bracket from early morning to evening UTC — zero successes at any time. Each run's
log shows a `📥 Downloading: https://malegislature.gov/...` line, then **nothing** for exactly
11–13 minutes, then `exit code 143` (SIGTERM) — a silent hang, not a 404/403/retry loop like CO
or HI. This matches the already-documented `malegislature.gov` Azure-IP-block behavior (the
reason MA's *scrape* step already runs on Tamara's self-hosted runner) — it looks like the same
block now hitting the *extract-text* step, which is still on `ubuntu-latest`.

**Conclusion: re-dispatching MA at a different hour won't help — it failed at every hour
already tried.** MA's `extract-text.yml` needs the same `runner: self-hosted` override the
scrape template already supports, not a retry.

## Next steps

1. **Re-run the tree audit** once all in-progress runs finish, to see actual backlog reduction
   (this doc's numbers are a snapshot mid-run).
2. **MA**: add `runner: self-hosted` to `extract-text.yml` (mirroring the scrape template's
   existing mechanism), not a re-dispatch.
3. **CO**: investigate the S3 403s — may need a different request header/auth for
   `beta.leg.colorado.gov`'s bucket.
4. **PR**: msword support gap in `actions/extract` is still open — 2,211/5,110 bills affected,
   the single biggest true error count in this batch.
5. **Workflow design**: consider prioritizing the `error-log-design-note.md` fix
   (decouple exit code from per-bill error count) before/around the `feat/session-scoped-repo-lifecycle`
   merge — almost every "failure" in this batch was actually a near-total success, which makes
   the signal noisy right when we most need to trust it for a merge decision.
6. Decide whether the audit script (`fetch_trees.sh` / `parse_audit.py`) is worth committing
   into the repo (e.g. `actions/pipeline-manager/scripts/`) as a reusable tool, alongside the
   existing staleness-audit script.
