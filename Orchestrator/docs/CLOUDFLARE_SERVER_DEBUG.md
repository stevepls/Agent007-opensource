# Cloudflare Tunnel - Server-Side Debugging

## Issue: "websocket: bad handshake" on SSH Connection

Even though SSH config generation works, the actual SSH connection fails. This suggests the tunnel might not be routing SSH correctly, or there's a loopback issue.

## Debug Commands (Run on Staging Server)

### 1. Check SSH Service

```bash
# Check if SSH is running
sudo systemctl status ssh

# Check if SSH is listening on port 22
sudo netstat -tlnp | grep :22
# or
sudo ss -tlnp | grep :22
```

**Expected**: SSH should be running and listening on `0.0.0.0:22` or `127.0.0.1:22`

### 2. Check Cloudflared Tunnel

```bash
# Check tunnel service status
sudo systemctl status cloudflared

# Check tunnel logs for errors
sudo journalctl -u cloudflared -n 100 --no-pager

# Check tunnel info
cloudflared tunnel info cw-staging
```

**Look for**:
- Tunnel is running
- Connectors are active
- No errors in logs

### 3. Verify Config File

```bash
# Check config file
sudo cat /etc/cloudflared/config.yml
```

**Should have**:
```yaml
ingress:
  - hostname: cw-staging-ssh.collegewise.com
    service: ssh://localhost:22
```

### 4. Test Local SSH (Without Tunnel)

```bash
# Test if SSH works locally
ssh localhost
# or
ssh 127.0.0.1
```

**If this works**: SSH service is fine, issue is with tunnel routing  
**If this fails**: SSH service has issues

### 5. Test Tunnel Connection

```bash
# Check if tunnel can reach localhost:22
cloudflared tunnel info cw-staging

# Check tunnel routes
cloudflared tunnel route dns list cw-staging
```

### 6. Check DNS

```bash
# Verify DNS resolves
nslookup cw-staging-ssh.collegewise.com
dig cw-staging-ssh.collegewise.com
```

### 7. Test with Verbose Logging

```bash
# Enable debug logging
export CLOUDFLARED_LOG_LEVEL=debug

# Try SSH with verbose output
ssh -v cw-staging-ssh.collegewise.com
```

## Common Issues and Fixes

### Issue 1: SSH Not Listening on localhost

**Check**:
```bash
sudo ss -tlnp | grep :22
```

**If SSH is only listening on external IP, not localhost**:
- Edit `/etc/ssh/sshd_config`
- Add: `ListenAddress 127.0.0.1` or `ListenAddress 0.0.0.0`
- Restart: `sudo systemctl restart ssh`

### Issue 2: Tunnel Not Routing to localhost:22

**Check config file**:
```bash
sudo cat /etc/cloudflared/config.yml
```

**Should have**:
```yaml
ingress:
  - hostname: cw-staging-ssh.collegewise.com
    service: ssh://localhost:22  # or ssh://127.0.0.1:22
```

**If wrong, fix and restart**:
```bash
sudo systemctl restart cloudflared
```

### Issue 3: Loopback Connection Issue

**Since you're on the server itself**, SSHing to itself through the tunnel might cause issues.

**Test from different machine**:
- Try from your local machine
- Or from GitHub Actions (which will work differently)

### Issue 4: Cloudflared Can't Reach localhost:22

**Check**:
```bash
# Test if cloudflared can reach SSH
curl -v telnet://localhost:22
# or
nc -zv localhost 22
```

**If fails**: SSH might not be listening on localhost

## Quick Fixes

### Fix 1: Restart Services

```bash
sudo systemctl restart ssh
sudo systemctl restart cloudflared
sudo systemctl status cloudflared
```

### Fix 2: Verify Config and Restart

```bash
# Check config
sudo cat /etc/cloudflared/config.yml

# If config looks wrong, fix it
sudo nano /etc/cloudflared/config.yml

# Restart
sudo systemctl restart cloudflared
sudo journalctl -u cloudflared -f
```

### Fix 3: Test from External Machine

The loopback (SSHing to itself) might be the issue. Test from:
- Your local machine
- Or wait for GitHub Actions (which will work)

## Expected Behavior

**From staging server itself**:
- Loopback through tunnel might have issues
- This is actually expected behavior
- **GitHub Actions will work fine** (different connection path)

**From external machine**:
- Should work if everything is configured correctly

## Next Steps

1. Run all debug commands above
2. Check SSH service status
3. Check cloudflared logs
4. Verify config file
5. Test local SSH (without tunnel)

**Most likely**: SSH service is fine, but loopback through tunnel has issues. GitHub Actions will work because it's coming from outside.

---

**Run the debug commands and share the output!**
