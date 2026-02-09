#!/bin/bash
#
# Migrate Bitbucket Deployment Variables to GitHub Secrets
#
# This script copies deployment variables from Bitbucket Pipelines to GitHub Secrets.
# It uses the Bitbucket API to fetch variables and GitHub CLI to set secrets.
#
# Usage:
#   ./migrate_bitbucket_variables_to_github.sh <bitbucket-workspace> <bitbucket-repo> <github-repo>
#   Example: ./migrate_bitbucket_variables_to_github.sh pdxaromatics phytom2-repo pdxaromatics/magento2
#
# Prerequisites:
#   1. Bitbucket App Password (with read permissions for repositories)
#   2. GitHub CLI (gh) installed and authenticated
#   3. Environment variable: BITBUCKET_APP_PASSWORD (or will prompt)
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
NC='\033[0m'

# Functions
log_info() { echo -e "${CYAN}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

show_help() {
    cat << 'EOF'
Migrate Bitbucket Deployment Variables to GitHub Secrets

This script copies deployment variables from Bitbucket Pipelines to GitHub Secrets.

Usage:
  migrate_bitbucket_variables_to_github.sh <bitbucket-workspace> <bitbucket-repo> <github-repo> [options]

Arguments:
  bitbucket-workspace    Bitbucket workspace/org (e.g., pdxaromatics)
  bitbucket-repo         Bitbucket repository slug (e.g., phytom2-repo)
  github-repo            GitHub repository (e.g., pdxaromatics/magento2)

Options:
  --username <user>      Bitbucket username (default: prompt)
  --password <pass>      Bitbucket app password (default: use BITBUCKET_APP_PASSWORD env var)
  --dry-run              Show what would be migrated without actually migrating
  --skip-existing        Skip secrets that already exist in GitHub
  --mapping <file>       Use custom variable name mapping file (JSON)
  -h, --help             Show this help message

Environment Variables:
  BITBUCKET_APP_PASSWORD  Bitbucket app password (alternative to --password)

Examples:
  # Basic migration
  ./migrate_bitbucket_variables_to_github.sh pdxaromatics phytom2-repo pdxaromatics/magento2

  # With custom username
  ./migrate_bitbucket_variables_to_github.sh pdxaromatics phytom2-repo pdxaromatics/magento2 --username myuser

  # Dry run to preview
  ./migrate_bitbucket_variables_to_github.sh pdxaromatics phytom2-repo pdxaromatics/magento2 --dry-run

Bitbucket App Password Setup:
  1. Go to Bitbucket → Personal settings → App passwords
  2. Create app password with "Repositories: Read" permission
  3. Copy the password (you won't see it again)
  4. Set as environment variable: export BITBUCKET_APP_PASSWORD="your-password"
  5. Or pass with --password flag

Variable Name Mapping:
  The script automatically maps common Bitbucket variable names to GitHub secret names:
  - STAGING_* → STAGING_* (keeps prefix)
  - PROD_* → PRODUCTION_* (converts prefix)
  - SSH_KEY → STAGING_SSH_KEY or PRODUCTION_SSH_KEY (based on context)
  - HOST → STAGING_HOST or PRODUCTION_HOST
  - USER → STAGING_USER or PRODUCTION_USER
  - PATH → STAGING_PATH or PRODUCTION_PATH
  - URL → STAGING_URL or PRODUCTION_URL

EOF
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    local errors=0
    
    # Check jq (for JSON parsing)
    if ! command -v jq &> /dev/null; then
        log_error "jq is not installed (required for JSON parsing)"
        log_info "Install with: brew install jq (macOS) or apt-get install jq (Linux)"
        errors=$((errors + 1))
    fi
    
    # Check curl
    if ! command -v curl &> /dev/null; then
        log_error "curl is not installed"
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
    
    if [[ $errors -gt 0 ]]; then
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

get_bitbucket_variables() {
    local workspace="$1"
    local repo="$2"
    local username="$3"
    local password="$4"
    
    log_info "Fetching Bitbucket deployment variables..."
    
    # Bitbucket API endpoint for deployment variables
    local api_url="https://api.bitbucket.org/2.0/repositories/${workspace}/${repo}/deployments_config/environments"
    
    # Fetch environments (deployments)
    local environments
    environments=$(curl -s -u "${username}:${password}" "$api_url" | jq -r '.values[].uuid' 2>/dev/null || echo "")
    
    if [[ -z "$environments" ]]; then
        log_warn "No deployment environments found in Bitbucket"
        log_info "Trying to fetch repository variables instead..."
        
        # Try repository variables instead
        api_url="https://api.bitbucket.org/2.0/repositories/${workspace}/${repo}/pipelines_config/variables"
        local variables_json
        variables_json=$(curl -s -u "${username}:${password}" "$api_url" 2>/dev/null || echo "{}")
        
        if [[ "$variables_json" == "{}" ]] || [[ -z "$variables_json" ]]; then
            log_error "Could not fetch variables from Bitbucket"
            log_info "Make sure:"
            log_info "  1. Bitbucket app password has correct permissions"
            log_info "  2. Repository name is correct"
            log_info "  3. You have access to the repository"
            return 1
        fi
        
        echo "$variables_json"
        return 0
    fi
    
    # Fetch variables for each environment
    local all_variables="[]"
    while IFS= read -r env_uuid; do
        [[ -z "$env_uuid" ]] && continue
        
        local env_vars_url="https://api.bitbucket.org/2.0/repositories/${workspace}/${repo}/deployments_config/environments/${env_uuid}/variables"
        local env_vars
        env_vars=$(curl -s -u "${username}:${password}" "$env_vars_url" 2>/dev/null || echo "{}")
        
        if [[ "$env_vars" != "{}" ]] && [[ -n "$env_vars" ]]; then
            local env_name
          env_name=$(curl -s -u "${username}:${password}" "https://api.bitbucket.org/2.0/repositories/${workspace}/${repo}/deployments_config/environments/${env_uuid}" | jq -r '.name' 2>/dev/null || echo "unknown")
          
          # Add environment prefix to variable names
          local prefixed_vars
          prefixed_vars=$(echo "$env_vars" | jq --arg env "$env_name" '.values[] | {key: ($env + "_" + .key), value: .value, secured: .secured}' 2>/dev/null || echo "[]")
          
          all_variables=$(echo "$all_variables" | jq --argjson new "$prefixed_vars" '. + [$new]' 2>/dev/null || echo "$all_variables")
        fi
    done <<< "$environments"
    
    # Also try repository-level variables
    local repo_vars_url="https://api.bitbucket.org/2.0/repositories/${workspace}/${repo}/pipelines_config/variables"
    local repo_vars
    repo_vars=$(curl -s -u "${username}:${password}" "$repo_vars_url" 2>/dev/null || echo "{}")
    
    if [[ "$repo_vars" != "{}" ]] && [[ -n "$repo_vars" ]]; then
        local repo_vars_array
        repo_vars_array=$(echo "$repo_vars" | jq '.values[] | {key: .key, value: .value, secured: .secured}' 2>/dev/null || echo "[]")
        all_variables=$(echo "$all_variables" | jq --argjson new "[$repo_vars_array]" '. + $new' 2>/dev/null || echo "$all_variables")
    fi
    
    echo "$all_variables" | jq -s 'flatten' 2>/dev/null || echo "[]"
}

map_variable_name() {
    local bitbucket_name="$1"
    local github_name
    
    # Convert to uppercase
    github_name=$(echo "$bitbucket_name" | tr '[:lower:]' '[:upper:]')
    
    # Common mappings
    case "$github_name" in
        *PROD_*)
            github_name=$(echo "$github_name" | sed 's/PROD_/PRODUCTION_/g')
            ;;
        *STAGING_*)
            # Keep as is
            ;;
        SSH_KEY|SSH_PRIVATE_KEY)
            # Try to infer from context
            if [[ "$bitbucket_name" =~ [Ss][Tt][Aa][Gg] ]]; then
                github_name="STAGING_SSH_KEY"
            elif [[ "$bitbucket_name" =~ [Pp][Rr][Oo][Dd] ]]; then
                github_name="PRODUCTION_SSH_KEY"
            else
                github_name="STAGING_SSH_KEY"  # Default to staging
            fi
            ;;
        HOST|SERVER|IP)
            if [[ "$bitbucket_name" =~ [Ss][Tt][Aa][Gg] ]]; then
                github_name="STAGING_HOST"
            elif [[ "$bitbucket_name" =~ [Pp][Rr][Oo][Dd] ]]; then
                github_name="PRODUCTION_HOST"
            else
                github_name="STAGING_HOST"
            fi
            ;;
        USER|USERNAME)
            if [[ "$bitbucket_name" =~ [Ss][Tt][Aa][Gg] ]]; then
                github_name="STAGING_USER"
            elif [[ "$bitbucket_name" =~ [Pp][Rr][Oo][Dd] ]]; then
                github_name="PRODUCTION_USER"
            else
                github_name="STAGING_USER"
            fi
            ;;
        PATH|DEPLOY_PATH)
            if [[ "$bitbucket_name" =~ [Ss][Tt][Aa][Gg] ]]; then
                github_name="STAGING_PATH"
            elif [[ "$bitbucket_name" =~ [Pp][Rr][Oo][Dd] ]]; then
                github_name="PRODUCTION_PATH"
            else
                github_name="STAGING_PATH"
            fi
            ;;
        URL|SITE_URL)
            if [[ "$bitbucket_name" =~ [Ss][Tt][Aa][Gg] ]]; then
                github_name="STAGING_URL"
            elif [[ "$bitbucket_name" =~ [Pp][Rr][Oo][Dd] ]]; then
                github_name="PRODUCTION_URL"
            else
                github_name="STAGING_URL"
            fi
            ;;
    esac
    
    echo "$github_name"
}

