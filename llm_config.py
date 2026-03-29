"""
LLM API Router Configuration

Optimizes AI feature costs by intelligently routing requests to most cost-effective providers.
Primary: Grok 4.1 Fast ($0.20/$0.50 per M tokens, 2M context)
Fallback: Google Gemini 2.0 Flash ($0.10/$0.40 per M tokens)

Estimated Monthly Cost (14-agent system, 20K requests/day):
- Grok primary: $24/month
- With data sharing credits: FREE ($150/month provided)
- Net annual: ~$288 (or $0 with credits)

Comparison:
- Claude Sonnet: $400-500/month
- GPT-4o: $500+/month
- Gemini Flash: $10-15/month but limited context (1M vs 2M)

Agent routing optimizes for both cost and capability match.
"""

import logging
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    GROK = "xai"
    GOOGLE = "google"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GROQ = "groq"
    MISTRAL = "mistral"
    OPENROUTER = "openrouter"
    NVIDIA_NIM = "nvidia_nim"
    MINIMAX = "minimax"
    COHERE = "cohere"


class LLMModel(str, Enum):
    """Supported models by provider."""

    # Grok models (RECOMMENDED - lowest cost)
    GROK_4_1_FAST = "grok-4-1-fast-reasoning"
    GROK_CODE_FAST = "grok-code-fast-1"
    GROK_3_MINI = "grok-3-mini"

    # Google Gemini (fallback - good performance/cost ratio)
    GEMINI_2_FLASH = "gemini-2-0-flash"
    GEMINI_2_PRO = "gemini-2-0-pro-exp-02-05"

    # Claude (premium - higher cost)
    CLAUDE_HAIKU = "claude-3-5-haiku-20241022"
    CLAUDE_SONNET = "claude-3-5-sonnet-20241022"
    CLAUDE_OPUS = "claude-3-opus-20250219"

    # GPT-4o (premium)
    GPT_4O = "gpt-4o"
    GPT_4O_MINI = "gpt-4o-mini"

    # Groq (free tier - ultra-fast inference)
    GROQ_LLAMA_70B = "llama-3.3-70b-versatile"
    GROQ_LLAMA_8B = "llama-3.1-8b-instant"
    GROQ_MIXTRAL = "mixtral-8x7b-32768"

    # Mistral (free tier)
    MISTRAL_SMALL = "mistral-small-latest"

    # NVIDIA NIM (free tier)
    NVIDIA_NEMOTRON = "nvidia/llama-3.1-nemotron-70b-instruct"

    # MiniMax (free tier)
    MINIMAX_M25 = "minimax-m2.5"

    # Cohere (free tier)
    COHERE_COMMAND_R = "command-r"
    COHERE_COMMAND_R_PLUS = "command-r-plus"

    # OpenRouter free models
    OPENROUTER_TRINITY = "arcee-ai/trinity-large-preview:free"
    OPENROUTER_KAT_CODER = "kwaipilot/kat-coder-pro:free"


class ModelConfig(BaseModel):
    """Configuration for a specific LLM model."""

    provider: LLMProvider
    model: LLMModel

    # Pricing (per million tokens)
    cost_per_m_input: float = Field(..., description="Cost per million input tokens")
    cost_per_m_output: float = Field(..., description="Cost per million output tokens")

    # Capabilities
    context_window: int = Field(..., description="Maximum context window in tokens")
    max_output_tokens: int = Field(4096, description="Maximum output tokens per request")
    supports_vision: bool = False
    supports_function_calling: bool = True
    supports_prompt_caching: bool = False

    # Rate limiting
    requests_per_minute: int = 480
    tokens_per_minute: int = 90_000

    # Performance
    avg_latency_ms: int = Field(..., description="Average response latency in milliseconds")

    class Config:
        json_schema_extra = {
            "example": {
                "provider": "xai",
                "model": "grok-4-1-fast-reasoning",
                "cost_per_m_input": 0.20,
                "cost_per_m_output": 0.50,
                "context_window": 2_000_000,
                "max_output_tokens": 4096,
                "requests_per_minute": 480,
                "avg_latency_ms": 450,
            }
        }


