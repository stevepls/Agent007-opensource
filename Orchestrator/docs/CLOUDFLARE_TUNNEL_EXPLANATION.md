# Cloudflare Tunnel - How It Works & Setup Guide

## How Cloudflare Tunnel Works

### The Problem We're Solving

**Before Cloudflare Tunnel:**
```
GitHub Actions (Dynamic IPs) → ❌ Blocked by Firewall → Staging Server (IP Restricted)
```

GitHub Actions runs on servers with **5,724+ different IP addresses** that change frequently. Your staging server has IP restrictions (firewall rules) that block these IPs.

**After Cloudflare Tunnel:**
```
GitHub Actions → ✅ Cloudflare Network → ✅ Cloudflare Tunnel → Staging Server
```

Cloudflare Tunnel creates a **persistent, encrypted connection** from your staging server to Cloudflare's network. GitHub Actions connects to Cloudflare (which has a small, stable set of IPs), and Cloudflare routes the connection through the tunnel to your server.

### Architecture Overview

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│  GitHub Actions │         │  Cloudflare      │         │  Staging Server │
│  (Dynamic IPs)  │────────▶│  Network         │────────▶│  (IP Restricted)│
│                 │         │  (Stable IPs)    │         │                 │
└─────────────────┘         └──────────────────┘         └─────────────────┘
                                      │
                                      │
                            ┌─────────▼─────────┐
                            │  Cloudflare Tunnel │
                            │  (cloudflared)    │
                            │  Running on Server│
                            └───────────────────┘
```

### Components

1. **cloudflared** (Cloudflare Tunnel daemon)
   - Runs on your staging server
   - Creates outbound connection to Cloudflare (no inbound firewall rules needed!)
   - Routes traffic from Cloudflare to local services (SSH, HTTP, etc.)

2. **Cloudflare Access**
   - Authentication layer on top of the tunnel
   - Uses service tokens for automated access (GitHub Actions)
   - Controls who can access what through the tunnel

3. **GitHub Actions Workflow**
   - Installs `cloudflared` client
   - Authenticates using service token (CF_ACCESS_CLIENT_ID/SECRET)
   - Connects via Cloudflare hostname instead of direct IP

### Why This Works

1. **Outbound Connection**: The tunnel is initiated FROM your server TO Cloudflare
   - No inbound firewall rules needed
   - Works through NAT/firewalls automatically
   - Server "calls out" to Cloudflare, not the other way around

2. **IP Whitelisting**: Only Cloudflare's IPs need to be allowed
   - Cloudflare has ~20 IP ranges (vs GitHub's 5,724+)
   - These IPs are stable and well-documented
   - Much easier to manage

3. **Authentication**: Cloudflare Access adds security
   - Service tokens for automated access
   - No need to expose SSH keys publicly
   - Centralized access control

## Setup Checklist

### ✅ Already Completed

- [x] GitHub Actions workflow updated to use Cloudflare Tunnel
- [x] Workflow installs `cloudflared` automatically
- [x] Workflow configures Cloudflare Access SSH
- [x] GitHub secrets configured:
  - [x] `CF_ACCESS_CLIENT_ID` (already exists)
  - [x] `CF_ACCESS_CLIENT_SECRET` (already exists)
  - [x] `STAGING_SSH_KEY`
  - [x] `STAGING_USER`
  - [x] `STAGING_PATH`
  - [x] `STAGING_URL`
- [x] Reusable template created in DevOps folder

### ❌ Still Needed (On Staging Server)

#### Step 1: Install cloudflared on Staging Server

```bash
# SSH into staging server
ssh ubuntu@35.84.165.174

# Download and install cloudflared
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb || sudo apt-get install -f -y

# Verify installation
cloudflared --version
```

**Time Estimate**: 5 minutes

#### Step 2: Authenticate with Cloudflare

```bash
# This opens a browser to authenticate with your Cloudflare account
cloudflared tunnel login
```

**What this does:**
- Opens browser to Cloudflare dashboard
- You log in and authorize the tunnel
- Creates credentials file: `~/.cloudflared/cert.pem`

**Time Estimate**: 2 minutes

#### Step 3: Create Tunnel

```bash
# Create a new tunnel (name it something like "staging-ssh")
cloudflared tunnel create staging-ssh

# List tunnels to see the ID
cloudflared tunnel list
```

**Output will show:**
```
ID                                   NAME         CREATED
xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx staging-ssh  2026-02-06T12:00:00Z
```

**Save the tunnel ID** - you'll need it for the config file.

**Time Estimate**: 2 minutes

#### Step 4: Configure DNS Route

```bash
# Route DNS to the tunnel
# Replace with your actual hostname (e.g., staging-ssh.collegewise.com)
cloudflared tunnel route dns staging-ssh staging-ssh.collegewise.com
```

**This creates a DNS record** pointing to your tunnel.

**Time Estimate**: 1 minute

#### Step 5: Create Tunnel Configuration

Create config file: `/etc/cloudflared/config.yml`

```bash
sudo mkdir -p /etc/cloudflared
sudo nano /etc/cloudflared/config.yml
```

**Config file content:**
```yaml
tunnel: <YOUR_TUNNEL_ID>
credentials-file: /root/.cloudflared/<TUNNEL_ID>.json

