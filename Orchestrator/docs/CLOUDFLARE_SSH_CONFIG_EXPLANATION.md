# Cloudflare SSH Config Explanation

## What This Means

```ssh-config
Host cw-staging-ssh.collegewise.com
  ProxyCommand /usr/bin/cloudflared access ssh --hostname %h
```

### Breaking It Down

**`Host cw-staging-ssh.collegewise.com`**
- This is an SSH alias/configuration block
- When you type `ssh cw-staging-ssh.collegewise.com`, SSH uses this configuration
- You can also use a shorter alias like `Host staging` if you prefer

**`ProxyCommand /usr/bin/cloudflared access ssh --hostname %h`**
- This tells SSH: "Don't connect directly, use this command as a proxy"
- `/usr/bin/cloudflared` - The cloudflared binary location
- `access ssh` - Use Cloudflare Access for SSH
- `--hostname %h` - `%h` is replaced with the hostname (`cw-staging-ssh.collegewise.com`)
- So it becomes: `cloudflared access ssh --hostname cw-staging-ssh.collegewise.com`

## How It Works

### Normal SSH (Direct Connection)
```
Your Computer → Direct SSH → Staging Server (Blocked by firewall)
```

### With Cloudflare Tunnel (This Config)
```
Your Computer → SSH → cloudflared → Cloudflare Network → Tunnel → Staging Server
```

When you run `ssh cw-staging-ssh.collegewise.com`:
1. SSH reads the config file
2. Sees the ProxyCommand
3. Runs `cloudflared access ssh --hostname cw-staging-ssh.collegewise.com`
4. cloudflared authenticates with Cloudflare Access (using your service token)
5. Cloudflare routes the connection through the tunnel
6. Connection reaches your staging server

## How to Use It

### Option 1: Add to SSH Config (Recommended)

```bash
# Add the config to your SSH config file
cat >> ~/.ssh/config << 'EOF'
Host cw-staging-ssh.collegewise.com
  ProxyCommand /usr/bin/cloudflared access ssh --hostname %h
  User ubuntu
  StrictHostKeyChecking no
EOF

# Then use regular SSH
ssh cw-staging-ssh.collegewise.com
```

### Option 2: Use Shorter Alias

```bash
# Add to ~/.ssh/config
cat >> ~/.ssh/config << 'EOF'
Host staging
  HostName cw-staging-ssh.collegewise.com
  ProxyCommand /usr/bin/cloudflared access ssh --hostname %h
  User ubuntu
  StrictHostKeyChecking no
EOF

# Then use shorter command
ssh staging
```

### Option 3: Use Directly (One-liner)

```bash
# Don't need to add to config, use directly
ssh -o ProxyCommand="cloudflared access ssh --hostname %h" \
    -o User=ubuntu \
    cw-staging-ssh.collegewise.com
```

## Important: Environment Variables

**Before using SSH, you need credentials:**

```bash
# Set these first
export CF_ACCESS_CLIENT_ID="your-client-id"
export CF_ACCESS_CLIENT_SECRET="your-client-secret"

# Then SSH will work
ssh cw-staging-ssh.collegewise.com
```

## What GitHub Actions Does

The GitHub Actions workflow does this automatically:

1. Sets environment variables from secrets
2. Runs `cloudflared access ssh-config --hostname cw-staging-ssh.collegewise.com`
3. Adds the output to `~/.ssh/config`
4. Uses regular SSH commands (rsync, ssh) which automatically use the ProxyCommand

## Example Usage

```bash
# 1. Set credentials
export CF_ACCESS_CLIENT_ID="abc123..."
export CF_ACCESS_CLIENT_SECRET="xyz789..."

# 2. Add to SSH config (one time)
echo 'Host cw-staging-ssh.collegewise.com
  ProxyCommand /usr/bin/cloudflared access ssh --hostname %h
  User ubuntu' >> ~/.ssh/config

# 3. Use regular SSH commands
ssh cw-staging-ssh.collegewise.com
rsync -e ssh file.txt cw-staging-ssh.collegewise.com:/path/
```

## Why This Works

- **No direct connection**: You're not connecting directly to the server IP
- **Through Cloudflare**: Connection goes through Cloudflare's network
- **Authenticated**: cloudflared uses your service token for authentication
- **Tunneled**: Cloudflare routes through the tunnel to your server
- **Bypasses firewall**: Since it's outbound from server, no inbound rules needed

## Summary

This SSH config tells SSH to use Cloudflare as a proxy instead of connecting directly. It's like saying "when I try to SSH to this hostname, don't go there directly - use cloudflared to route through Cloudflare first."

---

**This is exactly what your GitHub Actions workflow uses automatically!**
