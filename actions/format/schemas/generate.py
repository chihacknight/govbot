#!/usr/bin/env python3
"""
Schema code generator - generates types and parsers from JSON schemas
"""
import json
import yaml
import argparse
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import re


def load_yaml_config(config_path: Path) -> Dict[str, Any]:
    """Load the schemas.yaml configuration file"""
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_json_schema(schema_path: Path) -> Dict[str, Any]:
    """Load a JSON schema file"""
    with open(schema_path) as f:
        return json.load(f)


def json_schema_to_typescript_type(prop: Dict[str, Any], name: str = "") -> str:
    """Convert a JSON schema property to TypeScript type"""
    if "$ref" in prop:
        ref = prop["$ref"]
        if ref.startswith("#/definitions/"):
            return ref.split("/")[-1]
        return "any"
    
    prop_type = prop.get("type", "any")
    
    if prop_type == "array":
        items = prop.get("items", {})
        if "$ref" in items:
            ref = items["$ref"]
            if ref.startswith("#/definitions/"):
                item_type = ref.split("/")[-1]
            else:
                item_type = "any"
        else:
            item_type = json_schema_to_typescript_type(items, "")
        return f"{item_type}[]"
    
    if prop_type == "object":
        if "additionalProperties" in prop:
            if prop["additionalProperties"] is True:
                return "Record<string, any>"
        return "object"
    
    type_map = {
        "string": "string",
        "integer": "number",
        "number": "number",
        "boolean": "boolean",
        "null": "null",
    }
    
    if prop_type in type_map:
        ts_type = type_map[prop_type]
        if "enum" in prop:
            enum_values = " | ".join(f'"{v}"' for v in prop["enum"])
            return enum_values
        return ts_type
    
    # Handle union types
    if isinstance(prop_type, list):
        types = [json_schema_to_typescript_type({"type": t}, "") for t in prop_type]
        return " | ".join(types)
    
    return "any"


def generate_typescript_interface(schema: Dict[str, Any], name: str, definitions: Dict[str, Any]) -> str:
    """Generate a TypeScript interface from a JSON schema"""
    lines = [f"export interface {name} {{"]
    
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    
    for prop_name, prop_def in properties.items():
        is_required = prop_name in required
        optional = "" if is_required else "?"
        prop_type = json_schema_to_typescript_type(prop_def, prop_name)
        
        description = prop_def.get("description", "")
        comment = f"  // {description}" if description else ""
        
        lines.append(f"  {prop_name}{optional}: {prop_type};{comment}")
    
    lines.append("}")
    return "\n".join(lines)


def generate_typescript_types(schemas_dir: Path, output_dir: Path, config: Dict[str, Any]):
    """Generate TypeScript type definitions"""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    schemas_config = config.get("schemas", {})
    all_types = []
    
    for schema_name, schema_config in schemas_config.items():
        schema_file = schema_config.get("file")
        if not schema_file:
            continue
        
        schema_path = schemas_dir / schema_file
        if not schema_path.exists():
            print(f"Warning: Schema file not found: {schema_path}", file=sys.stderr)
            continue
        
        json_schema = load_json_schema(schema_path)
        type_name = schema_config.get("type", schema_name.title())
        
        # Generate main interface
        interface = generate_typescript_interface(json_schema, type_name, json_schema.get("definitions", {}))
        all_types.append(interface)
        
        # Generate definitions
        definitions = json_schema.get("definitions", {})
        for def_name, def_schema in definitions.items():
            def_interface = generate_typescript_interface(def_schema, def_name, definitions)
            all_types.append(def_interface)
    
    # Write all types to a single file
    output_file = output_dir / "types.ts"
    with open(output_file, "w") as f:
        f.write("// Auto-generated type definitions\n")
        f.write("// Do not edit manually\n\n")
        f.write("\n\n".join(all_types))
        f.write("\n")
    
    print(f"Generated TypeScript types: {output_file}")


def generate_python_dataclass(schema: Dict[str, Any], name: str) -> str:
    """Generate a Python dataclass from a JSON schema"""
    lines = [
        "from dataclasses import dataclass",
        "from typing import Optional, List, Dict, Any",
        "from datetime import datetime",
        "",
        f"@dataclass",
        f"class {name}:",
    ]
    
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    
    for prop_name, prop_def in properties.items():
        is_required = prop_name in required
        prop_type = json_schema_to_python_type(prop_def, prop_name)
        
        if not is_required:
            prop_type = f"Optional[{prop_type}]"
        
        description = prop_def.get("description", "")
        if description:
            lines.append(f'    """{description}"""')
        
        lines.append(f"    {prop_name}: {prop_type}")
    
    return "\n".join(lines)


