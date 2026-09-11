"""
AgentOS Voice Architecture — Voice API Router.

Endpoints:
- POST /api/v1/voice/transcribe: Transcribes audio file without starting task.
- POST /api/v1/voice/execute: Transcribes audio and immediately launches the VoiceAgent & Supervisor pipeline.
- POST /api/v1/voice/command: Direct text command processing for VoiceAgent.
- POST /api/v1/voice/synthesize: Synthesizes text to speech.
- GET /api/v1/voice/status: Returns voice subsystem status without exposing keys.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from backend.app.auth.service import AuthenticatedUser, get_current_user, require_role, UserRole
from backend.app.voice.agent.agent import VoiceAgent
from backend.app.voice.providers.assemblyai import (
    AssemblyAIAuthError,
    AssemblyAIRateLimitError,
    AssemblyAITranscriptionError,
)
from backend.app.voice.schemas import (
    TranscriptionResult,
    TTSRequest,
    TTSResponse,
    VoiceExecuteResponse,
    VoiceProviderStatus,
)
from backend.app.voice.service import InvalidAudioError, VoiceService

logger = logging.getLogger("agentos.voice.router")

router = APIRouter(prefix="/voice", tags=["v1-voice"])


class TextCommandRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=2000, description="Text voice command")
    session_id: str = Field(default="default-session", description="Session identifier for multi-turn context")


@router.get("/status", response_model=VoiceProviderStatus)
def get_voice_status() -> VoiceProviderStatus:
    """Return status of speech-to-text and text-to-speech providers."""
    return VoiceService.get_status()


@router.post("/transcribe", response_model=TranscriptionResult)
async def transcribe_audio(
    file: UploadFile = File(...),
    language: Optional[str] = Form(default="en"),
    user: AuthenticatedUser = Depends(get_current_user),
) -> TranscriptionResult:
    """
    Transcribe uploaded audio file into text.
    Uses AssemblyAI when configured; falls back cleanly to mock provider in tests.
    """
    try:
        audio_bytes = await file.read()
        mime_type = file.content_type or "audio/webm"
        return await VoiceService.transcribe_audio(
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            language_code=language,
        )
    except InvalidAudioError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except AssemblyAIAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    except AssemblyAIRateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc))
    except AssemblyAITranscriptionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    except Exception as exc:
        logger.error("Unhandled voice transcription error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Voice transcription failed: {str(exc)}")


@router.post("/execute", response_model=VoiceExecuteResponse)
async def execute_voice_command(
    file: UploadFile = File(...),
    session_id: str = Form(default="default-session"),
    auto_start: bool = Form(default=True),
    sync: bool = Form(default=False),
    user: AuthenticatedUser = Depends(require_role(UserRole.USER)),
) -> VoiceExecuteResponse:
    """
    Core Voice Endpoint:
    Uploads microphone audio -> transcribes -> processes via VoiceAgent & AgentOSCommandGateway.
    Returns live task ID, project metadata, and TTS summary response.
    """
    try:
        audio_bytes = await file.read()
        mime_type = file.content_type or "audio/webm"
        return await VoiceService.execute_voice_command(
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            user_id=user.user_id,
            session_id=session_id,
            auto_start=auto_start,
            sync=sync,
            user_role=user.role.value,
        )
    except InvalidAudioError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except AssemblyAIAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    except AssemblyAIRateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc))
    except AssemblyAITranscriptionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    except Exception as exc:
        logger.error("Unhandled voice execution error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Voice command execution failed: {str(exc)}")


@router.post("/command", response_model=VoiceExecuteResponse)
async def execute_text_command(
    req: TextCommandRequest,
    user: AuthenticatedUser = Depends(require_role(UserRole.USER)),
) -> VoiceExecuteResponse:
    """Process a typed voice-style command directly through the VoiceAgent."""
    try:
        return VoiceService.process_transcript(req.command, user_id=user.user_id,
                                               session_id=req.session_id, user_role=user.role.value)
    except Exception as exc:
        logger.error("Text command processing error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Command processing failed: {str(exc)}")


@router.post("/synthesize", response_model=TTSResponse)
async def synthesize_text(
    req: TTSRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> TTSResponse:
    """Synthesize text into speech or browser voice instructions."""
    return await VoiceService.synthesize_speech(text=req.text, voice=req.voice)
