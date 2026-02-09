# Testing Cloudflare Access SSH Connection

## Method 1: Using Environment Variables (Recommended)

```bash
# Set environment variables
export CF_ACCESS_CLIENT_ID="your-client-id"
export CF_ACCESS_CLIENT_SECRET="your-client-secret"

# Test SSH connection
cloudflared access ssh cw-staging-ssh.collegewise.com
```

## Method 2: Using Service Token Flags

```bash
cloudflared access ssh \
  --hostname cw-staging-ssh.collegewise.com \
  --service-token-id "your-client-id" \
  --service-token-secret "your-client-secret"
```

## Method 3: Using SSH Config (Best for GitHub Actions)

First, generate SSH config:

```bash
# Set environment variables
export CF_ACCESS_CLIENT_ID="your-client-id"
export CF_ACCESS_CLIENT_SECRET="your-client-secret"

# Generate SSH config
cloudflared access ssh-config --hostname cw-staging-ssh.collegewise.com

# This will output SSH config that you can add to ~/.ssh/config
# Then use regular SSH:
ssh cw-staging-ssh.collegewise.com
```

## Method 4: Direct SSH with ProxyCommand

Add to `~/.ssh/config`:

```
Host cw-staging-ssh
  HostName cw-staging-ssh.collegewise.com
  User ubuntu
  ProxyCommand cloudflared access ssh --hostname %h
```

Then test:
```bash
ssh cw-staging-ssh
```

## Getting Service Token Credentials

If you don't have the credentials:

1. Go to: **Zero Trust → Access → Service Tokens**
2. Find or create token for `cw-staging-ssh.collegewise.com`
3. Copy **Client ID** and **Client Secret**
4. Use them in the commands above

**Note**: If you created the token before, you can see the Client ID but not the secret (it's only shown once). You'll need to create a new token if you don't have the secret.

---

**Last Updated**: 2026-02-06
