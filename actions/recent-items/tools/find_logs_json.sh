#!/bin/bash

# Script to find all JSON files that have 'logs/' in their path
# Usage: ./find_logs_json.sh [directory]
# If no directory is provided, uses current directory

# Set the directory to search (default to current directory)
SEARCH_DIR="${1:-.}"

# Check if directory exists
if [ ! -d "$SEARCH_DIR" ]; then
    echo "Error: Directory $SEARCH_DIR does not exist"
    exit 1
fi

echo "Finding JSON files with 'logs/' in their path in: $SEARCH_DIR"
echo ""

# Find all files, filter for JSON files with 'logs/' in path
find "$SEARCH_DIR" -type f | grep -E '\.json$' | grep '/logs/'

echo ""
echo "Search completed."
