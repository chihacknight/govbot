#!/bin/bash
# Test runner for Report Publisher
# Finds all .yml files in examples/ and compares generated HTML outputs with snapshots in test_snapshots/
# Set UPDATE=1 to update snapshots instead of comparing them

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
    local expected_file="$SNAPSHOTS_DIR/${basename}.html"
    local actual_file=$(mktemp)
    
    echo -e "${YELLOW}Processing:${NC} $basename.yml"
    
    # Extract JSON from the YAML file
    local json_data=$(extract_json_from_yml "$yml_file")
    
    if [ -z "$json_data" ]; then
        echo -e "${RED}✗${NC} Failed to extract JSON from $basename.yml"
        rm -f "$actual_file"
        ((FAILED++))
        return 1
    fi
    
    # Run the publisher to generate actual output
    if ! echo "$json_data" | python3 "$PUBLISHER" --mode pages --output "$actual_file" > /dev/null 2>&1; then
        echo -e "${RED}✗${NC} Failed to generate output for $basename.html"
        rm -f "$actual_file"
        ((FAILED++))
        return 1
    fi
    
    if [ ! -f "$actual_file" ]; then
        echo -e "${RED}✗${NC} Output file not created: $basename.html"
        rm -f "$actual_file"
        ((FAILED++))
        return 1
    fi
    
    # Handle missing snapshot
    if [ ! -f "$expected_file" ]; then
        if [ "${UPDATE:-0}" = "1" ]; then
            # Update mode: create the snapshot
            cp "$actual_file" "$expected_file"
            echo -e "${GREEN}✓${NC} Created snapshot: $basename.html"
            rm -f "$actual_file"
            ((PASSED++))
            return 0
        else
            # Test mode: fail with instructions
            echo -e "${RED}✗${NC} Expected snapshot not found: $basename.html"
            echo -e "${YELLOW}  To create the snapshot, run:${NC}"
            echo -e "${YELLOW}    UPDATE=1 ./test.sh${NC}"
            rm -f "$actual_file"
            ((FAILED++))
            return 1
        fi
    fi
    
    # Compare files
    if diff -q "$expected_file" "$actual_file" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Snapshot matches: $basename.html"
        rm -f "$actual_file"
        ((PASSED++))
        return 0
    else
        # Snapshots differ
        if [ "${UPDATE:-0}" = "1" ]; then
            # Update mode: update the snapshot
            cp "$actual_file" "$expected_file"
            echo -e "${GREEN}✓${NC} Updated snapshot: $basename.html"
            rm -f "$actual_file"
            ((PASSED++))
            return 0
        else
            # Test mode: fail with instructions
            echo -e "${RED}✗${NC} Snapshot differs: $basename.html"
            echo -e "${YELLOW}  Differences:${NC}"
            diff -u "$expected_file" "$actual_file" || true
            echo -e "${YELLOW}  To update the snapshot, run:${NC}"
            echo -e "${YELLOW}    UPDATE=1 ./test.sh${NC}"
            rm -f "$actual_file"
            ((FAILED++))
            return 1
        fi
    fi
}

# Main function
main() {
    echo ""
    echo "╔════════════════════════════════════════╗"
    echo "║   Report Publisher Test Runner        ║"
    echo "╚════════════════════════════════════════╝"
    echo ""
    if [ "${UPDATE:-0}" = "1" ]; then
        echo -e "${YELLOW}Mode: UPDATE (snapshots will be updated)${NC}"
    else
        echo -e "${YELLOW}Mode: TEST (snapshots will be compared)${NC}"
    fi
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
        process_yml_file "$yml_file" || true  # Continue even if a test fails
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
