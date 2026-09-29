import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from backend.app.services.cloud_model_pool import (
    AUTO, AutoCloudProvider, CloudModelPool, CloudPoolExhausted, provider_failure,
)
from backend.app.llm.structured import GeneratedFiles, generate_structured, ModelOutputError


def failure(status, message="unavailable", headers=None):
    response = httpx.Response(status, request=httpx.Request("POST", "http://ollama/api/generate"),
                              json={"error": message}, headers=headers)
    return httpx.HTTPStatusError("Provider error", request=response.request, response=response)


def setup_pool(outcomes, clock=lambda: 100):
    pool = CloudModelPool([{"model": name, "cloud": True, "status": "HEALTHY", "latency_seconds": i}
                           for i, name in enumerate(outcomes)], clock=clock)
    calls = []
    class Provider:
        def __init__(self, model): self.model = model
        def generate(self, prompt, **kwargs):
            calls.append((self.model, prompt, kwargs))
            result = outcomes[self.model]
            if isinstance(result, Exception): raise result
            return result
    return AutoCloudProvider(model_pool=pool, provider_factory=Provider), pool, calls


def test_primary_and_task_context_preserved():
    provider, _, calls = setup_pool({"first:cloud": "ok", "second:cloud": "unused"})
    assert provider.generate("instruction, plan, evidence", format={"type": "object"}) == "ok"
    assert calls == [("first:cloud", "instruction, plan, evidence", {"format": {"type": "object"}})]


@pytest.mark.parametrize("error", [failure(402, "quota exhausted"), failure(429), failure(404),
                                    failure(502), httpx.ReadTimeout("timeout"), httpx.ConnectError("offline")])
def test_typed_provider_failover_preserves_request(error):
    provider, pool, calls = setup_pool({"first:cloud": error, "second:cloud": "ok"})
    assert provider.generate("captured evidence") == "ok"
    assert [c[:2] for c in calls] == [("first:cloud", "captured evidence"), ("second:cloud", "captured evidence")]
    assert "first:cloud" not in pool.candidates()


def test_exhaustion_bounded_and_never_calls_local():
    provider, _, calls = setup_pool({"a:cloud": failure(402, "quota exhausted"),
                                     "b:cloud": failure(429), "c:cloud": failure(503)})
    with pytest.raises(CloudPoolExhausted): provider.generate("task")
    assert [c[0] for c in calls] == ["a:cloud", "b:cloud", "c:cloud"]
    with pytest.raises(CloudPoolExhausted): provider.generate("task")
    assert len(calls) == 3


def test_rate_cooldown_recovers_only_on_next_real_request():
    now = [100]
    provider, pool, calls = setup_pool({"a:cloud": failure(429, headers={"Retry-After": "12"})}, clock=lambda: now[0])
    with pytest.raises(CloudPoolExhausted): provider.generate("task")
    now[0] = 111
    assert pool.candidates() == [] and len(calls) == 1
    now[0] = 112
    assert pool.candidates() == ["a:cloud"] and len(calls) == 1


def test_access_denial_is_not_quota_and_does_not_auto_retry():
    assert provider_failure(failure(402, "not included in your free usage")) == ("UNAVAILABLE", None)
    assert provider_failure(failure(429, "reached your weekly usage limit")) == ("QUOTA_EXHAUSTED", None)
    assert provider_failure(failure(400, "bad schema")) is None


def test_invalid_output_uses_existing_bounded_retry_without_model_hopping(monkeypatch):
    from backend.app.config.settings import settings
    monkeypatch.setattr(settings, "LLM_STRUCTURED_ATTEMPTS", 2)
    provider, pool, calls = setup_pool({"a:cloud": "{}", "b:cloud": "unused"})
    with pytest.raises(ModelOutputError): generate_structured(provider, "code", GeneratedFiles)
    assert [c[0] for c in calls] == ["a:cloud", "a:cloud"]
    assert pool.candidates() == ["a:cloud", "b:cloud"]


