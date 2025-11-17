#!/bin/bash
# Add PAT_WORKFLOW_TRIGGER secret to all state repos
# This enables auto-restart functionality for text extraction timeouts
# Usage: ./add-pat-secret-to-repos.sh <your-pat-token>

set -e

if [ $# -ne 1 ]; then
    echo "Usage: $0 <your-pat-token>"
    echo ""
    echo "Steps to create a PAT:"
    echo "  1. Go to GitHub Settings > Developer settings > Personal access tokens > Fine-grained tokens"
    echo "  2. Click 'Generate new token'"
    echo "  3. Name it something like 'Workflow Trigger for State Pipelines'"
    echo "  4. Set expiration (recommend 1 year)"
    echo "  5. Under 'Repository access', select 'All repositories' or specific org repos"
    echo "  6. Under 'Permissions', enable:"
    echo "     - Actions: Read and write (to trigger workflows)"
    echo "     - Contents: Read (to access repo)"
    echo "  7. Generate and copy the token"
    echo ""
    exit 1
fi

PAT_TOKEN="$1"
ORG="windy-civi-pipelines"
SECRET_NAME="PAT_WORKFLOW_TRIGGER"

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) is not installed"
    echo "Install it: brew install gh"
    exit 1
fi

echo "🔐 Adding $SECRET_NAME to all state repos..."
echo "Organization: $ORG"
echo ""
echo "⚠️  This will add the secret to ALL state pipeline repos"
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
        echo "⏭️  Skipping $repo_name (test repo)"
        SKIP_COUNT=$((SKIP_COUNT + 1))
        continue
    fi

    full_repo="$ORG/$repo_name"
    
    echo "🔑 Adding secret to $repo_name..."
    
    # Add the secret using gh CLI
    if echo "$PAT_TOKEN" | gh secret set "$SECRET_NAME" --repo "$full_repo" 2>/dev/null; then
        echo "   ✅ Secret added successfully"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        echo "   ❌ Failed to add secret"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
    
    # Be nice to GitHub API
    sleep 1
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Summary:"
echo "   ✅ Added: $SUCCESS_COUNT"
echo "   ⏭️  Skipped: $SKIP_COUNT"
echo "   ❌ Failed: $FAIL_COUNT"
echo ""
echo "🎉 Done! Auto-restart should now work for all repos."
echo ""
echo "📝 Next: Update the workflow files in each repo to use the PAT:"
echo "   Change: GH_TOKEN: \${{ secrets.GITHUB_TOKEN }}"
echo "   To:     GH_TOKEN: \${{ secrets.PAT_WORKFLOW_TRIGGER }}"

