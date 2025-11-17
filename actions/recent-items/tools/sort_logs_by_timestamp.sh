#!/bin/bash

# Script to sort log files from stdin by their timestamps
# Usage: ./find_logs_json.sh | ./sort_logs_by_timestamp.sh
# The timestamp format expected is: logs/YYYYMMDDTHHMMSSZ_*.json

# Read from stdin and process each line
while IFS= read -r line; do
    # Skip empty lines and non-file lines (like the header messages)
    if [[ -z "$line" || "$line" =~ ^Finding.* || "$line" =~ ^Search.* ]]; then
        continue
    fi
    
    # Extract the timestamp from the filename
    # Pattern: .../logs/YYYYMMDDTHHMMSSZ_*.json
    if [[ "$line" =~ /logs/([0-9]{8}T[0-9]{6}Z)_ ]]; then
        timestamp="${BASH_REMATCH[1]}"
        echo "$timestamp|$line"
    fi
done | sort -r | cut -d'|' -f2- 2>/dev/null || true
