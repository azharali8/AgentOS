"""Real graph, filesystem, approval, API and test runner; model/STT are explicit doubles."""
import json
import uuid

import httpx
import pytest
from langgraph.checkpoint.memory import MemorySaver

from backend.app.agents.specialized import CodingAgent
from backend.app.config.settings import settings
from backend.app.llm.mock import MockLLMProvider
from backend.app.models.multi_agent import SubTask, AgentType
from backend.app.models.task import TaskStatus
from backend.app.services.event_service import EventService
from backend.app.services.multi_agent_service import MultiAgentService
from backend.app.services.task_decomposer import TaskDecomposer
from backend.app.voice.agent.agent import VoiceAgent
from backend.app.voice.agent.command_router import AgentOSCommandGateway
from backend.app.voice.providers.assemblyai import AssemblyAIProvider
from backend.app.voice.service import VoiceService
from backend.app.workflows.multi_agent_workflow import build_multi_agent_graph


@pytest.fixture
def engineering_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    graph = build_multi_agent_graph().compile(checkpointer=MemorySaver())
    monkeypatch.setattr("backend.app.services.multi_agent_service.get_multi_agent_graph", lambda: graph)
    (tmp_path / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "test_value.py").write_text("from value import VALUE\ndef test_value():\n    assert VALUE == 22\n", encoding="utf-8")
    original_generate = MockLLMProvider.generate

    def generate(self, prompt, **kwargs):
        if prompt.startswith("CODING_CHANGES_PROMPT:"):
            return json.dumps({"files": [{"path": "value.py", "content": "VALUE = 22\n"}]})
        return original_generate(self, prompt, **kwargs)

    monkeypatch.setattr(MockLLMProvider, "generate", generate)
    def plan(self, instruction, task_id="task-1"):
        return [
            SubTask(task_id=task_id, subtask_id="code", description=instruction, assigned_agent=AgentType.CODING, target_files=["value.py"]),
            SubTask(task_id=task_id, subtask_id="test", description="Run tests", assigned_agent=AgentType.TESTING, dependencies=["code"]),
            SubTask(task_id=task_id, subtask_id="review", description="Review result", assigned_agent=AgentType.REVIEWER, dependencies=["test"]),
        ]
    monkeypatch.setattr(TaskDecomposer, "decompose", plan)
    return tmp_path


def test_real_graph_tests_applied_code_and_reviews_after_approval(engineering_runtime):
    task = MultiAgentService.start_task("Change VALUE to 22 and verify", sync=True)
    assert task.status == TaskStatus.WAITING_APPROVAL
    assert (engineering_runtime / "value.py").read_text() == "VALUE = 1\n"
    assert not any(e["event_type"] == "TEST_COMPLETED" for e in EventService.get_task_events(task.task_id))
    approved = AgentOSCommandGateway.resolve_approval(task.approval_id, True)
    assert approved["status"] == "ok"
    state = MultiAgentService.get_state(task.task_id)
    assert state["status"] == "COMPLETED"
    report = state["subtask_results"]["test"]["evidence"]["structured_report"]
    assert report["passed_count"] == 1
    assert report["exit_code"] == 0
    events = [e["event_type"] for e in EventService.get_task_events(task.task_id)]
    assert events.index("PATCH_APPLIED") < events.index("TEST_COMPLETED") < events.index("TASK_COMPLETED")


@pytest.mark.parametrize("tamper", [False, True])
def test_rejected_or_stale_patch_cannot_complete(engineering_runtime, tamper):
    task = MultiAgentService.start_task("Change VALUE to 22", sync=True)
    if tamper:
        (engineering_runtime / "value.py").write_text("VALUE = 999\n", encoding="utf-8")
    AgentOSCommandGateway.resolve_approval(task.approval_id, tamper)
    from backend.app.services.task_service import TaskService
    assert TaskService.get_task(task.task_id).status == (TaskStatus.FAILED if tamper else TaskStatus.CANCELLED)
    assert not any(e["event_type"] == "TEST_COMPLETED" for e in EventService.get_task_events(task.task_id))


