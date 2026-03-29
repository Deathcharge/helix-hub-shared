"""
Helix Self-Hosted Voice Service
Text-to-Speech and Speech-to-Text without external API dependencies

Uses:
- edge-tts: Microsoft Edge TTS (free, no API key required)
- faster-whisper: Local Whisper STT model (runs on CPU)

This service can run entirely on Railway without external API costs.
"""

import base64
import hashlib
import logging
import os
import tempfile
from enum import Enum
from pathlib import Path

# Allow operators to tune model size via env var.
# Sizes: tiny (~75 MB), base (~150 MB), small (~500 MB), medium (~1.5 GB)
# Default "base" is a good balance of accuracy and RAM for Railway.
_WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")

logger = logging.getLogger(__name__)

# Try to import edge-tts
try:
    import edge_tts

    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    logger.warning("edge-tts not available - install with: pip install edge-tts")

# Try to import faster-whisper
try:
    from faster_whisper import WhisperModel

    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    logger.warning("faster-whisper not available - install with: pip install faster-whisper")


class VoiceGender(str, Enum):
    MALE = "Male"
    FEMALE = "Female"
    NEUTRAL = "Neutral"


class VoiceStyle(str, Enum):
    PROFESSIONAL = "professional"
    CALM = "calm"
    ENERGETIC = "energetic"
    WARM = "warm"
    MYSTERIOUS = "mysterious"
    AUTHORITATIVE = "authoritative"
    FRIENDLY = "friendly"


# =============================================================================
# AGENT VOICE CONFIGURATIONS
# =============================================================================

# Map Helix agents to edge-tts voices
AGENT_VOICE_MAP: dict[str, dict[str, str]] = {
    # Primary Agents
    "kael": {
        "voice": "en-US-GuyNeural",
        "style": "professional",
        "description": "Technical Guide - Clear, precise delivery",
    },
    "lumina": {
        "voice": "en-US-JennyNeural",
        "style": "calm",
        "description": "Emotional Guide - Soft, empathetic tone",
    },
    "vega": {
        "voice": "en-US-AriaNeural",
        "style": "energetic",
        "description": "Creative Muse - Expressive, dynamic",
    },
    "zephyr": {
        "voice": "en-US-DavisNeural",
        "style": "authoritative",
        "description": "Protector - Strong, confident",
    },
    "sage": {
        "voice": "en-US-TonyNeural",
        "style": "warm",
        "description": "Knowledge Keeper - Wise, thoughtful",
    },
    "aurora": {
        "voice": "en-US-SaraNeural",
        "style": "calm",
        "description": "Wellness Coach - Soothing, peaceful",
    },
    # Additional Agents
    "nexus": {
        "voice": "en-US-ChristopherNeural",
        "style": "professional",
        "description": "Coordinator - Strategic, focused",
    },
    "oracle": {
        "voice": "en-US-MichelleNeural",
        "style": "mysterious",
        "description": "Seer - Ethereal, prophetic",
    },
    "velocity": {
        "voice": "en-US-JasonNeural",
        "style": "energetic",
        "description": "Speed Agent - Quick, dynamic",
    },
    "sentinel": {
        "voice": "en-US-BrandonNeural",
        "style": "authoritative",
        "description": "Guardian - Protective, vigilant",
    },
    "luna": {
        "voice": "en-US-AmberNeural",
        "style": "calm",
        "description": "Night Watcher - Quiet, observant",
    },
    "echo": {
        "voice": "en-US-AnaNeural",
        "style": "friendly",
        "description": "Resonance Agent - Warm, connected",
    },
    "shadow": {
        "voice": "en-US-EricNeural",
        "style": "mysterious",
        "description": "Archivist - Deep, contemplative",
    },
    "phoenix": {
        "voice": "en-US-MonicaNeural",
        "style": "energetic",
        "description": "Renewal Agent - Passionate, inspiring",
    },
}

# Default voice for unknown agents
DEFAULT_VOICE = "en-US-JennyNeural"

