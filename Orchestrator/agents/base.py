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

# Add parent to path for governance imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from governance.policies import inject_policies_into_prompt

load_dotenv()


def get_llm(model: str = None) -> LLM:
    """
    Get configured LLM instance.
    
    Supports both Anthropic and OpenAI.
    Defaults to Claude for better code understanding.
    """
    model = model or os.getenv("DEFAULT_MODEL", "claude-3-5-sonnet-20241022")
    
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
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", "/home/steve/Agent007")
REQUIRE_APPROVAL = os.getenv("REQUIRE_APPROVAL", "true").lower() == "true"
