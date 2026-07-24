#!/bin/bash
# One-time batch operation: clear stale extracted files (produced by the
# now-fixed extraction code -- see PR #82) across the PDF-only states so the
# next extract-text run rebuilds them clean, then dispatch extract-text.yml
# so it actually happens now instead of waiting for the next cron/dispatch.
#
# Usage: ./clear_and_reextract.sh state1 state2 ...
set -uo pipefail

WORKDIR=$(mktemp -d)
echo "Working in $WORKDIR"

MSGFILE="$WORKDIR/commit-message.txt"
cat > "$MSGFILE" << 'MSGEOF'
chore: clear stale extracted files for re-extraction with fixed pipeline

Old extracted files were produced by broken extraction code: the "PDF"
file was actually mislabeled already-extracted text (not the real PDF),
and the text file duplicated its content. Clearing so the next
extract-text run rebuilds everything with the fix (PR #82).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
MSGEOF

for state in "$@"; do
  echo "=== $state ==="
  repo_dir="$WORKDIR/${state}-legislation"

  if ! git clone --depth 1 "https://github.com/govbot-data/${state}-legislation.git" "$repo_dir" 2>&1 | tail -3; then
    echo "FAILED to clone $state, skipping"
    continue
  fi

  cd "$repo_dir" || continue

  file_dirs=$(find . -type d -name "files" -path "*/sessions/*/bills/*" 2>/dev/null)
  count=$(echo "$file_dirs" | grep -c . || true)
  if [ "$count" -eq 0 ]; then
    echo "  no files/ directories found, skipping"
    cd - >/dev/null
    continue
  fi
  echo "  clearing $count files/ directories"

  find . -type d -name "files" -path "*/sessions/*/bills/*" -exec rm -rf {} + 2>/dev/null

  git add -A
  if git diff --staged --quiet; then
    echo "  nothing to commit, skipping push"
  else
    git commit -q -F "$MSGFILE"
    if git push origin main 2>&1 | tail -5; then
      echo "  pushed clean"
    else
      echo "  FAILED to push $state"
      cd - >/dev/null
      continue
    fi
  fi

  cd - >/dev/null

  if gh workflow run "extract-text.yml" --repo "govbot-data/${state}-legislation" 2>&1; then
    echo "  dispatched extract-text.yml"
  else
    echo "  FAILED to dispatch extract-text.yml for $state"
  fi

  sleep 2
done

echo "=== done ==="
rm -rf "$WORKDIR"
