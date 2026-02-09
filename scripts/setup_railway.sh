#!/bin/bash
#
# Agent007 Railway Infrastructure Setup
# Creates project, services, environments, and configures deployment
#
# Usage:
#   ./scripts/setup_railway.sh              # Full setup
#   ./scripts/setup_railway.sh --env-only   # Just set environment variables
#   ./scripts/setup_railway.sh --status     # Check current status
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCHESTRATOR_DIR="$PROJECT_ROOT/Orchestrator"
DASHBOARD_DIR="$PROJECT_ROOT/dashboard"
ENV_FILE="$ORCHESTRATOR_DIR/.env"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warn()    { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error()   { echo -e "${RED}❌ $1${NC}"; }
log_header()  { echo -e "\n${BOLD}${CYAN}═══════════════════════════════════════════${NC}"; echo -e "${BOLD}${CYAN}  $1${NC}"; echo -e "${BOLD}${CYAN}═══════════════════════════════════════════${NC}\n"; }

# ============================================================================
# Prerequisites
# ============================================================================
check_prerequisites() {
    log_header "Checking Prerequisites"

    # Railway CLI
    if ! command -v railway &> /dev/null; then
        log_error "Railway CLI not installed!"
        echo "  Install: npm install -g @railway/cli"
        echo "  Or: curl -fsSL https://railway.app/install.sh | sh"
        exit 1
    fi
    log_success "Railway CLI found ($(railway --version 2>/dev/null || echo 'unknown'))"

    # Authentication
    if ! railway whoami &> /dev/null 2>&1; then
        log_warn "Not logged in to Railway"
        log_info "Starting browserless login..."
        railway login --browserless
        if ! railway whoami &> /dev/null 2>&1; then
            log_error "Login failed. Please try: railway login"
            exit 1
        fi
    fi
    RAILWAY_USER=$(railway whoami 2>/dev/null || echo "unknown")
    log_success "Logged in as: $RAILWAY_USER"

    # Git
    if ! command -v git &> /dev/null; then
        log_error "Git not installed"
        exit 1
    fi
    log_success "Git found"

    # Check for .env file
    if [ -f "$ENV_FILE" ]; then
        log_success "Found .env file at $ENV_FILE"
    else
        log_warn "No .env file found - will need manual variable configuration"
    fi
}

# ============================================================================
# Helper: read value from .env
# ============================================================================
get_env_value() {
    local key=$1
    if [ -f "$ENV_FILE" ]; then
        grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d '=' -f2- | sed 's/^"//;s/"$//' || true
    fi
}

# ============================================================================
# Create Project
# ============================================================================
create_project() {
    log_header "Creating Railway Project"

    # Check if we already have a project linked
    if railway status &> /dev/null 2>&1; then
        log_success "Already linked to a Railway project"
        railway status
        echo ""
        read -p "Use this project? (Y/n): " use_existing
        if [[ "$use_existing" =~ ^[Nn]$ ]]; then
            log_info "Unlinking current project..."
            railway unlink
        else
            return 0
        fi
    fi

    log_info "Creating new Railway project: Agent007"
    railway init --name "Agent007" 2>/dev/null || {
        log_warn "Could not create project automatically."
        log_info "Please select or create a project:"
        railway link
    }
    log_success "Project created/linked"
}

# ============================================================================
# Create Services
# ============================================================================
create_services() {
    log_header "Creating Services"

    # --- Orchestrator Service (Python/FastAPI) ---
    log_info "Creating Orchestrator service (Python/FastAPI backend)..."
    railway add --service "orchestrator" 2>/dev/null || true
    log_success "Orchestrator service ensured (if it already existed, Railway kept it)"

    # --- Dashboard Service (Next.js) ---
    log_info "Creating Dashboard service (Next.js frontend)..."
    railway add --service "dashboard" 2>/dev/null || true
    log_success "Dashboard service ensured (if it already existed, Railway kept it)"

    log_success "Services configured"
}

# ============================================================================
# Configure Orchestrator Environment Variables
# ============================================================================
configure_orchestrator_env() {
    log_header "Configuring Orchestrator Environment Variables"

    log_info "Selecting orchestrator service context..."
    railway service link orchestrator 2>/dev/null || true

    # Required variables
    declare -A REQUIRED=(
        ["ANTHROPIC_API_KEY"]="Anthropic API key for Claude LLM"
        ["CLICKUP_API_TOKEN"]="ClickUp API token for task management"
        ["SLACK_USER_TOKEN"]="Slack user token (xoxp-...) for team check-in"
    )

    # Optional variables
    declare -A OPTIONAL=(
        ["OPENAI_API_KEY"]="OpenAI API key (fallback LLM)"
        ["SLACK_BOT_TOKEN"]="Slack bot token (xoxb-...)"
        ["SLACK_APP_TOKEN"]="Slack app token (xapp-...)"
        ["SLACK_SIGNING_SECRET"]="Slack signing secret"
        ["GITHUB_TOKEN"]="GitHub token for activity checking"
        ["HUBSTAFF_API_TOKEN"]="Hubstaff API token"
        ["HUBSTAFF_ORG_ID"]="Hubstaff organization ID"
        ["HARVEST_ACCESS_TOKEN"]="Harvest access token"
        ["HARVEST_ACCOUNT_ID"]="Harvest account ID"
        ["ZENDESK_EMAIL"]="Zendesk email"
        ["ZENDESK_API_TOKEN"]="Zendesk API token"
        ["ZENDESK_SUBDOMAIN"]="Zendesk subdomain"
        ["CLICKUP_DEFAULT_LIST_ID"]="ClickUp default list ID"
        ["CLICKUP_MLN_LIST_ID"]="ClickUp MLN list ID"
        ["AIRTABLE_PERSONAL_ACCESS_TOKEN"]="Airtable personal access token"
        ["AIRTABLE_BASE_ID"]="Airtable base ID"
        ["AIRTABLE_TABLE_ID"]="Airtable table ID"
        ["ASANA_PERSONAL_ACCESS_TOKEN"]="Asana personal access token"
        ["DEFAULT_MODEL"]="Default LLM model"
        ["REQUIRE_APPROVAL"]="Require approval for actions (true/false)"
    )

    local vars_set=0
    local vars_skipped=0

    # Set required variables
    echo -e "\n${BOLD}Required Variables:${NC}"
    for key in "ANTHROPIC_API_KEY" "CLICKUP_API_TOKEN" "SLACK_USER_TOKEN"; do
        desc="${REQUIRED[$key]}"
        value=$(get_env_value "$key")
        if [ -n "$value" ]; then
            railway variables --service orchestrator --set "${key}=${value}" --skip-deploys 2>/dev/null && {
                log_success "Set $key"
                ((vars_set++))
            } || log_error "Failed to set $key"
        else
            log_warn "MISSING: $key ($desc) - not found in .env"
            ((vars_skipped++))
        fi
    done

    # Set optional variables (only if they exist in .env)
    echo -e "\n${BOLD}Optional Variables:${NC}"
    for key in "${!OPTIONAL[@]}"; do
        value=$(get_env_value "$key")
        if [ -n "$value" ]; then
            railway variables --service orchestrator --set "${key}=${value}" --skip-deploys 2>/dev/null && {
                log_success "Set $key"
                ((vars_set++))
            } || log_error "Failed to set $key"
        fi
    done

    echo ""
    log_info "Orchestrator: $vars_set variables set, $vars_skipped skipped"
}

# ============================================================================
# Configure Dashboard Environment Variables
# ============================================================================
configure_dashboard_env() {
    log_header "Configuring Dashboard Environment Variables"

    log_info "Selecting dashboard service context..."
    railway service link dashboard 2>/dev/null || true

    # The dashboard needs to know the orchestrator's internal URL
    # Railway provides internal networking via $RAILWAY_PRIVATE_DOMAIN
    # The actual URL will be set after both services are deployed
    
    declare -A DASHBOARD_VARS=(
        ["ANTHROPIC_API_KEY"]="Anthropic API key (fallback)"
        ["OPENAI_API_KEY"]="OpenAI API key (fallback)"
    )

    local vars_set=0

    for key in "${!DASHBOARD_VARS[@]}"; do
        value=$(get_env_value "$key")
        if [ -n "$value" ]; then
            railway variables --service dashboard --set "${key}=${value}" --skip-deploys 2>/dev/null && {
                log_success "Set $key"
                ((vars_set++))
            } || log_error "Failed to set $key"
        fi
    done

    # Set ORCHESTRATOR_API_URL placeholder (will be updated after deploy)
    railway variables --service dashboard --set "ORCHESTRATOR_API_URL=http://orchestrator.railway.internal:8502" --skip-deploys 2>/dev/null && {
        log_success "Set ORCHESTRATOR_API_URL (internal networking)"
    } || log_warn "Could not set ORCHESTRATOR_API_URL"

    # Set PORT for Next.js
    railway variables --service dashboard --set "PORT=3000" --skip-deploys 2>/dev/null && {
        log_success "Set PORT=3000"
    } || true

    log_info "Dashboard: $vars_set variables set"
}

# ============================================================================
# Configure Build Settings
# ============================================================================
configure_build_settings() {
    log_header "Configuring Build Settings"

    # Orchestrator - set root directory and start command
    log_info "Configuring Orchestrator build..."
    railway variables --service orchestrator --set "RAILWAY_ROOT_DIRECTORY=Orchestrator" --skip-deploys 2>/dev/null && {
        log_success "Set RAILWAY_ROOT_DIRECTORY=Orchestrator"
    } || log_warn "Could not set RAILWAY_ROOT_DIRECTORY for orchestrator"

    # Dashboard - set root directory
    log_info "Configuring Dashboard build..."
    railway variables --service dashboard --set "RAILWAY_ROOT_DIRECTORY=dashboard" --skip-deploys 2>/dev/null && {
        log_success "Set RAILWAY_ROOT_DIRECTORY=dashboard"
    } || log_warn "Could not set RAILWAY_ROOT_DIRECTORY for dashboard"
}

# ============================================================================
# Generate Domains
# ============================================================================
generate_domains() {
    log_header "Generating Domains"

    # Orchestrator domain
    log_info "Generating domain for orchestrator..."
    railway domain --service orchestrator 2>/dev/null && {
        log_success "Orchestrator domain generated"
    } || log_warn "Could not generate orchestrator domain (may already exist)"

    # Dashboard domain
    log_info "Generating domain for dashboard..."
    railway domain --service dashboard 2>/dev/null && {
        log_success "Dashboard domain generated"
    } || log_warn "Could not generate dashboard domain (may already exist)"
}

# ============================================================================
# Create Environments
# ============================================================================
create_environments() {
    log_header "Setting Up Environments"

    # Check if staging environment exists
    log_info "Creating staging environment..."
    railway environment new staging 2>/dev/null && {
        log_success "Staging environment created"
    } || log_warn "Staging environment may already exist"

    log_info "Production environment is default"
    log_success "Environments configured"
}

# ============================================================================
# Deploy
# ============================================================================
deploy_services() {
    log_header "Deploying Services"

    log_info "Deploying orchestrator..."
    cd "$PROJECT_ROOT"
    railway up --service orchestrator 2>/dev/null && {
        log_success "Orchestrator deployment triggered"
    } || log_warn "Could not trigger orchestrator deployment"

    log_info "Deploying dashboard..."
    railway up --service dashboard 2>/dev/null && {
        log_success "Dashboard deployment triggered"
    } || log_warn "Could not trigger dashboard deployment"

    cd "$SCRIPT_DIR"
}

# ============================================================================
# Status Check
# ============================================================================
show_status() {
    log_header "Railway Project Status"
    
    railway status 2>/dev/null || {
        log_error "Not linked to a project. Run: ./scripts/setup_railway.sh"
        return 1
    }

    echo ""
    log_info "Services:"
    railway service status --all 2>/dev/null || echo "  (could not list services via service status)"

    echo ""
    log_info "Orchestrator Variables:"
    railway variables --service orchestrator 2>/dev/null | head -20 || echo "  (could not list orchestrator variables)"

    echo ""
    log_info "Dashboard Variables:"
    railway variables --service dashboard 2>/dev/null | head -20 || echo "  (could not list dashboard variables)"
}

# ============================================================================
# Print Summary
# ============================================================================
print_summary() {
    log_header "Setup Complete! 🚀"

    echo -e "${BOLD}Project Structure:${NC}"
    echo "  📦 Agent007 (Railway Project)"
    echo "  ├── 🐍 orchestrator (Python/FastAPI)"
    echo "  │   ├── Root: Orchestrator/"
    echo "  │   ├── Build: NIXPACKS (auto-detect Python)"
    echo "  │   ├── Start: uvicorn api:app --host 0.0.0.0 --port \$PORT"
    echo "  │   └── Health: /health"
    echo "  └── ⚛️  dashboard (Next.js)"
    echo "      ├── Root: dashboard/"
    echo "      ├── Build: NIXPACKS (npm install && npm run build)"
    echo "      ├── Start: npm start"
    echo "      └── Health: /"
    echo ""
    echo -e "${BOLD}Networking:${NC}"
    echo "  Dashboard → Orchestrator: http://orchestrator.railway.internal:8502"
    echo ""
    echo -e "${BOLD}Next Steps:${NC}"
    echo "  1. Connect GitHub repo in Railway dashboard (Settings → Source)"
    echo "  2. Set root directories per service if not auto-detected"
    echo "  3. Verify environment variables: railway variables"
    echo "  4. Check deployments: railway logs"
    echo "  5. Open dashboard: railway open"
    echo ""
    echo -e "${BOLD}Useful Commands:${NC}"
    echo "  railway status          # Project status"
    echo "  railway logs            # View deploy logs"
    echo "  railway open            # Open Railway dashboard"
    echo "  railway variables       # List variables"
    echo "  railway up              # Deploy from local"
    echo ""
}

# ============================================================================
# Main
# ============================================================================
main() {
    echo -e "${BOLD}${CYAN}"
    echo "╔═══════════════════════════════════════════════════════╗"
    echo "║          🚀 Agent007 Railway Setup                    ║"
    echo "║          Infrastructure & Deployment                  ║"
    echo "╚═══════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    case "${1:-}" in
        --status)
            show_status
            exit 0
            ;;
        --env-only)
            check_prerequisites
            configure_orchestrator_env
            configure_dashboard_env
            exit 0
            ;;
        --deploy)
            check_prerequisites
            deploy_services
            exit 0
            ;;
        *)
            ;;
    esac

    # Full setup
    check_prerequisites
    create_project
    create_services
    configure_build_settings
    configure_orchestrator_env
    configure_dashboard_env
    generate_domains
    create_environments
    print_summary
}

main "$@"
