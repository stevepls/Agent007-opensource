#!/bin/bash
#
# Phyto Project: Bitbucket to GitHub Migration Script
# 
# This script migrates the phyto project from Bitbucket to an existing GitHub repository.
# 
# Prerequisites:
# 1. GitHub CLI (gh) installed and authenticated
# 2. Git installed
# 3. SSH access to both Bitbucket and GitHub
# 4. GitHub repository URL from Jarod
#
# Usage:
#   ./migrate_phyto_to_github.sh <github-repo-url>
#   Example: ./migrate_phyto_to_github.sh git@github.com:jarod/phyto-repo.git
#   Or: ./migrate_phyto_to_github.sh jarod/phyto-repo
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
BITBUCKET_REPO="git@bitbucket.org:pdxaromatics/phytom2-repo.git"
WORK_DIR="/tmp/phyto-migration-$(date +%Y%m%d-%H%M%S)"
MIRROR_DIR="${WORK_DIR}/phyto-mirror"

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check git
    if ! command -v git &> /dev/null; then
        log_error "Git is not installed"
        exit 1
    fi
    
    # Check gh CLI
    if ! command -v gh &> /dev/null; then
        log_error "GitHub CLI (gh) is not installed"
        log_info "Install with: brew install gh (macOS) or see https://cli.github.com/"
        exit 1
    fi
    
    # Check gh authentication
    if ! gh auth status &> /dev/null; then
        log_error "GitHub CLI is not authenticated"
        log_info "Run: gh auth login"
        exit 1
    fi
    
    log_info "Prerequisites check passed"
}

