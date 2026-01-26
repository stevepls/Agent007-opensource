"""
Self-Critique Agent

A Constitutional AI-style agent that reviews other agents' outputs against policies.
Runs as a final validation step before presenting results to the user.

Key responsibilities:
1. Check for security violations in outputs
2. Verify policy compliance
3. Detect incomplete work (placeholders, TODOs)
4. Flag production-related concerns
5. Recommend escalation when uncertain
"""

import sys
from pathlib import Path
from crewai import Agent, Task
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from .base import get_llm, AGENT_CONFIG
from governance.policies import inject_policies_into_prompt, get_policy


# =============================================================================
# CRITIC AGENT CONFIGURATION
# =============================================================================

CRITIC_BACKSTORY = """You are a policy compliance checker and quality gate.
Your job is to review agent outputs and verify they follow all policies.

You are the LAST line of defense before work is presented to the human.

You must check for:

1. SECURITY VIOLATIONS
   - Hardcoded secrets (API keys, passwords, tokens)
   - Dangerous operations (rm -rf, DROP TABLE, etc.)
   - Access to blocked paths (.env, secrets/, .git/)
   - Production environment modifications

2. QUALITY ISSUES
   - Placeholder code (TODO, FIXME, ..., pass # implement)
   - Incomplete implementations
   - Missing error handling
   - Files exceeding 500 lines

3. POLICY NON-COMPLIANCE
   - Violations of escalation rules
   - Missing human approval for sensitive operations
   - Operations outside allowed scope

4. CONFIDENCE ASSESSMENT
   - Agent uncertainty indicators
   - Low confidence statements
   - Requests for clarification

OUTPUT FORMAT:
You must output a structured assessment:

### Policy Checks Performed
- [List each policy area checked]

### Violations Found
| Type | Severity | Description |
|------|----------|-------------|
| ... | ... | ... |

### Quality Assessment
- Complete: [YES/NO]
- Secure: [YES/NO]
- Production Safe: [YES/NO]
- Follows Guidelines: [YES/NO]

### Verdict
[PASS / FAIL / ESCALATE]

### Confidence
[0-100]%

### Reasoning
[Why this verdict was given]

### Recommendations
[If FAIL or ESCALATE, what should be fixed/reviewed]

RULES:
- Be thorough but fair - don't invent issues that don't exist
- Always check for the presence of secrets or credentials
- Always verify production paths aren't being modified
- If in doubt, ESCALATE rather than PASS
- Never approve code with placeholders or incomplete implementations
- A single CRITICAL issue means FAIL
- Low confidence (<80%) from any agent means ESCALATE
"""


def create_critic_agent(tools: list = None) -> Agent:
    """
    Create the self-critique agent.
    
    This agent reviews other agents' outputs against policies.
    It should have read-only file access to verify changes.
    
    Args:
        tools: Optional list of tools (recommend read-only file tools)
    
    Returns:
        Configured Critic agent
    """
    # Inject policies into backstory
    full_backstory = inject_policies_into_prompt(
        CRITIC_BACKSTORY,
        categories=["security", "production", "quality", "escalation"]
    )
    
    return Agent(
        role="Policy Compliance Checker (Self-Critique)",
        goal="Review agent outputs for security violations, policy compliance, and quality issues. FAIL anything that violates policies.",
        backstory=full_backstory,
        llm=get_llm(),
        tools=tools or [],
        verbose=AGENT_CONFIG.get("verbose", True),
        allow_delegation=False,  # Critic doesn't delegate
        max_iter=5,  # Limited iterations - it's a review, not implementation
        max_rpm=30,
    )


def create_critique_task(
    agent_output: str,
    original_task: str,
    files_modified: list = None,
    agent: Agent = None,
) -> Task:
    """
    Create a critique task for reviewing agent output.
    
    Args:
        agent_output: The output from the agent(s) to review
        original_task: The original task description
        files_modified: List of files that were created/modified
        agent: The critic agent (created if not provided)
    
    Returns:
        A Task configured for critique
    """
    if agent is None:
        agent = create_critic_agent()
    
    files_context = ""
    if files_modified:
        files_context = f"""
FILES MODIFIED:
{chr(10).join(f'- {f}' for f in files_modified)}

You SHOULD read these files to verify:
1. No hardcoded secrets
2. No placeholder code (TODO, FIXME, ...)
3. Proper error handling
4. Production paths not modified
"""
    
    return Task(
        description=f"""Review the following agent output for policy compliance.

ORIGINAL TASK:
{original_task}

AGENT OUTPUT TO REVIEW:
---
{agent_output}
---

{files_context}

REVIEW CHECKLIST:
1. Check for security violations (secrets, dangerous commands)
2. Check for quality issues (placeholders, incomplete code)
3. Check for production safety (no prod path modifications)
4. Check for policy compliance (escalation rules followed)
5. Assess overall confidence

If you find ANY critical issues, your verdict must be FAIL.
If you have concerns but they're not critical, verdict is ESCALATE.
Only if everything passes, verdict is PASS.

Output your review in the structured format specified in your backstory.""",
        expected_output="Structured critique with policy checks, violations, assessment, verdict (PASS/FAIL/ESCALATE), and recommendations",
        agent=agent,
    )