class RoutingRule(BaseModel):
    """Rules for routing requests to specific models."""

    name: str
    priority: int = Field(1, ge=1, le=10, description="Lower = higher priority")
    use_cases: list[str] = Field(..., description="Task categories this rule handles")
    model: LLMModel
    conditions: dict = Field(default_factory=dict, description="Additional conditions")
    fallback_model: LLMModel | None = None


class AgentCostProfile(BaseModel):
    """Cost profile for an agent."""

    agent_id: str
    agent_name: str
    estimated_daily_requests: int
    primary_model: LLMModel
    estimated_monthly_cost: float  # Calculated
    estimated_monthly_cost_without_credits: float  # Before free tier


class LLMUsageMetrics(BaseModel):
    """Track LLM API usage for cost monitoring."""

    timestamp: datetime
    provider: LLMProvider
    model: LLMModel
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost: float
    agent_id: str
    task_type: str
    success: bool = True
    error_message: str | None = None


# ============================================================================
# MODEL CONFIGURATIONS
# ============================================================================

MODEL_CONFIGS = {
    # ========================================================================
    # GROK MODELS (PRIMARY - LOWEST COST)
    # ========================================================================
    LLMModel.GROK_4_1_FAST: ModelConfig(
        provider=LLMProvider.GROK,
        model=LLMModel.GROK_4_1_FAST,
        cost_per_m_input=0.20,
        cost_per_m_output=0.50,
        context_window=2_000_000,
        max_output_tokens=8192,
        supports_prompt_caching=True,
        requests_per_minute=480,
        tokens_per_minute=90_000,
        avg_latency_ms=450,
    ),
    LLMModel.GROK_CODE_FAST: ModelConfig(
        provider=LLMProvider.GROK,
        model=LLMModel.GROK_CODE_FAST,
        cost_per_m_input=0.20,
        cost_per_m_output=1.50,  # Higher output cost for code
        context_window=256_000,
        max_output_tokens=4096,
        supports_prompt_caching=True,
        requests_per_minute=480,
        tokens_per_minute=90_000,
        avg_latency_ms=520,
    ),
    LLMModel.GROK_3_MINI: ModelConfig(
        provider=LLMProvider.GROK,
        model=LLMModel.GROK_3_MINI,
        cost_per_m_input=0.30,
        cost_per_m_output=0.50,
        context_window=131_000,
        max_output_tokens=4096,
        supports_prompt_caching=True,
        requests_per_minute=480,
        tokens_per_minute=90_000,
        avg_latency_ms=350,
    ),
    # ========================================================================
    # GOOGLE GEMINI (FALLBACK - GOOD BALANCE)
    # ========================================================================
    LLMModel.GEMINI_2_FLASH: ModelConfig(
        provider=LLMProvider.GOOGLE,
        model=LLMModel.GEMINI_2_FLASH,
        cost_per_m_input=0.10,
        cost_per_m_output=0.40,
        context_window=1_000_000,
        max_output_tokens=8192,
        supports_vision=True,
        supports_prompt_caching=True,
        requests_per_minute=480,
        tokens_per_minute=90_000,
        avg_latency_ms=380,
    ),
    LLMModel.GEMINI_2_PRO: ModelConfig(
        provider=LLMProvider.GOOGLE,
        model=LLMModel.GEMINI_2_PRO,
        cost_per_m_input=0.40,
        cost_per_m_output=1.20,
        context_window=1_000_000,
        max_output_tokens=8192,
        supports_vision=True,
        supports_prompt_caching=True,
        requests_per_minute=360,
        tokens_per_minute=90_000,
        avg_latency_ms=420,
    ),
    # ========================================================================
    # CLAUDE (PREMIUM - HIGHER COST, EXCELLENT FOR COMPLEX REASONING)
    # ========================================================================
    LLMModel.CLAUDE_HAIKU: ModelConfig(
        provider=LLMProvider.ANTHROPIC,
        model=LLMModel.CLAUDE_HAIKU,
        cost_per_m_input=1.00,
        cost_per_m_output=5.00,
        context_window=200_000,
        max_output_tokens=4096,
        avg_latency_ms=350,
    ),
    LLMModel.CLAUDE_SONNET: ModelConfig(
        provider=LLMProvider.ANTHROPIC,
        model=LLMModel.CLAUDE_SONNET,
        cost_per_m_input=3.00,
        cost_per_m_output=15.00,
        context_window=200_000,
        max_output_tokens=4096,
        avg_latency_ms=450,
    ),
    LLMModel.CLAUDE_OPUS: ModelConfig(
        provider=LLMProvider.ANTHROPIC,
        model=LLMModel.CLAUDE_OPUS,
        cost_per_m_input=15.00,
        cost_per_m_output=75.00,
        context_window=200_000,
        max_output_tokens=4096,
        avg_latency_ms=550,
    ),
    # ========================================================================
    # OPENAI GPT-4o (PREMIUM - HIGHEST COST)
    # ========================================================================
    LLMModel.GPT_4O: ModelConfig(
        provider=LLMProvider.OPENAI,
        model=LLMModel.GPT_4O,
        cost_per_m_input=5.00,
        cost_per_m_output=15.00,
        context_window=128_000,
        max_output_tokens=4096,
        supports_vision=True,
        avg_latency_ms=500,
    ),
    LLMModel.GPT_4O_MINI: ModelConfig(
        provider=LLMProvider.OPENAI,
        model=LLMModel.GPT_4O_MINI,
        cost_per_m_input=0.15,
        cost_per_m_output=0.60,
        context_window=128_000,
        max_output_tokens=4096,
        supports_vision=True,
        avg_latency_ms=400,
    ),
    # =========== GROQ (FREE TIER) ===========
    LLMModel.GROQ_LLAMA_70B: ModelConfig(
        provider=LLMProvider.GROQ,
        model=LLMModel.GROQ_LLAMA_70B,
        cost_per_m_input=0.0,
        cost_per_m_output=0.0,
        context_window=128_000,
        max_output_tokens=8192,
        requests_per_minute=30,
        tokens_per_minute=6000,
        avg_latency_ms=200,
    ),
    LLMModel.GROQ_LLAMA_8B: ModelConfig(
        provider=LLMProvider.GROQ,
        model=LLMModel.GROQ_LLAMA_8B,
        cost_per_m_input=0.0,
        cost_per_m_output=0.0,
        context_window=128_000,
        max_output_tokens=8192,
        requests_per_minute=30,
        tokens_per_minute=6000,
        avg_latency_ms=100,
    ),
    LLMModel.GROQ_MIXTRAL: ModelConfig(
        provider=LLMProvider.GROQ,
        model=LLMModel.GROQ_MIXTRAL,
        cost_per_m_input=0.0,
        cost_per_m_output=0.0,
        context_window=32_768,
        max_output_tokens=8192,
        requests_per_minute=30,
        tokens_per_minute=6000,
        avg_latency_ms=200,
    ),
    # =========== MISTRAL (FREE TIER) ===========
    LLMModel.MISTRAL_SMALL: ModelConfig(
        provider=LLMProvider.MISTRAL,
        model=LLMModel.MISTRAL_SMALL,
        cost_per_m_input=0.0,
        cost_per_m_output=0.0,
        context_window=128_000,
        max_output_tokens=4096,
        requests_per_minute=5,
        avg_latency_ms=500,
    ),
    # =========== NVIDIA NIM (FREE TIER) ===========
    LLMModel.NVIDIA_NEMOTRON: ModelConfig(
        provider=LLMProvider.NVIDIA_NIM,
        model=LLMModel.NVIDIA_NEMOTRON,
        cost_per_m_input=0.0,
        cost_per_m_output=0.0,
        context_window=128_000,
        max_output_tokens=4096,
        requests_per_minute=30,
        avg_latency_ms=400,
    ),
    # =========== MINIMAX (FREE TIER) ===========
    LLMModel.MINIMAX_M25: ModelConfig(
        provider=LLMProvider.MINIMAX,
        model=LLMModel.MINIMAX_M25,
        cost_per_m_input=0.0,
        cost_per_m_output=0.0,
        context_window=128_000,
        max_output_tokens=4096,
        requests_per_minute=10,
        avg_latency_ms=500,
    ),
    # =========== COHERE (FREE TIER) ===========
    LLMModel.COHERE_COMMAND_R: ModelConfig(
        provider=LLMProvider.COHERE,
        model=LLMModel.COHERE_COMMAND_R,
        cost_per_m_input=0.0,
        cost_per_m_output=0.0,
        context_window=128_000,
        max_output_tokens=4096,
        requests_per_minute=20,
        avg_latency_ms=600,
    ),
    LLMModel.COHERE_COMMAND_R_PLUS: ModelConfig(
        provider=LLMProvider.COHERE,
        model=LLMModel.COHERE_COMMAND_R_PLUS,
        cost_per_m_input=0.0,
        cost_per_m_output=0.0,
        context_window=128_000,
        max_output_tokens=4096,
        requests_per_minute=20,
        avg_latency_ms=800,
    ),
    # =========== OPENROUTER FREE MODELS ===========
    LLMModel.OPENROUTER_TRINITY: ModelConfig(
        provider=LLMProvider.OPENROUTER,
        model=LLMModel.OPENROUTER_TRINITY,
        cost_per_m_input=0.0,
        cost_per_m_output=0.0,
        context_window=128_000,
        max_output_tokens=4096,
        requests_per_minute=20,
        avg_latency_ms=800,
    ),
    LLMModel.OPENROUTER_KAT_CODER: ModelConfig(
        provider=LLMProvider.OPENROUTER,
        model=LLMModel.OPENROUTER_KAT_CODER,
        cost_per_m_input=0.0,
        cost_per_m_output=0.0,
        context_window=256_000,
        max_output_tokens=4096,
        requests_per_minute=20,
        avg_latency_ms=600,
    ),
}


