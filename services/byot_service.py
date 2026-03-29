"""
🔑 BYOT (Bring Your Own Token) Service
Allows users to provide their own LLM API keys for cost savings.

Features:
- Encrypted key storage using Fernet
- Key validation before saving
- Automatic fallback to platform keys
- Usage tracking per provider
"""

import logging
import os
from datetime import datetime
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Encryption key for BYOT keys (separate from MFA key for security isolation)
BYOT_ENCRYPTION_KEY = os.getenv("BYOT_ENCRYPTION_KEY")
if not BYOT_ENCRYPTION_KEY:
    _env = (os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("ENVIRONMENT", "")).lower()
    if _env not in ("", "development", "test", "testing"):
        # In production/staging, missing BYOT_ENCRYPTION_KEY means existing
        # user-stored API keys can never be decrypted after a restart.
        raise RuntimeError(
            "BYOT_ENCRYPTION_KEY is not set in production. "
            'Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" '
            "and add it to your Railway environment variables."
        )
    # Development only: generate a temporary key (NOT persisted across restarts)
    BYOT_ENCRYPTION_KEY = Fernet.generate_key().decode()
    logger.warning("⚠️ BYOT_ENCRYPTION_KEY not set - using temporary key (NOT SECURE FOR PRODUCTION)")

try:
    _fernet = Fernet(BYOT_ENCRYPTION_KEY.encode())
except Exception as e:
    logger.error("Failed to initialize Fernet for BYOT: %s", e)
    _fernet = None


# Supported LLM providers
SUPPORTED_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "key_prefix": "sk-",
        "models": ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo", "gpt-4o"],
        "validation_url": "https://api.openai.com/v1/models",
    },
    "anthropic": {
        "name": "Anthropic (Claude)",
        "key_prefix": "sk-ant-",
        "models": [
            "claude-3-opus",
            "claude-3-sonnet",
            "claude-3-haiku",
            "claude-3-5-sonnet",
        ],
        "validation_url": "https://api.anthropic.com/v1/messages",
    },
    "xai": {
        "name": "xAI (Grok)",
        "key_prefix": "xai-",
        "models": ["grok-beta", "grok-2"],
        "validation_url": "https://api.x.ai/v1/models",
    },
    "perplexity": {
        "name": "Perplexity",
        "key_prefix": "pplx-",
        "models": ["llama-3.1-sonar-small", "llama-3.1-sonar-large"],
        "validation_url": "https://api.perplexity.ai/chat/completions",
    },
    "google": {
        "name": "Google (Gemini)",
        "key_prefix": "AI",
        "models": ["gemini-pro", "gemini-1.5-pro"],
        "validation_url": "https://generativelanguage.googleapis.com",
    },
}

# Prefer BYOK management when available
try:
    from apps.backend.byok_management import (
        delete_user_api_key as _byok_delete_user_api_key,
        get_active_provider_key as _byok_get_active_provider_key,
        get_effective_llm_key as _byok_get_effective_llm_key,
        get_user_api_keys as _byok_get_user_api_keys,
        store_user_api_key as _byok_store_user_api_key,
        validate_api_key as _byok_validate_api_key,
    )

    BYOK_AVAILABLE = True
except ImportError:
    BYOK_AVAILABLE = False


class BYOTKeyInput(BaseModel):
    """Input model for setting a BYOT key"""

    provider: str = Field(..., description="LLM provider (openai, anthropic, xai, perplexity)")
    api_key: str = Field(..., description="The API key to store", min_length=10)
    validate_key: bool = Field(default=True, description="Whether to validate the key before saving")


class BYOTKeyStatus(BaseModel):
    """Status of a single BYOT key"""

    provider: str
    provider_name: str
    is_set: bool
    last_updated: datetime | None = None
    key_preview: str | None = None  # Shows first 4 and last 4 chars


class BYOTStatus(BaseModel):
    """Overall BYOT status for a user"""

    enabled: bool
    keys: list[BYOTKeyStatus]
    cost_savings_enabled: bool
    supported_providers: list[str]


