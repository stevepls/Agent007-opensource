"""
GitHub Tools for CrewAI Agents

Provides access to GitHub via gh CLI.
All PR merges and destructive operations require confirmation.
Changes automatically trigger review requests in the UI.
"""

import sys
from pathlib import Path
from typing import List
from crewai.tools import BaseTool

TOOLS_ROOT = Path(__file__).parent
ORCHESTRATOR_ROOT = TOOLS_ROOT.parent
sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from governance.audit import get_audit_logger


class GitDiffTool(BaseTool):
    """View git diffs."""
    
    name: str = "git_diff"
    description: str = """View git diff for current changes or between refs.
    
    Input options:
    - "" (empty) - unstaged changes
    - "staged" - staged changes
    - "main..feature" - diff between branches
    - "HEAD~3" - last 3 commits
    - "path/to/file.py" - specific file"""
    
    def _run(self, ref: str = "") -> str:
        from services.github.client import get_github_client
        
        try:
            client = get_github_client()
            
            ref = ref.strip()
            
            if ref == "staged":
                diffs = client.get_staged_diff()
            elif ".." in ref:
                parts = ref.split("..")
                diffs = client.get_diff(parts[0], parts[1] if len(parts) > 1 else None)
            elif ref.startswith("HEAD"):
                diffs = client.get_diff(ref)
            elif ref and "/" in ref:
                # Assume it's a file path
                diffs = client.get_diff(file_path=ref)
            else:
                diffs = client.get_unstaged_diff()
            
            if not diffs:
                return "No changes found."
            
            return client.format_diff_for_review(diffs, max_lines=50)
            
        except Exception as e:
            return f"Error: {e}"


class GitStatusTool(BaseTool):
    """Check git status."""
    
    name: str = "git_status"
    description: str = """Check current git status.
    Input: none required (pass empty string)"""
    
    def _run(self, _: str = "") -> str:
        from services.github.client import get_github_client
        import subprocess
        
        try:
            client = get_github_client()
            
            result = subprocess.run(
                ["git", "status", "--short", "--branch"],
                cwd=client.repo_path,
                capture_output=True,
                text=True,
            )
            
            lines = [f"Repository: {client.current_repo or 'Unknown'}"]
            lines.append(f"Branch: {client.current_branch}")
            lines.append(f"Has uncommitted changes: {client.has_uncommitted_changes}")
            lines.append("")
            lines.append("Status:")
            lines.append(result.stdout if result.returncode == 0 else "Error getting status")
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Error: {e}"


class ListPRsTool(BaseTool):
    """List pull requests."""
    
    name: str = "list_prs"
    description: str = """List pull requests in the repository.
    Input: state filter - "open" (default), "closed", "merged", or "all" """
    
    def _run(self, state: str = "open") -> str:
        from services.github.client import get_github_client, PRState
        
        try:
            client = get_github_client()
            
            try:
                pr_state = PRState(state.lower().strip() or "open")
            except ValueError:
                pr_state = PRState.OPEN
            
            prs = client.list_prs(state=pr_state, limit=10)
            
            if not prs:
                return f"No {pr_state.value} pull requests found."
            
            lines = [f"Pull Requests ({pr_state.value}):\n"]
            for pr in prs:
                status = "⚠️" if pr.has_conflicts else "✓" if pr.mergeable else "?"
                lines.append(
                    f"{status} #{pr.number}: {pr.title}\n"
                    f"   {pr.head_branch} → {pr.base_branch} | "
                    f"+{pr.additions}/-{pr.deletions} ({pr.changed_files} files)\n"
                    f"   By: {pr.author} | {pr.url}"
                )
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Error: {e}"


class ViewPRTool(BaseTool):
    """View a specific pull request."""
    
    name: str = "view_pr"
    description: str = """View details of a pull request including diff.
    Input: PR number (e.g., "42")"""
    
    def _run(self, pr_number: str) -> str:
        from services.github.client import get_github_client
        
        if not pr_number:
            return "Please provide a PR number."
        
        try:
            pr_num = int(pr_number.strip().lstrip("#"))
        except ValueError:
            return f"Invalid PR number: {pr_number}"
        
        try:
            client = get_github_client()
            
            pr = client.get_pr(pr_num)
            if not pr:
                return f"PR #{pr_num} not found."
            
            # Get diff
            diff = client.get_pr_diff(pr_num)
            diff_preview = diff[:2000] + "\n... (truncated)" if len(diff) > 2000 else diff
            
            return (
                f"# PR #{pr.number}: {pr.title}\n\n"
                f"**State:** {pr.state}\n"
                f"**Author:** {pr.author}\n"
                f"**Branches:** {pr.head_branch} → {pr.base_branch}\n"
                f"**Mergeable:** {'Yes' if pr.mergeable else 'No' if pr.has_conflicts else 'Unknown'}\n"
                f"**Changes:** +{pr.additions}/-{pr.deletions} ({pr.changed_files} files)\n"
                f"**Labels:** {', '.join(pr.labels) if pr.labels else 'None'}\n"
                f"**URL:** {pr.url}\n\n"
                f"## Description\n{pr.body or 'No description'}\n\n"
                f"## Diff Preview\n```diff\n{diff_preview}\n```"
            )
            
        except Exception as e:
            return f"Error: {e}"


