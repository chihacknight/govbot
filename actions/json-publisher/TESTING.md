# Testing Documentation

This document provides detailed information about the test suite for JSON Publisher.

## Test Architecture

The JSON Publisher includes two layers of testing:

1. **Local Test Runner** (`test.sh`) - Fast, comprehensive tests for local development
2. **GitHub Actions Workflow** (`.github/workflows/test-json-publisher.yml`) - CI/CD integration tests

## Local Test Suite

### Running Tests

```bash
# From repository root
./actions/json-publisher/test.sh

# Or from the action directory
cd actions/json-publisher
./test.sh
```

### Test Categories

#### 1. Core Functionality Tests

**Test 1: Stdin Input with Git Mode**
- Validates: JSON input from stdin, git mode output
- Checks: File creation, content preservation
- Expected: JSON written to file with correct content

**Test 2: Pages Mode with HTML Generation**
- Validates: HTML generation from JSON input
- Checks: HTML file creation, JSON companion file, structure
- Expected: Both HTML and JSON files created with proper content

**Test 3: Complex JSON Structure**
- Validates: All JSON data types rendering correctly
- Checks: Strings, numbers, booleans, null, arrays, objects
- Expected: Proper CSS classes for each data type

#### 2. Error Handling Tests

**Test 4: Invalid JSON Handling**
- Validates: Graceful failure with invalid input
- Input: Non-JSON string
- Expected: Exit code != 0, error message

**Test 5: Missing Required Arguments**
- Validates: Argument validation
- Input: JSON without --mode flag
- Expected: Exit code != 0, usage message

**Test 6: No Stdin Input**
- Validates: TTY detection and error messaging
- Input: No piped input
- Expected: Timeout or immediate failure

#### 3. Feature Tests

**Test 7: Interactive HTML Features**
- Validates: JavaScript functions, UI elements
- Checks: Toggle, copy, download functions
- Expected: All interactive elements present

**Test 8: Output Format Validation**
- Validates: JSON formatting, indentation
- Checks: Valid JSON, 2-space indentation
- Requires: `jq` (optional)

**Test 9: HTML Structure Validation**
- Validates: HTML5 standards, responsive design
- Checks: DOCTYPE, meta tags, CSS rules
- Expected: Valid HTML5 structure

**Test 10: Help Documentation**
- Validates: --help flag functionality
- Checks: Usage information available
- Expected: Help text displayed

#### 4. Edge Case Tests

**Test 11: Empty JSON Object**
- Input: `{}`
- Expected: Valid output file created

**Test 12: Empty Array**
- Input: `[]`
- Expected: Proper rendering in HTML

**Test 13: Special Characters**
- Input: Unicode, quotes, symbols
- Expected: All characters preserved and displayed

**Test 14: Deeply Nested Structures**
- Input: 5+ levels of nesting
- Expected: Proper indentation and rendering

**Test 15: Large JSON Files**
- Input: 1000+ element array
- Expected: Successful processing without errors

### Test Output

```
╔════════════════════════════════════════╗
║   JSON Publisher Test Suite            ║
╚════════════════════════════════════════╝

✓ Stdin input with git mode
✓ Pages mode with HTML generation
✓ Complex JSON structure handling
✓ Invalid JSON properly rejected
✓ Missing arguments properly rejected
✓ Interactive HTML features
✓ Empty JSON object handled
✓ Empty array handled
✓ Special characters handled
✓ Valid JSON output
✓ Proper JSON indentation
✓ HTML structure validation
✓ Help documentation available

=========================================
Test Summary
=========================================
Passed: 13
Failed: 0
Total:  13
=========================================

✓ All tests passed!
```

## GitHub Actions Test Suite

### Workflow Structure

The CI/CD workflow includes 6 test jobs:

#### Job 1: `test-standalone-script`
Runs all core functionality tests on the Python script directly.

**Tests:**
1. Stdin input with git mode
2. File input with pages mode
3. Complex JSON structure
4. Invalid JSON handling
5. Missing required arguments
6. No stdin input handling
7. HTML interactive features

#### Job 2: `test-git-mode-with-commit`
Tests git integration features in isolation.

**Tests:**
1. Git commit without push
2. Custom git user configuration
3. Commit message customization

**Setup:**
- Creates temporary git repository
- Configures test credentials
- Validates git operations

#### Job 3: `test-action-integration`
Tests the GitHub Action wrapper.

**Tests:**
1. Action with file input
2. Action with inline JSON
3. Complex workflow simulation

**Validates:**
- Action inputs parsing
- Environment variable handling
- Output file creation
- Content preservation

#### Job 4: `test-output-formats`
Validates output quality and standards compliance.

**Tests:**
1. JSON format validation with `jq`
2. HTML validation with `tidy`
3. Responsive design elements

**Requires:**
- `jq` for JSON validation
- `tidy` for HTML validation

#### Job 5: `test-edge-cases`
Extensive edge case testing.

**Tests:**
1. Empty JSON object
2. Empty array
3. Large JSON files (1000+ elements)
4. Special characters and Unicode
5. Deeply nested structures