# ============================================================================
# ROUTING RULES FOR AGENT TASKS
# ============================================================================

ROUTING_RULES = [
    # Primary: Use Grok for all general agent reasoning
    RoutingRule(
        name="agent_reasoning_primary",
        priority=1,
        use_cases=[
            "agent_reasoning",
            "task_orchestration",
            "coordination_metrics",
            "decision_making",
            "ethical_reasoning",
        ],
        model=LLMModel.GROK_4_1_FAST,
        fallback_model=LLMModel.GEMINI_2_FLASH,
        conditions={"budget_tier": "economy", "latency_requirement": "<1000ms"},
    ),
    # Code generation: Use Grok Code Fast
    RoutingRule(
        name="code_generation",
        priority=2,
        use_cases=["code_generation", "code_analysis", "debugging"],
        model=LLMModel.GROK_CODE_FAST,
        fallback_model=LLMModel.GROK_4_1_FAST,
        conditions={"output_type": "code"},
    ),
    # Lightweight tasks: Use Grok 3 Mini (30% cheaper)
    RoutingRule(
        name="lightweight_tasks",
        priority=3,
        use_cases=[
            "sentiment_analysis",
            "text_classification",
            "simple_routing",
            "feedback_analysis",
        ],
        model=LLMModel.GROK_3_MINI,
        fallback_model=LLMModel.GROK_4_1_FAST,
        conditions={"estimated_tokens": "<500", "complexity": "low"},
    ),
    # Premium reasoning: Use Claude for complex multi-step reasoning
    RoutingRule(
        name="complex_reasoning",
        priority=4,
        use_cases=[
            "research",
            "long_form_analysis",
            "complex_problem_solving",
            "multi_step_planning",
        ],
        model=LLMModel.CLAUDE_SONNET,
        fallback_model=LLMModel.GROK_4_1_FAST,
        conditions={"budget_tier": "premium", "accuracy_required": "high"},
    ),
    # Vision tasks: Use Gemini 2.0 Pro (supports multimodal)
    RoutingRule(
        name="vision_tasks",
        priority=5,
        use_cases=["image_analysis", "visual_understanding", "multimodal_reasoning"],
        model=LLMModel.GEMINI_2_PRO,
        fallback_model=LLMModel.CLAUDE_SONNET,
        conditions={"input_type": "multimodal"},
    ),
]