ingress:
  # SSH service
  - hostname: staging-ssh.collegewise.com
    service: ssh://localhost:22
  # Catch-all (must be last)
  - service: http_status:404
```

**Important:**
- Replace `<YOUR_TUNNEL_ID>` with the actual tunnel ID from Step 3
- Replace `staging-ssh.collegewise.com` with your chosen hostname
- The credentials file path should match where `cloudflared tunnel login` saved it

**Time Estimate**: 5 minutes

#### Step 6: Install Tunnel as System Service

```bash
# Install as systemd service
sudo cloudflared service install

# Start the service
sudo systemctl start cloudflared
sudo systemctl enable cloudflared

# Check status
sudo systemctl status cloudflared

# View logs
sudo journalctl -u cloudflared -f
```

**Time Estimate**: 3 minutes

#### Step 7: Configure Cloudflare Access (Zero Trust)

1. **Go to Cloudflare Dashboard**
   - Navigate to: **Zero Trust → Access → Applications**
   - Click **Add an application**

2. **Create Application**
   - **Application name**: `Collegewise Staging SSH`
   - **Application domain**: `staging-ssh.collegewise.com` (same as DNS in Step 4)
   - **Session duration**: `24 hours`
   - Click **Next**

3. **Add Policy**
   - **Policy name**: `Allow Service Token`
   - **Action**: `Allow`
   - **Include**: 
     - Select **Service tokens**
   - Click **Next**

4. **Create Service Token**
   - Go to **Access → Service Tokens**
   - Click **Create Service Token**
   - **Token name**: `github-actions-collegewise-staging`
   - **Client ID**: Copy this value
   - **Client Secret**: Copy this value (only shown once!)
   - Click **Create**

5. **Add Service Token to GitHub Secrets**
   - Go to GitHub repo: `collegewise1/cw-magento`
   - **Settings → Secrets and variables → Actions**
   - Update secrets:
     - `CF_ACCESS_CLIENT_ID` = Client ID from step 4
     - `CF_ACCESS_CLIENT_SECRET` = Client Secret from step 4
   - Add new secret (if not exists):
     - `CLOUDFLARE_SSH_HOSTNAME` = `staging-ssh.collegewise.com`

**Time Estimate**: 10 minutes

#### Step 8: Test the Connection

```bash
# From your local machine (or GitHub Actions test)
# Install cloudflared locally first
brew install cloudflared  # macOS
# or
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb  # Linux

# Set environment variables
export CF_ACCESS_CLIENT_ID="your-client-id"
export CF_ACCESS_CLIENT_SECRET="your-client-secret"

# Test SSH connection
cloudflared access ssh staging-ssh.collegewise.com
```

**Time Estimate**: 5 minutes

## Total Setup Time Estimate

| Step | Task | Time |
|------|------|------|
| 1 | Install cloudflared | 5 min |
| 2 | Authenticate | 2 min |
| 3 | Create tunnel | 2 min |
| 4 | Configure DNS | 1 min |
| 5 | Create config file | 5 min |
| 6 | Install service | 3 min |
| 7 | Configure Access | 10 min |
| 8 | Test connection | 5 min |
| **Total** | | **33 minutes** |

## Verification Checklist

After setup, verify:

- [ ] `cloudflared` is installed and running
- [ ] Tunnel service is active: `sudo systemctl status cloudflared`
- [ ] DNS resolves: `nslookup staging-ssh.collegewise.com`
- [ ] Cloudflare Access application is created
- [ ] Service token is created and added to GitHub secrets
- [ ] Test SSH connection works
- [ ] GitHub Actions workflow can connect

## Troubleshooting

### Tunnel Not Starting

```bash
# Check logs
sudo journalctl -u cloudflared -n 50

# Common issues:
# - Wrong tunnel ID in config
# - Credentials file not found
# - DNS not configured
```

### Can't Connect via SSH

```bash
# Verify tunnel is running
sudo systemctl status cloudflared

# Check DNS resolution
nslookup staging-ssh.collegewise.com

# Test with cloudflared directly
cloudflared access ssh staging-ssh.collegewise.com
```

### Authentication Errors

- Verify service token is correct in GitHub secrets
- Check Cloudflare Access application policy allows service tokens
- Ensure token hasn't expired

## Next Steps After Setup

1. **Test deployment** - Merge a small PR to staging
2. **Monitor logs** - Watch GitHub Actions and cloudflared logs
3. **Document hostname** - Save the Cloudflare SSH hostname for future reference
4. **Set up production** - Repeat for production environment if needed

## Key Benefits

✅ **No IP whitelisting** - Only Cloudflare IPs need to be allowed  
✅ **Secure** - Encrypted tunnel + Access authentication  
✅ **Reliable** - Persistent connection, auto-reconnects  
✅ **Scalable** - Same pattern works for all projects  
✅ **Maintainable** - Centralized access control via Cloudflare dashboard

---

**Status**: Workflow ready, server setup pending  
**Estimated Remaining Time**: 33 minutes  
**Last Updated**: 2026-02-06
