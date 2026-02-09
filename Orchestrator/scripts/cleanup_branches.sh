#!/bin/bash
#
# Git Branch Cleanup Script
# 
# This script helps clean up old, merged, or unused branches from a repository.
# Useful before migration to reduce the number of branches being migrated.
#
# Usage:
#   ./cleanup_branches.sh [options]
#   ./cleanup_branches.sh --merged --dry-run
#   ./cleanup_branches.sh --remote origin --merged --force
#
# Options:
#   --merged          Delete branches that have been merged
#   --no-merged       Delete branches that have NOT been merged
#   --remote <name>   Clean up remote branches (default: origin)
#   --local           Clean up local branches only
#   --all             Clean up both local and remote branches
#   --dry-run         Show what would be deleted without actually deleting
#   --force           Skip confirmation prompts
#   --keep <branch>   Keep specific branch (can be used multiple times)
#   --exclude <pattern>  Exclude branches matching pattern (regex)
#   --older-than <days>  Delete branches older than N days
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

# Defaults
CLEANUP_LOCAL=false
CLEANUP_REMOTE=false
REMOTE_NAME="origin"
DRY_RUN=false
FORCE=false
MERGED_ONLY=false
NO_MERGED_ONLY=false
KEEP_BRANCHES=()
EXCLUDE_PATTERNS=()
OLDER_THAN_DAYS=""

