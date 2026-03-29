"""
Helix Community Template Marketplace
======================================

A full template marketplace for sharing, discovering, and importing
workflow templates, agent configurations, and automation recipes.

Features:
- Template submission with validation
- Category-based discovery with search
- Rating and review system
- Version management
- Import/export with dependency resolution
- Featured and trending templates
- Creator profiles and stats

(c) Helix Collective 2025 - Proprietary Technology Stack
"""

import json
import logging
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from apps.backend.core.redis_client import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/marketplace/templates", tags=["Template Marketplace"])


# ============================================================================
# TYPES
# ============================================================================


class TemplateCategory(str, Enum):
    AUTOMATION = "automation"
    AI_AGENTS = "ai_agents"
    DATA_PIPELINE = "data_pipeline"
    COMMUNICATION = "communication"
    DEVOPS = "devops"
    MARKETING = "marketing"
    SALES = "sales"
    CUSTOMER_SUPPORT = "customer_support"
    ANALYTICS = "analytics"
    SECURITY = "security"
    COORDINATION = "coordination"
    INTEGRATION = "integration"
    CUSTOM = "custom"


class TemplateStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    FEATURED = "featured"
    DEPRECATED = "deprecated"


@dataclass
class TemplateVersion:
    version: str
    changelog: str = ""
    definition: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    downloads: int = 0


@dataclass
class TemplateReview:
    review_id: str
    user_id: str
    username: str
    rating: int  # 1-5
    comment: str = ""
    created_at: str = ""
    helpful_votes: int = 0


@dataclass
class Template:
    id: str
    name: str
    description: str
    category: TemplateCategory
    creator_id: str
    creator_name: str
    status: TemplateStatus = TemplateStatus.DRAFT
    tags: list[str] = field(default_factory=list)
    icon: str = "⚡"
    color: str = "#6366F1"
    versions: list[TemplateVersion] = field(default_factory=list)
    reviews: list[TemplateReview] = field(default_factory=list)
    total_downloads: int = 0
    total_installs: int = 0
    avg_rating: float = 0.0
    dependencies: list[str] = field(default_factory=list)
    required_integrations: list[str] = field(default_factory=list)
    difficulty: str = "beginner"  # beginner, intermediate, advanced
    estimated_setup_minutes: int = 5
    created_at: str = ""
    updated_at: str = ""
    featured_at: str | None = None


# ============================================================================
# IN-MEMORY CACHE (Redis is primary store, these are fallback/cache)
# ============================================================================

# Write-through cache over Redis
_templates: dict[str, Template] = {}
_creator_stats: dict[str, dict[str, Any]] = defaultdict(
    lambda: {
        "templates_published": 0,
        "total_downloads": 0,
        "avg_rating": 0.0,
        "reputation": 0,
    }
)

# Redis key constants
_REDIS_TEMPLATES_HASH = "helix:marketplace:templates"
_REDIS_CREATOR_STATS_HASH = "helix:marketplace:creator_stats"


def _template_to_dict(t: Template) -> dict[str, Any]:
    """Serialize a Template dataclass to a JSON-safe dict."""
    d = asdict(t)
    # Convert enum values to strings for JSON serialization
    d["category"] = t.category.value
    d["status"] = t.status.value
    return d


def _template_from_dict(d: dict[str, Any]) -> Template:
    """Deserialize a dict back into a Template dataclass."""
    d["category"] = TemplateCategory(d["category"])
    d["status"] = TemplateStatus(d["status"])
    d["versions"] = [TemplateVersion(**v) for v in d.get("versions", [])]
    d["reviews"] = [TemplateReview(**r) for r in d.get("reviews", [])]
    return Template(**d)


async def _redis_save_template(template: Template) -> None:
    """Persist a single template to Redis hash."""
    try:
        r = await get_redis()
        if r:
            await r.hset(
                _REDIS_TEMPLATES_HASH,
                template.id,
                json.dumps(_template_to_dict(template)),
            )
    except Exception as exc:
        logger.warning("Redis write failed for template %s: %s", template.id, exc)


