"""
Tests for Voice Agent Layer:
- VoiceIntent classification
- ConfirmationGate detection & confirmation
- ConversationState multi-turn management
- AgentOSCommandGateway routing & approved operations
- VoiceAgent end-to-end processing & TTS generation
"""

import pytest
from pathlib import Path
from backend.app.voice.agent.agent import VoiceAgent, VoiceAgentResult
from backend.app.voice.agent.command_router import AgentOSCommandGateway
from backend.app.voice.agent.confirmation import ConfirmationGate
from backend.app.voice.agent.conversation import ConversationState
from backend.app.voice.agent.intent import IntentType, VoiceIntent
from backend.app.models.task import TaskStatus
from backend.app.auth.service import AuthenticatedUser, UserRole


class TestVoiceIntentAndConfirmation:
    def test_confirmation_gate_detects_destructive_keywords(self):
        gate = ConfirmationGate()
        assert gate.requires_confirmation("Delete all project files") is True
        assert gate.requires_confirmation("Wipe database") is True
        assert gate.requires_confirmation("rm -rf /workspace/old") is True
        assert gate.requires_confirmation("Run the pytest suite") is False
        assert gate.requires_confirmation("Create a FastAPI URL shortener") is False

    def test_confirmation_gate_recognizes_replies(self):
        gate = ConfirmationGate()
        assert gate.is_confirmed("yes") is True
        assert gate.is_confirmed("confirm") is True
        assert gate.is_confirmed("proceed") is True
        assert gate.is_rejected("no") is True
        assert gate.is_rejected("cancel") is True
        assert gate.is_rejected("abort") is True

    def test_conversation_state_multi_turn_ttl(self):
        conv = ConversationState(session_id="test-session", ttl_seconds=10)
        conv.add_user_turn("Create a new project")
        conv.add_agent_turn("What is the name?")
        assert len(conv.recent_turns()) == 2
        assert conv.is_expired() is False

        conv.set_pending_question("What is the technology?", {"project_name": "TaskApp"})
        assert conv.has_pending_question() is True
        q, ctx = conv.consume_pending_question()
        assert q == "What is the technology?"
        assert ctx["project_name"] == "TaskApp"
        assert conv.has_pending_question() is False


class TestVoiceAgentCommandUnderstanding:
    def test_classify_create_project(self):
        agent = VoiceAgent()
        intent = agent._classify_intent("Create a new project called TaskFlowApp")
        assert intent.intent_type == IntentType.CREATE_PROJECT
        assert intent.project_name == "TaskFlowApp"

    def test_classify_run_tests(self):
        agent = VoiceAgent()
        intent = agent._classify_intent("Run the tests again and tell me the result")
        assert intent.intent_type == IntentType.RUN_TESTS

    def test_classify_investigate_failure(self):
        agent = VoiceAgent()
        intent = agent._classify_intent("Why did the tests fail?")
        assert intent.intent_type == IntentType.INVESTIGATE_FAILURE

    def test_classify_review_changes(self):
        agent = VoiceAgent()
        intent = agent._classify_intent("Review the changes and explain what you modified")
        assert intent.intent_type == IntentType.REVIEW_CHANGES

    def test_classify_task_status(self):
        agent = VoiceAgent()
        intent = agent._classify_intent("Show me the current task status")
        assert intent.intent_type == IntentType.GET_TASK_STATUS

    def test_classify_cancel_task(self):
        agent = VoiceAgent()
        intent = agent._classify_intent("Stop the current task")
        assert intent.intent_type == IntentType.CANCEL_TASK


class TestVoiceAgentEndToEndJourneys:
    def test_voice_connect_requires_verified_developer_principal(self, tmp_path, monkeypatch):
        project = tmp_path / "project"
        project.mkdir()
        calls = []
        monkeypatch.setattr("backend.app.api.routes.v1.set_workspace_root",
                            lambda req, user: calls.append((req.path, user)) or {"path": req.path})
        assert AgentOSCommandGateway.connect_project(str(project))["status"] == "denied"
        viewer = AuthenticatedUser(user_id="viewer", username="viewer", role=UserRole.VIEWER)
        assert AgentOSCommandGateway.connect_project(str(project), viewer)["status"] == "denied"
        developer = AuthenticatedUser(user_id="developer", username="developer", role=UserRole.DEVELOPER)
        result = AgentOSCommandGateway.connect_project(str(project), developer)
        assert result["status"] == "connected"
        assert calls == [(str(project), developer)]

    def test_voice_disconnect_requires_verified_developer_principal(self, monkeypatch):
        calls = []
        monkeypatch.setattr("backend.app.api.routes.v1.disconnect_workspace_v1",
                            lambda user: calls.append(user) or {"path": "C:/default/workspace"})
        assert AgentOSCommandGateway.disconnect_project()["status"] == "denied"
        viewer = AuthenticatedUser(user_id="viewer", username="viewer", role=UserRole.VIEWER)
        assert AgentOSCommandGateway.disconnect_project(viewer)["status"] == "denied"
        developer = AuthenticatedUser(user_id="developer", username="developer", role=UserRole.DEVELOPER)
        result = AgentOSCommandGateway.disconnect_project(developer)
        assert result["status"] == "disconnected"
        assert result["path"] == "C:/default/workspace"
        assert calls == [developer]

    def test_disconnect_intent_is_classified(self):
        assert VoiceAgent()._classify_intent("Disconnect the current project").intent_type == IntentType.DISCONNECT_PROJECT

    def test_journey_create_project_with_confirmation_gate(self):
        conv = ConversationState()
        agent = VoiceAgent(conversation=conv)

        # Destructive action triggers confirmation
        res1 = agent.process("Wipe the database and purge everything")
        assert res1.requires_confirmation is True
        assert "confirm" in res1.tts_summary.lower()

        # User confirms
        res2 = agent.process("yes, proceed")
        assert res2.status in ("created", "ok")

    def test_journey_clarification_for_unnamed_project(self, tmp_path, monkeypatch):
        # Isolate workspace root for project creation
        monkeypatch.setattr("backend.app.config.settings.settings.WORKSPACE_ROOT", str(tmp_path))
        conv = ConversationState()
        agent = VoiceAgent(conversation=conv)

        # 1. Ask to create project without specifying name
        res1 = agent.process("Create a new project")
        assert res1.needs_clarification is True
        assert "name" in res1.tts_summary.lower()

        # 2. User provides name
        res2 = agent.process("FreshApp")
        # A clarification reply retains no authenticated principal when this
        # unit test invokes the agent directly, so workspace mutation fails
        # closed rather than creating/selecting a project.
        assert res2.status == "denied"
        assert res2.project_created is False

    def test_journey_run_tests_command(self):
        agent = VoiceAgent()
        res = agent.process("Run the tests")
        assert res.intent_type == IntentType.RUN_TESTS
        assert res.status in ("ok", "created")
        assert "test" in res.tts_summary.lower()

    def test_journey_review_changes_command(self):
        agent = VoiceAgent()
        res = agent.process("Review the changes")
        assert res.intent_type == IntentType.REVIEW_CHANGES
        assert res.task_id is not None
