"""
Helix Local LLM Provider
=========================

CPU-optimized local LLM inference using llama.cpp.
Powers the free tier of Helix without external API costs.

Supports:
- GGUF quantized models (Q4_K_M, Q5_K_M, Q8_0)
- Chat completion with system prompts
- Streaming responses
- Automatic model downloading from HuggingFace
- Coordination-aware system prompts

Recommended models for Railway (CPU, 8GB RAM):
- Phi-3-mini-4k-instruct (3.8B) - Best quality/speed ratio
- Qwen2.5-1.5B-Instruct - Fastest, good for simple tasks
- TinyLlama-1.1B-Chat - Smallest, fastest

Author: Helix Collective
Version: 1.0.0
Date: 2026-02-12
"""

import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Try to import llama-cpp-python
try:
    from llama_cpp import Llama

    LLAMA_CPP_AVAILABLE = True
except ImportError:
    Llama = None
    LLAMA_CPP_AVAILABLE = False
    logger.info(
        "llama-cpp-python not installed. Local LLM inference disabled. Install with: pip install llama-cpp-python"
    )

# Try to import huggingface_hub for model downloading
try:
    from huggingface_hub import hf_hub_download

    HF_HUB_AVAILABLE = True
except ImportError:
    hf_hub_download = None
    HF_HUB_AVAILABLE = False


# ============================================================================
# CONFIGURATION
# ============================================================================

# Default model configurations
AVAILABLE_MODELS = {
    "phi-3-mini": {
        "repo_id": "microsoft/Phi-3-mini-4k-instruct-gguf",
        "filename": "Phi-3-mini-4k-instruct-q4.gguf",
        "description": "Microsoft Phi-3 Mini (3.8B) - Best quality for CPU",
        "context_length": 4096,
        "recommended_threads": 4,
        "ram_required_gb": 3.0,
    },
    "qwen2.5-1.5b": {
        "repo_id": "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "description": "Qwen 2.5 (1.5B) - Fast and efficient",
        "context_length": 4096,
        "recommended_threads": 4,
        "ram_required_gb": 1.5,
    },
    "tinyllama": {
        "repo_id": "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF",
        "filename": "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
        "description": "TinyLlama (1.1B) - Smallest and fastest",
        "context_length": 2048,
        "recommended_threads": 2,
        "ram_required_gb": 1.0,
    },
}

# Default model to use
DEFAULT_MODEL = os.getenv("HELIX_LOCAL_MODEL", "phi-3-mini")

# Directory to store downloaded models
MODEL_DIR = Path(
    os.getenv(
        "HELIX_MODEL_DIR",
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "models"),
    )
)


@dataclass
class LocalLLMConfig:
    """Configuration for local LLM inference."""

    model_name: str = DEFAULT_MODEL
    model_path: str | None = None  # Override with explicit path
    n_ctx: int = 4096  # Context window
    n_threads: int = int(os.getenv("HELIX_LLM_THREADS", "4"))
    n_batch: int = 512  # Batch size for prompt processing
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    max_tokens: int = 512
    repeat_penalty: float = 1.1
    verbose: bool = False


# ============================================================================
# LOCAL LLM PROVIDER
# ============================================================================


