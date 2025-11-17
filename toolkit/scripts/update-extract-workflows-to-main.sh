#!/bin/bash
set -euo pipefail

# Script to update all state repos' extract-text.yml workflows to point to @main
# This ensures all repos are using the stable main branch instead of fix/debug branches

ORG="windy-civi-pipelines"
WORKFLOW_FILE=".github/workflows/extract-text.yml"
TEMP_DIR=$(mktemp -d)

echo "🔧 Updating extract-text.yml workflows to use @main branch"
echo "📁 Working directory: $TEMP_DIR"
echo ""

# Get list of all repos in the organization
REPOS=$(gh repo list "$ORG" --limit 100 --json name --jq '.[].name' | grep -E '^[a-z]{2}-data-pipeline$' || true)

if [ -z "$REPOS" ]; then
  echo "❌ No state repos found"
  exit 1
fi

REPO_COUNT=$(echo "$REPOS" | wc -l | tr -d ' ')
echo "📊 Found $REPO_COUNT state repos to update"
echo ""

read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "❌ Aborted"
  exit 1
fi

SUCCESS_COUNT=0
SKIP_COUNT=0
ERROR_COUNT=0

for repo in $REPOS; do
  echo "────────────────────────────────────────"
  echo "📦 Processing: $repo"

  REPO_DIR="$TEMP_DIR/$repo"

  # Clone the repo
  if ! gh repo clone "$ORG/$repo" "$REPO_DIR" -- --quiet 2>/dev/null; then
    echo "  ⚠️  Failed to clone, skipping"
    ((ERROR_COUNT++))
    continue
  fi

  cd "$REPO_DIR"

  # Check if workflow file exists
  if [ ! -f "$WORKFLOW_FILE" ]; then
    echo "  ⏭️  No extract-text.yml found, skipping"
    ((SKIP_COUNT++))
    cd - > /dev/null
    continue
  fi

  # Check if already pointing to @main
  if grep -q "windy-civi/toolkit/actions/extract@main" "$WORKFLOW_FILE" && \
     ! grep -q "windy-civi/toolkit/actions/extract@fix/" "$WORKFLOW_FILE" && \
     ! grep -q "windy-civi/toolkit/actions/extract@refactor/" "$WORKFLOW_FILE"; then
    echo "  ✅ Already using @main, skipping"
    ((SKIP_COUNT++))
    cd - > /dev/null
    continue
  fi

  echo "  🔍 Updating branch reference to @main and Display summary step..."

  # Replace any branch reference with @main
  sed -i.bak 's|windy-civi/toolkit/actions/extract@[^[:space:]]*|windy-civi/toolkit/actions/extract@main|g' "$WORKFLOW_FILE"

  # Update the Display extraction summary step if it exists and needs updating
  if grep -q "Display extraction summary" "$WORKFLOW_FILE" && ! grep -q ".extraction_summary.txt" "$WORKFLOW_FILE"; then
    echo "  📝 Updating Display extraction summary step..."

    # Use Python to do the replacement (more reliable for multi-line YAML)
    python3 << 'PYTHON_EOF'
import re
import sys

with open("$WORKFLOW_FILE", 'r') as f:
    content = f.read()

# Pattern to match the old Display extraction summary step
old_pattern = r'''      - name: Display extraction summary
        if: always\(\)
        shell: bash
        run: \|
          echo "📊 Text Extraction Summary"
          echo "================================"
          echo "✅ Check country:us/state:\*/sessions/\*/bills/\*/files/ for extracted text files"
          echo "📄 Look for \*_extracted\.txt files in the files/ directories"
          echo ""
          echo "ℹ️  Features:"
          echo "  - Incremental processing \(skips already-processed bills\)"
          echo "  - Auto-saves progress every 30 minutes"
          echo "  - Can be safely restarted if timeout occurs"'''

new_step = '''      - name: Display extraction summary
        if: always()
        shell: bash
        run: |
          if [ -f ".extraction_summary.txt" ]; then
            cat .extraction_summary.txt
          else
            echo "⚠️  Summary file not found"
          fi'''

# Try to replace
content = re.sub(old_pattern, new_step, content, flags=re.MULTILINE)

with open("$WORKFLOW_FILE", 'w') as f:
    f.write(content)
PYTHON_EOF
  fi

  # Remove backup file
  rm -f "${WORKFLOW_FILE}.bak"

  # Check if there are changes to commit
  if git diff --quiet "$WORKFLOW_FILE"; then
    echo "  ⚠️  No changes detected after processing"
    ((SKIP_COUNT++))
    cd - > /dev/null
    continue
  fi

  # Show what changed
  echo "  📝 Changes:"
  git diff "$WORKFLOW_FILE" | grep -E "^\+|^-" | grep "uses:" || true

  # Commit and push
  git add "$WORKFLOW_FILE"
  git commit -m "Update extract workflow to use @main branch

Point extract action to stable @main branch instead of fix/debug branches." --quiet

  if git push origin main --quiet 2>&1; then
    echo "  ✅ Updated successfully"
    ((SUCCESS_COUNT++))
  else
    echo "  ❌ Failed to push"
    ((ERROR_COUNT++))
  fi

  cd - > /dev/null
done

echo ""
echo "════════════════════════════════════════"
echo "📊 Summary:"
echo "  ✅ Successfully updated: $SUCCESS_COUNT"
echo "  ⏭️  Skipped (no change needed): $SKIP_COUNT"
echo "  ❌ Errors: $ERROR_COUNT"
echo ""
echo "🧹 Cleaning up temp directory..."
rm -rf "$TEMP_DIR"
echo "✅ Done!"

