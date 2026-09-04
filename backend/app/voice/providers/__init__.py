"""
AgentOS Voice Architecture — Voice Providers Package.
"""

from backend.app.voice.providers.base import SpeechToTextProvider, TextToSpeechProvider
from backend.app.voice.providers.assemblyai import (
    AssemblyAIProvider,
    AssemblyAIError,
    AssemblyAIAuthError,
    AssemblyAIRateLimitError,
    AssemblyAITranscriptionError,
)
from backend.app.voice.providers.mock import (
    MockSpeechToTextProvider,
    BrowserTextToSpeechProvider,
)

__all__ = [
    "SpeechToTextProvider",
    "TextToSpeechProvider",
    "AssemblyAIProvider",
    "AssemblyAIError",
    "AssemblyAIAuthError",
    "AssemblyAIRateLimitError",
    "AssemblyAITranscriptionError",
    "MockSpeechToTextProvider",
    "BrowserTextToSpeechProvider",
]
