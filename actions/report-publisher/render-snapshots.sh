#!/bin/bash
# Render snapshots for Report Publisher
# Finds all .yml files in examples/ and generates HTML outputs to __snapshots__/

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXAMPLES_DIR="$SCRIPT_DIR/examples"
SNAPSHOTS_DIR="$EXAMPLES_DIR/__snapshots__"
PUBLISHER="$SCRIPT_DIR/publish.py"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Ensure snapshots directory exists
mkdir -p "$SNAPSHOTS_DIR"

# Extract JSON from a YAML file
extract_json_from_yml() {
    local yml_file="$1"
    local in_run=false
    local in_echo=false
    local json=""
    local indent=""
    
    while IFS= read -r line; do
        # Check if we're entering a run: | block
        if [[ "$line" =~ ^[[:space:]]*run:[[:space:]]*\| ]]; then
            in_run=true
            # Capture the indentation
            indent="${line%%[^[:space:]]*}"
            continue
        fi
        
        # If we're in a run block
        if [ "$in_run" = true ]; then
            # Check if this line starts the echo command
            if [[ "$line" =~ echo[[:space:]]+\' ]]; then
                in_echo=true
                # Extract JSON from this line (everything after echo ')
                local rest="${line#*echo \'}"
                # Check if it ends on the same line
                if [[ "$rest" =~ \'[[:space:]]*\| ]]; then
                    # JSON is on one line
                    json="${rest%\' |*}"
                    break
                else
                    # JSON starts here, continue on next lines
                    json="$rest"
                fi
            elif [ "$in_echo" = true ]; then
                # Check if this line ends the JSON (contains ' |)
                if [[ "$line" =~ \'[[:space:]]*\| ]]; then
                    # Remove the closing quote and pipe
                    local rest="${line%\' |*}"
                    json="${json} ${rest}"
                    break
                else
                    # Continue collecting JSON
                    json="${json} ${line}"
                fi
            fi
            
            # Check if we've left the run block (line with less or equal indentation that's not part of the block)
            if [[ ! "$line" =~ ^${indent}[[:space:]] ]] && [ -n "${line// }" ]; then
                in_run=false
                in_echo=false
            fi
        fi
    done < "$yml_file"
    
    # Clean up the JSON: remove extra spaces and normalize
    json=$(echo "$json" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g')
    
    echo "$json"
}

# Process a single YAML file - generates output directly to snapshot directory
process_yml_file() {
    local yml_file="$1"
    local basename=$(basename "$yml_file" .yml)
    local output_file="$SNAPSHOTS_DIR/${basename}.html"
    
    echo -e "${YELLOW}Processing:${NC} $basename.yml"
    
    # Extract JSON from the YAML file
    local json_data=$(extract_json_from_yml "$yml_file")
    
    if [ -z "$json_data" ]; then
        echo -e "${RED}✗${NC} Failed to extract JSON from $basename.yml"
        return 1
    fi
    
    # Run the publisher to generate output directly to snapshot directory
    # Use TEST=1 to enable static timestamp for consistent snapshots
    export TEST=1
    if ! echo "$json_data" | python3 "$PUBLISHER" --mode pages --output "$output_file" > /dev/null 2>&1; then
        echo -e "${RED}✗${NC} Failed to generate output for $basename.html"
        return 1
    fi
    
    if [ ! -f "$output_file" ]; then
        echo -e "${RED}✗${NC} Output file not created: $basename.html"
        return 1
    fi
    
    # Remove corresponding JSON file if it was created (we only want HTML)
    local json_file="$SNAPSHOTS_DIR/${basename}.json"
    if [ -f "$json_file" ]; then
        rm -f "$json_file"
    fi
    
    echo -e "${GREEN}✓${NC} Generated: $basename.html"
    return 0
}

# Main function
main() {
    echo ""
    echo "╔════════════════════════════════════════╗"
    echo "║   Report Publisher Snapshot Renderer   ║"
    echo "╚════════════════════════════════════════╝"
    echo ""
    echo "Looking for .yml files in: $EXAMPLES_DIR"
    echo "Output directory: $SNAPSHOTS_DIR"
    echo ""
    
    # Find all .yml files in examples directory
    local yml_files=()
    while IFS= read -r -d '' file; do
        # Skip workflow-example.yml as it uses a different format
        if [[ "$(basename "$file")" != "workflow-example.yml" ]]; then
            yml_files+=("$file")
        fi
    done < <(find "$EXAMPLES_DIR" -maxdepth 1 -name "*.yml" -type f -print0)
    
    if [ ${#yml_files[@]} -eq 0 ]; then
        echo -e "${YELLOW}No .yml files found in examples directory${NC}"
        exit 0
    fi
    
    echo "Found ${#yml_files[@]} .yml file(s) to process:"
    for file in "${yml_files[@]}"; do
        echo "  - $(basename "$file")"
    done
    echo ""
    
    # Process each YAML file
    local has_errors=0
    for yml_file in "${yml_files[@]}"; do
        if ! process_yml_file "$yml_file"; then
            has_errors=1
        fi
    done
    
    # Keep removing JSON files until none remain (in case they get recreated)
    echo ""
    echo -e "${YELLOW}Cleaning up JSON files from snapshots directory...${NC}"
    local max_iterations=10
    local iteration=0
    local total_removed=0
    
    while [ $iteration -lt $max_iterations ]; do
        local json_files=()
        while IFS= read -r -d '' json_file; do
            json_files+=("$json_file")
        done < <(find "$SNAPSHOTS_DIR" -maxdepth 1 -name "*.json" -type f -print0 2>/dev/null || true)
        
        if [ ${#json_files[@]} -eq 0 ]; then
            break
        fi
        
        for json_file in "${json_files[@]}"; do
            echo -e "${YELLOW}  Removing:${NC} $(basename "$json_file")"
            rm -f "$json_file"
            ((total_removed++))
        done
        
        ((iteration++))
    done
    
    if [ $total_removed -gt 0 ]; then
        echo -e "${GREEN}  Removed $total_removed JSON file(s)${NC}"
    else
        echo -e "${GREEN}  No JSON files found${NC}"
    fi
    
    if [ $iteration -ge $max_iterations ] && [ ${#json_files[@]} -gt 0 ]; then
        echo -e "${RED}Warning: Reached maximum iterations while removing JSON files${NC}"
    fi
    
    echo ""
    if [ $has_errors -eq 0 ]; then
        echo -e "${GREEN}✓ All snapshots rendered successfully!${NC}"
        exit 0
    else
        echo -e "${RED}✗ Some snapshots failed to render${NC}"
        exit 1
    fi
}

# Run main function
main

