# Phyto Project: Bitbucket to GitHub Migration Plan

## Current State

Based on repository analysis, the Phyto project currently has:

### Bitbucket Repositories
- **Primary**: `git@bitbucket.org:pdxaromatics/phytom2-repo.git`
- **Internal**: `git@bitbucket.org:peoplelikesoftware/internal-phyto.git`

### GitHub Repository (Target)
- **Repository URL**: `https://github.com/pdxaromatics/magento2`
- **SSH URL**: `git@github.com:pdxaromatics/magento2.git`
- **Repository Identifier**: `pdxaromatics/magento2`
- **Status**: Repository exists on GitHub (shared by Jarod)
- **Visibility**: Private
- **Default Branch**: `main`
- **⚠️ IMPORTANT**: Repository is **NOT empty** - contains existing content

### Repository Structure
- Main repository appears to be a Magento 2 project (phytom2-repo)
- Multiple remotes suggest a complex workflow (internal vs external)
- Likely contains production code, branches, tags, and commit history

---

## Migration Strategy Options

### Option 1: Mirror Migration to Existing Repository (Recommended)
**Best for**: Preserving full history, maintaining all branches/tags, zero downtime

**⚠️ Important**: Since the GitHub repository already exists, we need to handle this carefully:
- If the GitHub repo is **empty**: Use `--mirror` push (overwrites everything)
- If the GitHub repo has **existing content**: Need to merge or coordinate with Jarod

**Process**:
1. **Verify GitHub repository status** (check if empty or has content):
   ```bash
   # Get the repo URL from Jarod first, then:
   gh repo view <org-or-user>/<repo-name> --json isEmpty,nameWithOwner
   ```

2. **Clone Bitbucket repo with all refs**:
   ```bash
   git clone --mirror git@bitbucket.org:pdxaromatics/phytom2-repo.git phyto-mirror
   cd phyto-mirror
   ```

3. **Add GitHub remote**:
   ```bash
   git remote set-url origin git@github.com:pdxaromatics/magento2.git
   # OR if repo has content, add as separate remote:
   git remote add github git@github.com:pdxaromatics/magento2.git
   ```

4. **Push all refs to GitHub**:
   ```bash
   # If GitHub repo is empty:
   git push --mirror origin
   
   # If GitHub repo has content, push to separate remote and merge:
   git push --mirror github
   # Then coordinate merge strategy with Jarod
   ```

5. **Update local clones**:
   ```bash
   git remote set-url origin git@github.com:pdxaromatics/magento2.git
   git fetch --all
   ```

**Pros**:
- ✅ Preserves 100% of history, branches, tags
- ✅ No data loss
- ✅ Can be done without downtime
- ✅ Reversible (Bitbucket remains intact)

**Cons**:
- ⚠️ Large repositories may take time to push
- ⚠️ Need to update CI/CD pipelines
- ⚠️ Team needs to update their remotes

---

### Option 2: Selective Migration
**Best for**: Cleaning up old branches, starting fresh on GitHub

**Process**:
1. **Clone only main branches**:
   ```bash
   git clone git@bitbucket.org:pdxaromatics/phytom2-repo.git phyto-clean
   cd phyto-clean
   ```
2. **Create GitHub repo and push**:
   ```bash
   git remote add github git@github.com:forgelab/phytom2-repo.git
   git push github main
   git push github --all  # Only active branches
   git push github --tags  # Only relevant tags
   ```

**Pros**:
- ✅ Cleaner repository (no dead branches)
- ✅ Faster initial sync
- ✅ Easier to audit what's migrated

**Cons**:
- ⚠️ Loses historical branches/tags
- ⚠️ May break references to old commits
- ⚠️ More manual work

---

### Option 3: Hybrid Approach
**Best for**: Migrating main repo + keeping internal separate