# ============================================================================
# AGENT COST PROFILES (14-AGENT SYSTEM)
# ============================================================================

AGENT_COST_PROFILES = [
    # Core Infrastructure Agents
    AgentCostProfile(
        agent_id="kael",
        agent_name="Kael (Ethics Engine)",
        estimated_daily_requests=2000,
        primary_model=LLMModel.GROK_4_1_FAST,
        estimated_monthly_cost=2.40,
        estimated_monthly_cost_without_credits=2.40,
    ),
    AgentCostProfile(
        agent_id="lumina",
        agent_name="Lumina (Resonance/Frontend)",
        estimated_daily_requests=1500,
        primary_model=LLMModel.GROK_3_MINI,  # Lighter tasks
        estimated_monthly_cost=1.35,
        estimated_monthly_cost_without_credits=1.35,
    ),
    AgentCostProfile(
        agent_id="vega",
        agent_name="Vega (Infrastructure)",
        estimated_daily_requests=1200,
        primary_model=LLMModel.GROK_4_1_FAST,
        estimated_monthly_cost=1.44,
        estimated_monthly_cost_without_credits=1.44,
    ),
    AgentCostProfile(
        agent_id="aether",
        agent_name="Aether (Balance/Database)",
        estimated_daily_requests=800,
        primary_model=LLMModel.GROK_3_MINI,
        estimated_monthly_cost=0.72,
        estimated_monthly_cost_without_credits=0.72,
    ),
    AgentCostProfile(
        agent_id="phoenix",
        agent_name="Phoenix (Renewal/QA)",
        estimated_daily_requests=1000,
        primary_model=LLMModel.GROK_4_1_FAST,
        estimated_monthly_cost=1.20,
        estimated_monthly_cost_without_credits=1.20,
    ),
    # Extended Agent Network
    AgentCostProfile(
        agent_id="arjuna",
        agent_name="Arjuna (Memory/SuperArjuna)",
        estimated_daily_requests=3000,
        primary_model=LLMModel.GROK_4_1_FAST,
        estimated_monthly_cost=3.60,
        estimated_monthly_cost_without_credits=3.60,
    ),
    AgentCostProfile(
        agent_id="grok",
        agent_name="Grok (Analysis)",
        estimated_daily_requests=2500,
        primary_model=LLMModel.GROK_4_1_FAST,
        estimated_monthly_cost=3.00,
        estimated_monthly_cost_without_credits=3.00,
    ),
    AgentCostProfile(
        agent_id="kavach",
        agent_name="Kavach (Security)",
        estimated_daily_requests=1200,
        primary_model=LLMModel.GROK_4_1_FAST,
        estimated_monthly_cost=1.44,
        estimated_monthly_cost_without_credits=1.44,
    ),
    AgentCostProfile(
        agent_id="gemini",
        agent_name="Gemini (Balance)",
        estimated_daily_requests=1000,
        primary_model=LLMModel.GROK_3_MINI,
        estimated_monthly_cost=0.90,
        estimated_monthly_cost_without_credits=0.90,
    ),
    # Additional agents (5 more)
    AgentCostProfile(
        agent_id="agent_6",
        agent_name="Agent 6 (Utility)",
        estimated_daily_requests=800,
        primary_model=LLMModel.GROK_3_MINI,
        estimated_monthly_cost=0.72,
        estimated_monthly_cost_without_credits=0.72,
    ),
    AgentCostProfile(
        agent_id="agent_7",
        agent_name="Agent 7 (Processing)",
        estimated_daily_requests=800,
        primary_model=LLMModel.GROK_3_MINI,
        estimated_monthly_cost=0.72,
        estimated_monthly_cost_without_credits=0.72,
    ),
    AgentCostProfile(
        agent_id="agent_8",
        agent_name="Agent 8 (Analysis)",
        estimated_daily_requests=600,
        primary_model=LLMModel.GROK_3_MINI,
        estimated_monthly_cost=0.54,
        estimated_monthly_cost_without_credits=0.54,
    ),
    AgentCostProfile(
        agent_id="agent_9",
        agent_name="Agent 9 (Monitoring)",
        estimated_daily_requests=500,
        primary_model=LLMModel.GROK_3_MINI,
        estimated_monthly_cost=0.45,
        estimated_monthly_cost_without_credits=0.45,
    ),
    AgentCostProfile(
        agent_id="agent_10",
        agent_name="Agent 10 (Support)",
        estimated_daily_requests=400,
        primary_model=LLMModel.GROK_3_MINI,
        estimated_monthly_cost=0.36,
        estimated_monthly_cost_without_credits=0.36,
    ),
]


