# Cloudflare Tunnel - Command Reference

## Correct Command Syntax

### Check DNS Routes

**Wrong:**
```bash
cloudflared tunnel route dns list  # ❌ Missing tunnel name
```

**Correct:**
```bash
# List routes for specific tunnel
cloudflared tunnel route dns list cw-staging

# Or check tunnel info (shows all routes)
cloudflared tunnel info cw-staging
```

### List All Tunnels

```bash
cloudflared tunnel list
```

### Check Tunnel Status

```bash
# Get detailed info about a tunnel
cloudflared tunnel info cw-staging

# Check if tunnel is running (on server)
sudo systemctl status cloudflared
```

### Add DNS Route

```bash
# Add DNS route for SSH
cloudflared tunnel route dns cw-staging staging-ssh.collegewise.com
```

### Check Config File

```bash
# View config file
sudo cat /etc/cloudflared/config.yml

# Check if SSH is configured
sudo grep -A 3 "ssh://localhost:22" /etc/cloudflared/config.yml
```

### Test SSH Connection

```bash
# Set environment variables first
export CF_ACCESS_CLIENT_ID="your-client-id"
export CF_ACCESS_CLIENT_SECRET="your-client-secret"

# Test connection
cloudflared access ssh staging-ssh.collegewise.com
```

## Common Commands for Verification

```bash
# 1. List all tunnels
cloudflared tunnel list

# 2. Check routes for your tunnel
cloudflared tunnel route dns list cw-staging

# 3. Get tunnel details
cloudflared tunnel info cw-staging

# 4. Check config file
sudo cat /etc/cloudflared/config.yml

# 5. Check service status
sudo systemctl status cloudflared

# 6. View service logs
sudo journalctl -u cloudflared -n 50
```

## Troubleshooting Commands

```bash
# Restart tunnel service
sudo systemctl restart cloudflared

# Check if tunnel is connected
cloudflared tunnel info cw-staging | grep -i connector

# Test DNS resolution
nslookup staging-ssh.collegewise.com

# Check tunnel logs
sudo journalctl -u cloudflared -f
```

---

**Last Updated**: 2026-02-06
