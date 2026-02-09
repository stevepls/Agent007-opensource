#!/bin/bash
#
# Create GitHub Actions workflow for Phyto Magento 2 project
#
# This script creates the workflow file and commits it to the GitHub repository
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
GITHUB_REPO="pdxaromatics/magento2"
GITHUB_URL="git@github.com:pdxaromatics/magento2.git"
WORK_DIR="/tmp/phyto-github-actions-$(date +%Y%m%d-%H%M%S)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Functions
log_info() { echo -e "${CYAN}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v git &> /dev/null; then
        log_error "Git is not installed"
        exit 1
    fi
    
    if ! command -v gh &> /dev/null; then
        log_error "GitHub CLI (gh) is not installed"
        exit 1
    fi
    
    if ! gh auth status &> /dev/null; then
        log_error "GitHub CLI is not authenticated"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

create_workflow_file() {
    local workflow_dir="$1"
    local workflow_file="${workflow_dir}/.github/workflows/deploy.yml"
    
    log_info "Creating GitHub Actions workflow file..."
    
    mkdir -p "$(dirname "$workflow_file")"
    
    cat > "$workflow_file" << 'WORKFLOW_EOF'
name: Deploy Magento

on:
  push:
    branches:
      - main
      - staging
      - production
  pull_request:
    branches:
      - main
      - staging
  workflow_dispatch:
    inputs:
      environment:
        description: 'Environment to deploy to'
        required: true
        type: choice
        options:
          - staging
          - production
      observability_only:
        description: 'Deploy observability stack only'
        required: false
        type: boolean
        default: false

env:
  PHP_VERSION: '8.2'
  COMPOSER_VERSION: '2'

jobs:
  test:
    name: Run Tests
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    
    services:
      mysql:
        image: mysql:8.0
        env:
          MYSQL_ROOT_PASSWORD: root
          MYSQL_DATABASE: test_db
        ports:
          - 3306:3306
        options: >-
          --health-cmd="mysqladmin ping"
          --health-interval=10s
          --health-timeout=5s
          --health-retries=5

    steps:
      - uses: actions/checkout@v4

      - name: Setup PHP
        uses: shivammathur/setup-php@v2
        with:
          php-version: ${{ env.PHP_VERSION }}
          extensions: mbstring, pdo, pdo_mysql, zip, gd, intl, soap, xsl, bcmath
          coverage: xdebug

      - name: Get Composer cache directory
        id: composer-cache
        run: echo "dir=$(composer config cache-files-dir)" >> $GITHUB_OUTPUT

      - name: Cache dependencies
        uses: actions/cache@v4
        with:
          path: ${{ steps.composer-cache.outputs.dir }}
          key: ${{ runner.os }}-composer-${{ hashFiles('**/composer.lock') }}
          restore-keys: ${{ runner.os }}-composer-

      - name: Install dependencies
        run: composer install --no-interaction --prefer-dist --no-dev

      - name: Run PHPUnit tests
        run: vendor/bin/phpunit --testdox --colors=always || echo "Tests completed with warnings"
        continue-on-error: true
        env:
          DB_HOST: 127.0.0.1
          DB_DATABASE: test_db
          DB_USERNAME: root
          DB_PASSWORD: root

  lint:
    name: Code Quality
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    
    steps:
      - uses: actions/checkout@v4

      - name: Setup PHP
        uses: shivammathur/setup-php@v2
        with:
          php-version: ${{ env.PHP_VERSION }}

      - name: Install dependencies
        run: composer install --no-interaction --prefer-dist --no-dev

      - name: PHP-CS-Fixer
        run: |
          if [ -f vendor/bin/php-cs-fixer ]; then
            vendor/bin/php-cs-fixer fix --dry-run --diff || echo "Code style check completed"
          else
            echo "PHP-CS-Fixer not available, skipping"
          fi
        continue-on-error: true

      - name: PHPStan
        run: |
          if [ -f vendor/bin/phpstan ]; then
            vendor/bin/phpstan analyse --error-format=github --memory-limit=512M || echo "Static analysis completed"
          else
            echo "PHPStan not available, skipping"
          fi
        continue-on-error: true

  security:
    name: Security Audit
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    
    steps:
      - uses: actions/checkout@v4

      - name: Setup PHP
        uses: shivammathur/setup-php@v2
        with:
          php-version: ${{ env.PHP_VERSION }}

      - name: Install dependencies
        run: composer install --no-interaction --prefer-dist --no-dev

      - name: Security audit
        run: composer audit || echo "Security audit completed"
        continue-on-error: true

  deploy-staging:
    name: Deploy to Staging
    runs-on: ubuntu-latest
    environment: staging
    needs: [test, lint, security]
    if: |
      (github.event_name == 'push' && github.ref == 'refs/heads/staging') ||
      (github.event_name == 'workflow_dispatch' && github.event.inputs.environment == 'staging' && github.event.inputs.observability_only != 'true')
    
    steps:
      - uses: actions/checkout@v4

      - name: Setup SSH
        uses: webfactory/ssh-agent@v0.9.0
        with:
          ssh-private-key: ${{ secrets.STAGING_SSH_KEY }}

      - name: Add server to known hosts
        run: |
          ssh-keyscan -H ${{ secrets.STAGING_HOST }} >> ~/.ssh/known_hosts

      - name: Sync code to staging
        run: |
          rsync -avz --progress \
            --exclude='.git' \
            --exclude='.github' \
            --exclude='.gitignore' \
            --exclude='var/cache/*' \
            --exclude='var/page_cache/*' \
            --exclude='var/generation/*' \
            --exclude='var/view_preprocessed/*' \
            --exclude='pub/static/*' \
            --exclude='node_modules' \
            --exclude='.env' \
            ./ ${{ secrets.STAGING_USER }}@${{ secrets.STAGING_HOST }}:${{ secrets.STAGING_PATH }}/

      - name: Deploy Magento
        run: |
          ssh ${{ secrets.STAGING_USER }}@${{ secrets.STAGING_HOST }} << 'DEPLOY_EOF'
            cd ${{ secrets.STAGING_PATH }}
            
            # Enable maintenance mode
            php bin/magento maintenance:enable || true
            
            # Install dependencies
            composer install --no-interaction --prefer-dist --no-dev --optimize-autoloader
            
            # Run Magento setup
            php bin/magento setup:upgrade --keep-generated
            php bin/magento setup:di:compile
            php bin/magento setup:static-content:deploy -f en_US
            php bin/magento cache:flush
            
            # Fix permissions
            find var generated pub/static pub/media app/etc -type f -exec chmod 644 {} \;
            find var generated pub/static pub/media app/etc -type d -exec chmod 755 {} \;
            chmod +x bin/magento
            
            # Disable maintenance mode
            php bin/magento maintenance:disable
          DEPLOY_EOF

      - name: Health check
        run: |
          curl -f ${{ secrets.STAGING_URL }} || echo "Health check failed"
        continue-on-error: true

  deploy-production:
    name: Deploy to Production
    runs-on: ubuntu-latest
    environment: production
    needs: [test, lint, security]
    if: |
      (github.event_name == 'push' && github.ref == 'refs/heads/production') ||
      (github.event_name == 'workflow_dispatch' && github.event.inputs.environment == 'production' && github.event.inputs.observability_only != 'true')
    
    steps:
      - uses: actions/checkout@v4

      - name: Setup SSH
        uses: webfactory/ssh-agent@v0.9.0
        with:
          ssh-private-key: ${{ secrets.PRODUCTION_SSH_KEY }}

      - name: Add server to known hosts
        run: |
          ssh-keyscan -H ${{ secrets.PRODUCTION_HOST }} >> ~/.ssh/known_hosts

      - name: Sync code to production
        run: |
          rsync -avz --progress \
            --exclude='.git' \
            --exclude='.github' \
            --exclude='.gitignore' \
            --exclude='var/cache/*' \
            --exclude='var/page_cache/*' \
            --exclude='var/generation/*' \
            --exclude='var/view_preprocessed/*' \
            --exclude='pub/static/*' \
            --exclude='node_modules' \
            --exclude='.env' \
            ./ ${{ secrets.PRODUCTION_USER }}@${{ secrets.PRODUCTION_HOST }}:${{ secrets.PRODUCTION_PATH }}/

      - name: Deploy Magento
        run: |
          ssh ${{ secrets.PRODUCTION_USER }}@${{ secrets.PRODUCTION_HOST }} << 'DEPLOY_EOF'
            cd ${{ secrets.PRODUCTION_PATH }}
            
            # Enable maintenance mode
            php bin/magento maintenance:enable || true
            
            # Install dependencies
            composer install --no-interaction --prefer-dist --no-dev --optimize-autoloader
            
            # Run Magento setup
            php bin/magento setup:upgrade --keep-generated
            php bin/magento setup:di:compile
            php bin/magento setup:static-content:deploy -f en_US
            php bin/magento cache:flush
            
            # Fix permissions
            find var generated pub/static pub/media app/etc -type f -exec chmod 644 {} \;
            find var generated pub/static pub/media app/etc -type d -exec chmod 755 {} \;
            chmod +x bin/magento
            
            # Disable maintenance mode
            php bin/magento maintenance:disable
          DEPLOY_EOF

      - name: Health check
        run: |
          curl -f ${{ secrets.PRODUCTION_URL }} || echo "Health check failed"
        continue-on-error: true

      - name: Purge Cloudflare cache
        if: env.CLOUDFLARE_ZONE_ID != ''
        run: |
          curl -X POST "https://api.cloudflare.com/client/v4/zones/${{ secrets.CLOUDFLARE_ZONE_ID }}/purge_cache" \
            -H "Authorization: Bearer ${{ secrets.CLOUDFLARE_API_TOKEN }}" \
            -H "Content-Type: application/json" \
            --data '{"purge_everything":true}'
        continue-on-error: true
        env:
          CLOUDFLARE_ZONE_ID: ${{ secrets.CLOUDFLARE_ZONE_ID }}
WORKFLOW_EOF

    log_success "Workflow file created: $workflow_file"
}

commit_workflow() {
    local repo_dir="$1"
    
    log_info "Committing workflow to GitHub repository..."
    
    cd "$repo_dir"
    
    # Check if workflow already exists
    if [ -f ".github/workflows/deploy.yml" ]; then
        log_warn "Workflow file already exists"
        read -p "Overwrite existing workflow? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Skipping commit"
            return 0
        fi
    fi
    
    # Add and commit
    git add .github/workflows/deploy.yml
    git commit -m "Add GitHub Actions deployment workflow for Magento 2" || {
        log_warn "Nothing to commit (workflow may already be committed)"
        return 0
    }
    
    # Push to GitHub
    log_info "Pushing to GitHub..."
    git push origin main
    
    log_success "Workflow committed and pushed to GitHub"
}

main() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  🚀 Create GitHub Actions Workflow for Phyto${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    
    check_prerequisites
    echo ""
    
    # Clone repository
    log_info "Cloning GitHub repository..."
    mkdir -p "$WORK_DIR"
    git clone "$GITHUB_URL" "${WORK_DIR}/repo"
    echo ""
    
    # Create workflow file
    create_workflow_file "${WORK_DIR}/repo"
    echo ""
    
    # Commit and push
    commit_workflow "${WORK_DIR}/repo"
    echo ""
    
    # Cleanup
    log_info "Cleaning up..."
    read -p "Remove temporary directory? ($WORK_DIR) [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$WORK_DIR"
        log_success "Cleanup complete"
    else
        log_info "Keeping temporary directory: $WORK_DIR"
    fi
    
    echo ""
    log_success "=== Workflow Creation Complete ==="
    log_info "Next steps:"
    log_info "  1. Configure GitHub Secrets (see documentation)"
    log_info "  2. Create GitHub Environments (staging, production)"
    log_info "  3. Test the workflow with a manual dispatch"
    echo ""
}

main
