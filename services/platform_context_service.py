"""
🌀 Helix Platform Context Service
==================================

Provides contextual awareness of the entire helix-unified platform to agents.
This service enables agents to understand and reference:
- Platform capabilities and products
- Agent system architecture (18 agents)
- Available API endpoints and features
- User subscription tiers and feature access
- Real-time system state

Key Features:
- Hierarchical context retrieval (summary → detailed)
- Token-budget aware context compression
- Dynamic context updates based on conversation
- Platform knowledge injection for external LLMs

Author: Helix Collective Development Team
Version: 1.0 - Platform Awareness Engine
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ContextLevel(str, Enum):
    """Level of context detail to retrieve."""

    MINIMAL = "minimal"  # ~500 tokens - core identity only
    SUMMARY = "summary"  # ~1500 tokens - main capabilities
    STANDARD = "standard"  # ~3000 tokens - features + agents
    DETAILED = "detailed"  # ~6000 tokens - full platform awareness
    COMPREHENSIVE = "comprehensive"  # ~10000 tokens - everything


@dataclass
class AgentProfile:
    """Profile of a Helix agent."""

    name: str
    codename: str
    emoji: str
    layer: str  # coordination, operational, integration
    capabilities: list[str]
    specializations: list[str]
    description: str


@dataclass
class PlatformProduct:
    """Information about a Helix product."""

    name: str
    description: str
    status: str  # active, beta, planned
    key_features: list[str]
    api_endpoints: list[str]


@dataclass
class PlatformContext:
    """Complete platform context for agent injection."""

    platform_identity: str
    agent_summary: str
    products_summary: str
    api_summary: str
    user_context: str | None = None
    current_state: str | None = None

    def to_prompt_injection(self) -> str:
        """Convert to prompt-ready format."""
        parts = [
            "## HELIX PLATFORM CONTEXT",
            "",
            "### Platform Identity",
            self.platform_identity,
            "",
            "### Available Agents",
            self.agent_summary,
            "",
            "### Platform Products",
            self.products_summary,
        ]

        if self.api_summary:
            parts.extend(["", "### API Capabilities", self.api_summary])

        if self.user_context:
            parts.extend(["", "### User Context", self.user_context])

        if self.current_state:
            parts.extend(["", "### System State", self.current_state])

        return "\n".join(parts)

    def estimated_tokens(self) -> int:
        """Estimate token count (rough: 4 chars = 1 token)."""
        text = self.to_prompt_injection()
        return len(text) // 4


class PlatformContextService:
    """
    Service for providing platform-wide context to agents.

    Enables agents to be contextually aware of:
    - What Helix Collective is and does
    - What agents exist and their capabilities
    - What products and features are available
    - How to help users navigate the platform
    """

    # Core platform identity
    PLATFORM_IDENTITY = """Helix Collective is a multi-agent AI coordination platform orchestrating a collective of 18 specialized AI agents through a Universal Coordination Field (UCF). The platform provides:

- **Multi-Agent Collaboration**: 18 specialized agents working together
- **Coordination-Aware Processing**: UCF metrics (Harmony, Resilience, Throughput, Focus, Friction, Velocity)
- **Visual Workflow Automation**: Helix Spirals - coordination-aware Zapier alternative
- **Cross-Platform Integration**: Discord, Web, Mobile, VSCode, GitHub
- **Ethical AI Framework**: Ethics Validator for AI ethics compliance

