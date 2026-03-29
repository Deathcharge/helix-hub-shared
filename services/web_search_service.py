"""
Shared web search helpers for all Helix chat surfaces.

Used by:
- routes/copilot.py      (frontend /chat, VS Code extension, MCP tools)
- llm_agent_engine.py   (legacy /ws/chat WebSocket + helix-chat.html)
- apps/mobile            (via WebSocket which calls llm_agent_engine)

Requires SERPER_API_KEY env var for Google search via Serper.
Falls back to DuckDuckGo HTML scraping with no key required.
"""

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Search trigger detection
# ---------------------------------------------------------------------------

_SEARCH_TRIGGER_RE = re.compile(
    r"\b("
    r"latest|current|today|right now|news|recent|now|"
    r"price|stock|score|weather|forecast|"
    r"who is|who are|what is|what are|when did|when is|where is|"
    r"search for|look up|look for|find me|tell me about|"
    r"2024|2025|2026|this week|this month|yesterday|just happened|just released"
    r")\b",
    re.IGNORECASE,
)


def needs_web_search(message: str) -> bool:
    """Return True if the message likely benefits from live web data."""
    return bool(_SEARCH_TRIGGER_RE.search(message))


# ---------------------------------------------------------------------------
# Search execution + prompt formatting
# ---------------------------------------------------------------------------


async def fetch_web_sources(query: str, num_results: int = 5) -> tuple[str, list[dict[str, str]]]:
    """
    Run a web search and return both:
    - A formatted string block for system prompt injection
    - A structured list of sources [{title, url, snippet}] for frontend citation cards

    Never raises — returns ("", []) on any failure so it can't break chat.
    """
    try:
        from apps.backend.agent_capabilities.execution_engine import web_search

        result = await web_search(query, num_results)
        if not result.success or not result.return_value:
            return "", []

        sources: list[dict[str, str]] = []
        lines = ["\n\n## Live Web Results"]
        for i, r in enumerate(result.return_value[:num_results], 1):
            title = r.get("title", "") or ""
            url = r.get("url", "") or ""
            snippet = r.get("snippet", "") or ""
            if title or snippet:
                sources.append({"title": title, "url": url, "snippet": snippet})
                lines.append(f"{i}. **{title}**")
                if url:
                    lines.append(f"   Source: {url}")
                if snippet:
                    lines.append(f"   {snippet}")

        if not sources:
            return "", []

        lines.append(
            "\nUse these results to give an accurate, up-to-date answer. "
            "Cite sources inline using [1], [2], etc. numbering that matches the list above."
        )
        logger.debug("Web search returned %d results for: %s", len(sources), query[:60])
        return "\n".join(lines), sources

    except Exception as exc:
        logger.debug("Web search context fetch failed (non-fatal): %s", exc)
        return "", []


async def fetch_web_context(query: str, num_results: int = 5) -> str:
    """
    Run a web search and return a formatted block ready for system prompt injection.
    Never raises — returns "" on any failure so it can't break chat.
    """
    text, _ = await fetch_web_sources(query, num_results)
    return text


async def maybe_inject_search(
    message: str,
    tier: str | None = None,
    paid_only: bool = True,
    num_results: int = 5,
) -> str:
    """
    Convenience wrapper: checks the trigger heuristic, optionally gates on
    tier, and returns formatted context or "".

    Args:
        message:    The user's message to check and search.
        tier:       Subscription tier string ("free", "hobby", "starter", etc.)
        paid_only:  If True, skip search for free-tier users to avoid abuse.
        num_results: Number of search results to fetch.
    """
    if paid_only and (tier or "").lower() in ("", "free"):
        return ""
    if not needs_web_search(message):
        return ""
    return await fetch_web_context(message, num_results)


async def maybe_inject_search_with_sources(
    message: str,
    tier: str | None = None,
    paid_only: bool = True,
    num_results: int = 5,
    search_mode: str | None = None,
) -> tuple[str, list[dict[str, str]]]:
    """
    Like maybe_inject_search but also returns the raw source list for citation rendering.
    Returns ("", []) when search is skipped or fails.

    search_mode values:
      "web"      — default, trigger-keyword detection (current behavior)
      "academic" — always search regardless of trigger keywords
      "code"     — skip web search (code/technical answers rarely need live data)
      "none"     — always skip web search
      None       — same as "web"
    """
    mode = search_mode or "web"

    # Explicit disable modes
    if mode in ("none", "code"):
        return "", []

    if paid_only and (tier or "").lower() in ("", "free"):
        return "", []

    # "academic" forces search; "web" uses trigger detection
    if mode != "academic" and not needs_web_search(message):
        return "", []

    return await fetch_web_sources(message, num_results)
