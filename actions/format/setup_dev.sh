#!/usr/bin/env bash
set -euo pipefail

# Development environment setup script for the format action
# This script ensures all required dependencies are installed

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🔧 Setting up development environment for format action..."
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.11 or later."
    echo "   macOS: brew install python@3.11"
    echo "   Linux: sudo apt-get install python3 python3-pip"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "✅ Python found: $PYTHON_VERSION"

# Check/install pipenv
if ! python3 -m pipenv --version &> /dev/null; then
    echo "📥 Installing pipenv..."
    python3 -m pip install --user pipenv
    if ! python3 -m pipenv --version &> /dev/null; then
        echo "❌ pipenv installation failed"
        exit 1
    fi
else
    echo "✅ pipenv already installed"
fi

PIPENV_VERSION=$(python3 -m pipenv --version)
echo "   $PIPENV_VERSION"
echo ""

# Check jq
if ! command -v jq &> /dev/null; then
    echo "📥 jq not found. Installing jq..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &> /dev/null; then
            brew install jq
        else
            echo "❌ Homebrew not found. Please install jq manually:"
            echo "   brew install jq"
            exit 1
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if command -v apt-get &> /dev/null; then
            sudo apt-get update && sudo apt-get install -y jq
        elif command -v yum &> /dev/null; then
            sudo yum install -y jq
        else
            echo "❌ Package manager not found. Please install jq manually"
            exit 1
        fi
    else
        echo "❌ Unsupported OS. Please install jq manually"
        exit 1
    fi
else
    echo "✅ jq already installed"
fi

JQ_VERSION=$(jq --version)
echo "   $JQ_VERSION"
echo ""

# Install Python dependencies
echo "📦 Installing Python dependencies..."
export PIPENV_VENV_IN_PROJECT=1
export PIPENV_IGNORE_VIRTUALENVS=1
export PIPENV_PIPFILE="$SCRIPT_DIR/Pipfile"

python3 -m pipenv install --dev

echo ""
echo "✅ Development environment setup complete!"
echo ""
echo "You can now run:"
echo "  ./render_snapshot.sh"
echo ""

