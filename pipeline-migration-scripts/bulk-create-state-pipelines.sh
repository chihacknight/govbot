#!/bin/bash
# Bulk create state pipeline repositories from template with auto-configured state codes
# Usage: ./bulk-create-state-pipelines.sh

set -e

TEMPLATE_REPO="windy-civi-pipelines/windy-civi-template-pipeline"
ORG="windy-civi-pipelines"
TEMP_DIR=$(mktemp -d)

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) is not installed"
    echo "Install it: brew install gh"
    exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null; then
    echo "❌ Not authenticated with GitHub CLI"
    echo "Run: gh auth login"
    exit 1
fi

# Cleanup function
cleanup() {
    if [ -d "$TEMP_DIR" ]; then
        echo "🧹 Cleaning up temp directory..."
        rm -rf "$TEMP_DIR"
    fi
}
trap cleanup EXIT

# List of states to create (excluding already tested: fl, ca, ct, wy)
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

echo "🏛️  Bulk Creating State Pipeline Repositories"
echo "Template: $TEMPLATE_REPO"
echo "Organization: $ORG"
echo "Total states to create: ${#STATES[@]}"
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

# Get list of existing repos in the org
echo "📋 Fetching existing repos in $ORG..."
EXISTING_REPOS=$(gh repo list "$ORG" --limit 200 --json name --jq '.[].name')

for state_entry in "${STATES[@]}"; do
    # Parse state code and name
    IFS=':' read -r state_code state_name <<< "$state_entry"
    state_lower=$(echo "$state_code" | tr '[:upper:]' '[:lower:]')
    repo_name="${state_lower}-data-pipeline"
    full_repo="$ORG/$repo_name"

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📍 $state_name ($state_code)"
    echo "   Repository: $full_repo"

    # Check if repo already exists in THIS org (not archived or other orgs)
    if echo "$EXISTING_REPOS" | grep -q "^${repo_name}$"; then
        echo "   ⚠️  Already exists - skipping"
        SKIP_COUNT=$((SKIP_COUNT + 1))
        continue
    fi

    # Step 1: Create repo from template (no clone)
    echo "   🔨 Creating repository from template..."
    if ! gh repo create "$full_repo" \
        --template "$TEMPLATE_REPO" \
        --public \
        --description "🏛️ $state_name legislative data pipeline" \
        --clone=false; then
        echo "   ❌ Failed to create repository"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        continue
    fi

    # Wait for repo to be ready
    sleep 3

    # Step 2: Clone temporarily to update workflow files
    echo "   📥 Cloning temporarily to update state codes..."
    REPO_DIR="$TEMP_DIR/$repo_name"

    if ! gh repo clone "$full_repo" "$REPO_DIR" -- --depth 1 --quiet; then
        echo "   ❌ Failed to clone repository"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        continue
    fi

    cd "$REPO_DIR"

    # Step 3: Update scrape-and-format workflow
    SCRAPE_WORKFLOW=".github/workflows/scrape-and-format-data.yml"
    if [ -f "$SCRAPE_WORKFLOW" ]; then
        echo "   ✏️  Updating scrape-and-format workflow..."
        sed -i.bak "s/STATE_CODE: UPDATE_STATE_HERE/STATE_CODE: $state_lower/" "$SCRAPE_WORKFLOW"
        rm -f "$SCRAPE_WORKFLOW.bak"
    fi

    # Step 4: Update text extraction workflow
    EXTRACT_WORKFLOW=".github/workflows/extract-text.yml"
    if [ -f "$EXTRACT_WORKFLOW" ]; then
        echo "   ✏️  Updating text extraction workflow..."
        sed -i.bak "s/state: UPDATE_STATE_HERE  # ⚠️ UPDATE THIS/state: $state_lower # $state_name/" "$EXTRACT_WORKFLOW"
        rm -f "$EXTRACT_WORKFLOW.bak"
    fi

    # Step 5: Update README title
    if [ -f "README.md" ]; then
        echo "   ✏️  Updating README..."
        sed -i.bak "s/STATE-data-pipeline/${state_name} Data Pipeline/" "README.md"
        sed -i.bak "s/STATE_CODE: il/STATE_CODE: $state_lower/" "README.md"
        sed -i.bak "s/state: il/state: $state_lower/" "README.md"
        rm -f "README.md.bak"
    fi

    # Step 6: Commit and push changes
    echo "   💾 Committing updates..."
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
    git add .

    if git diff --staged --quiet; then
        echo "   ℹ️  No changes needed"
    else
        git commit -m "chore: configure for $state_name ($state_code)

- Update STATE_CODE to $state_lower in scrape-and-format workflow
- Update state to $state_lower in text extraction workflow
- Update README for $state_name"

        echo "   📤 Pushing changes..."
        git push origin main
    fi

    # Step 7: Add topics
    echo "   🏷️  Adding topics..."
    gh repo edit "$full_repo" \
        --add-topic state-pipeline,openstates,legislative-data,testing \
        2>/dev/null || echo "   ⚠️  Topics may need manual update"

    echo "   ✅ Complete: https://github.com/$full_repo"
    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))

    # Clean up this repo's temp clone
    cd "$TEMP_DIR"
    rm -rf "$REPO_DIR"

    # Be nice to GitHub API
    sleep 2
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Summary:"
echo "   ✅ Created: $SUCCESS_COUNT"
echo "   ⚠️  Skipped: $SKIP_COUNT"
echo "   ❌ Failed: $FAIL_COUNT"
echo ""
echo "🎉 Done! All repos are ready to use."
echo ""
echo "📝 Next steps:"
echo "   1. Enable Actions in each repo (if not auto-enabled)"
echo "   2. Trigger scrape-and-format workflow manually to test"
echo "   3. Check output in country:us/state:XX/sessions/"
echo "   4. Update STATE_SCRAPER_STATUS.md as you test each one"

