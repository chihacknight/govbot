# JSON Publisher

[![Tests](https://github.com/windy-civi/toolkit/actions/workflows/test-json-publisher.yml/badge.svg)](https://github.com/windy-civi/toolkit/actions/workflows/test-json-publisher.yml)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A flexible GitHub Action and standalone tool for publishing JSON reports from CI/CD pipelines to multiple destinations.

**📋 [Testing Documentation](TESTING.md)** | **🔧 [Examples](examples/)** | **📖 [Action Metadata](action.yml)**

## Features

- **Zero Dependencies**: Uses only Python standard library
- **Multiple Publishing Modes**:
  - **Git**: Commit JSON files directly to your repository
  - **GitHub Releases**: Attach JSON as release artifacts
  - **GitHub Pages**: Transform JSON into beautiful HTML reports
- **Flexible Input**: Accepts JSON from stdin for easy pipeline integration
- **Auto-Retry**: Built-in retry logic for network operations
- **Customizable HTML**: Default template for JSON visualization (extensible)

## Publishing Modes

### 1. Git Mode
Publishes JSON as a file in your repository.

**Use cases:**
- Track report history over time
- Version control for test results
- Easy diff viewing in pull requests

### 2. Release Mode
Attaches JSON as an artifact to a GitHub Release.

**Use cases:**
- Archive reports for specific versions
- Download reports from release pages
- Keep artifacts separate from repository history

### 3. Pages Mode
Converts JSON to HTML and publishes to GitHub Pages.

**Use cases:**
- Human-readable reports
- Shareable dashboard URLs
- No technical knowledge required to view

## Usage

### As a Standalone Script

```bash
# Install (no dependencies needed, just Python 3.7+)
chmod +x actions/json-publisher/publish.py

# Publish to git file
cat report.json | python3 actions/json-publisher/publish.py \
  --mode git \
  --output results/report.json \
  --commit \
  --push

# Publish to GitHub Release
cat report.json | python3 actions/json-publisher/publish.py \
  --mode release \
  --tag v1.0.0 \
  --output report.json \
  --github-token $GITHUB_TOKEN \
  --repo owner/repo

# Publish to GitHub Pages
cat report.json | python3 actions/json-publisher/publish.py \
  --mode pages \
  --output index.html \
  --commit \
  --push \
  --branch gh-pages
```

### As a GitHub Action

#### Example 1: Publish Test Results to Git

```yaml
name: Run Tests and Publish Results

on: [push]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run tests
        run: |
          npm test -- --json > test-results.json

      - name: Publish test results
        uses: ./actions/json-publisher
        with:
          mode: git
          json-input: test-results.json
          output: reports/test-results.json
          commit: true
          push: true
          commit-message: "Update test results [skip ci]"
```

#### Example 2: Publish Coverage to GitHub Release

```yaml
name: Coverage Report

on:
  release:
    types: [created]

jobs:
  coverage:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Generate coverage
        run: |
          npm run coverage -- --json > coverage.json

      - name: Publish to release
        uses: ./actions/json-publisher
        with:
          mode: release
          json-input: coverage.json
          output: coverage-report.json
          tag: ${{ github.event.release.tag_name }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

#### Example 3: Publish Dashboard to GitHub Pages

```yaml
name: Publish Dashboard

on:
  schedule:
    - cron: '0 0 * * *'  # Daily
  workflow_dispatch:

jobs:
  dashboard:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          ref: gh-pages

      - name: Generate metrics
        run: |
          # Your metrics collection script
          ./scripts/collect-metrics.sh > metrics.json

      - name: Publish to GitHub Pages
        uses: ./actions/json-publisher
        with:
          mode: pages
          json-input: metrics.json
          output: index.html
          commit: true
          push: true
          branch: gh-pages
          commit-message: "Update dashboard"
```

#### Example 4: Multi-format Publishing

```yaml
name: Comprehensive Report

on: [push]

jobs:
  report:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4

      - name: Generate report
        run: |
          echo '{"status": "success", "coverage": 95}' > report.json

      # Publish to repository
      - name: Save to repo
        uses: ./actions/json-publisher
        with:
          mode: git
          json-input: report.json
          output: reports/latest.json
          commit: true
          push: true

      # Also publish HTML version
      - name: Publish HTML
        uses: ./actions/json-publisher
        with:
          mode: pages
          json-input: report.json
          output: docs/report.html
          commit: true
          push: true
```

## Command Line Options

### Required
- `--mode`: Publishing mode (`git`, `release`, or `pages`)

### Output
- `--output`, `-o`: Output file path
  - Default: `report.json` (git/release), `index.html` (pages)

### Git Options
- `--commit`: Commit changes to git
- `--push`: Push changes to remote (requires `--commit`)
- `--branch`: Git branch to use
  - Default: current branch (git mode), `gh-pages` (pages mode)
- `--commit-message`: Custom commit message
- `--git-user`: Git user name (default: `github-actions[bot]`)
- `--git-email`: Git user email

### GitHub Options
- `--github-token`: GitHub token (or use `GITHUB_TOKEN` env var)
- `--repo`: Repository in format `owner/repo` (or use `GITHUB_REPOSITORY` env var)
- `--tag`: Release tag (required for release mode)

## Action Inputs

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `mode` | Publishing mode: git, release, or pages | Yes | - |
| `json-input` | JSON string or file path | Yes | - |
| `output` | Output file path | No | mode-dependent |
| `commit` | Commit changes | No | `false` |
| `push` | Push to remote | No | `false` |
| `branch` | Git branch | No | mode-dependent |
| `commit-message` | Commit message | No | auto-generated |
| `tag` | Release tag | No (required for release mode) | - |
| `github-token` | GitHub token | No | `${{ github.token }}` |
| `repo` | Repository | No | `${{ github.repository }}` |
| `git-user` | Git user name | No | `github-actions[bot]` |
| `git-email` | Git user email | No | `github-actions[bot]@users.noreply.github.com` |

## HTML Template Features

When using `pages` mode, JSON is transformed into an interactive HTML page with:

- **Clean, modern design** with responsive layout
- **Syntax highlighting** for different JSON data types
- **Color coding**: strings (green), numbers (blue), booleans (purple), null (gray)
- **Interactive features**:
  - Toggle raw JSON view
  - Copy JSON to clipboard
  - Download raw JSON file
- **Nested structure** visualization with proper indentation

## Permissions

Depending on the mode, ensure your GitHub Actions workflow has appropriate permissions:

```yaml
permissions:
  contents: write  # For git and pages modes
  # No special permissions needed for release mode with default token
```

## Requirements

- Python 3.7 or higher
- Git (for git and pages modes)
- GitHub token with appropriate permissions (for release mode)

## Examples Directory Structure

```
your-repo/
├── .github/
│   └── workflows/
│       └── report.yml
├── actions/
│   └── json-publisher/
│       ├── action.yml
│       ├── publish.py
│       ├── requirements.txt
│       └── README.md
└── reports/
    ├── latest.json
    └── archive/
```

## Troubleshooting

### JSON Input Issues
- Ensure valid JSON format
- Check that stdin is properly piped
- Verify file path if using file input

### Git Push Issues
- Check branch permissions
- Verify token has `contents: write` permission
- Review branch protection rules

### Release Issues
- Ensure tag exists or will be created
- Verify token has release permissions
- Check repository name format (`owner/repo`)

### Pages Issues
- Ensure GitHub Pages is enabled in repository settings
- Check that gh-pages branch exists
- Verify pages deployment settings

## Testing

Comprehensive tests ensure all features work as advertised.

### Run Tests Locally

```bash
# Run the complete test suite
./actions/json-publisher/test.sh
```

The test script validates:
- ✓ Stdin input handling
- ✓ All three publishing modes (git, release, pages)
- ✓ HTML generation with proper formatting
- ✓ JSON output format and indentation
- ✓ Error handling (invalid JSON, missing args)
- ✓ Edge cases (empty objects, special characters, nested structures)
- ✓ Interactive HTML features (toggle, copy, download)
- ✓ Responsive design elements

### CI/CD Testing

Automated tests run on every push via GitHub Actions:

```yaml
# .github/workflows/test-json-publisher.yml
```

Test jobs include:
1. **Standalone Script Tests** - Core functionality validation
2. **Git Mode Tests** - Commit and configuration testing
3. **Action Integration Tests** - GitHub Action wrapper validation
4. **Output Format Tests** - JSON and HTML structure validation
5. **Edge Case Tests** - Special scenarios and error conditions

### Test Coverage

| Feature | Tests | Status |
|---------|-------|--------|
| Git Mode | 5 tests | ✓ Passing |
| Release Mode | 3 tests | ✓ Passing |
| Pages Mode | 7 tests | ✓ Passing |
| Error Handling | 4 tests | ✓ Passing |
| HTML Generation | 6 tests | ✓ Passing |
| Edge Cases | 8 tests | ✓ Passing |

**Total: 33+ automated tests**

### Manual Testing

Test individual features:

```bash
# Test git mode
echo '{"test": "manual"}' | python3 publish.py --mode git --output test.json

# Test pages mode
echo '{"test": "manual"}' | python3 publish.py --mode pages --output test.html

# View generated HTML
open test.html  # macOS
xdg-open test.html  # Linux
```

## Contributing

This tool is designed to be maintenance-free and easily extensible:

1. **Add new HTML templates**: Modify `_generate_html()` method
2. **Add new publishing modes**: Add new method and update parser
3. **Customize styling**: Edit CSS in HTML template
4. **Run tests before committing**: Always run `./test.sh` to ensure changes don't break existing features

## License

This project is part of the toolkit repository.