def test_unverified_degraded_and_local_models_never_enter_cloud_pool():
    pool = CloudModelPool([
        {"model": "local", "status": "HEALTHY", "cloud": False},
        {"model": "bad:cloud", "status": "DEGRADED", "cloud": True},
    ])
    assert pool.candidates() == []


def test_task_instances_do_not_share_attempt_or_prompt_state():
    a, _, a_calls = setup_pool({"a:cloud": "A"})
    b, _, b_calls = setup_pool({"b:cloud": "B"})
    with ThreadPoolExecutor(2) as executor:
        assert list(executor.map(lambda pair: pair[0].generate(pair[1]), [(a, "task A"), (b, "task B")])) == ["A", "B"]
    assert a_calls[0][1] == "task A" and b_calls[0][1] == "task B"


def test_per_user_override_is_scoped_and_auto_restored(monkeypatch):
    from backend.app.services import local_model_settings as model_settings
    monkeypatch.setattr(model_settings, "local_models", lambda user=None: {
        "status": "online", "models": [{"name": "coder:3b", "selectable": True}]})
    from backend.app.config.settings import settings
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    before = settings.OLLAMA_MODEL
    model_settings.select_model("coder:3b", "router-user-A")
    assert model_settings.model_preference("router-user-A") == "coder:3b"
    assert model_settings.model_preference("router-user-B") == AUTO
    assert settings.OLLAMA_MODEL == before
    model_settings.select_model(AUTO, "router-user-A")
    assert model_settings.model_preference("router-user-A") == AUTO


@pytest.mark.parametrize('exhaust_all', [False, True, 'review'])
def test_real_engineering_graph_provider_failover_and_local_checkpoint(tmp_path, monkeypatch, exhaust_all):
    from langgraph.checkpoint.memory import MemorySaver
    from backend.app.config.settings import settings
    from backend.app.llm.ollama import OllamaProvider
    from backend.app.llm.mock import MockLLMProvider
    from backend.app.services import cloud_model_pool
    from backend.app.services.multi_agent_service import MultiAgentService
    from backend.app.services.task_service import TaskService
    from backend.app.models.task import TaskStatus
    from backend.app.services.event_service import EventService
    from backend.app.workflows.multi_agent_workflow import build_multi_agent_graph
    from backend.app.voice.agent.command_router import AgentOSCommandGateway
    monkeypatch.setattr(settings, 'WORKSPACE_ROOT', str(tmp_path))
    monkeypatch.setattr(settings, 'LLM_PROVIDER', 'ollama')
    monkeypatch.setattr(settings, 'OLLAMA_MODEL', AUTO)
    test_pool = CloudModelPool([{'model': m, 'cloud': True, 'status': 'HEALTHY', 'latency_seconds': n}
                                for n,m in enumerate(['primary:cloud','fallback:cloud'])])
    monkeypatch.setattr(cloud_model_pool, 'pool', test_pool)
    graph = build_multi_agent_graph().compile(checkpointer=MemorySaver())
    monkeypatch.setattr('backend.app.services.multi_agent_service.get_multi_agent_graph', lambda: graph)
    (tmp_path/'value.py').write_text('VALUE = 1\n')
    (tmp_path/'test_value.py').write_text('from value import VALUE\ndef test_value():\n    assert VALUE == 22\n')
    calls=[]
    def generate(self,prompt,**kwargs):
        calls.append((self.model,prompt))
        if self.model=='primary:cloud' or (exhaust_all is True and self.model.endswith(':cloud')) or (exhaust_all == 'review' and 'REVIEWER_PROMPT' in prompt and self.model.endswith(':cloud')):
            raise failure(429)
        if 'MULTI_AGENT_DECOMPOSE_PROMPT' in prompt:
            return json.dumps({'subtasks':[
                {'subtask_id':'code','description':'Change VALUE to 22','assigned_agent':'coding','target_files':['value.py']},
                {'subtask_id':'test','description':'Run tests','assigned_agent':'testing','dependencies':['code']},
                {'subtask_id':'review','description':'Review result','assigned_agent':'reviewer','dependencies':['test']}]})
        if prompt.startswith('CODING_CHANGES_PROMPT:'):
            return json.dumps({'files':[{'path':'value.py','content':'VALUE = 22\n'}]})
        return MockLLMProvider().generate(prompt,**kwargs)
    monkeypatch.setattr(OllamaProvider,'generate',generate)
    task=MultiAgentService.start_task('Implement VALUE = 22 and verify the implementation',sync=True)
    if exhaust_all is True:
        assert task.status==TaskStatus.PAUSED, task.model_dump()
        assert len(calls)==2
        task=MultiAgentService.resume_capacity(task.task_id,'coder:3b')
        assert all(m=='coder:3b' for m,_ in calls[2:])
    assert task.status==TaskStatus.WAITING_APPROVAL, task.model_dump()
    assert (tmp_path/'value.py').read_text()=='VALUE = 1\n'
    AgentOSCommandGateway.resolve_approval(task.approval_id,True)
    result=TaskService.get_task(task.task_id)
    if exhaust_all == 'review':
        assert result.status == TaskStatus.PAUSED, result.model_dump()
        assert (tmp_path/'value.py').read_text() == 'VALUE = 22\n'
        before_events=EventService.get_task_events(task.task_id)
        assert any(e['event_type']=='TEST_COMPLETED' for e in before_events)
        resume_index=len(calls)
        test_pool.health.clear()  # Cloud recovered: explicit local must still win before replay.
        result=MultiAgentService.resume_capacity(task.task_id,'coder:3b')
        assert all(m=='coder:3b' for m,_ in calls[resume_index:])
    assert result.status==TaskStatus.COMPLETED, result.model_dump()
    events=EventService.get_task_events(task.task_id)
    assert sum(e['event_type']=='PATCH_APPLIED' for e in events)==1
    reports=[e['payload']['report'] for e in events if e['event_type']=='TEST_COMPLETED']
    assert reports and reports[-1]['passed_count']==1
    if exhaust_all is True: assert all(m=='coder:3b' for m,_ in calls[2:])
    else:
        assert calls[0][0]=='primary:cloud' and calls[1][0]=='fallback:cloud'
        assert calls[0][1]==calls[1][1]

