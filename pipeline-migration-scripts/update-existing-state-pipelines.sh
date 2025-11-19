#!/bin/bash
# Update existing state pipeline repositories with correct state codes
# Usage: ./update-existing-state-pipelines.sh

set -e

ORG="windy-civi-pipelines"
TEMP_DIR=$(mktemp -d)

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

# List of states to update
STATES=(
    "ks:Kansas"
    "ky:Kentucky"
    "la:Louisiana"
    "me:Maine"
    "md:Maryland"
    "ma:Massachusetts"
    "mi:Michigan"
    "mn:Minnesota"
    "ms:Mississippi"
    "mo:Missouri"
    "mt:Montana"
    "ne:Nebraska"
    "nv:Nevada"
    "nh:New Hampshire"
    "nj:New Jersey"
    "nm:New Mexico"
    "ny:New York"
    "nc:North Carolina"
    "nd:North Dakota"
    "mp:Northern Mariana Islands"
    "oh:Ohio"
    "ok:Oklahoma"
    "or:Oregon"
    "pa:Pennsylvania"
    "pr:Puerto Rico"
    "ri:Rhode Island"
    "sc:South Carolina"
    "sd:South Dakota"
    "tn:Tennessee"
    "ut:Utah"
    "vt:Vermont"
    "vi:Virgin Islands"
    "va:Virginia"
    "wa:Washington"
    "wv:West Virginia"
    "wi:Wisconsin"
)

echo "🔧 Updating Existing State Pipeline Repositories"
echo "Organization: $ORG"
echo "Total states to update: ${#STATES[@]}"
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

for state_entry in "${STATES[@]}"; do
    # Parse state code and name
    IFS=':' read -r state_code state_name <<< "$state_entry"
    state_lower=$(echo "$state_code" | tr '[:upper:]' '[:lower:]')
    repo_name="${state_lower}-data-pipeline"
    full_repo="$ORG/$repo_name"

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📍 $state_name ($state_code)"
    echo "   Repository: $full_repo"

    # Clone temporarily to update workflow files
    REPO_DIR="$TEMP_DIR/$repo_name"
    echo "   📥 Cloning..."

    if ! gh repo clone "$full_repo" "$REPO_DIR" -- --depth 1 --quiet 2>/dev/null; then
        echo "   ❌ Failed to clone repository"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        continue
    fi

    cd "$REPO_DIR"

    # Update text extraction workflow
    EXTRACT_WORKFLOW=".github/workflows/extract-text.yml"
    if [ -f "$EXTRACT_WORKFLOW" ]; then
        echo "   ✏️  Updating text extraction workflow state code..."

        # Try both possible patterns (in case some were updated, some weren't)
        sed -i.bak "s/state: UPDATE_STATE_HERE  # ⚠️ UPDATE THIS.*/state: $state_lower # $state_name/" "$EXTRACT_WORKFLOW"
        sed -i.bak "s/state: wy # ⚠️ UPDATE THIS.*/state: $state_lower # $state_name/" "$EXTRACT_WORKFLOW"
        rm -f "$EXTRACT_WORKFLOW.bak"
    else
        echo "   ⚠️  extract-text.yml not found"
    fi

    # Commit and push if there are changes
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
    git add .

    if git diff --staged --quiet; then
        echo "   ℹ️  No changes needed (already configured)"
        SKIP_COUNT=$((SKIP_COUNT + 1))
    else
        echo "   💾 Committing updates..."
        git commit -m "fix: update state code in text extraction workflow to $state_lower

Configure extract-text.yml with correct state: $state_lower for $state_name"

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
echo "   ℹ️  Already configured: $SKIP_COUNT"
echo "   ❌ Failed: $FAIL_COUNT"
echo ""
echo "🎉 Done! All repos should now have correct state codes."

