#!/bin/bash

output_dir="./__snapshots__"

# Fixed sample set for deterministic snapshots across platforms
# Selected to provide geographic diversity: ak (northwest), id (mountain), mt (plains), pr (territory), wy (mountain)
SAMPLE_LOCALES=("ak" "id" "mt" "pr" "wy")

# Render only the states we need for snapshots (much faster)
python3 render.py -o "generated" --test-states "ak,id,mt,pr,wy"

# Create output directory
mkdir -p "$output_dir"

# Process each generated config directory
for generated_config_dir in ./generated/*/; do
  if [ ! -d "$generated_config_dir" ]; then
    continue
  fi

  config_name=$(basename "$generated_config_dir")
  config_output_dir="$output_dir/$config_name"

  echo ""
  echo "Processing snapshots for $config_name..."

  # Get sorted list of directories for this config
  dirs=($(find "$generated_config_dir" -mindepth 1 -maxdepth 1 -type d | sort))
  total=${#dirs[@]}

  if [ $total -eq 0 ]; then
    echo "  No directories generated for $config_name, skipping..."
    continue
  fi

  echo "  Generated $total directories"

  # Clear this config's output directory
  if [ -d "$config_output_dir" ]; then
    rm -rf "$config_output_dir"
  fi
  mkdir -p "$config_output_dir"

  # Copy sample locales to snapshot directory
  sampled_count=0
  for locale in "${SAMPLE_LOCALES[@]}"; do
    locale_dir="$generated_config_dir/${locale}-legislation"
    if [ -d "$locale_dir" ]; then
      cp -r "$locale_dir" "$config_output_dir/"
      echo "  ✓ Sampled: ${locale}-legislation"
      ((sampled_count++))
    else
      echo "  ⚠ Not found: ${locale}-legislation"
    fi
  done

  echo "  Summary: $sampled_count directories in $config_output_dir"
done

echo ""
echo "✓ Snapshot generation complete. Output in $output_dir"
