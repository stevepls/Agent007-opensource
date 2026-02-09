# Cloudflare Tunnel Setup for Staging Deployment

## Overview

The staging deployment workflow now routes SSH connections through Cloudflare Access (similar to apdriving), bypassing IP restrictions on the staging server.

## How It Works

1. **GitHub Actions** installs `cloudflared`
2. **Cloudflare Access SSH** authenticates using `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET`
3. **SSH connections** are routed through Cloudflare's infrastructure
4. **Staging server** only needs to allow Cloudflare IPs (much smaller list)

## Required GitHub Secrets

The following secrets must be configured in GitHub:

| Secret | Description | Example |
|--------|-------------|---------|
| `CF_ACCESS_CLIENT_ID` | Cloudflare Access Client ID | Already configured ✅ |
| `CF_ACCESS_CLIENT_SECRET` | Cloudflare Access Client Secret | Already configured ✅ |
| `CLOUDFLARE_SSH_HOSTNAME` | Cloudflare hostname for SSH access | `staging-ssh.example.com` |
| `STAGING_SSH_KEY` | SSH private key for staging server | Already configured ✅ |
| `STAGING_USER` | SSH username | `ubuntu` ✅ |
| `STAGING_PATH` | Magento path on server | `/var/www/html` ✅ |
| `STAGING_URL` | Staging site URL | Already configured ✅ |

## Cloudflare Configuration

### 1. Set Up Cloudflare Tunnel on Staging Server

SSH into the staging server and install cloudflared:

```bash
ssh ubuntu@35.84.165.174

# Install cloudflared
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb || sudo apt-get install -f -y

# Authenticate (one-time setup)
cloudflared tunnel login
```

### 2. Create Tunnel for SSH

```bash
# Create a new tunnel
cloudflared tunnel create staging-ssh

# Get tunnel ID
cloudflared tunnel list

# Configure tunnel
cloudflared tunnel route dns staging-ssh staging-ssh.example.com
```

### 3. Configure Tunnel Config File

Create `/etc/cloudflared/config.yml`:

```yaml
tunnel: <TUNNEL_ID>
credentials-file: /etc/cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: staging-ssh.example.com
    service: ssh://localhost:22
  - service: http_status:404
```

### 4. Run Tunnel as Service

```bash
# Install as systemd service
sudo cloudflared service install

# Start service
sudo systemctl start cloudflared
sudo systemctl enable cloudflared

# Check status
sudo systemctl status cloudflared
```

### 5. Configure Cloudflare Access

1. Go to **Cloudflare Dashboard → Zero Trust → Access → Applications**
2. Create new application:
   - **Application name**: `Staging SSH`
   - **Application domain**: `staging-ssh.example.com`
   - **Session duration**: `24 hours`
3. Add **Policy**:
   - **Action**: Allow
   - **Include**: Service tokens (for GitHub Actions)
4. Create **Service Token**:
   - **Token name**: `github-actions-staging`
   - Copy `Client ID` and `Client Secret`
   - Add to GitHub secrets: `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET`

## Workflow Changes

The deployment workflow now:

1. **Installs cloudflared** in the GitHub Actions runner
2. **Configures SSH** to use Cloudflare Access via `cloudflared access ssh-config`
3. **Connects via tunnel** using the `staging-tunnel` SSH host alias
4. **All SSH/rsync commands** automatically route through Cloudflare

## Benefits

- ✅ **No IP whitelisting needed** - Only Cloudflare IPs need to be allowed
- ✅ **Secure authentication** - Uses Cloudflare Access service tokens
- ✅ **Consistent with apdriving** - Same pattern you're already using
- ✅ **Automatic routing** - SSH commands work transparently

## Testing

### Test SSH Connection

```bash
# From GitHub Actions (test workflow)
ssh -F ~/.ssh/config staging-tunnel "echo 'Connection successful'"
```

### Test Deployment

1. Create a test PR
2. Merge to `staging` branch
3. Check Actions tab for deployment
4. Verify deployment completes successfully

## Troubleshooting

### SSH Connection Fails

1. **Check Cloudflare Tunnel status**:
   ```bash
   ssh ubuntu@35.84.165.174
   sudo systemctl status cloudflared
   ```

2. **Check tunnel logs**:
   ```bash
   sudo journalctl -u cloudflared -f
   ```

3. **Verify Cloudflare Access**:
   - Check service token is valid
   - Verify application policy allows the token

### Authentication Errors

- Verify `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET` are correct
- Check service token hasn't expired
- Ensure token has access to the application

### Tunnel Not Running

```bash
# Restart tunnel service
sudo systemctl restart cloudflared

# Check configuration
sudo cloudflared tunnel info staging-ssh
```

## Next Steps

1. **Set up Cloudflare Tunnel** on staging server (if not already done)
2. **Configure Cloudflare Access** application and service token
3. **Add `CLOUDFLARE_SSH_HOSTNAME` secret** to GitHub
4. **Test deployment** with a small change
5. **Verify** deployment works through Cloudflare

---

**Status**: Workflow updated to use Cloudflare Access SSH
**Date**: 2026-02-06
