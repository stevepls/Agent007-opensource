# Staging Server IP Restriction Solutions

## Problem

The staging server (`35.84.165.174`) has IP restrictions (firewall rules) that block connections from GitHub Actions runners, which use dynamic IP addresses.

## Solution Options

### Option 1: Whitelist GitHub Actions IP Ranges (Recommended for Quick Fix)

**Pros:**
- ✅ Simple to implement
- ✅ No infrastructure changes
- ✅ Works immediately

**Cons:**
- ⚠️ IP ranges change periodically (need to update)
- ⚠️ Large number of IP ranges to whitelist

#### Implementation

1. **Get Current GitHub Actions IP Ranges**:
   ```bash
   curl -s https://api.github.com/meta | python3 -m json.tool | grep -A 100 '"actions"'
   ```

2. **Whitelist on Staging Server**:
   
   **For UFW (Ubuntu Firewall)**:
   ```bash
   # SSH into staging server
   ssh ubuntu@35.84.165.174
   
   # Add GitHub Actions IP ranges
   sudo ufw allow from 4.148.0.0/16 to any port 22
   sudo ufw allow from 4.149.0.0/18 to any port 22
   # ... (add all ranges from GitHub API)
   
   # Or use a script to add all ranges:
   curl -s https://api.github.com/meta | python3 -c "
   import sys, json
   data = json.load(sys.stdin)
   for ip in data.get('actions', []):
       print(f'sudo ufw allow from {ip} to any port 22')
   " | bash
   ```

   **For AWS Security Groups**:
   - Go to EC2 → Security Groups
   - Edit inbound rules
   - Add rules for each GitHub Actions CIDR block
   - Port: 22 (SSH)
   - Source: GitHub Actions IP ranges

   **For Cloudflare/Other Firewalls**:
   - Add GitHub Actions IP ranges to allowlist
   - Port: 22 (SSH)

3. **Automate IP Range Updates**:
   
   Create a script to periodically update IP ranges:
   ```bash
   #!/bin/bash
   # update-github-ips.sh
   
   GITHUB_IPS=$(curl -s https://api.github.com/meta | python3 -c "
   import sys, json
   data = json.load(sys.stdin)
   print(' '.join(data.get('actions', [])))
   ")
   
   # Remove old GitHub Actions rules
   sudo ufw status numbered | grep "GitHub Actions" | awk -F'[][]' '{print $2}' | sort -rn | xargs -I {} sudo ufw --force delete {}
   
   # Add new rules
   for ip in $GITHUB_IPS; do
       sudo ufw allow from $ip to any port 22 comment "GitHub Actions"
   done
   ```

   Run via cron:
   ```bash
   # Add to crontab (runs weekly)
   0 0 * * 0 /path/to/update-github-ips.sh
   ```

---

### Option 2: Self-Hosted GitHub Actions Runner (Recommended for Security)

**Pros:**
- ✅ Full control over IP address
- ✅ More secure (no need to whitelist many IPs)
- ✅ Can run on same network as staging server
- ✅ Better performance (no network latency)

**Cons:**
- ⚠️ Requires a server to run the runner
- ⚠️ Need to maintain the runner software
- ⚠️ Runner must be accessible from GitHub

#### Implementation

1. **Set Up Runner Server**:
   
   Option A: Use the staging server itself (if allowed)
   ```bash
   # SSH into staging server
   ssh ubuntu@35.84.165.174
   
   # Create actions-runner directory
   mkdir actions-runner && cd actions-runner
   
   # Download runner
   curl -o actions-runner-linux-x64-2.311.0.tar.gz -L https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-linux-x64-2.311.0.tar.gz
   tar xzf ./actions-runner-linux-x64-2.311.0.tar.gz
   ```

   Option B: Use a separate server with access to staging
   ```bash
   # Use a server that's already whitelisted
   # Same setup as above
   ```

2. **Configure Runner**:
   ```bash
   # Get registration token from GitHub
   # Repo → Settings → Actions → Runners → New self-hosted runner
   
   ./config.sh --url https://github.com/collegewise1/cw-magento --token <REGISTRATION_TOKEN>
   
   # Install as service
   sudo ./svc.sh install
   sudo ./svc.sh start
   ```

3. **Update Workflow to Use Self-Hosted Runner**:
   
   Update `.github/workflows/deploy.yml`:
   ```yaml
   jobs:
     deploy-staging:
       runs-on: self-hosted  # Changed from ubuntu-latest
       # ... rest of config
   ```

4. **Configure Runner Labels** (Optional):
   ```bash
   ./config.sh --url https://github.com/collegewise1/cw-magento --token <TOKEN> --labels staging,deploy
   ```
   
   Then in workflow:
   ```yaml
   runs-on: [self-hosted, staging]
   ```

---

### Option 3: SSH Jump Server / Proxy

**Pros:**
- ✅ No changes to staging server firewall
- ✅ Uses existing infrastructure
- ✅ Secure (SSH tunnel)

**Cons:**
- ⚠️ Requires a jump server with access to staging
- ⚠️ More complex setup

#### Implementation

1. **Set Up Jump Server**:
   - Use a server that's already whitelisted on staging
   - Ensure it has SSH access to staging server

