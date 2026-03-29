# Backend agents package
# Re-exports from agents_service.py and agent_registry.py for backward compatibility
# This allows 'from apps.backend.agents import Helix' to work seamlessly

try:
    from apps.backend.agents.agent_registry import AGENT_REGISTRY
except ImportError:
    try:
        from .agent_registry import AGENT_REGISTRY
    except ImportError:
        AGENT_REGISTRY = {}

try:
    from apps.backend.agents.agents_service import (
        AGENTS,
        AetherAgent,
        Agni,
        Aria,
        ArjunaAgent,
        Atlas,
        Echo,
        Gemini,
        Helix,
        HelixAgent,
        Iris,
        Kael,
        Lumina,
        Mitra,
        Nexus,
        Nova,
        Oracle,
        Phoenix,
        Sage,
        SanghaCore,
        Shadow,
        Surya,
        Titan,
        Varuna,
        Vega,
        get_collective_status,
    )
except ImportError:
    # Fallback for when running from different import contexts
    from .agents_service import (
        AGENTS,
        AetherAgent,
        Agni,
        Aria,
        ArjunaAgent,
        Atlas,
        Echo,
        Gemini,
        Helix,
        HelixAgent,
        Iris,
        Kael,
        Lumina,
        Mitra,
        Nexus,
        Nova,
        Oracle,
        Phoenix,
        Sage,
        SanghaCore,
        Shadow,
        Surya,
        Titan,
        Varuna,
        Vega,
        get_collective_status,
    )

__all__ = [
    "AGENTS",
    "AGENT_REGISTRY",
    "AetherAgent",
    "Agni",
    "Aria",
    "ArjunaAgent",
    "Atlas",
    "Echo",
    "Gemini",
    "Helix",
    "HelixAgent",
    "Iris",
    "Kael",
    "Lumina",
    "Mitra",
    "Nexus",
    "Nova",
    "Oracle",
    "Phoenix",
    "Sage",
    "SanghaCore",
    "Shadow",
    "Surya",
    "Titan",
    "Varuna",
    "Vega",
    "get_collective_status",
]
