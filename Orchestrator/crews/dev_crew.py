"""
Development Crew with Governance Integration

A reliable crew for software development tasks:
- Manager: Plans and coordinates
- Coder: Writes code
- Reviewer: Reviews code

GOVERNANCE FEATURES:
- Pre-validation: Tasks are validated against policies before execution
- Audit logging: All actions are logged for traceability
- Cost tracking: Token usage is monitored with budget limits
- Post-validation: Outputs are checked for policy violations
- Human approval: Required for sensitive operations
"""

import sys
from pathlib import Path
from crewai import Crew, Task, Process
from typing import Optional, Dict, Any
from datetime import datetime

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents import (
    create_manager_agent,
    create_coder_agent,
    create_reviewer_agent,
    create_critic_agent,
    run_self_critique,
    REQUIRE_APPROVAL
)
from tools import get_file_tools, get_claude_cli_tools, ClaudeCLIConfig
from governance.validators import (
    validate_before_execution,
    validate_after_execution,
    ValidationStatus,
)
from governance.audit import (
    get_audit_logger,
    AuditEvent,
    ActionType,
)
from governance.cost_tracker import (
    get_cost_tracker,
    TokenUsage,
    BudgetExceededError,
    CircuitBreakerOpenError,
)


def create_dev_crew(verbose: bool = True) -> Crew:
    """
    Create a development crew with Manager, Coder, and Reviewer.
    
    Returns a configured Crew ready to execute tasks.
    """
    # Get tools
    file_tools = get_file_tools()
    
    # Create agents
    manager = create_manager_agent()
    coder = create_coder_agent(tools=file_tools)
    reviewer = create_reviewer_agent(tools=file_tools)
    
    # Create crew with hierarchical process
    crew = Crew(
        agents=[manager, coder, reviewer],
        tasks=[],  # Tasks added dynamically
        process=Process.hierarchical,
        manager_agent=manager,
        verbose=verbose,
    )
    
    return crew


