# ⚠️ IMPORTANT: GitHub Repository Has Existing Content

## Repository Status

**Repository**: `pdxaromatics/magento2`  
**Status**: **NOT EMPTY** - Contains existing content  
**Default Branch**: `main`  
**Visibility**: Private

## Critical Warning

The GitHub repository `pdxaromatics/magento2` **already contains code**. 

A `git push --mirror` operation will **completely overwrite** all existing content in the GitHub repository, including:
- All existing branches
- All existing commits
- All existing tags
- All existing history

## Migration Options

### Option 1: Backup and Overwrite (If Existing Content is Not Needed)
**Use this if**: The existing GitHub content is not important or is outdated

```bash
# 1. Backup existing GitHub content first
cd /tmp
git clone --mirror git@github.com:pdxaromatics/magento2.git github-backup-$(date +%Y%m%d)
cd github-backup-*

# 2. List what will be overwritten
git branch -a
git tag -l

# 3. Proceed with migration (will overwrite)
cd /tmp
git clone --mirror git@bitbucket.org:pdxaromatics/phytom2-repo.git phyto-mirror
cd phyto-mirror
git remote set-url origin git@github.com:pdxaromatics/magento2.git
git push --mirror
```

### Option 2: Merge Strategy (Recommended)
**Use this if**: You want to preserve both Bitbucket and GitHub content

```bash
# 1. Clone Bitbucket repo
cd /tmp
git clone --mirror git@bitbucket.org:pdxaromatics/phytom2-repo.git phyto-mirror
cd phyto-mirror

# 2. Add GitHub as separate remote
git remote add github git@github.com:pdxaromatics/magento2.git

# 3. Fetch GitHub content
git fetch github

# 4. Push Bitbucket branches to GitHub (without overwriting)
# This creates new branches or updates existing ones
git push github --all

# 5. Push tags
git push github --tags

# 6. Coordinate with Jarod to merge branches via PRs
```

### Option 3: Push to Separate Branch First
**Use this if**: You want to review before merging

```bash
# 1. Clone Bitbucket repo
cd /tmp
git clone --mirror git@bitbucket.org:pdxaromatics/phytom2-repo.git phyto-mirror
cd phyto-mirror

# 2. Add GitHub remote
git remote add github git@github.com:pdxaromatics/magento2.git

# 3. Push main branch to a new branch name
git push github refs/heads/main:refs/heads/bitbucket-main

# 4. Push all other branches with prefix
git push github 'refs/heads/*:refs/heads/bitbucket-*'

# 5. Create PRs to merge bitbucket-* branches into main
```

## Recommended Approach

**Before proceeding, coordinate with Jarod to:**
1. ✅ Understand what content exists in the GitHub repo
2. ✅ Decide if existing content should be preserved
3. ✅ Choose the appropriate migration strategy
4. ✅ Schedule the migration window

## Quick Check Commands

```bash
# Check what's in GitHub repo currently
gh repo view pdxaromatics/magento2 --json defaultBranchRef
gh api repos/pdxaromatics/magento2/branches --jq '.[].name'
gh api repos/pdxaromatics/magento2/tags --jq '.[].name'

# Check what's in Bitbucket repo
git ls-remote --heads git@bitbucket.org:pdxaromatics/phytom2-repo.git
git ls-remote --tags git@bitbucket.org:pdxaromatics/phytom2-repo.git
```

## Next Steps

1. **Review existing GitHub content** with Jarod
2. **Decide on migration strategy** (backup/overwrite vs merge)
3. **Coordinate migration timing** with Jarod
4. **Execute chosen migration approach**
5. **Verify results** after migration

---

**⚠️ DO NOT run `git push --mirror` without coordinating with Jarod first!**