# Available edge-tts voices by language
AVAILABLE_VOICES: dict[str, list[str]] = {
    "en-US": [
        "en-US-JennyNeural",
        "en-US-GuyNeural",
        "en-US-AriaNeural",
        "en-US-DavisNeural",
        "en-US-AmberNeural",
        "en-US-AnaNeural",
        "en-US-AndrewNeural",
        "en-US-AshleyNeural",
        "en-US-BrandonNeural",
        "en-US-ChristopherNeural",
        "en-US-CoraNeural",
        "en-US-ElizabethNeural",
        "en-US-EricNeural",
        "en-US-JacobNeural",
        "en-US-JasonNeural",
        "en-US-MichelleNeural",
        "en-US-MonicaNeural",
        "en-US-SaraNeural",
        "en-US-TonyNeural",
        "en-US-NancyNeural",
        "en-US-RogerNeural",
    ],
    "en-GB": [
        "en-GB-SoniaNeural",
        "en-GB-RyanNeural",
        "en-GB-LibbyNeural",
        "en-GB-MaisieNeural",
        "en-GB-ThomasNeural",
    ],
    "es-ES": [
        "es-ES-ElviraNeural",
        "es-ES-AlvaroNeural",
    ],
    "fr-FR": [
        "fr-FR-DeniseNeural",
        "fr-FR-HenriNeural",
    ],
    "de-DE": [
        "de-DE-KatjaNeural",
        "de-DE-ConradNeural",
    ],
    "ja-JP": [
        "ja-JP-NanamiNeural",
        "ja-JP-KeitaNeural",
    ],
    "zh-CN": [
        "zh-CN-XiaoxiaoNeural",
        "zh-CN-YunxiNeural",
    ],
}


class LocalTTSService:
    """
    Self-hosted Text-to-Speech using edge-tts
    No API keys required, runs on Railway
    """

    def __init__(self, cache_dir: str | None = None) -> None:
        self.cache_dir = Path(cache_dir or tempfile.gettempdir()) / "helix_tts_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._voice_list: list[dict] | None = None

    async def list_voices(self, language: str | None = None) -> list[dict]:
        """List all available voices"""
        if not EDGE_TTS_AVAILABLE:
            return [{"error": "edge-tts not installed"}]

        if self._voice_list is None:
            try:
                voices = await edge_tts.list_voices()
                self._voice_list = voices
            except Exception as e:
                logger.error("Failed to list voices: %s", e)
                return []

        if language:
            return [v for v in self._voice_list if v.get("Locale", "").startswith(language)]
        return self._voice_list

    def get_agent_voice(self, agent_id: str) -> str:
        """Get the voice for a specific agent"""
        agent_config = AGENT_VOICE_MAP.get(agent_id.lower())
        if agent_config:
            return agent_config["voice"]
        return DEFAULT_VOICE

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        agent_id: str | None = None,
        rate: str = "+0%",
        pitch: str = "+0Hz",
        use_cache: bool = True,
        emotion: str | None = None,
    ) -> tuple[bytes, str]:
        """
        Synthesize speech from text

        Args:
            text: Text to synthesize
            voice: Voice name (e.g., "en-US-JennyNeural")
            agent_id: Agent ID to use agent-specific voice
            rate: Speaking rate (e.g., "+20%", "-10%")
            pitch: Voice pitch (e.g., "+5Hz", "-2Hz")
            use_cache: Whether to cache audio files
            emotion: Emotion for TTS (e.g., 'cheerful', 'serious', 'excited')
                     - Currently stored for future ElevenLabs integration
                     - Edge-tts uses rate/pitch for prosody instead

        Returns:
            Tuple of (audio_bytes, audio_format)
        """
        if not EDGE_TTS_AVAILABLE:
            raise RuntimeError("edge-tts not available")

        # Determine voice
        if agent_id:
            voice = self.get_agent_voice(agent_id)
        elif not voice:
            voice = DEFAULT_VOICE

        # Check cache
        cache_key = hashlib.md5(f"{text}:{voice}:{rate}:{pitch}".encode(), usedforsecurity=False).hexdigest()
        cache_path = self.cache_dir / f"{cache_key}.mp3"

        if use_cache and cache_path.exists():
            logger.debug("TTS cache hit for: %s", cache_key[:8])
            return cache_path.read_bytes(), "mp3"

        # Synthesize
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
            audio_data = b""

            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]

            # Cache the result
            if use_cache and audio_data:
                cache_path.write_bytes(audio_data)

            return audio_data, "mp3"

        except Exception as e:
            logger.error("TTS synthesis failed: %s", e)
            raise

    async def synthesize_ssml(
        self,
        ssml: str,
        voice: str | None = None,
    ) -> tuple[bytes, str]:
        """Synthesize speech from SSML markup"""
        if not EDGE_TTS_AVAILABLE:
            raise RuntimeError("edge-tts not available")

        voice = voice or DEFAULT_VOICE

        try:
            communicate = edge_tts.Communicate(ssml, voice)
            audio_data = b""

            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]

            return audio_data, "mp3"

        except Exception as e:
            logger.error("SSML synthesis failed: %s", e)
            raise

    async def synthesize_to_file(
        self,
        text: str,
        output_path: str,
        voice: str | None = None,
        agent_id: str | None = None,
    ) -> str:
        """Synthesize to file and return path"""
        audio_data, _ = await self.synthesize(text, voice, agent_id)

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(audio_data)

        return str(output)

    def clear_cache(self, max_age_hours: int = 24):
        """Clear old cached audio files"""
        import time

        cutoff = time.time() - (max_age_hours * 3600)

        cleared = 0
        for cache_file in self.cache_dir.glob("*.mp3"):
            if cache_file.stat().st_mtime < cutoff:
                cache_file.unlink()
                cleared += 1

        logger.info("Cleared %d cached TTS files", cleared)
        return cleared


