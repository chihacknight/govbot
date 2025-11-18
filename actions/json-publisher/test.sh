#!/bin/bash
# Local test runner for JSON Publisher
# Run this script to validate all features before committing

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PUBLISHER="$SCRIPT_DIR/publish.py"
PASSED=0
FAILED=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test result tracking
print_test_header() {
    echo ""
    echo "========================================="
    echo "$1"
    echo "========================================="
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASSED++))
}

print_failure() {
    echo -e "${RED}✗${NC} $1"
    ((FAILED++))
}

print_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

# Clean up test files
cleanup() {
    rm -rf /tmp/json-publisher-test 2>/dev/null || true
}

# Setup test directory
setup() {
    cleanup
    mkdir -p /tmp/json-publisher-test
    cd /tmp/json-publisher-test
}

# Test 1: Basic stdin input with git mode
test_stdin_git_mode() {
    print_test_header "Test 1: Stdin Input with Git Mode"

    echo '{"test": "stdin-git", "value": 123}' | \
    python3 "$PUBLISHER" --mode git --output test-git.json

    if [ -f test-git.json ] && grep -q '"test": "stdin-git"' test-git.json; then
        print_success "Stdin input with git mode"
    else
        print_failure "Stdin input with git mode"
        return 1
    fi
}

# Test 2: Pages mode with HTML generation
test_pages_mode() {
    print_test_header "Test 2: Pages Mode with HTML Generation"

    cat > test-input.json <<'EOF'
{
    "test": "pages",
    "data": {
        "nested": "value"
    },
    "array": [1, 2, 3]
}
EOF

    cat test-input.json | \
    python3 "$PUBLISHER" --mode pages --output test.html

    local errors=0

    if [ ! -f test.html ]; then
        print_failure "HTML file not created"
        ((errors++))
    elif ! grep -q '<title>JSON Report</title>' test.html; then
        print_failure "HTML missing title"
        ((errors++))
    elif ! grep -q 'json-key' test.html; then
        print_failure "HTML missing styling"
        ((errors++))
    elif ! grep -q '"test": "pages"' test.html; then
        print_failure "HTML missing data"
        ((errors++))
    fi

    if [ ! -f test.json ]; then
        print_failure "JSON file not created alongside HTML"
        ((errors++))
    fi

    if [ $errors -eq 0 ]; then
        print_success "Pages mode with HTML generation"
    else
        return 1
    fi
}

# Test 3: Complex JSON structure
test_complex_json() {
    print_test_header "Test 3: Complex JSON Structure"

    cat > complex.json <<'EOF'
{
    "string": "test",
    "number": 42,
    "float": 3.14,
    "boolean": true,
    "null_value": null,
    "array": [1, 2, 3],
    "nested": {
        "deep": {
            "value": "nested"
        }
    }
}
EOF

    cat complex.json | \
    python3 "$PUBLISHER" --mode pages --output complex.html

    local errors=0

    if ! grep -q 'json-string' complex.html; then
        print_failure "Missing string formatting"
        ((errors++))
    fi

    if ! grep -q 'json-number' complex.html; then
        print_failure "Missing number formatting"
        ((errors++))
    fi

    if ! grep -q 'json-boolean' complex.html; then
        print_failure "Missing boolean formatting"
        ((errors++))
    fi

    if ! grep -q 'json-null' complex.html; then
        print_failure "Missing null formatting"
        ((errors++))
    fi

    if ! grep -q 'json-array' complex.html; then
        print_failure "Missing array formatting"
        ((errors++))
    fi

    if ! grep -q 'json-object' complex.html; then
        print_failure "Missing object formatting"
        ((errors++))
    fi

    if [ $errors -eq 0 ]; then
        print_success "Complex JSON structure handling"
    else
        return 1
    fi
}

# Test 4: Invalid JSON handling
test_invalid_json() {
    print_test_header "Test 4: Invalid JSON Handling"

    if echo 'this is not valid json' | python3 "$PUBLISHER" --mode git --output should-fail.json 2>&1; then
        print_failure "Script should fail with invalid JSON"
        return 1
    else
        print_success "Invalid JSON properly rejected"
    fi
}

# Test 5: Missing required arguments
test_missing_args() {
    print_test_header "Test 5: Missing Required Arguments"

    if echo '{"test": "fail"}' | timeout 2 python3 "$PUBLISHER" 2>&1; then
        print_failure "Script should fail without mode argument"
        return 1
    else
        print_success "Missing arguments properly rejected"
    fi
}

