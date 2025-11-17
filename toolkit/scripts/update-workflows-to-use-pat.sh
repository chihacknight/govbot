#!/bin/bash
# Update text extraction workflows to use PAT instead of GITHUB_TOKEN
# This enables auto-restart functionality
# Usage: ./update-workflows-to-use-pat.sh

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

echo "🔧 Updating workflows to use PAT_WORKFLOW_TRIGGER..."
echo "Organization: $ORG"
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

# Get all repos in the org that end with -data-pipeline
ALL_REPOS=$(gh repo list "$ORG" --limit 200 --json name --jq '.[] | select(.name | endswith("-data-pipeline")) | .name' | sort)

# Skip test repos
SKIP_REPOS=(
    "usa-data-pipeline3"
    "usa-data-pipelinetest2"
    "usa-data-pipelinetest3"
)

for repo_name in $ALL_REPOS; do
    # Check if this repo should be skipped
    skip=false
    for skip_repo in "${SKIP_REPOS[@]}"; do
        if [ "$repo_name" == "$skip_repo" ]; then
            skip=true
            break
        fi
    done

    if [ "$skip" = true ]; then
        SKIP_COUNT=$((SKIP_COUNT + 1))
        continue
    fi

    full_repo="$ORG/$repo_name"
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📍 $repo_name"
    
    # Clone the repo
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
        # Check if it uses GITHUB_TOKEN in the restart step
        if grep -q "GH_TOKEN.*GITHUB_TOKEN" "$EXTRACT_WORKFLOW"; then
            echo "   ✏️  Updating to use PAT_WORKFLOW_TRIGGER..."
            
            # Replace GITHUB_TOKEN with PAT_WORKFLOW_TRIGGER in the restart step
            sed -i.bak 's/GH_TOKEN: \${{ secrets\.GITHUB_TOKEN }}/GH_TOKEN: ${{ secrets.PAT_WORKFLOW_TRIGGER }}/g' "$EXTRACT_WORKFLOW"
            rm -f "$EXTRACT_WORKFLOW.bak"
            
            # Commit and push
            git config user.name "github-actions[bot]"
            git config user.email "github-actions[bot]@users.noreply.github.com"
            git add .
            
            if git diff --staged --quiet; then
                echo "   ℹ️  No changes needed"
                SKIP_COUNT=$((SKIP_COUNT + 1))
            else
                git commit -m "fix: use PAT for workflow auto-restart

- Change from GITHUB_TOKEN to PAT_WORKFLOW_TRIGGER
- GITHUB_TOKEN cannot trigger workflows due to GitHub security policy
- This enables auto-restart functionality when extraction times out"

                echo "   📤 Pushing changes..."
                if git push origin main 2>/dev/null; then
                    echo "   ✅ Updated successfully"
                    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
                else
                    echo "   ❌ Failed to push"
                    FAIL_COUNT=$((FAIL_COUNT + 1))
                fi
            fi
        else
            echo "   ℹ️  Already using PAT or no restart logic found"
            SKIP_COUNT=$((SKIP_COUNT + 1))
        fi
    else
        echo "   ⚠️  extract-text.yml not found"
        SKIP_COUNT=$((SKIP_COUNT + 1))
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
echo "   ⏭️  Skipped: $SKIP_COUNT"
echo "   ❌ Failed: $FAIL_COUNT"
echo ""
echo "🎉 Done! Auto-restart should now work."

