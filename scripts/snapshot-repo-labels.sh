#!/bin/bash
# Appends a dated snapshot of every govbot-openstates-scrapers repo's GitHub
# topics (the "labels" shown in each repo's About section) to a log file, so
# label history is trackable over time instead of only ever showing the
# current state.
#
# Usage: ./scripts/snapshot-repo-labels.sh [output_file]
#   Defaults to project_docs/label-history.tsv (untracked -- see project_docs
#   conventions). Safe to run repeatedly; each run just appends new rows.

set -euo pipefail

OUT="${1:-project_docs/label-history.tsv}"
DATE="$(date -u +%Y-%m-%d)"

STATES="ak al ar az ca co ct dc de fl ga gu hi ia id il in ks ky la ma md me mi mn mo mp ms mt nc nd ne nh nj nm nv ny oh ok or pa pr ri sc sd tn tx usa ut va vi vt wa wi wv wy"

mkdir -p "$(dirname "$OUT")"

if [ ! -f "$OUT" ]; then
  printf 'date\tstate\ttopics\n' > "$OUT"
fi

for state in $STATES; do
  topics=$(gh api "repos/govbot-openstates-scrapers/${state}-legislation/topics" --jq '.names | join(",")' 2>/dev/null || echo "ERROR_FETCHING")
  printf '%s\t%s\t%s\n' "$DATE" "$state" "$topics" >> "$OUT"
done

echo "Snapshot for $DATE appended to $OUT"
