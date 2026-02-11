#!/bin/bash
# Setup Railway Environment Variables
# This script sets all required environment variables in Railway using the Railway CLI
#
# Usage:
#   ./scripts/setup_railway_env.sh
#   ./scripts/setup_railway_env.sh --from-env .env
#   ./scripts/setup_railway_env.sh --interactive

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCHESTRATOR_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ORCHESTRATOR_DIR/.env"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if Railway CLI is installed
check_railway_cli() {
    if ! command -v railway &> /dev/null; then
        print_error "Railway CLI is not installed!"
        echo "Install it from: https://docs.railway.app/develop/cli"
        exit 1
    fi
    print_success "Railway CLI found"
}

# Check if logged in to Railway
check_railway_login() {
    if ! railway whoami &> /dev/null; then
        print_warning "Not logged in to Railway"
        print_info "Logging in..."
        railway login
    else
        print_success "Logged in to Railway"
        railway whoami
    fi
}

# Link to Railway project (if not already linked)
link_project() {
    if [ ! -f "$ORCHESTRATOR_DIR/.railway" ]; then
        print_warning "Not linked to a Railway project"
        print_info "Linking to Railway project..."
        echo "Enter your Railway project ID (or press Enter to select from list):"
        read -r project_id
        if [ -z "$project_id" ]; then
            railway link
        else
            railway link "$project_id"
        fi
    else
        print_success "Already linked to Railway project"
    fi
}

# Set a single variable in Railway
set_railway_var() {
    local key=$1
    local value=$2
    local description=$3
    
    if [ -z "$value" ]; then
        print_warning "Skipping $key (empty value)"
        return
    fi
    
    print_info "Setting $key..."
    # Railway CLI syntax: railway variables --set "KEY=VALUE"
    if railway variables --set "${key}=${value}" &> /dev/null; then
        print_success "Set $key"
        if [ -n "$description" ]; then
            echo "   $description"
        fi
    else
        print_error "Failed to set $key"
        return 1
    fi
}

# Read value from .env file
read_from_env() {
    local key=$1
    if [ -f "$ENV_FILE" ]; then
        grep -E "^${key}=" "$ENV_FILE" | cut -d '=' -f2- | sed 's/^"//;s/"$//' | head -1
    fi
}

# Prompt for a value
prompt_for_value() {
    local key=$1
    local description=$2
    local default=$3
    
    if [ -n "$default" ]; then
        echo -n "Enter $key [$description] (default: ${default:0:20}...): "
    else
        echo -n "Enter $key [$description]: "
    fi
    read -r value
    echo "${value:-$default}"
}

# Main function to set all variables
set_all_variables() {
    local mode=$1  # "from-env", "interactive", or "auto"
    
    print_info "Setting environment variables in Railway..."
    echo ""
    
    # Required variables
    declare -A REQUIRED_VARS=(
        ["ANTHROPIC_API_KEY"]="Anthropic API key for Claude LLM (REQUIRED)"
        ["SLACK_USER_TOKEN"]="Slack user token for team check-in (REQUIRED)"
        ["CLICKUP_API_TOKEN"]="ClickUp API token for team check-in (REQUIRED)"
    )
    
    # Optional variables
    declare -A OPTIONAL_VARS=(
        ["OPENAI_API_KEY"]="OpenAI API key (fallback LLM)"
        ["GITHUB_TOKEN"]="GitHub token for activity checking"
        ["HUBSTAFF_API_TOKEN"]="Hubstaff API token for time tracking"
        ["HUBSTAFF_ORG_ID"]="Hubstaff organization ID"
        ["SLACK_BOT_TOKEN"]="Slack bot token"
        ["HARVEST_ACCESS_TOKEN"]="Harvest access token"
        ["HARVEST_ACCOUNT_ID"]="Harvest account ID"
        ["ZENDESK_EMAIL"]="Zendesk agent email"
        ["ZENDESK_API_TOKEN"]="Zendesk API token"
        ["ZENDESK_SUBDOMAIN"]="Zendesk subdomain (e.g. yourcompany)"
        ["GOOGLE_CREDENTIALS_JSON"]="Google OAuth credentials.json (raw JSON or base64)"
        ["GOOGLE_TOKEN_JSON"]="Google OAuth unified_token.json (raw JSON or base64)"
        ["DEFAULT_MODEL"]="Default LLM model (default: claude-opus-4-20250514)"
        ["REQUIRE_APPROVAL"]="Require approval for file writes (default: true)"
    )
    
    # Set required variables
    print_info "=== Required Variables ==="
    for key in "${!REQUIRED_VARS[@]}"; do
        description="${REQUIRED_VARS[$key]}"
        value=""
        
        case "$mode" in
            "from-env")
                value=$(read_from_env "$key")
                ;;
            "interactive")
                default=$(read_from_env "$key")
                value=$(prompt_for_value "$key" "$description" "$default")
                ;;
            "auto")
                value=$(read_from_env "$key")
                if [ -z "$value" ]; then
                    print_warning "$key not found in .env, skipping"
                    continue
                fi
                ;;
        esac
        
        if [ -z "$value" ] && [ "$mode" != "auto" ]; then
            print_error "$key is required but not provided!"
            continue
        fi
        
        set_railway_var "$key" "$value" "$description"
    done
    
    echo ""
    
    # Set optional variables
    print_info "=== Optional Variables ==="
    for key in "${!OPTIONAL_VARS[@]}"; do
        description="${OPTIONAL_VARS[$key]}"
        value=""
        
        case "$mode" in
            "from-env")
                value=$(read_from_env "$key")
                ;;
            "interactive")
                default=$(read_from_env "$key")
                if [ "$key" == "DEFAULT_MODEL" ] && [ -z "$default" ]; then
                    default="claude-opus-4-20250514"
                fi
                if [ "$key" == "REQUIRE_APPROVAL" ] && [ -z "$default" ]; then
                    default="true"
                fi
                echo -n "Set $key? (y/N): "
                read -r answer
                if [[ "$answer" =~ ^[Yy]$ ]]; then
                    value=$(prompt_for_value "$key" "$description" "$default")
                fi
                ;;
            "auto")
                value=$(read_from_env "$key")
                ;;
        esac
        
        if [ -n "$value" ]; then
            set_railway_var "$key" "$value" "$description"
        fi
    done
}

# Main execution
main() {
    echo "=========================================="
    echo "🚀 Railway Environment Variables Setup"
    echo "=========================================="
    echo ""
    
    # Parse arguments
    MODE="interactive"
    if [ "$1" == "--from-env" ]; then
        MODE="from-env"
        if [ -n "$2" ]; then
            ENV_FILE="$2"
        fi
    elif [ "$1" == "--interactive" ]; then
        MODE="interactive"
    elif [ "$1" == "--auto" ]; then
        MODE="auto"
    fi
    
    # Check prerequisites
    check_railway_cli
    check_railway_login
    link_project
    
    echo ""
    
    # Set variables
    set_all_variables "$MODE"
    
    echo ""
    print_success "Environment variables setup complete!"
    echo ""
    print_info "Verify variables in Railway dashboard or run:"
    echo "  railway variables"
    echo ""
    print_info "To view a specific variable:"
    echo "  railway variables get ANTHROPIC_API_KEY"
}

# Run main function
main "$@"
