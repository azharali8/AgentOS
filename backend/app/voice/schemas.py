"""
AgentOS Voice Architecture — Schemas.

Defines typed request and response envelopes for voice operations:
- Audio transcription
- Voice-driven task execution
- Text-to-speech synthesis
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TranscriptionResult(BaseModel):
    transcript: str = Field(..., description="Recognized speech text")
    confidence: Optional[float] = Field(default=None, description="Confidence score between 0.0 and 1.0")
    duration_seconds: Optional[float] = Field(default=None, description="Audio duration in seconds")
    words_count: int = Field(default=0, description="Total words transcribed")
    provider: str = Field(..., description="Provider used (assemblyai, mock)")
    language_code: Optional[str] = Field(default="en", description="Detected or configured language code")


class VoiceExecuteResponse(BaseModel):
    status: str = Field(..., description="Execution status: ok, planning, executing, created")
    transcript: str = Field(..., description="Transcribed voice command")
    task_id: Optional[str] = Field(default=None, description="Associated AgentOS task ID")
    project_created: bool = Field(default=False, description="Whether a new project was scaffolded")
    project_path: Optional[str] = Field(default=None, description="Target workspace path if project was created")
    tts_summary: str = Field(..., description="Succinct voice summary response for Text-To-Speech")
    provider: str = Field(..., description="Speech provider used")
    confidence: Optional[float] = Field(default=None)


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description="Text to synthesize")
    voice: Optional[str] = Field(default=None, description="Voice identifier")


class TTSResponse(BaseModel):
    status: str = Field(default="ok")
    text: str
    audio_base64: Optional[str] = Field(default=None, description="Base64-encoded audio (if backend synthesizes)")
    mime_type: str = Field(default="audio/wav")
    provider: str = Field(default="browser", description="browser, edge_tts, mock")


class VoiceProviderStatus(BaseModel):
    stt_provider: str
    has_api_key: bool
    tts_provider: str
    max_audio_size_mb: float
    allowed_mime_types: List[str]
