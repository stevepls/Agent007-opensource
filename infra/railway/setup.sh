#!/bin/bash
# ============================================================================
# Agent007 - Railway Multi-Service Project Setup
# ============================================================================
# Sets up a Railway project with three services:
#   1. Orchestrator  (Python/FastAPI)
#   2. Dashboard     (Next.js)
#   3. SyncAudit     (Python/FastAPI)
#
# Usage:
#   ./infra/railway/setup.sh                 # Full interactive setup
#   ./infra/railway/setup.sh --env staging   # Load staging env vars
#   ./infra/railway/setup.sh --env production
#   ./infra/railway/setup.sh --status        # Check deployment status
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${BLUE}ℹ  $1${NC}"; }
success() { echo -e "${GREEN}✅ $1${NC}"; }
warn()    { echo -e "${YELLOW}⚠️  $1${NC}"; }
error()   { echo -e "${RED}❌ $1${NC}"; }
header()  { echo -e "\n${BOLD}${CYAN}═══ $1 ═══${NC}\n"; }

# ============================================================================
# Service definitions
# ============================================================================
declare -A SERVICES
SERVICES[orchestrator]="$ROOT_DIR/Orchestrator"
SERVICES[dashboard]="$ROOT_DIR/dashboard"
SERVICES[syncaudit]="$ROOT_DIR/SyncAudit"

# Per-service required env vars
declare -A SERVICE_REQUIRED_VARS
SERVICE_REQUIRED_VARS[orchestrator]="ANTHROPIC_API_KEY SLACK_USER_TOKEN CLICKUP_API_TOKEN"
SERVICE_REQUIRED_VARS[dashboard]="ORCHESTRATOR_API_URL"
SERVICE_REQUIRED_VARS[syncaudit]="API_KEY"

# ============================================================================
# Helpers
# ============================================================================
check_railway_cli() {
    if ! command -v railway &>/dev/null; then
        error "Railway CLI not installed!"
        echo "  Install: curl -fsSL https://railway.app/install.sh | sh"
        echo "  Or:      npm install -g @railway/cli"
        exit 1
    fi
    success "Railway CLI $(railway --version 2>&1 | head -1)"
}

check_railway_auth() {
    if ! railway whoami &>/dev/null 2>&1; then
        warn "Not logged in to Railway"
        info "Running railway login..."
        railway login
    fi
    local user
    user=$(railway whoami 2>&1)
    success "Authenticated as: $user"
}

read_env_var() {
    local file=$1 key=$2
    if [[ -f "$file" ]]; then
        grep -E "^${key}=" "$file" 2>/dev/null | head -1 | cut -d'=' -f2- | sed 's/^"//;s/"$//'
    fi
}

# ============================================================================
# Project setup
# ============================================================================
setup_project() {
    header "Railway Project Setup"

    check_railway_cli
    check_railway_auth

    echo ""
    info "This will create/link a Railway project for Agent007."
    echo ""

    # Check if already linked at root
    if railway status &>/dev/null 2>&1; then
        success "Already linked to a Railway project"
        railway status
    else
        info "Creating new Railway project: agent007"
        railway init --name agent007 2>/dev/null || {
            warn "Project may already exist. Linking..."
            railway link
        }
    fi
}

# ============================================================================
# Service setup (create services in Railway project)
# ============================================================================
setup_services() {
    header "Service Configuration"

    for svc in orchestrator dashboard syncaudit; do
        local svc_dir="${SERVICES[$svc]}"
        info "Configuring service: ${BOLD}$svc${NC}"

        if [[ ! -d "$svc_dir" ]]; then
            warn "  Directory not found: $svc_dir — skipping"
            continue
        fi

        # Verify railway.json exists
        if [[ -f "$svc_dir/railway.json" ]]; then
            success "  railway.json exists"
        else
            warn "  No railway.json — creating default"
            create_railway_json "$svc" "$svc_dir"
        fi

        # Verify Procfile exists
        if [[ -f "$svc_dir/Procfile" ]]; then
            success "  Procfile exists"
        else
            warn "  No Procfile — creating default"
            create_procfile "$svc" "$svc_dir"
        fi

        echo ""
    done
}

create_railway_json() {
    local svc=$1 dir=$2
    case "$svc" in
        orchestrator)
            cat > "$dir/railway.json" <<'JSON'
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": { "builder": "NIXPACKS" },
  "deploy": {
    "healthcheckPath": "/health",
    "healthcheckTimeout": 60,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
JSON
            ;;
        dashboard)
            cat > "$dir/railway.json" <<'JSON'
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS",
    "buildCommand": "npm install && npm run build"
  },
  "deploy": {
    "healthcheckPath": "/",
    "healthcheckTimeout": 60,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
JSON
            ;;
        syncaudit)
            cat > "$dir/railway.json" <<'JSON'
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": { "builder": "NIXPACKS" },
  "deploy": {
    "healthcheckPath": "/health",
    "healthcheckTimeout": 60,
    "numReplicas": 1,
    "sleepApplication": false,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
JSON
            ;;
    esac
}

create_procfile() {
    local svc=$1 dir=$2
    case "$svc" in
        orchestrator) echo 'web: uvicorn api:app --host 0.0.0.0 --port $PORT' > "$dir/Procfile" ;;
        dashboard)    echo 'web: npm start' > "$dir/Procfile" ;;
        syncaudit)    echo 'web: uvicorn api.main:app --host 0.0.0.0 --port $PORT' > "$dir/Procfile" ;;
    esac
}

