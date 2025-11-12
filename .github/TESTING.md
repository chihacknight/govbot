# Testing GitHub Actions Workflows

This guide explains how to test the GitHub Actions workflows locally using `act`.

## Quick Start

### 1. Prerequisites

```bash
# Install act
brew install act

# Start Docker Desktop (required for act)
# Open Docker Desktop application
```

### 2. Validate Workflows (No Docker Required)

```bash
# Validate all workflows
./.github/scripts/validate-workflows.sh

# This checks YAML syntax and basic workflow structure
```

### 3. Test Workflows with act

#### Interactive Mode
```bash
./.github/scripts/test-workflows.sh
```

#### Command Line Mode
```bash
# List all workflows
./.github/scripts/test-workflows.sh list

# Validate a specific workflow
./.github/scripts/test-workflows.sh validate test-sources-recent-items.yml

# Run a workflow
./.github/scripts/test-workflows.sh run test-sources-recent-items.yml
```

#### Direct act Usage
```bash
# List jobs in a workflow
act workflow_dispatch -W .github/workflows/test-sources-recent-items.yml --list

# Run a workflow (dry-run)
act workflow_dispatch -W .github/workflows/test-sources-recent-items.yml --dryrun

# Run a workflow
act workflow_dispatch \
  -W .github/workflows/test-sources-recent-items.yml \
  --secret GITHUB_TOKEN=your_token_here \
  --container-architecture linux/amd64
```

## Available Test Workflows

### 1. test-sources-recent-items.yml
Tests the `sources` and `recent-items` actions together.

```bash
act workflow_dispatch \
  -W .github/workflows/test-sources-recent-items.yml \
  --secret GITHUB_TOKEN=$GITHUB_TOKEN \
  --container-architecture linux/amd64
```

### 2. test-scrape-action.yml
Tests the `scrape` action. Requires Docker for the OpenStates scraper.

```bash
act workflow_dispatch \
  -W .github/workflows/test-scrape-action.yml \
  --input state=id \
  --input use-scrape-cache=false \
  --secret GITHUB_TOKEN=$GITHUB_TOKEN \
  --container-architecture linux/amd64
```

### 3. test-format-action.yml
Tests the `format` action. Requires a scrape artifact.

```bash
# First, ensure you have a scrape artifact available
act workflow_dispatch \
  -W .github/workflows/test-format-action.yml \
  --input state=id \
  --secret GITHUB_TOKEN=$GITHUB_TOKEN \
  --container-architecture linux/amd64
```

### 4. test-extract-action.yml
Tests the `extract` action. Requires formatted data.

```bash
act workflow_dispatch \
  -W .github/workflows/test-extract-action.yml \
  --input state=id \
  --secret GITHUB_TOKEN=$GITHUB_TOKEN \
  --container-architecture linux/amd64
```

### 5. test-all-actions.yml
Tests all actions in sequence.

```bash
act workflow_dispatch \
  -W .github/workflows/test-all-actions.yml \
  --input state=id \
  --input test-sources=true \
  --input test-scrape=true \
  --input test-format=true \
  --input test-extract=false \
  --input test-recent-items=true \
  --secret GITHUB_TOKEN=$GITHUB_TOKEN \
  --container-architecture linux/amd64
```

## Setting Up Secrets

For workflows that need GitHub authentication:

```bash
# Option 1: Environment variable
export GITHUB_TOKEN=ghp_your_token_here

# Option 2: Pass directly to act
act workflow_dispatch \
  -W .github/workflows/test-sources-recent-items.yml \
  --secret GITHUB_TOKEN=ghp_your_token_here
```

## Common Issues

### Docker Not Running
```
Error: Cannot connect to the Docker daemon
```
**Solution**: Start Docker Desktop

### Architecture Issues (Apple Silicon)
The test scripts automatically use `--container-architecture linux/amd64` to avoid architecture issues on Apple Silicon Macs.

### Workflow Fails with "Action not found"
Make sure you're running from the repository root and using relative paths (`./actions/...`) in the workflows.

### Authentication Errors
- Ensure `GITHUB_TOKEN` is set correctly
- For private repositories, use a Personal Access Token with appropriate permissions

## Tips

1. **Start Simple**: Test `test-sources-recent-items.yml` first as it's the simplest
2. **Use Dry Run**: Test with `--dryrun` first to validate without executing
3. **Check Logs**: Logs are saved to `/tmp/act-<workflow-name>.log`
4. **Verbose Mode**: Add `--verbose` to see detailed output
5. **Specific Jobs**: Use `-j <job-name>` to run only specific jobs

## Example: Full Test Run

```bash
# 1. Validate all workflows
./.github/scripts/validate-workflows.sh

# 2. Test sources + recent-items (simplest)
./.github/scripts/test-workflows.sh run test-sources-recent-items.yml

# 3. If successful, test other workflows
./.github/scripts/test-workflows.sh run test-scrape-action.yml
```

## Notes

- Some workflows may take a long time (especially `scrape` which runs Docker containers)
- The `scrape` action requires Docker and will pull the OpenStates scraper image
- Test artifacts are uploaded to `/tmp/` during local testing
- Workflows use local action paths (`./actions/...`) for testing within the same repo

