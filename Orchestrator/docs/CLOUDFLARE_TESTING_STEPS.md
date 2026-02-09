# Cloudflare SSH Testing Steps

## Current Status

✅ Credentials are set:
- `CF_ACCESS_CLIENT_ID` = `922aa77867737fb363074aac2fda53a1.access`
- `CF_ACCESS_CLIENT_SECRET` = `5c739f66517825a04e10de3945bfa84fcf4859d073cf3fb81702dd14b94507ca`

## Testing Steps

### Step 1: Test SSH Config Generation

```bash
cloudflared access ssh-config --hostname cw-staging-ssh.collegewise.com
```

**Expected output**: SSH config block (like what we saw earlier)

**If this works**: ✅ Credentials are valid, proceed to Step 2  
**If this fails**: ❌ Credentials are wrong or token doesn't have access

### Step 2: Test SSH Connection

```bash
ssh cw-staging-ssh.collegewise.com
```

**Expected**: SSH connection prompt or successful connection

**If this works**: ✅ Everything is configured correctly!  
**If this fails**: Check error message

## Troubleshooting

### If SSH Config Generation Fails

**Error: "authentication failed" or similar**
- Credentials don't match the service token
- Token might be revoked
- **Fix**: Create new service token and update GitHub secrets

### If SSH Config Works But SSH Fails

**Possible causes:**
1. **SSH service not running on server**
   ```bash
   # On staging server
   sudo systemctl status ssh
   ```

2. **Tunnel not routing correctly**
   ```bash
   # Check tunnel status
   sudo systemctl status cloudflared
   sudo journalctl -u cloudflared -n 50
   ```

3. **Config file issue**
   ```bash
   # Verify config
   sudo cat /etc/cloudflared/config.yml
   ```

4. **DNS not resolving**
   ```bash
   nslookup cw-staging-ssh.collegewise.com
   ```

## Next Steps After Successful Test

Once SSH works:

1. ✅ **Test from GitHub Actions**: Merge a PR to staging branch
2. ✅ **Verify deployment**: Check if GitHub Actions can deploy
3. ✅ **Document**: Everything is working!

---

**Run the test commands above to verify everything works!**