# Test 6: Interactive HTML features
test_interactive_features() {
    print_test_header "Test 6: Interactive HTML Features"

    echo '{"interactive": "test"}' | \
    python3 "$PUBLISHER" --mode pages --output interactive.html

    local errors=0

    if ! grep -q 'toggleRaw()' interactive.html; then
        print_failure "Missing toggle function"
        ((errors++))
    fi

    if ! grep -q 'copyToClipboard()' interactive.html; then
        print_failure "Missing copy function"
        ((errors++))
    fi

    if ! grep -q 'download' interactive.html; then
        print_failure "Missing download link"
        ((errors++))
    fi

    if ! grep -q 'class="raw-json"' interactive.html; then
        print_failure "Missing raw JSON section"
        ((errors++))
    fi

    if [ $errors -eq 0 ]; then
        print_success "Interactive HTML features"
    else
        return 1
    fi
}

# Test 7: Edge cases
test_edge_cases() {
    print_test_header "Test 7: Edge Cases"

    local errors=0

    # Empty object
    if ! echo '{}' | python3 "$PUBLISHER" --mode git --output empty.json 2>&1; then
        print_failure "Failed to handle empty JSON object"
        ((errors++))
    else
        print_success "Empty JSON object handled"
    fi

    # Empty array
    if ! echo '[]' | python3 "$PUBLISHER" --mode pages --output empty-array.html 2>&1; then
        print_failure "Failed to handle empty array"
        ((errors++))
    else
        print_success "Empty array handled"
    fi

    # Special characters
    if ! echo '{"special": "Test with \"quotes\" and '\''apostrophes'\''", "unicode": "Hello 世界 🌍"}' | \
         python3 "$PUBLISHER" --mode pages --output special.html 2>&1; then
        print_failure "Failed to handle special characters"
        ((errors++))
    else
        print_success "Special characters handled"
    fi

    return $errors
}

# Test 8: Output format validation
test_output_format() {
    print_test_header "Test 8: Output Format Validation"

    echo '{"format": "test"}' | \
    python3 "$PUBLISHER" --mode git --output formatted.json

    local errors=0

    # Check if jq is available for JSON validation
    if command -v jq &> /dev/null; then
        if ! jq empty formatted.json 2>&1; then
            print_failure "Output is not valid JSON"
            ((errors++))
        else
            print_success "Valid JSON output"
        fi

        # Check indentation (should be 2 spaces)
        if ! grep -q '^  "format"' formatted.json; then
            print_failure "JSON not properly indented"
            ((errors++))
        else
            print_success "Proper JSON indentation"
        fi
    else
        print_info "jq not available, skipping JSON validation"
    fi

    return $errors
}

# Test 9: HTML structure validation
test_html_structure() {
    print_test_header "Test 9: HTML Structure Validation"

    echo '{"html": "test"}' | \
    python3 "$PUBLISHER" --mode pages --output structure.html

    local errors=0

    # Check DOCTYPE
    if ! grep -q '<!DOCTYPE html>' structure.html; then
        print_failure "Missing DOCTYPE declaration"
        ((errors++))
    fi

    # Check required meta tags
    if ! grep -q '<meta charset="UTF-8">' structure.html; then
        print_failure "Missing charset meta tag"
        ((errors++))
    fi

    if ! grep -q '<meta name="viewport"' structure.html; then
        print_failure "Missing viewport meta tag"
        ((errors++))
    fi

    # Check for CSS reset
    if ! grep -q 'box-sizing: border-box' structure.html; then
        print_failure "Missing CSS box-sizing reset"
        ((errors++))
    fi

    # Check for responsive design
    if ! grep -q 'max-width' structure.html; then
        print_failure "Missing responsive max-width"
        ((errors++))
    fi

    if [ $errors -eq 0 ]; then
        print_success "HTML structure validation"
    else
        return 1
    fi
}

# Test 10: Help and documentation
test_help() {
    print_test_header "Test 10: Help and Documentation"

    if python3 "$PUBLISHER" --help | grep -q "Publishing mode"; then
        print_success "Help documentation available"
    else
        print_failure "Help documentation missing or incomplete"
        return 1
    fi
}

# Run all tests
main() {
    echo ""
    echo "╔════════════════════════════════════════╗"
    echo "║   JSON Publisher Test Suite            ║"
    echo "╚════════════════════════════════════════╝"
    echo ""

    setup

    # Run all tests
    test_stdin_git_mode || true
    test_pages_mode || true
    test_complex_json || true
    test_invalid_json || true
    test_missing_args || true
    test_interactive_features || true
    test_edge_cases || true
    test_output_format || true
    test_html_structure || true
    test_help || true

    # Print summary
    echo ""
    echo "========================================="
    echo "Test Summary"
    echo "========================================="
    echo -e "${GREEN}Passed:${NC} $PASSED"
    echo -e "${RED}Failed:${NC} $FAILED"
    echo "Total:  $((PASSED + FAILED))"
    echo "========================================="

    cleanup

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