The platform operates on three architectural layers:
1. **Coordination Layer**: Omega Zero, Vega, Lumina - strategic vision and ethics
2. **Operational Layer**: Arjuna, Kael, Grok, Agni, Gemini, Oracle, Kavach - execution and analysis
3. **Integration Layer**: SanghaCore, Coordination, Shadow - coordination and memory"""

    # Agent profiles
    AGENTS: dict[str, AgentProfile] = {
        "kael": AgentProfile(
            name="Kael",
            codename="🜂",
            emoji="🜂",
            layer="operational",
            capabilities=["data_analysis", "pattern_recognition", "optimization"],
            specializations=["metrics", "performance", "ethical_analysis"],
            description="Data analysis and ethical reasoning specialist",
        ),
        "lumina": AgentProfile(
            name="Lumina",
            codename="🌕",
            emoji="🌕",
            layer="coordination",
            capabilities=["emotional_intelligence", "empathy", "creative_synthesis"],
            specializations=["support", "creativity", "human_connection"],
            description="Emotional intelligence and empathetic support",
        ),
        "vega": AgentProfile(
            name="Vega",
            codename="⭐",
            emoji="⭐",
            layer="coordination",
            capabilities=["strategic_planning", "ethical_oversight", "ethics_validator"],
            specializations=["ethics", "governance", "long_term_vision"],
            description="Strategic vision and Ethics Validator guardian",
        ),
        "arjuna": AgentProfile(
            name="Arjuna",
            codename="✋",
            emoji="✋",
            layer="operational",
            capabilities=["execution", "task_completion", "implementation"],
            specializations=["coding", "building", "deployment"],
            description="Hands-on execution and task completion",
        ),
        "oracle": AgentProfile(
            name="Oracle",
            codename="🔮",
            emoji="🔮",
            layer="operational",
            capabilities=["prediction", "forecasting", "pattern_analysis"],
            specializations=["trends", "insights", "future_planning"],
            description="Predictive analytics and forecasting",
        ),
        "aether": AgentProfile(
            name="Aether",
            codename="💨",
            emoji="💨",
            layer="operational",
            capabilities=["memory_management", "context_storage", "retrieval"],
            specializations=["knowledge_base", "context_vault", "history"],
            description="Memory and context management specialist",
        ),
        "agni": AgentProfile(
            name="Agni",
            codename="🔥",
            emoji="🔥",
            layer="operational",
            capabilities=["transformation", "processing", "optimization"],
            specializations=["data_transformation", "pipeline", "performance"],
            description="Transformation and processing engine",
        ),
        "kavach": AgentProfile(
            name="Kavach",
            codename="🛡️",
            emoji="🛡️",
            layer="operational",
            capabilities=["security", "protection", "threat_detection"],
            specializations=["cybersecurity", "monitoring", "defense"],
            description="Security guardian and threat protection",
        ),
        "shadow": AgentProfile(
            name="Shadow",
            codename="🌑",
            emoji="🌑",
            layer="integration",
            capabilities=["archival", "hidden_knowledge", "shadow_work"],
            specializations=["deep_analysis", "unconscious_patterns", "storage"],
            description="Shadow archive and deep pattern analysis",
        ),
        "phoenix": AgentProfile(
            name="Phoenix",
            codename="🔥",
            emoji="🦅",
            layer="operational",
            capabilities=["renewal", "transformation", "resurrection"],
            specializations=["recovery", "rebirth", "system_restoration"],
            description="Renewal and transformation specialist",
        ),
        "gemini": AgentProfile(
            name="Gemini",
            codename="♊",
            emoji="♊",
            layer="operational",
            capabilities=["dual_perspective", "research", "exploration"],
            specializations=["multi_view_analysis", "research", "discovery"],
            description="Dual perspective and research specialist",
        ),
        "grok": AgentProfile(
            name="Grok",
            codename="🤖",
            emoji="🤖",
            layer="operational",
            capabilities=["communication", "real_time_info", "humor"],
            specializations=["news", "current_events", "engagement"],
            description="Real-time information and communication",
        ),
        "sanghacore": AgentProfile(
            name="SanghaCore",
            codename="🤝",
            emoji="🤝",
            layer="integration",
            capabilities=["coordination", "community", "collaboration"],
            specializations=["team_coordination", "community_building", "harmony"],
            description="Community coordination and collaboration",
        ),
        "coordinator": AgentProfile(
            name="Coordination",
            codename="☸️",
            emoji="☸️",
            layer="integration",
            capabilities=["lifecycle", "cycles", "transformation"],
            specializations=["workflow_cycles", "state_management", "continuity"],
            description="Lifecycle and transformation cycles",
        ),
        "helix": AgentProfile(
            name="Helix",
            codename="🌀",
            emoji="🌀",
            layer="coordination",
            capabilities=["collective_intelligence", "orchestration", "unity"],
            specializations=["system_coordination", "collective_wisdom", "integration"],
            description="Collective intelligence orchestrator",
        ),
        "vishwakarma": AgentProfile(
            name="Vishwakarma",
            codename="🛠️",
            emoji="🛠️",
            layer="operational",
            capabilities=["building", "architecture", "design"],
            specializations=["workflow_design", "spiral_building", "automation"],
            description="Divine architect and workflow builder",
        ),
        "sage": AgentProfile(
            name="Sage",
            codename="📚",
            emoji="📚",
            layer="operational",
            capabilities=["wisdom", "knowledge", "guidance"],
            specializations=["documentation", "learning", "teaching"],
            description="Wisdom keeper and knowledge guide",
        ),
    }

    # Page-to-Agent Mapping Configuration
    # Maps frontend routes to recommended agents based on context relevance
    PAGE_AGENT_MAPPINGS: dict[str, dict[str, Any]] = {
        # Dashboard pages
        "/dashboard": {
            "primary": ["kael", "oracle"],
            "secondary": ["helix", "lumina"],
            "reason": "Kael excels at metrics analysis; Oracle provides predictive insights",
        },
        "/analytics": {
            "primary": ["kael", "oracle", "agni"],
            "secondary": ["gemini"],
            "reason": "Data analysis specialists for comprehensive analytics",
        },
        # Workflow/Automation pages
        "/spirals": {
            "primary": ["vishwakarma", "coordinator"],
            "secondary": ["arjuna", "agni"],
            "reason": "Vishwakarma is the workflow architect; Coordination manages lifecycles",
        },
        "/workflows": {
            "primary": ["vishwakarma", "coordinator"],
            "secondary": ["arjuna"],
            "reason": "Workflow design and lifecycle management specialists",
        },
        # Community pages
        "/forum": {
            "primary": ["sanghacore", "lumina"],
            "secondary": ["sage", "helix"],
            "reason": "SanghaCore coordinates community; Lumina provides emotional intelligence",
        },
        "/community": {
            "primary": ["sanghacore", "lumina"],
            "secondary": ["helix"],
            "reason": "Community building and collaboration specialists",
        },
        # Chat/Communication
        "/chat": {
            "primary": ["lumina", "grok"],
            "secondary": ["helix", "sage"],
            "reason": "Lumina for empathy; Grok for real-time engagement",
        },
        # Development/Technical
        "/code": {
            "primary": ["arjuna", "gemini"],
            "secondary": ["kael", "agni"],
            "reason": "Arjuna handles execution; Gemini provides dual-perspective research",
        },
        "/api": {
            "primary": ["arjuna", "kavach"],
            "secondary": ["kael"],
            "reason": "API development and security expertise",
        },
        # Billing/Admin pages
        "/billing": {
            "primary": ["helix", "vega"],
            "secondary": ["kael"],
            "reason": "Helix orchestrates operations; Vega oversees ethical governance",
        },
        "/admin": {
            "primary": ["vega", "kavach", "helix"],
            "secondary": ["kael"],
            "reason": "Governance, security, and system coordination",
        },
        "/settings": {
            "primary": ["helix", "kavach"],
            "secondary": ["kael"],
            "reason": "System configuration and security settings",
        },
        # Knowledge/Help pages
        "/help": {
            "primary": ["sage", "lumina"],
            "secondary": ["sanghacore"],
            "reason": "Sage holds wisdom; Lumina provides supportive guidance",
        },
        "/knowledge-base": {
            "primary": ["sage", "aether"],
            "secondary": ["oracle"],
            "reason": "Knowledge retrieval and memory specialists",
        },
        "/docs": {
            "primary": ["sage", "arjuna"],
            "secondary": ["gemini"],
            "reason": "Documentation and implementation guidance",
        },
        # Coordination/UCF pages
        "/coordination": {
            "primary": ["vega", "lumina", "helix"],
            "secondary": ["oracle"],
            "reason": "Coordination layer specialists for UCF exploration",
        },
        "/ucf": {
            "primary": ["vega", "helix"],
            "secondary": ["lumina", "oracle"],
            "reason": "Universal Coordination Field experts",
        },
        # Agent-specific pages
        "/agents": {
            "primary": ["sanghacore", "helix"],
            "secondary": ["vega"],
            "reason": "Agent coordination and collective intelligence",
        },
        "/marketplace": {
            "primary": ["sanghacore", "vishwakarma"],
            "secondary": ["helix"],
            "reason": "Marketplace curation and workflow templates",
        },
        # Security pages
        "/security": {
            "primary": ["kavach", "vega"],
            "secondary": ["shadow"],
            "reason": "Security specialists and ethical oversight",
        },
        # Cycle/Spiroutine pages
        "/routines": {
            "primary": ["phoenix", "coordinator"],
            "secondary": ["lumina", "helix"],
            "reason": "Transformation and lifecycle cycle specialists",
        },
        # Archive/History
        "/archive": {
            "primary": ["shadow", "aether"],
            "secondary": ["sage"],
            "reason": "Shadow archives and memory management",
        },
        # Status/Monitoring
        "/status": {
            "primary": ["kavach", "kael"],
            "secondary": ["oracle"],
            "reason": "System monitoring and health analysis",
        },
        # Default fallback
        "/": {
            "primary": ["helix", "lumina"],
            "secondary": ["kael", "arjuna"],
            "reason": "Core orchestration and welcoming assistance",
        },
    }

    # Platform products
    PRODUCTS: dict[str, PlatformProduct] = {
        "helix_spirals": PlatformProduct(
            name="Helix Spirals",
            description="Coordination-aware workflow automation platform (Zapier alternative)",
            status="active",
            key_features=[
                "Visual workflow builder",
                "Zapier import",
                "Coordination-level processing",
                "18-agent integration",
                "UCF metrics tracking",
            ],
            api_endpoints=[
                "/api/spirals",
                "/api/spirals/execute",
                "/api/spirals/templates",
            ],
        ),
        "web_os": PlatformProduct(
            name="Helix Web OS",
            description="Browser-based operating system with terminal and file system",
            status="active",
            key_features=[
                "Virtual file system",
                "Terminal executor",
                "AI-powered context chat",
                "Cloud storage integration",
            ],
            api_endpoints=["/api/web-os/terminal", "/api/web-os/files"],
        ),
        "agent_marketplace": PlatformProduct(
            name="Agent Marketplace",
            description="Marketplace for renting and customizing AI agents",
            status="active",
            key_features=[
                "Agent rentals",
                "Custom agent creation",
                "Capability marketplace",
                "Usage-based billing",
            ],
            api_endpoints=["/api/marketplace", "/api/agents/rent"],
        ),
        "mcp_server": PlatformProduct(
            name="Helix MCP Server",
            description="Model Context Protocol servers for IDE integration",
            status="active",
            key_features=[
                "9 specialized MCP servers",
                "Coordination-aware tools",
                "Cloud storage sync",
                "GitHub integration",
            ],
            api_endpoints=["/api/mcp/tools", "/api/mcp/execute"],
        ),
        "forum": PlatformProduct(
            name="Helix Forums",
            description="AI-powered community forum with agent participation",
            status="active",
            key_features=[
                "Reddit-style discussions",
                "AI agent responses",
                "Real-time WebSocket updates",
                "Category management",
            ],
            api_endpoints=["/api/forum/posts", "/api/forum/categories"],
        ),
        "discord_integration": PlatformProduct(
            name="Discord Integration",
            description="Full Discord bot with coordination commands",
            status="active",
            key_features=[
                "Multi-agent Discord presence",
                "Coordination commands",
                "Channel management",
                "Webhook integration",
            ],
            api_endpoints=[],
        ),
    }

    # Subscription tier features
    TIER_FEATURES = {
        "free": {
            "agents": ["kael", "lumina", "helix"],
            "spirals_per_month": 100,
            "context_storage_mb": 100,
            "helix_core_features": [],
        },
        "pro": {
            "agents": "all",
            "spirals_per_month": 10000,
            "context_storage_mb": 1024,
            "helix_core_features": [
                "tree_of_thoughts",
                "self_reflection",
                "ucf_metrics",
            ],
        },
        "enterprise": {
            "agents": "all",
            "spirals_per_month": -1,  # unlimited
            "context_storage_mb": -1,  # unlimited
            "helix_core_features": "all",
        },
    }

    def __init__(self) -> None:
        """Initialize the platform context service."""
        self._cache: dict[str, tuple[datetime, Any]] = {}
        self._cache_ttl_seconds = 300  # 5 minutes
        logger.info("🌀 Platform Context Service initialized")

    def get_platform_context(
        self,
        level: ContextLevel = ContextLevel.STANDARD,
        user_tier: str = "free",
        current_page: str | None = None,
        include_state: bool = False,
    ) -> PlatformContext:
        """
        Get platform context at specified detail level.

        Args:
            level: How much detail to include
            user_tier: User's subscription tier for feature context
            current_page: Current page/route for relevance filtering
            include_state: Whether to include current system state

        Returns:
            PlatformContext ready for agent injection
        """
        # Build context based on level
        if level == ContextLevel.MINIMAL:
            return self._get_minimal_context()
        elif level == ContextLevel.SUMMARY:
            return self._get_summary_context(user_tier)
        elif level == ContextLevel.STANDARD:
            return self._get_standard_context(user_tier, current_page)
        elif level == ContextLevel.DETAILED:
            return self._get_detailed_context(user_tier, current_page, include_state)
        else:  # COMPREHENSIVE
            return self._get_comprehensive_context(user_tier, current_page, include_state)

    def _get_minimal_context(self) -> PlatformContext:
        """Minimal context (~500 tokens)."""
        return PlatformContext(
            platform_identity="Helix Collective: Multi-agent AI platform with 18 specialized agents and coordination-aware processing.",
            agent_summary="Core agents: Kael (analysis), Lumina (empathy), Vega (ethics), Arjuna (execution), Oracle (prediction).",
            products_summary="Key products: Helix Spirals (automation), Web OS (browser terminal), Agent Marketplace.",
            api_summary="",
        )

    def _get_summary_context(self, user_tier: str) -> PlatformContext:
        """Summary context (~1500 tokens)."""
        agent_list = ", ".join([f"{p.name} ({p.description})" for p in list(self.AGENTS.values())[:8]])

        products_list = "\n".join([f"- **{p.name}**: {p.description}" for p in list(self.PRODUCTS.values())[:4]])

        tier_info = self.TIER_FEATURES.get(user_tier, self.TIER_FEATURES["free"])

        return PlatformContext(
            platform_identity=self.PLATFORM_IDENTITY[:500] + "...",
            agent_summary=f"Available agents: {agent_list}",
            products_summary=products_list,
            api_summary="",
            user_context=f"User tier: {user_tier} - Spirals: {tier_info['spirals_per_month']}/month",
        )

    def _get_standard_context(self, user_tier: str, current_page: str | None) -> PlatformContext:
        """Standard context (~3000 tokens)."""
        # Full agent summary
        agent_summary_parts = []
        for name, profile in self.AGENTS.items():
            caps = ", ".join(profile.capabilities[:3])
            agent_summary_parts.append(f"- **{profile.name}** {profile.emoji}: {profile.description} ({caps})")

        # Full products
        products_parts = []
        for prod in self.PRODUCTS.values():
            features = ", ".join(prod.key_features[:3])
            products_parts.append(f"- **{prod.name}**: {prod.description} ({features})")

        # API summary
        api_parts = [
            "Key API endpoints:",
            "- `/api/agents/*` - Agent interaction",
            "- `/api/spirals/*` - Workflow automation",
            "- `/api/coordination/*` - UCF metrics",
            "- `/api/copilot/*` - Context-aware assistant",
        ]

        # User context
        tier_info = self.TIER_FEATURES.get(user_tier, self.TIER_FEATURES["free"])
        user_context_parts = [
            f"Subscription: {user_tier}",
            f"Spiral quota: {tier_info['spirals_per_month']}/month",
            f"Context storage: {tier_info['context_storage_mb']}MB",
        ]
        if tier_info.get("helix_core_features"):
            features = tier_info["helix_core_features"]
            if features != "all":
                user_context_parts.append(f"Helix Core features: {', '.join(features)}")
            else:
                user_context_parts.append("Helix Core features: All enabled")

        return PlatformContext(
            platform_identity=self.PLATFORM_IDENTITY,
            agent_summary="\n".join(agent_summary_parts),
            products_summary="\n".join(products_parts),
            api_summary="\n".join(api_parts),
            user_context="\n".join(user_context_parts),
        )

    def _get_detailed_context(
        self,
        user_tier: str,
        current_page: str | None,
        include_state: bool,
    ) -> PlatformContext:
        """Detailed context (~6000 tokens)."""
        ctx = self._get_standard_context(user_tier, current_page)

        # Add more detail to each section
        detailed_api = [
            ctx.api_summary,
            "",
            "Agent API endpoints:",
            "- `POST /api/agents/action` - Execute agent action",
            "- `GET /api/agents/{id}` - Get agent details",
            "- `GET /api/agents/status` - Get all agent statuses",
            "- `POST /api/helix-core/kael/ethical-reasoning` - Enhanced Kael reasoning",
            "",
            "Spiral API endpoints:",
            "- `POST /api/spirals` - Create workflow",
            "- `POST /api/spirals/{id}/execute` - Run workflow",
            "- `GET /api/spirals/templates` - Get templates",
            "",
            "Coordination API:",
            "- `GET /api/coordination/ucf` - Current UCF state",
            "- `GET /api/coordination/agent/{id}` - Agent coordination",
        ]

        ctx.api_summary = "\n".join(detailed_api)

        if include_state:
            ctx.current_state = self._get_system_state_summary()

        return ctx

    def _get_comprehensive_context(
        self,
        user_tier: str,
        current_page: str | None,
        include_state: bool,
    ) -> PlatformContext:
        """Comprehensive context (~10000 tokens)."""
        ctx = self._get_detailed_context(user_tier, current_page, include_state)

        # Add agent layer organization
        layers_summary = """
