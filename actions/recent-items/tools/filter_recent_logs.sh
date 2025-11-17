#!/bin/bash

# Script to filter log files from stdin to only show files with timestamps from the last 30 days
# Usage: ./find_logs_json.sh | ./filter_recent_logs.sh
# The timestamp format expected is: logs/YYYYMMDDTHHMMSSZ_*.json

# Calculate the timestamp for 30 days ago
# Try GNU date first (Linux), then BSD date (macOS)
THIRTY_DAYS_AGO=$(date -d "30 days ago" +%Y%m%d%H%M%SZ 2>/dev/null || date -v-30d +%Y%m%d%H%M%SZ)

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
        
        # Compare timestamps (they're in sortable format)
        if [[ "$timestamp" > "$THIRTY_DAYS_AGO" ]]; then
            echo "$line"
        fi
    fi
done
