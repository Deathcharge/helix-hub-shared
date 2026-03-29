"""
🌀 Helix Collective - Multi-Provider Token Budget Manager
Manages AI model usage limits, cost tracking, and graceful degradation.

Supports:
- Anthropic (Claude models)
- OpenAI (GPT models)
- xAI (Grok models)
- Future providers

Features:
- Per-user token budgets by tier
- Multi-provider cost normalization
- Graceful model degradation when budget exhausted
- Rate limiting for "unlimited" cheap models
- BYOK (Bring Your Own Key) support
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# PROVIDER & MODEL DEFINITIONS
# ============================================================================


class Provider(str, Enum):
    """Supported AI providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    XAI = "xai"
    GOOGLE = "google"
    MISTRAL = "mistral"
    GROQ = "groq"
    OPENROUTER = "openrouter"
    NVIDIA_NIM = "nvidia_nim"
    MINIMAX = "minimax"
    COHERE = "cohere"


class ModelTier(str, Enum):
    """Model cost tiers for budget management."""

    FREE = "free"  # Truly free/unlimited (rate-limited)
    CHEAP = "cheap"  # Low cost: Haiku, GPT-4o-mini, Grok-fast
    STANDARD = "standard"  # Mid cost: Sonnet, GPT-4o
    PREMIUM = "premium"  # High cost: Opus, GPT-4, Grok


@dataclass
class ModelInfo:
    """Information about a specific model."""

    id: str
    provider: Provider
    tier: ModelTier
    display_name: str

    # Cost per 1M tokens (in USD)
    input_cost_per_million: float
    output_cost_per_million: float

    # Context window
    max_context: int = 128000

    # Rate limits (requests per minute for unlimited tier)
    rpm_limit: int = 60

    # Whether this model is available
    available: bool = True


