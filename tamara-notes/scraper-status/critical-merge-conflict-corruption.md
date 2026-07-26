# CRITICAL: silent git merge-conflict corruption in committed bill data

Found 2026-07-26. **Top priority for next session — start here.**

## The headline finding

GA's committed `_data/ga/` bill data was silently corrupted with literal, unresolved git
merge-conflict markers (`<<<<<<< HEAD`, `=======`, `>>>>>>>`) baked directly into the JSON as
committed file content — **all 352 of 352 `bill_*.json` files**, not a handful. This means every
downstream consumer (format, extract-text, anything reading `govbot-data/ga-legislation`) has
been reading unparseable garbage for GA for **5 days**, and nothing caught it until tonight, by
accident.

## How it was found

Not by design — a side effect of tonight's `fix/commit-summary-identifier-aware` (PR #97). That
fix's `count_distinct_identifiers` function tries to count distinct bills in the *previously
committed* data (via `git archive HEAD -- "_data/{state}/"`) to compare against a fresh scrape.
For GA, it reported `0 → 176` ("Net new content"), which looked at first like a possible bug in
the counting logic itself (see `fix/identifier-count-malformed-json`, PR #98, merged tonight —
that fix was for a *different*, real bug: a single malformed file crashing the whole count via
`xargs` exit 123). But manually reproducing the exact same jq-per-file count against GA's actual
committed tree confirmed the `0` was **correct** — every single `bill_*.json` file at that commit
genuinely fails to parse as JSON, because it's not JSON at all, it's a file with raw conflict
markers still in it.

## Root cause

Traced to commit `0ea65a5e` on `govbot-openstates-scrapers/ga-legislation`, 2026-07-21 07:07:01,
message `"🔄 Auto-merge: kept scraped data"` — added/modified 300 files, every one already
containing conflict markers at commit time.

This commit comes from the conflict-resolution path in `actions/scrape/action.yml`'s "Commit and
push scraped files" step (same logic likely also in `scrape.sh`'s autosave loop — not yet
checked):

```bash
if ! git pull --no-rebase origin "$BRANCH" 2>&1; then
  echo "⚠️ Merge conflict detected, resolving..."
  git checkout --ours "_data/${{ inputs.state }}/" 2>/dev/null || true
  git add "_data/${{ inputs.state }}/"
  git commit --no-edit -m "🔄 Auto-merge: kept scraped data" || true
fi
```

The intent: on a pull conflict, keep "our" (the fresh scrape's) version of the data directory,
resolve, commit. **What actually happened: the resolution didn't work, and files with live
conflict markers got `git add`-ed and committed as-is.** Exactly why `git checkout --ours` didn't
cleanly resolve here isn't root-caused yet — plausible theories, not yet verified:

- `git checkout --ours <path>` only correctly resolves paths that are in an *unmerged* index
  state from an add/add or modify/modify conflict. If git's merge machinery instead attempted a
  line-level 3-way text merge on some files (rather than treating them as whole-file conflicts)
  and left markers in the *working tree* while the *index* wasn'"t in the state `--ours` expects,
  the checkout could silently no-op on those files, leaving the marker-laden content to be
  `git add`ed as-is.
- Given every scrape run uses fresh random UUIDs per bill filename, two concurrent commits
  touching `_data/ga/` should mostly be pure adds (different filenames) — real content-level
  conflicts on the *same* filename should be rare. Worth checking what specifically triggered a
  real conflict here (concurrent autosave + final commit both touching the same file bundle?
  Two auto-saves overlapping? A schedule + manual dispatch race?).

## Current status

- **GA is fixed as a side effect**, not by design — tonight's re-dispatch (after PR #98 merged)
  produced a fresh clean commit with 176 real bills, zero conflict markers. Verified directly via
  a fresh clone at the latest commit.
- **The underlying bug that caused the corruption is still live** in `action.yml` (and possibly
  `scrape.sh`). Nothing has been fixed here yet — GA just happened to get lucky because its next
  successful run wholesale-replaced the corrupted files.
- **Completely unknown whether any other state hit this same corruption.** GA was found by
  accident; there's no reason to believe it's the only one. This needs a real audit, not a guess.

## What to do next session (in priority order)

1. **Audit every state's committed `_data/{state}/` for conflict markers**, not just GA. A quick
   check: `git grep -l "^<<<<<<< " -- '_data/*/bill_*.json'` (or per-repo, since each state is its
   own repo under `govbot-openstates-scrapers`) across all ~56 state repos. This is cheap and
   should run first, before anything else — if this is widespread, it's a much bigger deal than
   one state's data being briefly bad.
2. **Root-cause why `git checkout --ours` didn't work** here specifically. Reproduce locally: set
   up two conflicting commits touching the same `_data/{state}/` path and see what actually
   happens with this exact sequence, in a real git repo. Determine whether this can recur under
   normal operation (auto-save + final commit racing, or two auto-saves racing) or whether GA's
   case was some other one-off.
3. **Fix the conflict-resolution logic** so it can never commit marker-laden content again —
   possibilities: validate each file is real parseable JSON before `git add`+commit and hard-fail
   loudly instead of silently committing garbage if any file still has markers; or replace the
   whole conflict-resolution approach with something that can't partially fail per-file (e.g.
   `git checkout --ours` per individual conflicted file from `git diff --name-only
   --diff-filter=U`, verifying the unmerged list is empty afterward before committing).
3. **Consider a repo-wide validation guard**: before any commit lands, a cheap check that every
   `bill_*.json` file staged is valid JSON (not just the identifier-count logic, which currently
   swallows parse failures with `|| true` and moves on — appropriate for *counting*, but this
   incident shows real corruption can hide behind that same tolerance if nothing else validates).

## Related, already fixed tonight (context, not action items)

- PR #97 (`fix/commit-summary-identifier-aware`) — identifier-aware commit-summary label + 503/429
  classifier fix. Unrelated to this bug but same investigation trail.
- PR #98 (`fix/identifier-count-malformed-json`) — fixed a *different* bug (a single malformed
  file crashing the whole identifier count via batched `xargs`). Necessary but not sufficient —
  it stopped the crash, but doesn't address *why* files are malformed in the first place, which
  is this doc's finding.