2. **Update Workflow**:
   
   Modify `.github/workflows/deploy.yml`:
   ```yaml
   - name: Setup SSH key
     uses: webfactory/ssh-agent@v0.9.0
     with:
       ssh-private-key: ${{ secrets.STAGING_SSH_KEY }}

   - name: Deploy via jump server
     env:
       JUMP_HOST: ${{ secrets.JUMP_HOST }}  # e.g., jump.example.com
       JUMP_USER: ${{ secrets.JUMP_USER }}  # e.g., ubuntu
       STAGING_HOST: ${{ secrets.STAGING_HOST }}
       STAGING_USER: ${{ secrets.STAGING_USER }}
       STAGING_PATH: ${{ secrets.STAGING_PATH }}
     run: |
       # Create SSH config for jump host
       cat >> ~/.ssh/config << EOF
       Host staging
         HostName ${STAGING_HOST}
         User ${STAGING_USER}
         ProxyJump ${JUMP_USER}@${JUMP_HOST}
         StrictHostKeyChecking no
       EOF
       
       # Use jump host for rsync
       rsync -avz --delete \
         -e "ssh -J ${JUMP_USER}@${JUMP_HOST}" \
         --exclude='.git' \
         --exclude='.github' \
         ./ ${STAGING_USER}@${STAGING_HOST}:${STAGING_PATH}/
       
       # Use jump host for SSH commands
       ssh -J ${JUMP_USER}@${JUMP_HOST} ${STAGING_USER}@${STAGING_HOST} << 'DEPLOY_SCRIPT'
         cd ${STAGING_PATH}
         # ... deployment commands
       DEPLOY_SCRIPT
   ```

---

### Option 4: VPN Connection

**Pros:**
- ✅ Secure tunnel
- ✅ Can whitelist single VPN IP
- ✅ Works for multiple services

**Cons:**
- ⚠️ Requires VPN infrastructure
- ⚠️ More complex setup
- ⚠️ May need VPN client in GitHub Actions

#### Implementation

1. **Set Up VPN** (WireGuard, OpenVPN, etc.)
2. **Configure GitHub Actions to Connect to VPN**
3. **Whitelist VPN IP on Staging Server**

This is more complex and typically requires custom actions or scripts.

---

## Recommended Approach

### For Immediate Solution: **Option 1 (Whitelist IP Ranges)**

Quick to implement, works immediately. Set up automated updates for IP ranges.

### For Long-Term Solution: **Option 2 (Self-Hosted Runner)**

More secure, better performance, easier to maintain. If you have a server that can run the runner and has access to staging, this is the best option.

## Implementation Steps (Option 1 - Quick Fix)

1. **Get GitHub Actions IP Ranges**:
   ```bash
   curl -s https://api.github.com/meta | python3 -c "
   import sys, json
   data = json.load(sys.stdin)
   for ip in data.get('actions', []):
       print(ip)
   " > github-actions-ips.txt
   ```

2. **Whitelist on Staging Server**:
   ```bash
   ssh ubuntu@35.84.165.174
   
   # For UFW
   while read ip; do
       sudo ufw allow from $ip to any port 22 comment "GitHub Actions"
   done < github-actions-ips.txt
   ```

3. **Set Up Automated Updates** (Optional):
   - Create cron job to update IP ranges weekly
   - Or use GitHub webhook to trigger updates

4. **Test Deployment**:
   - Trigger a test deployment
   - Verify SSH connection works
   - Check deployment completes successfully

## Implementation Steps (Option 2 - Self-Hosted Runner)

1. **Choose Runner Location**:
   - Staging server itself (if allowed)
   - Separate server with staging access
   - Cloud instance with staging access

2. **Install Runner**:
   ```bash
   # On runner server
   mkdir actions-runner && cd actions-runner
   curl -o actions-runner-linux-x64-2.311.0.tar.gz -L https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-linux-x64-2.311.0.tar.gz
   tar xzf ./actions-runner-linux-x64-2.311.0.tar.gz
   ```

3. **Register Runner**:
   - Go to GitHub: Repo → Settings → Actions → Runners → New self-hosted runner
   - Copy registration token
   - Run: `./config.sh --url https://github.com/collegewise1/cw-magento --token <TOKEN>`

4. **Install as Service**:
   ```bash
   sudo ./svc.sh install
   sudo ./svc.sh start
   ```

5. **Update Workflow**:
   ```yaml
   deploy-staging:
     runs-on: self-hosted
     # ... rest of config
   ```

## Testing

After implementing either solution:

1. **Test SSH Connection**:
   ```bash
   # From GitHub Actions (test workflow)
   ssh -i <key> ubuntu@35.84.165.174 "echo 'Connection successful'"
   ```

2. **Test Deployment**:
   - Create a test PR
   - Merge to staging
   - Verify deployment runs successfully

3. **Monitor Logs**:
   - Check GitHub Actions logs
   - Check staging server logs
   - Verify deployment completed

## Security Considerations

- **Option 1**: Whitelisting many IP ranges increases attack surface
- **Option 2**: Self-hosted runner requires securing the runner server
- **Option 3**: Jump server must be secured
- **Option 4**: VPN requires proper key management

## Maintenance

- **Option 1**: Update IP ranges weekly/monthly
- **Option 2**: Keep runner software updated
- **Option 3**: Maintain jump server security
- **Option 4**: Keep VPN software updated

---

**Next Steps**: Choose an option and I can help implement it!
