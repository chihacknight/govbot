#!/bin/bash
# Reusable snapshot testing script using git diff
# Usage: snapshot-test.sh <path-to-compare>
#   Set UPDATE=1 to update snapshots (stage changes)
#   Otherwise, compares and fails if differences found

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default $1 to __snapshots__ if not provided
if [ $# -eq 0 ]; then
    set -- "__snapshots__"
fi

# Combine $1 with current working directory
SNAPSHOTS_PATH="$(pwd)/$1"

# Check if path exists
if [ ! -e "$SNAPSHOTS_PATH" ]; then
    echo -e "${RED}Error:${NC} Path does not exist: $SNAPSHOTS_PATH"
    exit 1
fi

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo -e "${RED}Error:${NC} Not in a git repository"
    exit 1
fi

# Handle UPDATE mode
if [ "${UPDATE:-0}" = "1" ]; then
    echo -e "${YELLOW}UPDATE mode:${NC} Staging changes for $SNAPSHOTS_PATH"
    git add "$SNAPSHOTS_PATH"
    echo -e "${GREEN}✓${NC} Changes staged. Commit them to update snapshots."
    exit 0
fi

# Compare snapshots with committed versions
echo "Comparing snapshots with committed versions..."
if git diff --quiet "$SNAPSHOTS_PATH" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Snapshots match committed versions"
    exit 0
else
    echo -e "${RED}✗${NC} Snapshots differ from committed versions:"
    echo ""
    git diff --stat "$SNAPSHOTS_PATH" || true
    echo ""
    echo -e "${YELLOW}Detailed differences:${NC}"
    git diff "$SNAPSHOTS_PATH" || true
    echo ""
    echo -e "${YELLOW}To update snapshots, run:${NC}"
    echo -e "${YELLOW}  UPDATE=1 $0 $SNAPSHOTS_PATH${NC}"
    exit 1
fi

