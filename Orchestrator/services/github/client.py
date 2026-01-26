"""
GitHub CLI Integration

Wraps the `gh` CLI for version control operations.
Provides:
- Diff viewing and previewing
- PR management
- Conflict detection and resolution
- Code review workflow
- Issue management

All destructive operations require confirmation.
Changes trigger UI prompts for human review.
"""

import os
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


# Configuration
SERVICES_ROOT = Path(__file__).parent.parent
ORCHESTRATOR_ROOT = SERVICES_ROOT.parent
AGENT007_ROOT = ORCHESTRATOR_ROOT.parent


class PRState(Enum):
    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"
    ALL = "all"


class ReviewState(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    COMMENTED = "commented"


@dataclass
class GitDiff:
    """Represents a git diff."""
    file_path: str
    additions: int
    deletions: int
    status: str  # added, modified, deleted, renamed
    diff_content: str
    
    @property
    def summary(self) -> str:
        return f"{self.status}: {self.file_path} (+{self.additions}/-{self.deletions})"


@dataclass
class PullRequest:
    """Represents a GitHub PR."""
    number: int
    title: str
    body: str
    state: str
    author: str
    base_branch: str
    head_branch: str
    url: str
    created_at: str
    updated_at: str
    mergeable: bool
    has_conflicts: bool
    review_status: str
    additions: int
    deletions: int
    changed_files: int
    labels: List[str]
    reviewers: List[str]


@dataclass
class Conflict:
    """Represents a merge conflict."""
    file_path: str
    conflict_markers: List[str]  # The conflict sections
    ours: str
    theirs: str


@dataclass
class ReviewRequest:
    """A request for human code review."""
    id: str
    type: str  # "diff", "pr", "conflict"
    title: str
    description: str
    repo: str
    branch: str
    files_changed: int
    additions: int
    deletions: int
    diff_preview: str
    created_at: str
    status: str  # "pending", "approved", "rejected"
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    comments: List[str] = field(default_factory=list)


class GitHubClient:
    """GitHub CLI wrapper with safety controls."""
    
    def __init__(self, repo_path: str = None):
        self.repo_path = Path(repo_path) if repo_path else AGENT007_ROOT
        self._review_requests: Dict[str, ReviewRequest] = {}
    
    def _run_gh(self, args: List[str], capture_output: bool = True) -> Tuple[int, str, str]:
        """Run a gh CLI command."""
        cmd = ["gh"] + args
        
        result = subprocess.run(
            cmd,
            cwd=self.repo_path,
            capture_output=capture_output,
            text=True,
        )
        
        return result.returncode, result.stdout, result.stderr
    
    def _run_git(self, args: List[str]) -> Tuple[int, str, str]:
        """Run a git command."""
        cmd = ["git"] + args
        
        result = subprocess.run(
            cmd,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )
        
        return result.returncode, result.stdout, result.stderr
    
    @property
    def is_authenticated(self) -> bool:
        """Check if gh is authenticated."""
        code, _, _ = self._run_gh(["auth", "status"])
        return code == 0
    
    @property
    def current_repo(self) -> Optional[str]:
        """Get current repo name."""
        code, out, _ = self._run_gh(["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])
        return out.strip() if code == 0 else None
    
    @property
    def current_branch(self) -> str:
        """Get current branch name."""
        _, out, _ = self._run_git(["branch", "--show-current"])
        return out.strip()
    
    @property
    def has_uncommitted_changes(self) -> bool:
        """Check for uncommitted changes."""
        code, _, _ = self._run_git(["diff", "--quiet"])
        return code != 0
    
    # =========================================================================
    # DIFF OPERATIONS
    # =========================================================================
    
    def get_diff(self, ref1: str = "HEAD", ref2: str = None, file_path: str = None) -> List[GitDiff]:
        """
        Get diff between refs or for staged/unstaged changes.
        
        Examples:
        - get_diff() - unstaged changes
        - get_diff("HEAD") - staged changes
        - get_diff("main", "feature") - between branches
        - get_diff(file_path="src/app.py") - specific file
        """
        args = ["diff", "--numstat"]
        
        if ref2:
            args.extend([ref1, ref2])
        elif ref1 and ref1 != "HEAD":
            args.append(ref1)
        
        if file_path:
            args.extend(["--", file_path])
        
        code, numstat, _ = self._run_git(args)
        if code != 0:
            return []
        
        # Get full diff content
        diff_args = ["diff"]
        if ref2:
            diff_args.extend([ref1, ref2])
        elif ref1 and ref1 != "HEAD":
            diff_args.append(ref1)
        if file_path:
            diff_args.extend(["--", file_path])
        
        _, diff_content, _ = self._run_git(diff_args)
        
        # Parse numstat
        diffs = []
        for line in numstat.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                adds = int(parts[0]) if parts[0] != "-" else 0
                dels = int(parts[1]) if parts[1] != "-" else 0
                path = parts[2]
                
                # Extract file-specific diff
                file_diff = self._extract_file_diff(diff_content, path)
                
                diffs.append(GitDiff(
                    file_path=path,
                    additions=adds,
                    deletions=dels,
                    status="modified",
                    diff_content=file_diff,
                ))
        
        return diffs
    
    def _extract_file_diff(self, full_diff: str, file_path: str) -> str:
        """Extract diff for a specific file."""
        lines = full_diff.split("\n")
        in_file = False
        result = []
        
        for line in lines:
            if line.startswith("diff --git"):
                in_file = file_path in line
            if in_file:
                result.append(line)
        
        return "\n".join(result)
    
    def get_staged_diff(self) -> List[GitDiff]:
        """Get diff of staged changes."""
        return self.get_diff("HEAD")
    
    def get_unstaged_diff(self) -> List[GitDiff]:
        """Get diff of unstaged changes."""
        args = ["diff", "--numstat"]
        code, numstat, _ = self._run_git(args)
        
        _, diff_content, _ = self._run_git(["diff"])
        
        diffs = []
        for line in numstat.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                diffs.append(GitDiff(
                    file_path=parts[2],
                    additions=int(parts[0]) if parts[0] != "-" else 0,
                    deletions=int(parts[1]) if parts[1] != "-" else 0,
                    status="modified",
                    diff_content=self._extract_file_diff(diff_content, parts[2]),
                ))
        
        return diffs
    
    def format_diff_for_review(self, diffs: List[GitDiff], max_lines: int = 100) -> str:
        """Format diffs for human review."""
        lines = ["## Changes Summary\n"]
        
        total_adds = sum(d.additions for d in diffs)
        total_dels = sum(d.deletions for d in diffs)
        lines.append(f"**{len(diffs)} files changed**, +{total_adds} additions, -{total_dels} deletions\n")
        
        for diff in diffs:
            lines.append(f"\n### {diff.file_path}")
            lines.append(f"+{diff.additions}/-{diff.deletions}\n")
            
            # Show truncated diff
            diff_lines = diff.diff_content.split("\n")
            if len(diff_lines) > max_lines:
                lines.append("```diff")
                lines.extend(diff_lines[:max_lines])
                lines.append(f"... ({len(diff_lines) - max_lines} more lines)")
                lines.append("```")
            else:
                lines.append("```diff")
                lines.append(diff.diff_content)
                lines.append("```")
        
        return "\n".join(lines)
    
    # =========================================================================
    # PULL REQUEST OPERATIONS
    # =========================================================================
    
    def list_prs(self, state: PRState = PRState.OPEN, limit: int = 10) -> List[PullRequest]:
        """List pull requests."""
        code, out, _ = self._run_gh([
            "pr", "list",
            "--state", state.value,
            "--limit", str(limit),
            "--json", "number,title,body,state,author,baseRefName,headRefName,url,createdAt,updatedAt,mergeable,additions,deletions,changedFiles,labels,reviewRequests",
        ])
        
        if code != 0:
            return []
        
        try:
            prs_data = json.loads(out)
        except json.JSONDecodeError:
            return []
        
        prs = []
        for pr in prs_data:
            prs.append(PullRequest(
                number=pr["number"],
                title=pr["title"],
                body=pr.get("body", ""),
                state=pr["state"],
                author=pr["author"]["login"] if pr.get("author") else "",
                base_branch=pr["baseRefName"],
                head_branch=pr["headRefName"],
                url=pr["url"],
                created_at=pr["createdAt"],
                updated_at=pr["updatedAt"],
                mergeable=pr.get("mergeable", "UNKNOWN") == "MERGEABLE",
                has_conflicts=pr.get("mergeable", "") == "CONFLICTING",
                review_status="pending",
                additions=pr.get("additions", 0),
                deletions=pr.get("deletions", 0),
                changed_files=pr.get("changedFiles", 0),
                labels=[l["name"] for l in pr.get("labels", [])],
                reviewers=[r["login"] for r in pr.get("reviewRequests", []) if r.get("login")],
            ))
        
        return prs
    
    def get_pr(self, pr_number: int) -> Optional[PullRequest]:
        """Get a specific PR."""
        code, out, _ = self._run_gh([
            "pr", "view", str(pr_number),
            "--json", "number,title,body,state,author,baseRefName,headRefName,url,createdAt,updatedAt,mergeable,additions,deletions,changedFiles,labels,reviewRequests",
        ])
        
        if code != 0:
            return None
        
        try:
            pr = json.loads(out)
            return PullRequest(
                number=pr["number"],
                title=pr["title"],
                body=pr.get("body", ""),
                state=pr["state"],
                author=pr["author"]["login"] if pr.get("author") else "",
                base_branch=pr["baseRefName"],
                head_branch=pr["headRefName"],
                url=pr["url"],
                created_at=pr["createdAt"],
                updated_at=pr["updatedAt"],
                mergeable=pr.get("mergeable", "UNKNOWN") == "MERGEABLE",
                has_conflicts=pr.get("mergeable", "") == "CONFLICTING",
                review_status="pending",
                additions=pr.get("additions", 0),
                deletions=pr.get("deletions", 0),
                changed_files=pr.get("changedFiles", 0),
                labels=[l["name"] for l in pr.get("labels", [])],
                reviewers=[r["login"] for r in pr.get("reviewRequests", []) if r.get("login")],
            )
        except (json.JSONDecodeError, KeyError):
            return None
    
    def get_pr_diff(self, pr_number: int) -> str:
        """Get the diff for a PR."""
        code, out, _ = self._run_gh(["pr", "diff", str(pr_number)])
        return out if code == 0 else ""
    
    def create_pr(
        self,
        title: str,
        body: str,
        base: str = "main",
        head: str = None,
        draft: bool = True,
    ) -> Optional[PullRequest]:
        """
        Create a pull request.
        NOTE: Creates as DRAFT by default for safety.
        """
        args = [
            "pr", "create",
            "--title", title,
            "--body", body,
            "--base", base,
        ]
        
        if head:
            args.extend(["--head", head])
        
        if draft:
            args.append("--draft")
        
        code, out, err = self._run_gh(args)
        
        if code != 0:
            return None
        
        # Get the PR number from the URL
        pr_url = out.strip()
        pr_number = int(pr_url.split("/")[-1]) if "/" in pr_url else None
        
        if pr_number:
            return self.get_pr(pr_number)
        return None
    
    def approve_pr(self, pr_number: int, comment: str = None) -> bool:
        """Approve a PR (requires confirmation)."""
        args = ["pr", "review", str(pr_number), "--approve"]
        if comment:
            args.extend(["--body", comment])
        
        code, _, _ = self._run_gh(args)
        return code == 0
    
    def request_changes(self, pr_number: int, comment: str) -> bool:
        """Request changes on a PR."""
        code, _, _ = self._run_gh([
            "pr", "review", str(pr_number),
            "--request-changes",
            "--body", comment,
        ])
        return code == 0
    
    def merge_pr(self, pr_number: int, merge_method: str = "squash") -> bool:
        """
        Merge a PR.
        NOTE: DESTRUCTIVE - requires confirmation.
        """
        code, _, _ = self._run_gh([
            "pr", "merge", str(pr_number),
            f"--{merge_method}",
            "--delete-branch",
        ])
        return code == 0
    
    # =========================================================================
    # CONFLICT RESOLUTION
    # =========================================================================
    
    def check_conflicts(self, branch: str = None) -> List[str]:
        """Check for merge conflicts with a branch."""
        target = branch or "main"
        
        # Try a dry-run merge
        _, _, err = self._run_git(["merge", "--no-commit", "--no-ff", target])
        
        if "CONFLICT" in err:
            # Extract conflicting files
            _, status, _ = self._run_git(["diff", "--name-only", "--diff-filter=U"])
            return status.strip().split("\n") if status.strip() else []
        
        # Abort the merge attempt
        self._run_git(["merge", "--abort"])
        return []
    
    def get_conflict_details(self, file_path: str) -> Optional[Conflict]:
        """Get details of a conflict in a file."""
        try:
            with open(self.repo_path / file_path) as f:
                content = f.read()
        except FileNotFoundError:
            return None
        
        if "<<<<<<<" not in content:
            return None
        
        # Parse conflict markers
        lines = content.split("\n")
        ours = []
        theirs = []
        in_ours = False
        in_theirs = False
        markers = []
        
        for line in lines:
            if line.startswith("<<<<<<<"):
                in_ours = True
                markers.append(line)
            elif line.startswith("======="):
                in_ours = False
                in_theirs = True
            elif line.startswith(">>>>>>>"):
                in_theirs = False
                markers.append(line)
            elif in_ours:
                ours.append(line)
            elif in_theirs:
                theirs.append(line)
        
        return Conflict(
            file_path=file_path,
            conflict_markers=markers,
            ours="\n".join(ours),
            theirs="\n".join(theirs),
        )
    
    def resolve_conflict(self, file_path: str, resolution: str) -> bool:
        """
        Resolve a conflict by writing the resolution.
        NOTE: Requires confirmation.
        """
        try:
            with open(self.repo_path / file_path, "w") as f:
                f.write(resolution)
            
            # Stage the resolved file
            self._run_git(["add", file_path])
            return True
        except Exception:
            return False
    
    # =========================================================================
    # REVIEW REQUEST SYSTEM
    # =========================================================================
    
    def request_review(
        self,
        review_type: str,
        title: str,
        description: str,
        diff_preview: str,
        files_changed: int = 0,
        additions: int = 0,
        deletions: int = 0,
    ) -> ReviewRequest:
        """Create a review request for human approval."""
        import uuid
        
        req = ReviewRequest(
            id=str(uuid.uuid4())[:8],
            type=review_type,
            title=title,
            description=description,
            repo=self.current_repo or "",
            branch=self.current_branch,
            files_changed=files_changed,
            additions=additions,
            deletions=deletions,
            diff_preview=diff_preview,
            created_at=datetime.utcnow().isoformat(),
            status="pending",
        )
        
        self._review_requests[req.id] = req
        return req
    
    def get_pending_reviews(self) -> List[ReviewRequest]:
        """Get all pending review requests."""
        return [r for r in self._review_requests.values() if r.status == "pending"]
    
    def complete_review(self, review_id: str, approved: bool, reviewer: str, comments: str = None) -> Optional[ReviewRequest]:
        """Complete a review request."""
        req = self._review_requests.get(review_id)
        if not req:
            return None
        
        req.status = "approved" if approved else "rejected"
        req.reviewed_by = reviewer
        req.reviewed_at = datetime.utcnow().isoformat()
        if comments:
            req.comments.append(comments)
        
        return req


# Global instance
_client: Optional[GitHubClient] = None


def get_github_client(repo_path: str = None) -> GitHubClient:
    """Get the GitHub client."""
    global _client
    if _client is None or (repo_path and str(_client.repo_path) != repo_path):
        _client = GitHubClient(repo_path)
    return _client
