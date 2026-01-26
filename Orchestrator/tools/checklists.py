"""
Checklist Tools

CrewAI tools for running project checklists.
Provides documentation, security, and deployment readiness checks.
"""

from typing import Any, Type, Optional, List
from pydantic import BaseModel, Field
from pathlib import Path

try:
    from crewai.tools import BaseTool
    CREWAI_AVAILABLE = True
except ImportError:
    CREWAI_AVAILABLE = False
    BaseTool = object

from ..governance.checklists import (
    run_all_checklists,
    check_documentation,
    check_security,
    check_deployment_readiness,
    format_checklist_results,
    ChecklistResult,
)


class ChecklistInput(BaseModel):
    """Input for running checklists."""
    project_path: str = Field(..., description="Path to the project to check")
    checklist: str = Field(
        default="all",
        description="Which checklist to run: 'all', 'documentation', 'security', 'deployment'"
    )


class RunChecklistTool(BaseTool if CREWAI_AVAILABLE else object):
    """Run project checklists to verify completeness."""
    
    name: str = "run_checklist"
    description: str = (
        "Run checklists to verify project documentation, security, and deployment readiness. "
        "Returns actionable items with fix commands."
    )
    args_schema: Type[BaseModel] = ChecklistInput
    
    def _run(self, project_path: str, checklist: str = "all") -> str:
        path = Path(project_path).expanduser()
        
        if not path.exists():
            return f"❌ Project path not found: {project_path}"
        
        try:
            if checklist == "all":
                results = run_all_checklists(str(path))
                return format_checklist_results(results)
            elif checklist == "documentation":
                result = check_documentation(path)
                return format_checklist_results({"documentation": result})
            elif checklist == "security":
                result = check_security(path)
                return format_checklist_results({"security": result})
            elif checklist == "deployment":
                result = check_deployment_readiness(path)
                return format_checklist_results({"deployment": result})
            else:
                return f"❌ Unknown checklist: {checklist}. Use: all, documentation, security, deployment"
                
        except Exception as e:
            return f"❌ Error running checklist: {e}"


class InitDocsInput(BaseModel):
    """Input for initializing documentation."""
    project_path: str = Field(..., description="Path to the project")


class InitDocsTool(BaseTool if CREWAI_AVAILABLE else object):
    """Initialize auto-documentation for a project."""
    
    name: str = "init_docs"
    description: str = (
        "Initialize auto-documentation for a project. Sets up git hooks for diagram generation, "
        "AppMap configuration, and documentation directory structure."
    )
    args_schema: Type[BaseModel] = InitDocsInput
    
    def _run(self, project_path: str) -> str:
        import subprocess
        
        path = Path(project_path).expanduser()
        
        if not path.exists():
            return f"❌ Project path not found: {project_path}"
        
        try:
            # Run init-docs script
            result = subprocess.run(
                ["bash", str(Path.home() / "DevOps" / "bin" / "init-docs"), str(path)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            if result.returncode == 0:
                return f"✅ Documentation initialized for {path.name}\n\n{result.stdout}"
            else:
                return f"⚠️ Partial success:\n{result.stdout}\n{result.stderr}"
                
        except subprocess.TimeoutExpired:
            return "❌ Initialization timed out"
        except FileNotFoundError:
            return "❌ init-docs script not found. Run: ~/DevOps/bin/init-docs"
        except Exception as e:
            return f"❌ Error: {e}"


class GenerateDiagramsInput(BaseModel):
    """Input for generating diagrams."""
    project_path: str = Field(..., description="Path to the project")


class GenerateDiagramsTool(BaseTool if CREWAI_AVAILABLE else object):
    """Generate Mermaid diagrams for a project."""
    
    name: str = "generate_diagrams"
    description: str = (
        "Generate Mermaid architecture and flow diagrams from project configuration files "
        "(docker-compose, database schemas, API routes)."
    )
    args_schema: Type[BaseModel] = GenerateDiagramsInput
    
    def _run(self, project_path: str) -> str:
        import subprocess
        
        path = Path(project_path).expanduser()
        
        if not path.exists():
            return f"❌ Project path not found: {project_path}"
        
        try:
            result = subprocess.run(
                [
                    "python3",
                    str(Path.home() / "DevOps" / "observability" / "scripts" / "generate-diagrams.py"),
                    "--project", str(path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            if result.returncode == 0:
                return f"✅ Diagrams generated for {path.name}\n\n{result.stdout}"
            else:
                return f"⚠️ Generation issues:\n{result.stdout}\n{result.stderr}"
                
        except subprocess.TimeoutExpired:
            return "❌ Diagram generation timed out"
        except Exception as e:
            return f"❌ Error: {e}"


# =============================================================================
# Tool Collection
# =============================================================================

def get_checklist_tools() -> List:
    """Get all checklist tools."""
    if not CREWAI_AVAILABLE:
        return []
    
    return [
        RunChecklistTool(),
        InitDocsTool(),
        GenerateDiagramsTool(),
    ]