class CreatePRTool(BaseTool):
    """Create a pull request."""
    
    name: str = "create_pr"
    description: str = """Create a pull request (as draft by default for safety).
    
    Input format: JSON with fields:
    - title: PR title (REQUIRED)
    - body: PR description (REQUIRED)
    - base: target branch (default: "main")
    - head: source branch (default: current branch)
    - draft: create as draft (default: true)
    
    Example: {"title": "Add feature X", "body": "This PR adds feature X", "base": "main"}"""
    
    def _run(self, input_json: str) -> str:
        import json
        from services.github.client import get_github_client
        
        try:
            data = json.loads(input_json)
        except json.JSONDecodeError:
            return "Invalid JSON input."
        
        title = data.get("title")
        body = data.get("body", "")
        
        if not title:
            return "Missing required field: title"
        
        try:
            client = get_github_client()
            
            pr = client.create_pr(
                title=title,
                body=body,
                base=data.get("base", "main"),
                head=data.get("head"),
                draft=data.get("draft", True),
            )
            
            if pr:
                get_audit_logger().log_tool_use(
                    agent="github",
                    tool="create_pr",
                    input_data={"title": title},
                    output_data={"pr_number": pr.number},
                )
                
                return (
                    f"✓ Pull request created!\n\n"
                    f"**#{pr.number}:** {pr.title}\n"
                    f"**Branch:** {pr.head_branch} → {pr.base_branch}\n"
                    f"**Draft:** Yes\n"
                    f"**URL:** {pr.url}\n\n"
                    "Ready to mark as ready-for-review when complete."
                )
            else:
                return "Failed to create PR. Check if branch has commits ahead of base."
                
        except Exception as e:
            return f"Error: {e}"


class RequestReviewTool(BaseTool):
    """Request human review of changes."""
    
    name: str = "request_code_review"
    description: str = """Request human review of current changes or a PR.
    This creates a review request visible in the UI.
    
    Input options:
    - "current" or "" - review current uncommitted changes
    - PR number (e.g., "42") - review a specific PR
    - "staged" - review staged changes"""
    
    def _run(self, target: str = "current") -> str:
        from services.github.client import get_github_client
        
        try:
            client = get_github_client()
            target = target.strip().lower() or "current"
            
            if target == "current" or target == "unstaged":
                diffs = client.get_unstaged_diff()
                review_type = "unstaged_changes"
                title = "Review: Unstaged Changes"
                description = "Please review these uncommitted changes before staging."
            elif target == "staged":
                diffs = client.get_staged_diff()
                review_type = "staged_changes"
                title = "Review: Staged Changes"
                description = "Please review these staged changes before committing."
            else:
                # Assume PR number
                try:
                    pr_num = int(target.lstrip("#"))
                    pr = client.get_pr(pr_num)
                    if not pr:
                        return f"PR #{pr_num} not found."
                    
                    diff_content = client.get_pr_diff(pr_num)
                    
                    review = client.request_review(
                        review_type="pull_request",
                        title=f"Review PR #{pr.number}: {pr.title}",
                        description=pr.body or "No description",
                        diff_preview=diff_content[:3000],
                        files_changed=pr.changed_files,
                        additions=pr.additions,
                        deletions=pr.deletions,
                    )
                    
                    return (
                        f"✓ Review requested!\n\n"
                        f"**Review ID:** {review.id}\n"
                        f"**Type:** Pull Request\n"
                        f"**PR:** #{pr.number} - {pr.title}\n"
                        f"**Changes:** +{pr.additions}/-{pr.deletions} ({pr.changed_files} files)\n\n"
                        "Check the UI to complete the review."
                    )
                except ValueError:
                    return f"Invalid target: {target}. Use 'current', 'staged', or a PR number."
            
            if not diffs:
                return f"No {target} changes to review."
            
            formatted = client.format_diff_for_review(diffs, max_lines=30)
            total_adds = sum(d.additions for d in diffs)
            total_dels = sum(d.deletions for d in diffs)
            
            review = client.request_review(
                review_type=review_type,
                title=title,
                description=description,
                diff_preview=formatted,
                files_changed=len(diffs),
                additions=total_adds,
                deletions=total_dels,
            )
            
            return (
                f"✓ Review requested!\n\n"
                f"**Review ID:** {review.id}\n"
                f"**Type:** {review_type}\n"
                f"**Files:** {len(diffs)}\n"
                f"**Changes:** +{total_adds}/-{total_dels}\n\n"
                "Check the UI to complete the review."
            )
            
        except Exception as e:
            return f"Error: {e}"