def json_schema_to_python_type(prop: Dict[str, Any], name: str = "") -> str:
    """Convert a JSON schema property to Python type"""
    if "$ref" in prop:
        ref = prop["$ref"]
        if ref.startswith("#/definitions/"):
            return ref.split("/")[-1]
        return "Any"
    
    prop_type = prop.get("type", "Any")
    
    if prop_type == "array":
        items = prop.get("items", {})
        if "$ref" in items:
            ref = items["$ref"]
            if ref.startswith("#/definitions/"):
                item_type = ref.split("/")[-1]
            else:
                item_type = "Any"
        else:
            item_type = json_schema_to_python_type(items, "")
        return f"List[{item_type}]"
    
    if prop_type == "object":
        if "additionalProperties" in prop:
            if prop["additionalProperties"] is True:
                return "Dict[str, Any]"
        return "Dict[str, Any]"
    
    type_map = {
        "string": "str",
        "integer": "int",
        "number": "float",
        "boolean": "bool",
    }
    
    if prop_type in type_map:
        return type_map[prop_type]
    
    # Handle union types
    if isinstance(prop_type, list):
        types = [json_schema_to_python_type({"type": t}, "") for t in prop_type if t != "null"]
        if len(types) == 1:
            return types[0]
        return f"Union[{', '.join(types)}]"
    
    return "Any"


def generate_python_types(schemas_dir: Path, output_dir: Path, config: Dict[str, Any]):
    """Generate Python type definitions"""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    schemas_config = config.get("schemas", {})
    all_classes = []
    
    for schema_name, schema_config in schemas_config.items():
        schema_file = schema_config.get("file")
        if not schema_file:
            continue
        
        schema_path = schemas_dir / schema_file
        if not schema_path.exists():
            print(f"Warning: Schema file not found: {schema_path}", file=sys.stderr)
            continue
        
        json_schema = load_json_schema(schema_path)
        type_name = schema_config.get("type", schema_name.title())
        
        # Generate main class
        dataclass = generate_python_dataclass(json_schema, type_name)
        all_classes.append(dataclass)
        
        # Generate definitions
        definitions = json_schema.get("definitions", {})
        for def_name, def_schema in definitions.items():
            def_class = generate_python_dataclass(def_schema, def_name)
            all_classes.append(def_class)
    
    # Write all classes to a single file
    output_file = output_dir / "types.py"
    with open(output_file, "w") as f:
        f.write('"""Auto-generated type definitions - Do not edit manually"""\n\n')
        f.write("\n\n".join(all_classes))
        f.write("\n")
    
    print(f"Generated Python types: {output_file}")


def generate_parser(schemas_dir: Path, output_dir: Path, config: Dict[str, Any], language: str):
    """Generate parser/validator code for a specific language"""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    schemas_config = config.get("schemas", {})
    
    if language == "python":
        generate_python_parser(schemas_dir, output_dir, schemas_config)
    elif language == "typescript":
        generate_typescript_parser(schemas_dir, output_dir, schemas_config)
    else:
        print(f"Parser generation for {language} not yet implemented", file=sys.stderr)


def generate_python_parser(schemas_dir: Path, output_dir: Path, schemas_config: Dict[str, Any]):
    """Generate Python parser that validates files based on path patterns"""
    lines = [
        '"""Auto-generated parser - validates files based on path patterns"""',
        "import json",
        "from pathlib import Path",
        "from typing import Dict, Any, Optional, Tuple",
        "from jsonschema import validate, ValidationError",
        "import fnmatch",
        "",
        "",
        "SCHEMA_PATHS = {",
    ]
    
    # Build path to schema mapping
    for schema_name, schema_config in schemas_config.items():
        path_pattern = schema_config.get("path", "")
        schema_file = schema_config.get("file", "")
        if path_pattern and schema_file:
            lines.append(f'    "{path_pattern}": "{schema_file}",')
    
    lines.extend([
        "}",
        "",
        "",
        "def load_schema(schema_file: str) -> Dict[str, Any]:",
        '    """Load a JSON schema file"""',
        "    schema_path = Path(__file__).parent.parent / schema_file",
        "    with open(schema_path) as f:",
        "        return json.load(f)",
        "",
        "",
        "def get_schema_for_path(file_path: str) -> Optional[Dict[str, Any]]:",
        '    """Get the schema for a file based on its path"""',
        "    path = Path(file_path)",
        "    relative_path = str(path.relative_to(path.anchor))",
        "",
        "    for pattern, schema_file in SCHEMA_PATHS.items():",
        "        if fnmatch.fnmatch(relative_path, pattern) or fnmatch.fnmatch(str(path), pattern):",
        "            return load_schema(schema_file)",
        "    return None",
        "",
        "",
        "def validate_file(file_path: str) -> Tuple[bool, Optional[str]]:",
        '    """Validate a file against its schema based on path"""',
        "    schema = get_schema_for_path(file_path)",
        "    if not schema:",
        "        return False, 'No schema found for path: ' + file_path",
        "",
        "    try:",
        "        with open(file_path) as f:",
        "            data = json.load(f)",
        "        validate(instance=data, schema=schema)",
        "        return True, None",
        "    except ValidationError as e:",
        "        return False, str(e)",
        "    except Exception as e:",
        "        return False, 'Error reading file: ' + str(e)",
        "",
    ])
    
    output_file = output_dir / "parser.py"
    with open(output_file, "w") as f:
        f.write("\n".join(lines))
    
    print(f"Generated Python parser: {output_file}")


