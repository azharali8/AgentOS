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
from backend.app.llm.evidence import failure_excerpt


def test_failure_context_preserves_assertion_ahead_of_long_warning_tail():
    failure = '_____ test_redirect _____\n> assert info["target_url"] == target\nE AssertionError: URLs differ\ntest_app.py:42\n'
    output = failure + '================ warnings summary ================\n' + 'DeprecationWarning\n' * 1000
    excerpt = failure_excerpt(output)
    assert 'assert info["target_url"] == target' in excerpt
    assert 'test_app.py:42' in excerpt and 'DeprecationWarning' not in excerpt


def test_failure_context_remains_bounded_without_warning_section():
    excerpt = failure_excerpt('first failure\n' + 'x' * 10000 + '\nlast failure')
    assert len(excerpt) == 4000
    assert excerpt.startswith('first failure') and excerpt.endswith('last failure')


def test_malformed_and_wrong_shape_output_regenerates_without_partial_execution(monkeypatch):
    monkeypatch.setattr(settings, "LLM_STRUCTURED_ATTEMPTS", 3)
    provider = MockLLMProvider(response_queue=['{"files": [{"path": "app.py", "content": 42}]}',
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


def test_missing_model_fails_real_task_before_execution(monkeypatch, tmp_path):
    from backend.app.services.multi_agent_service import MultiAgentService
    from backend.app.models.task import TaskStatus
    monkeypatch.setattr(settings, 'LLM_PROVIDER', 'ollama')
    monkeypatch.setattr(settings, 'OLLAMA_MODEL', 'missing-model')
    monkeypatch.setattr(settings, 'WORKSPACE_ROOT', str(tmp_path))
    monkeypatch.setattr(httpx, 'get', lambda url, **kw: httpx.Response(200,
        request=httpx.Request('GET', url), json={'models': []}))
    result = MultiAgentService.start_task('Implement a service with tests', sync=True)
    assert result.status == TaskStatus.FAILED
    assert 'not installed' in result.error
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('metadata', [{'models': [{'name': 'tiny:latest'}]}, {'models': []}, {'unexpected': []}])
def test_model_preflight_validates_inventory(monkeypatch, metadata):
    monkeypatch.setattr(settings, 'OLLAMA_MODEL', 'tiny')
    monkeypatch.setattr(httpx, 'get', lambda url, **kw: httpx.Response(200,
        request=httpx.Request('GET', url), json=metadata))
    if metadata.get('models'):
        OllamaProvider().check_available()
    else:
        with pytest.raises(RuntimeError):
            OllamaProvider().check_available()


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
                "assert False\n" if len(prompts) == 1 else "assert True\nassert 1 == 1\n"}]})
    patch = CodingAgent(Model()).formulate_patch(SubTask(task_id="context", subtask_id="code",
        description="Update tests", assigned_agent=AgentType.CODING, target_files=["app.py"]))
    assert len(prompts) == 2
    assert 'assert True' not in prompts[0] and 'assert True' in prompts[1]
    assert (tmp_path / "test_app.py").read_text() == "assert True\n"
    assert any("assert 1 == 1" in line for h in patch.files[0].hunks for line in h.lines)
    assert not any("assert False" in line for h in patch.files[0].hunks for line in h.lines)


def test_generated_absolute_path_is_repaired_once(monkeypatch):
    monkeypatch.setattr(settings, "LLM_STRUCTURED_ATTEMPTS", 2)
    calls = []
    class Provider:
        def generate(self, prompt, **kwargs):
            calls.append(prompt)
            return json.dumps({"files": [{"path": "/main.py" if len(calls) == 1 else "main.py", "content": "x = 1"}]})
    assert generate_structured(Provider(), "Generate", GeneratedFiles).files[0].path == "main.py"
    assert len(calls) == 2 and "workspace-relative" in calls[1]


@pytest.mark.parametrize("path", ["/main.py", "C:\\main.py", "../main.py", "//host/share/a.py"])
def test_generated_paths_never_escape_after_retry(monkeypatch, path):
    monkeypatch.setattr(settings, "LLM_STRUCTURED_ATTEMPTS", 3)
    calls = []
    class Provider:
        def generate(self, prompt, **kwargs):
            calls.append(prompt)
            return json.dumps({"files": [{"path": path, "content": "x = 1"}]})
    with pytest.raises(ValueError, match="bounded retries"):
        generate_structured(Provider(), "Generate", GeneratedFiles)
    assert len(calls) == 2


def test_task_model_snapshot_reaches_supervisor_and_worker(monkeypatch):
    from backend.app.workflows.multi_agent_nodes import _supervisor
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "new-selection")
    supervisor = _supervisor({"selected_model": "selected-at-task-start"})
    assert supervisor.llm.model == "selected-at-task-start"
    assert supervisor.decomposer.llm is supervisor.llm
    assert supervisor.coding_agent.llm is supervisor.llm
    assert settings.OLLAMA_MODEL == "new-selection"


def test_cloud_payment_failure_is_actionable_without_leaking_body(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: httpx.Response(402,
        request=httpx.Request("POST", "http://localhost"), json={"error": "secret-private-body"}))
    with pytest.raises(RuntimeError, match="HTTP 402.*account") as exc:
        OllamaProvider().generate("hello")
    assert "secret-private-body" not in str(exc.value)