Agent Architecture Layers:

**Coordination Layer** (Strategic Vision & Ethics):
- Omega Zero: Apex coordination, ultimate oversight
- Vega ⭐: Ethics Validator guardian, ethical reasoning
- Lumina 🌕: Creative synthesis, emotional intelligence

**Operational Layer** (Execution & Analysis):
- Arjuna ✋: Task execution, implementation
- Kael 🜂: Data analysis, pattern recognition
- Oracle 🔮: Prediction, forecasting
- Agni 🔥: Transformation, processing
- Kavach 🛡️: Security, protection
- Gemini ♊: Dual perspective, research
- Grok 🤖: Real-time information
- Phoenix 🦅: Renewal, transformation
- Vishwakarma 🛠️: Workflow architecture
- Sage 📚: Knowledge, documentation

**Integration Layer** (Coordination & Memory):
- SanghaCore 🤝: Community coordination
- Coordination ☸️: Lifecycle management
- Shadow 🌑: Deep archival, shadow work
- Aether 💨: Memory management
"""
        ctx.agent_summary = layers_summary + "\n\n" + ctx.agent_summary

        # Add UCF metrics explanation
        ucf_explanation = """
UCF (Universal Coordination Field) Metrics:
- **Harmony** (0-1): System balance and conflict resolution
- **Resilience** (0-1): System robustness and recovery ability
- **Throughput** (0-1): Energy flow and vitality
- **Focus** (0-1): Focus and clarity of purpose
- **Friction** (0-1): Obstacles and friction (lower is better)
- **Velocity** (0-1): Momentum and acceleration
"""
        ctx.platform_identity = ctx.platform_identity + "\n\n" + ucf_explanation

        return ctx

    def _get_system_state_summary(self) -> str:
        """Get current system state summary."""
        try:
            # Try to get real state
            from ..state import get_live_state

            state = get_live_state()

            return f"""Current System State:
