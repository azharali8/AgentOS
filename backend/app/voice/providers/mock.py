"""
AgentOS Voice Architecture — Mock Speech & TTS Providers for Testing.

Provides deterministic, credit-safe testing of the entire voice pipeline:
- No network requests
- Zero AssemblyAI credit usage
- Configurable failure simulation (auth error, timeout, rate limit)
"""

from __future__ import annotations

from typing import Optional

from backend.app.voice.providers.base import SpeechToTextProvider, TextToSpeechProvider
from backend.app.voice.schemas import TranscriptionResult, TTSResponse


class MockSpeechToTextProvider(SpeechToTextProvider):
    """Deterministic Speech-to-Text mock provider for unit and regression tests."""

    def __init__(
        self,
        canned_transcript: str = "Create a FastAPI URL shortener with authentication and tests.",
        should_fail_auth: bool = False,
        should_fail_timeout: bool = False,
        should_fail_rate_limit: bool = False,
    ) -> None:
        self.canned_transcript = canned_transcript
        self.should_fail_auth = should_fail_auth
        self.should_fail_timeout = should_fail_timeout
        self.should_fail_rate_limit = should_fail_rate_limit
        self.transcribe_call_count = 0

    async def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/webm",
        language_code: Optional[str] = "en",
    ) -> TranscriptionResult:
        self.transcribe_call_count += 1

        if self.should_fail_auth:
            from backend.app.voice.providers.assemblyai import AssemblyAIAuthError
            raise AssemblyAIAuthError("Mock authentication failure: invalid key.")

        if self.should_fail_rate_limit:
            from backend.app.voice.providers.assemblyai import AssemblyAIRateLimitError
            raise AssemblyAIRateLimitError("Mock rate limit failure: quota exhausted.")

        if self.should_fail_timeout:
            from backend.app.voice.providers.assemblyai import AssemblyAITranscriptionError
            raise AssemblyAITranscriptionError("Mock timeout failure: transcription job timed out.")

        if not audio_bytes or len(audio_bytes) < 10:
            from backend.app.voice.providers.assemblyai import AssemblyAITranscriptionError
            raise AssemblyAITranscriptionError("Audio payload too small or empty.")

        return TranscriptionResult(
            transcript=self.canned_transcript,
            confidence=0.98,
            duration_seconds=3.5,
            words_count=len(self.canned_transcript.split()),
            provider="mock",
            language_code=language_code or "en",
        )


class BrowserTextToSpeechProvider(TextToSpeechProvider):
    """Default lightweight TTS provider that prepares the browser for speech synthesis."""

    async def synthesize(self, text: str, voice: Optional[str] = None) -> TTSResponse:
        return TTSResponse(
            status="ok",
            text=text.strip(),
            audio_base64=None,
            mime_type="text/plain",
            provider="browser",
        )
