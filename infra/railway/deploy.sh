#!/bin/bash
# ============================================================================
# Agent007 — Deploy individual or all services to Railway
# ============================================================================
# Usage:
#   ./infra/railway/deploy.sh                    # Deploy all changed services
#   ./infra/railway/deploy.sh orchestrator       # Deploy only orchestrator
#   ./infra/railway/deploy.sh dashboard          # Deploy only dashboard
#   ./infra/railway/deploy.sh syncaudit          # Deploy only syncaudit
#   ./infra/railway/deploy.sh --all              # Force deploy all
# ============================================================================

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${BLUE}ℹ  $1${NC}"; }
success() { echo -e "${GREEN}✅ $1${NC}"; }
warn()    { echo -e "${YELLOW}⚠️  $1${NC}"; }
error()   { echo -e "${RED}❌ $1${NC}"; }

# Verify Railway CLI is ready
if ! command -v railway &>/dev/null; then
    error "Railway CLI not installed"
    exit 1
fi

if ! railway whoami &>/dev/null 2>&1; then
    error "Not logged in. Run: railway login"
    exit 1
fi

deploy_service() {
    local service=$1
    local dir=$2

    if [[ ! -d "$dir" ]]; then
        warn "Directory not found: $dir — skipping $service"
        return 1
    fi

    echo ""
    echo -e "${BOLD}═══ Deploying $service ═══${NC}"
    info "Directory: $dir"

    cd "$dir"

    if railway up --service "$service" --detach; then
        success "$service deployed!"
    else
        error "$service deploy failed"
        return 1
    fi
}

# Parse args
TARGET="${1:-}"

case "$TARGET" in
    orchestrator)
        deploy_service orchestrator "$ROOT_DIR/Orchestrator"
        ;;
    dashboard)
        deploy_service dashboard "$ROOT_DIR/dashboard"
        ;;
    syncaudit)
        deploy_service syncaudit "$ROOT_DIR/SyncAudit"
        ;;
    --all|"")
        deploy_service orchestrator "$ROOT_DIR/Orchestrator"
        deploy_service dashboard "$ROOT_DIR/dashboard"
        deploy_service syncaudit "$ROOT_DIR/SyncAudit"
        ;;
    *)
        error "Unknown service: $TARGET"
        echo "Usage: $0 [orchestrator|dashboard|syncaudit|--all]"
        exit 1
        ;;
esac

echo ""
success "Deployment complete!"
echo ""
info "Check status:  railway status"
info "View logs:     railway logs --service <name>"
