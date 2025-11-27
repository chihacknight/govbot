# Schema Catalog

This directory contains JSON Schema definitions and Project Open Data catalog files that describe the structure and location of legislative data files.

## Data Catalog Files

The `*.data.json` files use the [Project Open Data](https://project-open-data.cio.gov/) catalog format to describe datasets. These files extend the standard format with custom extensions for filesystem path validation and schema references.

### Files

- **`ocd-files.data.json`** - Catalog for formatted OCD (Open Civic Data) files from the format action
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

These catalog files are used by:

1. **Schema Generators** - Tools that generate TypeScript, Python, and Rust type definitions from the JSON schemas
2. **Path Validators** - Validators that extract and validate path parameters from filesystem paths
3. **Documentation** - Self-documenting catalog of all data file types and their locations

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
