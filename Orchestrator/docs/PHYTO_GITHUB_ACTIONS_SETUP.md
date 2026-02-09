# Phyto GitHub Actions Setup Guide

## ✅ Workflow Created

The GitHub Actions deployment workflow has been created and committed to the repository.

**Workflow File**: `.github/workflows/deploy.yml`  
**Repository**: `pdxaromatics/magento2`  
**Status**: ✅ Active

## Workflow Features

### Jobs Included

1. **Test** - Runs PHPUnit tests on pull requests
2. **Lint** - Code quality checks (PHP-CS-Fixer, PHPStan)
3. **Security** - Security audit (Composer audit)
4. **Deploy to Staging** - Automatic deployment on push to `staging` branch
5. **Deploy to Production** - Automatic deployment on push to `production` branch

### Triggers

- **Pull Requests**: Runs tests, lint, and security checks
- **Push to `staging`**: Automatically deploys to staging
- **Push to `production`**: Automatically deploys to production
- **Manual Dispatch**: Can manually trigger deployment via GitHub Actions UI

## Required GitHub Secrets

The workflow requires the following secrets to be configured in GitHub:

### Staging Secrets

| Secret Name | Description | Example |
|------------|-------------|---------|
| `STAGING_SSH_KEY` | SSH private key for staging server | Full SSH private key (including headers) |
| `STAGING_HOST` | Staging server hostname/IP | `staging.example.com` or `192.168.1.100` |
| `STAGING_USER` | SSH username | `ubuntu`, `deploy`, `www-data` |
| `STAGING_PATH` | Magento installation path | `/var/www/html` |
| `STAGING_URL` | Staging site URL | `https://staging.phyto.com` |

### Production Secrets

| Secret Name | Description | Example |
|------------|-------------|---------|
| `PRODUCTION_SSH_KEY` | SSH private key for production server | Full SSH private key (including headers) |
| `PRODUCTION_HOST` | Production server hostname/IP | `prod.example.com` or `192.168.1.101` |
| `PRODUCTION_USER` | SSH username | `ubuntu`, `deploy`, `www-data` |
| `PRODUCTION_PATH` | Magento installation path | `/var/www/html` |
| `PRODUCTION_URL` | Production site URL | `https://phyto.com` |

### Optional Secrets

| Secret Name | Description | When Needed |
|------------|-------------|-------------|
| `CLOUDFLARE_ZONE_ID` | Cloudflare zone ID | If using Cloudflare cache purge |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token | If using Cloudflare cache purge |

## Setup Instructions

### Step 1: Configure GitHub Secrets

1. Go to: **GitHub Repository → Settings → Secrets and variables → Actions**
2. Click **New repository secret** for each secret listed above
3. Add all required secrets

**To get SSH key**:
```bash
# Generate a new SSH key for deployment (if needed)
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/phyto_deploy_key

# Add public key to server's authorized_keys
ssh-copy-id -i ~/.ssh/phyto_deploy_key.pub user@staging-server

# Copy private key content for GitHub secret
cat ~/.ssh/phyto_deploy_key
# Copy the entire output (including BEGIN/END lines) to STAGING_SSH_KEY secret
```

### Step 2: Create GitHub Environments

1. Go to: **Settings → Environments**
2. Click **New environment**
3. Create two environments:

#### Staging Environment
- **Name**: `staging`
- **Deployment branches**: Allow `staging` branch
- **Protection rules**: Optional (recommend no required reviewers for auto-deploy)

#### Production Environment
- **Name**: `production`
- **Deployment branches**: Allow `production` branch
- **Protection rules**: Recommended to require approval for production deployments

### Step 3: Verify Workflow

1. Go to: **Actions** tab in GitHub repository
2. You should see "Deploy Magento" workflow listed
3. Test with manual dispatch:
   - Click "Deploy Magento" workflow
   - Click "Run workflow"
   - Select environment: `staging`
   - Click "Run workflow"

## Deployment Process

When triggered, the workflow will:

1. **Checkout code** from the branch
2. **Run tests** (on pull requests only)
3. **Setup SSH** connection using stored SSH key
4. **Sync code** to server via rsync (excludes cache, node_modules, etc.)
5. **Deploy Magento**:
   - Enable maintenance mode
   - `composer install --no-dev --optimize-autoloader`
   - `bin/magento setup:upgrade --keep-generated`
   - `bin/magento setup:di:compile`
   - `bin/magento setup:static-content:deploy -f en_US`
   - `bin/magento cache:flush`
   - Fix file permissions
   - Disable maintenance mode
6. **Health check** - Verify site is responding
7. **Purge Cloudflare cache** (if configured)

## Branch Strategy

- **`main`**: Development branch, runs tests on PRs
- **`staging`**: Auto-deploys to staging on push
- **`production`**: Auto-deploys to production on push (with environment protection)

## Testing the Workflow

### Test Pull Request Workflow
1. Create a pull request to `main` or `staging`
2. Check Actions tab - should see test, lint, and security jobs running

### Test Staging Deployment
1. Push to `staging` branch:
   ```bash
   git checkout staging
   git push origin staging
   ```
2. Check Actions tab - should see deployment job running

### Test Manual Deployment
1. Go to Actions → Deploy Magento
2. Click "Run workflow"
3. Select environment and click "Run workflow"

## Troubleshooting

### Workflow Not Triggering
- Verify workflow file is in `.github/workflows/deploy.yml`
- Check branch name matches exactly: `staging` or `production`
- Verify workflow syntax is valid (check Actions tab for errors)

### SSH Connection Failed
- Verify SSH key secret is correct (full key including headers)
- Check server firewall allows GitHub Actions IPs
- Test SSH manually: `ssh -i <key> user@host`
- Ensure public key is in server's `~/.ssh/authorized_keys`

### Deployment Fails
- Check server has enough disk space
- Verify file permissions on server
- Check Magento logs: `var/log/system.log`, `var/log/exception.log`
- Ensure PHP version matches (workflow uses PHP 8.2)
- Verify Composer is installed on server

### Secrets Not Found
- Ensure secrets are in the correct repository (not organization-level)
- Check secret names match exactly (case-sensitive)
- Verify secrets are not expired

### Permission Denied
- Check SSH key has correct permissions on server
- Verify user has write access to deployment path
- Ensure Magento bin/magento is executable

## Next Steps

1. ✅ Workflow created and committed
2. ⬜ Configure GitHub Secrets (Step 1)
3. ⬜ Create GitHub Environments (Step 2)
4. ⬜ Test workflow with manual dispatch
5. ⬜ Test automatic deployment on staging branch
6. ⬜ Configure production environment protection rules
7. ⬜ Update team documentation

## Verification Commands

```bash
# Check workflow exists
gh workflow list --repo pdxaromatics/magento2

# View workflow runs
gh run list --repo pdxaromatics/magento2 --workflow "Deploy Magento"

# Check secrets (names only, not values)
gh secret list --repo pdxaromatics/magento2

# Check environments
gh api repos/pdxaromatics/magento2/environments
```

---

**Last Updated**: 2026-02-06  
**Status**: Workflow created, awaiting secret configuration