parse_github_url() {
    local input="$1"
    local github_url=""
    local repo_identifier=""
    
    if [[ -z "$input" ]]; then
        log_error "GitHub repository URL or identifier is required"
        echo "Usage: $0 <github-repo-url>"
        echo "  Example: $0 git@github.com:jarod/phyto-repo.git"
        echo "  Example: $0 jarod/phyto-repo"
        exit 1
    fi
    
    # If it's already a full URL
    if [[ "$input" =~ ^git@github.com: ]] || [[ "$input" =~ ^https://github.com/ ]]; then
        github_url="$input"
        # Extract org/repo from URL
        if [[ "$input" =~ git@github.com:(.+)\.git$ ]]; then
            repo_identifier="${BASH_REMATCH[1]}"
        elif [[ "$input" =~ https://github.com/(.+)\.git$ ]]; then
            repo_identifier="${BASH_REMATCH[1]}"
        elif [[ "$input" =~ git@github.com:(.+)$ ]]; then
            repo_identifier="${BASH_REMATCH[1]}"
        elif [[ "$input" =~ https://github.com/(.+)$ ]]; then
            repo_identifier="${BASH_REMATCH[1]}"
        fi
    # If it's org/repo format
    elif [[ "$input" =~ ^[^/]+/[^/]+$ ]]; then
        repo_identifier="$input"
        github_url="git@github.com:${input}.git"
    else
        log_error "Invalid GitHub repository format: $input"
        log_info "Expected format: git@github.com:org/repo.git or org/repo"
        exit 1
    fi
    
    echo "$repo_identifier|$github_url"
}

verify_github_repo() {
    local repo_identifier="$1"
    
    log_info "Verifying GitHub repository: $repo_identifier"
    
    # Check if repo exists and get info
    local repo_info
    repo_info=$(gh repo view "$repo_identifier" --json isEmpty,nameWithOwner,defaultBranchRef,url 2>&1) || {
        log_error "Failed to access GitHub repository: $repo_identifier"
        log_info "Make sure:"
        log_info "  1. The repository exists"
        log_info "  2. You have access to it"
        log_info "  3. GitHub CLI is authenticated: gh auth status"
        exit 1
    }
    
    local is_empty
    is_empty=$(echo "$repo_info" | jq -r '.isEmpty // true')
    local name_with_owner
    name_with_owner=$(echo "$repo_info" | jq -r '.nameWithOwner')
    local default_branch
    default_branch=$(echo "$repo_info" | jq -r '.defaultBranchRef.name // "main"')
    
    log_info "Repository: $name_with_owner"
    log_info "Default branch: $default_branch"
    
    if [[ "$is_empty" == "false" ]]; then
        log_warn "GitHub repository is NOT empty - it contains existing content"
        log_warn "This will overwrite the repository with Bitbucket content"
        echo ""
        read -p "Do you want to continue? This will overwrite existing content! (yes/no): " confirm
        if [[ "$confirm" != "yes" ]]; then
            log_info "Migration cancelled"
            exit 0
        fi
    else
        log_info "GitHub repository is empty - safe to proceed"
    fi
    
    echo "$is_empty|$name_with_owner|$default_branch"
}

audit_bitbucket_repo() {
    log_info "Auditing Bitbucket repository..."
    
    # Test access to Bitbucket repo
    if ! git ls-remote "$BITBUCKET_REPO" &> /dev/null; then
        log_error "Cannot access Bitbucket repository: $BITBUCKET_REPO"
        log_info "Make sure you have SSH access configured"
        exit 1
    fi
    
    log_info "Creating mirror clone for audit..."
    mkdir -p "$WORK_DIR"
    git clone --mirror "$BITBUCKET_REPO" "$MIRROR_DIR"
    
    cd "$MIRROR_DIR"
    
    log_info "Repository statistics:"
    echo "  Branches: $(git branch -r | wc -l)"
    echo "  Tags: $(git tag -l | wc -l)"
    
    local repo_size
    repo_size=$(git count-objects -vH | grep "size-pack" | awk '{print $2}')
    echo "  Repository size: $repo_size"
    
    local commit_count
    commit_count=$(git log --oneline --all | wc -l)
    echo "  Total commits: $commit_count"
    
    log_info "Audit complete"
}

perform_migration() {
    local github_url="$1"
    
    log_info "Starting migration..."
    log_info "Source: $BITBUCKET_REPO"
    log_info "Destination: $github_url"
    
    cd "$MIRROR_DIR"
    
    # Update remote to point to GitHub
    log_info "Updating remote to GitHub..."
    git remote set-url origin "$github_url"
    
    # Push everything
    log_info "Pushing all branches, tags, and refs to GitHub..."
    log_info "This may take a while depending on repository size..."
    
    if git push --mirror; then
        log_info "Migration completed successfully!"
    else
        log_error "Migration failed during push"
        log_info "Check the error above and verify:"
        log_info "  1. GitHub repository access"
        log_info "  2. Network connection"
        log_info "  3. Repository size limits"
        exit 1
    fi
}

verify_migration() {
    local repo_identifier="$1"
    
    log_info "Verifying migration..."
    
    # Check branches
    local github_branches
    github_branches=$(git ls-remote --heads origin | wc -l)
    log_info "Branches on GitHub: $github_branches"
    
    # Check tags
    local github_tags
    github_tags=$(git ls-remote --tags origin | wc -l)
    log_info "Tags on GitHub: $github_tags"
    
    log_info "Verification complete"
    log_info "View repository at: https://github.com/$repo_identifier"
}

cleanup() {
    log_info "Cleaning up temporary files..."
    if [[ -d "$WORK_DIR" ]]; then
        read -p "Remove temporary migration directory? ($WORK_DIR) (yes/no): " cleanup_confirm
        if [[ "$cleanup_confirm" == "yes" ]]; then
            rm -rf "$WORK_DIR"
            log_info "Cleanup complete"
        else
            log_info "Keeping migration directory: $WORK_DIR"
            log_info "You can review it or remove it manually later"
        fi
    fi
}

# Main execution
main() {
    log_info "=== Phyto Bitbucket to GitHub Migration ==="
    echo ""
    
    # Parse arguments
    local github_input="$1"
    if [[ -z "$github_input" ]]; then
        log_error "GitHub repository URL or identifier is required"
        echo ""
        echo "Usage: $0 <github-repo-url>"
        echo ""
        echo "Examples:"
        echo "  $0 git@github.com:jarod/phyto-repo.git"
        echo "  $0 jarod/phyto-repo"
        echo ""
        exit 1
    fi
    
    # Parse GitHub URL
    local url_info
    url_info=$(parse_github_url "$github_input")
    local repo_identifier
    repo_identifier=$(echo "$url_info" | cut -d'|' -f1)
    local github_url
    github_url=$(echo "$url_info" | cut -d'|' -f2)
    
    log_info "GitHub Repository: $repo_identifier"
    log_info "GitHub URL: $github_url"
    echo ""
    
    # Run migration steps
    check_prerequisites
    echo ""
    
    local repo_info
    repo_info=$(verify_github_repo "$repo_identifier")
    echo ""
    
    audit_bitbucket_repo
    echo ""
    
    log_warn "Ready to migrate. This will push all content from Bitbucket to GitHub."
    read -p "Continue with migration? (yes/no): " proceed
    if [[ "$proceed" != "yes" ]]; then
        log_info "Migration cancelled"
        exit 0
    fi
    echo ""
    
    perform_migration "$github_url"
    echo ""
    
    verify_migration "$repo_identifier"
    echo ""
    
    cleanup
    
    log_info "=== Migration Complete ==="
    log_info "Next steps:"
    log_info "  1. Update local repository remotes (see migration guide)"
    log_info "  2. Update CI/CD pipelines"
    log_info "  3. Notify team members"
    log_info "  4. Test the migrated repository"
}

# Run main function
main "$@"
