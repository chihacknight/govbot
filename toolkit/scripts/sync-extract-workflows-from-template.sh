#!/bin/bash
set -euo pipefail

# Script to sync all state repos' extract-text.yml workflows with the canonical template
# This ensures all repos have the latest workflow structure with proper summary display and auto-restart

# Disable git pager to prevent interactive prompts
export GIT_PAGER=cat

# Get the script directory and toolkit root at the start (before changing directories)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ORG="windy-civi-pipelines"
WORKFLOW_FILE=".github/workflows/extract-text.yml"
TEMPLATE_FILE="docs/for-caller-repos/example-caller-text-extraction.yml"
TEMP_DIR=$(mktemp -d)

echo "🔧 Syncing extract-text.yml workflows from template"
echo "📁 Working directory: $TEMP_DIR"
echo ""

# Check if template exists
if [ ! -f "$TEMPLATE_FILE" ]; then
  echo "❌ Template file not found: $TEMPLATE_FILE"
  exit 1
fi

# Get list of all repos in the organization
REPOS=$(gh repo list "$ORG" --limit 100 --json name --jq '.[].name' | grep -E '^[a-z]{2}-data-pipeline$' || true)

if [ -z "$REPOS" ]; then
  echo "❌ No state repos found"
  exit 1
fi

REPO_COUNT=$(echo "$REPOS" | wc -l | tr -d ' ')
echo "📊 Found $REPO_COUNT state repos to update"
echo ""
echo "This will replace each repo's extract-text.yml with the template,"
echo "preserving only the state code in the 'state:' field."
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

  # Extract state code from repo name (e.g., "tx-data-pipeline" -> "tx")
  STATE_CODE="${repo%%-*}"

  REPO_DIR="$TEMP_DIR/$repo"

  # Clone the repo
  if ! gh repo clone "$ORG/$repo" "$REPO_DIR" -- --quiet 2>/dev/null; then
    echo "  ⚠️  Failed to clone, skipping"
    ((ERROR_COUNT++))
    continue
  fi

  cd "$REPO_DIR"

  # Create .github/workflows directory if it doesn't exist
  mkdir -p "$(dirname "$WORKFLOW_FILE")"

  # Copy template and update state code
  echo "  📝 Copying template and updating state code to: $STATE_CODE"

  # Copy template (SCRIPT_DIR was set at the top of the script)
  cp "$SCRIPT_DIR/$TEMPLATE_FILE" "$WORKFLOW_FILE"

  # Replace the state code (default is "wy" in template)
  sed -i.bak "s/state: wy/state: $STATE_CODE/g" "$WORKFLOW_FILE"

  # Update the comment to match
  if [ "$STATE_CODE" = "usa" ]; then
    STATE_NAME="Federal"
  else
    STATE_NAME=$(echo "$STATE_CODE" | tr '[:lower:]' '[:upper:]')
  fi
  sed -i.bak "s/# ⚠️ UPDATE THIS: Change to your state code (e.g., wy, usa, il, tx)/# $STATE_NAME/g" "$WORKFLOW_FILE"

  # Remove backup file
  rm -f "${WORKFLOW_FILE}.bak"

  # Check if there are changes to commit
  if git diff --quiet "$WORKFLOW_FILE" 2>/dev/null; then
    echo "  ✅ Already up to date, skipping"
    ((SKIP_COUNT++))
    cd - > /dev/null
    continue
  fi

  # Show summary of changes
  if git diff --stat "$WORKFLOW_FILE" 2>/dev/null | grep -q .; then
    echo "  📊 Changes detected:"
    git diff --stat "$WORKFLOW_FILE" 2>/dev/null || true
  fi

  # Commit and push
  git add "$WORKFLOW_FILE"
  git commit -m "Sync extract-text workflow with latest template

Updates:
- Display extraction summary from .extraction_summary.txt file
- Use @main branch for toolkit actions
- Include auto-restart job with PAT support
- Proper timeout and error handling configuration

State: $STATE_CODE" --quiet

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

