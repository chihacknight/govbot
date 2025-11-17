#!/bin/bash
# Script to test GitHub Actions workflows locally using act

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKFLOWS_DIR="$(cd "$SCRIPT_DIR/../workflows" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🧪 GitHub Actions Workflow Tester"
echo "=================================="
echo ""

# Check if act is installed
if ! command -v act &> /dev/null; then
    echo -e "${RED}❌ act is not installed${NC}"
    echo "Install it with: brew install act"
    exit 1
fi

echo -e "${GREEN}✅ act is installed${NC}"

# Check if Docker is running
if ! docker ps &> /dev/null; then
    echo -e "${YELLOW}⚠️  Docker is not running${NC}"
    echo "Please start Docker Desktop and try again"
    exit 1
fi

echo -e "${GREEN}✅ Docker is running${NC}"
echo ""

# Function to test a workflow
test_workflow() {
    local workflow_file="$1"
    local workflow_name=$(basename "$workflow_file" .yml)
    
    echo -e "${YELLOW}Testing: $workflow_name${NC}"
    echo "----------------------------------------"
    
    # List available jobs
    echo "📋 Available jobs:"
    act workflow_dispatch -W "$workflow_file" --list 2>&1 | grep -E "Job ID|test-" || true
    echo ""
    
    # Try to run with dry-run first to validate syntax
    echo "🔍 Validating workflow syntax..."
    if act workflow_dispatch -W "$workflow_file" --dryrun --container-architecture linux/amd64 &> /dev/null; then
        echo -e "${GREEN}✅ Workflow syntax is valid${NC}"
    else
        echo -e "${RED}❌ Workflow syntax validation failed${NC}"
        return 1
    fi
    echo ""
}

# Function to run a workflow
run_workflow() {
    local workflow_file="$1"
    local workflow_name=$(basename "$workflow_file" .yml)
    
    echo -e "${YELLOW}Running: $workflow_name${NC}"
    echo "----------------------------------------"
    
    # Check if GITHUB_TOKEN is set
    if [ -z "${GITHUB_TOKEN:-}" ]; then
        echo -e "${YELLOW}⚠️  GITHUB_TOKEN not set, using dummy token for testing${NC}"
        export GITHUB_TOKEN="test_token_$(date +%s)"
    fi
    
    cd "$REPO_ROOT"
    
    # Run the workflow
    act workflow_dispatch \
        -W "$workflow_file" \
        --secret "GITHUB_TOKEN=$GITHUB_TOKEN" \
        --container-architecture linux/amd64 \
        --verbose 2>&1 | tee "/tmp/act-${workflow_name}.log"
    
    local exit_code=${PIPESTATUS[0]}
    
    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}✅ Workflow completed successfully${NC}"
    else
        echo -e "${RED}❌ Workflow failed (exit code: $exit_code)${NC}"
        echo "Check log: /tmp/act-${workflow_name}.log"
    fi
    
    echo ""
    return $exit_code
}

# Main menu
show_menu() {
    echo "Available workflows:"
    echo ""
    local i=1
    for workflow in "$WORKFLOWS_DIR"/*.yml; do
        if [ -f "$workflow" ]; then
            echo "  $i) $(basename "$workflow")"
            ((i++))
        fi
    done
    echo "  $i) Test all workflows (validate only)"
    ((i++))
    echo "  $i) Exit"
    echo ""
}

# Parse command line arguments
if [ $# -eq 0 ]; then
    # Interactive mode
    while true; do
        show_menu
        read -p "Select workflow to test (or 'all' to test all): " choice
        
        case "$choice" in
            [1-9]|[1-9][0-9])
                workflows=("$WORKFLOWS_DIR"/*.yml)
                if [ "$choice" -le "${#workflows[@]}" ]; then
                    selected="${workflows[$((choice-1))]}"
                    if [ -f "$selected" ]; then
                        test_workflow "$selected"
                        read -p "Run this workflow? (y/n): " run_choice
                        if [[ "$run_choice" =~ ^[Yy]$ ]]; then
                            run_workflow "$selected"
                        fi
                    fi
                elif [ "$choice" -eq $((${#workflows[@]}+1)) ]; then
                    # Test all (validate only)
                    echo "🔍 Validating all workflows..."
                    for workflow in "$WORKFLOWS_DIR"/*.yml; do
                        if [ -f "$workflow" ]; then
                            test_workflow "$workflow"
                        fi
                    done
                elif [ "$choice" -eq $((${#workflows[@]}+2)) ]; then
                    exit 0
                fi
                ;;
            all|a)
                echo "🔍 Validating all workflows..."
                for workflow in "$WORKFLOWS_DIR"/*.yml; do
                    if [ -f "$workflow" ]; then
                        test_workflow "$workflow"
                    fi
                done
                ;;
            q|quit|exit)
                exit 0
                ;;
            *)
                echo "Invalid choice"
                ;;
        esac
    done
else
    # Command line mode
    case "$1" in
        list)
            echo "Available workflows:"
            for workflow in "$WORKFLOWS_DIR"/*.yml; do
                if [ -f "$workflow" ]; then
                    echo "  - $(basename "$workflow")"
                fi
            done
            ;;
        validate|check)
            if [ -n "${2:-}" ]; then
                workflow="$WORKFLOWS_DIR/$2"
                if [ -f "$workflow" ]; then
                    test_workflow "$workflow"
                else
                    echo "Workflow not found: $2"
                    exit 1
                fi
            else
                echo "Validating all workflows..."
                for workflow in "$WORKFLOWS_DIR"/*.yml; do
                    if [ -f "$workflow" ]; then
                        test_workflow "$workflow"
                    fi
                done
            fi
            ;;
        run)
            if [ -z "${2:-}" ]; then
                echo "Usage: $0 run <workflow-name>"
                exit 1
            fi
            workflow="$WORKFLOWS_DIR/$2"
            if [ -f "$workflow" ]; then
                run_workflow "$workflow"
            else
                echo "Workflow not found: $2"
                exit 1
            fi
            ;;
        *)
            echo "Usage: $0 [list|validate|run] [workflow-name]"
            echo ""
            echo "Commands:"
            echo "  list                    - List all available workflows"
            echo "  validate [workflow]     - Validate workflow syntax"
            echo "  run <workflow>          - Run a workflow"
            echo ""
            echo "Examples:"
            echo "  $0 list"
            echo "  $0 validate test-sources-recent-items.yml"
            echo "  $0 run test-sources-recent-items.yml"
            exit 1
            ;;
    esac
fi

