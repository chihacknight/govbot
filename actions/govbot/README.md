# govbot

`govbot` enables distributed data anaylsis of government updates via a friendly terminal interface. Git repos function as datasets, including the legislation of all 47 states/jurisdictions.

## 1 Line Install

```bash
sh -c "$(curl -fsSL https://raw.githubusercontent.com/windy-civi/toolkit/main/actions/govbot/scripts/install-nightly.sh)"
```

```bash
govbot # to see help
govbot clone # to show
govbot clone {{repo}} {{repo}} # to download specific items
govbot delete {{locale}} # to delete specific items
govbot delete all # to delete everything
govbot load # load bill metadata into DuckDB database
```

## Contribute

This is Rust land, & it uses `just`. `just setup` to start, and then `just govbot ...` to develop the cli.

### Prerequisites

1. **Rust & Cargo**: Install the [Rust Toolchain](https://rustup.rs/)
2. **Just**: Install the task runner: `cargo install just`

### Development Workflow

Use `just govbot ...` as your cli "dev" environment.

### Other Useful Commands

- `just` - See all available tasks
- `just test` - Run all tests
- `just review` - Review snapshot test changes
- `just mocks [LOCALES...]` - Update mock data for testing

We build snapshots off `examples`. Add examples to make a test.

## Advanced

```bash
GOVBOT_REPO_URL_TEMPLATE="https://gitsite.com/org/{locale}.git" govbot ...
```

## Working with Logs

The `govbot logs` command outputs JSON Lines (JSONL) format, making it easy to pipe to tools like `jq`, `yq`, and `jl` for filtering, transformation, and pretty-printing, and even sending to AI CLI tools like `claude`.

### Basic Usage

```bash
# Easiest way with smart defaults
govbot logs

# Get more args and their help
govbot logs --help
```

### modular CLI Examples

#### Output as YAML with `yq`

Convert JSON Lines to prettified YAML:

```bash
# Output prettified yaml
just govbot logs | yq -p=json -o=yaml '.'

# Multiple documents (separated by ---)
govbot logs --repos="il" --limit=10 --filter=default | yq -p json -P
```

#### Filtering with `jq`

Filter and transform JSON Lines:

```bash
# Filter by specific fields
govbot logs| jq 'select(.log.action.classification[] == "passage")'

# Extract specific fields
govbot logs | jq '{bill_id: .log.bill_id, date: .log.action.date, description: .log.action.description}'

# Count by bill
govbot logs | jq -s 'group_by(.log.bill_id) | map({bill_id: .[0].log.bill_id, count: length})'

# Filter by date range
govbot logs | jq 'select(.timestamp >= "20250301" and .timestamp <= "20250331")'
```

#### Using `jl` (JSON Lines processor)

`jl` is specifically designed for JSON Lines:

```bash
# Pretty print JSON Lines
govbot logs | jl

# Filter with jl
govbot logs | jl 'select(.log.action.classification[] == "passage")'
```

### Combining Tools

Chain multiple tools for powerful data processing:

```bash
# Filter with jq, then convert to YAML
govbot logs --repos="il" --limit=100 | \
  jq 'select(.log.action.classification[] == "passage")' | \
  yq -p json -P

# Extract and format specific fields, then output as YAML
govbot logs --repos="il" --limit=10 | \
  jq '{bill: .log.bill_id, action: .log.action.description, date: .log.action.date}' | \
  yq -p json -P

# Aggregate data with jq, then format as YAML array
govbot logs --repos="il" --limit=100 | \
  jq -s 'group_by(.log.bill_id) | map({bill_id: .[0].log.bill_id, actions: length})' | \
  yq -P
```

### Advanced Examples

```bash
# Find all bills with multiple actions in a single day
govbot logs --repos="il" --limit=1000 | \
  jq -s 'group_by(.log.bill_id + .timestamp) | map(select(length > 1)) | flatten'

# Extract action classifications and count them
govbot logs --repos="il" --limit=1000 | \
  jq -r '.log.action.classification[]?' | \
  sort | uniq -c | sort -rn

# Join with bill metadata and filter by title
govbot logs --repos="il" --limit=10 --join=bill | \
  jq 'select(.bill.title | contains("Education"))' | \
  yq -p json -P
```

## Tagging Bills

Tag legislative logs using semantic similarity matching. See [TAGGING.md](./TAGGING.md) for detailed setup instructions.

**Quick start** (with `tags.toml`, `model.onnx`, and `tokenizer.json` in current directory):

```bash
just govbot logs --repos il --limit 10 | just govbot tag
```

## Using DuckDB

Query the cloned repos with DuckDB! See [DUCKDB.md](./DUCKDB.md) for detailed examples.

### Quick Start (Command Line)

```sql
-- Load JSON extension
INSTALL json;
LOAD json;

-- Query all bill metadata
SELECT *
FROM read_json_auto('~/.govbot/repos/**/bills/*/metadata.json')
LIMIT 10;
```

### Using DuckDB UI

Load data into a database file and open in the web UI:

```bash
# Load all data into a database (default: govbot.duckdb)
govbot load

# Or specify a custom database file
govbot load --database my-bills.duckdb

# With memory limit and thread settings
govbot load --memory-limit 32GB --threads 8

# Open in DuckDB UI (opens in your browser)
duckdb --ui govbot.duckdb
```

### Helper Scripts

```bash
# Run example queries
./duckdb-query.sh examples/duckdb-example.sql
```
