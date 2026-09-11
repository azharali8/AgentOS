"""Real API/database/gateway integration; explicit graph/STT doubles, never a live mic demo."""
import os
import subprocess
import sys
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.config.settings import PROJECT_ROOT, settings
from backend.app.main import app
from backend.app.models.task import TaskRequest, TaskStatus
from backend.app.services.task_service import TaskService
from backend.app.services.event_service import EventService
from backend.app.services.multi_agent_service import MultiAgentService
from backend.app.voice.service import VoiceService
from backend.app.voice.providers.mock import MockSpeechToTextProvider
from backend.app.voice.agent.agent import VoiceAgent
from backend.app.voice.agent.confirmation import ConfirmationGate
from backend.app.voice.agent.command_router import AgentOSCommandGateway


@pytest.fixture
def graph(monkeypatch):
    class Graph:
        calls = []
        status = "COMPLETED"
        def invoke(self, state, config):
            self.calls.append((state, config))
            EventService.record_event(state["task_id"], "SUBTASK_STARTED", payload={"agent": "RESEARCH"})
            return {**state, "status": self.status, "final_response": "Controlled graph result"}
        def get_state(self, config):
            return SimpleNamespace(next=("human_approval",) if self.status == "WAITING_APPROVAL" else ())
    instance = Graph()
    monkeypatch.setattr("backend.app.services.multi_agent_service.get_multi_agent_graph", lambda: instance)
    return instance


@pytest.mark.asyncio
async def test_final_audio_executes_exactly_one_original_task(graph):
    provider = MockSpeechToTextProvider(canned_transcript="Inspect the repository structure")
    VoiceService.set_stt_provider(provider)
    before = {t.task_id for t in TaskService.list_tasks(1000)}
    response = await VoiceService.execute_voice_command(b"a" * 200, session_id=uuid.uuid4().hex, sync=True)
    after = {t.task_id for t in TaskService.list_tasks(1000)}
    assert after - before == {response.task_id}
    assert provider.transcribe_call_count == 1
    assert graph.calls[0][0]["task_id"] == response.task_id
    assert graph.calls[0][1]["configurable"]["thread_id"] == response.task_id
    assert TaskService.get_task(response.task_id).status == TaskStatus.COMPLETED
    assert response.tts_summary == "Controlled graph result"


def test_text_uses_same_task_identity(graph):
    with TestClient(app) as client:
        response = client.post("/api/v1/tasks", json={"task": "Inspect repository", "sync": True})
    assert response.status_code == 201
    task_id = response.json()["task_id"]
    assert graph.calls[0][0]["task_id"] == task_id
    assert response.json()["status"] == "COMPLETED"


@pytest.mark.parametrize("status", ["FAILED", "WAITING_APPROVAL", "CANCELLED"])
def test_non_success_never_marked_completed(graph, status):
    graph.status = status
    task = MultiAgentService.start_task("Inspect repository", sync=True)
    assert task.status.value == status


def test_project_clarification_keeps_instruction(graph, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(VoiceAgent, "_resolve_project_parent", staticmethod(lambda: tmp_path))
    session = uuid.uuid4().hex
    first = VoiceService.process_transcript("Create a new project", session_id=session, sync=True)
    assert first.status == "needs_clarification"
    assert not graph.calls
    reply = VoiceService.process_transcript("URL Shortener", session_id=session, sync=True)
    assert reply.project_created
    assert (tmp_path / "URL-Shortener" / "README.md").exists()
    assert graph.calls[0][0]["user_instruction"] == "Create a new project"
    assert graph.calls[0][0]["task_id"] == reply.task_id


def test_sensitive_command_requires_unambiguous_confirmation(graph):
    session = uuid.uuid4().hex
    first = VoiceService.process_transcript("Delete the project", session_id=session, sync=True)
    assert first.status == "awaiting_confirmation"
    for ambiguous in ["maybe", "yes but do not delete it", "confirm later"]:
        reply = VoiceService.process_transcript(ambiguous, session_id=session, sync=True)
        assert reply.status == "awaiting_confirmation"
        assert not graph.calls
    confirmed = VoiceService.process_transcript("Confirm.", session_id=session, sync=True)
    assert graph.calls[0][0]["user_instruction"] == "Delete the project"
    assert confirmed.task_id == graph.calls[0][0]["task_id"]


def test_voice_approval_enforces_role(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    result = AgentOSCommandGateway.resolve_approval("irrelevant", True, user_id="viewer", user_role="VIEWER")
    assert result["status"] == "denied"


def test_conversation_users_do_not_share_pending_intent():
    session = uuid.uuid4().hex
    one = VoiceService.get_conversation_state(session, "one")
    one.set_pending_question("Confirm?", {"kind": "confirmation"})
    assert not VoiceService.get_conversation_state(session, "two").has_pending_question()


def test_websocket_delivers_events_after_connect():
    task = TaskService.create_task(TaskRequest(instruction="Observe live events"))
    with TestClient(app) as client:
        with client.websocket_connect(f"/api/v1/events/stream/{task.task_id}") as ws:
            assert ws.receive_json()["event_type"] == "STREAM_CONNECTED"
            EventService.record_event(task.task_id, "SUBTASK_STARTED", payload={"agent": "TESTING"})
            assert ws.receive_json()["event_type"] == "SUBTASK_STARTED"
            ws.send_text("ping")
            assert ws.receive_text() == "pong"


def test_fresh_database_import_is_safe_and_bootstrap_idempotent(tmp_path):
    database = tmp_path / "nested" / "test.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database.as_posix()}", "PYTHONPATH": str(PROJECT_ROOT)}
    script = """
from pathlib import Path
from backend.app.db import models
from backend.app.db.database import engine, init_db, Base
assert not Path(engine.url.database).exists()
assert models.TaskModel.metadata is Base.metadata
init_db()
init_db()
with engine.connect() as connection:
    assert connection.exec_driver_sql('SELECT count(*) FROM tasks').scalar() == 0
"""
    result = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert database.exists()
