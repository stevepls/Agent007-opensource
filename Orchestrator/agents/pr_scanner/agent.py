"""PR Scanner Agent — scans GitHub repos for open pull requests needing attention."""

import json
import logging
import subprocess
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("pr_scanner")


def _run_gh(args: list, timeout: int = 15) -> dict | list | None:
    """Run a gh CLI command and return parsed JSON, or None on failure."""
    try:
        result = subprocess.run(
            ["gh"] + args + ["--json", "number,title,author,createdAt,updatedAt,state,isDraft,reviewDecision,headRefName,url,additions,deletions,changedFiles"],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            if "gh auth" in result.stderr or "authentication" in result.stderr.lower():
                logger.warning("GitHub authentication not configured — set GITHUB_TOKEN")
                return None
            logger.debug(f"gh command failed: {result.stderr[:200]}")
            return None
        return json.loads(result.stdout)
    except FileNotFoundError:
        logger.warning("gh CLI not found — install GitHub CLI")
        return None
    except subprocess.TimeoutExpired:
        logger.warning(f"gh command timed out after {timeout}s")
        return None
    except json.JSONDecodeError:
        return None


def run_pr_scanner() -> dict:
    """Scan configured repos for open PRs needing attention."""
    try:
        from services.project_context.project_registry import get_project_registry

        project_reg = get_project_registry()
        all_projects = project_reg.get_all_projects()

        # Collect repos from projects that have github_repo set
        repos = set()
        repo_to_project = {}
        for p in all_projects:
            if p.github_repo:
                repos.add(p.github_repo)
                repo_to_project[p.github_repo] = p.name

        # Also always scan the Agent007 repo
        repos.add("supportpals/Agent007")
        repo_to_project.setdefault("supportpals/Agent007", "Product & Technology")

        if not repos:
            return {
                "agent": "pr_scanner",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "items_processed": 0,
                "items_found": 0,
                "summary": "No repos configured with github_repo in project registry",
                "details": [],
                "error": None,
            }

        now = datetime.now(timezone.utc)
        all_prs = []
        repos_scanned = 0

        for repo in repos:
            prs = _run_gh(["pr", "list", "-R", repo, "--state", "open", "--limit", "20"])
            if prs is None:
                continue
            repos_scanned += 1

            project_name = repo_to_project.get(repo, repo)

            for pr in prs:
                created = pr.get("createdAt", "")
                updated = pr.get("updatedAt", "")

                # Parse dates
                age_hours = 0
                stale_hours = 0
                try:
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    age_hours = (now - created_dt).total_seconds() / 3600
                except Exception:
                    pass
                try:
                    updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    stale_hours = (now - updated_dt).total_seconds() / 3600
                except Exception:
                    pass

                review_decision = pr.get("reviewDecision", "") or ""
                needs_review = review_decision not in ("APPROVED", "CHANGES_REQUESTED")
                is_stale = stale_hours > 48

                author = pr.get("author", {})
                author_name = author.get("login", "unknown") if isinstance(author, dict) else str(author)

                all_prs.append({
                    "repo": repo,
                    "project": project_name,
                    "number": pr.get("number"),
                    "title": pr.get("title", ""),
                    "author": author_name,
                    "url": pr.get("url", ""),
                    "branch": pr.get("headRefName", ""),
                    "is_draft": pr.get("isDraft", False),
                    "review_status": review_decision.lower() if review_decision else "pending",
                    "needs_review": needs_review and not pr.get("isDraft", False),
                    "is_stale": is_stale,
                    "age_hours": round(age_hours, 1),
                    "stale_hours": round(stale_hours, 1),
                    "additions": pr.get("additions", 0),
                    "deletions": pr.get("deletions", 0),
                    "changed_files": pr.get("changedFiles", 0),
                })

        # Sort: needs_review first, then stale, then by age
        all_prs.sort(key=lambda x: (
            not x["needs_review"],
            not x["is_stale"],
            -x["age_hours"],
        ))

        needs_review_count = sum(1 for p in all_prs if p["needs_review"])
        stale_count = sum(1 for p in all_prs if p["is_stale"])

        summary_parts = [f"{len(all_prs)} open PRs across {repos_scanned} repos"]
        if needs_review_count:
            summary_parts.append(f"{needs_review_count} need review")
        if stale_count:
            summary_parts.append(f"{stale_count} stale (48h+ no activity)")

        return {
            "agent": "pr_scanner",
            "timestamp": now.isoformat(),
            "items_processed": repos_scanned,
            "items_found": len(all_prs),
            "summary": "; ".join(summary_parts),
            "details": all_prs,
            "error": None,
        }
    except Exception as e:
        logger.exception("PR scanner failed")
        return {
            "agent": "pr_scanner",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "items_processed": 0,
            "items_found": 0,
            "summary": f"Failed: {e}",
            "details": [],
            "error": str(e),
        }
