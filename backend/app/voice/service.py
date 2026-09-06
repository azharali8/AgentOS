"""
AgentOS Voice Architecture — Voice Service.

Central coordinator for voice input processing:
- Provider lifecycle & resolution (AssemblyAI vs Mock)
- Audio payload validation & size clamping
- Auditable event emission (voice.requested, voice.transcription.*, voice.agent.*)
- Delegates intent understanding & routing to dedicated VoiceAgent & AgentOSCommandGateway
- Generates natural, concise voice feedback summary for Text-to-Speech
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.config.settings import settings
from backend.app.models.task import TaskRequest, TaskStatus
from backend.app.services.event_service import EventService
from backend.app.services.multi_agent_service import MultiAgentService
from backend.app.services.task_service import TaskService
from backend.app.voice.agent.agent import VoiceAgent, VoiceAgentResult
from backend.app.voice.agent.conversation import ConversationState
from backend.app.voice.providers.assemblyai import AssemblyAIProvider
from backend.app.voice.providers.base import SpeechToTextProvider, TextToSpeechProvider
from backend.app.voice.providers.mock import BrowserTextToSpeechProvider, MockSpeechToTextProvider
from backend.app.voice.schemas import (
    TranscriptionResult,
    TTSRequest,
    TTSResponse,
    VoiceExecuteResponse,
    VoiceProviderStatus,
)

logger = logging.getLogger("agentos.voice.service")

_ALLOWED_AUDIO_MIMES = [
    "audio/webm",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/ogg",
    "audio/mp4",
    "audio/aac",
    "audio/flac",
    "application/octet-stream",
]


class VoiceServiceError(Exception):
    """Base exception for VoiceService domain errors."""
    pass


class InvalidAudioError(VoiceServiceError):
    """Raised when audio payload is invalid, empty, or exceeds size limits."""
    pass


class VoiceService:
    """Service orchestrating voice recognition, VoiceAgent execution, and audio synthesis."""

    _stt_provider_override: Optional[SpeechToTextProvider] = None
    _tts_provider_override: Optional[TextToSpeechProvider] = None
    _session_conversations: Dict[str, ConversationState] = {}

    @classmethod
    def set_stt_provider(cls, provider: Optional[SpeechToTextProvider]) -> None:
        """Allow injecting a test/mock provider directly."""
        cls._stt_provider_override = provider

    @classmethod
    def set_tts_provider(cls, provider: Optional[TextToSpeechProvider]) -> None:
        """Allow injecting a test/mock TTS provider directly."""
        cls._tts_provider_override = provider

    @classmethod
    def get_stt_provider(cls) -> SpeechToTextProvider:
        """Resolve the active Speech-to-Text provider."""
        if cls._stt_provider_override is not None:
            return cls._stt_provider_override

        api_key = settings.ASSEMBLYAI_API_KEY.strip()
        preferred_provider = (settings.VOICE_PROVIDER or "assemblyai").lower().strip()

        if preferred_provider == "assemblyai" and api_key:
            return AssemblyAIProvider(
                api_key=api_key,
                timeout_seconds=settings.VOICE_TIMEOUT_SECONDS,
            )
        else:
            return MockSpeechToTextProvider()

    @classmethod
    def get_tts_provider(cls) -> TextToSpeechProvider:
        """Resolve the active Text-to-Speech provider."""
        if cls._tts_provider_override is not None:
            return cls._tts_provider_override
        return BrowserTextToSpeechProvider()

    @classmethod
    def get_conversation_state(cls, session_id: str = "default-session") -> ConversationState:
        """Retrieve or create session-scoped ConversationState."""
        if session_id not in cls._session_conversations or cls._session_conversations[session_id].is_expired():
            cls._session_conversations[session_id] = ConversationState(session_id=session_id)
        return cls._session_conversations[session_id]

    @classmethod
    def validate_audio(cls, audio_bytes: bytes, mime_type: str) -> None:
        """Validate audio bytes length and MIME type."""
        if not audio_bytes or len(audio_bytes) < 32:
            raise InvalidAudioError("Uploaded audio is empty or corrupt.")

        max_size = settings.VOICE_MAX_AUDIO_SIZE_BYTES
        if len(audio_bytes) > max_size:
            mb = max_size / (1024 * 1024)
            raise InvalidAudioError(f"Audio exceeds maximum permitted size of {mb:.1f} MB.")

        clean_mime = mime_type.split(";")[0].strip().lower()
        if clean_mime not in _ALLOWED_AUDIO_MIMES:
            logger.warning("Uncommon audio MIME type: %s; proceeding cautiously", clean_mime)

    @classmethod
    async def transcribe_audio(
        cls,
        audio_bytes: bytes,
        mime_type: str = "audio/webm",
        language_code: Optional[str] = "en",
    ) -> TranscriptionResult:
        """Validate and transcribe audio with auditable events."""
        cls.validate_audio(audio_bytes, mime_type)

        EventService.record_event(
            task_id="system-voice",
            event_type="voice.transcription.started",
            payload={"audio_size_bytes": len(audio_bytes), "mime_type": mime_type},
        )

        provider = cls.get_stt_provider()
        try:
            result = await provider.transcribe(
                audio_bytes=audio_bytes,
                mime_type=mime_type,
                language_code=language_code,
            )
            EventService.record_event(
                task_id="system-voice",
                event_type="voice.transcription.completed",
                payload={
                    "transcript": result.transcript,
                    "provider": result.provider,
                    "duration_seconds": result.duration_seconds,
                },
            )
            return result
        except Exception as exc:
            EventService.record_event(
                task_id="system-voice",
                event_type="voice.transcription.failed",
                payload={"error": str(exc)},
            )
            raise

    @classmethod
    async def execute_voice_command(
        cls,
        audio_bytes: bytes,
        mime_type: str = "audio/webm",
        user_id: Optional[str] = None,
        session_id: str = "default-session",
        auto_start: bool = True,
        sync: bool = False,
    ) -> VoiceExecuteResponse:
        """
        Voice Execution Workflow:
        1. Transcribe audio via active provider (AssemblyAI or Mock)
        2. Delegate intent classification and execution to VoiceAgent & AgentOSCommandGateway
        3. Emit auditable voice lifecycle events
        4. If a task was created and auto_start is True, trigger MultiAgentService
        5. Return natural TTS feedback and structured response
        """
        EventService.record_event(
            task_id="system-voice",
            event_type="voice.requested",
            payload={"user_id": user_id, "session_id": session_id, "mime_type": mime_type},
        )

        transcription = await cls.transcribe_audio(audio_bytes, mime_type)
        transcript_text = transcription.transcript.strip()

        if not transcript_text:
            return VoiceExecuteResponse(
                status="failed",
                transcript="",
                tts_summary="I didn't catch that. Please speak again clearly.",
                provider=transcription.provider,
                confidence=transcription.confidence,
            )

        # Retrieve conversation context and execute via VoiceAgent
        conv = cls.get_conversation_state(session_id)
        agent = VoiceAgent(conversation=conv)
        agent_res: VoiceAgentResult = agent.process(transcript=transcript_text, user_id=user_id)

        task_id = agent_res.task_id
        final_status = "planning" if (auto_start and task_id and agent_res.status in ("created", "planning")) else agent_res.status

        EventService.record_event(
            task_id=task_id or "system-voice",
            event_type="voice.agent.executed",
            payload={
                "intent_type": agent_res.intent_type.value if hasattr(agent_res.intent_type, "value") else str(agent_res.intent_type),
                "status": final_status,
                "project_created": agent_res.project_created,
                "project_path": agent_res.project_path,
                "provider": transcription.provider,
            },
        )

        # Trigger background execution if a new engineering task was created
        if task_id and auto_start and agent_res.status in ("created", "planning", "ok"):
            import threading

            def _bg_execute():
                try:
                    TaskService.update_task_status(task_id, TaskStatus.PLANNING)
                    MultiAgentService.start_task(instruction=transcript_text, sync=True)
                    EventService.record_event(
                        task_id=task_id,
                        event_type="voice.task.completed",
                        payload={"status": "COMPLETED"},
                    )
                except Exception as exc:
                    TaskService.set_error(task_id, str(exc))
                    EventService.record_event(
                        task_id=task_id,
                        event_type="voice.task.failed",
                        payload={"error": str(exc)},
                    )

            if sync:
                _bg_execute()
            else:
                thread = threading.Thread(
                    target=_bg_execute,
                    daemon=True,
                    name=f"voice-exec-{task_id[:8]}",
                )
                thread.start()

        return VoiceExecuteResponse(
            status=final_status,
            transcript=transcript_text,
            task_id=agent_res.task_id,
            project_created=agent_res.project_created,
            project_path=agent_res.project_path,
            tts_summary=agent_res.tts_summary,
            provider=transcription.provider,
            confidence=transcription.confidence,
        )

    @classmethod
    async def synthesize_speech(cls, text: str, voice: Optional[str] = None) -> TTSResponse:
        """Synthesize response text for browser / voice playback."""
        tts_provider = cls.get_tts_provider()
        return await tts_provider.synthesize(text=text, voice=voice)

    @classmethod
    def get_status(cls) -> VoiceProviderStatus:
        """Get voice runtime status without exposing secrets."""
        key = settings.ASSEMBLYAI_API_KEY.strip()
        provider = cls.get_stt_provider()
        return VoiceProviderStatus(
            stt_provider=provider.__class__.__name__,
            has_api_key=bool(key),
            tts_provider=settings.VOICE_TTS_PROVIDER,
            max_audio_size_mb=round(settings.VOICE_MAX_AUDIO_SIZE_BYTES / (1024 * 1024), 1),
            allowed_mime_types=_ALLOWED_AUDIO_MIMES,
        )
