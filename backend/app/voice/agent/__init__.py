"""
AgentOS Voice Agent Package.

Provides dedicated voice control and natural language command routing for AgentOS.
"""

from backend.app.voice.agent.agent import VoiceAgent, VoiceAgentResult
from backend.app.voice.agent.command_router import AgentOSCommandGateway
from backend.app.voice.agent.confirmation import ConfirmationGate
from backend.app.voice.agent.conversation import ConversationState
from backend.app.voice.agent.intent import IntentType, VoiceIntent

__all__ = [
    "VoiceAgent",
    "VoiceAgentResult",
    "AgentOSCommandGateway",
    "ConfirmationGate",
    "ConversationState",
    "IntentType",
    "VoiceIntent",
]