migrate_variables() {
    local variables_json="$1"
    local github_repo="$2"
    local dry_run="$3"
    local skip_existing="$4"
    
    log_info "Migrating variables to GitHub Secrets..."
    
    local count=0
    local skipped=0
    local failed=0
    
    # Parse variables and migrate
    echo "$variables_json" | jq -r '.[] | @json' 2>/dev/null | while IFS= read -r var_json; do
        [[ -z "$var_json" ]] && continue
        
        local key
        key=$(echo "$var_json" | jq -r '.key' 2>/dev/null || echo "")
        local value
        value=$(echo "$var_json" | jq -r '.value' 2>/dev/null || echo "")
        local secured
        secured=$(echo "$var_json" | jq -r '.secured // false' 2>/dev/null || echo "false")
        
        if [[ -z "$key" ]] || [[ -z "$value" ]]; then
            continue
        fi
        
        # Map variable name
        local github_secret_name
        github_secret_name=$(map_variable_name "$key")
        
        # Check if secret already exists
        if [[ "$skip_existing" == "true" ]]; then
            if gh secret list --repo "$github_repo" 2>/dev/null | grep -q "^${github_secret_name}"; then
                log_warn "Secret ${github_secret_name} already exists, skipping"
                skipped=$((skipped + 1))
                continue
            fi
        fi
        
        if [[ "$dry_run" == "true" ]]; then
            log_info "[DRY RUN] Would create secret: ${github_secret_name} (from ${key})"
            if [[ "$secured" == "true" ]]; then
                log_info "  Value: [SECURED - hidden in Bitbucket]"
            else
                log_info "  Value: ${value:0:20}..."
            fi
        else
            log_info "Creating secret: ${github_secret_name}..."
            
            # Set GitHub secret
            if echo -n "$value" | gh secret set "$github_secret_name" --repo "$github_repo" 2>/dev/null; then
                log_success "Created secret: ${github_secret_name}"
                count=$((count + 1))
            else
                log_error "Failed to create secret: ${github_secret_name}"
                failed=$((failed + 1))
            fi
        fi
    done
    
    if [[ "$dry_run" != "true" ]]; then
        echo ""
        log_success "Migration complete!"
        log_info "Created: $count secrets"
        if [[ $skipped -gt 0 ]]; then
            log_info "Skipped: $skipped secrets (already exist)"
        fi
        if [[ $failed -gt 0 ]]; then
            log_warn "Failed: $failed secrets"
        fi
    fi
}

