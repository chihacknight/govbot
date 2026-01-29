#!/bin/bash

# This file will run openstate scrape and make new production mocks.
# These mocks are used downstream, specifically right now by `actions/format`.

PROD_MOCKS="prod-mocks-$(date +%F)"
OPENSTATES_DATA_DIR="$PROD_MOCKS/_working/_data"

rm -rf "$PROD_MOCKS"
mkdir -p "$PROD_MOCKS"

# Using wy because its fast
./scrape.sh wy latest "$PROD_MOCKS"

files=($(find "$PROD_MOCKS" -type f | sort))
total=${#files[@]}
echo "Initial total count of files: $total"

# Get all file types from schemas directory
# Extract types from schema filenames (e.g., bill.schema.json -> bill)
SCHEMAS_DIR="schemas"
types=()
for schema_file in "$SCHEMAS_DIR"/*.schema.json; do
    if [ -f "$schema_file" ]; then
        basename=$(basename "$schema_file" .schema.json)
        types+=("$basename")
    fi
done

echo "Found types: ${types[*]}"

# For each type, keep only the first 20 files max
for type in "${types[@]}"; do
    echo "Processing type: $type"
    files=($(find "$PROD_MOCKS" -type f -name "${type}_*.json" | sort))
    total=${#files[@]}
    echo "  Total files for $type: $total"
    
    if [ $total -gt 20 ]; then
        # Keep first 20, delete the rest
        for i in "${!files[@]}"; do
            if [ $i -ge 20 ]; then
                rm -f "${files[$i]}"
            fi
        done
        echo "  Kept 20 files, deleted $((total - 20)) files"
    else
        echo "  Kept all $total files"
    fi
done

# Final count
files=($(find "$PROD_MOCKS" -type f | sort))
total=${#files[@]}
echo "Final total count of files: $total"