def test_auto_health_uses_verified_capacity_not_a_fake_installed_tag(monkeypatch):
    from backend.app.services.model_router import ModelRouter
    from backend.app.config.settings import settings
    from backend.app.services import cloud_model_pool
    monkeypatch.setattr(settings,'LLM_PROVIDER','ollama')
    monkeypatch.setattr(settings,'OLLAMA_MODEL',AUTO)
    monkeypatch.setattr(ModelRouter,'_is_test_mode',False)
    monkeypatch.setattr(cloud_model_pool,'pool',CloudModelPool([{'model':'a:cloud','cloud':True,'status':'HEALTHY','latency_seconds':1}]))
    monkeypatch.setattr(httpx,'get',lambda *a,**k:httpx.Response(200,request=httpx.Request('GET','http://ollama/api/tags'),json={'models':[{'name':'a:cloud'}]}))
    assert ModelRouter.check_health().status.value=='READY'
    cloud_model_pool.pool.failed('a:cloud',('QUOTA_EXHAUSTED',None))
    result=ModelRouter.check_health()
    assert result.status.value=='UNAVAILABLE' and 'CLOUD_POOL_EXHAUSTED' in result.error


def test_verification_expiration_and_endpoint_binding(tmp_path,monkeypatch):
    from backend.app.config.settings import settings
    from backend.app.services import cloud_model_pool
    path=tmp_path/'verified.json'
    monkeypatch.setattr(settings,'MODEL_VERIFICATION_FILE',str(path))
    monkeypatch.setattr(cloud_model_pool.time,'time',lambda:1000000)
    row={'endpoint':settings.OLLAMA_BASE_URL.rstrip('/'),'checked_at':1000000,'models':[{'model':'verified'}]}
    path.write_text(json.dumps(row));assert cloud_model_pool.verification()==row['models']
    row['checked_at']=0;path.write_text(json.dumps(row));assert cloud_model_pool.verification()==[]
    row['checked_at']=1000000;row['endpoint']='http://different-provider';path.write_text(json.dumps(row));assert cloud_model_pool.verification()==[]
