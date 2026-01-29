#!/usr/bin/env bash
# Main formatter script - shared logic for both local and CI environments
# Usage: main.sh <state> <input-data-folder> <output-folder> [pipenv-cmd]

set -euo pipefail

STATE="${1:-}"
INPUT_DATA_FOLDER="${2:-}"
OUTPUT_FOLDER="${3:-}"
PIPENV_CMD="${4:-}"

if [ -z "$STATE" ] || [ -z "$INPUT_DATA_FOLDER" ] || [ -z "$OUTPUT_FOLDER" ]; then
    echo "Usage: $0 <state> <input-data-folder> <output-folder> [pipenv-cmd]"
    echo "  state: State abbreviation (e.g., wy, id, il)"
    echo "  input-data-folder: Path to folder containing JSON files (with state subdirectory)"
    echo "  output-folder: Path where processed files will be saved"
    echo "  pipenv-cmd: Optional pipenv command (default: auto-detect)"
    exit 1
fi

# Get the script directory (where this script lives)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Determine input folder - check for common structures:
# 1. INPUT_DATA_FOLDER/_data/STATE (GitHub Actions structure)
# 2. INPUT_DATA_FOLDER/STATE (local structure)
# 3. INPUT_DATA_FOLDER (files directly in folder)
STATE_LOWER=$(echo "$STATE" | tr '[:upper:]' '[:lower:]')

if [ -d "$INPUT_DATA_FOLDER/_data/$STATE_LOWER" ]; then
    ACTUAL_INPUT_FOLDER="$INPUT_DATA_FOLDER/_data/$STATE_LOWER"
elif [ -d "$INPUT_DATA_FOLDER/$STATE_LOWER" ]; then
    ACTUAL_INPUT_FOLDER="$INPUT_DATA_FOLDER/$STATE_LOWER"
else
    ACTUAL_INPUT_FOLDER="$INPUT_DATA_FOLDER"
fi

echo "📂 Using input folder: $ACTUAL_INPUT_FOLDER"

# Setup pipenv if not provided
if [ -z "$PIPENV_CMD" ]; then
    echo "📦 Setting up Python environment..."
    
    # Check if Python 3 is available
    if ! command -v python3 &> /dev/null; then
        echo "❌ Python 3 is not installed. Please install Python 3.9 or later."
        exit 1
    fi
    
    PYTHON_CMD="python3"
    
    # Check if pipenv is available (either as command or as module)
    if command -v pipenv &> /dev/null; then
        PIPENV_CMD="pipenv"
    elif $PYTHON_CMD -m pipenv --version &> /dev/null 2>&1; then
        PIPENV_CMD="$PYTHON_CMD -m pipenv"
    else
        echo "📥 pipenv not found. Installing pipenv..."
        $PYTHON_CMD -m pip install --user pipenv
        # Try again after installation
        if $PYTHON_CMD -m pipenv --version &> /dev/null 2>&1; then
            PIPENV_CMD="$PYTHON_CMD -m pipenv"
        else
            echo "❌ pipenv installation failed. Please install manually: pip install pipenv"
            exit 1
        fi
    fi
    
    echo "✅ pipenv found: $PIPENV_CMD"
    
    # Set up pipenv environment variables
    export PIPENV_VENV_IN_PROJECT=1
    export PIPENV_IGNORE_VIRTUALENVS=1
    export PIPENV_PIPFILE="$SCRIPT_DIR/Pipfile"
    
    # Install dependencies
    echo "📦 Installing dependencies with pipenv..."
    cd "$SCRIPT_DIR"
    $PIPENV_CMD install --dev
fi

# Verify main.py exists
if [ ! -f "$SCRIPT_DIR/main.py" ]; then
    echo "❌ main.py not found at $SCRIPT_DIR/main.py"
    exit 1
fi

# Sanitize JSON files (remove _id and scraped_at fields)
echo "🧹 Sanitizing JSON files..."
if ! command -v jq &> /dev/null; then
    echo "❌ jq is not installed. Please install jq: brew install jq (macOS) or apt-get install jq (Linux)"
    exit 1
fi

tmpc="${TMPDIR:-/tmp}/san_count_$$.txt"
: > "$tmpc"
find "$ACTUAL_INPUT_FOLDER" -type f -name "*.json" -print0 | while IFS= read -r -d '' f; do
    jq 'del(..|._id?, .scraped_at?)' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
    echo 1 >> "$tmpc"
done
SANITIZED_COUNT=$(wc -l < "$tmpc" | tr -d ' ')
rm -f "$tmpc"
echo "✅ Sanitized $SANITIZED_COUNT files"

echo ""
echo "🚀 Running formatter..."
echo ""

# Run the formatter
cd "$SCRIPT_DIR"
export PIPENV_PIPFILE="$SCRIPT_DIR/Pipfile"

$PIPENV_CMD run python main.py \
    --state "$STATE" \
    --openstates-data-folder "$ACTUAL_INPUT_FOLDER" \
    --git-repo-folder "$OUTPUT_FOLDER"

echo ""
echo "✅ Formatting complete! Output saved to: $OUTPUT_FOLDER"

