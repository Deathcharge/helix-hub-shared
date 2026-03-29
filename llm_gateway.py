"""
⚠️ DEPRECATION NOTICE
=====================

This module is DEPRECATED and will be removed in a future version.

The canonical location for llm_gateway is:
    apps.backend.services.unified_llm

This redirect file provides backward compatibility by re-exporting
all public symbols from the canonical location.

Migration:
    # Old (deprecated)
    from apps.backend.llm_gateway import SomeClass
    
    # New (canonical)
    from apps.backend.services.unified_llm import SomeClass

This file will be removed in version 22.0.0.
"""

import warnings

# Issue deprecation warning
warnings.warn(
    "apps.backend.llm_gateway is deprecated. "
    "Use apps.backend.services.unified_llm instead. "
    "This redirect will be removed in version 22.0.0.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export all public symbols from canonical location
from apps.backend.services.unified_llm import *  # noqa: F401, F403

# Re-export __all__ if defined in canonical module
try:
    from apps.backend.services.unified_llm import __all__ as _canonical_all
    __all__ = _canonical_all
except ImportError:
    pass