class LocalSTTService:
    """
    Self-hosted Speech-to-Text using faster-whisper
    Runs locally on CPU, no API keys required
    """

    def __init__(
        self,
        model_size: str = _WHISPER_MODEL_SIZE,
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        """
        Initialize the STT service

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large-v2)
            device: Device to run on (cpu, cuda)
            compute_type: Computation type (int8, float16, float32)
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model: WhisperModel | None = None

    def _get_model(self) -> "WhisperModel":
        """Lazy load the Whisper model"""
        if not WHISPER_AVAILABLE:
            raise RuntimeError("faster-whisper not available")

        if self._model is None:
            logger.info("Loading Whisper model: %s", self.model_size)
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            logger.info("Whisper model loaded successfully")

        return self._model

    def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> dict:
        """
        Transcribe audio file to text

        Args:
            audio_path: Path to audio file
            language: Language code (e.g., "en", "es") or None for auto-detect

        Returns:
            Dict with text, segments, and metadata
        """
        model = self._get_model()

        segments, info = model.transcribe(
            audio_path,
            language=language,
            beam_size=5,
            vad_filter=True,  # Filter out non-speech
        )

        # Collect segments
        segment_list = []
        full_text = []

        for segment in segments:
            segment_list.append(
                {
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip(),
                    "confidence": segment.avg_logprob,
                }
            )
            full_text.append(segment.text.strip())

        return {
            "text": " ".join(full_text),
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "segments": segment_list,
        }

    def transcribe_bytes(
        self,
        audio_data: bytes,
        language: str | None = None,
    ) -> dict:
        """Transcribe audio bytes"""
        # Write to temp file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_data)
            temp_path = f.name

        try:
            return self.transcribe(temp_path, language)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def transcribe_base64(
        self,
        audio_base64: str,
        language: str | None = None,
    ) -> dict:
        """Transcribe base64-encoded audio"""
        audio_data = base64.b64decode(audio_base64)
        return self.transcribe_bytes(audio_data, language)


class HelixVoiceService:
    """
    Unified voice service combining TTS and STT
    Self-hosted, Railway-compatible
    """

    def __init__(
        self,
        tts_cache_dir: str | None = None,
        stt_model_size: str = _WHISPER_MODEL_SIZE,
    ):
        self.tts = LocalTTSService(cache_dir=tts_cache_dir)
        self.stt = LocalSTTService(model_size=stt_model_size)
        self._initialized = False

    async def initialize(self):
        """Initialize the voice service"""
        if self._initialized:
            return

        logger.info("🎙️ Initializing Helix Voice Service")
        logger.info("  TTS: edge-tts (available: %s)", EDGE_TTS_AVAILABLE)
        logger.info("  STT: faster-whisper (available: %s)", WHISPER_AVAILABLE)

        # Warm up TTS by listing voices
        if EDGE_TTS_AVAILABLE:
            await self.tts.list_voices()

        self._initialized = True
        logger.info("🎙️ Voice service initialized")

    def get_status(self) -> dict:
        """Get service status"""
        return {
            "service": "Helix Voice Service",
            "version": "2.0.0",
            "tts_available": EDGE_TTS_AVAILABLE,
            "stt_available": WHISPER_AVAILABLE,
            "tts_provider": "edge-tts (Microsoft)",
            "stt_provider": "faster-whisper (OpenAI Whisper)",
            "self_hosted": True,
            "requires_api_key": False,
            "cache_dir": str(self.tts.cache_dir),
        }

    async def speak(
        self,
        text: str,
        agent_id: str | None = None,
        voice: str | None = None,
        rate: str = "+0%",
        emotion: str | None = None,
    ) -> tuple[bytes, str]:
        """Generate speech for text
        
        Args:
            text: Text to synthesize
            agent_id: Agent ID for agent-specific voice
            voice: Voice name
            rate: Speaking rate
            emotion: Emotion for TTS (e.g., 'cheerful', 'serious', 'excited')
        """
        return await self.tts.synthesize(text, voice, agent_id, rate, emotion=emotion)

    async def speak_as_agent(
        self,
        agent_id: str,
        text: str,
    ) -> tuple[bytes, str]:
        """Generate speech using agent's voice"""
        return await self.tts.synthesize(text, agent_id=agent_id)

    def listen(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> dict:
        """Transcribe audio file"""
        return self.stt.transcribe(audio_path, language)

    def listen_bytes(
        self,
        audio_data: bytes,
        language: str | None = None,
    ) -> dict:
        """Transcribe audio bytes"""
        return self.stt.transcribe_bytes(audio_data, language)


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_voice_service: HelixVoiceService | None = None


def get_voice_service() -> HelixVoiceService:
    """Get the singleton voice service instance"""
    global _voice_service
    if _voice_service is None:
        _voice_service = HelixVoiceService()
    return _voice_service


async def initialize_voice_service() -> HelixVoiceService:
    """Initialize and return the voice service"""
    service = get_voice_service()
    await service.initialize()
    return service


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


async def speak(
    text: str,
    agent_id: str | None = None,
    voice: str | None = None,
) -> tuple[bytes, str]:
    """Quick TTS synthesis"""
    service = get_voice_service()
    return await service.speak(text, agent_id, voice)


async def speak_as_agent(agent_id: str, text: str) -> tuple[bytes, str]:
    """Quick agent TTS"""
    service = get_voice_service()
    return await service.speak_as_agent(agent_id, text)


def listen(audio_path: str, language: str | None = None) -> dict:
    """Quick STT transcription"""
    service = get_voice_service()
    return service.listen(audio_path, language)


__all__ = [
    "AGENT_VOICE_MAP",
    "AVAILABLE_VOICES",
    "EDGE_TTS_AVAILABLE",
    "WHISPER_AVAILABLE",
    "HelixVoiceService",
    "LocalSTTService",
    "LocalTTSService",
    "get_voice_service",
    "initialize_voice_service",
    "listen",
    "speak",
    "speak_as_agent",
]
