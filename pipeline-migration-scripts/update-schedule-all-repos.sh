#!/bin/bash
# Update GitHub Actions schedules for all state pipeline repositories
# Usage: ./update-schedule-all-repos.sh

set -e

ORG="windy-civi-pipelines"
TEMP_DIR=$(mktemp -d)

# New schedules
SCRAPE_SCHEDULE='    - cron: "0 2 * * *"  # Daily at 2 AM UTC (~9 PM ET, ~6 PM PT)'
EXTRACT_SCHEDULE='    - cron: "0 8 * * *"  # Daily at 8 AM UTC (~3 AM ET, ~12 AM PT)'

# Cleanup function
cleanup() {
    if [ -d "$TEMP_DIR" ]; then
        echo "🧹 Cleaning up temp directory..."
        rm -rf "$TEMP_DIR"
    fi
}
trap cleanup EXIT

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) is not installed"
    echo "Install it: brew install gh"
    exit 1
fi

# Get all state repos
echo "📋 Fetching all state repositories from $ORG..."
REPOS=$(gh repo list "$ORG" --json name --jq '.[].name' | grep -E '^[a-z]{2,4}-data-pipeline$')

if [ -z "$REPOS" ]; then
    echo "❌ No state repositories found"
    exit 1
fi

REPO_COUNT=$(echo "$REPOS" | wc -l | tr -d ' ')
echo "Found $REPO_COUNT repositories"
echo ""
echo "New schedules:"
echo "  Scrape & Format: 02:00 UTC (~9 PM ET, ~6 PM PT)"
echo "  Text Extraction: 08:00 UTC (~3 AM ET, ~12 AM PT)"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi
echo ""

SUCCESS_COUNT=0
SKIP_COUNT=0
FAIL_COUNT=0

for repo_name in $REPOS; do
    full_repo="$ORG/$repo_name"
    state_code=$(echo "$repo_name" | sed 's/-data-pipeline//')

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📍 $state_code"
    echo "   Repository: $full_repo"

    # Clone temporarily
    REPO_DIR="$TEMP_DIR/$repo_name"
    echo "   📥 Cloning..."

    if ! gh repo clone "$full_repo" "$REPO_DIR" -- --depth 1 --quiet 2>/dev/null; then
        echo "   ❌ Failed to clone repository"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        continue
    fi

    cd "$REPO_DIR"

    CHANGES_MADE=false

    # Update scrape-and-format workflow schedule
    SCRAPE_WORKFLOW=".github/workflows/scrape-and-format-data.yml"
    if [ -f "$SCRAPE_WORKFLOW" ]; then
        echo "   ✏️  Updating scrape-and-format schedule..."
        # Match any existing cron schedule and replace it
        sed -i.bak '/schedule:/,/- cron:/ {
            /- cron:/ c\
'"$SCRAPE_SCHEDULE"'
        }' "$SCRAPE_WORKFLOW"
        rm -f "$SCRAPE_WORKFLOW.bak"
        CHANGES_MADE=true
    fi

    # Update extract-text workflow schedule
    EXTRACT_WORKFLOW=".github/workflows/extract-text.yml"
    if [ -f "$EXTRACT_WORKFLOW" ]; then
        echo "   ✏️  Updating extract-text schedule..."
        # Match any existing cron schedule and replace it
        sed -i.bak '/schedule:/,/- cron:/ {
            /- cron:/ c\
'"$EXTRACT_SCHEDULE"'
        }' "$EXTRACT_WORKFLOW"
        rm -f "$EXTRACT_WORKFLOW.bak"
        CHANGES_MADE=true
    fi

    # Commit and push if there are changes
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
    git add .

    if git diff --staged --quiet; then
        echo "   ℹ️  No changes needed"
        SKIP_COUNT=$((SKIP_COUNT + 1))
    else
        echo "   💾 Committing updates..."
        git commit -m "chore: optimize workflow schedules for better performance

- Scrape & Format: 02:00 UTC (~9 PM ET, ~6 PM PT)
  Catches full legislative day across all US time zones

- Text Extraction: 08:00 UTC (~3 AM ET, ~12 AM PT)
  Off-peak hours for better GitHub Actions performance
  6-hour buffer after scraping completes"

        echo "   📤 Pushing changes..."
        if git push origin main 2>/dev/null; then
            echo "   ✅ Updated successfully"
            SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        else
            echo "   ❌ Failed to push"
            FAIL_COUNT=$((FAIL_COUNT + 1))
        fi
    fi

    # Clean up this repo's temp clone
    cd "$TEMP_DIR"
    rm -rf "$REPO_DIR"

    # Be nice to GitHub API
    sleep 1
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Summary:"
echo "   ✅ Updated: $SUCCESS_COUNT"
echo "   ℹ️  No changes needed: $SKIP_COUNT"
echo "   ❌ Failed: $FAIL_COUNT"
echo ""
echo "🎉 Done! All repos have been updated with optimized schedules."

