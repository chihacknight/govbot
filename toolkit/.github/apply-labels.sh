#!/bin/bash

# Script to apply standard labels to a GitHub repository
# Usage: ./apply-labels.sh [owner/repo]
# If no repo is specified, uses the current repo

set -e

# Get the repository
if [ -z "$1" ]; then
  # Try to get from current git remote
  REPO=$(git remote get-url origin | sed -E 's/.*[:/]([^/]+\/[^.]+)(\.git)?$/\1/')
  echo "Using current repository: $REPO"
else
  REPO="$1"
  echo "Using specified repository: $REPO"
fi

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
  echo "Error: GitHub CLI (gh) is not installed"
  echo "Install it with: brew install gh"
  exit 1
fi

# Check if user is authenticated
if ! gh auth status &> /dev/null; then
  echo "Error: Not authenticated with GitHub CLI"
  echo "Run: gh auth login"
  exit 1
fi

# Path to labels file
LABELS_FILE="$(dirname "$0")/labels.json"

if [ ! -f "$LABELS_FILE" ]; then
  echo "Error: labels.json not found at $LABELS_FILE"
  exit 1
fi

echo "Applying labels from $LABELS_FILE to $REPO..."

# Read and apply each label
jq -c '.[]' "$LABELS_FILE" | while read -r label; do
  NAME=$(echo "$label" | jq -r '.name')
  COLOR=$(echo "$label" | jq -r '.color')
  DESCRIPTION=$(echo "$label" | jq -r '.description')

  echo "Creating label: $NAME"

  # Try to create the label, or update if it exists
  gh label create "$NAME" \
    --repo "$REPO" \
    --color "$COLOR" \
    --description "$DESCRIPTION" \
    --force 2>/dev/null || echo "  (already exists, updating...)"
done

echo "✅ Done! Labels applied to $REPO"

