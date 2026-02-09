# Fixing "websocket: bad handshake" Error

## The Problem

The SSH config is correct, but `cloudflared` needs credentials to authenticate. When you run `ssh cw-staging-ssh.collegewise.com`, the ProxyCommand runs `cloudflared access ssh`, but cloudflared doesn't have the credentials.

## The Solution

You need to set the environment variables **before** running SSH.

### Step 1: Get Credentials from GitHub Secrets

**In GitHub:**
1. Go to: `collegewise1/cw-magento` → Settings → Secrets
2. Copy `CF_ACCESS_CLIENT_ID`
3. Copy `CF_ACCESS_CLIENT_SECRET`

### Step 2: Set Environment Variables

```bash
# Set credentials in your current shell
export CF_ACCESS_CLIENT_ID="paste-client-id-here"
export CF_ACCESS_CLIENT_SECRET="paste-client-secret-here"

# Verify they're set
echo $CF_ACCESS_CLIENT_ID
echo $CF_ACCESS_CLIENT_SECRET
```

### Step 3: Test SSH Config Generation First

```bash
# This will tell you if credentials work
cloudflared access ssh-config --hostname cw-staging-ssh.collegewise.com
```

**If this works**: Credentials are correct, proceed to SSH  
**If this fails**: Credentials are wrong, need to update them

### Step 4: Test SSH Connection

```bash
# Now SSH should work
ssh cw-staging-ssh.collegewise.com
```

## Alternative: Add Credentials to SSH Config (Advanced)

You can add credentials to SSH config, but it's less secure:

```bash
# Add to ~/.ssh/config
Host cw-staging-ssh.collegewise.com
  ProxyCommand /usr/bin/cloudflared access ssh --hostname %h
  User ubuntu
  SetEnv CF_ACCESS_CLIENT_ID=your-client-id
  SetEnv CF_ACCESS_CLIENT_SECRET=your-client-secret
```

**Note**: This stores credentials in plain text, not recommended for production.

## Better Solution: Use a Wrapper Script

Create a script that sets credentials and runs SSH:

```bash
# Create ~/ssh-staging.sh
cat > ~/ssh-staging.sh << 'SCRIPT'
#!/bin/bash
export CF_ACCESS_CLIENT_ID="your-client-id"
export CF_ACCESS_CLIENT_SECRET="your-client-secret"
ssh cw-staging-ssh.collegewise.com "$@"
SCRIPT

chmod +x ~/ssh-staging.sh

# Use it
~/ssh-staging.sh
```

## For GitHub Actions

GitHub Actions automatically sets these environment variables from secrets, so it works there. The workflow does:

```yaml
env:
  CF_ACCESS_CLIENT_ID: ${{ secrets.CF_ACCESS_CLIENT_ID }}
  CF_ACCESS_CLIENT_SECRET: ${{ secrets.CF_ACCESS_CLIENT_SECRET }}
```

## Quick Test

```bash
# 1. Get credentials from GitHub secrets
# 2. Set them:
export CF_ACCESS_CLIENT_ID="<from-github>"
export CF_ACCESS_CLIENT_SECRET="<from-github>"

# 3. Test config generation
cloudflared access ssh-config --hostname cw-staging-ssh.collegewise.com

# 4. If that works, test SSH
ssh cw-staging-ssh.collegewise.com
```

## Summary

**The error happens because**: cloudflared doesn't have credentials  
**The fix**: Set `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET` before running SSH  
**Get credentials from**: GitHub secrets (`collegewise1/cw-magento` → Settings → Secrets)

---

**Set the environment variables first, then try SSH again!**
