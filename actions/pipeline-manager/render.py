#!/usr/bin/env python3
"""
Template renderer for pipeline-manager using Python with shell commands.
Uses shell tools (sed, find, etc.) where possible for efficiency.
"""

import os
import sys
import subprocess
import re
import shutil
import argparse
from pathlib import Path


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


def render_template(template_file, output_file, locale, toolkit_branch="main", managed="true", extra_vars=None, marker_open="✏️✏️", marker_close="✏️✏️"):
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


def get_config_value(config_str, key, default=""):
    """Extract a value from a config string using sed."""
    # Try to match key=value after | or at start
    value = run_shell(f"echo '{config_str}' | sed -n 's/.*|{key}=\\([^|]*\\).*/\\1/p'", check=False)
    if not value:
        value = run_shell(f"echo '{config_str}' | sed -n 's/^{key}=\\([^|]*\\).*/\\1/p'", check=False)
    return value if value else default


def parse_config(config_file):
    """Parse config.yml using Python but with shell-style regex matching."""
    
    all_locales = []
    all_configs = []
    marker_open = "✏️{"  # default
    marker_close = "}✏️"  # default
    templates = {}  # Dictionary mapping template names to their folder-name values
    org_username = ""  # GitHub organization/username
    
    current_locale = None
    in_locale = False
    in_template_markers = False
    in_templates = False
    in_org = False
    current_template = None
    locale_config_str = ""
    
    # Read file line by line
    with open(config_file, 'r') as f:
        for line in f:
            line = line.rstrip('\n')
            
            # Check for org section
            if re.match(r'^org:\s*$', line):
                in_org = True
                continue
            
            # Parse org.username
            if in_org:
                match = re.match(r'^  username:\s*(.+)$', line)
                if match:
                    value = match.group(1).strip()
                    # Remove quotes using sed
                    value = run_shell(f"echo '{value}' | sed \"s/^['\\\"]//; s/['\\\"]$//\"")
                    org_username = value
                elif re.match(r'^[a-z]', line):
                    # We've left the org section
                    in_org = False
            
            # Check for template_markers section
            if re.match(r'^template_markers:\s*$', line):
                in_template_markers = True
                continue
            
            # Parse template_markers values
            if in_template_markers:
                match = re.match(r'^  (open|close):\s*(.+)$', line)
                if match:
                    key = match.group(1)
                    value = match.group(2).strip()
                    # Remove quotes using sed
                    value = run_shell(f"echo '{value}' | sed \"s/^['\\\"]//; s/['\\\"]$//\"")
                    if key == "open":
                        marker_open = value
                    elif key == "close":
                        marker_close = value
                elif re.match(r'^[a-z]', line):
                    # We've left the template_markers section
                    in_template_markers = False
            
            # Check for templates section
            if re.match(r'^templates:\s*$', line):
                in_templates = True
                continue
            
            # Parse templates section
            if in_templates:
                # Check if this is a template name (2 spaces, template name with hyphens, colon)
                # Template names are like "openstates-to-ocd-files", not 2-letter codes
                match = re.match(r'^  ([a-z][a-z-]+):\s*$', line)
                if match:
                    template_name = match.group(1)
                    # Only treat as template if it contains a hyphen (template names have hyphens, locale codes don't)
                    # Or if it's a known template pattern
                    if '-' in template_name or len(template_name) > 2:
                        current_template = template_name
                        templates[current_template] = {}
                        continue
                
                # Parse folder-name and fully_override_dirs within template
                if current_template:
                    match = re.match(r'^    folder-name:\s*(.+)$', line)
                    if match:
                        value = match.group(1).strip()
                        # Remove quotes using sed
                        value = run_shell(f"echo '{value}' | sed \"s/^['\\\"]//; s/['\\\"]$//\"")
                        templates[current_template]['folder-name'] = value
                        continue
                    
                    # Parse fully_override_dirs (array)
                    match = re.match(r'^    fully_override_dirs:\s*$', line)
                    if match:
                        templates[current_template]['fully_override_dirs'] = []
                        continue
                    
                    # Parse array items (6 spaces for list items)
                    if 'fully_override_dirs' in templates[current_template]:
                        match = re.match(r'^      -\s*(.+)$', line)
                        if match:
                            value = match.group(1).strip()
                            # Remove quotes using sed
                            value = run_shell(f"echo '{value}' | sed \"s/^['\\\"]//; s/['\\\"]$//\"")
                            templates[current_template]['fully_override_dirs'].append(value)
                            continue
                        # If we hit a line that's not an array item and not indented with 4 spaces, we're done with the array
                        elif not re.match(r'^    ', line):
                            # Remove the key if we're leaving the templates section
                            pass
                    
                    # Check if we've left the templates section (line starts with 2 spaces and a lowercase letter, but not 4 spaces)
                    if re.match(r'^  [a-z]', line) and not re.match(r'^    ', line):
                        # We've left the templates section
                        in_templates = False
                        current_template = None
            
            # Check if this is a locale key (2 spaces, 2 lowercase letters, colon)
            # Using shell-style regex: ^  [a-z]{2}:$
            match = re.match(r'^  ([a-z]{2}):\s*$', line)
            if match:
                # Save previous locale
                if current_locale:
                    all_locales.append(current_locale)
                    all_configs.append(locale_config_str)
                
                current_locale = match.group(1)
                in_locale = True
                locale_config_str = ""
                continue
            
            # If in locale block, parse key-value pairs (4 spaces)
            if in_locale:
                # First, check for array items (6 spaces) - this must come before checking for array declarations
                # because array items come after the array declaration
                match = re.match(r'^      -\s*(.+)$', line)
                if match:
                    value = match.group(1).strip()
                    # Remove comments and quotes
                    value = re.sub(r'\s*#.*$', '', value).strip()
                    value = run_shell(f"echo '{value}' | sed \"s/^['\\\"]//; s/['\\\"]$//\"")
                    
                    # Check which array this belongs to (disabled_jobs or labels)
                    if locale_config_str:
                        if 'disabled_jobs=[]' in locale_config_str:
                            # Replace [] with the first item, or append
                            if locale_config_str.endswith('|disabled_jobs=[]'):
                                locale_config_str = locale_config_str.replace('|disabled_jobs=[]', f'|disabled_jobs={value}')
                            elif 'disabled_jobs=[]' in locale_config_str:
                                locale_config_str = locale_config_str.replace('disabled_jobs=[]', f'disabled_jobs={value}')
                            else:
                                # Append to existing array (format: disabled_jobs=item1,item2)
                                locale_config_str = re.sub(
                                    r'\|disabled_jobs=([^|]+)',
                                    lambda m: f"|disabled_jobs={m.group(1)},{value}",
                                    locale_config_str
                                )
                        elif 'labels=[]' in locale_config_str:
                            if locale_config_str.endswith('|labels=[]'):
                                locale_config_str = locale_config_str.replace('|labels=[]', f'|labels={value}')
                            elif 'labels=[]' in locale_config_str:
                                locale_config_str = locale_config_str.replace('labels=[]', f'labels={value}')
                            else:
                                locale_config_str = re.sub(
                                    r'\|labels=([^|]+)',
                                    lambda m: f"|labels={m.group(1)},{value}",
                                    locale_config_str
                                )
                    continue
                
                # Check for array fields (like disabled_jobs) - declarations (4 spaces, key with colon, no value)
                match = re.match(r'^    ([a-z_]+):\s*$', line)
                if match:
                    key = match.group(1)
                    # Check if this is an array field (disabled_jobs, labels, etc.)
                    if key in ('disabled_jobs', 'labels'):
                        # Initialize array in config - we'll parse items next
                        if not locale_config_str:
                            locale_config_str = f"{key}=[]"
                        else:
                            locale_config_str = f"{locale_config_str}|{key}=[]"
                        continue
                
                # Regular key-value pairs
                match = re.match(r'^    ([a-z_]+):\s*(.+)$', line)
                if match:
                    key = match.group(1)
                    value = match.group(2).strip()
                    # Remove comments (everything after #)
                    value = re.sub(r'\s*#.*$', '', value).strip()
                    # Remove quotes using sed
                    value = run_shell(f"echo '{value}' | sed \"s/^['\\\"]//; s/['\\\"]$//\"")
                    
                    if not locale_config_str:
                        locale_config_str = f"{key}={value}"
                    else:
                        locale_config_str = f"{locale_config_str}|{key}={value}"
                elif re.match(r'^[a-z]', line) and not re.match(r'^  [a-z]{2}:', line):
                    # We've left the locales section
                    in_locale = False
    
    # Save last locale
    if current_locale:
        all_locales.append(current_locale)
        all_configs.append(locale_config_str)
    
    return all_locales, all_configs, marker_open, marker_close, templates, org_username