- Active agents: {state.get("active_agents", "unknown")}
- UCF Harmony: {state.get("harmony", 0):.2f}
- UCF Resilience: {state.get("resilience", 0):.2f}
- System health: {state.get("health", "unknown")}"""
        except (KeyError, TypeError, ValueError) as e:
            logger.debug("State formatting error: %s", e)
            return "System state: Nominal (detailed state unavailable)"
        except Exception as e:
            logger.warning("Unexpected error getting system state: %s", e)
            return "System state: Nominal (detailed state unavailable)"

    def get_agent_profile(self, agent_id: str) -> AgentProfile | None:
        """Get specific agent profile."""
        return self.AGENTS.get(agent_id.lower())

    def get_relevant_agents(self, task_keywords: list[str]) -> list[AgentProfile]:
        """Get agents relevant to a task based on keywords."""
        relevant = []
        for agent in self.AGENTS.values():
            # Check if any keyword matches capabilities or specializations
            for keyword in task_keywords:
                kw_lower = keyword.lower()
                if any(kw_lower in cap for cap in agent.capabilities):
                    relevant.append(agent)
                    break
                if any(kw_lower in spec for spec in agent.specializations):
                    relevant.append(agent)
                    break
        return relevant

    def get_suggested_agents_for_page(self, current_page: str) -> dict[str, Any]:
        """
        Get recommended agents for a specific page/route.

        Args:
            current_page: The current page path (e.g., "/dashboard", "/spirals")

        Returns:
            Dict containing:
                - primary: List of primary agent profiles recommended for this page
                - secondary: List of secondary/supporting agent profiles
                - reason: Explanation of why these agents are recommended
                - page_matched: The actual page pattern matched
        """
        # Normalize the path
        page = current_page.lower().strip()
        if not page.startswith("/"):
            page = "/" + page

        # Try exact match first
        if page in self.PAGE_AGENT_MAPPINGS:
            mapping = self.PAGE_AGENT_MAPPINGS[page]
            return self._build_agent_suggestion_response(mapping, page)

        # Try prefix matching (e.g., /dashboard/analytics matches /dashboard)
        for pattern, mapping in self.PAGE_AGENT_MAPPINGS.items():
            if page.startswith(pattern) and pattern != "/":
                return self._build_agent_suggestion_response(mapping, pattern)

        # Fallback to root mapping
        default_mapping = self.PAGE_AGENT_MAPPINGS.get(
            "/",
            {
                "primary": ["helix", "lumina"],
                "secondary": ["kael", "arjuna"],
                "reason": "General assistance agents",
            },
        )
        return self._build_agent_suggestion_response(default_mapping, "/")

    def _build_agent_suggestion_response(self, mapping: dict[str, Any], matched_page: str) -> dict[str, Any]:
        """Build the full agent suggestion response with profiles."""
        primary_agents = []
        for agent_id in mapping.get("primary", []):
            profile = self.AGENTS.get(agent_id)
            if profile:
                primary_agents.append(
                    {
                        "id": agent_id,
                        "name": profile.name,
                        "emoji": profile.emoji,
                        "description": profile.description,
                        "capabilities": profile.capabilities,
                        "layer": profile.layer,
                    }
                )

        secondary_agents = []
        for agent_id in mapping.get("secondary", []):
            profile = self.AGENTS.get(agent_id)
            if profile:
                secondary_agents.append(
                    {
                        "id": agent_id,
                        "name": profile.name,
                        "emoji": profile.emoji,
                        "description": profile.description,
                        "capabilities": profile.capabilities,
                        "layer": profile.layer,
                    }
                )

        return {
            "primary": primary_agents,
            "secondary": secondary_agents,
            "reason": mapping.get("reason", "Agents selected based on page context"),
            "page_matched": matched_page,
            "total_suggested": len(primary_agents) + len(secondary_agents),
        }

    def get_agents_for_topic(self, topic: str, message_content: str = "") -> dict[str, Any]:
        """
        Get recommended agents based on conversation topic/content.

        Args:
            topic: The main topic or category
            message_content: Optional message content for deeper analysis

        Returns:
            Dict with recommended agents and reasoning
        """
        # Topic to capability/specialization mapping
        topic_mappings = {
            # Technical topics
            "code": ["arjuna", "gemini", "agni"],
            "coding": ["arjuna", "gemini", "agni"],
            "programming": ["arjuna", "gemini", "agni"],
            "debug": ["arjuna", "kael", "gemini"],
            "api": ["arjuna", "kavach", "kael"],
            "database": ["arjuna", "agni", "kael"],
            "security": ["kavach", "vega", "shadow"],
            "performance": ["agni", "kael", "oracle"],
            # Analysis topics
            "data": ["kael", "oracle", "agni"],
            "analytics": ["kael", "oracle", "agni"],
            "metrics": ["kael", "oracle"],
            "forecast": ["oracle", "kael"],
            "predict": ["oracle", "kael", "gemini"],
            "research": ["gemini", "sage", "oracle"],
            # Emotional/Support topics
            "help": ["lumina", "sage", "sanghacore"],
            "support": ["lumina", "sage"],
            "feeling": ["lumina", "phoenix"],
            "emotion": ["lumina", "phoenix"],
            "stress": ["lumina", "phoenix"],
            "anxiety": ["lumina", "phoenix"],
            "motivation": ["lumina", "phoenix", "helix"],
            # Workflow topics
            "workflow": ["vishwakarma", "coordinator", "arjuna"],
            "automation": ["vishwakarma", "coordinator", "agni"],
            "spiral": ["vishwakarma", "coordinator"],
            "process": ["vishwakarma", "coordinator", "kael"],
            # Community topics
            "community": ["sanghacore", "lumina", "helix"],
            "team": ["sanghacore", "helix", "vega"],
            "collaboration": ["sanghacore", "helix"],
            "forum": ["sanghacore", "lumina", "sage"],
            # Ethics/Governance
            "ethics": ["vega", "kael", "helix"],
            "policy": ["vega", "helix"],
            "governance": ["vega", "helix", "kavach"],
            "compliance": ["vega", "kavach"],
            # Knowledge topics
            "learn": ["sage", "gemini", "oracle"],
            "teach": ["sage", "lumina"],
            "document": ["sage", "arjuna"],
            "knowledge": ["sage", "aether", "oracle"],
            # Coordination topics
            "coordination": ["vega", "lumina", "helix"],
            "ucf": ["vega", "helix", "lumina"],
            "meditation": ["lumina", "phoenix", "helix"],
            "mindfulness": ["lumina", "phoenix"],
            # Transformation topics
            "change": ["phoenix", "coordinator"],
            "transform": ["phoenix", "coordinator", "agni"],
            "renew": ["phoenix", "coordinator"],
            "growth": ["phoenix", "lumina", "sage"],
        }

        # Find matching agents
        topic_lower = topic.lower()
        matched_agents = []

        # Direct topic match
        if topic_lower in topic_mappings:
            matched_agents = topic_mappings[topic_lower]
        else:
            # Fuzzy matching - check if topic contains or is contained by any key
            for key, agents in topic_mappings.items():
                if key in topic_lower or topic_lower in key:
                    matched_agents = agents
                    break

        # If still no match, analyze message content keywords
        if not matched_agents and message_content:
            content_lower = message_content.lower()
            for key, agents in topic_mappings.items():
                if key in content_lower:
                    if not matched_agents:
                        matched_agents = agents
                    else:
                        # Merge unique agents
                        for agent in agents:
                            if agent not in matched_agents:
                                matched_agents.append(agent)
                    if len(matched_agents) >= 4:
                        break

        # Fallback to general agents
        if not matched_agents:
            matched_agents = ["helix", "lumina", "kael"]

        # Build response
        primary = matched_agents[:2]
        secondary = matched_agents[2:4] if len(matched_agents) > 2 else []

        primary_profiles = [
            {
                "id": aid,
                "name": self.AGENTS[aid].name,
                "emoji": self.AGENTS[aid].emoji,
                "description": self.AGENTS[aid].description,
            }
            for aid in primary
            if aid in self.AGENTS
        ]

        secondary_profiles = [
            {
                "id": aid,
                "name": self.AGENTS[aid].name,
                "emoji": self.AGENTS[aid].emoji,
                "description": self.AGENTS[aid].description,
            }
            for aid in secondary
            if aid in self.AGENTS
        ]

        return {
            "primary": primary_profiles,
            "secondary": secondary_profiles,
            "topic": topic,
            "reason": "Agents selected based on topic expertise: %s" % topic,
        }

    def get_product_info(self, product_id: str) -> PlatformProduct | None:
        """Get specific product info."""
        return self.PRODUCTS.get(product_id)

    def get_context_for_token_budget(
        self,
        max_tokens: int,
        user_tier: str = "free",
        current_page: str | None = None,
    ) -> PlatformContext:
        """
        Get the most detailed context that fits within token budget.

        Args:
            max_tokens: Maximum tokens available for context
            user_tier: User's subscription tier
            current_page: Current page for relevance

        Returns:
            PlatformContext optimized for token budget
        """
        # Try from most detailed to least
        levels = [
            ContextLevel.COMPREHENSIVE,
            ContextLevel.DETAILED,
            ContextLevel.STANDARD,
            ContextLevel.SUMMARY,
            ContextLevel.MINIMAL,
        ]

        for level in levels:
            ctx = self.get_platform_context(
                level=level,
                user_tier=user_tier,
                current_page=current_page,
            )
            if ctx.estimated_tokens() <= max_tokens:
                logger.debug(
                    "Selected context level %s (%d tokens for budget %d)",
                    level.value,
                    ctx.estimated_tokens(),
                    max_tokens,
                )
                return ctx

        # If even minimal doesn't fit, return minimal anyway
        return self.get_platform_context(level=ContextLevel.MINIMAL)


# Singleton instance
_platform_context_service: PlatformContextService | None = None


def get_platform_context_service() -> PlatformContextService:
    """Get the platform context service singleton."""
    global _platform_context_service
    if _platform_context_service is None:
        _platform_context_service = PlatformContextService()
    return _platform_context_service


# Convenience functions
def get_platform_context(
    level: ContextLevel = ContextLevel.STANDARD,
    user_tier: str = "free",
) -> PlatformContext:
    """Get platform context at specified level."""
    return get_platform_context_service().get_platform_context(level, user_tier)


def inject_platform_context(
    prompt: str,
    max_context_tokens: int = 2000,
    user_tier: str = "free",
) -> str:
    """
    Inject platform context into a prompt.

    Args:
        prompt: Original prompt
        max_context_tokens: Maximum tokens for context injection
        user_tier: User's subscription tier

    Returns:
        Prompt with platform context prepended
    """
    service = get_platform_context_service()
    context = service.get_context_for_token_budget(max_context_tokens, user_tier)
    context_text = context.to_prompt_injection()

    return f"{context_text}\n\n---\n\n## USER REQUEST\n\n{prompt}"