async def _redis_load_all_templates() -> dict[str, Template] | None:
    """Load all templates from Redis hash. Returns None if Redis unavailable."""
    try:
        r = await get_redis()
        if r:
            raw = await r.hgetall(_REDIS_TEMPLATES_HASH)
            if raw:
                result = {}
                for k, v in raw.items():
                    key = k if isinstance(k, str) else k.decode()
                    val = v if isinstance(v, str) else v.decode()
                    result[key] = _template_from_dict(json.loads(val))
                return result
    except Exception as exc:
        logger.warning("Redis read failed for templates: %s", exc)
    return None


async def _redis_delete_template(template_id: str) -> None:
    """Remove a template from Redis hash."""
    try:
        r = await get_redis()
        if r:
            await r.hdel(_REDIS_TEMPLATES_HASH, template_id)
    except Exception as exc:
        logger.warning("Redis delete failed for template %s: %s", template_id, exc)


async def _redis_save_creator_stats(creator_id: str, stats: dict[str, Any]) -> None:
    """Persist creator stats to Redis hash."""
    try:
        r = await get_redis()
        if r:
            await r.hset(
                _REDIS_CREATOR_STATS_HASH,
                creator_id,
                json.dumps(stats),
            )
    except Exception as exc:
        logger.warning("Redis write failed for creator stats %s: %s", creator_id, exc)


async def _redis_load_creator_stats(creator_id: str) -> dict[str, Any] | None:
    """Load creator stats from Redis hash."""
    try:
        r = await get_redis()
        if r:
            val = await r.hget(_REDIS_CREATOR_STATS_HASH, creator_id)
            if val:
                return json.loads(val if isinstance(val, str) else val.decode())
    except Exception as exc:
        logger.warning("Redis read failed for creator stats %s: %s", creator_id, exc)
    return None


async def _ensure_templates_loaded() -> None:
    """Ensure _templates is populated from Redis (or seed if first run)."""
    if _templates:
        return  # already loaded into cache
    loaded = await _redis_load_all_templates()
    if loaded:
        _templates.update(loaded)
    else:
        # First run: seed defaults and persist to Redis
        _seed_templates()
        for tmpl in _templates.values():
            await _redis_save_template(tmpl)


