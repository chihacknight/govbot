#!/usr/bin/env bash
# Reference implementation for the staleness audit described in
# actions/pipeline-manager/docs/staleness-audit-spec.md. Run once manually on
# 2026-07-14 and found 16 govbot-data states + usa frozen since 2025-12-14 —
# see that spec doc for what to do with the output and how to build this into
# a real recurring check (cadence, anomaly flagging, cross-referencing against
# the session calendar). This script alone just answers "when did each state
# last get real bill data" — it does not diagnose *why* a state is stale.
#
# Usage: ./audit-data-staleness.sh [output-file]
set -uo pipefail

OUT="${1:-/tmp/state_audit.tsv}"
> "$OUT"

repos=$(gh repo list govbot-data --limit 100 --json name --jq '.[].name' | grep -v -- '-format$' | sort)

for repo in $repos; do
  state=$(echo "$repo" | sed 's/-legislation//')
  path="country:us/state:${state}/sessions"

  # The most recent commit that actually touched a file under sessions/ —
  # NOT the plain "last commit," which is misleading: govbot-data repos get a
  # commit every day regardless of whether real data changed, because
  # .windycivi/last-processed-sha gets bumped as a tracking file on every run.
  last_bill_commit=$(gh api "repos/govbot-data/${repo}/commits?path=${path}&per_page=1" \
    --jq '.[0].commit.author.date // "NONE"' 2>&1)

  echo -e "${state}\t${last_bill_commit}" >> "$OUT"
  echo "done: $state -> $last_bill_commit" >&2
done

echo "Wrote results to $OUT" >&2