def parse_critique_verdict(critique_output: str) -> dict:
    """
    Parse the critique output to extract the verdict and key information.
    
    Args:
        critique_output: The raw output from the critic agent
    
    Returns:
        dict with verdict, confidence, violations, and recommendations
    """
    result = {
        "verdict": "ESCALATE",  # Default to safe option
        "confidence": 0,
        "violations": [],
        "is_complete": False,
        "is_secure": False,
        "is_production_safe": False,
        "follows_guidelines": False,
        "recommendations": [],
        "raw_output": critique_output,
    }
    
    output_upper = critique_output.upper()
    
    # Extract verdict
    if "### VERDICT" in output_upper:
        verdict_section = critique_output.split("### Verdict")[-1].split("###")[0]
        if "PASS" in verdict_section.upper() and "FAIL" not in verdict_section.upper():
            result["verdict"] = "PASS"
        elif "FAIL" in verdict_section.upper():
            result["verdict"] = "FAIL"
        elif "ESCALATE" in verdict_section.upper():
            result["verdict"] = "ESCALATE"
    
    # Extract confidence
    if "### CONFIDENCE" in output_upper:
        conf_section = critique_output.split("### Confidence")[-1].split("###")[0]
        import re
        conf_match = re.search(r'(\d+)\s*%', conf_section)
        if conf_match:
            result["confidence"] = int(conf_match.group(1))
    
    # Check quality flags
    if "### QUALITY ASSESSMENT" in output_upper:
        qa_section = critique_output.split("### Quality Assessment")[-1].split("###")[0].upper()
        result["is_complete"] = "COMPLETE:" in qa_section and "YES" in qa_section.split("COMPLETE:")[1].split("\n")[0]
        result["is_secure"] = "SECURE:" in qa_section and "YES" in qa_section.split("SECURE:")[1].split("\n")[0]
        result["is_production_safe"] = "PRODUCTION SAFE:" in qa_section and "YES" in qa_section.split("PRODUCTION SAFE:")[1].split("\n")[0]
        result["follows_guidelines"] = "FOLLOWS GUIDELINES:" in qa_section and "YES" in qa_section.split("FOLLOWS GUIDELINES:")[1].split("\n")[0]
    
    # Extract violations (simple approach)
    if "### VIOLATIONS FOUND" in output_upper:
        violations_section = critique_output.split("### Violations Found")[-1].split("###")[0]
        # Look for table rows
        lines = violations_section.strip().split("\n")
        for line in lines:
            if "|" in line and "---" not in line and "Type" not in line:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 3:
                    result["violations"].append({
                        "type": parts[0],
                        "severity": parts[1],
                        "description": parts[2],
                    })
    
    # Extract recommendations
    if "### RECOMMENDATIONS" in output_upper:
        rec_section = critique_output.split("### Recommendations")[-1].split("###")[0]
        lines = rec_section.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("-") or line.startswith("*"):
                result["recommendations"].append(line[1:].strip())
            elif line and not line.startswith("|"):
                result["recommendations"].append(line)
    
    return result


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def run_self_critique(
    agent_output: str,
    original_task: str,
    files_modified: list = None,
    file_tools: list = None,
) -> dict:
    """
    Run self-critique on agent output.
    
    This is a convenience function that creates the critic, runs the task,
    and parses the result.
    
    Args:
        agent_output: The output to critique
        original_task: The original task description
        files_modified: List of files that were modified
        file_tools: Optional read-only file tools for verification
    
    Returns:
        Parsed critique result with verdict
    """
    from crewai import Crew, Process
    
    # Create critic with optional file reading capability
    critic = create_critic_agent(tools=file_tools)
    
    # Create task
    task = create_critique_task(
        agent_output=agent_output,
        original_task=original_task,
        files_modified=files_modified,
        agent=critic,
    )
    
    # Run critique
    crew = Crew(
        agents=[critic],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
    )
    
    result = crew.kickoff()
    
    # Parse and return
    return parse_critique_verdict(str(result))
