# CW Staging Auto-Deploy Configuration - COMPLETE ✅

## Configuration Status

All required configuration for auto-deploy on staging branch merges has been completed.

### ✅ 1. Workflow Enabled
- **File**: `.github/workflows/deploy.yml` (active)
- **Status**: Enabled and committed to `staging` branch
- **Trigger**: Updated to include `staging` branch merges

### ✅ 2. GitHub Secrets Configured

All required secrets are now set in GitHub:

| Secret | Status | Value |
|--------|--------|-------|
| `STAGING_SSH_KEY` | ✅ Configured | SSH private key for staging server |
| `STAGING_HOST` | ✅ Configured | `35.84.165.174` |
| `STAGING_USER` | ✅ Configured | `ubuntu` |
| `STAGING_PATH` | ✅ Configured | `/var/www/html` |
| `STAGING_URL` | ✅ Configured | Staging site URL |

**Verification**:
```bash
gh secret list | grep STAGING
```

### ✅ 3. GitHub Environment Configured

**Environment**: `staging`
- **Status**: ✅ Created and configured
- **Deployment Branch Policy**: ✅ Custom branch policies enabled
- **Branch Policy**: ✅ `staging` branch allowed
- **Protection Rules**: 1 rule (branch policy)
- **Admin Bypass**: Enabled

**Configuration**:
- `deployment_branch_policy.custom_branch_policies`: `true`
- `deployment_branch_policy.protected_branches`: `false`
- Branch policy name: `staging` (matches branch name)

**Verification**:
```bash
gh api repos/collegewise1/cw-magento/environments/staging
```

## How It Works

### Automatic Deployment Flow

1. **PR Merged to Staging**
   - Developer merges PR into `staging` branch
   - GitHub Actions workflow automatically triggers

2. **Workflow Execution**
   - Checks out code from merged commit
   - Sets up SSH connection using `STAGING_SSH_KEY`
   - Syncs code to staging server via rsync

3. **Magento Deployment**
   - Enables maintenance mode
   - Runs `composer install --no-dev`
   - Runs `bin/magento setup:upgrade`
   - Runs `bin/magento setup:di:compile`
   - Runs `bin/magento setup:static-content:deploy`
   - Flushes cache
   - Fixes permissions
   - Disables maintenance mode

4. **Observability Stack** (optional)
   - Deploys Grafana/Loki stack if enabled

5. **Health Checks**
   - Verifies Magento frontend is responding
   - Checks Grafana health

## Testing

### Test the Workflow

1. **Manual Test**:
   ```bash
   # Go to GitHub Actions tab
   # Click "Deploy Magento" workflow
   # Click "Run workflow"
   # Select environment: staging
   # Click "Run workflow"
   ```

2. **Automatic Test**:
   - Merge any PR into `staging` branch
   - Check Actions tab for deployment run
   - Verify deployment completes successfully

### Verify Configuration

```bash
# Check secrets
gh secret list | grep STAGING

# Check environment
gh api repos/collegewise1/cw-magento/environments/staging

# Check branch policies
gh api repos/collegewise1/cw-magento/environments/staging/deployment-branch-policies
```

## Deployment Details

### Server Information
- **Host**: `35.84.165.174`
- **User**: `ubuntu`
- **Path**: `/var/www/html`
- **URL**: (configured in `STAGING_URL` secret)

### Deployment Steps
1. Code sync (rsync with exclusions)
2. Composer install (production mode)
3. Magento setup:upgrade
4. Magento DI compile
5. Static content deploy
6. Cache flush
7. Permission fixes
8. Maintenance mode toggle

## Troubleshooting

### Workflow Not Triggering
- Verify workflow file is in `.github/workflows/deploy.yml`
- Check branch name matches exactly: `staging`
- Verify trigger condition in workflow file

### SSH Connection Failed
- Verify `STAGING_SSH_KEY` secret is correct
- Check server firewall allows GitHub Actions IPs
- Test SSH manually: `ssh -i <key> ubuntu@35.84.165.174`

### Deployment Fails
- Check server disk space
- Verify file permissions
- Check Magento logs: `var/log/system.log`

### Secrets Not Found
- Ensure secrets are repository-level (not organization)
- Check secret names match exactly (case-sensitive)

## Next Actions

The pipeline is now fully configured and ready to use. When you merge a PR into the `staging` branch, it will automatically:

1. ✅ Trigger the deployment workflow
2. ✅ Deploy code to staging server
3. ✅ Run Magento deployment steps
4. ✅ Perform health checks

**No further manual configuration needed!**

---

**Configuration Date**: 2026-02-06
**Status**: ✅ Complete
**Workflow**: Active
**Secrets**: All configured
**Environment**: Configured with branch policy