def encrypt_key(api_key: str) -> str | None:
    """Encrypt an API key for storage"""
    if not _fernet:
        logger.error("Encryption not available")
        return None
    try:
        encrypted = _fernet.encrypt(api_key.encode())
        return encrypted.decode()
    except Exception as e:
        logger.error("Failed to encrypt key: %s", e)
        return None


def decrypt_key(encrypted_key: str) -> str | None:
    """Decrypt a stored API key"""
    if not _fernet or not encrypted_key:
        return None
    try:
        decrypted = _fernet.decrypt(encrypted_key.encode())
        return decrypted.decode()
    except InvalidToken:
        logger.error("Invalid token - key may have been encrypted with different key")
        return None
    except Exception as e:
        logger.error("Failed to decrypt key: %s", e)
        return None


def mask_key(api_key: str) -> str:
    """Create a masked preview of a key (first 4 + last 4 chars)"""
    if not api_key or len(api_key) < 12:
        return "****"
    return f"{api_key[:4]}...{api_key[-4:]}"


async def validate_api_key(provider: str, api_key: str) -> dict[str, Any]:
    """
    Validate an API key by making a test request to the provider.

    Returns:
        Dict with 'valid' (bool), 'message' (str), and optionally 'models' (list)
    """
    import httpx

    if provider not in SUPPORTED_PROVIDERS:
        return {"valid": False, "message": f"Unknown provider: {provider}"}

    if BYOK_AVAILABLE and provider in {"openai", "anthropic", "google"}:
        result = await _byok_validate_api_key(provider, api_key)
        return {
            "valid": bool(result.get("valid")),
            "message": (result.get("error") if not result.get("valid") else "Key validated successfully"),
            "models": result.get("models"),
        }

    provider_info = SUPPORTED_PROVIDERS[provider]

    # Check key prefix
    expected_prefix = provider_info["key_prefix"]
    if not api_key.startswith(expected_prefix):
        return {
            "valid": False,
            "message": f"Invalid key format. {provider_info['name']} keys should start with '{expected_prefix}'",
        }

    # Make validation request
    try:
        import aiohttp

        async with aiohttp.ClientSession() as client:
            if provider == "openai":
                response = await client.get(
                    provider_info["validation_url"],
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            elif provider == "anthropic":
                # Anthropic doesn't have a simple validation endpoint, use a minimal request
                response = await client.post(
                    provider_info["validation_url"],
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-3-haiku-20240307",
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                )
                # 200 or 400 (bad request but valid key) both indicate valid key
                if response.status in [200, 400]:
                    return {"valid": True, "message": "Key validated successfully"}
            elif provider == "xai":
                response = await client.get(
                    provider_info["validation_url"],
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            elif provider == "perplexity":
                response = await client.post(
                    provider_info["validation_url"],
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "llama-3.1-sonar-small-128k-online",
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 1,
                    },
                )
            elif provider == "google":
                # Google Gemini uses API key as query parameter
                response = await client.get(
                    provider_info["validation_url"] + "/v1beta/models",
                    params={"key": api_key},
                )
            else:
                return {
                    "valid": False,
                    "message": "Validation not implemented for this provider",
                }

            if response.status == 200:
                return {"valid": True, "message": "Key validated successfully"}
            elif response.status == 401:
                return {"valid": False, "message": "Invalid API key"}
            elif response.status == 403:
                return {
                    "valid": False,
                    "message": "API key access denied (may be revoked or expired)",
                }
            elif response.status == 429:
                # Rate limited but key is valid
                return {
                    "valid": True,
                    "message": "Key validated (rate limited but valid)",
                }
            else:
                return {
                    "valid": False,
                    "message": f"Validation failed with status {response.status}",
                }

    except httpx.TimeoutException:
        return {"valid": False, "message": "Validation timed out - try again later"}
    except Exception as e:
        logger.error("Key validation error: %s", e)
        return {"valid": False, "message": "Validation failed"}


async def get_user_llm_key(user_id: str, provider: str) -> str | None:
    """
    Get a user's decrypted LLM API key for a provider.
    Returns None if BYOT is disabled or key not set, falling back to platform key.

    This is the main function other services should call.
    """
    if not BYOK_AVAILABLE:
        logger.error("BYOK management unavailable - cannot resolve user key")
        return None

    return await _byok_get_active_provider_key(user_id, provider)


async def get_effective_llm_key(user_id: str | None, provider: str) -> str:
    """
    Get the effective LLM API key to use - user's BYOT key if available,
    otherwise fall back to platform environment variable.

    This is the PRIMARY function for LLM services to call.
    """
    if not BYOK_AVAILABLE:
        raise ValueError("BYOK management unavailable")

    return await _byok_get_effective_llm_key(user_id, provider)


async def set_user_byot_key(user_id: str, provider: str, api_key: str, validate: bool = True) -> dict[str, Any]:
    """
    Set a user's BYOT API key for a provider.

    Returns:
        Dict with 'success' (bool), 'message' (str)
    """

    if provider not in SUPPORTED_PROVIDERS:
        return {"success": False, "message": f"Unsupported provider: {provider}"}

    # Validate key if requested
    if validate:
        validation = await validate_api_key(provider, api_key)
        if not validation["valid"]:
            return {"success": False, "message": validation["message"]}

    if not BYOK_AVAILABLE:
        return {"success": False, "message": "BYOK management unavailable"}

    try:
        await _byok_store_user_api_key(user_id, provider, api_key, None)
        return {
            "success": True,
            "message": f"{SUPPORTED_PROVIDERS[provider]['name']} key saved successfully",
        }
    except Exception as e:
        logger.error("Failed to save BYOK key: %s", e)
        return {"success": False, "message": "Failed to save key"}


async def delete_user_byot_key(user_id: str, provider: str) -> dict[str, Any]:
    """Remove a user's BYOT key for a provider"""

    if provider not in SUPPORTED_PROVIDERS:
        return {"success": False, "message": f"Unsupported provider: {provider}"}

    if not BYOK_AVAILABLE:
        return {"success": False, "message": "BYOK management unavailable"}

    try:
        await _byok_delete_user_api_key(user_id, provider)
        return {
            "success": True,
            "message": f"{SUPPORTED_PROVIDERS[provider]['name']} key removed",
        }
    except Exception as e:
        logger.error("Failed to delete BYOK key: %s", e)
        return {"success": False, "message": "Failed to delete key"}


async def get_user_byot_status(user_id: str) -> BYOTStatus:
    """Get the complete BYOT status for a user"""
    keys_status = []
    enabled = False
    if not BYOK_AVAILABLE:
        return BYOTStatus(
            enabled=False,
            keys=[],
            cost_savings_enabled=False,
            supported_providers=list(SUPPORTED_PROVIDERS.keys()),
        )

    try:
        keys_data = await _byok_get_user_api_keys(user_id)
        provider_has_key = {}
        provider_last_updated = {}
        for key in keys_data:
            provider = key.get("provider")
            provider_has_key[provider] = True
            provider_last_updated[provider] = key.get("created_at")

        for provider, info in SUPPORTED_PROVIDERS.items():
            keys_status.append(
                BYOTKeyStatus(
                    provider=provider,
                    provider_name=info["name"],
                    is_set=bool(provider_has_key.get(provider)),
                    last_updated=provider_last_updated.get(provider),
                    key_preview=None,
                )
            )

        enabled = any(k.is_set for k in keys_status)
        return BYOTStatus(
            enabled=enabled,
            keys=keys_status,
            cost_savings_enabled=enabled,
            supported_providers=list(SUPPORTED_PROVIDERS.keys()),
        )
    except Exception as e:
        logger.error("Error getting BYOK status: %s", e)
        return BYOTStatus(
            enabled=False,
            keys=[],
            cost_savings_enabled=False,
            supported_providers=list(SUPPORTED_PROVIDERS.keys()),
        )


async def toggle_user_byot(user_id: str, enabled: bool) -> dict[str, Any]:
    """Enable or disable BYOT for a user"""
    if not BYOK_AVAILABLE:
        return {"success": False, "message": "BYOK management unavailable"}

    status = "enabled" if enabled else "disabled"
    return {
        "success": True,
        "message": f"BYOT {status} (managed via keys)",
    }