# Parse arguments
BITBUCKET_WORKSPACE=""
BITBUCKET_REPO=""
GITHUB_REPO=""
BITBUCKET_USERNAME=""
BITBUCKET_PASSWORD="${BITBUCKET_APP_PASSWORD:-}"
DRY_RUN=false
SKIP_EXISTING=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            show_help
            exit 0
            ;;
        --username)
            BITBUCKET_USERNAME="$2"
            shift 2
            ;;
        --password)
            BITBUCKET_PASSWORD="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --skip-existing)
            SKIP_EXISTING=true
            shift
            ;;
        --mapping)
            log_warn "Custom mapping file not yet implemented"
            shift 2
            ;;
        -*)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
        *)
            if [[ -z "$BITBUCKET_WORKSPACE" ]]; then
                BITBUCKET_WORKSPACE="$1"
            elif [[ -z "$BITBUCKET_REPO" ]]; then
                BITBUCKET_REPO="$1"
            elif [[ -z "$GITHUB_REPO" ]]; then
                GITHUB_REPO="$1"
            fi
            shift
            ;;
    esac
done

# Validate arguments
if [[ -z "$BITBUCKET_WORKSPACE" ]] || [[ -z "$BITBUCKET_REPO" ]] || [[ -z "$GITHUB_REPO" ]]; then
    log_error "Missing required arguments"
    echo ""
    show_help
    exit 1
