#!/bin/bash

output_dir="./__snapshots__"
limit=5  # Set your limit here (adjust as needed)

# Render all config files (render.py finds and processes all *.yml files)
python3 render.py -o "generated"

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
  
  # Take a sample from this config's output
  sampled_count=0
  
  if [ $total -gt $limit ]; then
    # Calculate step to spread the selection
    step=$(awk "BEGIN { print ($total-1)/($limit-1) }")
    keep_indices=()
    for ((i=0; i<$limit; i++)); do
      idx=$(awk "BEGIN {printf \"%d\", ($i*$step + 0.5)}")
      keep_indices+=($idx)
    done

    # Ensure indices are unique and valid
    keeps=()
    for idx in "${keep_indices[@]}"; do
      if [ $idx -ge 0 ] && [ $idx -lt $total ]; then
        dir_to_add="${dirs[$idx]}"
        # Check if this directory is already in keeps
        already_added=0
        for k in "${keeps[@]}"; do
          if [ "$dir_to_add" == "$k" ]; then
            already_added=1
            break
          fi
        done
        if [ $already_added -eq 0 ]; then
          keeps+=("$dir_to_add")
        fi
      fi
    done

    # Copy sampled directories to config-specific output directory
    for k in "${keeps[@]}"; do
      dir_name=$(basename "$k")
      cp -r "$k" "$config_output_dir/"
      echo "  ✓ Sampled: $dir_name"
      ((sampled_count++))
    done
  else
    # If total is less than or equal to limit, copy all
    for d in "${dirs[@]}"; do
      dir_name=$(basename "$d")
      cp -r "$d" "$config_output_dir/"
      echo "  ✓ Included: $dir_name"
      ((sampled_count++))
    done
  fi
  
  echo "  Summary: $sampled_count directories in $config_output_dir"
done

echo ""
echo "✓ Snapshot generation complete. Output in $output_dir"