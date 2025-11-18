#!/bin/bash
# Example usage of JSON Publisher

# Example 1: Publish to git file (without committing)
echo "Example 1: Publishing to git file..."
cat sample-report.json | python3 ../publish.py \
  --mode git \
  --output test-output/report.json

echo ""

# Example 2: Generate GitHub Pages HTML
echo "Example 2: Generating HTML for GitHub Pages..."
cat sample-report.json | python3 ../publish.py \
  --mode pages \
  --output test-output/index.html

echo ""

# Example 3: Show help
echo "Example 3: Available options..."
python3 ../publish.py --help

echo ""
echo "Check test-output/ directory for generated files"