fi

# Get Bitbucket credentials
# Try LastPass first (same method as vault-pass-lastpass uses)
VAULT_PASS_SCRIPT="/home/steve/Agent007/DevOps/bin/vault-pass-lastpass"

if [[ -z "$BITBUCKET_USERNAME" ]] && [[ -f "$VAULT_PASS_SCRIPT" ]]; then
    log_info "Checking LastPass for Bitbucket credentials..."
    if bash "$VAULT_PASS_SCRIPT" >/dev/null 2>&1; then
        # Try various LastPass entry names
        BITBUCKET_USERNAME=$(lpass show "Shared-DevOps/Bitbucket Username" --field="Username" 2>/dev/null || \
                             lpass show "Shared-DevOps/Bitbucket" --field="Username" 2>/dev/null || \
                             lpass show "Shared-DevOps/Bitbucket" --username 2>/dev/null || \
                             lpass show "Shared-PLS-Firewalls/Firewalls/Bitbucket" --username 2>/dev/null || \
                             echo "")
        if [[ -n "$BITBUCKET_USERNAME" ]]; then
            log_success "Found Bitbucket username in LastPass"
        fi
    fi
fi

if [[ -z "$BITBUCKET_PASSWORD" ]] && [[ -f "$VAULT_PASS_SCRIPT" ]]; then
    if bash "$VAULT_PASS_SCRIPT" >/dev/null 2>&1; then
        # Try various LastPass entry names for password
        BITBUCKET_PASSWORD=$(lpass show "Shared-DevOps/Bitbucket App Password" --password 2>/dev/null || \
                            lpass show "Shared-DevOps/Bitbucket" --field="App Password" 2>/dev/null || \
                            lpass show "Shared-DevOps/Bitbucket" --password 2>/dev/null || \
                            lpass show "Shared-PLS-Firewalls/Firewalls/Bitbucket" --password 2>/dev/null || \
                            echo "")
        if [[ -n "$BITBUCKET_PASSWORD" ]]; then
            log_success "Found Bitbucket password in LastPass"
        fi
    fi