def render_folder_name(folder_name_template, locale, marker_open, marker_close):
    """Render the folder name template by replacing locale.key marker with actual locale."""
    # Replace the locale.key marker pattern (e.g., ✏️{locale.key}✏️ or ✏️{ locale.key }✏️) with the actual locale
    # Match with optional whitespace (trim whitespace)
    pattern = re.escape(marker_open) + r'\s*locale\.key\s*' + re.escape(marker_close)
    return re.sub(pattern, locale, folder_name_template)


def process_locale(locale, config_str, templates_dir, output_dir, marker_open, marker_close, templates):
    """Process templates for a single locale."""
    # Extract template using shell
    template = get_config_value(config_str, "template", "")
    if not template:
        return
    
    # Extract managed status
    managed = get_config_value(config_str, "managed", "true")
    if managed == "false":
        return
    
    # Extract toolkit_branch
    toolkit_branch = get_config_value(config_str, "toolkit_branch", "main")
    
    # Get folder-name from templates config, fallback to locale if not found
    folder_name = locale  # default fallback
    if template in templates and 'folder-name' in templates[template]:
        folder_name_template = templates[template]['folder-name']
        folder_name = render_folder_name(folder_name_template, locale, marker_open, marker_close)
    
    # Extract disabled_jobs
    disabled_jobs_str = get_config_value(config_str, "disabled_jobs", "")
    disabled_jobs = []
    if disabled_jobs_str:
        # Parse comma-separated list
        disabled_jobs = [job.strip() for job in disabled_jobs_str.split(',') if job.strip()]
    
    # Build extra vars array
    # Include all fields except managed, toolkit_branch, template, and disabled_jobs (which are handled separately)
    extra_vars = []
    for pair in config_str.split("|"):
        if "=" in pair:
            key, value = pair.split("=", 1)
            if key not in ("managed", "toolkit_branch", "template", "disabled_jobs"):
                extra_vars.append(f"{key}={value}")
    
    # Find all template files in the specific template directory
    template_dir = os.path.join(templates_dir, template)
    if not os.path.exists(template_dir):
        return
    
    find_cmd = f"find '{template_dir}' -type f ! -name '.*' -print0"
    result = subprocess.run(find_cmd, shell=True, capture_output=True, text=True)
    template_files = [f for f in result.stdout.split('\0') if f]
    
    for template_file in template_files:
        # Check if this file should be excluded based on disabled_jobs
        # Get the base filename without extension (e.g., "extract-text.yml" -> "extract-text")
        file_name = os.path.basename(template_file)
        file_base = os.path.splitext(file_name)[0]  # Remove .yml extension
        
        # Skip if this file is in disabled_jobs
        if file_base in disabled_jobs:
            print(f"⊘ Skipped {file_name} (disabled_jobs: {file_base})")
            continue
        # Get relative path from the template directory (not templates_dir)
        rel_path = os.path.relpath(template_file, template_dir)
        output_file = os.path.join(output_dir, folder_name, rel_path)
        
        # Remove .j2 extension if present
        if output_file.endswith('.j2'):
            output_file = output_file[:-3]
        
        render_template(
            template_file,
            output_file,
            locale,
            toolkit_branch,
            managed,
            extra_vars,
            marker_open,
            marker_close
        )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Template renderer for pipeline-manager")
    parser.add_argument(
        "-o", "--output",
        type=str,
        default="generated",
        help="Output directory (default: generated, relative to script directory)"
    )
    args = parser.parse_args()
    
    script_dir = Path(__file__).parent
    config_file = script_dir / "config.yml"
    templates_dir = script_dir / "templates"
    output_dir = script_dir / args.output
    
    # Check if config file exists
    if not config_file.exists():
        print(f"Error: config.yml not found at {config_file}", file=sys.stderr)
        sys.exit(1)
    
    # Check if templates directory exists
    if not templates_dir.exists():
        print(f"Error: templates directory not found at {templates_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Delete output directory if it exists to ensure clean output
    if output_dir.exists():
        shutil.rmtree(output_dir)
        print(f"✓ Deleted existing output directory: {output_dir}")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Parse config using shell commands
    all_locales, all_configs, marker_open, marker_close, templates, org_username = parse_config(config_file)
    
    # Process each locale
    for locale, config_str in zip(all_locales, all_configs):
        process_locale(str(locale), config_str, str(templates_dir), str(output_dir), marker_open, marker_close, templates)
    
    # Count generated folders using shell
    count = run_shell(f"ls -1 '{output_dir}' 2>/dev/null | wc -l | tr -d ' '", check=False) or "0"
    
    print("")
    print(f"✓ Template rendering complete. Output written to {output_dir}")
    print(f"  Generated folders: {count} locales")


if __name__ == "__main__":
    main()