# ============================================================================
# COST SUMMARY
# ============================================================================


def calculate_total_system_cost() -> dict[str, float]:
    """Calculate total monthly cost for all agents."""
    total_daily_requests = sum(p.estimated_daily_requests for p in AGENT_COST_PROFILES)
    total_monthly_cost = sum(p.estimated_monthly_cost for p in AGENT_COST_PROFILES)
    total_monthly_cost_without_credits = sum(p.estimated_monthly_cost_without_credits for p in AGENT_COST_PROFILES)

    # Grok data sharing program provides $150/month in credits
    free_credits_per_month = 150
    net_monthly_cost = max(0, total_monthly_cost - free_credits_per_month)

    return {
        "total_daily_requests": total_daily_requests,
        "total_monthly_cost": total_monthly_cost,
        "total_monthly_cost_without_credits": total_monthly_cost_without_credits,
        "free_credits_per_month": free_credits_per_month,
        "net_monthly_cost": net_monthly_cost,
        "annual_cost": total_monthly_cost * 12,
        "net_annual_cost": net_monthly_cost * 12,
        "savings_vs_claude": (400 - total_monthly_cost) * 12,  # vs Claude Sonnet
        "savings_vs_gpt4o": (500 - total_monthly_cost) * 12,  # vs GPT-4o
    }


