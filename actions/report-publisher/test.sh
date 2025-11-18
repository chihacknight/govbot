#!/bin/bash
# Test runner for JSON Publisher
# Finds all .yml files in examples/ and generates corresponding HTML outputs in test_snapshots/

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXAMPLES_DIR="$SCRIPT_DIR/examples"
SNAPSHOTS_DIR="$EXAMPLES_DIR/test_snapshots"
PUBLISHER="$SCRIPT_DIR/publish.py"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASSED=0
FAILED=0

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

# Process a single YAML file
process_yml_file() {
    local yml_file="$1"
    local basename=$(basename "$yml_file" .yml)
    local output_file="$SNAPSHOTS_DIR/${basename}.html"
    
    echo -e "${YELLOW}Processing:${NC} $basename.yml"
    
    # Extract JSON from the YAML file
    local json_data=$(extract_json_from_yml "$yml_file")
    
    if [ -z "$json_data" ]; then
        echo -e "${RED}✗${NC} Failed to extract JSON from $basename.yml"
        ((FAILED++))
        return 1
    fi
    
    # Run the publisher
    if echo "$json_data" | python3 "$PUBLISHER" --mode pages --output "$output_file" > /dev/null 2>&1; then
        if [ -f "$output_file" ]; then
            echo -e "${GREEN}✓${NC} Generated $basename.html"
            ((PASSED++))
            return 0
        else
            echo -e "${RED}✗${NC} Output file not created: $basename.html"
            ((FAILED++))
            return 1
        fi
    else
        echo -e "${RED}✗${NC} Failed to generate $basename.html"
        ((FAILED++))
        return 1
    fi
}

# Main function
main() {
    echo ""
    echo "╔════════════════════════════════════════╗"
    echo "║   Report Publisher Test Runner        ║"
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
    for yml_file in "${yml_files[@]}"; do
        process_yml_file "$yml_file"
    done
    
    # Clean up orphaned snapshot files
    echo ""
    echo -e "${YELLOW}Cleaning up orphaned snapshots...${NC}"
    local cleaned=0
    if [ -d "$SNAPSHOTS_DIR" ]; then
        while IFS= read -r -d '' html_file; do
            local html_basename=$(basename "$html_file" .html)
            local corresponding_yml="$EXAMPLES_DIR/${html_basename}.yml"
            
            # Check if corresponding YAML file exists (and is not workflow-example.yml)
            if [ ! -f "$corresponding_yml" ] || [[ "$(basename "$corresponding_yml")" == "workflow-example.yml" ]]; then
                echo -e "${YELLOW}  Removing orphaned:${NC} $html_basename.html"
                rm -f "$html_file"
                ((cleaned++))
            fi
        done < <(find "$SNAPSHOTS_DIR" -maxdepth 1 -name "*.html" -type f -print0 2>/dev/null || true)
    fi
    
    if [ $cleaned -eq 0 ]; then
        echo -e "${GREEN}  No orphaned snapshots found${NC}"
    else
        echo -e "${GREEN}  Cleaned up $cleaned orphaned snapshot(s)${NC}"
    fi
    
    # Print summary
    echo ""
    echo "========================================="
    echo "Test Summary"
    echo "========================================="
    echo -e "${GREEN}Passed:${NC} $PASSED"
    echo -e "${RED}Failed:${NC} $FAILED"
    echo "Total:  $((PASSED + FAILED))"
    echo "========================================="
    
    if [ $FAILED -eq 0 ]; then
        echo -e "\n${GREEN}✓ All tests passed!${NC}\n"
        exit 0
    else
        echo -e "\n${RED}✗ Some tests failed${NC}\n"
        exit 1
    fi
}

# Run main function
main
