# Cloudflare Access SSH Troubleshooting

## Error: "websocket: bad handshake" / "Connection closed by remote host"

This error typically indicates:
1. Service token authentication failure
2. Service token doesn't have access to the application
3. Application policy doesn't allow service tokens
4. Credentials not being passed correctly

## Step-by-Step Troubleshooting

### 1. Verify Service Token Credentials

```bash
# Check if credentials are set
echo $CF_ACCESS_CLIENT_ID
echo $CF_ACCESS_CLIENT_SECRET

# If empty, export them:
export CF_ACCESS_CLIENT_ID="your-client-id"
export CF_ACCESS_CLIENT_SECRET="your-client-secret"
```

### 2. Verify Service Token Has Access

**In Cloudflare Dashboard:**
1. Go to: **Zero Trust → Access → Applications → CW Staging SSH**
2. Click on the application
3. Go to **Policies** tab
4. **Check**: Does the policy include "Service tokens"?
   - If not: Edit policy → Add "Service tokens" to Include
   - Save policy

### 3. Verify Service Token is Active

**In Cloudflare Dashboard:**
1. Go to: **Zero Trust → Access → Service Tokens**
2. Find your token
3. Check:
   - Status (should be Active)
   - Last used date
   - Associated applications

### 4. Test with Verbose Logging

```bash
# Enable debug logging
export CLOUDFLARED_LOG_LEVEL=debug

# Try connection with verbose output
ssh -v -o ProxyCommand="cloudflared access ssh --hostname %h" \
    -o User=ubuntu \
    cw-staging-ssh.collegewise.com
```

### 5. Test SSH Config Generation

```bash
# This should work if credentials are correct
export CF_ACCESS_CLIENT_ID="your-client-id"
export CF_ACCESS_CLIENT_SECRET="your-client-secret"

cloudflared access ssh-config --hostname cw-staging-ssh.collegewise.com
```

**If this fails**: Credentials are wrong or token doesn't have access  
**If this works**: The SSH config should be generated correctly

### 6. Check Tunnel Status

```bash
# On staging server
sudo systemctl status cloudflared
sudo journalctl -u cloudflared -n 50
```

Look for errors or connection issues.

### 7. Verify Application Domain Matches

**Check:**
- Application domain in Cloudflare: `cw-staging-ssh.collegewise.com`
- DNS route: `cw-staging-ssh.collegewise.com`
- Config file hostname: `cw-staging-ssh.collegewise.com`

All three must match exactly.

## Common Fixes

### Fix 1: Update Application Policy

1. Go to: **Zero Trust → Access → Applications → CW Staging SSH**
2. Click **Policies** tab
3. Edit the policy
4. Under **Include**, make sure "Service tokens" is selected
5. Save

### Fix 2: Create New Service Token

If the token might be invalid:

1. Go to: **Zero Trust → Access → Service Tokens**
2. Create new token:
   - Name: `github-actions-collegewise-staging-v2`
   - Copy Client ID and Secret
3. Update GitHub secrets with new credentials
4. Test again

### Fix 3: Verify Tunnel Config

On staging server, check config file:

```bash
sudo cat /etc/cloudflared/config.yml
```

Should have:
```yaml
ingress:
  - hostname: cw-staging-ssh.collegewise.com
    service: ssh://localhost:22
```

### Fix 4: Restart Tunnel Service

```bash
sudo systemctl restart cloudflared
sudo systemctl status cloudflared
```

## Testing Checklist

- [ ] Service token credentials exported
- [ ] Service token exists in Cloudflare
- [ ] Application policy allows service tokens
- [ ] Application domain matches DNS route
- [ ] Config file has correct SSH ingress
- [ ] Tunnel service is running
- [ ] DNS resolves correctly: `nslookup cw-staging-ssh.collegewise.com`

---

**Last Updated**: 2026-02-06
