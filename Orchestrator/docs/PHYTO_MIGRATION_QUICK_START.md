# Phyto Migration Quick Start Guide

## Prerequisites

1. **GitHub Repository** ✅
   - Repository: `https://github.com/pdxaromatics/magento2`
   - SSH URL: `git@github.com:pdxaromatics/magento2.git`
   - Identifier: `pdxaromatics/magento2`

2. **Verify Access**
   ```bash
   # Check GitHub CLI authentication
   gh auth status
   
   # If not authenticated:
   gh auth login
   
   # Test access to the repository
   gh repo view pdxaromatics/magento2
   ```

3. **Verify Bitbucket Access**
   ```bash
   # Test SSH access to Bitbucket
   git ls-remote git@bitbucket.org:pdxaromatics/phytom2-repo.git
   ```

## Quick Migration (Automated)

Use the complete migration and cleanup script:

```bash
cd /home/steve/Agent007/Orchestrator/scripts
./migrate_and_cleanup_phyto.sh
```

The script will:
- ✅ Check prerequisites
- ✅ Verify GitHub repository access
- ✅ Migrate all branches/tags from Bitbucket to GitHub (as-is)
- ✅ Clean up merged branches on GitHub (keeps backups and important branches)
- ✅ Verify results

**Options**:
- `--skip-cleanup` - Skip branch cleanup after migration
- `--cleanup-only` - Only run cleanup (skip migration)
- `--dry-run` - Preview what would be done

**Alternative**: Use the migration-only script if you want to skip cleanup:
```bash
./migrate_phyto_to_github.sh pdxaromatics/magento2
```

## Manual Migration Steps

If you prefer to do it manually:

### 1. Audit Bitbucket Repository
```bash
cd /tmp
git clone --mirror git@bitbucket.org:pdxaromatics/phytom2-repo.git phyto-mirror
cd phyto-mirror
git branch -a
git tag -l
git count-objects -vH
```

### 2. Check GitHub Repository Status
```bash
gh repo view pdxaromatics/magento2 --json isEmpty,nameWithOwner,defaultBranchRef
```

### 3. Perform Migration
```bash
cd /tmp/phyto-mirror
git remote set-url origin git@github.com:pdxaromatics/magento2.git

# If GitHub repo is empty:
git push --mirror

# If GitHub repo has content, coordinate with Jarod first!
```

### 4. Verify Migration
```bash
git ls-remote --heads origin
git ls-remote --tags origin
gh repo view pdxaromatics/magento2
```

## Update Local Repositories

After migration, update your local clone:

```bash
cd /path/to/local/phytom2-repo
git remote -v  # Check current remotes

# Update to GitHub
git remote set-url origin git@github.com:pdxaromatics/magento2.git

# Fetch everything
git fetch --all
git fetch --tags
```

## Important Notes

⚠️ **If GitHub repository has existing content:**
- Coordinate with Jarod before migration
- Decide on merge strategy
- Consider pushing to separate branch first, then merging via PR

⚠️ **Large repositories:**
- Migration may take time (hours for very large repos)
- Monitor network connection
- Consider doing during low-traffic period

⚠️ **After migration:**
- Update CI/CD pipelines
- Update webhooks and integrations
- Notify team members
- Keep Bitbucket repo as backup for 30 days

## Getting Help

- Full migration guide: `Orchestrator/docs/PHYTO_BITBUCKET_TO_GITHUB_MIGRATION.md`
- Migration script: `Orchestrator/scripts/migrate_phyto_to_github.sh`
- Check script help: `./migrate_phyto_to_github.sh` (without arguments)

## Next Steps After Migration

1. ✅ Verify all branches and tags migrated
2. ✅ Update local repository remotes
3. ✅ Update CI/CD pipelines (Bitbucket Pipelines → GitHub Actions)
4. ✅ Update webhooks (ClickUp, Slack, etc.)
5. ✅ Test deployment process
6. ✅ Notify team members
7. ✅ Archive Bitbucket repository (after 30 days)

## Team Member Instructions

**For team members switching over, see**: `PHYTO_TEAM_MIGRATION_GUIDE.md`

Quick steps:
1. Update remote: `git remote set-url origin git@github.com:pdxaromatics/magento2.git`
2. Fetch branches: `git fetch --all`
3. Continue working normally!
