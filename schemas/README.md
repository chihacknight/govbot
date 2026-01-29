# Schema Catalog

This directory contains JSON Schema definitions and Project Open Data catalog files that describe the structure and location of legislative data files.

## JSON Schema Files

The `*.schema.json` files are JSON Schema definitions that validate the structure of configuration and data files.

### Configuration Schemas

- **`govbot.schema.json`** - Schema for `govbot.yml` configuration files used by the govbot CLI tool. Defines the structure for repositories, tags, and RSS publishing configuration.

### Data Schemas

- **`openstates.*.schema.json`** - Schemas for OpenStates scraped data structures
- **`ocdfiles.*.schema.json`** - Schemas for OCD (Open Civic Data) formatted files

## Data Catalog Files

The `*.data.json` files use the [Project Open Data](https://project-open-data.cio.gov/) catalog format to describe datasets. These files extend the standard format with custom extensions for filesystem path validation and schema references.

### Files

- **`ocdfiles.data.json`** - Catalog for formatted OCD (Open Civic Data) files from the format action
- **`openstates-scrape.data.json`** - Catalog for raw scraped files from OpenStates

## Custom Extensions

The data.json files extend the Project Open Data schema with three custom fields (prefixed with `x-`):

### `x-filesystem-path`

A template string that describes the filesystem path pattern for files in this dataset. Path parameters are enclosed in curly braces `{param_name}`.

**Example:**

```json
"x-filesystem-path": "{jurisdiction}/{session}/bills/{bill_id}-{title}/metadata.json"
```

This pattern would match paths like:

- `wy/2024/bills/SF0001-some-bill-title/metadata.json`
- `il/2023/bills/HB1234-another-bill/metadata.json`

### `x-schema-file`

A relative path to the JSON Schema file that validates the structure of files matching this path pattern.

**Example:**

```json
"x-schema-file": "schemas/metadata.schema.json"
```

This references the JSON Schema that defines the structure of the data files (e.g., required fields, data types, validation rules).

### `x-path-parameters`

An array of OpenAPI-style parameter definitions that describe the path variables extracted from `x-filesystem-path`. Each parameter includes:

- `name`: The parameter name (matches the `{name}` in the path pattern)
- `in`: Always `"path"` for filesystem paths
- `required`: Whether the parameter is required
- `schema`: A JSON Schema object describing the parameter:
  - `type`: The data type (typically `"string"`)
  - `pattern`: Optional regex pattern for validation
  - `description`: Human-readable description

**Example:**

```json
"x-path-parameters": [
  {
    "name": "jurisdiction",
    "in": "path",
    "required": true,
    "schema": {
      "type": "string",
      "pattern": "^[a-z]{2}$",
      "description": "Jurisdiction code (e.g., wy, il)"
    }
  },
  {
    "name": "session",
    "in": "path",
    "required": true,
    "schema": {
      "type": "string",
      "pattern": "^\\d{4}$",
      "description": "Legislative session year (e.g., 2024)"
    }
  }
]
```

## Usage

### Code Editor Support

Schemas can be referenced in YAML files using the `$schema` key:

```yaml
# govbot.yml
$schema: https://raw.githubusercontent.com/windy-civi/toolkit/main/schemas/govbot.schema.json

repos:
  - all
tags:
  # ... tag definitions
```

This enables:
- **Autocomplete** - Editors suggest valid keys and values
- **Validation** - Real-time error checking as you type
- **Documentation** - Hover tooltips with field descriptions

### Other Uses

These catalog and schema files are used by:

1. **Schema Generators** - Tools that generate TypeScript, Python, and Rust type definitions from the JSON schemas
2. **Path Validators** - Validators that extract and validate path parameters from filesystem paths
3. **Documentation** - Self-documenting catalog of all data file types and their locations
4. **CI/CD Validation** - Automated validation in GitHub Actions and other CI systems

## Standard Project Open Data Fields

Each dataset entry also includes standard Project Open Data fields:

- `identifier` - Unique identifier for the dataset
- `title` - Human-readable title
- `description` - Description of the dataset
- `keyword` - Array of keywords/tags
- `modified` - Last modification date (ISO 8601)
- `publisher` - Organization that publishes the data
- `contactPoint` - Contact information
- `accessLevel` - Access level (typically `"public"`)
- `license` - License information

These fields provide metadata about the datasets and can be used for cataloging, discovery, and compliance with open data standards.
