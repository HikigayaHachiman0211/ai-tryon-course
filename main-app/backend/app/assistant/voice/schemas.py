"""Voice module schemas — shared by ASR, TTS, voice catalog, and call mode."""
from __future__ import annotations

from pydantic import BaseModel, Field


class VoicePublicConfig(BaseModel):
    """Non-sensitive voice config exposed to the main site frontend."""
    asr_enabled: bool = False
    tts_enabled: bool = False
    voice_clone_enabled: bool = False
    asr_disabled_reason: str = ""
    tts_disabled_reason: str = ""
    default_asr_provider: str = "mimo_asr"
    default_asr_model: str = "mimo-v2.5-asr"
    default_tts_provider: str = "mimo_tts"
    default_tts_model: str = "mimo-v2.5-tts"
    default_voice: str = "茉莉"
    available_voices: list[str] = Field(default_factory=lambda: [
        "冰糖", "茉莉", "苏打", "白桦", "Mia", "Chloe", "Milo", "Dean",
    ])
    published_clone_voices: list[dict[str, str]] = Field(default_factory=list)
    asr_languages: list[str] = Field(default_factory=lambda: ["zh", "en", "auto"])
    max_record_seconds: int = 15
    hard_max_record_seconds: int = 55
    max_audio_base64_mb: int = 10
    supported_audio_formats: list[str] = Field(default_factory=lambda: ["wav", "mp3"])
    default_language: str = "zh"
    max_tts_text_length: int = 300


class ASRResponse(BaseModel):
    success: bool = False
    text: str = ""
    normalized_text: str | None = None
    provider: str = "mimo"
    model: str = "mimo-v2.5-asr"
    language: str = "zh"
    duration_ms: int | None = None
    latency_ms: int | None = None
    error: dict[str, str] | None = None


class TTSRequest(BaseModel):
    session_id: str = ""
    text: str = ""
    voice: str | None = None
    format: str | None = "wav"
    style_prompt: str | None = None
    voice_source: str | None = "preset"  # preset | clone
    clone_voice_id: str | None = None
    tone_preset: str | None = None
    volume: float | None = 1.0


class TTSResponse(BaseModel):
    success: bool = False
    audio_url: str | None = None
    audio_base64: str | None = None
    format: str = "wav"
    voice: str = "茉莉"
    provider: str = "mimo"
    model: str = "mimo-v2.5-tts"
    error: dict[str, str] | None = None


class VoiceCatalogItem(BaseModel):
    id: str
    name: str
    source: str = "preset"  # preset | clone
    enabled: bool = True
    published: bool = True
    description: str | None = None
    gender: str | None = None
    language: str | None = None