# ============================================================================
# Environment variables
# ============================================================================
set_env_vars() {
    local env_name="${1:-staging}"
    local env_file="$ROOT_DIR/infra/environments/${env_name}.env"
    local local_env=""

    header "Environment Variables — ${env_name^^}"

    if [[ ! -f "$env_file" ]]; then
        error "Environment file not found: $env_file"
        exit 1
    fi

    for svc in orchestrator dashboard syncaudit; do
        local svc_dir="${SERVICES[$svc]}"
        local svc_local_env="$svc_dir/.env"

        info "Setting vars for ${BOLD}$svc${NC}..."

        # Prefer local .env, fall back to env template
        if [[ -f "$svc_local_env" ]]; then
            local_env="$svc_local_env"
            info "  Using local .env from $svc_dir"
        else
            local_env=""
        fi

        # Service-specific required vars
        local required_vars="${SERVICE_REQUIRED_VARS[$svc]}"
        local vars_set=0

        for key in $required_vars; do
            local value=""

            # Try local .env first
            if [[ -n "$local_env" ]]; then
                value=$(read_env_var "$local_env" "$key")
            fi

            # Fall back to environment template
            if [[ -z "$value" ]]; then
                value=$(read_env_var "$env_file" "$key")
            fi

            if [[ -n "$value" ]]; then
                # Would run: railway variables --set "${key}=${value}" --service "$svc"
                # For now, print what would be set
                echo "    railway variables --set \"${key}=<redacted>\" --service $svc"
                ((vars_set++))
            else
                warn "    $key — not found in local .env or $env_name.env"
            fi
        done

        # Also set shared vars
        for key in ENVIRONMENT LOG_LEVEL; do
            local value
            value=$(read_env_var "$env_file" "$key")
            if [[ -n "$value" ]]; then
                echo "    railway variables --set \"${key}=${value}\" --service $svc"
                ((vars_set++))
            fi
        done

        success "  $vars_set variables queued for $svc"
        echo ""
    done

    echo ""
    warn "DRY RUN — Variables printed above are not yet applied."
    echo ""
    echo -e "To apply, re-run with ${BOLD}--apply${NC}:"
    echo "  $0 --env $env_name --apply"
}

apply_env_vars() {
    local env_name="${1:-staging}"
    local env_file="$ROOT_DIR/infra/environments/${env_name}.env"

    header "Applying Variables to Railway — ${env_name^^}"

    if [[ ! -f "$env_file" ]]; then
        error "Environment file not found: $env_file"
        exit 1
    fi

    # Read all non-empty, non-comment lines
    while IFS= read -r line; do
        # Skip empty lines, comments, section headers
        [[ -z "$line" || "$line" =~ ^# || "$line" =~ ^[[:space:]]*$ ]] && continue

        local key="${line%%=*}"
        local value="${line#*=}"

        # Skip template placeholders
        [[ -z "$value" ]] && continue

        info "Setting $key..."
        if railway variables --set "${key}=${value}" 2>/dev/null; then
            success "  $key set"
        else
            warn "  Failed to set $key (service may need to be selected)"
        fi
    done < "$env_file"
}

# ============================================================================
# Status check
# ============================================================================
check_status() {
    header "Agent007 Deployment Status"

    check_railway_cli

    for svc in orchestrator dashboard syncaudit; do
        local svc_dir="${SERVICES[$svc]}"
        echo -e "${BOLD}$svc${NC}"

        # Check local configs
        [[ -f "$svc_dir/railway.json" ]] && echo "  ✅ railway.json" || echo "  ❌ railway.json missing"
        [[ -f "$svc_dir/Procfile" ]]     && echo "  ✅ Procfile"     || echo "  ❌ Procfile missing"

        # Check requirements/package.json
        case "$svc" in
            orchestrator|syncaudit)
                [[ -f "$svc_dir/requirements.txt" ]] && echo "  ✅ requirements.txt" || echo "  ❌ requirements.txt missing"
                ;;
            dashboard)
                [[ -f "$svc_dir/package.json" ]] && echo "  ✅ package.json" || echo "  ❌ package.json missing"
                ;;
        esac

        echo ""
    done

    # Try Railway status
    if railway whoami &>/dev/null 2>&1; then
        info "Railway status:"
        railway status 2>&1 || warn "Not linked to a project"
    else
        warn "Not logged in to Railway"
    fi
}

# ============================================================================
# Main
# ============================================================================
main() {
    echo -e "${BOLD}${CYAN}"
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║          Agent007 — Railway Infrastructure          ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    local action="setup"
    local env_name="staging"
    local apply=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --env)       env_name="$2"; action="env"; shift 2 ;;
            --apply)     apply=true; shift ;;
            --status)    action="status"; shift ;;
            --help|-h)   usage; exit 0 ;;
            *)           warn "Unknown flag: $1"; shift ;;
        esac
    done

    case "$action" in
        setup)
            setup_project
            setup_services
            echo ""
            info "Next steps:"
            echo "  1. Add services in Railway dashboard (one per subdirectory)"
            echo "  2. Set root directory per service:"
            echo "       orchestrator → /Orchestrator"
            echo "       dashboard    → /dashboard"
            echo "       syncaudit    → /SyncAudit"
            echo "  3. Set env vars:  $0 --env staging --apply"
            echo "  4. Deploy:        railway up"
            ;;
        env)
            if $apply; then
                apply_env_vars "$env_name"
            else
                set_env_vars "$env_name"
            fi
            ;;
        status)
            check_status
            ;;
    esac
}

usage() {
    echo "Usage: $(basename "$0") [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  (no args)          Full interactive project setup"
    echo "  --env NAME         Preview env vars for environment (staging|production)"
    echo "  --env NAME --apply Actually set env vars in Railway"
    echo "  --status           Show deployment readiness status"
    echo "  --help             Show this help"
}

main "$@"
