#!/bin/bash
set -euo pipefail

# Script to update the "Display extraction summary" step in all state repos
# This updates it to read the .extraction_summary.txt file created by the extract action

ORG="windy-civi-pipelines"
WORKFLOW_FILE=".github/workflows/extract-text.yml"
TEMP_DIR=$(mktemp -d)

echo "🔧 Updating extraction summary step in all state repos"
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

  # Check if the old step exists
  if ! grep -q "Display extraction summary" "$WORKFLOW_FILE"; then
    echo "  ⏭️  No 'Display extraction summary' step found, skipping"
    ((SKIP_COUNT++))
    cd - > /dev/null
    continue
  fi

  # Check if already updated
  if grep -q ".extraction_summary.txt" "$WORKFLOW_FILE"; then
    echo "  ✅ Already updated, skipping"
    ((SKIP_COUNT++))
    cd - > /dev/null
    continue
  fi

  echo "  🔍 Updating summary step..."

  # Create a Python script to do the replacement (more reliable than awk/sed for YAML)
  cat > /tmp/update_workflow.py << 'PYTHON_SCRIPT'
import sys
import re

with open(sys.argv[1], 'r') as f:
    content = f.read()

# Find and replace the Display extraction summary step
old_step = r'''      - name: Display extraction summary
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

# Replace the step
content = re.sub(old_step, new_step, content, flags=re.MULTILINE)

with open(sys.argv[1], 'w') as f:
    f.write(content)
PYTHON_SCRIPT

  # Run the Python script
  if python3 /tmp/update_workflow.py "$WORKFLOW_FILE"; then
    # Check if there are changes to commit
    if git diff --quiet "$WORKFLOW_FILE"; then
      echo "  ⚠️  No changes detected after processing"
      ((SKIP_COUNT++))
      cd - > /dev/null
      continue
    fi

    # Commit and push
    git add "$WORKFLOW_FILE"
    git commit -m "Update extraction summary step to read from file

The extract action now saves summary stats to .extraction_summary.txt,
making them easy to view in the 'Display extraction summary' step
without scrolling through thousands of lines in the main extraction logs." --quiet

    if git push origin main --quiet 2>&1; then
      echo "  ✅ Updated successfully"
      ((SUCCESS_COUNT++))
    else
      echo "  ❌ Failed to push"
      ((ERROR_COUNT++))
    fi
  else
    echo "  ❌ Failed to update file"
    ((ERROR_COUNT++))
  fi

  cd - > /dev/null
done

# Cleanup
rm -f /tmp/update_workflow.py

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

