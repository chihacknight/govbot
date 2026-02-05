# DuckDB Integration

govbot can load bill metadata into a DuckDB database for powerful SQL-based analysis.

## Prerequisites

Install DuckDB CLI: https://duckdb.org/docs/installation/

```bash
# macOS
brew install duckdb

# Linux (Debian/Ubuntu)
wget https://github.com/duckdb/duckdb/releases/latest/download/duckdb_cli-linux-amd64.zip
unzip duckdb_cli-linux-amd64.zip
sudo mv duckdb /usr/local/bin/

# Verify installation
duckdb --version
```

## Quick Start

```bash
# 1. Clone repositories first
govbot clone all

# 2. Load into DuckDB
govbot load

# 3. Open in DuckDB UI (browser-based)
duckdb --ui ~/.govbot/govbot.duckdb

# Or query from command line
duckdb ~/.govbot/govbot.duckdb
```

## Command Options

```bash
govbot load [OPTIONS]

Options:
  --database <NAME>       Database filename (default: govbot.duckdb)
  --govbot-dir <PATH>     Custom govbot directory
  --memory-limit <SIZE>   Memory limit for DuckDB (default: 16GB)
  --threads <COUNT>       Number of threads (default: 4)
```

### Examples

```bash
# Load with defaults
govbot load

# Custom database name
govbot load --database my-analysis.duckdb

# Increase resources for large datasets
govbot load --memory-limit 32GB --threads 8

# Use custom data directory
govbot load --govbot-dir /path/to/.govbot
```

## Database Schema

### Tables

#### `bills`
Contains all bill metadata from `metadata.json` files.

| Column | Type | Description |
|--------|------|-------------|
| identifier | VARCHAR | Bill identifier (e.g., "HB0001") |
| title | VARCHAR | Bill title |
| legislative_session | VARCHAR | Session identifier (e.g., "2025") |
| classification | JSON | Bill classification array |
| subject | JSON | Subject matter tags |
| abstracts | JSON | Bill abstracts/summaries |
| actions | JSON | Array of legislative actions |
| sponsorships | JSON | Array of sponsors |
| versions | JSON | Array of bill versions/amendments |
| documents | JSON | Related documents |
| sources | JSON | Source URLs |
| jurisdiction | JSON | Jurisdiction info (state, name, etc.) |
| source_file | VARCHAR | Path to source metadata.json |

#### `bills_summary` (View)
A simplified view for common queries.

| Column | Type | Description |
|--------|------|-------------|
| identifier | VARCHAR | Bill identifier |
| title | VARCHAR | Bill title |
| legislative_session | VARCHAR | Session identifier |
| jurisdiction_id | VARCHAR | OCD jurisdiction ID |
| jurisdiction_name | VARCHAR | State/jurisdiction name |
| action_count | INTEGER | Number of actions on the bill |
| sponsor_count | INTEGER | Number of sponsors |
| source_file | VARCHAR | Path to source file |

## Example Queries

### Basic Queries

```sql
-- Count bills by state
SELECT
    jurisdiction->>'name' as state,
    COUNT(*) as bill_count
FROM bills
GROUP BY jurisdiction->>'name'
ORDER BY bill_count DESC;

-- Find bills by keyword in title
SELECT identifier, title, jurisdiction->>'name' as state
FROM bills
WHERE title ILIKE '%education%'
LIMIT 20;

-- Bills with the most actions
SELECT identifier, title, json_array_length(actions) as action_count
FROM bills
ORDER BY action_count DESC
LIMIT 10;
```

### Working with JSON Arrays

```sql
-- Unnest actions to analyze legislative activity
SELECT
    b.identifier,
    b.title,
    action->>'description' as action_description,
    action->>'date' as action_date,
    action->'classification' as classifications
FROM bills b,
     LATERAL unnest(from_json(b.actions, '["json"]')) as t(action)
WHERE action->>'description' ILIKE '%passed%'
LIMIT 20;

-- Count bills by classification type
SELECT
    classification,
    COUNT(DISTINCT identifier) as bill_count
FROM bills,
     LATERAL unnest(from_json(classification, '["varchar"]')) as t(classification)
GROUP BY classification
ORDER BY bill_count DESC;
```

