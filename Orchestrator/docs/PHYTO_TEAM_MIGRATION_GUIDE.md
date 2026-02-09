# Phyto Project: Team Migration Guide (Bitbucket → GitHub)

## 🎯 What Changed

The Phyto project has been migrated from Bitbucket to GitHub:
- **Old Repository**: `git@bitbucket.org:pdxaromatics/phytom2-repo.git`
- **New Repository**: `git@github.com:pdxaromatics/magento2.git`
- **CI/CD**: Bitbucket Pipelines → GitHub Actions
- **Status**: ✅ Migration complete, all branches and history preserved

---

## 📋 Quick Start (5 Minutes)

### Step 1: Update Your Local Repository

If you have an existing local clone:

```bash
# Navigate to your local repository
cd /path/to/phytom2-repo

# Check current remotes
git remote -v

# Update to GitHub
git remote set-url origin git@github.com:pdxaromatics/magento2.git

# Fetch all branches and tags
git fetch --all
git fetch --tags

# Update your current branch to track GitHub
git branch -u origin/main main  # or origin/master if using master
```

### Step 2: Verify Access

```bash
# Test GitHub access
git ls-remote origin

# You should see all branches including:
# - main
# - staging
# - production
# - production-backup041525
# - staging-server-backup
# etc.
```

### Step 3: Continue Working

That's it! You can now work normally:
```bash
git pull origin main
git checkout staging
# etc.
```

---

## 🔄 For New Clones

If you're cloning fresh or don't have a local copy:

```bash
# Clone from GitHub
git clone git@github.com:pdxaromatics/magento2.git
cd magento2

# Or clone specific branch
git clone -b staging git@github.com:pdxaromatics/magento2.git
```

---

## 🌿 Branch Strategy

The following branches are available on GitHub:

- **`main`** - Main development branch
- **`staging`** - Staging environment (auto-deploys)
- **`production`** - Production environment (auto-deploys)
- **`production-backup041525`** - Backup branch (protected)
- **`production-server-backup`** - Backup branch (protected)
- **`staging-server-backup`** - Backup branch (protected)

**Note**: All backup branches are automatically protected and won't be cleaned up.

---

## 🚀 New Workflow: GitHub Actions

### Pull Requests

When you create a pull request:
- ✅ **Tests** run automatically (PHPUnit)
- ✅ **Code Quality** checks (PHP-CS-Fixer, PHPStan)
- ✅ **Security** audit (Composer audit)

### Automatic Deployments

- **Push to `staging`** → Automatically deploys to staging server
- **Push to `production`** → Automatically deploys to production server

### Manual Deployments

You can also trigger deployments manually:
1. Go to **Actions** tab in GitHub
2. Click **"Deploy Magento"** workflow
3. Click **"Run workflow"**
4. Select environment (staging/production)
5. Click **"Run workflow"**

---

## 📝 Daily Workflow

### Making Changes

```bash
# 1. Make sure you're up to date
git checkout main
git pull origin main

# 2. Create a feature branch
git checkout -b feature/my-new-feature

# 3. Make your changes and commit
git add .
git commit -m "Add new feature"

# 4. Push to GitHub
git push origin feature/my-new-feature

# 5. Create Pull Request on GitHub
# Go to: https://github.com/pdxaromatics/magento2
# Click "New Pull Request"
```

### Deploying to Staging

```bash
# Option 1: Merge PR to staging branch (auto-deploys)
# Create PR: feature/my-new-feature → staging

# Option 2: Push directly to staging (auto-deploys)
git checkout staging
git merge feature/my-new-feature
git push origin staging
# Deployment happens automatically via GitHub Actions
```

### Deploying to Production

```bash
# Merge to production branch (auto-deploys)
git checkout production
git merge staging  # or merge your feature branch
git push origin production
# Deployment happens automatically via GitHub Actions
```

---

## 🔐 SSH Keys & Access

### GitHub SSH Setup

If you haven't set up SSH for GitHub:

```bash
# Test current SSH access
ssh -T git@github.com

# If you see "Hi username! You've successfully authenticated..."
# then you're all set!

# If not, add your SSH key to GitHub:
# 1. Copy your public key
cat ~/.ssh/id_rsa.pub
# or
cat ~/.ssh/id_ed25519.pub

# 2. Go to: https://github.com/settings/keys
# 3. Click "New SSH key"
# 4. Paste your public key
```

