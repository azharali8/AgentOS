"""
AgentOS Voice Package.

Integrates AssemblyAI speech-to-text and speech synthesis with the
canonical AgentOS supervisor engineering pipeline.
"""

from backend.app.voice.service import VoiceService
from backend.app.voice.router import router as voice_router

__all__ = ["VoiceService", "voice_router"]