def run_dev_task(
    task_description: str,
    context: Optional[str] = None,
    require_review: bool = True,
    dry_run: bool = False,
    use_claude_cli: bool = True,  # Use Claude CLI for file ops (hybrid mode)
) -> Dict[str, Any]:
    """
    Run a development task through the crew with full governance.
    
    Args:
        task_description: What needs to be done
        context: Additional context (existing code, requirements, etc.)
        require_review: Whether to run the Reviewer after Coder
        dry_run: If True, validate but don't execute (for testing governance)
    
    Returns:
        dict with 'result', 'validation', 'audit_summary', 'cost_summary', 'needs_approval'
    """
    # Initialize governance components
    logger = get_audit_logger()
    cost_tracker = get_cost_tracker()
    
    # Log task start
    logger.log(AuditEvent(
        action_type=ActionType.TASK_START,
        description=f"Task started: {task_description[:100]}...",
        input_data={"task": task_description, "context": context[:200] if context else None},
    ))
    
    # ==========================================================================
    # PHASE 1: PRE-VALIDATION
    # ==========================================================================
    
    pre_validation = validate_before_execution(task=task_description)
    logger.log_validation("PreValidator", pre_validation.to_dict(), context="task_description")
    
    if pre_validation.is_blocked:
        logger.log(AuditEvent(
            action_type=ActionType.TASK_FAILED,
            description="Task blocked by pre-validation",
            policy_violations=[i.code for i in pre_validation.issues],
        ))
        return {
            "result": None,
            "status": "blocked",
            "validation": pre_validation.to_dict(),
            "reason": "Task blocked by security policy",
            "issues": [i.message for i in pre_validation.issues],
            "audit_summary": logger.get_session_summary(),
            "cost_summary": cost_tracker.get_summary(),
            "needs_approval": False,
        }
    
    if pre_validation.requires_escalation:
        logger.log_escalation(
            agent="PreValidator",
            reason="Task requires human approval before execution",
            context={"issues": [i.to_dict() if hasattr(i, 'to_dict') else str(i) for i in pre_validation.issues]},
        )
        return {
            "result": None,
            "status": "escalated",
            "validation": pre_validation.to_dict(),
            "reason": "Task requires human approval",
            "issues": [i.message for i in pre_validation.issues],
            "audit_summary": logger.get_session_summary(),
            "cost_summary": cost_tracker.get_summary(),
            "needs_approval": True,
            "approval_prompt": "This task involves sensitive operations. Please review and approve to continue.",
        }
    
    # ==========================================================================
    # PHASE 2: DRY RUN CHECK
    # ==========================================================================
    
    if dry_run:
        logger.log(AuditEvent(
            action_type=ActionType.TASK_COMPLETE,
            description="Dry run completed - task would be executed",
        ))
        return {
            "result": None,
            "status": "dry_run",
            "validation": pre_validation.to_dict(),
            "reason": "Dry run mode - task validated but not executed",
            "audit_summary": logger.get_session_summary(),
            "cost_summary": cost_tracker.get_summary(),
            "needs_approval": pre_validation.has_warnings,
        }
    
    # ==========================================================================
    # PHASE 3: BUDGET CHECK
    # ==========================================================================
    
    can_proceed, budget_reason = cost_tracker.can_proceed()
    if not can_proceed:
        logger.log(AuditEvent(
            action_type=ActionType.TASK_FAILED,
            description=f"Task blocked by budget: {budget_reason}",
        ))
        return {
            "result": None,
            "status": "budget_exceeded",
            "reason": budget_reason,
            "audit_summary": logger.get_session_summary(),
            "cost_summary": cost_tracker.get_summary(),
            "needs_approval": False,
        }
    
    # ==========================================================================
    # PHASE 4: AGENT EXECUTION
    # ==========================================================================
    
    # Choose tools based on mode
    if use_claude_cli:
        # Hybrid mode: Claude CLI for file operations
        coder_tools = get_claude_cli_tools(ClaudeCLIConfig(
            model="sonnet",
            max_budget_usd=2.0,
        ))
        reviewer_tools = get_file_tools()  # Reviewer uses direct read for inspection
        logger.log(AuditEvent(
            action_type=ActionType.TASK_START,
            description="Using HYBRID mode: Claude CLI for execution",
        ))
    else:
        # Direct mode: Python file tools
        coder_tools = get_file_tools()
        reviewer_tools = get_file_tools()
        logger.log(AuditEvent(
            action_type=ActionType.TASK_START,
            description="Using DIRECT mode: Python file tools",
        ))
    
    # Create agents
    manager = create_manager_agent()
    coder = create_coder_agent(tools=coder_tools)
    reviewer = create_reviewer_agent(tools=reviewer_tools)
    
    # Build task list
    tasks = []
    
    # Task 1: Manager plans the approach
    plan_task = Task(
        description=f"""Analyze this task and create a clear plan:

TASK: {task_description}

{f'CONTEXT: {context}' if context else ''}

Your output should be:
1. What files need to be created or modified
2. Step-by-step implementation plan
3. Any questions or concerns (if something is unclear, ask)
4. Whether this needs human approval before proceeding
5. Your confidence level [CONFIDENCE: XX%]

DO NOT write any code. Just plan.

Remember: You MUST escalate if:
- Confidence < 80%
- Task involves production, money, legal, or security
- Requirements are unclear""",
        expected_output="A clear implementation plan with files to modify, steps to take, and confidence level",
        agent=manager
    )
    tasks.append(plan_task)
    
    # Task 2: Coder implements
    tools_instruction = """Use the claude_cli tool to execute file operations. This delegates to Claude Code CLI which has native file editing capabilities.""" if use_claude_cli else """Use the file tools (read_file, write_file) to read and modify files."""
    
    code_task = Task(
        description=f"""Implement the plan from the previous task.

ORIGINAL TASK: {task_description}

{f'CONTEXT: {context}' if context else ''}

TOOLS: {tools_instruction}

RULES (enforced by governance):
1. Write complete, working code - no placeholders (TODO, FIXME, ...)
2. Follow existing patterns in the codebase
3. Include proper error handling
4. NEVER hardcode secrets - use environment variables
5. NEVER write to .env, secrets/, or production paths
6. Use the tools to read existing files first
7. Use the appropriate tool to create/update files

At the end, report:
- [FILES_MODIFIED: file1.py, file2.py, ...]
- [CONFIDENCE: XX%]""",
        expected_output="Complete implementation with all files created/modified and confidence level",
        agent=coder,
        context=[plan_task]
    )
    tasks.append(code_task)
    
    # Task 3: Reviewer checks the work
    if require_review:
        review_task = Task(
            description=f"""Review the code written in the previous task.

ORIGINAL TASK: {task_description}

Use the read_file tool to examine the files that were created/modified.

MANDATORY CHECKS:
1. Security: No hardcoded secrets, SQL injection, XSS, path traversal
2. Quality: No placeholders (TODO, FIXME, ...), complete error handling
3. Production safety: No writes to production paths or .env files
4. Code patterns: Matches existing codebase style

Output your review in the standard format:
### Severity Summary
X Critical, Y High, Z Medium, W Low

### Issues
(tables for each severity level)

### Security Checklist
- [ ] No hardcoded secrets
- [ ] No SQL injection risks
- [ ] No XSS vulnerabilities
- [ ] No path traversal risks
- [ ] No writes to sensitive paths

### Verdict
APPROVE / NEEDS_CHANGES / REJECT

[CONFIDENCE: XX%]""",
            expected_output="Detailed code review with security checklist, verdict, and confidence level",
            agent=reviewer,
            context=[code_task]
        )
        tasks.append(review_task)
    
    # Execute crew
    try:
        start_time = datetime.utcnow()
        
        crew = Crew(
            agents=[manager, coder, reviewer] if require_review else [manager, coder],
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
        )
        
        result = crew.kickoff()
        
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        # Log agent execution
        logger.log_agent_call(
            agent="dev_crew",
            task=task_description[:200],
            response=str(result)[:500],
            duration_ms=duration_ms,
        )
        
    except BudgetExceededError as e:
        logger.log(AuditEvent(
            action_type=ActionType.TASK_FAILED,
            description=f"Budget exceeded during execution: {e}",
        ))
        cost_tracker.record_failure(str(e))
        return {
            "result": None,
            "status": "budget_exceeded",
            "reason": str(e),
            "audit_summary": logger.get_session_summary(),
            "cost_summary": cost_tracker.get_summary(),
            "needs_approval": False,
        }
    except CircuitBreakerOpenError as e:
        logger.log(AuditEvent(
            action_type=ActionType.TASK_FAILED,
            description=f"Circuit breaker tripped: {e}",
        ))
        return {
            "result": None,
            "status": "circuit_breaker",
            "reason": str(e),
            "audit_summary": logger.get_session_summary(),
            "cost_summary": cost_tracker.get_summary(),
            "needs_approval": False,
        }
    except Exception as e:
        cost_tracker.record_failure(str(e))
        logger.log(AuditEvent(
            action_type=ActionType.TASK_FAILED,
            description=f"Execution error: {e}",
        ))
        return {
            "result": None,
            "status": "error",
            "reason": str(e),
            "audit_summary": logger.get_session_summary(),
            "cost_summary": cost_tracker.get_summary(),
            "needs_approval": False,
        }
    
    # ==========================================================================
    # PHASE 5: POST-VALIDATION
    # ==========================================================================
    
    result_str = str(result)
    post_validation = validate_after_execution(response=result_str)
    logger.log_validation("PostValidator", post_validation.to_dict(), context="agent_response")
    
    # Check for REJECT verdict in review
    if require_review and "REJECT" in result_str.upper():
        logger.log(AuditEvent(
            action_type=ActionType.TASK_FAILED,
            description="Code review resulted in REJECT",
        ))
        return {
            "result": result_str,
            "status": "rejected",
            "reason": "Code review resulted in REJECT - requires fixes",
            "validation": post_validation.to_dict(),
            "audit_summary": logger.get_session_summary(),
            "cost_summary": cost_tracker.get_summary(),
            "needs_approval": False,
        }
    
    # ==========================================================================
    # PHASE 5.5: SELF-CRITIQUE (Constitutional AI-style)
    # ==========================================================================
    
    # Extract files modified from result (heuristic)
    files_modified = []
    if "FILES_MODIFIED:" in result_str:
        fm_section = result_str.split("FILES_MODIFIED:")[1].split("\n")[0]
        files_modified = [f.strip() for f in fm_section.replace("[", "").replace("]", "").split(",") if f.strip()]
    
    # Run self-critique
    try:
        critique_result = run_self_critique(
            agent_output=result_str,
            original_task=task_description,
            files_modified=files_modified if files_modified else None,
            file_tools=reviewer_tools,  # Use read-only tools for verification
        )
        
        logger.log(AuditEvent(
            action_type=ActionType.VALIDATION_CHECK,
            agent="critic",
            description=f"Self-critique verdict: {critique_result.get('verdict', 'UNKNOWN')}",
            metadata={"critique": critique_result},
        ))
        
        # Handle critique verdict
        if critique_result.get("verdict") == "FAIL":
            logger.log(AuditEvent(
                action_type=ActionType.TASK_FAILED,
                description=f"Self-critique FAILED: {critique_result.get('violations', [])}",
                policy_violations=[v.get('type', 'UNKNOWN') for v in critique_result.get('violations', [])],
            ))
            return {
                "result": result_str,
                "status": "critique_failed",
                "reason": "Self-critique failed - policy violations detected",
                "critique": critique_result,
                "validation": {
                    "pre": pre_validation.to_dict(),
                    "post": post_validation.to_dict(),
                },
                "audit_summary": logger.get_session_summary(),
                "cost_summary": cost_tracker.get_summary(),
                "needs_approval": False,
            }
        
        if critique_result.get("verdict") == "ESCALATE":
            logger.log_escalation(
                agent="critic",
                reason="Self-critique requires human review",
                context={"critique": critique_result},
            )
            return {
                "result": result_str,
                "status": "escalated",
                "reason": critique_result.get("escalation_reason", "Self-critique requires human review"),
                "critique": critique_result,
                "validation": {
                    "pre": pre_validation.to_dict(),
                    "post": post_validation.to_dict(),
                },
                "audit_summary": logger.get_session_summary(),
                "cost_summary": cost_tracker.get_summary(),
                "needs_approval": True,
                "approval_prompt": "Self-critique flagged this task for human review. Please verify the output is safe and complete.",
            }
    
    except Exception as e:
        # Log critique failure but don't block - escalate instead
        logger.log(AuditEvent(
            action_type=ActionType.VALIDATION_CHECK,
            agent="critic",
            description=f"Self-critique failed to run: {e}",
        ))
        # Continue without critique - escalate for safety
        logger.log_escalation(
            agent="critic",
            reason=f"Self-critique failed to run: {e}",
        )
    
    # ==========================================================================
    # PHASE 6: APPROVAL GATE
    # ==========================================================================
    
    needs_approval = REQUIRE_APPROVAL or post_validation.has_warnings or pre_validation.has_warnings
    
    logger.log(AuditEvent(
        action_type=ActionType.TASK_COMPLETE,
        description="Task completed successfully",
        metadata={"needs_approval": needs_approval},
    ))
    
    return {
        "result": result_str,
        "status": "completed",
        "tasks_completed": len(tasks),
        "validation": {
            "pre": pre_validation.to_dict(),
            "post": post_validation.to_dict(),
        },
        "audit_summary": logger.get_session_summary(),
        "cost_summary": cost_tracker.get_summary(),
        "needs_approval": needs_approval,
        "approval_prompt": "Review the changes above. Type 'approve' to apply or 'reject' to discard." if needs_approval else None,
    }
