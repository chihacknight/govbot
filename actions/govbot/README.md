# govbot

`govbot` enables distributed data analysis of government updates via a friendly terminal interface. Git repos function as datasets, including the legislation of all 47 states/jurisdictions.

## Quick Start

### 1. Install

```bash
sh -c "$(curl -fsSL https://raw.githubusercontent.com/chihacknight/govbot/main/actions/govbot/scripts/install-nightly.sh)"
```

### 2. Run govbot

```bash
govbot
```

That's it. If no `govbot.yml` exists, an interactive wizard walks you through setup:

1. **Datasets** - Choose all 47 states or pick specific ones
2. **Classification** - Point the manifest at a fastclass classifier bundle
3. **Publishing** - An RSS feed publisher configured automatically

The wizard creates `govbot.yml` (a project manifest: `datasets` / `transforms` /
`publish` / `pipelines`), `.gitignore`, and a GitHub Actions workflow.

### 3. Run the pipeline

```bash
govbot
```

With `govbot.yml` present, running `govbot` executes the full pipeline:

1. Pulls/updates legislation datasets (smart: only clones on first run, pulls after)
2. Classifies bills with fastclass and applies the results into the dataset
3. Runs the manifest's publishers (RSS feeds into the `docs/` directory)

### Other Commands

```bash
govbot pull all            # download all state legislation datasets
govbot pull il ca ny       # download specific states
govbot source              # stream legislative activity as JSON Lines
govbot source --select docs | fastclass classify - classifier=./classifier | govbot apply
govbot publish             # run the manifest's publishers (RSS / HTML / JSON / DuckDB)
govbot run                 # run the full pipeline
govbot load                # load bill metadata into DuckDB
govbot delete all          # remove all downloaded data
govbot update              # update govbot to latest version
govbot --help              # see all commands and options
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

Datasets are resolved at runtime through the **dataset registry** (see
[`REGISTRY.md`](./REGISTRY.md)). To point govbot at a custom registry:

```bash
# An http(s):// URL or a local file path.
GOVBOT_REGISTRY_URL="https://example.com/registry.json" govbot pull all
```

A project-local `.govbot/registry.json` is also honored. `govbot search`
queries the registry; `govbot pull` clones datasets once into the shared
`~/.govbot/cache/` and pins resolved commits in `govbot.lock`.

## Working with the Record Stream

The `govbot source` command outputs JSON Lines (JSONL) format, making it easy to pipe to tools like `jq`, `yq`, and `jl` for filtering, transformation, and pretty-printing, and even sending to AI CLI tools like `claude`.

### Basic Usage

```bash
# Easiest way with smart defaults
govbot source

# Get more args and their help
govbot source --help
```

### modular CLI Examples

#### Output as YAML with `yq`

Convert JSON Lines to prettified YAML:

```bash
# Output prettified yaml
just govbot source | yq -p=json -o=yaml '.'

# Multiple documents (separated by ---)
govbot source --repos="il" --limit=10 --filter=default | yq -p json -P
```

#### Filtering with `jq`

Filter and transform JSON Lines:

```bash
# Filter by specific fields
govbot source| jq 'select(.log.action.classification[] == "passage")'

# Extract specific fields
govbot source | jq '{bill_id: .log.bill_id, date: .log.action.date, description: .log.action.description}'

# Count by bill
govbot source | jq -s 'group_by(.log.bill_id) | map({bill_id: .[0].log.bill_id, count: length})'

# Filter by date range
govbot source | jq 'select(.timestamp >= "20250301" and .timestamp <= "20250331")'
```

#### Using `jl` (JSON Lines processor)

`jl` is specifically designed for JSON Lines:

```bash
# Pretty print JSON Lines
govbot source | jl

# Filter with jl
govbot source | jl 'select(.log.action.classification[] == "passage")'
```

### Combining Tools

Chain multiple tools for powerful data processing:

```bash
# Filter with jq, then convert to YAML
govbot source --repos="il" --limit=100 | \
  jq 'select(.log.action.classification[] == "passage")' | \
  yq -p json -P

# Extract and format specific fields, then output as YAML
govbot source --repos="il" --limit=10 | \
  jq '{bill: .log.bill_id, action: .log.action.description, date: .log.action.date}' | \
  yq -p json -P

# Aggregate data with jq, then format as YAML array
govbot source --repos="il" --limit=100 | \
  jq -s 'group_by(.log.bill_id) | map({bill_id: .[0].log.bill_id, actions: length})' | \
  yq -P
```

### Advanced Examples

```bash
# Find all bills with multiple actions in a single day
govbot source --repos="il" --limit=1000 | \
  jq -s 'group_by(.log.bill_id + .timestamp) | map(select(length > 1)) | flatten'

# Extract action classifications and count them
govbot source --repos="il" --limit=1000 | \
  jq -r '.log.action.classification[]?' | \
  sort | uniq -c | sort -rn

# Join with bill metadata and filter by title
govbot source --repos="il" --limit=10 --join=bill | \
  jq 'select(.bill.title | contains("Education"))' | \
  yq -p json -P
```

## Generating RSS Feeds

Generate RSS feeds using the `govbot publish` command, which reads from `govbot.yml` configuration.

**Note:** The Python scripts have been replaced by a Rust implementation. Use `govbot publish` instead.

## Publishing

Publishers consume the classified result stream and emit artifacts. RSS, HTML,
JSON, and DuckDB are built-in publishers, declared in the manifest's `publish:`
map.

### Quick Start

1. **Configure `govbot.yml`** with your datasets, transforms, and publishers.
   The tag taxonomy is NOT in `govbot.yml` — it lives in a separate fastclass
   classifier bundle that `transforms.classify.classifier` references by path:

   ```yaml
   datasets:
     - all
   transforms:
     classify:
       command: [fastclass, classify, "-"]
       reads: docs
       writes: classification
       classifier: ./classifier
   publish:
     lgbtq-feed:
       type: rss
       select: [lgbtq]                 # tag names from the classifier bundle
       base_url: "https://yourusername.github.io/repo-name"
       output_dir: "feeds"
   pipelines:
     default:
       - classify
       - lgbtq-feed
   ```

2. **Run all publishers:**

   ```bash
   govbot publish
   ```

3. **Run a specific publisher:**

   ```bash
   govbot publish --publisher lgbtq-feed
   ```

4. **Customize output:**

   ```bash
   govbot publish --output-dir ./feeds --limit 100
   ```

### Publisher configuration

Each entry in `publish:` declares a `type` (`rss` / `html` / `json` / `duckdb`)
plus type-specific keys:

- `select`: tag names to include — only records carrying one of these tags are
  published. Tag names must exist in the classifier bundle.
- `base_url`: base URL for generated links (required for `rss`/`html`).
- `output_dir`: directory the publisher writes into (default: `docs`).
- `output_file`: the primary artifact filename.
- `title` / `description`: custom feed/index metadata.
- `limit`: maximum entries (`"none"` for unlimited).

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

### Learn More

See [DUCKDB.md](./DUCKDB.md) for comprehensive examples including:
- Working with JSON arrays and nested data
- Cross-state analysis queries
- Sponsor analysis
- Exporting to CSV/Parquet
- Performance optimization tips
