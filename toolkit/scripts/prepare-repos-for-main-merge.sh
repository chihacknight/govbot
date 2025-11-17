#!/bin/bash
# Prepare all state repos for toolkit main branch merge
# This script:
# 1. Updates both workflow files to use @main instead of @refactor/v2-data-structure
# 2. Removes 'testing' topic from all repos (keeps other topics like 'working')
# 3. Updates repo descriptions to standard format
#
# Usage: ./prepare-repos-for-main-merge.sh

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

# Check if authenticated
if ! gh auth status &> /dev/null; then
    echo "❌ Not authenticated with GitHub CLI"
    echo "Run: gh auth login"
    exit 1
fi

# Function to get state name from code
get_state_name() {
    local code=$1
    case "$code" in
        "ak") echo "Alaska" ;;
        "al") echo "Alabama" ;;
        "ar") echo "Arkansas" ;;
        "az") echo "Arizona" ;;
        "ca") echo "California" ;;
        "co") echo "Colorado" ;;
        "ct") echo "Connecticut" ;;
        "dc") echo "District of Columbia" ;;
        "de") echo "Delaware" ;;
        "fl") echo "Florida" ;;
        "ga") echo "Georgia" ;;
        "gu") echo "Guam" ;;
        "hi") echo "Hawaii" ;;
        "ia") echo "Iowa" ;;
        "id") echo "Idaho" ;;
        "il") echo "Illinois" ;;
        "in") echo "Indiana" ;;
        "ks") echo "Kansas" ;;
        "ky") echo "Kentucky" ;;
        "la") echo "Louisiana" ;;
        "ma") echo "Massachusetts" ;;
        "md") echo "Maryland" ;;
        "me") echo "Maine" ;;
        "mi") echo "Michigan" ;;
        "mn") echo "Minnesota" ;;
        "mo") echo "Missouri" ;;
        "mp") echo "Northern Mariana Islands" ;;
        "ms") echo "Mississippi" ;;
        "mt") echo "Montana" ;;
        "nc") echo "North Carolina" ;;
        "nd") echo "North Dakota" ;;
        "ne") echo "Nebraska" ;;
        "nh") echo "New Hampshire" ;;
        "nj") echo "New Jersey" ;;
        "nm") echo "New Mexico" ;;
        "nv") echo "Nevada" ;;
        "ny") echo "New York" ;;
        "oh") echo "Ohio" ;;
        "ok") echo "Oklahoma" ;;
        "or") echo "Oregon" ;;
        "pa") echo "Pennsylvania" ;;
        "pr") echo "Puerto Rico" ;;
        "ri") echo "Rhode Island" ;;
        "sc") echo "South Carolina" ;;
        "sd") echo "South Dakota" ;;
        "tn") echo "Tennessee" ;;
        "tx") echo "Texas" ;;
        "usa") echo "Federal" ;;
        "ut") echo "Utah" ;;
        "va") echo "Virginia" ;;
        "vi") echo "Virgin Islands" ;;
        "vt") echo "Vermont" ;;
        "wa") echo "Washington" ;;
        "wi") echo "Wisconsin" ;;
        "wv") echo "West Virginia" ;;
        "wy") echo "Wyoming" ;;
        *) echo "" ;;
    esac
}

# Repos to skip (test repos that will be archived)
SKIP_REPOS=(
    "usa-data-pipeline3"
    "usa-data-pipelinetest2"
    "usa-data-pipelinetest3"
)

