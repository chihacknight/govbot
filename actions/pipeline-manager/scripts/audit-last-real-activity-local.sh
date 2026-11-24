#!/usr/bin/env bash
# Local-clone variant of audit-last-real-activity.sh. The GitHub tree API
# version truncates on large repos (GitHub caps recursive tree listings --
# confirmed on a real run 2026-09-30, roughly half of the 56 states came back
# truncated=true), so for a repo too big for one API response, this reads the
# same signal off a full local clone instead, where there's no such cap.
#
# Same underlying logic as the API version: actions/format only logs an entry
# (a line in a bill's action_logs.jsonl / vote_event_logs.jsonl) when it's
# genuinely new, and each entry carries the government's own recorded date.
# The max of those dates across a state's repo is
# "the most recent real legislative activity we have on record" -- see that
# script's own header comment and tamara-notes/processes/dream-list.md for
# why the existing .windycivi timestamp files can't be trusted for this.
#
# Prerequisite: a local clone via the govbot CLI, e.g.
#   govbot clone all --govbot-dir /path/to/govbot_data
# (depth-50 shallow by default -- fine here, since this reads working-tree
# files, not git history.)
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

  # Newest government-recorded date across every log entry: action.occurred_at
  # in bills/<id>/action_logs.jsonl and vote_event.start_date in
  # vote_event_logs.jsonl, as YYYYMMDDTHHMMSSZ in the source's own clock time
  # (not converted to UTC -- the old filenames weren't either, so both layouts
  # agree). A repo not yet converted is read from the old filenames, which start
  # with that same timestamp, skipping the sessions/<s>/logs/ symlinks.
  last_ts=$(python3 - "$repo_dir" <<'PY'
import json, re, sys
from datetime import datetime
from pathlib import Path
root = Path(sys.argv[1])
best = ""
files = list(root.glob("country:*/state:*/sessions/*/bills/*/action_logs.jsonl")) + \
        list(root.glob("country:*/state:*/sessions/*/bills/*/vote_event_logs.jsonl"))
for f in files:
    for raw in f.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        line = json.loads(raw)
        date = (line.get("action") or {}).get("occurred_at") or (line.get("vote_event") or {}).get("start_date")
        try:
            best = max(best, datetime.fromisoformat(date).strftime("%Y%m%dT%H%M%SZ"))
        except Exception:
            pass
if not files:
    for f in root.glob("country:*/state:*/sessions/*/bills/*/logs/*.json"):
        m = re.match(r"(\d{8}T\d{6}Z)", f.name)
        if m and not f.is_symlink():
            best = max(best, m.group(1))
print(best)
PY
)

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
