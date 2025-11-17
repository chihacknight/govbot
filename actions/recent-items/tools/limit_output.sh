#!/bin/bash

# Script to limit the number of output lines from stdin
# Usage: ./find_logs_json.sh | ./limit_output.sh [number]
# If no number is provided, defaults to 10

# Set the limit (default to 10 if no argument provided)
LIMIT="${1:-10}"

# Validate that the argument is a positive integer
if ! [[ "$LIMIT" =~ ^[0-9]+$ ]] || [ "$LIMIT" -le 0 ]; then
    echo "Error: Please provide a positive integer for the limit" >&2
    echo "Usage: $0 [number]" >&2
    exit 1
fi

# Read from stdin and limit output
head -n "$LIMIT" 2>/dev/null || true
