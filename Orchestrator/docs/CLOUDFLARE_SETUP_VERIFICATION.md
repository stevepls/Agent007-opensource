# Cloudflare Tunnel Setup - Verification Checklist

## Quick Verification Steps

### 1. Check Tunnel Status (Cloudflare Dashboard)

✅ **Already Verified:**
- Tunnel exists: `cw-staging`
- Status: HEALTHY
- Tunnel ID: `5c9f3b89-51e4-4fa1-9aac-e83b89998947`

**Next Check:**
- Go to: **Zero Trust → Networks → Tunnels → cw-staging**
- Click on the tunnel name
- Check **Public Hostnames** tab
- **Look for**: `staging-ssh.collegewise.com` or similar SSH hostname

**If you see a hostname**: DNS route is configured ✅  
**If empty**: Need to add DNS route ❌

---

### 2. Check DNS Route (Command Line)

**On staging server**, run:

```bash
ssh ubuntu@35.84.165.174

# Check if DNS route exists
cloudflared tunnel route dns list

# Or check specific tunnel
cloudflared tunnel route dns list cw-staging
```

**Expected output if configured:**
```
staging-ssh.collegewise.com -> cw-staging
```

**If empty**: Need to add DNS route ❌

---

### 3. Check Config File (On Server)

**On staging server**, run:

```bash
# Check if config file exists
sudo cat /etc/cloudflared/config.yml

# Or check if it has SSH configuration
sudo grep -A 5 "ssh://localhost:22" /etc/cloudflared/config.yml
```

**What to look for:**
- File exists ✅
- Contains tunnel ID: `5c9f3b89-51e4-4fa1-9aac-e83b89998947` ✅
- Has SSH ingress rule for `staging-ssh.collegewise.com` ✅

**If file doesn't exist or missing SSH config**: Need to create/update ❌

---

### 4. Check Cloudflare Access Application

**In Cloudflare Dashboard:**
- Go to: **Zero Trust → Access → Applications**
- **Look for**: Application with domain like `staging-ssh.collegewise.com` or `cw-staging-ssh`

**If application exists**: ✅  
**If not**: Need to create ❌

**Check application details:**
- Click on application
- Check **Policies** tab
- **Look for**: Policy that allows "Service tokens"

---

### 5. Check Service Token

**In Cloudflare Dashboard:**
- Go to: **Zero Trust → Access → Service Tokens**
- **Look for**: Token named something like:
  - `github-actions-collegewise-staging`
  - `github-actions-cw-staging`
  - `collegewise-staging-ssh`

**If token exists**: ✅  
**If not**: Need to create ❌

**Note**: You can see Client ID but not the secret (only shown once at creation)

---

### 6. Check GitHub Secrets

**In GitHub:**
- Go to: `collegewise1/cw-magento` repo
- **Settings → Secrets and variables → Actions**
- **Check for**:
  - ✅ `CF_ACCESS_CLIENT_ID` (should have value)
  - ✅ `CF_ACCESS_CLIENT_SECRET` (should have value)
  - ❓ `CLOUDFLARE_SSH_HOSTNAME` (may or may not exist)

**If secrets exist**: ✅  
**If missing**: Need to add ❌

---

### 7. Test SSH Connection

**From your local machine or GitHub Actions test:**

```bash
# Set environment variables
export CF_ACCESS_CLIENT_ID="your-client-id"
export CF_ACCESS_CLIENT_SECRET="your-client-secret"

# Test connection
cloudflared access ssh staging-ssh.collegewise.com
```

**If connection works**: ✅ Setup is complete!  
**If fails**: Check error message and troubleshoot

---

## Quick Verification Script

**Run on staging server:**

```bash
#!/bin/bash
echo "=== Cloudflare Tunnel Verification ==="
echo ""

echo "1. Tunnel Status:"
cloudflared tunnel list
echo ""

echo "2. DNS Routes:"
cloudflared tunnel route dns list
echo ""

echo "3. Config File:"
if [ -f /etc/cloudflared/config.yml ]; then
    echo "✅ Config file exists"
    echo "Contents:"
    sudo cat /etc/cloudflared/config.yml
else
    echo "❌ Config file missing"
fi
echo ""

echo "4. Cloudflared Service:"
sudo systemctl status cloudflared --no-pager | head -5
echo ""

echo "5. Check for SSH ingress:"
if sudo grep -q "ssh://localhost:22" /etc/cloudflared/config.yml 2>/dev/null; then
    echo "✅ SSH ingress configured"
else
    echo "❌ SSH ingress missing"
fi
```

---

## What's Already Done ✅

Based on dashboard screenshot:
- ✅ Tunnel created: `cw-staging`
- ✅ Tunnel is HEALTHY and running
- ✅ Certificate exists (tunnel is authenticated)

## What Might Be Missing ❓

Need to verify:
- ❓ DNS route for SSH hostname
- ❓ Config file with SSH ingress
- ❓ Cloudflare Access application
- ❓ Service token
- ❓ GitHub secrets configured

---

## Next Steps Based on Verification

### If Everything is Configured:
- Test SSH connection
- Test GitHub Actions deployment
- Done! ✅

### If DNS Route Missing:
- Run: `cloudflared tunnel route dns cw-staging staging-ssh.collegewise.com`

### If Config File Missing:
- Create `/etc/cloudflared/config.yml` with tunnel ID and SSH ingress

### If Access Application Missing:
- Create application in Cloudflare dashboard
- Create service token
- Add to GitHub secrets

---

**Run the verification steps above to see what's already done!**
