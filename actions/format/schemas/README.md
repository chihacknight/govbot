# Schema Code Generator

This directory contains schema definitions and a code generator that creates types and parsers from JSON schemas.

## Files

- `schemas.yaml` - Schema definitions mapping file paths to schemas
- `*.schema.json` - JSON Schema files for validation
- `generate.py` - Code generator script

## Usage

Generate all code (TypeScript types, Python types, and parsers):

```bash
python3 schemas/generate.py
```

Generate specific targets:

```bash
# TypeScript types only
python3 schemas/generate.py --target typescript

# Python types only
python3 schemas/generate.py --target python

# Parsers only
python3 schemas/generate.py --target parsers
```

## Generated Output

The generator creates code in the `generated/` directory:

- `generated/typescript/types.ts` - TypeScript type definitions
- `generated/python/types.py` - Python dataclass definitions
- `generated/parsers/parser.py` - Python parser that validates files based on path patterns
- `generated/parsers/parser.ts` - TypeScript parser (requires additional dependencies)

## Schema Path Mapping

The `schemas.yaml` file maps file path patterns to schema files:

```yaml
schemas:
  metadata:
    path: metadata.json
    file: metadata.schema.json
    type: Metadata
  action_log:
    path: logs/*.json
    file: action_log.schema.json
    type: ActionLog
```

The parser uses these mappings to automatically determine which schema to use for validation based on file paths.

## Dependencies

The generator requires:
- Python 3.9+
- PyYAML (`pip install pyyaml`)

For using the generated parsers:
- Python: `jsonschema` library
- TypeScript: `minimatch` and `ajv` (or similar JSON schema validator)

## Example: Using the Python Parser

```python
from generated.parsers.parser import validate_file

# Validate a metadata.json file
valid, error = validate_file("snapshots/wy/country:us/state:wy/sessions/2025/bills/SF0001/metadata.json")
if not valid:
    print(f"Validation error: {error}")
```

