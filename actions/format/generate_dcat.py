#!/usr/bin/env python3

"""
Generate a DCAT (Data Catalog Vocabulary) data.json file for a legislative data repository.

This creates a simple catalog file that describes the dataset structure.
"""

import argparse
import json
import sys
from pathlib import Path


def generate_dcat_data(
    title: str,
    repo_url: str,
    schema_url: str = "https://raw.githubusercontent.com/windy-civi/toolkit/refs/heads/main/schemas/ocdfiles.bill.metadata.schema.json",
) -> dict:
    """
    Generate a DCAT Dataset structure.

    Args:
        title: Title of the dataset (e.g., "Illinois Legislation")
        repo_url: GitHub repository URL (e.g., "https://github.com/chn-openstates-files/il-legislation")
        schema_url: URL to the JSON schema that validates the data

    Returns:
        Dictionary representing the DCAT Dataset
    """
    return {
        "@type": "dcat:Dataset",
        "title": title,
        "distribution": [
            {
                "@type": "dcat:Distribution",
                "mediaType": "application/json",
                "conformsTo": schema_url,
                "accessURL": repo_url,
                "ex:pathPattern": "country:{country_code}/state:{jurisdiction_code}/sessions/{session_id}/bills/{bill_id}/metadata.json",
            }
        ],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate a DCAT data.json file for a legislative data repository"
    )
    parser.add_argument(
        "--repo-root",
        required=True,
        type=Path,
        help="Root directory of the repository",
    )
    parser.add_argument(
        "--title",
        required=True,
        help="Title of the dataset (e.g., 'Illinois Legislation')",
    )
    parser.add_argument(
        "--repo-url",
        required=True,
        help="GitHub repository URL (e.g., 'https://github.com/chn-openstates-files/il-legislation')",
    )
    parser.add_argument(
        "--schema-url",
        default="https://raw.githubusercontent.com/windy-civi/toolkit/refs/heads/main/schemas/ocdfiles.bill.metadata.schema.json",
        help="URL to the JSON schema (default: toolkit schema URL)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file path (default: {repo-root}/data.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write the file, just print what would be written",
    )

    args = parser.parse_args()

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        output_path = args.repo_root / "data.json"

    # Generate the DCAT data
    dcat_data = generate_dcat_data(
        title=args.title,
        repo_url=args.repo_url,
        schema_url=args.schema_url,
    )

    # Format as JSON
    json_output = json.dumps(dcat_data, indent=2)

    if args.dry_run:
        print(f"[DRY RUN] Would write to: {output_path}")
        print("\nContent:")
        print(json_output)
    else:
        # Write the file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_output + "\n")
        print(f"✅ Generated DCAT data.json at: {output_path}")
        print(f"   Title: {args.title}")
        print(f"   Repo URL: {args.repo_url}")


if __name__ == "__main__":
    main()

