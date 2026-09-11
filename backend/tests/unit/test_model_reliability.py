import json

import httpx
import pytest

from backend.app.agents.reviewer import ReviewerAgent
from backend.app.config.settings import settings
from backend.app.llm.mock import MockLLMProvider
from backend.app.llm.ollama import OllamaProvider
from backend.app.llm.structured import GeneratedFiles, generate_structured
from backend.app.models.agent import Observation, PlanStep
from backend.app.services.model_router import ModelRouter, ModelStatus
from backend.app.services.task_decomposer import TaskDecomposer
from backend.app.voice.agent.agent import VoiceAgent
from backend.app.voice.agent.conversation import ConversationState


def test_malformed_and_wrong_shape_output_regenerates_without_partial_execution(monkeypatch):
    monkeypatch.setattr(settings, "LLM_STRUCTURED_ATTEMPTS", 3)
    provider = MockLLMProvider(response_queue=['{"files":', '{"files": [{"path": "app.py", "content": 42}]}',
        json.dumps({"files": [{"path": "app.py", "content": "answer = 42\n"}]})])
    result = generate_structured(provider, "Generate files", GeneratedFiles)
    assert result.files[0].content == "answer = 42\n"


def test_invalid_output_exhausts_bounded_retries(monkeypatch):
    monkeypatch.setattr(settings, "LLM_STRUCTURED_ATTEMPTS", 2)
    provider = MockLLMProvider(response_queue=['{}', '{}'])
    with pytest.raises(ValueError, match="after bounded retries"):
        generate_structured(provider, "Generate files", GeneratedFiles)


@pytest.mark.parametrize("kind, message", [(404, "not installed|unavailable"), (503, "HTTP 503"),
                                          ("timeout", "timed out"), ("length", "token limit")])
def test_provider_errors_are_explicit_and_not_retried_as_json(monkeypatch, kind, message):
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs)
        if kind == "timeout":
            raise httpx.ReadTimeout("slow")
        return httpx.Response(kind if isinstance(kind, int) else 200,
                              request=httpx.Request("POST", "http://localhost"),
                              json={"response": "truncated", "done_reason": "length"})
    monkeypatch.setattr(httpx, "post", post)
    with pytest.raises(RuntimeError, match=message):
        generate_structured(OllamaProvider(), "Generate files", GeneratedFiles)
    assert len(calls) == 1


def test_missing_model_health_is_unavailable_even_when_server_is_up(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "missing-model")
    monkeypatch.setattr(ModelRouter, "_is_test_mode", False)
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: httpx.Response(200,
        request=httpx.Request("GET", "http://localhost"), json={"models": [{"name": "qwen2.5-coder:3b"}]}))
    health = ModelRouter.check_health()
    assert health.status == ModelStatus.UNAVAILABLE
    assert "not installed" in health.error


def test_network_failure_cannot_become_heuristic_plan_or_successful_review():
    class Offline(MockLLMProvider):
        def generate(self, *a, **kw):
            raise RuntimeError("Ollama offline")
    with pytest.raises(RuntimeError, match="offline"):
        TaskDecomposer(Offline()).decompose("Create a service with tests")
    step = PlanStep(step_id="review", tool_name="review", operation="eval", description="Review")
    observation = Observation(step_id="review", tool_name="review", operation="eval", success=True, data={})
    verdict, reason = ReviewerAgent(Offline(), strict=True).review(step, observation)
    assert verdict != "SUCCESS" and "offline" in reason


def test_real_transcription_word_spacing_preserves_project_creation():
    agent = VoiceAgent(conversation=ConversationState(session_id="spoken-names"))
    intent = agent._classify_intent("Agent OS, create a fast API URL shortener with authentication and tests.")
    assert intent.intent_type.value == "create_project"
    assert intent.project_name == "UrlShortenerApp"


def test_cloud_uses_client_validation_without_unsupported_format(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "gpt-oss:120b-cloud")
    calls = []
    responses = iter(['{}', '{"files": [{"path": "app.py", "content": "x = 1"}]}'])
    def post(url, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(200, request=httpx.Request("POST", url), json={"response": next(responses)})
    monkeypatch.setattr(httpx, "post", post)
    assert generate_structured(OllamaProvider(), "Generate", GeneratedFiles).files[0].path == "app.py"
    assert len(calls) == 2 and all("format" not in call for call in calls)


def test_project_subprocess_does_not_inherit_control_database_or_speech_key(tmp_path, monkeypatch):
    from backend.app.tools.test_runner import TestRunnerTool
    monkeypatch.setenv("DATABASE_URL", "sqlite:///control-plane-must-not-be-used.db")
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "sentinel-not-a-real-key")
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(tmp_path))
    (tmp_path / "test_environment.py").write_text(
        "import os\ndef test_isolation():\n"
        "    assert 'DATABASE_URL' not in os.environ\n"
        "    assert 'ASSEMBLYAI_API_KEY' not in os.environ\n", encoding="utf-8")
    result = TestRunnerTool()._run_pytest({"path": "test_environment.py"})
    assert result.exit_code == 0, result.stdout + result.stderr
    assert result.passed == 1


def test_unread_existing_target_is_read_and_regenerated_before_patch(tmp_path, monkeypatch):
    from backend.app.agents.specialized import CodingAgent
    from backend.app.models.multi_agent import SubTask, AgentType
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(tmp_path))
    (tmp_path / "app.py").write_text("VALUE = 1\n")
    (tmp_path / "test_app.py").write_text("assert True\n")
    prompts = []
    class Model(MockLLMProvider):
        def generate(self, prompt, **kwargs):
            prompts.append(prompt)
            return json.dumps({"files": [{"path": "test_app.py", "content":
                "assert False\n" if len(prompts) == 1 else "assert 1 == 1\n"}]})
    patch = CodingAgent(Model()).formulate_patch(SubTask(task_id="context", subtask_id="code",
        description="Update tests", assigned_agent=AgentType.CODING, target_files=["app.py"]))
    assert len(prompts) == 2
    assert 'assert True' not in prompts[0] and 'assert True' in prompts[1]
    assert (tmp_path / "test_app.py").read_text() == "assert True\n"
    assert any("assert 1 == 1" in line for h in patch.files[0].hunks for line in h.lines)
    assert not any("assert False" in line for h in patch.files[0].hunks for line in h.lines)
