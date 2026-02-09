#!/bin/bash
#
# Phyto Project: Complete Migration and Cleanup Script
# 
# This script:
# 1. Migrates the phyto project from Bitbucket to GitHub (as-is, all branches)
# 2. Cleans up old/merged branches on GitHub after migration
#
# Usage:
#   ./migrate_and_cleanup_phyto.sh [options]
#
# Options:
#   --skip-cleanup    Skip branch cleanup after migration
#   --cleanup-only    Only run cleanup (skip migration)
#   --dry-run         Show what would be done without executing
#   -h, --help        Show help
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
BITBUCKET_REPO="git@bitbucket.org:pdxaromatics/phytom2-repo.git"
GITHUB_REPO="pdxaromatics/magento2"
GITHUB_URL="git@github.com:pdxaromatics/magento2.git"
WORK_DIR="/tmp/phyto-migration-$(date +%Y%m%d-%H%M%S)"
MIRROR_DIR="${WORK_DIR}/phyto-mirror"
CLEANUP_DIR="${WORK_DIR}/phyto-cleanup"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLEANUP_SCRIPT="${SCRIPT_DIR}/cleanup_branches.sh"

# Flags
SKIP_CLEANUP=false
CLEANUP_ONLY=false
DRY_RUN=false

# Functions
log_info() { echo -e "${CYAN}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

show_help() {
    cat << 'EOF'
Phyto Project: Complete Migration and Cleanup Script

This script migrates the phyto project from Bitbucket to GitHub and then
cleans up old/merged branches.

Usage:
  migrate_and_cleanup_phyto.sh [options]

Options:
  --skip-cleanup    Skip branch cleanup after migration
  --cleanup-only    Only run cleanup (skip migration)
  --dry-run         Show what would be done without executing
  -h, --help        Show this help message

Process:
  1. Clone Bitbucket repo with all branches/tags
  2. Push everything to GitHub (mirror push)
  3. Clean up merged branches on GitHub (keeps backups and important branches)
  4. Verify results

Protected branches during cleanup:
  - Branches with: bk, backup, copy, cp in name
  - Branches with: master, main, production, dev, prod, stage in name
  - Exact matches: main, master, develop, staging, production
  - Current branch

EOF
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    local errors=0
    
    # Check git
    if ! command -v git &> /dev/null; then
        log_error "Git is not installed"
        errors=$((errors + 1))
    fi
    
    # Check gh CLI
    if ! command -v gh &> /dev/null; then
        log_error "GitHub CLI (gh) is not installed"
        log_info "Install with: brew install gh (macOS) or see https://cli.github.com/"
        errors=$((errors + 1))
    elif ! gh auth status &> /dev/null; then
        log_error "GitHub CLI is not authenticated"
        log_info "Run: gh auth login"
        errors=$((errors + 1))
    fi
    
    # Check cleanup script exists
    if [[ ! -f "$CLEANUP_SCRIPT" ]]; then
        log_error "Cleanup script not found: $CLEANUP_SCRIPT"
        errors=$((errors + 1))
    fi
    
    if [[ $errors -gt 0 ]]; then
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

verify_github_repo() {
    log_info "Verifying GitHub repository: $GITHUB_REPO"
    
    local repo_info
    repo_info=$(gh repo view "$GITHUB_REPO" --json isEmpty,nameWithOwner,defaultBranchRef,url 2>&1) || {
        log_error "Failed to access GitHub repository: $GITHUB_REPO"
        log_info "Make sure:"
        log_info "  1. The repository exists"
        log_info "  2. You have access to it"
        log_info "  3. GitHub CLI is authenticated: gh auth status"
        exit 1
    }
    
    local is_empty
    is_empty=$(echo "$repo_info" | grep -o '"isEmpty":[^,]*' | cut -d: -f2)
    local name_with_owner
    name_with_owner=$(echo "$repo_info" | grep -o '"nameWithOwner":"[^"]*"' | cut -d'"' -f4)
    
    log_info "Repository: $name_with_owner"
    
    if [[ "$is_empty" == "false" ]]; then
        log_warn "GitHub repository is NOT empty - it contains existing content"
        log_warn "Migration will overwrite the repository with Bitbucket content"
        echo ""
        read -p "Do you want to continue? This will overwrite existing content! (yes/no): " confirm
        if [[ "$confirm" != "yes" ]]; then
            log_info "Migration cancelled"
            exit 0
        fi
    else
        log_info "GitHub repository is empty - safe to proceed"
    fi
}

migrate_repository() {
    log_info "=== Step 1: Migrating Repository ==="
    echo ""
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "[DRY RUN] Would clone and migrate repository"
        return 0
    fi
    
    # Create work directory
    mkdir -p "$WORK_DIR"
    
    # Clone Bitbucket repo with all refs
    log_info "Cloning Bitbucket repository (this may take a while)..."
    git clone --mirror "$BITBUCKET_REPO" "$MIRROR_DIR"
    
    cd "$MIRROR_DIR"
    
    # Add GitHub remote
    log_info "Setting GitHub remote..."
    git remote set-url origin "$GITHUB_URL"
    
    # Push everything
    log_info "Pushing all branches, tags, and refs to GitHub..."
    log_info "This may take a while depending on repository size..."
    
    if git push --mirror --force; then
        log_success "Migration completed successfully!"
    else
        log_error "Migration failed during push"
        log_info "Check the error above and verify:"
        log_info "  1. GitHub repository access"
        log_info "  2. Network connection"
        log_info "  3. Repository size limits"
        exit 1
    fi
    
    # Verify
    log_info "Verifying migration..."
    local github_branches
    github_branches=$(git ls-remote --heads origin | wc -l)
    local github_tags
    github_tags=$(git ls-remote --tags origin | wc -l)
    
    log_success "Branches on GitHub: $github_branches"
    log_success "Tags on GitHub: $github_tags"
}

cleanup_branches() {
    log_info "=== Step 2: Cleaning Up Branches ==="
    echo ""
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "[DRY RUN] Would clean up merged branches"
        return 0
    fi
    
    # Clone GitHub repo for cleanup
    log_info "Cloning GitHub repository for cleanup..."
    git clone "$GITHUB_URL" "$CLEANUP_DIR"
    cd "$CLEANUP_DIR"
    
    # Run cleanup script
    log_info "Running branch cleanup (will keep backups and important branches)..."
    log_info "Previewing what would be deleted..."
    
    if "$CLEANUP_SCRIPT" --remote origin --merged --dry-run; then
        echo ""
        read -p "Proceed with cleanup? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "Cleaning up merged branches..."
            "$CLEANUP_SCRIPT" --remote origin --merged
            log_success "Branch cleanup completed!"
        else
            log_info "Cleanup skipped"
        fi
    else
        log_warn "Cleanup script failed or no branches to clean"
    fi
}

cleanup_workdir() {
    log_info "Cleaning up temporary files..."
    if [[ -d "$WORK_DIR" ]]; then
        read -p "Remove temporary migration directory? ($WORK_DIR) (yes/no): " cleanup_confirm
        if [[ "$cleanup_confirm" == "yes" ]]; then
            rm -rf "$WORK_DIR"
            log_success "Cleanup complete"
        else
            log_info "Keeping migration directory: $WORK_DIR"
            log_info "You can review it or remove it manually later"
        fi
    fi
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            show_help
            exit 0
            ;;
        --skip-cleanup)
            SKIP_CLEANUP=true
            shift
            ;;
        --cleanup-only)
            CLEANUP_ONLY=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Main execution
main() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  🚀 Phyto Project: Migration and Cleanup${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "DRY RUN MODE - No changes will be made"
    fi
    
    check_prerequisites
    echo ""
    
    if [[ "$CLEANUP_ONLY" != "true" ]]; then
        verify_github_repo
        echo ""
        migrate_repository
        echo ""
    fi
    
    if [[ "$SKIP_CLEANUP" != "true" ]]; then
        cleanup_branches
        echo ""
    fi
    
    cleanup_workdir
    
    echo ""
    log_success "=== Process Complete ==="
    log_info "Next steps:"
    log_info "  1. Update local repository remotes"
    log_info "  2. Update CI/CD pipelines"
    log_info "  3. Notify team members"
    log_info "  4. Test the migrated repository"
    log_info "  5. Archive Bitbucket repo (after 30 days)"
}

main