class CheckConflictsTool(BaseTool):
    """Check for merge conflicts."""
    
    name: str = "check_conflicts"
    description: str = """Check if current branch has conflicts with another branch.
    Input: target branch to check against (default: "main")"""
    
    def _run(self, target_branch: str = "main") -> str:
        from services.github.client import get_github_client
        
        try:
            client = get_github_client()
            
            conflicts = client.check_conflicts(target_branch.strip() or "main")
            
            if not conflicts:
                return f"✓ No conflicts with {target_branch}. Safe to merge."
            
            lines = [f"⚠️ Found {len(conflicts)} conflicting file(s):\n"]
            for file_path in conflicts:
                lines.append(f"  • {file_path}")
                
                # Get conflict details
                conflict = client.get_conflict_details(file_path)
                if conflict:
                    lines.append(f"    Ours: {len(conflict.ours.split(chr(10)))} lines")
                    lines.append(f"    Theirs: {len(conflict.theirs.split(chr(10)))} lines")
            
            lines.append("\nUse 'view_conflict' to see details of each conflict.")
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Error: {e}"


class ViewConflictTool(BaseTool):
    """View details of a specific conflict."""
    
    name: str = "view_conflict"
    description: str = """View the conflict markers and content for a conflicting file.
    Input: path to the conflicting file"""
    
    def _run(self, file_path: str) -> str:
        from services.github.client import get_github_client
        
        if not file_path:
            return "Please provide a file path."
        
        try:
            client = get_github_client()
            
            conflict = client.get_conflict_details(file_path.strip())
            
            if not conflict:
                return f"No conflict found in {file_path}."
            
            return (
                f"# Conflict in {conflict.file_path}\n\n"
                f"## Our Version (current branch)\n```\n{conflict.ours}\n```\n\n"
                f"## Their Version (incoming)\n```\n{conflict.theirs}\n```\n\n"
                "To resolve, choose which version to keep or combine them manually."
            )
            
        except Exception as e:
            return f"Error: {e}"


class MergePRTool(BaseTool):
    """Merge a pull request (requires confirmation)."""
    
    name: str = "merge_pr"
    description: str = """Queue a PR merge for approval.
    This is a DESTRUCTIVE operation - requires human confirmation.
    
    Input format: JSON with fields:
    - pr_number: PR number to merge (REQUIRED)
    - method: "squash" (default), "merge", or "rebase"
    
    Example: {"pr_number": 42, "method": "squash"}"""
    
    def _run(self, input_json: str) -> str:
        import json
        from services.message_queue import get_message_queue, MessageType
        from governance.confirmations import (
            get_confirmation_manager,
            OperationType,
            ConfirmationLevel,
        )
        
        try:
            data = json.loads(input_json)
        except json.JSONDecodeError:
            return "Invalid JSON input."
        
        pr_number = data.get("pr_number")
        if not pr_number:
            return "Missing required field: pr_number"
        
        method = data.get("method", "squash")
        if method not in ("squash", "merge", "rebase"):
            return f"Invalid merge method: {method}"
        
        from services.github.client import get_github_client
        
        try:
            client = get_github_client()
            
            pr = client.get_pr(int(pr_number))
            if not pr:
                return f"PR #{pr_number} not found."
            
            if pr.has_conflicts:
                return f"❌ PR #{pr_number} has conflicts. Resolve before merging."
            
            # Request confirmation
            confirm_mgr = get_confirmation_manager()
            req = confirm_mgr.request(
                operation=OperationType.MODIFY_PRODUCTION,
                title=f"Merge PR #{pr.number}",
                description=f"Merge '{pr.title}' into {pr.base_branch}",
                details={
                    "pr_number": pr.number,
                    "title": pr.title,
                    "method": method,
                    "base": pr.base_branch,
                    "head": pr.head_branch,
                    "additions": pr.additions,
                    "deletions": pr.deletions,
                },
                impact=f"This will merge {pr.changed_files} files (+{pr.additions}/-{pr.deletions}) into {pr.base_branch}",
                level=ConfirmationLevel.ELEVATED,
            )
            
            get_audit_logger().log_tool_use(
                agent="github",
                tool="merge_pr",
                input_data={"pr_number": pr_number, "method": method},
                output_data={"confirmation_id": req.id},
            )
            
            return (
                f"⚠️ Merge queued for approval\n\n"
                f"**Confirmation ID:** {req.id}\n"
                f"**PR:** #{pr.number} - {pr.title}\n"
                f"**Method:** {method}\n"
                f"**Target:** {pr.base_branch}\n"
                f"**Impact:** {pr.changed_files} files, +{pr.additions}/-{pr.deletions}\n\n"
                "A human must approve this merge in the UI."
            )
            
        except Exception as e:
            return f"Error: {e}"


def get_github_tools() -> List[BaseTool]:
    """Get all GitHub tools for CrewAI agents."""
    return [
        GitStatusTool(),
        GitDiffTool(),
        ListPRsTool(),
        ViewPRTool(),
        CreatePRTool(),
        RequestReviewTool(),
        CheckConflictsTool(),
        ViewConflictTool(),
        MergePRTool(),
    ]
