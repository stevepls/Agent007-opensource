#!/bin/bash
# Quick Railway Environment Variables Setup
# Sets all variables from .env file in one command
#
# Usage:
#   ./scripts/setup_railway_env_quick.sh
#   ./scripts/setup_railway_env_quick.sh .env

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCHESTRATOR_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="${1:-$ORCHESTRATOR_DIR/.env}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}🚀 Quick Railway Environment Variables Setup${NC}"
echo ""

# Check Railway CLI
if ! command -v railway &> /dev/null; then
    echo -e "${RED}❌ Railway CLI not found!${NC}"
    echo "Install: https://docs.railway.app/develop/cli"
    exit 1
fi

# Check login
if ! railway whoami &> /dev/null; then
    echo -e "${YELLOW}⚠️  Not logged in. Please login:${NC}"
    railway login
fi

# Check project link
if [ ! -f "$ORCHESTRATOR_DIR/.railway" ]; then
    echo -e "${YELLOW}⚠️  Not linked to project. Linking...${NC}"
    railway link
fi

# Check .env file
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}❌ .env file not found: $ENV_FILE${NC}"
    exit 1
fi

echo -e "${BLUE}📋 Reading variables from: $ENV_FILE${NC}"
echo ""

# Variables to set (from RAILWAY_DEPLOYMENT.md)
REQUIRED_VARS=(
    "ANTHROPIC_API_KEY"
    "SLACK_USER_TOKEN"
    "CLICKUP_API_TOKEN"
)

OPTIONAL_VARS=(
    "OPENAI_API_KEY"
    "GITHUB_TOKEN"
    "HUBSTAFF_API_TOKEN"
    "HUBSTAFF_ORG_ID"
    "SLACK_BOT_TOKEN"
    "HARVEST_ACCESS_TOKEN"
    "HARVEST_ACCOUNT_ID"
    "DEFAULT_MODEL"
    "REQUIRE_APPROVAL"
)

# Build Railway CLI command
RAILWAY_CMD="railway variables"

# Function to read value from .env
get_env_value() {
    local key=$1
    grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2- | sed 's/^"//;s/"$//' | head -1
}

# Collect variables to set
VARS_TO_SET=()

echo -e "${BLUE}=== Required Variables ===${NC}"
for key in "${REQUIRED_VARS[@]}"; do
    value=$(get_env_value "$key")
    if [ -z "$value" ]; then
        echo -e "${YELLOW}⚠️  $key not found in .env - SKIPPING${NC}"
    else
        echo -e "${GREEN}✅ Found $key${NC}"
        VARS_TO_SET+=("--set" "${key}=${value}")
    fi
done

echo ""
echo -e "${BLUE}=== Optional Variables ===${NC}"
for key in "${OPTIONAL_VARS[@]}"; do
    value=$(get_env_value "$key")
    if [ -n "$value" ]; then
        echo -e "${GREEN}✅ Found $key${NC}"
        VARS_TO_SET+=("--set" "${key}=${value}")
    fi
done

echo ""
if [ ${#VARS_TO_SET[@]} -eq 0 ]; then
    echo -e "${RED}❌ No variables found to set!${NC}"
    exit 1
fi

echo -e "${BLUE}📤 Setting ${#VARS_TO_SET[@]/2} variables in Railway...${NC}"
echo ""

# Execute Railway command
if railway variables "${VARS_TO_SET[@]}"; then
    echo ""
    echo -e "${GREEN}✅ Successfully set all variables!${NC}"
    echo ""
    echo -e "${BLUE}Verify with:${NC}"
    echo "  railway variables"
else
    echo ""
    echo -e "${RED}❌ Failed to set variables${NC}"
    exit 1
fi
