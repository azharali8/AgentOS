"""
AgentOS Voice Architecture — Base Provider Interfaces.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from backend.app.voice.schemas import TranscriptionResult, TTSResponse


class SpeechToTextProvider(ABC):
    """Abstract interface for speech-to-text providers."""

    @abstractmethod
    async def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/webm",
        language_code: Optional[str] = "en",
    ) -> TranscriptionResult:
        """Transcribe raw audio bytes into text."""
        pass


class TextToSpeechProvider(ABC):
    """Abstract interface for text-to-speech providers."""

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
    ) -> TTSResponse:
        """Synthesize text into speech audio or browser instruction."""
        pass
