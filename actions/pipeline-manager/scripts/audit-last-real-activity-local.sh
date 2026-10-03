#!/usr/bin/env bash
# Local-clone variant of audit-last-real-activity.sh. The GitHub tree API
# version truncates on large repos (GitHub caps recursive tree listings --
# confirmed on a real run 2026-09-30, roughly half of the 56 states came back
# truncated=true), so for a repo too big for one API response, this reads the
# same signal off a full local clone instead, where there's no such cap.
#
# Same underlying logic as the API version: actions/format only writes a new
# file under a bill's logs/ when find_new_actions() finds something genuinely
# new, and the filename is prefixed with the action's own government-recorded
# date (%Y%m%dT%H%M%SZ). The max of those filenames across a state's repo is
# "the most recent real legislative activity we have on record" -- see that
# script's own header comment and tamara-notes/processes/dream-list.md for
# why the existing .windycivi timestamp files can't be trusted for this.
#
# Prerequisite: a local clone via the govbot CLI, e.g.
#   govbot clone all --govbot-dir /path/to/govbot_data
# (depth-50 shallow by default -- fine here, since this reads working-tree
# file names, not git history.)
#
# Usage: ./audit-last-real-activity-local.sh <govbot-dir>/repos [output-file]
#   <govbot-dir>/repos should contain one folder per state, e.g.
#   govbot_data/repos/wy-legislation/, matching `govbot clone`'s layout.
set -uo pipefail

REPOS_DIR="${1:?Usage: $0 <path-to-repos-dir> [output-file]}"
OUT="${2:-/tmp/last_real_activity_local.tsv}"
> "$OUT"

if [ ! -d "$REPOS_DIR" ]; then
  echo "Error: $REPOS_DIR does not exist" >&2
  exit 1
fi

today_epoch=$(date -u +%s)

for repo_dir in "$REPOS_DIR"/*-legislation/; do
  [ -d "$repo_dir" ] || continue
  repo=$(basename "$repo_dir")
  state="${repo%-legislation}"

  # Every logs/*.json filename starts with its action's own government-
  # recorded date as YYYYMMDDTHHMMSSZ -- lexicographic sort == chronological
  # sort for this format.
  # -exec basename (not GNU find's -printf '%f') -- portable across BSD
  # find (macOS) and GNU find (Linux CI runners).
  last_ts=$(find "$repo_dir" -path '*/logs/*.json' -type f -exec basename {} \; 2>/dev/null \
    | sed -E 's/^([0-9]{8}T[0-9]{6}Z).*/\1/' \
    | grep -E '^[0-9]{8}T[0-9]{6}Z$' \
    | sort \
    | tail -1)

  if [ -z "$last_ts" ]; then
    echo -e "${state}\tNONE\t" >> "$OUT"
    echo "done: $state -> no logs found" >&2
    continue
  fi

  iso="${last_ts:0:4}-${last_ts:4:2}-${last_ts:6:2}T${last_ts:9:2}:${last_ts:11:2}:${last_ts:13:2}Z"
  last_epoch=$(date -u -d "$iso" +%s 2>/dev/null || date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$iso" +%s 2>/dev/null)
  days_ago="?"
  if [ -n "$last_epoch" ]; then
    days_ago=$(( (today_epoch - last_epoch) / 86400 ))
  fi

  echo -e "${state}\t${last_ts}\t${days_ago}" >> "$OUT"
  echo "done: $state -> ${last_ts} (${days_ago}d ago)" >&2
done

echo "" >&2
echo "Wrote results to $OUT (columns: state, last_real_activity, days_ago)" >&2
echo "No truncation risk here -- this reads the full local clone, not a capped API response." >&2