**Process**:
1. **Migrate primary repo** (pdxaromatics/phytom2-repo) → GitHub
2. **Keep internal repo** (peoplelikesoftware/internal-phyto) on Bitbucket OR migrate separately
3. **Update remotes** to point to GitHub for primary, Bitbucket for internal (if kept)

**Pros**:
- ✅ Separates concerns (public vs internal)
- ✅ Gradual migration
- ✅ Can test primary migration first

**Cons**:
- ⚠️ More complex remote management
- ⚠️ Team needs to understand dual-remote setup

---

## Pre-Migration Checklist

### 1. Repository Audit
- [ ] Identify all active branches
- [ ] List all tags and their purposes
- [ ] Check repository size (`git count-objects -vH`)
- [ ] Identify large files (LFS candidates)
- [ ] Review commit history for sensitive data
- [ ] **Optional**: Clean up old/merged branches before migration
  ```bash
  # Preview what would be deleted
  cd /path/to/phytom2-repo
  /home/steve/Agent007/Orchestrator/scripts/cleanup_branches.sh --all --merged --dry-run
  
  # Actually clean up merged branches
  /home/steve/Agent007/Orchestrator/scripts/cleanup_branches.sh --all --merged
  ```

### 2. Access & Permissions
- [ ] Create GitHub organization/team (forgelab)
- [ ] Set up repository permissions
- [ ] Generate SSH keys or PATs for CI/CD
- [ ] Document who needs access

### 3. CI/CD Pipeline Updates
- [ ] Identify all Bitbucket Pipelines configurations
- [ ] Map to GitHub Actions equivalents
- [ ] Update deployment scripts
- [ ] Update webhook URLs
- [ ] Test pipeline in GitHub before cutover

### 4. Integrations
- [ ] ClickUp integrations (if any)
- [ ] Slack notifications
- [ ] Deployment automation
- [ ] Monitoring/alerting systems
- [ ] Documentation links

### 5. Team Communication
- [ ] Notify team of migration date
- [ ] Provide update instructions
- [ ] Schedule migration window
- [ ] Plan rollback procedure

---

## Migration Steps (Detailed - Option 1)

### Phase 1: Preparation (1-2 days before)

```bash
# 1. Verify GitHub repository access and status
gh repo view pdxaromatics/magento2 --json isEmpty,nameWithOwner,defaultBranchRef
# Check if repo is empty (isEmpty: true/false)
# Note the default branch name

# 3. Audit Bitbucket repository
cd /tmp
git clone --mirror git@bitbucket.org:pdxaromatics/phytom2-repo.git phyto-audit
cd phyto-audit
git branch -a
git tag -l
git count-objects -vH
git log --oneline --all | wc -l  # Total commits

# 4. Test clone and push (dry run)
cd /tmp
git clone --mirror git@bitbucket.org:pdxaromatics/phytom2-repo.git phyto-test
cd phyto-test
git remote set-url origin git@github.com:pdxaromatics/magento2.git
# If repo is empty, test mirror push:
git push --mirror --dry-run  # Check for issues
# If repo has content, coordinate with Jarod first
```

### Phase 2: Migration (Migration window)

**Strategy**: Copy everything as-is to GitHub, then clean up afterwards

```bash
# 1. Create mirror clone
cd /tmp
git clone --mirror git@bitbucket.org:pdxaromatics/phytom2-repo.git phyto-migration
cd phyto-migration

# 2. Add GitHub remote
git remote set-url origin git@github.com:pdxaromatics/magento2.git

# 3. Push everything (this may take time)
# This will overwrite existing content in GitHub repo
# Coordinate with Jarod first if GitHub repo has important content
git push --mirror --force

# 4. Verify migration
gh repo view pdxaromatics/magento2 --json name,defaultBranchRef,refs
git ls-remote --heads origin  # List all branches on GitHub
git ls-remote --tags origin   # List all tags on GitHub
```

### Phase 3: Update Local Repositories