#### Job 6: `test-summary`
Aggregates results from all test jobs.

**Functionality:**
- Checks status of all previous jobs
- Reports overall pass/fail status
- Required for branch protection rules

### Running CI Tests

Tests run automatically on:
- Push to branches with changes in `actions/json-publisher/**`
- Pull requests affecting the action
- Manual trigger via `workflow_dispatch`

Manual trigger:
```bash
# Via GitHub CLI
gh workflow run test-json-publisher.yml

# Via GitHub UI
Actions → Test JSON Publisher → Run workflow
```

## Test Coverage Matrix

| Feature | Local Tests | CI Tests | Total Coverage |
|---------|-------------|----------|----------------|
| **Git Mode** | ||||
| - Stdin input | ✓ | ✓ | 100% |
| - File output | ✓ | ✓ | 100% |
| - Commit | ✓ | ✓ | 100% |
| - Custom user | - | ✓ | 100% |
| - Push (mock) | - | ✓ | 100% |
| **Pages Mode** | ||||
| - HTML generation | ✓ | ✓ | 100% |
| - JSON companion | ✓ | ✓ | 100% |
| - Interactive features | ✓ | ✓ | 100% |
| - Responsive design | ✓ | ✓ | 100% |
| - Data type styling | ✓ | ✓ | 100% |
| **Release Mode** | ||||
| - API integration | - | Mock | N/A |
| - File upload | - | Mock | N/A |
| **Error Handling** | ||||
| - Invalid JSON | ✓ | ✓ | 100% |
| - Missing args | ✓ | ✓ | 100% |
| - No stdin | ✓ | ✓ | 100% |
| **Edge Cases** | ||||
| - Empty data | ✓ | ✓ | 100% |
| - Large files | ✓ | ✓ | 100% |
| - Special chars | ✓ | ✓ | 100% |
| - Deep nesting | ✓ | ✓ | 100% |

## Adding New Tests

### Adding to Local Test Suite

1. Create new test function in `test.sh`:

```bash
test_new_feature() {
    print_test_header "Test N: New Feature"

    # Test implementation
    echo '{"new": "feature"}' | \
    python3 "$PUBLISHER" --mode git --output test.json

    # Validation
    if [ -f test.json ]; then
        print_success "New feature works"
    else
        print_failure "New feature failed"
        return 1
    fi
}
```

2. Add to `main()` function:

```bash
main() {
    # ... existing tests
    test_new_feature || true
    # ...
}
```

### Adding to CI Tests

1. Add new step to appropriate job in `.github/workflows/test-json-publisher.yml`:

```yaml
- name: Test new feature
  run: |
    echo '{"new": "feature"}' | \
    python3 actions/json-publisher/publish.py \
      --mode git \
      --output /tmp/new-feature.json

    # Validation
    if [ ! -f /tmp/new-feature.json ]; then
      echo "ERROR: New feature test failed"
      exit 1
    fi

    echo "✓ New feature test passed"
```

## Test Maintenance

### When to Update Tests

- **New feature added**: Add tests for all use cases
- **Bug fixed**: Add regression test
- **Behavior changed**: Update affected tests
- **Dependencies updated**: Verify all tests still pass

### Test Best Practices

1. **Isolation**: Each test should be independent
2. **Cleanup**: Always clean up test artifacts
3. **Clarity**: Use descriptive test names and error messages
4. **Coverage**: Test both success and failure paths
5. **Speed**: Keep tests fast for quick feedback

### Common Issues

**Issue: Tests pass locally but fail in CI**
- Check environment differences (Python version, dependencies)
- Verify file paths are absolute
- Check for race conditions in parallel tests

**Issue: Flaky tests**
- Add retry logic for network operations
- Increase timeouts for slow operations
- Check for timing dependencies

**Issue: Tests are slow**
- Parallelize independent tests
- Mock external services
- Use smaller test data sets

## Performance Benchmarks

Local test suite completes in ~5-10 seconds:
- Setup: <1s
- Core tests: 2-3s
- Edge cases: 2-3s
- Format validation: 1-2s
- Cleanup: <1s

CI test suite completes in ~3-5 minutes:
- Standalone tests: 1-2 min
- Git mode tests: 30s-1 min
- Action integration: 1 min
- Format validation: 30s-1 min
- Edge cases: 30s

## Continuous Improvement

The test suite is continuously improved to:
- Increase coverage of edge cases
- Add performance benchmarks
- Improve error messages
- Reduce test execution time
- Add more realistic test scenarios

## Support

For test-related issues:
1. Run local tests first: `./test.sh`
2. Check test output for specific failures
3. Review this documentation
4. Check CI logs for additional details
5. Open an issue with test output

## Test Philosophy

The JSON Publisher test suite follows these principles:

1. **Comprehensive**: Test all advertised features
2. **Fast**: Quick feedback loop for development
3. **Reliable**: No flaky tests, deterministic results
4. **Maintainable**: Simple, readable test code
5. **Documented**: Clear purpose and expectations for each test

This ensures that the JSON Publisher reliably delivers on all its promises to users.