# Model catalog - costs as of early 2025 (update as needed)
MODEL_CATALOG: dict[str, ModelInfo] = {
    # =========== ANTHROPIC ===========
    "claude-3-haiku-20240307": ModelInfo(
        id="claude-3-haiku-20240307",
        provider=Provider.ANTHROPIC,
        tier=ModelTier.CHEAP,
        display_name="Claude 3 Haiku",
        input_cost_per_million=0.25,
        output_cost_per_million=1.25,
        max_context=200000,
        rpm_limit=100,
    ),
    "claude-3-5-haiku-20241022": ModelInfo(
        id="claude-3-5-haiku-20241022",
        provider=Provider.ANTHROPIC,
        tier=ModelTier.CHEAP,
        display_name="Claude 3.5 Haiku",
        input_cost_per_million=0.80,
        output_cost_per_million=4.00,
        max_context=200000,
        rpm_limit=100,
    ),
    "claude-3-5-sonnet-20241022": ModelInfo(
        id="claude-3-5-sonnet-20241022",
        provider=Provider.ANTHROPIC,
        tier=ModelTier.STANDARD,
        display_name="Claude 3.5 Sonnet",
        input_cost_per_million=3.00,
        output_cost_per_million=15.00,
        max_context=200000,
        rpm_limit=50,
    ),
    "claude-sonnet-4-20250514": ModelInfo(
        id="claude-sonnet-4-20250514",
        provider=Provider.ANTHROPIC,
        tier=ModelTier.STANDARD,
        display_name="Claude Sonnet 4",
        input_cost_per_million=3.00,
        output_cost_per_million=15.00,
        max_context=200000,
        rpm_limit=50,
    ),
    "claude-opus-4-20250514": ModelInfo(
        id="claude-opus-4-20250514",
        provider=Provider.ANTHROPIC,
        tier=ModelTier.PREMIUM,
        display_name="Claude Opus 4",
        input_cost_per_million=15.00,
        output_cost_per_million=75.00,
        max_context=200000,
        rpm_limit=20,
    ),
    # =========== OPENAI ===========
    "gpt-4o-mini": ModelInfo(
        id="gpt-4o-mini",
        provider=Provider.OPENAI,
        tier=ModelTier.CHEAP,
        display_name="GPT-4o Mini",
        input_cost_per_million=0.15,
        output_cost_per_million=0.60,
        max_context=128000,
        rpm_limit=100,
    ),
    "gpt-4o": ModelInfo(
        id="gpt-4o",
        provider=Provider.OPENAI,
        tier=ModelTier.STANDARD,
        display_name="GPT-4o",
        input_cost_per_million=2.50,
        output_cost_per_million=10.00,
        max_context=128000,
        rpm_limit=50,
    ),
    "gpt-4-turbo": ModelInfo(
        id="gpt-4-turbo",
        provider=Provider.OPENAI,
        tier=ModelTier.PREMIUM,
        display_name="GPT-4 Turbo",
        input_cost_per_million=10.00,
        output_cost_per_million=30.00,
        max_context=128000,
        rpm_limit=30,
    ),
    "o1": ModelInfo(
        id="o1",
        provider=Provider.OPENAI,
        tier=ModelTier.PREMIUM,
        display_name="OpenAI o1",
        input_cost_per_million=15.00,
        output_cost_per_million=60.00,
        max_context=200000,
        rpm_limit=20,
    ),
    # =========== XAI (GROK) ===========
    "grok-3-fast": ModelInfo(
        id="grok-3-fast",
        provider=Provider.XAI,
        tier=ModelTier.CHEAP,
        display_name="Grok 3 Fast",
        input_cost_per_million=0.15,
        output_cost_per_million=0.60,
        max_context=131072,
        rpm_limit=100,
    ),
    "grok-3": ModelInfo(
        id="grok-3",
        provider=Provider.XAI,
        tier=ModelTier.STANDARD,
        display_name="Grok 3",
        input_cost_per_million=3.00,
        output_cost_per_million=15.00,
        max_context=131072,
        rpm_limit=50,
    ),
    # =========== GOOGLE ===========
    "gemini-2.0-flash": ModelInfo(
        id="gemini-2.0-flash",
        provider=Provider.GOOGLE,
        tier=ModelTier.CHEAP,
        display_name="Gemini 2.0 Flash",
        input_cost_per_million=0.075,
        output_cost_per_million=0.30,
        max_context=1000000,
        rpm_limit=100,
    ),
    "gemini-1.5-pro": ModelInfo(
        id="gemini-1.5-pro",
        provider=Provider.GOOGLE,
        tier=ModelTier.STANDARD,
        display_name="Gemini 1.5 Pro",
        input_cost_per_million=1.25,
        output_cost_per_million=5.00,
        max_context=2000000,
        rpm_limit=50,
    ),
    # =========== GROQ (FREE TIER) ===========
    "llama-3.3-70b-versatile": ModelInfo(
        id="llama-3.3-70b-versatile",
        provider=Provider.GROQ,
        tier=ModelTier.FREE,
        display_name="Llama 3.3 70B (Groq)",
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        max_context=128000,
        rpm_limit=30,
    ),
    "llama-3.1-8b-instant": ModelInfo(
        id="llama-3.1-8b-instant",
        provider=Provider.GROQ,
        tier=ModelTier.FREE,
        display_name="Llama 3.1 8B Instant (Groq)",
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        max_context=128000,
        rpm_limit=30,
    ),
    "mixtral-8x7b-32768": ModelInfo(
        id="mixtral-8x7b-32768",
        provider=Provider.GROQ,
        tier=ModelTier.FREE,
        display_name="Mixtral 8x7B (Groq)",
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        max_context=32768,
        rpm_limit=30,
    ),
    # =========== NVIDIA NIM (FREE TIER) ===========
    "nvidia/llama-3.1-nemotron-70b-instruct": ModelInfo(
        id="nvidia/llama-3.1-nemotron-70b-instruct",
        provider=Provider.NVIDIA_NIM,
        tier=ModelTier.FREE,
        display_name="Nemotron 70B (NVIDIA NIM)",
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        max_context=128000,
        rpm_limit=30,
    ),
    # =========== MINIMAX (FREE TIER) ===========
    "minimax-m2.5": ModelInfo(
        id="minimax-m2.5",
        provider=Provider.MINIMAX,
        tier=ModelTier.FREE,
        display_name="MiniMax M2.5",
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        max_context=128000,
        rpm_limit=10,
    ),
    # =========== MISTRAL (FREE TIER) ===========
    "mistral-small-latest": ModelInfo(
        id="mistral-small-latest",
        provider=Provider.MISTRAL,
        tier=ModelTier.FREE,
        display_name="Mistral Small",
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        max_context=128000,
        rpm_limit=5,
    ),
    # =========== COHERE (FREE TIER) ===========
    "command-r": ModelInfo(
        id="command-r",
        provider=Provider.COHERE,
        tier=ModelTier.FREE,
        display_name="Command R (Cohere)",
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        max_context=128000,
        rpm_limit=20,
    ),
    "command-r-plus": ModelInfo(
        id="command-r-plus",
        provider=Provider.COHERE,
        tier=ModelTier.FREE,
        display_name="Command R+ (Cohere)",
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        max_context=128000,
        rpm_limit=20,
    ),
    # =========== OPENROUTER FREE MODELS ===========
    "arcee-ai/trinity-large-preview:free": ModelInfo(
        id="arcee-ai/trinity-large-preview:free",
        provider=Provider.OPENROUTER,
        tier=ModelTier.FREE,
        display_name="Arcee Trinity Large (OpenRouter)",
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        max_context=128000,
        rpm_limit=20,
    ),
    "kwaipilot/kat-coder-pro:free": ModelInfo(
        id="kwaipilot/kat-coder-pro:free",
        provider=Provider.OPENROUTER,
        tier=ModelTier.FREE,
        display_name="KAT-Coder-Pro (OpenRouter)",
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        max_context=256000,
        rpm_limit=20,
    ),
}

