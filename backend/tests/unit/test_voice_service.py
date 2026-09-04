"""
AgentOS Phase: Voice Agent — Unit and Integration Test Suite.

Ensures:
- Safe AssemblyAI provider boundaries (mocked, zero credits consumed)
- Authentication error handling (AssemblyAIAuthError)
- Rate limiting / credit exhaustion error handling (AssemblyAIRateLimitError)
- Timeout and processing failure error handling (AssemblyAITranscriptionError)
- Payload safety & size validation (empty audio, oversized audio)
- Voice command delegation to standard AgentOS TaskService / Supervisor
- Auditable event logging
- REST API endpoint contracts
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.config.settings import settings
from backend.app.main import app
from backend.app.models.task import TaskStatus
from backend.app.services.task_service import TaskService
from backend.app.voice.providers.assemblyai import (
    AssemblyAIAuthError,
    AssemblyAIProvider,
    AssemblyAIRateLimitError,
    AssemblyAITranscriptionError,
)
from backend.app.voice.providers.mock import BrowserTextToSpeechProvider, MockSpeechToTextProvider
from backend.app.voice.schemas import TranscriptionResult
from backend.app.voice.service import InvalidAudioError, VoiceService


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_audio_bytes() -> bytes:
    # 200 bytes of dummy webm audio data
    return b"\x1a\x45\xdf\xa3" + b"\x00" * 200


@pytest.fixture(autouse=True)
def restore_voice_providers():
    """Ensure VoiceService overrides are cleanly restored after each test."""
    VoiceService.set_stt_provider(None)
    VoiceService.set_tts_provider(None)
    yield
    VoiceService.set_stt_provider(None)
    VoiceService.set_tts_provider(None)


# ──────────────────────────────────────────────────────────────────────────────
# 1. Payload & Audio Validation Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_validate_audio_rejects_empty():
    with pytest.raises(InvalidAudioError, match="empty or corrupt"):
        VoiceService.validate_audio(b"", "audio/webm")


def test_validate_audio_rejects_tiny():
    with pytest.raises(InvalidAudioError, match="empty or corrupt"):
        VoiceService.validate_audio(b"too_short", "audio/webm")


def test_validate_audio_rejects_oversized():
    with patch.object(settings, "VOICE_MAX_AUDIO_SIZE_BYTES", 100):
        with pytest.raises(InvalidAudioError, match="exceeds maximum permitted size"):
            VoiceService.validate_audio(b"x" * 200, "audio/webm")


def test_validate_audio_accepts_valid(mock_audio_bytes):
    # Should complete without error
    VoiceService.validate_audio(mock_audio_bytes, "audio/webm")


# ──────────────────────────────────────────────────────────────────────────────
# 2. Mock STT & TTS Provider Tests
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mock_speech_to_text_transcription(mock_audio_bytes):
    provider = MockSpeechToTextProvider(canned_transcript="Run the test suite and fix failures.")
    res = await provider.transcribe(mock_audio_bytes, "audio/webm")
    assert res.transcript == "Run the test suite and fix failures."
    assert res.provider == "mock"
    assert res.confidence == 0.98
    assert res.words_count == 7


@pytest.mark.asyncio
async def test_mock_speech_to_text_simulates_auth_failure(mock_audio_bytes):
    provider = MockSpeechToTextProvider(should_fail_auth=True)
    with pytest.raises(AssemblyAIAuthError, match="Mock authentication failure"):
        await provider.transcribe(mock_audio_bytes)


@pytest.mark.asyncio
async def test_mock_speech_to_text_simulates_rate_limit(mock_audio_bytes):
    provider = MockSpeechToTextProvider(should_fail_rate_limit=True)
    with pytest.raises(AssemblyAIRateLimitError, match="quota exhausted"):
        await provider.transcribe(mock_audio_bytes)


@pytest.mark.asyncio
async def test_mock_speech_to_text_simulates_timeout(mock_audio_bytes):
    provider = MockSpeechToTextProvider(should_fail_timeout=True)
    with pytest.raises(AssemblyAITranscriptionError, match="timed out"):
        await provider.transcribe(mock_audio_bytes)


@pytest.mark.asyncio
async def test_browser_tts_provider():
    provider = BrowserTextToSpeechProvider()
    res = await provider.synthesize("Project created successfully.")
    assert res.status == "ok"
    assert res.text == "Project created successfully."
    assert res.provider == "browser"


# ──────────────────────────────────────────────────────────────────────────────
# 3. AssemblyAI REST Provider (Unit with Mocked Network - ZERO CREDITS)
# ──────────────────────────────────────────────────────────────────────────────

def test_assemblyai_provider_rejects_empty_key():
    with pytest.raises(AssemblyAIAuthError, match="key is required"):
        AssemblyAIProvider(api_key="")


@pytest.mark.asyncio
async def test_assemblyai_provider_successful_flow(mock_audio_bytes):
    provider = AssemblyAIProvider(api_key="test-key-fake-123", timeout_seconds=10)

    upload_response = MagicMock(status_code=200)
    upload_response.json.return_value = {"upload_url": "https://cdn.assemblyai.com/upload/test-uuid"}

    submit_response = MagicMock(status_code=200)
    submit_response.json.return_value = {"id": "transcript-job-999"}

    poll_response = MagicMock(status_code=200)
    poll_response.json.return_value = {
        "status": "completed",
        "text": "Create a FastAPI task manager.",
        "confidence": 0.95,
        "audio_duration": 2.4,
        "words": [{"text": "Create"}, {"text": "a"}, {"text": "FastAPI"}, {"text": "task"}, {"text": "manager"}],
    }

    mock_client = AsyncMock()
    mock_client.post.side_effect = [upload_response, submit_response]
    mock_client.get.return_value = poll_response

    with patch("httpx.AsyncClient") as mock_client_cls, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        res = await provider.transcribe(mock_audio_bytes)

    assert res.transcript == "Create a FastAPI task manager."
    assert res.confidence == 0.95
    assert res.duration_seconds == 2.4
    assert res.words_count == 5
    assert res.provider == "assemblyai"


@pytest.mark.asyncio
async def test_assemblyai_provider_handles_auth_error(mock_audio_bytes):
    provider = AssemblyAIProvider(api_key="invalid-key", timeout_seconds=10)

    upload_response = MagicMock(status_code=401, text="Unauthorized")
    mock_client = AsyncMock()
    mock_client.post.return_value = upload_response

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        with pytest.raises(AssemblyAIAuthError, match="Invalid or unauthorized"):
            await provider.transcribe(mock_audio_bytes)


@pytest.mark.asyncio
async def test_assemblyai_provider_handles_rate_limit(mock_audio_bytes):
    provider = AssemblyAIProvider(api_key="capped-key", timeout_seconds=10)

    upload_response = MagicMock(status_code=429, text="Rate limit exceeded")
    mock_client = AsyncMock()
    mock_client.post.return_value = upload_response

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        with pytest.raises(AssemblyAIRateLimitError, match="credit quota exceeded"):
            await provider.transcribe(mock_audio_bytes)


# ──────────────────────────────────────────────────────────────────────────────
# 4. VoiceService Pipeline & Task Integration Tests
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_voice_command_launches_task(mock_audio_bytes):
    mock_provider = MockSpeechToTextProvider(
        canned_transcript="Build a REST API endpoint for health check."
    )
    VoiceService.set_stt_provider(mock_provider)

    with patch("backend.app.services.multi_agent_service.MultiAgentService.start_task") as mock_start:
        response = await VoiceService.execute_voice_command(
            audio_bytes=mock_audio_bytes,
            mime_type="audio/webm",
            auto_start=True,
            sync=True,
        )

    assert response.status == "planning"
    assert response.transcript == "Build a REST API endpoint for health check."
    assert response.task_id is not None
    assert "Build a REST API endpoint" in response.tts_summary

    # Verify task exists in the real TaskService
    task = TaskService.get_task(response.task_id)
    assert task is not None
    assert task.user_request == "Build a REST API endpoint for health check."
    mock_start.assert_called_once_with(
        instruction="Build a REST API endpoint for health check.",
        sync=True,
    )


@pytest.mark.asyncio
async def test_execute_voice_command_with_empty_transcript(mock_audio_bytes):
    mock_provider = MockSpeechToTextProvider(canned_transcript="   ")
    VoiceService.set_stt_provider(mock_provider)

    response = await VoiceService.execute_voice_command(
        audio_bytes=mock_audio_bytes,
        mime_type="audio/webm",
    )
    assert response.status == "failed"
    assert response.task_id is None
    assert "speak again" in response.tts_summary.lower()


# ──────────────────────────────────────────────────────────────────────────────
# 5. REST API Router Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_api_voice_status():
    client = TestClient(app)
    res = client.get("/api/v1/voice/status")
    assert res.status_code == 200
    data = res.json()
    assert "stt_provider" in data
    assert "has_api_key" in data
    assert "allowed_mime_types" in data


def test_api_voice_transcribe_endpoint(mock_audio_bytes):
    mock_provider = MockSpeechToTextProvider(canned_transcript="Analyze repository structure.")
    VoiceService.set_stt_provider(mock_provider)

    client = TestClient(app)
    files = {"file": ("audio.webm", io.BytesIO(mock_audio_bytes), "audio/webm")}
    res = client.post("/api/v1/voice/transcribe", files=files)

    assert res.status_code == 200
    data = res.json()
    assert data["transcript"] == "Analyze repository structure."
    assert data["provider"] == "mock"


def test_api_voice_execute_endpoint(mock_audio_bytes):
    mock_provider = MockSpeechToTextProvider(canned_transcript="Test all authentication routes.")
    VoiceService.set_stt_provider(mock_provider)

    client = TestClient(app)
    files = {"file": ("command.webm", io.BytesIO(mock_audio_bytes), "audio/webm")}

    with patch("backend.app.services.multi_agent_service.MultiAgentService.start_task"):
        res = client.post(
            "/api/v1/voice/execute",
            files=files,
            data={"auto_start": "false"},
        )

    assert res.status_code == 200
    data = res.json()
    assert data["transcript"] == "Test all authentication routes."
    assert data["task_id"] is not None
    assert data["status"] == "created"
    assert "Test all authentication routes" in data["tts_summary"]


def test_api_voice_synthesize_endpoint():
    client = TestClient(app)
    res = client.post(
        "/api/v1/voice/synthesize",
        json={"text": "Task finished. All tests passed."},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["text"] == "Task finished. All tests passed."
    assert data["provider"] == "browser"
