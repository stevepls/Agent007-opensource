# Cloudflare Tunnel Troubleshooting

## Error: Existing Certificate Found

### Problem
```
ERR You have an existing certificate at /home/ubuntu/.cloudflared/cert.pem which login would overwrite.
If this is intentional, please move or delete that file then run this command again.
```

### Solution Options

#### Option 1: Use Existing Certificate (Recommended First)

The certificate might already be valid. Check if you can use it:

```bash
# Test if existing certificate works
cloudflared tunnel list

# If this works, you can skip the login step and proceed to creating tunnels
```

**If `cloudflared tunnel list` works:**
- ✅ Certificate is valid
- ✅ Skip `cloudflared tunnel login`
- ✅ Proceed directly to `cloudflared tunnel create`

#### Option 2: Backup and Delete (If Certificate is Invalid)

If the certificate doesn't work or is from a different account:

```bash
# Backup the old certificate (just in case)
cp ~/.cloudflared/cert.pem ~/.cloudflared/cert.pem.backup

# Delete the old certificate
rm ~/.cloudflared/cert.pem

# Now run login again
cloudflared tunnel login
```

#### Option 3: Move to Different Location

If you want to keep the old certificate for reference:

```bash
# Move old certificate
mv ~/.cloudflared/cert.pem ~/.cloudflared/cert.pem.old

# Run login to create new certificate
cloudflared tunnel login
```

### Quick Decision Guide

1. **Run**: `cloudflared tunnel list`
2. **If it works**: Use existing certificate, skip login
3. **If it fails**: Delete old certificate and run login

### Common Scenarios

#### Scenario 1: Certificate from Previous Setup
- **Action**: Delete and create new one
- **Command**: `rm ~/.cloudflared/cert.pem && cloudflared tunnel login`

#### Scenario 2: Certificate from Different Cloudflare Account
- **Action**: Delete and create new one for correct account
- **Command**: `rm ~/.cloudflared/cert.pem && cloudflared tunnel login`

#### Scenario 3: Certificate Still Valid
- **Action**: Use existing certificate
- **Command**: Skip login, proceed to `cloudflared tunnel create`

## Other Common Issues

### Tunnel Not Starting

```bash
# Check service status
sudo systemctl status cloudflared

# Check logs
sudo journalctl -u cloudflared -n 50

# Common fixes:
# - Verify config file exists: /etc/cloudflared/config.yml
# - Check tunnel ID matches in config
# - Verify credentials file path is correct
```

### DNS Not Resolving

```bash
# Check DNS record
nslookup staging-ssh.collegewise.com

# Verify DNS route
cloudflared tunnel route dns list

# Re-create DNS route if needed
cloudflared tunnel route dns staging-ssh staging-ssh.collegewise.com
```

### SSH Connection Fails

```bash
# Test tunnel is running
sudo systemctl status cloudflared

# Test DNS resolution
nslookup staging-ssh.collegewise.com

# Test with cloudflared directly
export CF_ACCESS_CLIENT_ID="your-id"
export CF_ACCESS_CLIENT_SECRET="your-secret"
cloudflared access ssh staging-ssh.collegewise.com
```

### Authentication Errors

- Verify `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET` in GitHub secrets
- Check Cloudflare Access application policy allows service tokens
- Ensure service token hasn't expired
- Verify token has access to the correct application

---

**Last Updated**: 2026-02-06
