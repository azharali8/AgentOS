import pytest
import httpx
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.config.settings import settings
from backend.app.auth.service import AuthService
from backend.app.services import local_model_settings as models
from backend.app.services.task_context import instruction_with_context
from backend.app.db.database import get_db_session
from backend.app.db.models import WorkspacePreferenceModel

@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setattr(settings,'AUTH_ENABLED',True)
    monkeypatch.setattr(settings,'LLM_PROVIDER','ollama')
    monkeypatch.setattr(settings,'OLLAMA_MODEL','old:3b')
    AuthService.reset()
    with get_db_session() as db: db.query(WorkspacePreferenceModel).delete()
    yield
    with get_db_session() as db: db.query(WorkspacePreferenceModel).delete()
    AuthService.reset()

@pytest.fixture
def catalog(monkeypatch):
    def get(url,**kwargs):
        return httpx.Response(200,request=httpx.Request('GET',url),json={'models':[{'name':'coder:3b','size':2000000000},{'name':'embed:latest','size':200000000},{'name':'huge:cloud','remote_host':'https://ollama.com'}]})
    def post(url,json,**kwargs):
        return httpx.Response(200,request=httpx.Request('POST',url),json={'capabilities':['embedding'] if json['model'].startswith('embed') else ['completion']})
    monkeypatch.setattr(models.httpx,'get',get);monkeypatch.setattr(models.httpx,'post',post)

client=TestClient(app)
headers={'X-API-Key':'test-user-key'}

def test_installed_models_only_and_selection_persists(catalog):
    response=client.get('/api/v1/system/local-models',headers=headers)
    assert response.status_code==200
    entries=response.json()['models']
    assert [m['name'] for m in entries]==['coder:3b','embed:latest','huge:cloud']
    assert entries[0]['selectable'] and not entries[1]['selectable']
    assert client.put('/api/v1/system/local-models',headers=headers,json={'model':'coder:3b'}).status_code==200
    from backend.app.llm.factory import get_llm_provider
    from backend.app.services.model_router import ModelRouter
    assert get_llm_provider().model=='coder:3b'
    assert ModelRouter.get_provider().model=='coder:3b'
    settings.OLLAMA_MODEL='old:3b'
    models.restore_model_preference()
    assert settings.OLLAMA_MODEL=='coder:3b'

@pytest.mark.parametrize('name',['missing:3b','embed:latest'])
def test_unavailable_model_cannot_be_selected(catalog,name):
    assert client.put('/api/v1/system/local-models',headers=headers,json={'model':name}).status_code==400
    assert settings.OLLAMA_MODEL=='old:3b'

def test_offline_and_rbac(monkeypatch):
    monkeypatch.setattr(models.httpx,'get',lambda *a,**k: (_ for _ in ()).throw(httpx.ConnectError('offline')))
    assert models.local_models()['status']=='offline'
    assert client.put('/api/v1/system/local-models',headers=headers,json={'model':'coder:3b'}).status_code==503
    assert client.put('/api/v1/system/local-models',headers={'X-API-Key':'test-viewer-key'},json={'model':'coder:3b'}).status_code==403
    assert client.get('/api/v1/system/local-models').status_code==401
    assert settings.OLLAMA_MODEL=='old:3b'

def test_non_ollama_routing_is_preserved(monkeypatch,catalog):
    monkeypatch.setattr(settings,'LLM_PROVIDER','openai')
    assert client.put('/api/v1/system/local-models',headers=headers,json={'model':'coder:3b'}).status_code==409
    models.restore_model_preference()
    assert settings.LLM_PROVIDER=='openai'

@pytest.mark.parametrize('name,content',[('../outside.py','x'),('C:\\secret.py','x'),('.env','secret'),('secret.exe','x'),('requirements.pdf','x'),('ok.py','x'*32769),('ok.py','\x00')], ids=['traversal','drive','sensitive','executable','pdf','oversized','binary'])
def test_unsafe_context_is_rejected(name,content):
    from fastapi import HTTPException
    with pytest.raises(HTTPException): instruction_with_context('Review code',[{'name':name,'content':content}])

def test_context_reaches_existing_supervisor(monkeypatch):
    from backend.app.services.multi_agent_service import MultiAgentService
    captured=[]
    monkeypatch.setattr(MultiAgentService,'start_task',lambda **kw:captured.append(kw))
    response=client.post('/api/v1/tasks',headers=headers,json={'task':'Review attached code','sync':True,'context':{'attachments':[{'name':'example.py','content':'print(42)'}]}})
    assert response.status_code==201
    assert 'print(42)' in captured[0]['instruction'] and 'untrusted context' in captured[0]['instruction']
    assert captured[0]['task_id']==response.json()['task_id']
    assert client.post('/api/v1/tasks',headers={'X-API-Key':'test-viewer-key'},json={'task':'Review'}).status_code==403


def test_one_failed_metadata_probe_does_not_hide_other_models(monkeypatch,catalog):
    original=models.httpx.post
    def show(url,json,**kwargs):
        if json['model']=='embed:latest': raise httpx.ReadTimeout('slow metadata')
        return original(url,json=json,**kwargs)
    monkeypatch.setattr(models.httpx,'post',show)
    result=models.local_models()
    assert result['status']=='online'
    assert result['models'][0]['selectable']
    assert result['models'][1]['status']=='Unavailable'


def test_cloud_selection_uses_existing_provider(catalog):
    assert client.put('/api/v1/system/local-models',headers=headers,json={'model':'huge:cloud'}).status_code == 200
    assert settings.OLLAMA_MODEL == 'huge:cloud'
    assert models.local_models()['models'][-1]['cloud'] is True


def test_model_aliases_are_deduplicated(monkeypatch,catalog):
    monkeypatch.setattr(models.httpx,'get',lambda url,**kwargs:httpx.Response(200,request=httpx.Request('GET',url),json={'models':[{'name':'llama3.2:latest','digest':'same'},{'name':'llama3.2:3b','digest':'same'}]}))
    settings.OLLAMA_MODEL='llama3.2:3b'
    entries=models.local_models()['models']
    assert len(entries)==1
    assert entries[0]['name']=='llama3.2:3b'
