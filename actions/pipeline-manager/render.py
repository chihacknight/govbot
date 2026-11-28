#!/usr/bin/env python3
"""
Template renderer for pipeline-manager: fills a template file's ✏️{ locale.<key> }✏️
markers. Used by jurisdictions.py (which decides what to render, and where).
"""

import os
import re
import subprocess


def run_shell(cmd, check=True, capture_output=True):
    """Run a shell command and return the result."""
    result = subprocess.run(
        cmd,
        shell=True,
        check=check,
        capture_output=capture_output,
        text=True
    )
    if capture_output:
        return result.stdout.strip()
    return result


def render_template(template_file, output_file, locale, toolkit_branch="main", managed="true", runner="ubuntu-latest", force_self_hosted="false", docker_image="openstates/scrapers:latest", extra_vars=None, marker_open="✏️✏️", marker_close="✏️✏️"):
    """Render a template file using sed for replacements."""
    if extra_vars is None:
        extra_vars = []

    # Create output directory
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # Escape markers for sed (escape special regex characters, but NOT { and } which are literal in basic sed)
    def escape_sed_pattern(s):
        # Escape special sed regex characters
        # Need to escape: . * ^ $ [ \ ( ) + ? |
        # Do NOT escape { and } - they are literal in basic sed regex
        return re.sub(r'([.\\*^$[()+?|])', r'\\\1', s)

    escaped_open = escape_sed_pattern(marker_open)
    escaped_close = escape_sed_pattern(marker_close)

    # Use sed to do all replacements in one pipeline, reading from file
    # Build sed script - match variable names with optional whitespace (trim whitespace)
    # Handle locale.* variables - need to escape dot in sed pattern
    # Note: { and } are literal in basic sed, so we use them directly (not escaped)
    # But we need to escape the dot in locale.key, locale.toolkit_branch, etc.
    # marker_open is "✏️{" and marker_close is "}✏️", but escape_sed_pattern escapes { and }
    # So we need to use the raw markers for the pattern, but escape the dot
    raw_open = marker_open  # Use raw since { } are literal in basic sed
    raw_close = marker_close

    sed_script = f"sed 's|{raw_open}[[:space:]]*locale\\.key[[:space:]]*{raw_close}|{locale}|g'"
    sed_script += f" | sed 's|{raw_open}[[:space:]]*locale\\.toolkit_branch[[:space:]]*{raw_close}|{toolkit_branch}|g'"
    sed_script += f" | sed 's|{raw_open}[[:space:]]*locale\\.runner[[:space:]]*{raw_close}|{runner}|g'"
    sed_script += f" | sed 's|{raw_open}[[:space:]]*locale\\.force_self_hosted[[:space:]]*{raw_close}|{force_self_hosted}|g'"
    sed_script += f" | sed 's|{raw_open}[[:space:]]*locale\\.docker_image[[:space:]]*{raw_close}|{docker_image}|g'"
    sed_script += f" | sed 's|{raw_open}[[:space:]]*managed[[:space:]]*{raw_close}|{managed}|g'"

    # Add extra variable replacements with locale. prefix
    for var in extra_vars:
        if "=" in var:
            key, value = var.split("=", 1)
            # Escape special sed characters in value using shell
            escaped_value = run_shell(f"echo '{value}' | sed 's/[[\\.*^$()+?{{|}}]/\\\\&/g'")
            # Escape dot in key for sed pattern (replace . with \.)
            escaped_key = key.replace('.', r'\.')
            # Replace locale.key patterns
            sed_script += f" | sed 's|{raw_open}[[:space:]]*locale\\.{escaped_key}[[:space:]]*{raw_close}|{escaped_value}|g'"

    # Execute sed pipeline and write to output
    cmd = f"cat '{template_file}' | {sed_script} > '{output_file}'"
    run_shell(cmd, capture_output=False)

    print(f"✓ Rendered {os.path.basename(template_file)} -> {output_file}")
