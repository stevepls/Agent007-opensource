# Cloudflare Dashboard - Where to Check Everything

## Quick Navigation Guide

### 1. Check Existing Tunnels

**Path**: `Zero Trust → Networks → Tunnels`

**Steps**:
1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Click **Zero Trust** (or **Access** in older accounts)
3. In left sidebar: **Networks → Tunnels**
4. You'll see a list of all tunnels

**What to look for**:
- Tunnel name (e.g., "staging-ssh", "apdriving-ssh")
- Tunnel ID (UUID format)
- Status (Active/Inactive)
- Created date
- Connectors (shows if tunnel is running)

**If you see tunnels listed**: The certificate is valid and you can use existing tunnels or create new ones.

---

### 2. Check DNS Routes

**Path**: `Zero Trust → Networks → Tunnels → [Select Tunnel] → Public Hostnames`

**Steps**:
1. Go to **Zero Trust → Networks → Tunnels**
2. Click on a tunnel name
3. Click **Public Hostnames** tab
4. See all DNS routes for that tunnel

**What to look for**:
- Hostname (e.g., `staging-ssh.collegewise.com`)
- Service (e.g., `ssh://localhost:22`)
- Status

**Alternative**: Check DNS in main dashboard
- **Path**: `Websites → [Your Domain] → DNS`
- Look for CNAME records pointing to tunnel hostnames

---

### 3. Check Cloudflare Access Applications

**Path**: `Zero Trust → Access → Applications`

**Steps**:
1. Go to **Zero Trust → Access → Applications**
2. See list of all Access applications

**What to look for**:
- Application name (e.g., "Collegewise Staging SSH")
- Application domain (e.g., `staging-ssh.collegewise.com`)
- Status (Active/Inactive)
- Policies (who can access)

**To view details**:
- Click on application name
- See **Policies** tab (who has access)
- See **Settings** tab (configuration)

---

### 4. Check Service Tokens

**Path**: `Zero Trust → Access → Service Tokens`

**Steps**:
1. Go to **Zero Trust → Access → Service Tokens**
2. See list of all service tokens

**What to look for**:
- Token name (e.g., "github-actions-collegewise-staging")
- Client ID
- Created date
- Last used date

**Important**: 
- You can see Client ID but NOT the secret (it's only shown once at creation)
- If you need a new secret, you must create a new token

**To create new token**:
1. Click **Create Service Token**
2. Enter name
3. Click **Create**
4. **Copy Client ID and Client Secret immediately** (secret only shown once!)

---

### 5. Check Tunnel Status (Real-time)

**Path**: `Zero Trust → Networks → Tunnels → [Select Tunnel] → Status`

**Steps**:
1. Go to **Zero Trust → Networks → Tunnels**
2. Click on tunnel name
3. See **Status** tab

**What to look for**:
- **Connectors**: Shows active connections
  - If you see a connector, tunnel is running
  - Shows IP address and last seen time
- **Traffic**: Shows data transferred
- **Events**: Shows connection/disconnection events

**If no connectors shown**: Tunnel is not running on the server

---

### 6. Check DNS Records

**Path**: `Websites → [Your Domain] → DNS`

**Steps**:
1. Go to main Cloudflare dashboard
2. Select your domain (e.g., `collegewise.com`)
3. Click **DNS** in left sidebar
4. Look for CNAME records

**What to look for**:
- Record type: `CNAME`
- Name: `staging-ssh` (or your hostname)
- Target: Should be a `.cfargotunnel.com` domain
- Proxy status: Usually gray cloud (DNS only)

**Example**:
```
Type: CNAME
Name: staging-ssh
Target: xxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.cfargotunnel.com
Proxy: DNS only (gray cloud)
```

---

## Quick Checklist for Setup Verification

### ✅ Tunnel Setup
- [ ] Go to **Zero Trust → Networks → Tunnels**
- [ ] Verify tunnel exists (or create new one)
- [ ] Check tunnel has connectors (is running)
- [ ] Verify DNS route exists in tunnel's Public Hostnames

### ✅ Access Application
- [ ] Go to **Zero Trust → Access → Applications**
- [ ] Verify application exists for SSH hostname
- [ ] Check application has policy allowing service tokens
- [ ] Verify application domain matches DNS hostname

### ✅ Service Token
- [ ] Go to **Zero Trust → Access → Service Tokens**
- [ ] Verify token exists (or create new one)
- [ ] Copy Client ID and Client Secret
- [ ] Add to GitHub secrets

### ✅ DNS
- [ ] Go to **Websites → [Domain] → DNS**
- [ ] Verify CNAME record exists for hostname
- [ ] Check target points to `.cfargotunnel.com` domain

---

## Common Dashboard Locations

| What You Need | Dashboard Path |
|---------------|----------------|
| List all tunnels | Zero Trust → Networks → Tunnels |
| Tunnel details | Zero Trust → Networks → Tunnels → [Tunnel Name] |
| DNS routes for tunnel | Zero Trust → Networks → Tunnels → [Tunnel] → Public Hostnames |
| Access applications | Zero Trust → Access → Applications |
| Service tokens | Zero Trust → Access → Service Tokens |
| DNS records | Websites → [Domain] → DNS |
| Tunnel status | Zero Trust → Networks → Tunnels → [Tunnel] → Status |

---

## Troubleshooting Dashboard Checks

### "I don't see Zero Trust"
- You need a Cloudflare Zero Trust account (free tier available)
- Go to [one.dash.cloudflare.com](https://one.dash.cloudflare.com)
- Sign up for Zero Trust if needed

### "I see tunnels but no connectors"
- Tunnel is not running on the server
- Check server: `sudo systemctl status cloudflared`
- Start service: `sudo systemctl start cloudflared`

### "I see application but no service tokens"
- Create service token: **Zero Trust → Access → Service Tokens → Create**
- Make sure token has access to the application (check policies)

### "DNS record doesn't exist"
- Create DNS route: `cloudflared tunnel route dns staging-ssh staging-ssh.collegewise.com`
- Or manually create CNAME in DNS dashboard

---

**Last Updated**: 2026-02-06