fi

# Also check Ansible vault (in case credentials are stored there)
VAULT_FILE="/home/steve/Agent007/DevOps/ansible/group_vars/pressable/vault.yml"
if [[ -z "$BITBUCKET_USERNAME" ]] && [[ -f "$VAULT_FILE" ]] && [[ -f "$VAULT_PASS_SCRIPT" ]]; then
    log_info "Checking Ansible vault for Bitbucket credentials..."
    if command -v ansible-vault >/dev/null 2>&1 && bash "$VAULT_PASS_SCRIPT" >/dev/null 2>&1; then
        vault_content=$(ansible-vault view "$VAULT_FILE" --vault-password-file="$VAULT_PASS_SCRIPT" 2>/dev/null || echo "")
        if [[ -n "$vault_content" ]]; then
            BITBUCKET_USERNAME=$(echo "$vault_content" | grep -iE "bitbucket.*username|bitbucket_username" | head -1 | sed -E 's/.*[:=][[:space:]]*["'\'']?([^"'\'']+)["'\'']?.*/\1/' || echo "")
            if [[ -n "$BITBUCKET_USERNAME" ]]; then
                log_success "Found Bitbucket username in Ansible vault"
            fi
        fi
    fi
fi

if [[ -z "$BITBUCKET_PASSWORD" ]] && [[ -f "$VAULT_FILE" ]] && [[ -f "$VAULT_PASS_SCRIPT" ]]; then
    if command -v ansible-vault >/dev/null 2>&1 && bash "$VAULT_PASS_SCRIPT" >/dev/null 2>&1; then
        vault_content=$(ansible-vault view "$VAULT_FILE" --vault-password-file="$VAULT_PASS_SCRIPT" 2>/dev/null || echo "")
        if [[ -n "$vault_content" ]]; then
            BITBUCKET_PASSWORD=$(echo "$vault_content" | grep -iE "bitbucket.*password|bitbucket.*app.*password|bitbucket_app_password" | head -1 | sed -E 's/.*[:=][[:space:]]*["'\'']?([^"'\'']+)["'\'']?.*/\1/' || echo "")
            if [[ -n "$BITBUCKET_PASSWORD" ]]; then
                log_success "Found Bitbucket password in Ansible vault"
            fi
        fi
    fi
fi

# Fallback to prompts if not found
if [[ -z "$BITBUCKET_USERNAME" ]]; then
    read -p "Bitbucket username: " BITBUCKET_USERNAME
fi

if [[ -z "$BITBUCKET_PASSWORD" ]]; then
    read -sp "Bitbucket app password: " BITBUCKET_PASSWORD
    echo ""
fi

# Main execution
main() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  🔄 Migrate Bitbucket Variables to GitHub Secrets${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "DRY RUN MODE - No secrets will be created"
    fi
    
    check_prerequisites
    echo ""
    
    log_info "Bitbucket: ${BITBUCKET_WORKSPACE}/${BITBUCKET_REPO}"
    log_info "GitHub: ${GITHUB_REPO}"
    echo ""
    
    # Fetch variables
    local variables_json
    variables_json=$(get_bitbucket_variables "$BITBUCKET_WORKSPACE" "$BITBUCKET_REPO" "$BITBUCKET_USERNAME" "$BITBUCKET_PASSWORD")
    
    if [[ -z "$variables_json" ]] || [[ "$variables_json" == "[]" ]]; then
        log_warn "No variables found to migrate"
        exit 0
    fi
    
    local var_count
    var_count=$(echo "$variables_json" | jq 'length' 2>/dev/null || echo "0")
    log_info "Found $var_count variable(s) in Bitbucket"
    echo ""
    
    # Migrate variables
    migrate_variables "$variables_json" "$GITHUB_REPO" "$DRY_RUN" "$SKIP_EXISTING"
    
    echo ""
    log_success "=== Migration Complete ==="
}

main
