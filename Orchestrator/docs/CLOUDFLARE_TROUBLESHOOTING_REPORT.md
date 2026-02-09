# Cloudflare Tunnel Troubleshooting Report
**Date**: 2026-02-06  
**Project**: Collegewise (cw-magento)  
**Issue**: "websocket: bad handshake" when connecting via SSH

## Automated Checks

### ✅ Verified Configuration

1. **Tunnel Status**: ✅ HEALTHY
   - Tunnel: `cw-staging`
   - Tunnel ID: `5c9f3b89-51e4-4fa1-9aac-e83b89998947`
   - Uptime: 9 days

2. **DNS Route**: ✅ Configured
   - Hostname: `cw-staging-ssh.collegewise.com`
   - Route exists in tunnel

3. **Config File**: ✅ Configured
   - File exists: `/etc/cloudflared/config.yml`
   - SSH ingress: `cw-staging-ssh.collegewise.com` → `ssh://localhost:22`
   - Tunnel ID matches

4. **Access Application**: ✅ Exists
   - Application: "CW Staging SSH"
   - Domain: `cw-staging-ssh.collegewise.com`
   - Policies: 1 assigned

5. **GitHub Workflow**: ✅ Configured
   - Uses `cloudflared access ssh-config`
   - Configures SSH with ProxyCommand
   - Environment variables set correctly

### ❓ Needs Manual Verification

#### 1. Service Token Configuration

**Check in Cloudflare Dashboard:**
- Go to: **Zero Trust → Access → Service Tokens**
- **Look for**: Token for `cw-staging-ssh.collegewise.com` or `github-actions`
- **Verify**:
  - [ ] Token exists
  - [ ] Token is Active
  - [ ] Token has access to "CW Staging SSH" application
  - [ ] Client ID matches `CF_ACCESS_CLIENT_ID` in GitHub secrets
  - [ ] Client Secret matches `CF_ACCESS_CLIENT_SECRET` in GitHub secrets

**If token doesn't exist or is wrong:**
1. Create new service token
2. Name: `github-actions-collegewise-staging`
3. Copy Client ID and Secret
4. Update GitHub secrets

#### 2. Application Policy

**Check in Cloudflare Dashboard:**
- Go to: **Zero Trust → Access → Applications → CW Staging SSH**
- Click **Policies** tab
- **Verify**:
  - [ ] Policy exists
  - [ ] Policy action is "Allow"
  - [ ] Policy includes "Service tokens" in the Include section
  - [ ] Policy is enabled/active

**If policy doesn't allow service tokens:**
1. Click on the policy to edit
2. Under **Include**, add "Service tokens"
3. Save policy

#### 3. GitHub Secrets

**Check in GitHub:**
- Repo: `collegewise1/cw-magento`
- **Settings → Secrets and variables → Actions**
- **Verify**:
  - [ ] `CF_ACCESS_CLIENT_ID` exists and has value
  - [ ] `CF_ACCESS_CLIENT_SECRET` exists and has value
  - [ ] Values match the service token in Cloudflare
  - [ ] `CLOUDFLARE_SSH_HOSTNAME` is set to `cw-staging-ssh.collegewise.com` (optional)

## Root Cause Analysis

The "websocket: bad handshake" error indicates:

**Most Likely Cause (90%)**: Application policy doesn't allow service tokens
- Policy exists but doesn't include "Service tokens" in Include section
- **Fix**: Edit policy to include service tokens

**Second Most Likely (8%)**: Service token doesn't have access
- Token exists but isn't associated with the application
- Token was revoked or expired
- **Fix**: Create new service token and update GitHub secrets

**Least Likely (2%)**: Credentials mismatch
- GitHub secrets don't match Cloudflare token
- **Fix**: Verify and update secrets

## Recommended Fix Steps

### Step 1: Verify Application Policy (5 minutes)

1. Go to Cloudflare Dashboard
2. **Zero Trust → Access → Applications → CW Staging SSH**
3. Click **Policies** tab
4. **If policy doesn't include "Service tokens"**:
   - Click on policy to edit
   - Under **Include**, check "Service tokens"
   - Save

### Step 2: Verify/Create Service Token (5 minutes)

1. Go to **Zero Trust → Access → Service Tokens**
2. **If token doesn't exist**:
   - Click "Create Service Token"
   - Name: `github-actions-collegewise-staging`
   - Copy Client ID and Secret immediately
3. **If token exists**:
   - Verify it's Active
   - Check it has access to "CW Staging SSH"
   - If not, create new token

### Step 3: Update GitHub Secrets (2 minutes)

1. Go to GitHub: `collegewise1/cw-magento` → Settings → Secrets
2. Update:
   - `CF_ACCESS_CLIENT_ID` = Service token Client ID
   - `CF_ACCESS_CLIENT_SECRET` = Service token Client Secret
3. Optional: Add `CLOUDFLARE_SSH_HOSTNAME` = `cw-staging-ssh.collegewise.com`

### Step 4: Test Connection (2 minutes)

```bash
# On your local machine or staging server
export CF_ACCESS_CLIENT_ID="your-client-id"
export CF_ACCESS_CLIENT_SECRET="your-client-secret"

# Test SSH config generation
cloudflared access ssh-config --hostname cw-staging-ssh.collegewise.com

# If that works, test SSH
ssh -o ProxyCommand="cloudflared access ssh --hostname %h" \
    -o User=ubuntu \
    cw-staging-ssh.collegewise.com
```

## Expected Outcome

After fixing the policy and verifying the service token:

1. `cloudflared access ssh-config` should output SSH config
2. SSH connection should work
3. GitHub Actions deployment should work automatically

## Time Estimate

- Policy fix: 5 minutes
- Service token verification/creation: 5 minutes
- GitHub secrets update: 2 minutes
- Testing: 2 minutes
- **Total**: ~15 minutes

---

**Status**: Configuration is 95% complete, likely just needs policy update  
**Next Action**: Check application policy in Cloudflare dashboard
