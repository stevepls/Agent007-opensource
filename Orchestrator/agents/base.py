"""
Orchestrator - Base Agent Configuration

Provides consistent LLM configuration and shared settings for all agents.
Integrates governance policies into agent prompts.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from crewai import LLM

# Paths - relative to this file for portability
ORCHESTRATOR_ROOT = Path(__file__).parent.parent
AGENT007_ROOT = ORCHESTRATOR_ROOT.parent

# Add parent to path for governance imports
sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from governance.policies import inject_policies_into_prompt

load_dotenv()


def get_llm(model: str = None) -> LLM:
    """
    Get configured LLM instance.

    Supports both Anthropic and OpenAI.
    Defaults to Claude Opus 4.6 for maximum capability.

    Available models:
    - claude-opus-4-6 (most capable, best for complex orchestration)
    - claude-sonnet-4-6 (fast, great for most tasks)
    - claude-haiku-4-5-20251001 (fastest, good for classification)
    """
    model = model or os.getenv("DEFAULT_MODEL", "claude-opus-4-6")
    
    # Determine provider from model name
    if "claude" in model.lower():
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return LLM(
            model=f"anthropic/{model}",
            api_key=api_key,
            temperature=0.1  # Low temperature for consistent, reliable output
        )
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        return LLM(
            model=f"openai/{model}",
            api_key=api_key,
            temperature=0.1
        )


def create_policy_aware_backstory(base_backstory: str, categories: list = None) -> str:
    """
    Enhance an agent's backstory with mandatory policy rules.
    
    This ensures all agents are aware of and comply with governance policies.
    """
    return inject_policies_into_prompt(base_backstory, categories)


# Shared agent configuration
AGENT_CONFIG = {
    "verbose": True,
    "allow_delegation": False,  # Agents don't delegate to each other directly
    "max_iter": 10,  # Prevent infinite loops
    "max_rpm": 30,  # Rate limit
}


# Workspace configuration
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", str(AGENT007_ROOT))
REQUIRE_APPROVAL = os.getenv("REQUIRE_APPROVAL", "true").lower() == "true"
