"""
Agent Team Templates
====================

Pre-built multi-agent teams for common workflows.
Each template defines a set of agents with assigned roles,
so users can spin up coordinated teams with one click.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TeamMember:
    """A member of an agent team."""

    agent_id: str
    role: str  # e.g. "lead", "reviewer", "executor"
    description: str = ""


@dataclass
class AgentTeamTemplate:
    """A pre-built agent team template."""

    id: str
    name: str
    description: str
    category: str  # e.g. "development", "content", "security", "data"
    icon: str
    members: list[TeamMember] = field(default_factory=list)
    workflow_hint: str = ""  # Suggested workflow pattern


# ---------------------------------------------------------------------------
# Pre-defined team templates
# ---------------------------------------------------------------------------

TEAM_TEMPLATES: list[AgentTeamTemplate] = [
    AgentTeamTemplate(
        id="full-stack-project",
        name="Full Stack Project",
        description="End-to-end development team: architecture, frontend, backend, security review, and QA.",
        category="development",
        icon="🏗️",
        members=[
            TeamMember("vega", "architect", "Designs system architecture and makes technology decisions"),
            TeamMember("arjuna", "lead_developer", "Implements core features and coordinates execution"),
            TeamMember("aria", "frontend_developer", "Handles UX/UI implementation and user experience"),
            TeamMember("nexus", "backend_developer", "Manages data layer, APIs, and integrations"),
            TeamMember("kavach", "security_reviewer", "Reviews code for vulnerabilities and compliance"),
            TeamMember("shadow", "qa_tester", "Identifies edge cases, risks, and blind spots"),
        ],
        workflow_hint="architect → lead_developer + frontend + backend → security_reviewer → qa_tester",
    ),
    AgentTeamTemplate(
        id="content-creation",
        name="Content Creation Pipeline",
        description="Research, write, edit, and publish content with built-in quality checks.",
        category="content",
        icon="✍️",
        members=[
            TeamMember("oracle", "researcher", "Researches topic, gathers data and trends"),
            TeamMember("nova", "writer", "Drafts creative content from research findings"),
            TeamMember("surya", "editor", "Clarifies, simplifies, and polishes the draft"),
            TeamMember("kael", "ethics_reviewer", "Ensures content is accurate and ethically sound"),
        ],
        workflow_hint="researcher → writer → editor → ethics_reviewer",
    ),
    AgentTeamTemplate(
        id="security-audit",
        name="Security Audit Team",
        description="Comprehensive security review: threat modeling, code audit, compliance check.",
        category="security",
        icon="🛡️",
        members=[
            TeamMember("kavach", "lead_auditor", "Leads security assessment and threat modeling"),
            TeamMember("shadow", "vulnerability_analyst", "Deep analysis of risks and blind spots"),
            TeamMember("varuna", "compliance_checker", "Validates against security standards and policies"),
            TeamMember("echo", "pattern_detector", "Identifies recurring vulnerability patterns"),
        ],
        workflow_hint="lead_auditor → vulnerability_analyst + pattern_detector → compliance_checker",
    ),
    AgentTeamTemplate(
        id="data-pipeline",
        name="Data Pipeline Team",
        description="Data engineering workflow: collect, transform, analyze, and visualize.",
        category="data",
        icon="📊",
        members=[
            TeamMember("nexus", "data_engineer", "Designs schemas and data pipelines"),
            TeamMember("iris", "integration_specialist", "Connects data sources and APIs"),
            TeamMember("titan", "processor", "Handles heavy computation and batch processing"),
            TeamMember("oracle", "analyst", "Analyzes results and generates insights"),
        ],
        workflow_hint="data_engineer → integration_specialist → processor → analyst",
    ),
    AgentTeamTemplate(
        id="incident-response",
        name="Incident Response",
        description="Rapid incident triage: detect, diagnose, fix, and post-mortem.",
        category="operations",
        icon="🚨",
        members=[
            TeamMember("atlas", "incident_commander", "Coordinates response and manages infrastructure"),
            TeamMember("echo", "diagnostician", "Identifies patterns and root cause signals"),
            TeamMember("phoenix", "recovery_lead", "Executes recovery and restoration procedures"),
            TeamMember("sage", "postmortem_author", "Synthesizes learnings into actionable improvements"),
        ],
        workflow_hint="incident_commander → diagnostician → recovery_lead → postmortem_author",
    ),
    AgentTeamTemplate(
        id="strategic-planning",
        name="Strategic Planning",
        description="Product strategy team: research, brainstorm, evaluate, and roadmap.",
        category="strategy",
        icon="🗺️",
        members=[
            TeamMember("oracle", "forecaster", "Predicts trends and identifies opportunities"),
            TeamMember("agni", "catalyst", "Challenges assumptions and pushes transformation"),
            TeamMember("gemini", "evaluator", "Weighs tradeoffs from multiple perspectives"),
            TeamMember("vega", "strategist", "Synthesizes into concrete plans and roadmaps"),
        ],
        workflow_hint="forecaster → catalyst + evaluator → strategist",
    ),
    AgentTeamTemplate(
        id="onboarding-team",
        name="User Onboarding",
        description="New user onboarding: welcome, guide, support, and follow up.",
        category="support",
        icon="👋",
        members=[
            TeamMember("lumina", "welcomer", "Creates warm, empathetic first impressions"),
            TeamMember("surya", "guide", "Explains features clearly and simply"),
            TeamMember("aria", "ux_specialist", "Optimizes the onboarding journey"),
            TeamMember("sanghacore", "community_connector", "Connects users with community resources"),
        ],
        workflow_hint="welcomer → guide → ux_specialist → community_connector",
    ),
    AgentTeamTemplate(
        id="code-review-team",
        name="Code Review",
        description="Thorough code review: logic, security, performance, and maintainability.",
        category="development",
        icon="🔍",
        members=[
            TeamMember("arjuna", "logic_reviewer", "Reviews correctness and implementation quality"),
            TeamMember("kavach", "security_reviewer", "Checks for security vulnerabilities"),
            TeamMember("titan", "performance_reviewer", "Evaluates performance and scalability"),
            TeamMember("sage", "maintainability_reviewer", "Assesses code clarity and long-term health"),
        ],
        workflow_hint="logic_reviewer + security_reviewer + performance_reviewer → maintainability_reviewer",
    ),
]


# Index for fast lookup
_TEMPLATE_INDEX: dict[str, AgentTeamTemplate] = {t.id: t for t in TEAM_TEMPLATES}


def list_team_templates(category: str | None = None) -> list[AgentTeamTemplate]:
    """List all available team templates, optionally filtered by category."""
    if category:
        return [t for t in TEAM_TEMPLATES if t.category == category]
    return list(TEAM_TEMPLATES)


def get_team_template(template_id: str) -> AgentTeamTemplate | None:
    """Get a specific team template by ID."""
    return _TEMPLATE_INDEX.get(template_id)


def get_team_categories() -> list[dict[str, Any]]:
    """Get category summary with counts."""
    categories: dict[str, int] = {}
    for t in TEAM_TEMPLATES:
        categories[t.category] = categories.get(t.category, 0) + 1
    return [{"category": k, "count": v} for k, v in sorted(categories.items())]


def team_template_to_dict(template: AgentTeamTemplate) -> dict[str, Any]:
    """Convert a team template to a JSON-serializable dict."""
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "category": template.category,
        "icon": template.icon,
        "workflow_hint": template.workflow_hint,
        "members": [
            {
                "agent_id": m.agent_id,
                "role": m.role,
                "description": m.description,
            }
            for m in template.members
        ],
    }