```bash
# For each developer's local clone:
cd /path/to/local/phytom2-repo
git remote -v  # Check current remotes

# Update to GitHub
git remote set-url origin git@github.com:pdxaromatics/magento2.git

# Or add GitHub as new remote and keep Bitbucket as backup:
git remote rename origin bitbucket
git remote add origin git@github.com:pdxaromatics/magento2.git

# Fetch all branches and tags
git fetch --all
git fetch --tags

# Update tracking branch (adjust branch name if different)
git branch -u origin/main main  # or origin/master master
```

### Phase 4: Update CI/CD

```yaml
# Example: Update GitHub Actions workflow
name: Deploy
on:
  push:
    branches: [main, staging]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          repository: forgelab/phytom2-repo
```

### Phase 5: Cleanup Branches on GitHub

After migration, clean up old/merged branches on GitHub:

```bash
# Clone the GitHub repo locally for cleanup
cd /tmp
git clone git@github.com:pdxaromatics/magento2.git phyto-cleanup
cd phyto-cleanup

# Preview what would be deleted (merged branches)
/home/steve/Agent007/Orchestrator/scripts/cleanup_branches.sh --remote origin --merged --dry-run

# Actually delete merged branches on GitHub
# This will keep: main, master, production, dev, prod, stage, and any branches with bk/backup/copy/cp
/home/steve/Agent007/Orchestrator/scripts/cleanup_branches.sh --remote origin --merged

# Or clean up both local and remote
/home/steve/Agent007/Orchestrator/scripts/cleanup_branches.sh --all --merged
```

**Note**: The cleanup script automatically protects:
- Branches with: `bk`, `backup`, `copy`, `cp` in the name
- Branches with: `master`, `main`, `production`, `dev`, `prod`, `stage` in the name
- Exact matches: `main`, `master`, `develop`, `staging`, `production`
- Current branch

### Phase 6: Post-Migration