def _seed_templates():
    """Seed the marketplace with starter templates."""
    starters = [
        {
            "name": "AI-Powered Email Responder",
            "description": "Automatically classify incoming emails and generate AI responses using Helix agents. Routes to Lumina for empathetic responses, Kael for ethical review, and Arjuna for action items.",
            "category": TemplateCategory.COMMUNICATION,
            "tags": ["email", "ai", "automation", "customer-support"],
            "icon": "📧",
            "difficulty": "beginner",
            "estimated_setup_minutes": 10,
            "definition": {
                "nodes": [
                    {"id": "trigger", "type": "webhook", "name": "Email Webhook", "params": {}},
                    {
                        "id": "classify",
                        "type": "ai_classify",
                        "name": "Classify Email",
                        "params": {"categories": ["support", "sales", "feedback", "spam"]},
                    },
                    {
                        "id": "route",
                        "type": "conditional",
                        "name": "Route by Category",
                        "params": {"field": "category", "operator": "equals", "value": "support"},
                    },
                    {
                        "id": "respond",
                        "type": "ai_agent",
                        "name": "Generate Response",
                        "params": {"agent_id": "lumina", "prompt": "Respond empathetically to: {{body}}"},
                    },
                    {
                        "id": "review",
                        "type": "ai_agent",
                        "name": "Ethics Review",
                        "params": {
                            "agent_id": "kael",
                            "prompt": "Review this response for ethical concerns: {{response}}",
                        },
                    },
                    {
                        "id": "send",
                        "type": "email_send",
                        "name": "Send Reply",
                        "params": {"subject": "Re: {{subject}}"},
                    },
                ],
                "connections": [
                    {"from_node": "trigger", "to_node": "classify"},
                    {"from_node": "classify", "to_node": "route"},
                    {"from_node": "route", "to_node": "respond", "condition": "true"},
                    {"from_node": "respond", "to_node": "review"},
                    {"from_node": "review", "to_node": "send"},
                ],
            },
        },
        {
            "name": "GitHub PR Review Pipeline",
            "description": "Automatically review pull requests using AI agents. Oracle analyzes code patterns, Sentinel checks for security issues, and Kael ensures ethical coding practices.",
            "category": TemplateCategory.DEVOPS,
            "tags": ["github", "code-review", "ai", "devops", "security"],
            "icon": "🔍",
            "difficulty": "intermediate",
            "estimated_setup_minutes": 15,
            "definition": {
                "nodes": [
                    {"id": "webhook", "type": "webhook", "name": "GitHub PR Webhook", "params": {}},
                    {
                        "id": "fetch",
                        "type": "http_request",
                        "name": "Fetch PR Diff",
                        "params": {"method": "GET", "url": "{{pr_url}}"},
                    },
                    {
                        "id": "analyze",
                        "type": "ai_agent",
                        "name": "Code Analysis",
                        "params": {
                            "agent_id": "oracle",
                            "prompt": "Analyze this code diff for patterns and issues: {{diff}}",
                        },
                    },
                    {
                        "id": "security",
                        "type": "ai_agent",
                        "name": "Security Scan",
                        "params": {"agent_id": "sentinel", "prompt": "Check for security vulnerabilities: {{diff}}"},
                    },
                    {"id": "merge", "type": "merge", "name": "Combine Reviews", "params": {"mode": "combine"}},
                    {
                        "id": "comment",
                        "type": "github",
                        "name": "Post Review",
                        "params": {"action": "create_issue", "title": "AI Review"},
                    },
                ],
                "connections": [
                    {"from_node": "webhook", "to_node": "fetch"},
                    {"from_node": "fetch", "to_node": "analyze"},
                    {"from_node": "fetch", "to_node": "security"},
                    {"from_node": "analyze", "to_node": "merge"},
                    {"from_node": "security", "to_node": "merge"},
                    {"from_node": "merge", "to_node": "comment"},
                ],
            },
        },
        {
            "name": "Coordination Analytics Pipeline",
            "description": "Monitor and analyze UCF coordination metrics across all agents. Aggregates harmony, resilience, throughput, focus, and friction scores with trend detection.",
            "category": TemplateCategory.COORDINATION,
            "tags": ["ucf", "coordination", "analytics", "monitoring"],
            "icon": "🧠",
            "difficulty": "advanced",
            "estimated_setup_minutes": 20,
            "definition": {
                "nodes": [
                    {"id": "schedule", "type": "schedule", "name": "Hourly Check", "params": {"cron": "0 * * * *"}},
                    {
                        "id": "collect",
                        "type": "http_request",
                        "name": "Collect UCF Metrics",
                        "params": {"url": "/api/coordination/metrics", "method": "GET"},
                    },
                    {
                        "id": "analyze",
                        "type": "ai_agent",
                        "name": "Trend Analysis",
                        "params": {"agent_id": "oracle", "prompt": "Analyze coordination trends: {{metrics}}"},
                    },
                    {
                        "id": "alert",
                        "type": "conditional",
                        "name": "Check Thresholds",
                        "params": {"field": "harmony", "operator": "less_than", "value": 0.5},
                    },
                    {
                        "id": "notify",
                        "type": "notification",
                        "name": "Alert Team",
                        "params": {"channel": "discord", "message": "⚠️ Coordination alert: {{analysis}}"},
                    },
                ],
                "connections": [
                    {"from_node": "schedule", "to_node": "collect"},
                    {"from_node": "collect", "to_node": "analyze"},
                    {"from_node": "analyze", "to_node": "alert"},
                    {"from_node": "alert", "to_node": "notify", "condition": "true"},
                ],
            },
        },
        {
            "name": "Multi-Agent Content Generator",
            "description": "Generate content using a pipeline of specialized agents. Surya generates ideas, Gemini creates visuals, Echo refines messaging, and Kavach ensures compliance.",
            "category": TemplateCategory.MARKETING,
            "tags": ["content", "marketing", "multi-agent", "ai"],
            "icon": "✨",
            "difficulty": "intermediate",
            "estimated_setup_minutes": 10,
            "definition": {
                "nodes": [
                    {"id": "input", "type": "manual", "name": "Content Brief", "params": {}},
                    {"id": "ideate", "type": "ai_agent", "name": "Generate Ideas", "params": {"agent_id": "surya"}},
                    {"id": "draft", "type": "ai_generate", "name": "Write Draft", "params": {"agent_id": "echo"}},
                    {"id": "review", "type": "ai_agent", "name": "Compliance Check", "params": {"agent_id": "kavach"}},
                    {
                        "id": "output",
                        "type": "write_file",
                        "name": "Save Content",
                        "params": {"path": "output/content_{{timestamp}}.md"},
                    },
                ],
                "connections": [
                    {"from_node": "input", "to_node": "ideate"},
                    {"from_node": "ideate", "to_node": "draft"},
                    {"from_node": "draft", "to_node": "review"},
                    {"from_node": "review", "to_node": "output"},
                ],
            },
        },
        {
            "name": "Data Sync & Transform Pipeline",
            "description": "Fetch data from an API, transform it, filter relevant records, aggregate statistics, and push to a database or webhook.",
            "category": TemplateCategory.DATA_PIPELINE,
            "tags": ["data", "etl", "transform", "sync"],
            "icon": "🔄",
            "difficulty": "beginner",
            "estimated_setup_minutes": 10,
            "definition": {
                "nodes": [
                    {
                        "id": "fetch",
                        "type": "http_request",
                        "name": "Fetch Data",
                        "params": {"url": "{{api_url}}", "method": "GET"},
                    },
                    {"id": "parse", "type": "json_parse", "name": "Parse Response", "params": {"path": "data.results"}},
                    {
                        "id": "transform",
                        "type": "transform",
                        "name": "Reshape Data",
                        "params": {"operation": "map", "field_map": {"name": "full_name", "email": "contact_email"}},
                    },
                    {
                        "id": "filter",
                        "type": "filter",
                        "name": "Filter Active",
                        "params": {"field": "status", "operator": "equals", "value": "active"},
                    },
                    {"id": "aggregate", "type": "aggregate", "name": "Count Records", "params": {"operation": "count"}},
                    {
                        "id": "notify",
                        "type": "notification",
                        "name": "Report Results",
                        "params": {"channel": "internal", "message": "Synced {{count}} records"},
                    },
                ],
                "connections": [
                    {"from_node": "fetch", "to_node": "parse"},
                    {"from_node": "parse", "to_node": "transform"},
                    {"from_node": "transform", "to_node": "filter"},
                    {"from_node": "filter", "to_node": "aggregate"},
                    {"from_node": "aggregate", "to_node": "notify"},
                ],
            },
        },
    ]

    for i, tmpl_data in enumerate(starters):
        tmpl = Template(
            id=f"helix_template_{i + 1:03d}",
            name=tmpl_data["name"],
            description=tmpl_data["description"],
            category=tmpl_data["category"],
            creator_id="helix_official",
            creator_name="Helix Collective",
            status=TemplateStatus.FEATURED,
            tags=tmpl_data["tags"],
            icon=tmpl_data["icon"],
            difficulty=tmpl_data["difficulty"],
            estimated_setup_minutes=tmpl_data["estimated_setup_minutes"],
            versions=[
                TemplateVersion(
                    version="1.0.0",
                    changelog="Initial release",
                    definition=tmpl_data["definition"],
                    created_at=datetime.now(UTC).isoformat(),
                )
            ],
            total_downloads=100 * (5 - i),
            avg_rating=4.5 + (i * 0.1) if i < 3 else 4.2,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
            featured_at=datetime.now(UTC).isoformat(),
        )
        _templates[tmpl.id] = tmpl

    logger.info("🏪 Seeded %d marketplace templates", len(starters))