### Repository Access

Make sure you have access to the repository:
- Contact Jarod or repository admin to be added as a collaborator
- Repository: `pdxaromatics/magento2`

---

## 🔍 What's Different from Bitbucket?

| Feature | Bitbucket | GitHub |
|---------|-----------|--------|
| **Repository URL** | `bitbucket.org/pdxaromatics/phytom2-repo` | `github.com/pdxaromatics/magento2` |
| **CI/CD** | Bitbucket Pipelines | GitHub Actions |
| **Pull Requests** | Bitbucket PRs | GitHub PRs |
| **Deployments** | Manual or Bitbucket Pipelines | Automatic on push to staging/production |
| **Branch Protection** | Bitbucket settings | GitHub branch protection rules |

---

## 🛠️ Troubleshooting

### "Repository not found" or "Permission denied"

**Solution**: Make sure you have access to the repository
1. Check with Jarod that you're added as a collaborator
2. Verify your SSH key is added to GitHub
3. Try: `gh auth status` (if using GitHub CLI)

### "Remote origin already exists"

**Solution**: Update existing remote instead of adding new one
```bash
git remote set-url origin git@github.com:pdxaromatics/magento2.git
```

### "Branch not found"

**Solution**: Fetch all branches
```bash
git fetch --all
git branch -a  # List all branches
```

### "Deployment not working"

**Solution**: Check GitHub Actions
1. Go to **Actions** tab in GitHub
2. Check for failed workflow runs
3. Verify secrets are configured (contact admin)
4. Check deployment logs for errors

### "Can't push to protected branch"

**Solution**: Protected branches require pull requests
- `main`, `staging`, `production` are protected
- Create a feature branch and open a PR
- Or contact admin for direct push access if needed

---

## 📚 Useful Commands

```bash
# Check current remote
git remote -v

# List all branches (local and remote)
git branch -a

# Switch to staging
git checkout staging
git pull origin staging

# Switch to production
git checkout production
git pull origin production

# See recent commits
git log --oneline --graph --all -20

# Check GitHub Actions status
gh run list --repo pdxaromatics/magento2

# View workflow runs
gh workflow list --repo pdxaromatics/magento2
```

---

## 🆘 Need Help?

### Common Issues

1. **Can't access repository**
   - Contact Jarod to be added as collaborator
   - Verify SSH key is added to GitHub

2. **Deployment failed**
   - Check Actions tab for error messages
   - Verify secrets are configured (admin task)
   - Check server connectivity

3. **Branch missing**
   - Run `git fetch --all` to sync all branches
   - Check if branch was cleaned up (backup branches are protected)

4. **CI/CD not running**
   - Check Actions tab
   - Verify workflow file exists: `.github/workflows/deploy.yml`
   - Check branch protection rules

### Getting Support

- **Repository Issues**: Contact Jarod
- **Deployment Issues**: Check GitHub Actions logs
- **Access Issues**: Verify you're added as collaborator
- **Technical Questions**: Check this guide or team documentation

---

## ✅ Migration Checklist

For each team member:

- [ ] Update local repository remote to GitHub
- [ ] Verify access to GitHub repository
- [ ] Test pulling/pushing to GitHub
- [ ] Familiarize with GitHub Actions (check Actions tab)
- [ ] Update any local scripts/tools that reference Bitbucket
- [ ] Bookmark new repository: https://github.com/pdxaromatics/magento2
- [ ] Update IDE/editor settings if needed

---

## 🔗 Quick Links

- **Repository**: https://github.com/pdxaromatics/magento2
- **Actions**: https://github.com/pdxaromatics/magento2/actions
- **Pull Requests**: https://github.com/pdxaromatics/magento2/pulls
- **Settings**: https://github.com/pdxaromatics/magento2/settings

---

## 📝 Notes

- **Bitbucket repository** is still available as read-only backup (for 30 days)
- **All history** has been preserved in GitHub
- **All branches** have been migrated (except merged/cleaned branches)
- **Backup branches** are automatically protected and won't be deleted

---

**Last Updated**: 2026-02-06  
**Migration Date**: 2026-02-06  
**Status**: ✅ Complete - Ready for team use
