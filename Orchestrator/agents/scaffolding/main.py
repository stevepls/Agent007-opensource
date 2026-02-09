#!/usr/bin/env python3
"""
Scaffolding Agent - CLI Entry Point

Usage:
    # Run once for a specific project
    python -m agents.scaffolding.main --project phyto

    # Run once for all configured projects
    python -m agents.scaffolding.main --all

    # Run as a scheduler (every 15 minutes)
    python -m agents.scaffolding.main --schedule --interval 900

    # Dry run (list tasks without processing)
    python -m agents.scaffolding.main --project phyto --dry-run

    # List configured projects
    python -m agents.scaffolding.main --list-projects
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from datetime import datetime

# Add parent paths
AGENT_ROOT = Path(__file__).parent
ORCHESTRATOR_ROOT = AGENT_ROOT.parent.parent
sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from agents.scaffolding.agent import ScaffoldingAgent, ScaffoldingConfig
from agents.scaffolding.config import PROJECT_CONFIGS


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("scaffolding.main")


def run_project(project_key: str, dry_run: bool = False) -> dict:
    """Run scaffolding agent for a single project."""
    logger.info(f"Starting scaffolding for: {project_key}")

    try:
        config = ScaffoldingConfig.from_project_key(project_key)
    except ValueError as e:
        logger.error(str(e))
        return {"project": project_key, "status": "error", "error": str(e)}

    agent = ScaffoldingAgent(config)

    if dry_run:
        # Just list pending tasks
        logger.info("DRY RUN - listing pending tasks only")
        try:
            tasks = agent.fetch_pending_tasks()
            task_list = []
            for t in tasks:
                task_list.append({
                    "id": t.id,
                    "name": t.name,
                    "status": t.status,
                    "priority": t.priority_name,
                    "url": t.url,
                })
                logger.info(f"  [{t.id}] {t.name} (priority: {t.priority_name})")

            return {
                "project": project_key,
                "status": "dry_run",
                "tasks_found": len(tasks),
                "tasks": task_list,
            }
        except Exception as e:
            logger.error(f"Error fetching tasks: {e}")
            return {"project": project_key, "status": "error", "error": str(e)}

    # Run the agent
    results = agent.run()

    return {
        "project": project_key,
        "status": "completed",
        "results": [
            {
                "task_id": r.task_id,
                "task_name": r.task_name,
                "status": r.status,
                "branch": r.branch_name,
                "branch_url": r.branch_url,
                "comment": r.comment,
                "error": r.error,
            }
            for r in results
        ],
        "summary": {
            "total": len(results),
            "completed": sum(1 for r in results if r.status == "completed"),
            "blocked": sum(1 for r in results if r.status == "blocked"),
            "errors": sum(1 for r in results if r.status == "error"),
        },
    }


def run_all_projects(dry_run: bool = False) -> list:
    """Run scaffolding for all configured projects."""
    results = []
    for project_key in PROJECT_CONFIGS:
        result = run_project(project_key, dry_run=dry_run)
        results.append(result)
    return results


def run_scheduler(interval: int = 900, projects: list = None):
    """Run as a scheduler, executing every `interval` seconds."""
    target_projects = projects or list(PROJECT_CONFIGS.keys())
    logger.info(f"Starting scheduler: interval={interval}s, projects={target_projects}")

    while True:
        start = time.time()
        logger.info(f"=== Scheduler run at {datetime.now().isoformat()} ===")

        for project_key in target_projects:
            try:
                result = run_project(project_key)
                summary = result.get("summary", {})
                logger.info(
                    f"  {project_key}: {summary.get('completed', 0)} completed, "
                    f"{summary.get('blocked', 0)} blocked, "
                    f"{summary.get('errors', 0)} errors"
                )
            except Exception as e:
                logger.error(f"  {project_key}: {e}")

        elapsed = time.time() - start
        sleep_time = max(0, interval - elapsed)
        logger.info(f"=== Run completed in {elapsed:.1f}s. Sleeping {sleep_time:.0f}s ===")
        time.sleep(sleep_time)


def list_projects():
    """List all configured projects."""
    print("\nConfigured Projects:")
    print("=" * 60)
    for key, cfg in PROJECT_CONFIGS.items():
        print(f"\n  {key}:")
        print(f"    Name:       {cfg['name']}")
        print(f"    GitHub:     {cfg['github_repo']}")
        print(f"    ClickUp:    list/{cfg['clickup_list_id']}")
        print(f"    Local Path: {cfg.get('local_path', 'N/A')}")
        print(f"    Stack:      {', '.join(cfg.get('stack', []))}")
        print(f"    Pending:    '{cfg.get('status_pending', 'pending ai scaffolding')}'")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Project Task Scaffolding Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --project phyto              # Run for Phyto project
  %(prog)s --project phyto --dry-run    # Preview pending tasks
  %(prog)s --all                        # Run for all projects
  %(prog)s --schedule --interval 900    # Run every 15 minutes
  %(prog)s --list-projects              # Show configured projects
        """,
    )

    parser.add_argument(
        "--project", "-p",
        help="Project key to run scaffolding for",
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Run for all configured projects",
    )
    parser.add_argument(
        "--schedule", "-s",
        action="store_true",
        help="Run as a scheduler (loop mode)",
    )
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=900,
        help="Scheduler interval in seconds (default: 900 = 15 minutes)",
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="List pending tasks without processing",
    )
    parser.add_argument(
        "--list-projects", "-l",
        action="store_true",
        help="List all configured projects",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    if args.list_projects:
        list_projects()
        return

    if args.schedule:
        projects = [args.project] if args.project else None
        run_scheduler(interval=args.interval, projects=projects)
        return

    if args.project:
        result = run_project(args.project, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            _print_result(result)
        return

    if args.all:
        results = run_all_projects(dry_run=args.dry_run)
        if args.json:
            print(json.dumps(results, indent=2, default=str))
        else:
            for result in results:
                _print_result(result)
        return

    parser.print_help()


def _print_result(result: dict):
    """Print a result in human-readable format."""
    project = result.get("project", "?")
    status = result.get("status", "?")

    print(f"\n{'=' * 60}")
    print(f"Project: {project}")
    print(f"Status:  {status}")

    if status == "error":
        print(f"Error:   {result.get('error', 'Unknown')}")
        return

    if status == "dry_run":
        print(f"Pending: {result.get('tasks_found', 0)} task(s)")
        for t in result.get("tasks", []):
            print(f"  [{t['id']}] {t['name']} ({t.get('priority', '?')})")
        return

    summary = result.get("summary", {})
    print(f"Total:   {summary.get('total', 0)}")
    print(f"  ✅ Completed: {summary.get('completed', 0)}")
    print(f"  🚧 Blocked:   {summary.get('blocked', 0)}")
    print(f"  ❌ Errors:     {summary.get('errors', 0)}")

    for r in result.get("results", []):
        icon = {"completed": "✅", "blocked": "🚧", "error": "❌", "skipped": "⏭️"}.get(r["status"], "?")
        print(f"\n  {icon} [{r['task_id']}] {r['task_name']}")
        if r.get("branch"):
            print(f"     Branch: {r['branch']}")
        if r.get("branch_url"):
            print(f"     URL:    {r['branch_url']}")
        if r.get("error"):
            print(f"     Error:  {r['error']}")
        if r.get("comment"):
            print(f"     Note:   {r['comment']}")


if __name__ == "__main__":
    main()