def generate_typescript_parser(schemas_dir: Path, output_dir: Path, schemas_config: Dict[str, Any]):
    """Generate TypeScript parser that validates files based on path patterns"""
    lines = [
        "// Auto-generated parser - validates files based on path patterns",
        "import * as fs from 'fs';",
        "import * as path from 'path';",
        "import { minimatch } from 'minimatch';",
        "",
        "interface SchemaPaths {",
        "  [pattern: string]: string;",
        "}",
        "",
        "const SCHEMA_PATHS: SchemaPaths = {",
    ]
    
    # Build path to schema mapping
    for schema_name, schema_config in schemas_config.items():
        path_pattern = schema_config.get("path", "")
        schema_file = schema_config.get("file", "")
        if path_pattern and schema_file:
            lines.append(f'  "{path_pattern}": "{schema_file}",')
    
    lines.extend([
        "};",
        "",
        "export function loadSchema(schemaFile: string): any {",
        "  const schemaPath = path.join(__dirname, '..', schemaFile);",
        "  return JSON.parse(fs.readFileSync(schemaPath, 'utf-8'));",
        "}",
        "",
        "export function getSchemaForPath(filePath: string): any | null {",
        "  for (const [pattern, schemaFile] of Object.entries(SCHEMA_PATHS)) {",
        "    if (minimatch(filePath, pattern)) {",
        "      return loadSchema(schemaFile);",
        "    }",
        "  }",
        "  return null;",
        "}",
        "",
        "export function validateFile(filePath: string): { valid: boolean; error?: string } {",
        "  const schema = getSchemaForPath(filePath);",
        "  if (!schema) {",
        "    return { valid: false, error: `No schema found for path: ${filePath}` };",
        "  }",
        "",
        "  try {",
        "    const data = JSON.parse(fs.readFileSync(filePath, 'utf-8'));",
        "    // Note: You'll need to use a JSON schema validator library like ajv",
        "    // const Ajv = require('ajv');",
        "    // const ajv = new Ajv();",
        "    // const valid = ajv.validate(schema, data);",
        "    return { valid: true };",
        "  } catch (e: any) {",
        "    return { valid: false, error: e.message };",
        "  }",
        "}",
        "",
    ])
    
    output_file = output_dir / "parser.ts"
    with open(output_file, "w") as f:
        f.write("\n".join(lines))
    
    print(f"Generated TypeScript parser: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Generate code from schema definitions")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "schemas.yaml",
        help="Path to schemas.yaml config file",
    )
    parser.add_argument(
        "--schemas-dir",
        type=Path,
        default=Path(__file__).parent,
        help="Directory containing JSON schema files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent / "generated",
        help="Output directory for generated code",
    )
    parser.add_argument(
        "--target",
        choices=["typescript", "python", "rust", "parsers", "all"],
        default="all",
        help="What to generate",
    )
    
    args = parser.parse_args()
    
    # Load config
    config = load_yaml_config(args.config)
    generator_config = config.get("generators", {})
    
    # Generate based on target
    if args.target in ["typescript", "all"]:
        ts_config = generator_config.get("typescript", {})
        ts_output = args.output_dir / ts_config.get("output_dir", "typescript")
        generate_typescript_types(args.schemas_dir, ts_output, config)
    
    if args.target in ["python", "all"]:
        py_config = generator_config.get("python", {})
        py_output = args.output_dir / py_config.get("output_dir", "python")
        generate_python_types(args.schemas_dir, py_output, config)
    
    if args.target in ["parsers", "all"]:
        parser_config = generator_config.get("parsers", {})
        parser_output = args.output_dir / parser_config.get("output_dir", "parsers")
        languages = parser_config.get("languages", ["python", "typescript"])
        for lang in languages:
            generate_parser(args.schemas_dir, parser_output, config, lang)
    
    if args.target == "rust":
        print("Rust generation not yet implemented", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