# Functions
log_info() { echo -e "${CYAN}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

show_help() {
    cat << 'EOF'
Git Branch Cleanup Script

This script helps clean up old, merged, or unused branches from a repository.

Usage:
  cleanup_branches.sh [options]

Options:
  --merged              Delete branches that have been merged into main/master
  --no-merged           Delete branches that have NOT been merged
  --remote <name>       Clean up remote branches (default: origin)
  --local               Clean up local branches only
  --all                 Clean up both local and remote branches
  --dry-run             Show what would be deleted without actually deleting
  --force               Skip confirmation prompts
  --keep <branch>       Keep specific branch (can be used multiple times)
  --exclude <pattern>  Exclude branches matching pattern (regex)
  --older-than <days>   Delete branches older than N days (based on last commit)
  -h, --help            Show this help message

Examples:
  # Preview merged branches that would be deleted
  ./cleanup_branches.sh --merged --dry-run

  # Delete merged local branches
  ./cleanup_branches.sh --local --merged

  # Delete merged remote branches
  ./cleanup_branches.sh --remote origin --merged

  # Delete all merged branches (local and remote)
  ./cleanup_branches.sh --all --merged

  # Keep specific branches while cleaning
  ./cleanup_branches.sh --all --merged --keep main --keep develop --keep staging

  # Exclude branches matching pattern
  ./cleanup_branches.sh --all --merged --exclude "release/.*" --exclude "hotfix/.*"

  # Delete branches older than 90 days
  ./cleanup_branches.sh --all --older-than 90

Protected Branches (always kept):
  - main, master, develop, staging, production (exact matches)
  - Branches containing: bk, backup, copy, cp (anywhere in name)
  - Branches containing: master, main, production, dev, prod, stage (anywhere in name)
  - Current branch

EOF
}

check_git_repo() {
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        log_error "Not in a git repository"
        exit 1
    fi
}

get_default_branch() {
    # Try to detect default branch
    if git show-ref --verify --quiet refs/heads/main; then
        echo "main"
    elif git show-ref --verify --quiet refs/heads/master; then
        echo "master"
    else
        # Get the branch that HEAD points to
        git symbolic-ref --short HEAD 2>/dev/null || echo "main"
    fi
}

is_protected_branch() {
    local branch="$1"
    local branch_lower
    branch_lower=$(echo "$branch" | tr '[:upper:]' '[:lower:]')
    
    # Remove "origin/" prefix for pattern matching
    local branch_name="${branch#origin/}"
    local branch_name_lower
    branch_name_lower=$(echo "$branch_name" | tr '[:upper:]' '[:lower:]')
    
    local protected=("main" "master" "develop" "staging" "production")
    local current_branch
    current_branch=$(git branch --show-current 2>/dev/null || echo "")
    
    # Check against protected list (exact match)
    for protected_branch in "${protected[@]}"; do
        if [[ "$branch" == "$protected_branch" ]] || [[ "$branch" == "origin/$protected_branch" ]]; then
            return 0
        fi
    done
    
    # Check if it's the current branch
    if [[ "$branch" == "$current_branch" ]] || [[ "$branch" == "origin/$current_branch" ]]; then
        return 0
    fi
    
    # Check for backup-related keywords in branch name (case-insensitive)
    # Keep branches with: bk, backup, copy, cp
    if [[ "$branch_name_lower" =~ (bk|backup|copy|cp) ]]; then
        return 0
    fi
    
    # Check for important environment keywords in branch name (case-insensitive)
    # Keep branches with: master, main, production, dev, prod, stage
    if [[ "$branch_name_lower" =~ (master|main|production|dev|prod|stage) ]]; then
        return 0
    fi
    
    # Check keep list
    for keep_branch in "${KEEP_BRANCHES[@]}"; do
        if [[ "$branch" == "$keep_branch" ]] || [[ "$branch" == "origin/$keep_branch" ]]; then
            return 0
        fi
    done
    
    # Check exclude patterns
    for pattern in "${EXCLUDE_PATTERNS[@]}"; do
        if [[ "$branch" =~ $pattern ]]; then
            return 0
        fi
    done
    
    return 1
}

is_branch_older_than() {
    local branch="$1"
    local days="$2"
    local branch_date
    local days_ago
    
    # Get last commit date for branch
    if [[ "$branch" =~ ^origin/ ]]; then
        branch_date=$(git log -1 --format=%ct "refs/remotes/$branch" 2>/dev/null || echo "0")
    else
        branch_date=$(git log -1 --format=%ct "refs/heads/$branch" 2>/dev/null || echo "0")
    fi
    
    if [[ "$branch_date" == "0" ]]; then
        return 1
    fi
    
    days_ago=$(($(date +%s) - days * 86400))
    
    if [[ $branch_date -lt $days_ago ]]; then
        return 0
    else
        return 1
    fi
}

get_merged_branches() {
    local default_branch="$1"
    local remote="$2"
    
    if [[ "$remote" == "local" ]]; then
        git branch --merged "$default_branch" --format='%(refname:short)' 2>/dev/null | grep -v "^$default_branch$" || true
    else
        git branch -r --merged "$default_branch" --format='%(refname:short)' 2>/dev/null | grep "^$REMOTE_NAME/" | sed "s|^$REMOTE_NAME/||" | grep -v "^$default_branch$" || true
    fi
}

get_unmerged_branches() {
    local default_branch="$1"
    local remote="$2"
    
    if [[ "$remote" == "local" ]]; then
        git branch --no-merged "$default_branch" --format='%(refname:short)' 2>/dev/null | grep -v "^$default_branch$" || true
    else
        git branch -r --no-merged "$default_branch" --format='%(refname:short)' 2>/dev/null | grep "^$REMOTE_NAME/" | sed "s|^$REMOTE_NAME/||" | grep -v "^$default_branch$" || true
    fi
}

cleanup_local_branches() {
    local branches_to_delete=()
    local default_branch
    default_branch=$(get_default_branch)
    
    log_info "Default branch: $default_branch"
    
    # Fetch latest from remote first
    if git remote | grep -q "^${REMOTE_NAME}$"; then
        log_info "Fetching latest from $REMOTE_NAME..."
        git fetch "$REMOTE_NAME" --prune --quiet 2>/dev/null || true
    fi
    
    # Get branches based on criteria
    if [[ "$MERGED_ONLY" == "true" ]]; then
        log_info "Finding merged local branches..."
        while IFS= read -r branch; do
            [[ -z "$branch" ]] && continue
            if ! is_protected_branch "$branch"; then
                if [[ -z "$OLDER_THAN_DAYS" ]] || is_branch_older_than "$branch" "$OLDER_THAN_DAYS"; then
                    branches_to_delete+=("$branch")
                fi
            fi
        done < <(get_merged_branches "$default_branch" "local")
    elif [[ "$NO_MERGED_ONLY" == "true" ]]; then
        log_info "Finding unmerged local branches..."
        while IFS= read -r branch; do
            [[ -z "$branch" ]] && continue
            if ! is_protected_branch "$branch"; then
                if [[ -z "$OLDER_THAN_DAYS" ]] || is_branch_older_than "$branch" "$OLDER_THAN_DAYS"; then
                    branches_to_delete+=("$branch")
                fi
            fi
        done < <(get_unmerged_branches "$default_branch" "local")
    fi
    
    if [[ ${#branches_to_delete[@]} -eq 0 ]]; then
        log_info "No local branches to delete"
        return 0
    fi
    
    log_info "Found ${#branches_to_delete[@]} local branch(es) to delete:"
    for branch in "${branches_to_delete[@]}"; do
        echo "  - $branch"
    done
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "[DRY RUN] Would delete local branches (not actually deleting)"
        return 0
    fi
    
    if [[ "$FORCE" != "true" ]]; then
        echo ""
        read -p "Delete these local branches? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Cancelled"
            return 0
        fi
    fi
    
    for branch in "${branches_to_delete[@]}"; do
        if git branch -D "$branch" 2>/dev/null; then
            log_success "Deleted local branch: $branch"
        else
            log_warn "Failed to delete local branch: $branch"
        fi
    done
}

cleanup_remote_branches() {
    local branches_to_delete=()
    local default_branch
    default_branch=$(get_default_branch)
    
    log_info "Default branch: $default_branch"
    log_info "Remote: $REMOTE_NAME"
    
    # Fetch latest
    log_info "Fetching latest from $REMOTE_NAME..."
    git fetch "$REMOTE_NAME" --prune --quiet 2>/dev/null || true
    
    # Get branches based on criteria
    if [[ "$MERGED_ONLY" == "true" ]]; then
        log_info "Finding merged remote branches..."
        while IFS= read -r branch; do
            [[ -z "$branch" ]] && continue
            if ! is_protected_branch "$branch"; then
                if [[ -z "$OLDER_THAN_DAYS" ]] || is_branch_older_than "origin/$branch" "$OLDER_THAN_DAYS"; then
                    branches_to_delete+=("$branch")
                fi
            fi
        done < <(get_merged_branches "$default_branch" "remote")
    elif [[ "$NO_MERGED_ONLY" == "true" ]]; then
        log_info "Finding unmerged remote branches..."
        while IFS= read -r branch; do
            [[ -z "$branch" ]] && continue
            if ! is_protected_branch "$branch"; then
                if [[ -z "$OLDER_THAN_DAYS" ]] || is_branch_older_than "origin/$branch" "$OLDER_THAN_DAYS"; then
                    branches_to_delete+=("$branch")
                fi
            fi
        done < <(get_unmerged_branches "$default_branch" "remote")
    fi
    
    if [[ ${#branches_to_delete[@]} -eq 0 ]]; then
        log_info "No remote branches to delete"
        return 0
    fi
    
    log_info "Found ${#branches_to_delete[@]} remote branch(es) to delete:"
    for branch in "${branches_to_delete[@]}"; do
        echo "  - $REMOTE_NAME/$branch"
    done
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "[DRY RUN] Would delete remote branches (not actually deleting)"
        return 0
    fi
    
    if [[ "$FORCE" != "true" ]]; then
        echo ""
        read -p "Delete these remote branches? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Cancelled"
            return 0
        fi
    fi
    
    for branch in "${branches_to_delete[@]}"; do
        if git push "$REMOTE_NAME" --delete "$branch" 2>/dev/null; then
            log_success "Deleted remote branch: $REMOTE_NAME/$branch"
        else
            log_warn "Failed to delete remote branch: $REMOTE_NAME/$branch"
        fi
    done
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            show_help
            exit 0
            ;;
        --merged)
            MERGED_ONLY=true
            shift
            ;;
        --no-merged)
            NO_MERGED_ONLY=true
            shift
            ;;
        --remote)
            REMOTE_NAME="$2"
            CLEANUP_REMOTE=true
            shift 2
            ;;
        --local)
            CLEANUP_LOCAL=true
            shift
            ;;
        --all)
            CLEANUP_LOCAL=true
            CLEANUP_REMOTE=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --keep)
            KEEP_BRANCHES+=("$2")
            shift 2
            ;;
        --exclude)
            EXCLUDE_PATTERNS+=("$2")
            shift 2
            ;;
        --older-than)
            OLDER_THAN_DAYS="$2"
            shift 2
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Validate options
if [[ "$MERGED_ONLY" == "false" && "$NO_MERGED_ONLY" == "false" && -z "$OLDER_THAN_DAYS" ]]; then
    log_error "Must specify --merged, --no-merged, or --older-than"
    show_help
    exit 1
fi

if [[ "$CLEANUP_LOCAL" == "false" && "$CLEANUP_REMOTE" == "false" ]]; then
    # Default to local if nothing specified
    CLEANUP_LOCAL=true
fi

# Main execution
main() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  🧹 Git Branch Cleanup${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "DRY RUN MODE - No branches will be deleted"
    fi
    
    check_git_repo
    
    if [[ "$CLEANUP_LOCAL" == "true" ]]; then
        echo ""
        log_info "Cleaning up local branches..."
        cleanup_local_branches
    fi
    
    if [[ "$CLEANUP_REMOTE" == "true" ]]; then
        echo ""
        log_info "Cleaning up remote branches..."
        cleanup_remote_branches
    fi
    
    echo ""
    log_success "Cleanup complete!"
}

main
