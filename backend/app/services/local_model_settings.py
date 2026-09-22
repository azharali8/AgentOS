"""Persist the local workspace model without adding a provider router."""
import threading
from concurrent.futures import ThreadPoolExecutor
import httpx
from fastapi import HTTPException
from backend.app.config.settings import settings
from backend.app.db.database import get_db_session
from backend.app.db.models import WorkspacePreferenceModel

_lock = threading.Lock()

def restore_model_preference():
    if settings.LLM_PROVIDER.lower() != 'ollama':
        return
    with get_db_session() as db:
        row = db.get(WorkspacePreferenceModel, 'ollama_model')
        if row and isinstance(row.value, str):
            settings.OLLAMA_MODEL = row.value

def _probe_model(entry):
    try:
        response = httpx.post(settings.OLLAMA_BASE_URL.rstrip('/') + '/api/show', json={'model': entry['name']}, timeout=5)
        response.raise_for_status()
        capable = 'completion' in response.json().get('capabilities', [])
        status = 'Available' if capable else 'Not a chat model'
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        capable, status = False, 'Unavailable'
    return entry | {'selectable': capable, 'status': status, 'recommended': capable and not entry['cloud'] and 0 < entry['size'] <= 4000000000}


def local_models():
    models=[]
    try:
        response=httpx.get(settings.OLLAMA_BASE_URL.rstrip('/')+'/api/tags',timeout=3)
        response.raise_for_status()
        seen = {}
        for item in response.json()['models']:
            name=item['name']
            cloud = bool(item.get('remote_host')) or name.endswith((':cloud','-cloud'))
            identity = item.get('digest') or ('llama3.2:3b' if name in ('llama3.2:latest', 'llama3.2:3b') else name)
            if identity in seen:
                if name == settings.OLLAMA_MODEL:
                    seen[identity]['name'] = name
                continue
            capable=False
            model_status='Checking'
            entry = {'name':name,'size':item.get('size',0),'selectable':capable,'status':model_status, 'cloud':cloud, 'recommended':capable and not cloud and 0 < item.get('size',0) <= 4000000000}
            models.append(entry)
            seen[identity] = entry
        with ThreadPoolExecutor(max_workers=6) as executor:
            models = list(executor.map(_probe_model, models))
        status='online'
    except (httpx.HTTPError,ValueError,KeyError,TypeError):
        status='offline';models=[]
    return {'models':models,'status':status,'active_model':settings.OLLAMA_MODEL,'provider':settings.LLM_PROVIDER,'selection_enabled':settings.LLM_PROVIDER.lower()=='ollama'}

def select_model(name):
    with _lock:
        if settings.LLM_PROVIDER.lower() != 'ollama':
            raise HTTPException(409,'Local model selection requires the existing Ollama provider.')
        catalog=local_models()
        if catalog['status']=='offline':
            raise HTTPException(503,'Ollama is offline. Your active model has not changed.')
        if not any(m['name']==name and m['selectable'] for m in catalog['models']):
            raise HTTPException(400,'Select an available Ollama chat model.')
        with get_db_session() as db:
            row=db.get(WorkspacePreferenceModel,'ollama_model')
            if row: row.value=name
            else: db.add(WorkspacePreferenceModel(key='ollama_model',value=name))
        settings.OLLAMA_MODEL=name
        return catalog | {'active_model':name}
