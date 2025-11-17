#!/bin/bash
# Check text extraction workflow run times across all state repos
# to identify states with incremental processing issues
# Usage: ./check-extraction-times.sh

set -e

ORG="windy-civi-pipelines"
WORKFLOW_NAME="extract-text.yml"

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) is not installed"
    echo "Install it: brew install gh"
    exit 1
fi

echo "🔍 Checking text extraction run times for all state repos..."
echo "⚠️  Runs longer than 40 minutes likely have incremental processing issues"
echo ""
echo "Repository                    | Status    | Duration | Conclusion"
echo "----------------------------- | --------- | -------- | ----------"

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
        continue
    fi

    full_repo="$ORG/$repo_name"
    
    # Get the most recent text extraction workflow run
    run_info=$(gh run list \
        --repo "$full_repo" \
        --workflow "$WORKFLOW_NAME" \
        --limit 1 \
        --json status,conclusion,startedAt,updatedAt,createdAt \
        --jq '.[0]' 2>/dev/null || echo "null")
    
    if [ "$run_info" == "null" ] || [ -z "$run_info" ]; then
        printf "%-30s | %-9s | %-8s | %s\n" "$repo_name" "N/A" "N/A" "No runs"
        continue
    fi
    
    status=$(echo "$run_info" | jq -r '.status // "unknown"')
    conclusion=$(echo "$run_info" | jq -r '.conclusion // "unknown"')
    started_at=$(echo "$run_info" | jq -r '.startedAt // ""')
    updated_at=$(echo "$run_info" | jq -r '.updatedAt // ""')
    
    # Calculate duration in minutes
    if [ -n "$started_at" ] && [ -n "$updated_at" ]; then
        start_sec=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$started_at" +%s 2>/dev/null || echo "0")
        end_sec=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$updated_at" +%s 2>/dev/null || echo "0")
        duration_sec=$((end_sec - start_sec))
        duration_min=$((duration_sec / 60))
    else
        duration_min=0
    fi
    
    # Flag if duration > 40 minutes
    flag=""
    if [ "$duration_min" -gt 40 ]; then
        flag="⚠️"
    fi
    
    printf "%-30s | %-9s | %3d min%s | %s\n" "$repo_name" "$status" "$duration_min" "$flag" "$conclusion"
done

echo ""
echo "Legend:"
echo "  ⚠️  = Longer than 40 minutes (likely has incremental processing issue)"
echo ""
echo "States with ⚠️ are likely using uppercase file extensions (.HTM instead of .html)"

