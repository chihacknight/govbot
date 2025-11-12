#!/bin/bash
# Quick workflow validation script (doesn't require Docker)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKFLOWS_DIR="$(cd "$SCRIPT_DIR/../workflows" && pwd)"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "🔍 Validating GitHub Actions Workflows"
echo "======================================"
echo ""

# Check if yq is available for YAML validation
if command -v yq &> /dev/null; then
    USE_YQ=true
else
    USE_YQ=false
    echo -e "${YELLOW}⚠️  yq not found - using basic YAML validation${NC}"
    echo ""
fi

# Check if act is available for workflow validation
if command -v act &> /dev/null; then
    USE_ACT=true
else
    USE_ACT=false
    echo -e "${YELLOW}⚠️  act not found - skipping workflow-specific validation${NC}"
    echo ""
fi

validate_yaml() {
    local file="$1"
    
    if [ "$USE_YQ" = true ]; then
        if yq eval '.' "$file" > /dev/null 2>&1; then
            return 0
        else
            return 1
        fi
    else
        # Basic check - just verify it's valid YAML-like
        if grep -q "^name:" "$file" && grep -q "^on:" "$file"; then
            return 0
        else
            return 1
        fi
    fi
}

validate_workflow() {
    local workflow_file="$1"
    local workflow_name=$(basename "$workflow_file")
    
    echo -n "Validating $workflow_name... "
    
    # Check file exists
    if [ ! -f "$workflow_file" ]; then
        echo -e "${RED}❌ File not found${NC}"
        return 1
    fi
    
    # Validate YAML syntax
    if ! validate_yaml "$workflow_file"; then
        echo -e "${RED}❌ Invalid YAML syntax${NC}"
        return 1
    fi
    
    # Validate with act if available
    if [ "$USE_ACT" = true ]; then
        if act workflow_dispatch -W "$workflow_file" --list &> /dev/null; then
            echo -e "${GREEN}✅ Valid${NC}"
            return 0
        else
            echo -e "${YELLOW}⚠️  YAML valid but act validation failed${NC}"
            return 1
        fi
    else
        echo -e "${GREEN}✅ Valid YAML${NC}"
        return 0
    fi
}

# Validate all workflows
failed=0
total=0

for workflow in "$WORKFLOWS_DIR"/*.yml; do
    if [ -f "$workflow" ]; then
        ((total++))
        if ! validate_workflow "$workflow"; then
            ((failed++))
        fi
    fi
done

echo ""
echo "======================================"
if [ $failed -eq 0 ]; then
    echo -e "${GREEN}✅ All workflows validated successfully ($total/$total)${NC}"
    exit 0
else
    echo -e "${RED}❌ Validation failed ($failed/$total workflows have issues)${NC}"
    exit 1
fi

