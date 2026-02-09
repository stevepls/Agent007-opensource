# CW Staging Auto-Deploy Setup

## Current Status

**Workflow File**: `.github/workflows/deploy.yml.disabled` (DISABLED)

The deployment workflow exists but is currently disabled and configured to trigger on `release-*` branches, not on PR merges to `staging`.

## What's Missing

### 1. **Workflow Not Enabled**
- File is named `deploy.yml.disabled` instead of `deploy.yml`
- GitHub Actions won't run disabled workflows

### 2. **Missing Trigger for Staging Branch**
Current trigger (line 96-98):
```yaml
if: |
  (github.event_name == 'push' && startsWith(github.ref, 'refs/heads/release-')) ||
  (github.event_name == 'workflow_dispatch' && github.event.inputs.environment == 'staging')
```

**Missing**: Trigger for PR merges into `staging` branch

### 3. **Required GitHub Secrets**
The workflow requires these secrets to be configured in GitHub:

#### Staging Secrets
- `STAGING_SSH_KEY` - SSH private key for staging server
- `STAGING_HOST` - Server IP/hostname (e.g., `35.84.165.174`)
- `STAGING_USER` - SSH username (e.g., `ubuntu`)
- `STAGING_PATH` - Magento path (e.g., `/var/www/html`)
- `STAGING_URL` - Staging site URL

### 4. **GitHub Environment Configuration**
- Environment `staging` needs to be created in GitHub Settings → Environments
- Protection rules (if any) need to be configured

## Solution: Enable Auto-Deploy on Staging Merge

### Step 1: Enable the Workflow

```bash
cd /home/steve/Sites/forge-lab/cw
mv .github/workflows/deploy.yml.disabled .github/workflows/deploy.yml
```

### Step 2: Update Trigger to Include Staging Branch

Modify the `deploy-staging` job condition to trigger on:
1. Push to `release-*` branches (existing)
2. **PR merge to `staging` branch** (NEW)
3. Manual dispatch (existing)

**Updated condition**:
```yaml
if: |
  (github.event_name == 'push' && (
    startsWith(github.ref, 'refs/heads/release-') ||
    github.ref == 'refs/heads/staging'
  )) ||
  (github.event_name == 'workflow_dispatch' && github.event.inputs.environment == 'staging' && github.event.inputs.observability_only != 'true')
```

### Step 3: Configure GitHub Secrets

Go to: **GitHub Repo → Settings → Secrets and variables → Actions**

Add these secrets:

| Secret Name | Value | Example |
|------------|-------|---------|
| `STAGING_SSH_KEY` | SSH private key | `-----BEGIN OPENSSH PRIVATE KEY-----...` |
| `STAGING_HOST` | Server IP | `35.84.165.174` |
| `STAGING_USER` | SSH username | `ubuntu` |
| `STAGING_PATH` | Magento path | `/var/www/html` |
| `STAGING_URL` | Site URL | `https://staging.collegewise.com` |

**To get SSH key**:
```bash
# If you have SSH access, generate a deploy key:
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_actions_deploy
# Add public key to server's authorized_keys
# Use private key as STAGING_SSH_KEY secret
```

### Step 4: Create GitHub Environment

1. Go to **Settings → Environments**
2. Click **New environment**
3. Name: `staging`
4. **Deployment branches**: Allow `staging` branch
5. **Protection rules** (optional):
   - No required reviewers (for auto-deploy)
   - No wait timer

### Step 5: Test the Workflow

1. **Test with manual trigger**:
   - Go to Actions → Deploy Magento
   - Click "Run workflow"
   - Select environment: `staging`
   - Click "Run workflow"

2. **Test with PR merge**:
   - Merge a PR into `staging` branch
   - Check Actions tab for deployment

## Alternative: Simpler Trigger (Recommended)

For automatic deployment on every merge to staging, use this simpler condition:

```yaml
deploy-staging:
  name: Deploy to Staging
  runs-on: ubuntu-latest
  environment: staging
  if: |
    (github.event_name == 'push' && github.ref == 'refs/heads/staging') ||
    (github.event_name == 'workflow_dispatch' && github.event.inputs.environment == 'staging' && github.event.inputs.observability_only != 'true')
```

This will:
- ✅ Auto-deploy on every push/merge to `staging` branch
- ✅ Still allow manual dispatch
- ✅ Skip `release-*` branches (remove if you want those too)

## Deployment Process

When triggered, the workflow will:

1. **Checkout code** from the merged commit
2. **Setup SSH** using the stored SSH key
3. **Sync code** to staging server via rsync
4. **Run Magento deployment**:
   - Enable maintenance mode
   - `composer install --no-dev`
   - `bin/magento setup:upgrade`
   - `bin/magento setup:di:compile`
   - `bin/magento setup:static-content:deploy`
   - `bin/magento cache:flush`
   - Fix permissions
   - Disable maintenance mode
5. **Deploy observability stack** (if enabled)
6. **Run health checks**

## Verification Checklist

- [ ] Workflow file renamed from `.disabled` to active
- [ ] Trigger condition updated to include `staging` branch
- [ ] All required secrets configured in GitHub
- [ ] `staging` environment created in GitHub
- [ ] SSH key added to server's `authorized_keys`
- [ ] Test manual deployment works
- [ ] Test PR merge triggers deployment

## Troubleshooting

### Workflow Not Triggering
- Check workflow file is in `.github/workflows/` (not `.disabled`)
- Verify branch name matches exactly: `staging`
- Check Actions tab for any errors

### SSH Connection Failed
- Verify `STAGING_SSH_KEY` secret is correct (full key including headers)
- Check server firewall allows GitHub Actions IPs
- Test SSH manually: `ssh -i <key> ubuntu@35.84.165.174`

### Deployment Fails
- Check server has enough disk space
- Verify file permissions on server
- Check Magento logs: `var/log/system.log`, `var/log/exception.log`

### Secrets Not Found
- Ensure secrets are in the correct repository (not organization-level)
- Check secret names match exactly (case-sensitive)

## Next Steps

1. **Enable workflow**: Rename file and update trigger
2. **Configure secrets**: Add all required SSH/server secrets
3. **Test**: Merge a test PR to staging
4. **Monitor**: Watch first few deployments to ensure stability
5. **Document**: Update team on new auto-deploy process

## Rollback Plan

If auto-deploy causes issues:

1. **Disable workflow**: Rename back to `.disabled`
2. **Manual deploy**: Use `deploy.sh` script directly on server
3. **Fix issues**: Address any problems before re-enabling

---

**Status**: Ready to implement - workflow exists, just needs enabling and trigger update