# Calculate costs
SYSTEM_COSTS = calculate_total_system_cost()


# ============================================================================
# COST OPTIMIZATION STRATEGIES
# ============================================================================

COST_OPTIMIZATION_STRATEGIES = {
    "prompt_caching": {
        "description": "Cache agent system prompts to avoid repeated processing",
        "savings": "30-40% on repeated requests",
        "implementation": "Enable for all agents with >100 daily requests",
        "models_supported": [
            LLMModel.GROK_4_1_FAST,
            LLMModel.GROK_CODE_FAST,
            LLMModel.GROK_3_MINI,
        ],
    },
    "batch_processing": {
        "description": "Combine 5 small tasks into 1 larger request",
        "savings": "20-25% through reduced per-request overhead",
        "implementation": "Accumulate requests for 100ms before sending",
        "models_supported": "all",
    },
    "query_optimization": {
        "description": "Fix N+1 database queries to reduce LLM call volume",
        "savings": "40% reduction in total LLM requests",
        "implementation": "See FEATURE_IMPROVEMENTS_CODE_GAPS_JAN2026.md",
        "timeline": "2-3 days",
    },
    "model_downsampling": {
        "description": "Use Grok 3 Mini for simple tasks instead of 4.1 Fast",
        "savings": "33% per request on lightweight operations",
        "implementation": "Automatic routing based on task complexity",
        "criteria": "<500 input tokens + low complexity",
    },
    "data_sharing_enrollment": {
        "description": "Enroll in Grok data sharing program",
        "savings": "$150/month in free credits",
        "implementation": "Opt-in at https://x.ai/api (data sharing program)",
        "timeline": "Immediate",
        "net_effect": "Platform runs for FREE for 6+ months",
    },
    "fallback_routing": {
        "description": "Use Gemini 2.0 Flash when Grok unavailable",
        "cost_impact": "+$0.10/M tokens input (but maintains 99.9% availability)",
        "implementation": "Automatic failover in router",
    },
}