# Aliases for convenience
MODEL_ALIASES = {
    "haiku": "claude-3-5-haiku-20241022",
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
    "gpt4": "gpt-4o",
    "gpt4-mini": "gpt-4o-mini",
    "grok": "grok-3",
    "grok-fast": "grok-3-fast",
    "gemini": "gemini-2.0-flash",
    "gemini-pro": "gemini-1.5-pro",
    "groq": "llama-3.3-70b-versatile",
    "mistral": "mistral-small-latest",
    "cohere": "command-r",
    "nvidia": "nvidia/llama-3.1-nemotron-70b-instruct",
    "minimax": "minimax-m2.5",
}


def resolve_model(model_id: str) -> ModelInfo | None:
    """Resolve a model ID (including aliases) to ModelInfo."""
    resolved_id = MODEL_ALIASES.get(model_id.lower(), model_id)
    return MODEL_CATALOG.get(resolved_id)


# ============================================================================
# TIER BUDGETS
# ============================================================================


@dataclass
class TierBudget:
    """Token budget configuration for a subscription tier."""

    tier_name: str

    # Monthly token budgets by model tier (in tokens)
    # -1 means unlimited (but rate-limited)
    cheap_tokens: int = -1  # Unlimited cheap models
    standard_tokens: int = 0  # Standard model budget
    premium_tokens: int = 0  # Premium model budget

    # Rate limits for "unlimited" cheap models
    cheap_rpm: int = 20  # Requests per minute
    cheap_daily_requests: int = 500  # Max requests per day

    # Whether BYOK is allowed
    byok_allowed: bool = False

    # Overage pricing (cost per 1K tokens beyond budget, 0 = hard cap)
    overage_cost_per_1k: float = 0.0


# Tier configurations
TIER_BUDGETS: dict[str, TierBudget] = {
    "free": TierBudget(
        tier_name="Free",
        cheap_tokens=-1,  # "Unlimited" cheap (rate-limited)
        standard_tokens=0,  # No standard models
        premium_tokens=0,  # No premium models
        cheap_rpm=10,  # 10 requests/minute
        cheap_daily_requests=100,  # 100 requests/day
        byok_allowed=False,
    ),
    "pro": TierBudget(
        tier_name="Professional",
        cheap_tokens=-1,  # Unlimited cheap
        standard_tokens=500_000,  # 500K standard tokens/month
        premium_tokens=50_000,  # 50K premium tokens/month
        cheap_rpm=30,
        cheap_daily_requests=1000,
        byok_allowed=True,
        overage_cost_per_1k=0.02,  # $0.02 per 1K tokens overage
    ),
    "enterprise": TierBudget(
        tier_name="Enterprise",
        cheap_tokens=-1,  # Unlimited cheap
        standard_tokens=2_000_000,  # 2M standard tokens/month
        premium_tokens=200_000,  # 200K premium tokens/month
        cheap_rpm=60,
        cheap_daily_requests=5000,
        byok_allowed=True,
        overage_cost_per_1k=0.01,  # $0.01 per 1K tokens overage
    ),
    "byok": TierBudget(
        tier_name="Bring Your Own Key",
        cheap_tokens=-1,
        standard_tokens=-1,  # Unlimited with own keys
        premium_tokens=-1,
        cheap_rpm=100,
        cheap_daily_requests=-1,  # Unlimited
        byok_allowed=True,
    ),
}


# ============================================================================
# USAGE TRACKING
# ============================================================================


@dataclass
class UsageRecord:
    """Record of token usage."""

    timestamp: datetime
    user_id: str
    model_id: str
    provider: str
    model_tier: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    request_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class UserBudgetStatus:
    """Current budget status for a user."""

    user_id: str
    tier: str

    # Current period
    period_start: datetime
    period_end: datetime

    # Usage by model tier
    cheap_tokens_used: int = 0
    standard_tokens_used: int = 0
    premium_tokens_used: int = 0

    # Request counts (for rate limiting)
    requests_today: int = 0
    requests_this_minute: int = 0
    last_request_time: datetime | None = None

    # Cost tracking
    total_cost_usd: float = 0.0
    overage_cost_usd: float = 0.0

    # BYOK status
    using_own_key: bool = False

    def get_remaining(self, model_tier: ModelTier, tier_budget: TierBudget) -> int:
        """Get remaining tokens for a model tier."""
        if model_tier == ModelTier.CHEAP:
            budget = tier_budget.cheap_tokens
            used = self.cheap_tokens_used
        elif model_tier == ModelTier.STANDARD:
            budget = tier_budget.standard_tokens
            used = self.standard_tokens_used
        elif model_tier == ModelTier.PREMIUM:
            budget = tier_budget.premium_tokens
            used = self.premium_tokens_used
        else:
            return 0

        if budget == -1:  # Unlimited
            return -1
        return max(0, budget - used)

    def get_percentage_used(self, model_tier: ModelTier, tier_budget: TierBudget) -> float:
        """Get percentage of budget used for a model tier."""
        if model_tier == ModelTier.CHEAP:
            budget = tier_budget.cheap_tokens
            used = self.cheap_tokens_used
        elif model_tier == ModelTier.STANDARD:
            budget = tier_budget.standard_tokens
            used = self.standard_tokens_used
        elif model_tier == ModelTier.PREMIUM:
            budget = tier_budget.premium_tokens
            used = self.premium_tokens_used
        else:
            return 0.0

        if budget <= 0:
            return 0.0 if budget == 0 else 0.0  # -1 = unlimited
        return min(100.0, (used / budget) * 100)