def test_model_generated_new_files_use_real_validator_and_applier(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(tmp_path))
    model = MockLLMProvider(response_queue=[json.dumps({"files": [{"path": "api.py", "content": "answer = 42\n"}]})])
    agent = CodingAgent(model)
    patch = agent.formulate_patch(SubTask(task_id="new", subtask_id="code", description="Create api.py", assigned_agent=AgentType.CODING))
    assert patch.files[0].is_new_file
    assert not (tmp_path / "api.py").exists()
    assert agent.validator.validate(patch).valid
    assert agent.apply_patch(patch)["applied"]
    assert (tmp_path / "api.py").read_text() == "answer = 42\n"


def test_uncertain_confirmation_does_not_consume_pending_intent():
    session = uuid.uuid4().hex
    first = VoiceService.process_transcript("Delete the project", session_id=session, auto_start=False)
    assert first.status == "awaiting_confirmation"
    second = VoiceService.process_transcript("confirm", session_id=session, confidence=0.2, auto_start=False)
    assert second.status == "needs_clarification" and second.task_id is None
    assert VoiceService.get_conversation_state(session).has_pending_question()
    assert VoiceService.process_transcript("cancel", session_id=session, auto_start=False).status == "cancelled"


def test_project_failure_does_not_create_task_in_current_workspace(monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("Project name already exists")
    monkeypatch.setattr(AgentOSCommandGateway, "create_project", fail)
    result = VoiceService.process_transcript("Create a FastAPI URL shortener", session_id=uuid.uuid4().hex)
    assert result.status == "failed" and result.task_id is None


def test_punctuated_wake_word_keeps_name_clarification():
    assert VoiceAgent._extract_project_name("AgentOS, create a project.") is None


def test_test_only_followup_delegates_no_coding():
    subtasks = TaskDecomposer(MockLLMProvider()).decompose("Run the full test suite and report the results.")
    assert [s.assigned_agent for s in subtasks] == [AgentType.TESTING]


def test_failed_test_replans_and_requires_new_patch_approval(engineering_runtime, monkeypatch):
    original_generate = MockLLMProvider.generate
    proposals = []
    def generate(self, prompt, **kwargs):
        if prompt.startswith("CODING_CHANGES_PROMPT:"):
            proposals.append(1)
            return json.dumps({"files": [{"path": "value.py", "content": "VALUE = 2\n" if len(proposals) == 1 else "VALUE = 22\n"}]})
        return original_generate(self, prompt, **kwargs)
    monkeypatch.setattr(MockLLMProvider, "generate", generate)
    task = MultiAgentService.start_task("Implement VALUE = 22 and test", sync=True)
    first_approval = task.approval_id
    AgentOSCommandGateway.resolve_approval(first_approval, True)
    from backend.app.services.task_service import TaskService
    paused = TaskService.get_task(task.task_id)
    assert paused.status == TaskStatus.WAITING_APPROVAL
    assert paused.approval_id != first_approval
    assert (engineering_runtime / "value.py").read_text() == "VALUE = 2\n"
    AgentOSCommandGateway.resolve_approval(paused.approval_id, True)
    assert TaskService.get_task(task.task_id).status == TaskStatus.COMPLETED
    events = EventService.get_task_events(task.task_id)
    reports = [e["payload"]["report"] for e in events if e["event_type"] == "TEST_COMPLETED"]
    assert [r["passed"] for r in reports] == [False, True]
    assert any(e["event_type"] == "REPLAN_TRIGGERED" for e in events)


@pytest.mark.asyncio
async def test_provider_ignores_processing_text_until_completed(monkeypatch):
    polls = []
    def handle(request):
        if request.url.path == "/v2/upload":
            return httpx.Response(200, json={"upload_url": "https://example.invalid/audio"})
        if request.method == "POST":
            return httpx.Response(200, json={"id": "job"})
        polls.append(1)
        return httpx.Response(200, json={"status": "processing" if len(polls) == 1 else "completed",
                                         "text": "partial" if len(polls) == 1 else "Run tests", "confidence": 0.99})
    real_client = httpx.AsyncClient
    monkeypatch.setattr("backend.app.voice.providers.assemblyai.httpx.AsyncClient",
                        lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw))
    result = await AssemblyAIProvider("test-key", timeout_seconds=10).transcribe(b"audio" * 100)
    assert result.transcript == "Run tests" and len(polls) == 2