### Sponsor Analysis

```sql
-- Top sponsors across all states
SELECT
    sponsor->>'name' as sponsor_name,
    sponsor->>'classification' as role,
    COUNT(*) as bills_sponsored
FROM bills,
     LATERAL unnest(from_json(sponsorships, '["json"]')) as t(sponsor)
WHERE sponsor->>'classification' = 'primary'
GROUP BY sponsor->>'name', sponsor->>'classification'
ORDER BY bills_sponsored DESC
LIMIT 20;
```

### Cross-State Analysis

```sql
-- Compare bill counts by session and state
SELECT
    jurisdiction->>'name' as state,
    legislative_session,
    COUNT(*) as bills
FROM bills
GROUP BY jurisdiction->>'name', legislative_session
ORDER BY state, legislative_session;

-- Find similar bill titles across states
SELECT
    a.jurisdiction->>'name' as state_a,
    b.jurisdiction->>'name' as state_b,
    a.identifier as bill_a,
    b.identifier as bill_b,
    a.title
FROM bills a
JOIN bills b ON a.title = b.title
    AND a.jurisdiction->>'name' < b.jurisdiction->>'name'
LIMIT 20;
```

### Export Results

```sql
-- Export to CSV
COPY (
    SELECT identifier, title, jurisdiction->>'name' as state
    FROM bills
    WHERE title ILIKE '%tax%'
) TO 'tax_bills.csv' (HEADER, DELIMITER ',');

-- Export to Parquet (efficient for large datasets)
COPY (SELECT * FROM bills) TO 'bills.parquet' (FORMAT PARQUET);

-- Export to JSON
COPY (
    SELECT identifier, title, actions
    FROM bills
    LIMIT 100
) TO 'bills_sample.json';
```

## Using with DuckDB UI

The DuckDB UI provides a browser-based interface for exploring data:

```bash
duckdb --ui ~/.govbot/govbot.duckdb
```

Features:
- Visual query builder
- Result visualization
- Schema explorer
- Query history

## Direct File Queries (Without `govbot load`)

You can query the JSON files directly without creating a database:

```sql
-- Start DuckDB
duckdb

-- Load JSON extension
INSTALL json;
LOAD json;

-- Query metadata files directly
SELECT *
FROM read_json_auto('~/.govbot/repos/**/bills/*/metadata.json')
LIMIT 10;

-- Query with filtering
SELECT identifier, title, jurisdiction->>'name' as state
FROM read_json_auto('~/.govbot/repos/**/bills/*/metadata.json')
WHERE title ILIKE '%health%';
```

## Performance Tips

1. **Use `govbot load`** - Pre-loading into a database file is faster for repeated queries than reading JSON files each time.

2. **Increase memory for large datasets**:
   ```bash
   govbot load --memory-limit 32GB
   ```

3. **Use Parquet for archival**:
   ```sql
   COPY (SELECT * FROM bills) TO 'bills.parquet' (FORMAT PARQUET);
   -- Later, query directly from Parquet (very fast)
   SELECT * FROM 'bills.parquet' WHERE jurisdiction->>'name' = 'Wyoming';
   ```

4. **Create indexes for frequent queries** (persisted in database):
   ```sql
   CREATE INDEX idx_bills_state ON bills ((jurisdiction->>'name'));
   ```

## Troubleshooting

### "duckdb command not found"
Install DuckDB CLI from https://duckdb.org/docs/installation/

### Memory errors with large datasets
Increase memory limit: `govbot load --memory-limit 32GB`

### Slow loading
- Reduce thread count if I/O bound: `govbot load --threads 2`
- Ensure SSD storage for best performance

### Schema variation errors
The `union_by_name=true` option handles schema variations, but severely malformed JSON files may cause issues. Check the source data.