# ============================================================================
# TOKEN BUDGET MANAGER
# ============================================================================


class TokenBudgetManager:
    """
    Manages token budgets across multiple AI providers.

    Features:
    - Per-user token tracking by model tier
    - Rate limiting for "unlimited" models
    - Graceful degradation to cheaper models
    - Cost tracking and overage handling
    - BYOK support
    """

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or Path("Helix/state/token_usage")
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # In-memory caches (rebuilt from PostgreSQL on startup, ephemeral rate-limit window)
        self._user_status_cache: dict[str, UserBudgetStatus] = {}
        self._rate_limit_cache: dict[str, list[datetime]] = {}  # Sliding-window, intentionally ephemeral

    # ========================================================================
    # BUDGET CHECKING
    # ========================================================================

    def can_use_model(
        self,
        user_id: str,
        model_id: str,
        tier: str = "free",
        estimated_tokens: int = 1000,
        using_own_key: bool = False,
    ) -> tuple[bool, str, str | None]:
        """
        Check if user can use a model.

        Returns:
            (allowed, reason, suggested_alternative)
        """
        # BYOK always allowed
        if using_own_key:
            return True, "Using your own API key", None

        # Get model info
        model = resolve_model(model_id)
        if not model:
            return False, f"Unknown model: {model_id}", "haiku"

        if not model.available:
            return False, f"Model {model.display_name} is currently unavailable", None

        # Get tier budget
        tier_budget = TIER_BUDGETS.get(tier, TIER_BUDGETS["free"])

        # Get user status
        status = self._get_user_status(user_id, tier)

        # ── Custom spend limit check ──────────────────────────────────────────
        # If the user has configured a monthly USD ceiling, enforce it before
        # checking token counts. This is the P4 spend-budget gate.
        spend_limit = self._get_user_spend_limit(user_id)
        if spend_limit is not None:
            limit_usd, alert_pct, hard_block = spend_limit
            month_spend = self._get_month_spend_usd(user_id)
            if hard_block and month_spend >= float(limit_usd):
                return (
                    False,
                    f"Monthly spend limit of ${limit_usd:.2f} reached "
                    f"(used ${month_spend:.4f}). Update your limit in Settings > Budget.",
                    None,
                )
        # ─────────────────────────────────────────────────────────────────────

        # Check rate limits first
        rate_ok, rate_msg = self._check_rate_limit(user_id, model, tier_budget)
        if not rate_ok:
            return False, rate_msg, self._get_degraded_model(model, tier)

        # Check token budget
        remaining = status.get_remaining(model.tier, tier_budget)

        if remaining == -1:  # Unlimited
            return True, "Within rate limits", None

        if remaining < estimated_tokens:
            # Try to suggest alternative
            alternative = self._get_degraded_model(model, tier)
            if alternative:
                return (
                    False,
                    f"Insufficient {model.tier.value} tokens (have {remaining:,}, need ~{estimated_tokens:,})",
                    alternative,
                )
            return False, f"Token budget exhausted for {model.tier.value} models", None

        return True, f"{remaining:,} tokens remaining", None

    def _get_user_spend_limit(self, user_id: str) -> tuple[float, int, bool] | None:
        """Return (monthly_limit_usd, alert_at_pct, hard_block) or None."""
        try:
            from apps.backend.db_models import LlmSpendLimit, SessionLocal

            session = SessionLocal()
            try:
                row = session.query(LlmSpendLimit).filter(LlmSpendLimit.user_id == user_id).first()
                if row:
                    return (float(row.monthly_limit_usd), row.alert_at_pct, row.hard_block)
            finally:
                session.close()
        except Exception as exc:
            logger.debug("Spend limit lookup failed for %s: %s", user_id, exc)
        return None

    def _get_month_spend_usd(self, user_id: str) -> float:
        """Return this calendar-month's total LLM spend in USD from api_usage."""
        try:

            from sqlalchemy import text as _text

            from apps.backend.db_models import SessionLocal

            now = datetime.now(UTC)
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            session = SessionLocal()
            try:
                result = session.execute(
                    _text(
                        "SELECT COALESCE(SUM(cost), 0) FROM api_usage " "WHERE user_id = :uid AND created_at >= :start"
                    ),
                    {"uid": user_id, "start": month_start},
                ).scalar()
                return float(result or 0.0)
            finally:
                session.close()
        except Exception as exc:
            logger.debug("Month spend lookup failed for %s: %s", user_id, exc)
            return 0.0

    def get_best_available_model(
        self,
        user_id: str,
        preferred_model: str,
        tier: str = "free",
        using_own_key: bool = False,
    ) -> tuple[str, str]:
        """
        Get the best available model for a user.

        If preferred model isn't available, gracefully degrade.

        Returns:
            (model_id, reason)
        """
        can_use, reason, alternative = self.can_use_model(user_id, preferred_model, tier, using_own_key=using_own_key)

        if can_use:
            resolved = MODEL_ALIASES.get(preferred_model.lower(), preferred_model)
            return resolved, reason

        # Try alternative
        if alternative:
            alt_can_use, alt_reason, _ = self.can_use_model(user_id, alternative, tier, using_own_key=using_own_key)
            if alt_can_use:
                return alternative, f"Degraded from {preferred_model}: {reason}"

        # Fall back to cheapest available
        fallback = self._get_cheapest_available(tier)
        return fallback, f"Fell back to {fallback}: {reason}"

    def _get_degraded_model(self, model: ModelInfo, tier: str) -> str | None:
        """Get a cheaper alternative model."""
        # Degradation paths by provider
        degradation_paths = {
            Provider.ANTHROPIC: {
                ModelTier.PREMIUM: "claude-3-5-sonnet-20241022",
                ModelTier.STANDARD: "claude-3-5-haiku-20241022",
            },
            Provider.OPENAI: {
                ModelTier.PREMIUM: "gpt-4o",
                ModelTier.STANDARD: "gpt-4o-mini",
            },
            Provider.XAI: {
                ModelTier.PREMIUM: "grok-3",
                ModelTier.STANDARD: "grok-3-fast",
            },
            Provider.GOOGLE: {
                ModelTier.PREMIUM: "gemini-1.5-pro",
                ModelTier.STANDARD: "gemini-2.0-flash",
            },
        }

        provider_paths = degradation_paths.get(model.provider, {})
        return provider_paths.get(model.tier)

    def _get_cheapest_available(self, tier: str) -> str:
        """Get the cheapest available model for a tier."""
        # Prefer Gemini Flash (cheapest), then GPT-4o-mini, then Haiku
        cheap_models = [
            "gemini-2.0-flash",
            "gpt-4o-mini",
            "claude-3-5-haiku-20241022",
            "grok-3-fast",
        ]

        for model_id in cheap_models:
            model = MODEL_CATALOG.get(model_id)
            if model and model.available:
                return model_id

        return "claude-3-5-haiku-20241022"  # Default fallback

    # ========================================================================
    # RATE LIMITING
    # ========================================================================

    def _check_rate_limit(
        self,
        user_id: str,
        model: ModelInfo,
        tier_budget: TierBudget,
    ) -> tuple[bool, str]:
        """Check if user is within rate limits."""
        now = datetime.now(UTC)
        cache_key = f"{user_id}:{model.tier.value}"

        # Get request history
        requests = self._rate_limit_cache.get(cache_key, [])

        # Clean old entries
        minute_ago = now - timedelta(minutes=1)
        day_ago = now - timedelta(days=1)

        requests_last_minute = [r for r in requests if r > minute_ago]
        requests_last_day = [r for r in requests if r > day_ago]

        # Check limits based on model tier
        if model.tier == ModelTier.CHEAP:
            rpm_limit = tier_budget.cheap_rpm
            daily_limit = tier_budget.cheap_daily_requests
        else:
            rpm_limit = model.rpm_limit
            daily_limit = -1  # No daily limit for paid tiers

        # Check RPM
        if len(requests_last_minute) >= rpm_limit:
            return False, f"Rate limit exceeded ({rpm_limit} requests/minute)"

        # Check daily limit
        if daily_limit > 0 and len(requests_last_day) >= daily_limit:
            return False, f"Daily limit exceeded ({daily_limit} requests/day)"

        return True, "OK"

    def _record_request(self, user_id: str, model_tier: ModelTier):
        """Record a request for rate limiting."""
        cache_key = f"{user_id}:{model_tier.value}"
        now = datetime.now(UTC)

        if cache_key not in self._rate_limit_cache:
            self._rate_limit_cache[cache_key] = []

        self._rate_limit_cache[cache_key].append(now)

        # Keep only last 24 hours
        day_ago = now - timedelta(days=1)
        self._rate_limit_cache[cache_key] = [r for r in self._rate_limit_cache[cache_key] if r > day_ago]

    # ========================================================================
    # USAGE TRACKING
    # ========================================================================

    def record_usage(
        self,
        user_id: str,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        tier: str = "free",
        using_own_key: bool = False,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UsageRecord:
        """Record token usage after a request."""
        model = resolve_model(model_id) or MODEL_CATALOG.get("claude-3-5-haiku-20241022")

        # Calculate cost
        input_cost = (input_tokens / 1_000_000) * model.input_cost_per_million
        output_cost = (output_tokens / 1_000_000) * model.output_cost_per_million
        total_cost = input_cost + output_cost

        # Create record
        record = UsageRecord(
            timestamp=datetime.now(UTC),
            user_id=user_id,
            model_id=model.id,
            provider=model.provider.value,
            model_tier=model.tier.value,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cost_usd=total_cost if not using_own_key else 0.0,
            request_id=request_id,
            metadata=metadata or {},
        )

        # Update user status
        if not using_own_key:
            self._update_user_status(user_id, tier, record)

        # Record for rate limiting
        self._record_request(user_id, model.tier)

        # Persist to storage
        self._persist_usage(record)

        logger.info(
            f"Usage recorded: {user_id} | {model.display_name} | "
            f"{input_tokens + output_tokens:,} tokens | ${total_cost:.4f}"
        )

        return record

    def _update_user_status(self, user_id: str, tier: str, record: UsageRecord):
        """Update user's budget status."""
        status = self._get_user_status(user_id, tier)

        # Update token counts by tier
        if record.model_tier == ModelTier.CHEAP.value:
            status.cheap_tokens_used += record.total_tokens
        elif record.model_tier == ModelTier.STANDARD.value:
            status.standard_tokens_used += record.total_tokens
        elif record.model_tier == ModelTier.PREMIUM.value:
            status.premium_tokens_used += record.total_tokens

        status.total_cost_usd += record.cost_usd
        status.requests_today += 1
        status.last_request_time = record.timestamp

        # Check for overage
        tier_budget = TIER_BUDGETS.get(tier, TIER_BUDGETS["free"])
        self._calculate_overage(status, tier_budget)

        self._user_status_cache[user_id] = status

    def _calculate_overage(self, status: UserBudgetStatus, tier_budget: TierBudget):
        """Calculate overage costs if applicable."""
        if tier_budget.overage_cost_per_1k <= 0:
            return  # No overage allowed

        overage_tokens = 0

        # Check standard tokens
        if tier_budget.standard_tokens > 0:
            std_overage = status.standard_tokens_used - tier_budget.standard_tokens
            if std_overage > 0:
                overage_tokens += std_overage

        # Check premium tokens
        if tier_budget.premium_tokens > 0:
            prem_overage = status.premium_tokens_used - tier_budget.premium_tokens
            if prem_overage > 0:
                overage_tokens += prem_overage

        status.overage_cost_usd = (overage_tokens / 1000) * tier_budget.overage_cost_per_1k

    def _get_user_status(self, user_id: str, tier: str) -> UserBudgetStatus:
        """Get or create user budget status."""
        if user_id in self._user_status_cache:
            status = self._user_status_cache[user_id]
            # Check if we need to reset for new period
            if datetime.now(UTC) > status.period_end:
                status = self._create_new_period(user_id, tier)
            return status

        # Try to load from storage
        status = self._load_user_status(user_id)
        if status:
            self._user_status_cache[user_id] = status
            return status

        # Create new status
        return self._create_new_period(user_id, tier)

    def _create_new_period(self, user_id: str, tier: str) -> UserBudgetStatus:
        """Create a new billing period for user."""
        now = datetime.now(UTC)
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Calculate period end (first of next month)
        if period_start.month == 12:
            period_end = period_start.replace(year=period_start.year + 1, month=1)
        else:
            period_end = period_start.replace(month=period_start.month + 1)

        status = UserBudgetStatus(
            user_id=user_id,
            tier=tier,
            period_start=period_start,
            period_end=period_end,
        )

        self._user_status_cache[user_id] = status
        return status

    # ========================================================================
    # PERSISTENCE
    # ========================================================================

    def _persist_usage(self, record: UsageRecord):
        """Persist usage record to PostgreSQL api_usage table (primary) and JSONL (backup)."""
        # Primary: write to PostgreSQL api_usage table
        try:
            from apps.backend.db_models import APIUsage, SessionLocal

            session = SessionLocal()
            try:
                usage_row = APIUsage(
                    user_id=record.user_id,
                    model_id=record.model_id,
                    input_tokens=record.input_tokens,
                    output_tokens=record.output_tokens,
                    total_tokens=record.total_tokens,
                    cost=record.cost_usd,
                    request_id=record.request_id,
                    usage_metadata={
                        "provider": record.provider,
                        "model_tier": record.model_tier,
                        **(record.metadata or {}),
                    },
                )
                session.add(usage_row)
                session.commit()
            finally:
                session.close()
        except ImportError:
            logger.debug("Database session not available for usage persistence")
        except Exception as e:
            logger.warning("Failed to persist usage to PostgreSQL: %s", e)

        # Backup: also write to JSONL for offline/local dev scenarios
        try:
            usage_file = self.storage_path / f"usage_{record.user_id}.jsonl"
            entry = {
                "timestamp": record.timestamp.isoformat(),
                "model_id": record.model_id,
                "provider": record.provider,
                "model_tier": record.model_tier,
                "input_tokens": record.input_tokens,
                "output_tokens": record.output_tokens,
                "total_tokens": record.total_tokens,
                "cost_usd": record.cost_usd,
                "request_id": record.request_id,
                "metadata": record.metadata,
            }
            with open(usage_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.debug("JSONL usage persistence failed: %s", e)

    def _load_user_status(self, user_id: str) -> UserBudgetStatus | None:
        """Load user status from PostgreSQL (primary) or JSONL (fallback)."""
        now = datetime.now(UTC)
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Calculate period end
        if period_start.month == 12:
            period_end = period_start.replace(year=period_start.year + 1, month=1)
        else:
            period_end = period_start.replace(month=period_start.month + 1)

        # Primary: read from PostgreSQL
        try:

            from apps.backend.db_models import APIUsage, SessionLocal

            session = SessionLocal()
            try:
                rows = (
                    session.query(APIUsage)
                    .filter(
                        APIUsage.user_id == user_id,
                        APIUsage.created_at >= period_start,
                    )
                    .all()
                )
                if rows:
                    cheap_tokens = 0
                    standard_tokens = 0
                    premium_tokens = 0
                    total_cost = 0.0
                    requests_today = 0

                    for row in rows:
                        tokens = (row.input_tokens or 0) + (row.output_tokens or 0)
                        tier_label = (row.usage_metadata or {}).get("model_tier", "cheap")
                        if tier_label == "cheap":
                            cheap_tokens += tokens
                        elif tier_label == "standard":
                            standard_tokens += tokens
                        elif tier_label == "premium":
                            premium_tokens += tokens
                        total_cost += float(row.cost or 0)
                        if row.created_at and row.created_at >= today_start:
                            requests_today += 1

                    return UserBudgetStatus(
                        user_id=user_id,
                        tier="free",
                        period_start=period_start,
                        period_end=period_end,
                        cheap_tokens_used=cheap_tokens,
                        standard_tokens_used=standard_tokens,
                        premium_tokens_used=premium_tokens,
                        requests_today=requests_today,
                        total_cost_usd=total_cost,
                    )
            finally:
                session.close()
        except Exception as e:
            logger.debug("PostgreSQL user status load failed, trying JSONL: %s", e)

        # Fallback: read from JSONL
        usage_file = self.storage_path / f"usage_{user_id}.jsonl"

        if not usage_file.exists():
            return None

        cheap_tokens = 0
        standard_tokens = 0
        premium_tokens = 0
        total_cost = 0.0
        requests_today = 0

        with open(usage_file, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                entry = json.loads(line)
                ts = datetime.fromisoformat(entry["timestamp"])

                if ts < period_start:
                    continue

                tokens = entry.get("total_tokens", 0)
                tier = entry.get("model_tier", "cheap")

                if tier == "cheap":
                    cheap_tokens += tokens
                elif tier == "standard":
                    standard_tokens += tokens
                elif tier == "premium":
                    premium_tokens += tokens

                total_cost += entry.get("cost_usd", 0)

                if ts >= today_start:
                    requests_today += 1

        return UserBudgetStatus(
            user_id=user_id,
            tier="free",  # Will be updated by caller
            period_start=period_start,
            period_end=period_end,
            cheap_tokens_used=cheap_tokens,
            standard_tokens_used=standard_tokens,
            premium_tokens_used=premium_tokens,
            requests_today=requests_today,
            total_cost_usd=total_cost,
        )

    # ========================================================================
    # USAGE HISTORY
    # ========================================================================

    def get_usage_history(self, user_id: str, days: int = 30) -> dict[str, Any]:
        """Get usage history aggregated by day and model for a user."""
        usage_file = self.storage_path / f"usage_{user_id}.jsonl"
        cutoff = datetime.now(UTC) - timedelta(days=days)

        daily: dict[str, dict[str, Any]] = {}
        by_model: dict[str, dict[str, Any]] = {}
        total_tokens = 0
        total_cost = 0.0
        total_requests = 0

        if usage_file.exists():
            with open(usage_file, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    ts = datetime.fromisoformat(entry["timestamp"])
                    if ts < cutoff:
                        continue

                    day_key = ts.strftime("%Y-%m-%d")
                    tokens = entry.get("total_tokens", 0)
                    cost = entry.get("cost_usd", 0.0)
                    model = entry.get("model_id", "unknown")

                    # Daily aggregation
                    if day_key not in daily:
                        daily[day_key] = {"tokens": 0, "cost": 0.0, "requests": 0}
                    daily[day_key]["tokens"] += tokens
                    daily[day_key]["cost"] += cost
                    daily[day_key]["requests"] += 1

                    # Per-model aggregation
                    if model not in by_model:
                        by_model[model] = {"tokens": 0, "cost": 0.0, "requests": 0}
                    by_model[model]["tokens"] += tokens
                    by_model[model]["cost"] += cost
                    by_model[model]["requests"] += 1

                    total_tokens += tokens
                    total_cost += cost
                    total_requests += 1

        # Build sorted daily series
        daily_series = [{"date": k, **v} for k, v in sorted(daily.items())]

        # Build model breakdown sorted by cost desc
        model_breakdown = [
            {"model": k, **v} for k, v in sorted(by_model.items(), key=lambda x: x[1]["cost"], reverse=True)
        ]

        return {
            "period_days": days,
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 4),
            "total_requests": total_requests,
            "daily": daily_series,
            "by_model": model_breakdown,
        }

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    def get_user_budget_status(self, user_id: str, tier: str = "free") -> dict[str, Any]:
        """Get comprehensive budget status for user."""
        status = self._get_user_status(user_id, tier)
        tier_budget = TIER_BUDGETS.get(tier, TIER_BUDGETS["free"])

        return {
            "user_id": user_id,
            "tier": tier,
            "tier_name": tier_budget.tier_name,
            "period": {
                "start": status.period_start.isoformat(),
                "end": status.period_end.isoformat(),
                "days_remaining": (status.period_end - datetime.now(UTC)).days,
            },
            "usage": {
                "cheap": {
                    "used": status.cheap_tokens_used,
                    "budget": tier_budget.cheap_tokens,
                    "remaining": status.get_remaining(ModelTier.CHEAP, tier_budget),
                    "percentage": status.get_percentage_used(ModelTier.CHEAP, tier_budget),
                    "unlimited": tier_budget.cheap_tokens == -1,
                },
                "standard": {
                    "used": status.standard_tokens_used,
                    "budget": tier_budget.standard_tokens,
                    "remaining": status.get_remaining(ModelTier.STANDARD, tier_budget),
                    "percentage": status.get_percentage_used(ModelTier.STANDARD, tier_budget),
                    "unlimited": tier_budget.standard_tokens == -1,
                },
                "premium": {
                    "used": status.premium_tokens_used,
                    "budget": tier_budget.premium_tokens,
                    "remaining": status.get_remaining(ModelTier.PREMIUM, tier_budget),
                    "percentage": status.get_percentage_used(ModelTier.PREMIUM, tier_budget),
                    "unlimited": tier_budget.premium_tokens == -1,
                },
            },
            "rate_limits": {
                "requests_today": status.requests_today,
                "daily_limit": tier_budget.cheap_daily_requests,
                "rpm_limit": tier_budget.cheap_rpm,
            },
            "costs": {
                "total_usd": round(status.total_cost_usd, 4),
                "overage_usd": round(status.overage_cost_usd, 4),
            },
            "byok_allowed": tier_budget.byok_allowed,
        }

    def get_available_models(self, tier: str = "free") -> list[dict[str, Any]]:
        """Get list of models available for a tier."""
        tier_budget = TIER_BUDGETS.get(tier, TIER_BUDGETS["free"])

        available = []
        for model_id, model in MODEL_CATALOG.items():
            if not model.available:
                continue

            # Check if tier has access
            has_budget = False
            if model.tier == ModelTier.CHEAP:
                has_budget = True  # Always available (rate-limited)
            elif model.tier == ModelTier.STANDARD:
                has_budget = tier_budget.standard_tokens != 0
            elif model.tier == ModelTier.PREMIUM:
                has_budget = tier_budget.premium_tokens != 0

            available.append(
                {
                    "id": model.id,
                    "display_name": model.display_name,
                    "provider": model.provider.value,
                    "tier": model.tier.value,
                    "available_for_tier": has_budget,
                    "requires_upgrade": not has_budget,
                    "cost_per_1k_tokens": round(
                        (model.input_cost_per_million + model.output_cost_per_million) / 2000,
                        4,
                    ),
                }
            )

        return sorted(available, key=lambda x: (not x["available_for_tier"], x["tier"]))


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_token_budget_manager: TokenBudgetManager | None = None


def get_token_budget_manager() -> TokenBudgetManager:
    """Get the singleton TokenBudgetManager instance."""
    global _token_budget_manager
    if _token_budget_manager is None:
        _token_budget_manager = TokenBudgetManager()
    return _token_budget_manager


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "MODEL_CATALOG",
    "TIER_BUDGETS",
    "ModelInfo",
    "ModelTier",
    "Provider",
    "TierBudget",
    "TokenBudgetManager",
    "get_token_budget_manager",
    "resolve_model",
]
