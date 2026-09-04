"""
AgentOS Voice Architecture — AssemblyAI Speech-to-Text Provider.

Integrates with the AssemblyAI REST API:
- POST /v2/upload (streams audio chunks)
- POST /v2/transcript (initiates speech model)
- GET /v2/transcript/{id} (polls completion)

Security & Credit Safeguards:
- Never hardcodes or exposes API key in logs
- Validates non-empty audio payload
- Detects authentication errors (401), rate limits / quotas (429), and transcript errors
- Sets reasonable timeout to prevent hanging connections
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from backend.app.voice.providers.base import SpeechToTextProvider
from backend.app.voice.schemas import TranscriptionResult

logger = logging.getLogger("agentos.voice.assemblyai")

BASE_URL = "https://api.assemblyai.com/v2"


class AssemblyAIError(Exception):
    """Base exception for AssemblyAI service interactions."""
    pass


class AssemblyAIAuthError(AssemblyAIError):
    """Raised when API key is missing, invalid, or unauthorized."""
    pass


class AssemblyAIRateLimitError(AssemblyAIError):
    """Raised when account credit limit is exhausted or rate limited."""
    pass


class AssemblyAITranscriptionError(AssemblyAIError):
    """Raised when transcription fails during processing."""
    pass


class AssemblyAIProvider(SpeechToTextProvider):
    """Production Speech-to-Text provider powered by AssemblyAI."""

    def __init__(self, api_key: str, timeout_seconds: int = 60) -> None:
        if not api_key or not api_key.strip():
            raise AssemblyAIAuthError("AssemblyAI API key is required but was not provided.")
        self._api_key = api_key.strip()
        self._timeout = timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {
            "authorization": self._api_key,
        }

    async def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/webm",
        language_code: Optional[str] = "en",
    ) -> TranscriptionResult:
        if not audio_bytes or len(audio_bytes) < 100:
            raise AssemblyAITranscriptionError("Audio payload is empty or too small to process.")

        headers = self._headers()

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            # 1. Upload audio to AssemblyAI upload endpoint
            logger.info("Uploading audio (%d bytes) to AssemblyAI...", len(audio_bytes))
            try:
                upload_res = await client.post(
                    f"{BASE_URL}/upload",
                    headers=headers,
                    content=audio_bytes,
                )
            except httpx.TimeoutException:
                raise AssemblyAITranscriptionError("Upload timed out connecting to AssemblyAI.")
            except Exception as exc:
                raise AssemblyAITranscriptionError(f"Network error during audio upload: {str(exc)}")

            if upload_res.status_code in (401, 403):
                raise AssemblyAIAuthError("Invalid or unauthorized AssemblyAI API key.")
            elif upload_res.status_code == 429:
                raise AssemblyAIRateLimitError("AssemblyAI rate limit or credit quota exceeded.")
            elif upload_res.status_code >= 400:
                raise AssemblyAITranscriptionError(
                    f"AssemblyAI upload failed with status {upload_res.status_code}: {upload_res.text}"
                )

            upload_data = upload_res.json()
            audio_url = upload_data.get("upload_url")
            if not audio_url:
                raise AssemblyAITranscriptionError("AssemblyAI upload response missing 'upload_url'.")

            # 2. Submit transcription job
            transcript_payload = {
                "audio_url": audio_url,
                "punctuate": True,
                "format_text": True,
            }
            if language_code and language_code != "auto":
                transcript_payload["language_code"] = language_code

            try:
                submit_res = await client.post(
                    f"{BASE_URL}/transcript",
                    headers={**headers, "content-type": "application/json"},
                    json=transcript_payload,
                )
            except Exception as exc:
                raise AssemblyAITranscriptionError(f"Failed to submit transcription job: {str(exc)}")

            if submit_res.status_code in (401, 403):
                raise AssemblyAIAuthError("Invalid or unauthorized AssemblyAI API key.")
            elif submit_res.status_code == 429:
                raise AssemblyAIRateLimitError("AssemblyAI rate limit or credit quota exceeded.")
            elif submit_res.status_code >= 400:
                raise AssemblyAITranscriptionError(
                    f"AssemblyAI transcript submission failed: {submit_res.text}"
                )

            transcript_job = submit_res.json()
            transcript_id = transcript_job.get("id")
            if not transcript_id:
                raise AssemblyAITranscriptionError("Transcription job ID was not returned.")

            # 3. Poll for completion
            polling_url = f"{BASE_URL}/transcript/{transcript_id}"
            max_attempts = int(self._timeout / 2)  # poll every 2s

            for attempt in range(max_attempts):
                await asyncio.sleep(2)
                try:
                    poll_res = await client.get(polling_url, headers=headers)
                except Exception as exc:
                    logger.warning("Polling retry %d encountered error: %s", attempt, exc)
                    continue

                if poll_res.status_code != 200:
                    continue

                poll_data = poll_res.json()
                current_status = poll_data.get("status")

                if current_status == "completed":
                    text = poll_data.get("text") or ""
                    confidence = poll_data.get("confidence")
                    audio_duration = poll_data.get("audio_duration")
                    words = poll_data.get("words") or []

                    return TranscriptionResult(
                        transcript=text.strip(),
                        confidence=confidence,
                        duration_seconds=audio_duration,
                        words_count=len(words) if words else len(text.split()),
                        provider="assemblyai",
                        language_code=poll_data.get("language_code") or language_code or "en",
                    )
                elif current_status == "error":
                    err_msg = poll_data.get("error") or "Unknown transcription processing error."
                    raise AssemblyAITranscriptionError(f"AssemblyAI processing failed: {err_msg}")

            raise AssemblyAITranscriptionError(
                f"Transcription job {transcript_id} did not complete within {self._timeout}s timeout."
            )