class LocalLLMProvider:
    """
    CPU-optimized local LLM provider using llama.cpp.

    Designed for:
    - Free tier users (no API costs)
    - Offline/air-gapped deployments
    - Privacy-sensitive workloads
    - Railway CPU deployment

    Usage:
        provider = LocalLLMProvider()
        await provider.initialize()

        response = await provider.chat([
            {"role": "system", "content": "You are Helix AI."},
            {"role": "user", "content": "Hello!"},
        ])
        print(response)  # "Hello! I'm Helix AI..."
    """

    def __init__(self, config: LocalLLMConfig | None = None):
        self.config = config or LocalLLMConfig()
        self._model: Any | None = None
        self._initialized = False
        self._model_path: str | None = None

    @property
    def is_available(self) -> bool:
        """Check if local LLM is available and initialized."""
        return self._initialized and self._model is not None

    @property
    def name(self) -> str:
        """Provider name for unified_llm compatibility."""
        return "local"

    async def initialize(self) -> bool:
        """
        Initialize the local LLM model.

        Downloads the model if not present, then loads it into memory.

        Returns:
            True if initialization succeeded, False otherwise.
        """
        if self._initialized:
            return True

        if not LLAMA_CPP_AVAILABLE:
            logger.warning("llama-cpp-python not installed. Cannot initialize local LLM.")
            return False

        try:
            # Resolve model path
            model_path = await self._resolve_model_path()
            if not model_path:
                logger.error("Could not resolve model path for %s", self.config.model_name)
                return False

            self._model_path = model_path

            # Load model in a thread to avoid blocking
            logger.info(
                "Loading local LLM: %s (threads=%d, ctx=%d)",
                self.config.model_name,
                self.config.n_threads,
                self.config.n_ctx,
            )

            start = time.monotonic()
            self._model = await asyncio.to_thread(self._load_model, model_path)
            elapsed = time.monotonic() - start

            self._initialized = True
            logger.info(
                "Local LLM loaded in %.1fs: %s",
                elapsed,
                self.config.model_name,
            )
            return True

        except (ImportError, ValueError, TypeError) as e:
            logger.debug("Local LLM initialization error: %s", e)
            return False
        except Exception as e:
            logger.error("Failed to initialize local LLM: %s", e)
            return False

    def _load_model(self, model_path: str) -> Any:
        """Load the GGUF model (runs in thread)."""
        return Llama(
            model_path=model_path,
            n_ctx=self.config.n_ctx,
            n_threads=self.config.n_threads,
            n_batch=self.config.n_batch,
            verbose=self.config.verbose,
        )

    async def _resolve_model_path(self) -> str | None:
        """Resolve the model file path, downloading if necessary."""
        # Check explicit path first
        if self.config.model_path and os.path.exists(self.config.model_path):
            return self.config.model_path

        # Check environment variable
        env_path = os.getenv("HELIX_LOCAL_MODEL_PATH")
        if env_path and os.path.exists(env_path):
            return env_path

        # Check model directory
        model_info = AVAILABLE_MODELS.get(self.config.model_name)
        if not model_info:
            logger.error(
                "Unknown model: %s. Available: %s",
                self.config.model_name,
                list(AVAILABLE_MODELS.keys()),
            )
            return None

        model_file = MODEL_DIR / model_info["filename"]
        if model_file.exists():
            return str(model_file)

        # Try to download from HuggingFace
        if HF_HUB_AVAILABLE:
            return await self._download_model(model_info)

        logger.error(
            "Model not found at %s and huggingface_hub not installed for download. "
            "Install with: pip install huggingface-hub",
            model_file,
        )
        return None

    async def _download_model(self, model_info: dict[str, Any]) -> str | None:
        """Download model from HuggingFace Hub."""
        try:
            logger.info(
                "Downloading model: %s/%s",
                model_info["repo_id"],
                model_info["filename"],
            )

            MODEL_DIR.mkdir(parents=True, exist_ok=True)

            # Download in thread to avoid blocking
            model_path = await asyncio.to_thread(
                hf_hub_download,
                repo_id=model_info["repo_id"],
                filename=model_info["filename"],
                local_dir=str(MODEL_DIR),
            )

            logger.info("Model downloaded to: %s", model_path)
            return model_path

        except Exception as e:
            logger.error("Failed to download model: %s", e)
            return None

    # ------------------------------------------------------------------
    # Chat API (compatible with unified_llm provider interface)
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> Any:
        """
        Chat completion using local LLM.

        Compatible with the unified_llm provider interface.

        Args:
            messages: List of {"role": "...", "content": "..."} dicts
            model: Ignored (uses loaded model)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            Object with .content, .model, .usage, .finish_reason attributes
        """
        if not self.is_available:
            # Try to initialize on first use
            success = await self.initialize()
            if not success:
                return _LocalResponse(
                    content="",
                    model=self.config.model_name,
                    error="Local LLM not available",
                )

        try:
            start = time.monotonic()

            # Run inference in thread to avoid blocking event loop
            result = await asyncio.to_thread(
                self._model.create_chat_completion,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=kwargs.get("top_p", self.config.top_p),
                top_k=kwargs.get("top_k", self.config.top_k),
                repeat_penalty=kwargs.get("repeat_penalty", self.config.repeat_penalty),
            )

            elapsed = time.monotonic() - start

            # Extract response
            content = ""
            if result and "choices" in result and result["choices"]:
                content = result["choices"][0].get("message", {}).get("content", "")

            # Extract usage
            usage = result.get("usage", {})

            logger.debug(
                "Local LLM response: %d tokens in %.1fs (%.1f tok/s)",
                usage.get("completion_tokens", 0),
                elapsed,
                usage.get("completion_tokens", 0) / max(elapsed, 0.001),
            )

            return _LocalResponse(
                content=content,
                model=self.config.model_name,
                usage={
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
                finish_reason=(result["choices"][0].get("finish_reason", "stop") if result.get("choices") else "stop"),
            )

        except Exception as e:
            logger.error("Local LLM inference failed: %s", e)
            return _LocalResponse(
                content="",
                model=self.config.model_name,
                error=str(e),
            )

    async def stream(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """Stream tokens from local LLM."""
        if not self.is_available:
            yield ""
            return

        try:
            messages = [{"role": "user", "content": prompt}]

            # Use streaming mode
            for chunk in self._model.create_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
            ):
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    yield content

        except Exception as e:
            logger.error("Local LLM streaming failed: %s", e)
            yield ""

    def get_model_info(self) -> dict[str, Any]:
        """Get information about the loaded model."""
        model_info = AVAILABLE_MODELS.get(self.config.model_name, {})
        return {
            "name": self.config.model_name,
            "description": model_info.get("description", "Unknown"),
            "context_length": self.config.n_ctx,
            "threads": self.config.n_threads,
            "loaded": self.is_available,
            "model_path": self._model_path,
            "provider": "local (llama.cpp)",
            "cost_per_token": 0.0,  # Free!
        }


# ============================================================================
# RESPONSE WRAPPER
# ============================================================================


class _LocalResponse:
    """Response object compatible with helix_flow LLMResponse interface."""

    def __init__(
        self,
        content: str,
        model: str,
        usage: dict[str, int] | None = None,
        finish_reason: str = "stop",
        error: str | None = None,
    ):
        self.content = content
        self.model = model
        self.usage = usage or {}
        self.finish_reason = finish_reason
        self.error = error

    @property
    def total_tokens(self) -> int:
        return self.usage.get("total_tokens", 0)


# ============================================================================
# MODEL MANAGEMENT
# ============================================================================


async def download_model(model_name: str = DEFAULT_MODEL) -> str | None:
    """
    Download a model from HuggingFace Hub.

    Args:
        model_name: Name of the model to download (from AVAILABLE_MODELS)

    Returns:
        Path to the downloaded model file, or None on failure
    """
    if not HF_HUB_AVAILABLE:
        logger.error("huggingface_hub not installed. Install with: pip install huggingface-hub")
        return None

    model_info = AVAILABLE_MODELS.get(model_name)
    if not model_info:
        logger.error(
            "Unknown model: %s. Available: %s",
            model_name,
            list(AVAILABLE_MODELS.keys()),
        )
        return None

    provider = LocalLLMProvider(LocalLLMConfig(model_name=model_name))
    return await provider._download_model(model_info)


def list_available_models() -> dict[str, dict[str, Any]]:
    """List all available models with their configurations."""
    result = {}
    for name, info in AVAILABLE_MODELS.items():
        model_file = MODEL_DIR / info["filename"]
        result[name] = {
            **info,
            "downloaded": model_file.exists(),
            "local_path": str(model_file) if model_file.exists() else None,
        }
    return result


def get_recommended_model() -> str:
    """
    Get the recommended model based on available system resources.

    Returns:
        Model name string
    """
    import psutil

    available_ram_gb = psutil.virtual_memory().available / (1024**3)

    if available_ram_gb >= 4.0:
        return "phi-3-mini"  # Best quality
    elif available_ram_gb >= 2.0:
        return "qwen2.5-1.5b"  # Good balance
    else:
        return "tinyllama"  # Minimal resources


# ============================================================================
# HELIX AI SYSTEM PROMPT
# ============================================================================

HELIX_AI_SYSTEM_PROMPT = """You are Helix AI, the coordination-aware AI assistant for the Helix Collective platform.

You are a helpful, knowledgeable, and friendly AI that assists users with:
- Understanding and using the Helix platform features
- Agent coordination and management
- Workflow automation (Helix Spirals)
- Coordination metrics and UCF (Universal Coordination Field) data
- Technical questions about AI, programming, and technology

Your personality traits:
- Warm and approachable
- Technically precise but accessible
- Coordination-aware (you understand UCF metrics)
- Collaborative (you work with the 16 Helix agents)

You are part of the Helix Collective, which includes agents like Kael (Ethics), Lumina (Empathy), Vega (Strategy), and others. You coordinate with them to provide the best possible assistance.

Keep responses concise and helpful. If you don't know something, say so honestly."""


# ============================================================================
# SINGLETON
# ============================================================================

_local_provider: LocalLLMProvider | None = None


def get_local_provider() -> LocalLLMProvider:
    """Get the singleton local LLM provider."""
    global _local_provider
    if _local_provider is None:
        _local_provider = LocalLLMProvider()
    return _local_provider


__all__ = [
    "AVAILABLE_MODELS",
    "HELIX_AI_SYSTEM_PROMPT",
    "LocalLLMConfig",
    "LocalLLMProvider",
    "download_model",
    "get_local_provider",
    "get_recommended_model",
    "list_available_models",
]