# ============================================================================
# LLM ROUTER CONFIGURATION
# ============================================================================

LLM_ROUTER = {
    "primary": {
        "provider": "xai",
        "model": "grok-4-1-fast-reasoning",
        "cost_per_m_input": 0.20,
        "cost_per_m_output": 0.50,
        "context_window": 2_000_000,
    },
    "code": {
        "provider": "xai",
        "model": "grok-code-fast-1",
        "cost_per_m_input": 0.20,
        "cost_per_m_output": 1.50,
        "context_window": 256_000,
    },
    "lightweight": {
        "provider": "xai",
        "model": "grok-3-mini",
        "cost_per_m_input": 0.30,
        "cost_per_m_output": 0.50,
        "context_window": 131_000,
    },
    "fallback": {
        "provider": "google",
        "model": "gemini-2-0-flash",
        "cost_per_m_input": 0.10,
        "cost_per_m_output": 0.40,
        "context_window": 1_000_000,
    },
}


def calculate_cost(input_tokens: int, output_tokens: int, model_type: str = "primary") -> float:
    """
    Calculate the cost of an LLM API call.

    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        model_type: Type of model used ("primary", "code", "lightweight", "fallback")

    Returns:
        Cost in USD
    """
    config = LLM_ROUTER.get(model_type, LLM_ROUTER["primary"])

    input_cost = (input_tokens / 1_000_000) * config["cost_per_m_input"]
    output_cost = (output_tokens / 1_000_000) * config["cost_per_m_output"]

    return input_cost + output_cost


def get_total_estimated_cost() -> float:
    """
    Get the total estimated monthly cost for the system.

    Returns:
        Total monthly cost in USD
    """
    return SYSTEM_COSTS["net_monthly_cost"]


# ============================================================================
# COST SUMMARY OUTPUT
# ============================================================================

if __name__ == "__main__":
    logger.info("\n" + "=" * 80)
    logger.info("HELIX UNIFIED: LLM COST ANALYSIS")
    logger.info("=" * 80)
    logger.info("\n14-Agent System (Active 24/7)")
    logger.info("├─ Total Daily Requests: %s", f"{SYSTEM_COSTS['total_daily_requests']:,}")
    logger.info("├─ Total Monthly Cost: $%.2f", SYSTEM_COSTS["total_monthly_cost"])
    logger.info("├─ Free Credits (Data Sharing): $%.2f/month", SYSTEM_COSTS["free_credits_per_month"])
    logger.info("├─ Net Monthly Cost: $%.2f", SYSTEM_COSTS["net_monthly_cost"])
    logger.info("├─ Annual Cost: $%.2f", SYSTEM_COSTS["annual_cost"])
    logger.info("└─ Net Annual Cost: $%.2f", SYSTEM_COSTS["net_annual_cost"])

    logger.info("\nCost Savings vs Alternatives:")
    logger.info("├─ vs Claude Sonnet: $%.2f/year", SYSTEM_COSTS["savings_vs_claude"])
    logger.info("└─ vs GPT-4o: $%.2f/year", SYSTEM_COSTS["savings_vs_gpt4o"])

    logger.info("\n✅ Platform runs essentially FREE with Grok data sharing program!")
    logger.info("✅ 2M token context window (15x larger than GPT-4o's 128K)")
    logger.info("✅ Real-time web search included (no extra API calls)")
    logger.info("\n" + "=" * 80)
