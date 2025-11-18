# Report Publisher

A GitHub Action that takes JSON from stdin and publishes it in multiple formats.

## What It Does

Takes JSON input from stdin and outputs it in one of three formats:

- **Git mode**: Saves JSON as a file in your repository
- **Release mode**: Attaches JSON as an artifact to a GitHub Release
- **Pages mode**: Converts JSON to HTML and publishes to GitHub Pages

## Usage

### As a GitHub Action

```yaml
- name: Publish JSON
  uses: ./actions/report-publisher
  with:
    mode: git
    json-input: report.json
    output: reports/latest.json
    commit: true
    push: true
```

### As a Standalone Script

```bash
cat report.json | python3 actions/report-publisher/publish.py \
  --mode git \
  --output results/report.json
```

## Inputs

| Input          | Description                                   | Required |
| -------------- | --------------------------------------------- | -------- |
| `mode`         | Publishing mode: `git`, `release`, or `pages` | Yes      |
| `json-input`   | JSON string or file path                      | Yes      |
| `output`       | Output file path                              | No       |
| `commit`       | Commit changes to git                         | No       |
| `push`         | Push changes to remote                        | No       |
| `branch`       | Git branch to use                             | No       |
| `tag`          | Release tag (required for release mode)       | No       |
| `github-token` | GitHub token for API operations               | No       |

See `action.yml` for the complete list of inputs.

## Testing

The `examples/` folder contains test cases. Each test generates output that can be compared against reference snapshots in `examples/test_snapshots/`. Run the tests with:

```bash
./actions/report-publisher/test.sh
```
