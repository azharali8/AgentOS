"""
AgentOS Voice Architecture — Voice Service.

Central coordinator for voice input processing:
- Provider lifecycle & resolution (AssemblyAI vs Mock)
- Audio payload validation & size clamping
- Auditable event emission (voice.requested, voice.transcription.*, voice.task.*)
- Delegates intent classification and command routing to VoiceAgent
- Generates natural, concise voice feedback summary for Text-to-Speech

Architecture:
    VoiceService (API boundary & provider lifecycle)
        → VoiceAgent (intent classification + command routing)
            → CommandRouter → AgentOSCommandGateway
                → TaskService / ProjectCreatorService / MultiAgentService
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.config.settings import settings
from backend.app.models.task import TaskRequest, TaskStatus
from backend.app.services.event_service import EventService
from backend.app.services.multi_agent_service import MultiAgentService
from backend.app.services.task_service import TaskService
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
    "application/octet-stream",  # often sent by generic browser form data
]


class VoiceServiceError(Exception):
    """Base exception for VoiceService domain errors."""
    pass


class InvalidAudioError(VoiceServiceError):
    """Raised when audio payload is invalid, empty, or exceeds size limits."""
    pass


class VoiceService:
    """Service orchestrating voice recognition, execution, and audio synthesis."""

    _stt_provider_override: Optional[SpeechToTextProvider] = None
    _tts_provider_override: Optional[TextToSpeechProvider] = None

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

        # In test or dev without key, fallback safely to mock to prevent credit usage / crash
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
    def _detect_project_creation(cls, transcript: str) -> Optional[Dict[str, str]]:
        """
        Check if transcript is requesting to create a brand new project.
        E.g.:
        - 'AgentOS, create a FastAPI URL shortener with authentication and tests.'
        - 'Create a new project named TaskFlow'
        - 'Scaffold a Python CLI project called MyTool'
        """
        lower = transcript.lower()

        # Check for explicit or implicit project creation phrases
        triggers = [
            "create a new project",
            "create new project",
            "scaffold project",
            "scaffold a project",
            "create a fastapi",
            "create a python",
            "create a react",
            "create a nextjs",
            "create a web app",
            "create an app",
            "create a url shortener",
        ]

        is_creation = any(t in lower for t in triggers)
        if not is_creation:
            return None

        # 1. Look for explicit project name patterns: "named <name>", "called <name>", "project <name>"
        match = re.search(r"(?:project|called|named)\s+([a-zA-Z0-9_\-]+)", transcript, re.IGNORECASE)
        if match and match.group(1).lower() not in {"a", "an", "the", "with", "for", "in"}:
            proj_name = match.group(1)
        else:
            # 2. Derive a clean name from key technology or task keywords
            if "url shortener" in lower or "url-shortener" in lower:
                proj_name = "UrlShortenerApp"
            elif "fastapi" in lower:
                proj_name = "FastApiProject"
            elif "todo" in lower:
                proj_name = "TodoApp"
            elif "api" in lower:
                proj_name = "ApiProject"
            else:
                proj_name = "NewAgentOSProject"

        return {"name": proj_name, "instruction": transcript}

    @classmethod
    async def execute_voice_command(
        cls,
        audio_bytes: bytes,
        mime_type: str = "audio/webm",
        user_id: Optional[str] = None,
        auto_start: bool = True,
        sync: bool = False,
    ) -> VoiceExecuteResponse:
        """
        Core Voice Execution Workflow:
        1. Transcribe audio via active provider (AssemblyAI or Mock)
        2. Feed transcript directly into the EXISTING AgentOS Supervisor / TaskService pipeline
        3. No fake animations, no duplicate voice supervisor
        4. Return live execution status & natural TTS response
        """
        EventService.record_event(
            task_id="system-voice",
            event_type="voice.requested",
            payload={"user_id": user_id, "mime_type": mime_type},
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

        # Check if voice command is asking to scaffold a project
        proj_creation = cls._detect_project_creation(transcript_text)
        project_created = False
        project_path = None

        if proj_creation:
            from backend.app.services.project_creator import ProjectCreatorService
            try:
                from backend.app.services.workspace_service import WorkspaceService
                from backend.app.config.settings import PROJECT_ROOT
                agentos_root = Path(PROJECT_ROOT).resolve()
                current_root = WorkspaceService.get_workspace_root()

                # Determine a safe project parent location
                if current_root.resolve() == agentos_root / "workspace":
                    # Default workspace inside repo -> use workspace itself or tmp/projects for safe creation
                    parent_dir = current_root
                elif current_root.exists() and current_root.is_dir() and not current_root.resolve().is_relative_to(agentos_root):
                    # Outside existing workspace -> use its parent
                    parent_dir = current_root.parent
                else:
                    parent_dir = current_root

                proj_meta = ProjectCreatorService.create_project(
                    name=proj_creation["name"],
                    location=str(parent_dir),
                    instruction=transcript_text,
                )
                project_created = True
                project_path = proj_meta["path"]
            except Exception as exc:
                logger.warning("Project creation through voice skipped or failed: %s; falling back to normal task", exc)

        # Standard AgentOS task pipeline
        task_req = TaskRequest(instruction=transcript_text)
        task_record = TaskService.create_task(request=task_req)
        task_id = task_record.task_id

        EventService.record_event(
            task_id=task_id,
            event_type="voice.task.submitted",
            payload={
                "instruction": transcript_text,
                "project_created": project_created,
                "project_path": project_path,
                "provider": transcription.provider,
            },
        )

        if auto_start:
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

        # Generate natural TTS summary
        tts_text = f"Got it. Starting engineering task: {transcript_text[:90]}"
        if len(transcript_text) > 90:
            tts_text += "..."

        return VoiceExecuteResponse(
            status="planning" if auto_start else "created",
            transcript=transcript_text,
            task_id=task_id,
            project_created=project_created,
            project_path=project_path,
            tts_summary=tts_text,
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