echo "🏛️  Preparing State Repos for Main Branch Merge"
echo "Organization: $ORG"
echo ""
echo "Changes to be made:"
echo "  1. Update workflow files to use @main branch"
echo "  2. Remove 'testing' topic (keep other tags)"
echo "  3. Update repo descriptions to standard format"
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
echo "📋 Fetching all pipeline repos from $ORG..."
ALL_REPOS=$(gh repo list "$ORG" --limit 200 --json name --jq '.[] | select(.name | endswith("-data-pipeline")) | .name')

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
        continue
    fi

    # Extract state code from repo name (e.g., "il-data-pipeline" -> "il")
    state_code="${repo_name%-data-pipeline}"
    state_name=$(get_state_name "$state_code")

    if [ -z "$state_name" ]; then
        echo "⚠️  Unknown state code: $state_code (repo: $repo_name) - skipping"
        SKIP_COUNT=$((SKIP_COUNT + 1))
        continue
    fi

    full_repo="$ORG/$repo_name"

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📍 $state_name ($state_code)"
    echo "   Repository: $full_repo"

    # Clone the repo
    REPO_DIR="$TEMP_DIR/$repo_name"
    echo "   📥 Cloning..."

    if ! gh repo clone "$full_repo" "$REPO_DIR" -- --depth 1 --quiet 2>/dev/null; then
        echo "   ❌ Failed to clone repository"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        continue
    fi

    cd "$REPO_DIR"

    # Track if we made any changes
    changes_made=false

    # Update scrape-and-format workflow
    SCRAPE_WORKFLOW=".github/workflows/scrape-and-format-data.yml"
    if [ -f "$SCRAPE_WORKFLOW" ]; then
        echo "   ✏️  Updating scrape-and-format workflow to @main..."
        # Update both scrape and format action references
        if grep -q "@refactor/v2-data-structure" "$SCRAPE_WORKFLOW" || \
           grep -q "@[^m][^a][^i][^n]" "$SCRAPE_WORKFLOW" 2>/dev/null; then
            sed -i.bak 's|windy-civi/toolkit/actions/scrape@[^[:space:]]*|windy-civi/toolkit/actions/scrape@main|g' "$SCRAPE_WORKFLOW"
            sed -i.bak 's|windy-civi/toolkit/actions/format@[^[:space:]]*|windy-civi/toolkit/actions/format@main|g' "$SCRAPE_WORKFLOW"
            rm -f "$SCRAPE_WORKFLOW.bak"
            changes_made=true
        fi
    fi

    # Update text extraction workflow
    EXTRACT_WORKFLOW=".github/workflows/extract-text.yml"
    if [ -f "$EXTRACT_WORKFLOW" ]; then
        echo "   ✏️  Updating extract-text workflow to @main..."
        if grep -q "@refactor/v2-data-structure" "$EXTRACT_WORKFLOW" || \
           grep -q "@[^m][^a][^i][^n]" "$EXTRACT_WORKFLOW" 2>/dev/null; then
            sed -i.bak 's|windy-civi/toolkit/actions/extract@[^[:space:]]*|windy-civi/toolkit/actions/extract@main|g' "$EXTRACT_WORKFLOW"
            rm -f "$EXTRACT_WORKFLOW.bak"
            changes_made=true
        fi
    fi

    # Commit workflow changes if any were made
    if [ "$changes_made" = true ]; then
        git config user.name "github-actions[bot]"
        git config user.email "github-actions[bot]@users.noreply.github.com"
        git add .

        echo "   💾 Committing workflow updates..."
        git commit -m "chore: update toolkit actions to use @main branch

- Update scrape action reference to @main
- Update format action reference to @main
- Update extract action reference to @main

Preparing for toolkit v2.0 data structure merge to main."

        echo "   📤 Pushing changes..."
        if ! git push origin main 2>/dev/null; then
            echo "   ❌ Failed to push changes"
            FAIL_COUNT=$((FAIL_COUNT + 1))
            cd "$TEMP_DIR"
            rm -rf "$REPO_DIR"
            continue
        fi
    else
        echo "   ℹ️  Workflows already use @main"
    fi

    # Update repo description
    echo "   📝 Updating repository description..."
    if [ "$state_code" == "usa" ]; then
        new_description="🏛️ Federal legislative data pipeline"
    else
        new_description="🏛️ $state_name legislative data pipeline"
    fi

    gh repo edit "$full_repo" --description "$new_description" 2>/dev/null || \
        echo "   ⚠️  Could not update description"

    # Get current topics and remove 'testing' while keeping others
    echo "   🏷️  Updating topics (removing 'testing')..."
    current_topics=$(gh repo view "$full_repo" --json repositoryTopics --jq '.repositoryTopics[].name' | tr '\n' ' ')

    # Remove 'testing' from topics if present
    new_topics=""
    for topic in $current_topics; do
        if [ "$topic" != "testing" ]; then
            new_topics="$new_topics$topic,"
        fi
    done
    # Remove trailing comma
    new_topics="${new_topics%,}"

    if [ -n "$new_topics" ]; then
        # Remove all topics first, then add back the filtered ones
        # Note: We need to do this because gh doesn't have a remove-topic command
        IFS=',' read -ra TOPICS_ARRAY <<< "$new_topics"

        # Clear all topics first
        for topic in $current_topics; do
            gh repo edit "$full_repo" --remove-topic "$topic" 2>/dev/null || true
        done

        # Add back non-testing topics
        for topic in "${TOPICS_ARRAY[@]}"; do
            gh repo edit "$full_repo" --add-topic "$topic" 2>/dev/null || true
        done
    fi

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
echo "   ✅ Updated: $SUCCESS_COUNT"
echo "   ⏭️  Skipped: $SKIP_COUNT"
echo "   ❌ Failed: $FAIL_COUNT"
echo ""
echo "🎉 Done! All state repos are ready for main branch merge."
echo ""
echo "📝 Next steps:"
echo "   1. Verify changes in a few repos"
echo "   2. Merge toolkit refactor/v2-data-structure branch to main"
echo "   3. Monitor first few workflow runs"
echo ""