- [ ] Verify all branches pushed
- [ ] Verify all tags present
- [ ] Clean up old/merged branches (Phase 5)
- [ ] Test CI/CD pipelines
- [ ] Update documentation
- [ ] Archive Bitbucket repo (don't delete immediately)

---

## Handling the Internal Repository

The `internal-phyto` repository presents a decision point:

### Option A: Migrate Separately
- Create `forgelab/internal-phyto` on GitHub
- Migrate using same mirror process
- Update remotes in projects that reference it

### Option B: Merge into Main Repo
- If internal is just a fork/branch, merge branches
- Consolidate into single repository
- Update any submodule references

### Option C: Keep on Bitbucket
- If internal has different access requirements
- Maintain dual-remote setup
- Document which remote to use for what

**Recommendation**: Migrate separately to `forgelab/internal-phyto` to maintain separation of concerns.

---

## Potential Issues & Solutions

### Issue 1: Large Repository Size
**Problem**: Repository > 1GB may timeout on push

**Solution**:
```bash
# Use Git LFS for large files
git lfs migrate import --include="*.zip,*.sql,*.dump" --everything

# Or push in chunks
git push origin main
git push origin --all
git push origin --tags
```

### Issue 2: LFS Files
**Problem**: Git LFS files may not migrate automatically

**Solution**:
```bash
# Migrate LFS files
git lfs fetch --all
git lfs push --all git@github.com:forgelab/phytom2-repo.git
```

### Issue 3: Protected Branches
**Problem**: GitHub branch protection rules need setup

**Solution**:
```bash
# Set up branch protection via API or UI
gh api repos/forgelab/phytom2-repo/branches/main/protection \
  --method PUT \
  --field required_status_checks='{"strict":true,"contexts":["ci"]}' \
  --field enforce_admins=true \
  --field required_pull_request_reviews='{"required_approving_review_count":1}'
```

### Issue 4: Webhooks & Integrations
**Problem**: External services still point to Bitbucket

**Solution**:
- Update webhook URLs in:
  - ClickUp (if integrated)
  - Deployment systems
  - Monitoring tools
  - Slack notifications

### Issue 5: Commit Signing
**Problem**: GPG keys may need re-verification

**Solution**:
```bash
# Verify GPG keys are in GitHub account
gh auth refresh -s write:gpg_key
```

---

## Rollback Plan

If migration fails:

1. **Keep Bitbucket repository active** (don't delete)
2. **Revert remotes**:
   ```bash
   git remote set-url origin git@bitbucket.org:pdxaromatics/phytom2-repo.git
   ```
3. **Communicate rollback** to team
4. **Investigate issues** before retry
5. **Schedule new migration window**

---

## Timeline Estimate

| Phase | Duration | Notes |
|-------|----------|-------|
| Preparation | 2-3 days | Audit, setup, testing |
| Migration | 2-4 hours | Actual push (depends on repo size) |
| Team Updates | 1 day | Update local repos, test |
| CI/CD Updates | 1-2 days | Pipeline migration, testing |
| Post-Migration | 1 week | Monitoring, fixes, documentation |

**Total**: ~1-2 weeks for complete migration

---

## Cost Considerations

### Bitbucket
- Current: Likely free tier or paid plan
- After migration: Can downgrade or cancel

### GitHub
- **Free tier**: Public repos, unlimited private repos (limited collaborators)
- **Team plan**: $4/user/month (if needed for private repos with more collaborators)
- **Actions**: 2,000 minutes/month free, then $0.008/minute

**Recommendation**: Start with free tier, upgrade if needed for team features.

---

## Next Steps

1. **Decision**: Choose migration option (recommend Option 1 - Mirror)
2. **Schedule**: Pick migration window (low-traffic period)
3. **Prepare**: Complete pre-migration checklist
4. **Execute**: Run migration during scheduled window
5. **Verify**: Confirm all data migrated correctly
6. **Update**: Team remotes, CI/CD, integrations
7. **Monitor**: Watch for issues in first week
8. **Archive**: Mark Bitbucket repo as archived (keep for 30 days)

---

## Questions to Resolve

1. **GitHub Repository URL**: ✅ **RESOLVED**
   - Repository: `https://github.com/pdxaromatics/magento2`
   - SSH URL: `git@github.com:pdxaromatics/magento2.git`
   - Identifier: `pdxaromatics/magento2`

2. **Existing Repository Status**: ✅ **VERIFIED**
   - Repository is **NOT empty** - contains existing content
   - **⚠️ CRITICAL**: Mirror push will **overwrite** all existing content
   - **Action Required**: Coordinate with Jarod before migration
   - **Options**:
     - Option A: Backup existing GitHub content, then mirror push
     - Option B: Merge Bitbucket content into existing GitHub repo
     - Option C: Push Bitbucket branches separately and merge via PRs
   - If it has content, coordinate merge strategy with Jarod
   - If empty, can proceed with mirror push

3. **Repository visibility**: Private or public?

4. **Internal repo**: Migrate separately or merge?

5. **Migration date**: When is best window?

6. **Team size**: How many developers need access?

7. **CI/CD**: Current pipeline complexity?

8. **Large files**: Any files > 100MB that need LFS?

---

## Tools & Commands Reference

```bash
# Repository size
git count-objects -vH

# List all branches
git branch -a

# List all tags
git tag -l

# Mirror clone
git clone --mirror <source-url>

# Push everything
git push --mirror

# Update remote
git remote set-url origin <new-url>

# Verify migration
gh repo view <org>/<repo> --json name,defaultBranchRef,refs

# Check LFS files
git lfs ls-files

# Migrate LFS
git lfs migrate import --include="*.ext" --everything
```

---

**Document Status**: Ready for execution
**Created**: 2026-02-06
**Updated**: 2026-02-06
**GitHub Repository**: `pdxaromatics/magento2`
**Next Steps**: 
1. ✅ Verify repository status (empty vs. has content)
2. Coordinate migration approach with Jarod (if repo has content)
3. Execute migration using script or manual steps
