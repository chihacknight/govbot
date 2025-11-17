# Testing GitHub Actions Locally

This directory contains scripts to help test GitHub Actions workflows locally using [act](https://github.com/nektos/act).

## Prerequisites

1. **Install act**: `brew install act`
2. **Start Docker Desktop**: `act` requires Docker to run workflows

## Quick Start

### Interactive Mode

Run the test script without arguments for an interactive menu:

```bash
./.github/scripts/test-workflows.sh
```

### Command Line Mode

#### List all workflows
```bash
./.github/scripts/test-workflows.sh list
```

#### Validate workflow syntax
```bash
# Validate all workflows
./.github/scripts/test-workflows.sh validate

# Validate a specific workflow
./.github/scripts/test-workflows.sh validate test-sources-recent-items.yml
```

#### Run a workflow
```bash
./.github/scripts/test-workflows.sh run test-sources-recent-items.yml
```

## Setting GITHUB_TOKEN

For workflows that require authentication, set the `GITHUB_TOKEN` environment variable:

```bash
export GITHUB_TOKEN=your_token_here
./.github/scripts/test-workflows.sh run test-sources-recent-items.yml
```

If not set, the script will use a dummy token (which may cause some steps to fail).

## Available Test Workflows

- `test-sources-recent-items.yml` - Tests sources and recent-items actions
- `test-scrape-action.yml` - Tests the scrape action
- `test-format-action.yml` - Tests the format action
- `test-extract-action.yml` - Tests the extract action
- `test-all-actions.yml` - Tests all actions in sequence

## Notes

- Some workflows may require Docker images or external dependencies
- The `scrape` action requires Docker to run the OpenStates scraper
- Workflows are tested with `linux/amd64` architecture by default (required for Apple Silicon Macs)
- Test logs are saved to `/tmp/act-<workflow-name>.log`

## Troubleshooting

### Docker not running
```
Error: Cannot connect to the Docker daemon
```
**Solution**: Start Docker Desktop

### Architecture issues on Apple Silicon
If you encounter architecture-related errors, the script automatically uses `--container-architecture linux/amd64`.

### Workflow fails with authentication errors
Make sure to set `GITHUB_TOKEN` if the workflow needs to access GitHub APIs or clone private repositories.

