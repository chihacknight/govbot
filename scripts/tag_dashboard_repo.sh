#!/usr/bin/env bash
#
# Incrementally tag one cloned legislation repo for the Pages dashboard.
#
# Steps, per repo:
#   1. Copy the canonical taxonomy in as the repo's govbot.yml (govbot tag forces
#      its output to the directory containing govbot.yml).
#   2. Restore tag files produced on previous runs (so unchanged bills keep tags).
#   3. Stream `govbot logs` -> filter_new_bills.py (only new/changed bills) ->
#      `govbot tag --overwrite` (embedding mode). Only changed bills get embedded.
#   4. Save the produced tag files + ledger back to the cache for the next run.
#
# Designed to be run in parallel across repos (e.g. xargs -P4); all state is
# per-repo so workers never contend. Failures are downgraded to warnings so the
# dashboard build proceeds to its keyword fallback for this repo.
#
# Inputs: repo dir as $1; the rest via environment so the call site stays simple:
#   GOVBOT_DATA       dir containing repos/ (passed to `govbot logs --govbot-dir`)
#   MODEL_DIR         shared ONNX model cache (passed to `govbot tag --govbot-dir`)
#   CACHE_DIR         root for per-repo incremental state (ledger + tag snapshot)
#   DASHBOARD_CONFIG  path to scripts/govbot-dashboard.yml
#   FILTER_SCRIPT     path to scripts/filter_new_bills.py
#
set -uo pipefail

repo_dir=${1:?usage: tag_dashboard_repo.sh <repo_dir>}
: "${GOVBOT_DATA:?}" "${MODEL_DIR:?}" "${CACHE_DIR:?}" "${DASHBOARD_CONFIG:?}" "${FILTER_SCRIPT:?}"

[ -d "$repo_dir" ] || exit 0
name=$(basename "$repo_dir")
locale=${name%-legislation}
repo_cache="$CACHE_DIR/$name"
mkdir -p "$repo_cache"

warn() { echo "::warning::$*"; }

# 1. govbot tag reads tag definitions from ./govbot.yml and writes tags/ beside it.
cp "$DASHBOARD_CONFIG" "$repo_dir/govbot.yml"

# 2. Restore previously-produced tag files into the fresh clone.
if [ -f "$repo_cache/tags.tgz" ]; then
  tar -xzf "$repo_cache/tags.tgz" -C "$repo_dir" 2>/dev/null \
    || warn "could not restore cached tags for $name (will re-tag)"
fi

# 3. Tag only new/changed bills. --limit none: all bills; --filter none: don't
# drop entries; --join bill: stable content (no self-injected tags); --overwrite:
# actually re-tag a changed bill (the tagger otherwise skips by id presence).
govbot logs --repos "$locale" --govbot-dir "$GOVBOT_DATA" \
    --join bill --limit none --filter none \
  | python3 "$FILTER_SCRIPT" --ledger "$repo_cache/ledger.json" \
  | ( cd "$repo_dir" && govbot tag --govbot-dir "$MODEL_DIR" --overwrite )
status=${PIPESTATUS[2]}

# 4. Persist produced tag files for next run's cache.
filelist="$repo_cache/filelist.txt"
( cd "$repo_dir" && find . -path '*/tags/*.tag.json' -print > "$filelist" ) 2>/dev/null || true
if [ -s "$filelist" ]; then
  tar -czf "$repo_cache/tags.tgz" -C "$repo_dir" -T "$filelist" 2>/dev/null \
    || warn "could not save tag cache for $name"
fi
rm -f "$filelist"

if [ "${status:-1}" -ne 0 ]; then
  warn "govbot tag pipeline failed for $name (keyword fallback applies)"
fi
exit 0
