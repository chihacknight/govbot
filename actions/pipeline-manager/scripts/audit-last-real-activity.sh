#!/usr/bin/env bash
# Companion to audit-data-staleness.sh, fixing the trap that script doesn't
# handle: a commit touching country:us/state:{code}/sessions can be an
# extraction-only run (actions/extract writing into a bill's files/ folder),
# which looks like "fresh data" but isn't -- extraction never means anything
# new happened with the bill, just that we re-processed a PDF we already knew
# about. See tamara-notes/processes/dream-list.md item 2 for why the obvious
# alternative (.windycivi/latest_timestamp_seen.txt) doesn't work either.
#
# Real signal: actions/format only writes a new file under a bill's logs/
# when find_new_actions() (processing_tracker.py) finds a genuinely new
# action or vote event -- and that file's name is prefixed with the ACTION'S
# OWN government-recorded date (format_timestamp(), %Y%m%dT%H%M%SZ), not a
# processing timestamp. So the max timestamp across every logs/*.json
# filename in a state's repo is a direct, content-accurate answer to "what's
# the most recent real legislative activity we have on record" -- no git
# history needed, no per-bill API calls: one recursive tree listing per repo.
#
# Caveat: GitHub's tree API truncates very large repos (checked via the
# response's "truncated" field) -- flagged per-row below, not silently
# trusted. Also: this answers "how current is our data," not "is the
# pipeline currently running" -- a state correctly out of session will
# legitimately show an old date here, that's not itself a bug. Cross-reference
# against tamara-notes/session-dates/session-calendar-2026.md before reading
# an old date as a problem.
#
# Usage: ./audit-last-real-activity.sh [output-file]
set -uo pipefail

OUT="${1:-/tmp/last_real_activity.tsv}"
> "$OUT"

repos=$(gh repo list govbot-data --limit 100 --json name --jq '.[].name' | grep -v -- '-format$' | sort)

today_epoch=$(date -u +%s)

for repo in $repos; do
  state=$(echo "$repo" | sed 's/-legislation//')

  tree_json=$(gh api "repos/govbot-data/${repo}/git/trees/HEAD?recursive=1" 2>&1)
  if [ $? -ne 0 ]; then
    echo -e "${state}\tERROR\t\tfalse" >> "$OUT"
    echo "error: $state -> failed to fetch tree" >&2
    continue
  fi

  truncated=$(echo "$tree_json" | jq -r '.truncated // false')

  # Every logs/*.json filename starts with its action's own government-
  # recorded date as YYYYMMDDTHHMMSSZ -- lexicographic sort == chronological
  # sort for this format, so plain `sort | tail -1` finds the max without
  # needing to parse dates.
  last_ts=$(echo "$tree_json" \
    | jq -r '.tree[]? | select(.path | test("/logs/.*\\.json$")) | .path' \
    | sed -E 's#.*/([0-9]{8}T[0-9]{6}Z).*#\1#' \
    | grep -E '^[0-9]{8}T[0-9]{6}Z$' \
    | sort \
    | tail -1)

  if [ -z "$last_ts" ]; then
    echo -e "${state}\tNONE\t\t${truncated}" >> "$OUT"
    echo "done: $state -> no logs found" >&2
    continue
  fi

  # Convert YYYYMMDDTHHMMSSZ -> epoch -> days ago (GNU/BSD date differ; try both)
  iso="${last_ts:0:4}-${last_ts:4:2}-${last_ts:6:2}T${last_ts:9:2}:${last_ts:11:2}:${last_ts:13:2}Z"
  last_epoch=$(date -u -d "$iso" +%s 2>/dev/null || date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$iso" +%s 2>/dev/null)
  days_ago="?"
  if [ -n "$last_epoch" ]; then
    days_ago=$(( (today_epoch - last_epoch) / 86400 ))
  fi

  echo -e "${state}\t${last_ts}\t${days_ago}\t${truncated}" >> "$OUT"
  echo "done: $state -> ${last_ts} (${days_ago}d ago)$([ "$truncated" = "true" ] && echo " [TRUNCATED]")" >&2
done

echo "" >&2
echo "Wrote results to $OUT (columns: state, last_real_activity, days_ago, tree_truncated)" >&2