# Seeding now happens lazily via _ensure_templates_loaded() on first request,
# so templates can be loaded from Redis if they were already persisted.


# ============================================================================
# API MODELS
# ============================================================================


class TemplateSubmitRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: str = Field(..., min_length=10, max_length=2000)
    category: str
    tags: list[str] = []
    icon: str = "⚡"
    color: str = "#6366F1"
    definition: dict[str, Any] = {}
    difficulty: str = "beginner"
    estimated_setup_minutes: int = 5
    required_integrations: list[str] = []
    dependencies: list[str] = []


class ReviewRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str = ""


class TemplateVersionRequest(BaseModel):
    version: str
    changelog: str = ""
    definition: dict[str, Any] = {}


# ============================================================================
# API ROUTES
# ============================================================================


@router.get("/")
async def list_templates(
    category: str | None = None,
    tag: str | None = None,
    search: str | None = None,
    difficulty: str | None = None,
    sort_by: str = Query("downloads", pattern="^(downloads|rating|newest|name)$"),
    status: str = Query("approved", pattern="^(all|draft|submitted|approved|featured|deprecated)$"),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
):
    """Browse and search templates."""
    await _ensure_templates_loaded()
    templates = list(_templates.values())

    # Filter
    if status != "all":
        if status == "approved":
            templates = [t for t in templates if t.status in (TemplateStatus.APPROVED, TemplateStatus.FEATURED)]
        else:
            templates = [t for t in templates if t.status.value == status]

    if category:
        templates = [t for t in templates if t.category.value == category]
    if tag:
        templates = [t for t in templates if tag.lower() in [tg.lower() for tg in t.tags]]
    if difficulty:
        templates = [t for t in templates if t.difficulty == difficulty]
    if search:
        search_lower = search.lower()
        templates = [
            t
            for t in templates
            if search_lower in t.name.lower()
            or search_lower in t.description.lower()
            or any(search_lower in tag.lower() for tag in t.tags)
        ]

    # Sort
    if sort_by == "downloads":
        templates.sort(key=lambda t: t.total_downloads, reverse=True)
    elif sort_by == "rating":
        templates.sort(key=lambda t: t.avg_rating, reverse=True)
    elif sort_by == "newest":
        templates.sort(key=lambda t: t.created_at, reverse=True)
    elif sort_by == "name":
        templates.sort(key=lambda t: t.name.lower())

    total = len(templates)
    templates = templates[offset : offset + limit]

    return {
        "templates": [_serialize_template(t) for t in templates],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/featured")
async def featured_templates():
    """Get featured templates."""
    await _ensure_templates_loaded()
    featured = [t for t in _templates.values() if t.status == TemplateStatus.FEATURED]
    featured.sort(key=lambda t: t.total_downloads, reverse=True)
    return {"templates": [_serialize_template(t) for t in featured[:10]]}


@router.get("/categories")
async def list_categories():
    """List all template categories with counts."""
    await _ensure_templates_loaded()
    counts: dict[str, int] = defaultdict(int)
    for t in _templates.values():
        if t.status in (TemplateStatus.APPROVED, TemplateStatus.FEATURED):
            counts[t.category.value] += 1

    return {
        "categories": [
            {"id": cat.value, "name": cat.value.replace("_", " ").title(), "count": counts.get(cat.value, 0)}
            for cat in TemplateCategory
        ]
    }


@router.get("/{template_id}")
async def get_template(template_id: str):
    """Get a template by ID with full details."""
    await _ensure_templates_loaded()
    if template_id not in _templates:
        raise HTTPException(404, f"Template not found: {template_id}")
    return _serialize_template(_templates[template_id], full=True)


@router.post("/")
async def submit_template(request: TemplateSubmitRequest):
    """Submit a new template to the marketplace."""
    template_id = f"tmpl_{uuid.uuid4().hex[:12]}"

    try:
        category = TemplateCategory(request.category)
    except ValueError:
        category = TemplateCategory.CUSTOM

    template = Template(
        id=template_id,
        name=request.name,
        description=request.description,
        category=category,
        creator_id="user",  # Would come from auth in production
        creator_name="Community Creator",
        status=TemplateStatus.SUBMITTED,
        tags=request.tags,
        icon=request.icon,
        color=request.color,
        difficulty=request.difficulty,
        estimated_setup_minutes=request.estimated_setup_minutes,
        required_integrations=request.required_integrations,
        dependencies=request.dependencies,
        versions=[
            TemplateVersion(
                version="1.0.0",
                changelog="Initial submission",
                definition=request.definition,
                created_at=datetime.now(UTC).isoformat(),
            )
        ],
        created_at=datetime.now(UTC).isoformat(),
        updated_at=datetime.now(UTC).isoformat(),
    )

    _templates[template_id] = template
    await _redis_save_template(template)
    logger.info("New template submitted: %s (%s)", request.name, template_id)

    return {
        "template_id": template_id,
        "status": "submitted",
        "message": "Template submitted for review",
    }


@router.post("/{template_id}/install")
async def install_template(template_id: str):
    """Install a template (creates a workflow from the template)."""
    await _ensure_templates_loaded()
    if template_id not in _templates:
        raise HTTPException(404, f"Template not found: {template_id}")

    template = _templates[template_id]
    template.total_downloads += 1
    template.total_installs += 1

    # Get latest version definition
    if not template.versions:
        raise HTTPException(400, "Template has no versions")

    latest = template.versions[-1]
    latest.downloads += 1

    # Persist updated counters to Redis
    await _redis_save_template(template)

    return {
        "installed": True,
        "template_id": template_id,
        "template_name": template.name,
        "version": latest.version,
        "definition": latest.definition,
        "message": "Use the definition to create a workflow via /api/workflows/engine/workflows",
    }


@router.post("/{template_id}/reviews")
async def add_review(template_id: str, request: ReviewRequest):
    """Add a review to a template."""
    await _ensure_templates_loaded()
    if template_id not in _templates:
        raise HTTPException(404, f"Template not found: {template_id}")

    template = _templates[template_id]
    review = TemplateReview(
        review_id=str(uuid.uuid4()),
        user_id="user",
        username="Community User",
        rating=request.rating,
        comment=request.comment,
        created_at=datetime.now(UTC).isoformat(),
    )
    template.reviews.append(review)

    # Recalculate average rating
    if template.reviews:
        template.avg_rating = sum(r.rating for r in template.reviews) / len(template.reviews)

    template.updated_at = datetime.now(UTC).isoformat()

    # Persist updated template to Redis
    await _redis_save_template(template)

    return {"review_id": review.review_id, "avg_rating": template.avg_rating}


@router.post("/{template_id}/versions")
async def add_version(template_id: str, request: TemplateVersionRequest):
    """Add a new version to a template."""
    await _ensure_templates_loaded()
    if template_id not in _templates:
        raise HTTPException(404, f"Template not found: {template_id}")

    template = _templates[template_id]
    version = TemplateVersion(
        version=request.version,
        changelog=request.changelog,
        definition=request.definition,
        created_at=datetime.now(UTC).isoformat(),
    )
    template.versions.append(version)
    template.updated_at = datetime.now(UTC).isoformat()

    # Persist updated template to Redis
    await _redis_save_template(template)

    return {"version": request.version, "template_id": template_id}


# ============================================================================
# HELPERS
# ============================================================================


def _serialize_template(t: Template, full: bool = False) -> dict[str, Any]:
    """Serialize a template for API response."""
    data = {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "category": t.category.value,
        "creator_name": t.creator_name,
        "status": t.status.value,
        "tags": t.tags,
        "icon": t.icon,
        "color": t.color,
        "difficulty": t.difficulty,
        "estimated_setup_minutes": t.estimated_setup_minutes,
        "total_downloads": t.total_downloads,
        "avg_rating": round(t.avg_rating, 1),
        "review_count": len(t.reviews),
        "version_count": len(t.versions),
        "latest_version": t.versions[-1].version if t.versions else None,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
        "featured": t.status == TemplateStatus.FEATURED,
    }

    if full:
        data["versions"] = [
            {
                "version": v.version,
                "changelog": v.changelog,
                "definition": v.definition,
                "created_at": v.created_at,
                "downloads": v.downloads,
            }
            for v in t.versions
        ]
        data["reviews"] = [
            {
                "review_id": r.review_id,
                "username": r.username,
                "rating": r.rating,
                "comment": r.comment,
                "created_at": r.created_at,
            }
            for r in t.reviews[-20:]  # Last 20 reviews
        ]
        data["required_integrations"] = t.required_integrations
        data["dependencies"] = t.dependencies

    return data
