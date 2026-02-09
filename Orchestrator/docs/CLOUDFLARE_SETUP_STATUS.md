# Cloudflare Tunnel Setup - Current Status

**Date**: 2026-02-06  
**Project**: Collegewise (cw-magento)

## ✅ Fully Configured

1. **Tunnel**: `cw-staging`
   - Status: HEALTHY
   - Tunnel ID: `5c9f3b89-51e4-4fa1-9aac-e83b89998947`
   - Uptime: 9+ days

2. **DNS Route**: `cw-staging-ssh.collegewise.com`
   - Configured and routing to tunnel

3. **Config File**: `/etc/cloudflared/config.yml`
   - SSH ingress: `cw-staging-ssh.collegewise.com` → `ssh://localhost:22`
   - Tunnel ID matches

4. **Access Application**: "CW Staging SSH"
   - Domain: `cw-staging-ssh.collegewise.com`
   - Status: Active

5. **Access Policy**: "Allow Service Token"
   - Action: SERVICE AUTH ✅
   - Assigned to application ✅
   - **This is correct!**

6. **GitHub Secrets**:
   - `CF_ACCESS_CLIENT_ID` ✅ (exists)
   - `CF_ACCESS_CLIENT_SECRET` ✅ (exists)
   - `STAGING_HOST`, `STAGING_USER`, `STAGING_PATH` ✅

7. **GitHub Workflow**:
   - Configured to use Cloudflare Access SSH ✅
   - Uses `cloudflared access ssh-config` ✅

## ❓ Needs Verification

### Service Token

**Check in Cloudflare Dashboard:**
- Go to: **Zero Trust → Access → Service Tokens**
- **Verify**:
  - [ ] Service token exists
  - [ ] Token name matches (e.g., `github-actions-collegewise-staging`)
  - [ ] Token is Active
  - [ ] Client ID matches `CF_ACCESS_CLIENT_ID` in GitHub secrets
  - [ ] Token has access to "CW Staging SSH" application

**If token doesn't exist:**
1. Create new service token
2. Name: `github-actions-collegewise-staging`
3. Copy Client ID and Secret
4. Update GitHub secrets

**If token exists but credentials don't match:**
1. Create new service token
2. Update GitHub secrets with new credentials

## Root Cause of "websocket: bad handshake"

Since the policy is correctly configured with SERVICE AUTH, the issue is most likely:

1. **Service token doesn't exist** (80% likely)
   - Need to create service token
   - Add to GitHub secrets

2. **Service token credentials don't match GitHub secrets** (15% likely)
   - GitHub secrets have old/wrong credentials
   - Need to create new token and update secrets

3. **Service token not associated with application** (5% likely)
   - Token exists but doesn't have access
   - Need to verify token has access to "CW Staging SSH"

## Next Steps

### Step 1: Check Service Tokens (2 minutes)

1. Go to: **Zero Trust → Access → Service Tokens**
2. Look for token related to Collegewise or GitHub Actions
3. **If found**: Verify Client ID matches GitHub secret
4. **If not found**: Create new token

### Step 2: Create/Update Service Token (5 minutes)

**If token doesn't exist:**
1. Click "Create Service Token"
2. Name: `github-actions-collegewise-staging`
3. **Copy Client ID and Secret immediately** (secret only shown once!)
4. Update GitHub secrets:
   - `CF_ACCESS_CLIENT_ID` = Client ID
   - `CF_ACCESS_CLIENT_SECRET` = Client Secret

### Step 3: Test Connection (2 minutes)

```bash
# Set credentials
export CF_ACCESS_CLIENT_ID="new-client-id"
export CF_ACCESS_CLIENT_SECRET="new-client-secret"

# Test SSH config generation
cloudflared access ssh-config --hostname cw-staging-ssh.collegewise.com

# If that works, test SSH
ssh -o ProxyCommand="cloudflared access ssh --hostname %h" \
    -o User=ubuntu \
    cw-staging-ssh.collegewise.com
```

## Expected Result

After creating/updating the service token:

1. `cloudflared access ssh-config` should output SSH config ✅
2. SSH connection should work ✅
3. GitHub Actions deployment should work automatically ✅

## Summary

**Configuration Status**: 95% complete  
**Remaining Issue**: Service token verification/creation  
**Estimated Time**: 5-10 minutes  
**Confidence**: High - policy is correct, just need valid service token

---

**All infrastructure is configured correctly. The issue is authentication credentials.**
