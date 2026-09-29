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
    # Per-user preferences are read at request creation, never copied into global settings.
    return


def model_preference(user_id=None):
    if user_id is None:
        return settings.OLLAMA_MODEL
    from hashlib import sha256
    key = 'model:' + sha256(user_id.encode()).hexdigest()
    with get_db_session() as db:
        row = db.get(WorkspacePreferenceModel, key)
        return row.value if row and isinstance(row.value, str) else 'AGENTOS_AUTO'


def _probe_model(entry):
    try:
        response = httpx.post(settings.OLLAMA_BASE_URL.rstrip('/') + '/api/show', json={'model': entry['name']}, timeout=5)
        response.raise_for_status()
        capable = 'completion' in response.json().get('capabilities', [])
        status = 'Available' if capable else 'Not a chat model'
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        capable, status = False, 'Unavailable'
    return entry | {'selectable': capable, 'status': status, 'recommended': capable and not entry['cloud'] and 0 < entry['size'] <= 4000000000}


def local_models(user_id=None):
    from backend.app.services.cloud_model_pool import verification, pool
    verified = {r["model"] for r in verification() if not r.get("cloud") and r.get("compatible")}
    selected = model_preference(user_id)
    models=[]
    try:
        response=httpx.get(settings.OLLAMA_BASE_URL.rstrip('/')+'/api/tags',timeout=3)
        response.raise_for_status()
        seen = {}
        for item in response.json()['models']:
            name=item['name']
            cloud = bool(item.get('remote_host')) or name.endswith((':cloud','-cloud'))
            if cloud:
                continue
            if name not in verified:
                continue
            identity = item.get('digest') or ('llama3.2:3b' if name in ('llama3.2:latest', 'llama3.2:3b') else name)
            if identity in seen:
                if name == selected:
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
    return {'models':models,'status':status,'active_model':selected,'cloud_status':'AVAILABLE' if pool.candidates() else 'CLOUD_POOL_EXHAUSTED','provider':settings.LLM_PROVIDER,'selection_enabled':settings.LLM_PROVIDER.lower()=='ollama'}

def select_model(name, user_id=None):
    from backend.app.services.cloud_model_pool import AUTO
    from hashlib import sha256
    with _lock:
        if settings.LLM_PROVIDER.lower() != 'ollama':
            raise HTTPException(409,'Local model selection requires the existing Ollama provider.')
        catalog=local_models(user_id)
        if name != AUTO and catalog['status']=='offline':
            raise HTTPException(503,'Ollama is offline. Your active model has not changed.')
        if name != AUTO and not any(m['name']==name and m['selectable'] for m in catalog['models']):
            raise HTTPException(400,'Select an available Ollama chat model.')
        with get_db_session() as db:
            key='model:' + sha256((user_id or 'default').encode()).hexdigest()
            row=db.get(WorkspacePreferenceModel,key)
            if row: row.value=name
            else: db.add(WorkspacePreferenceModel(key=key,value=name))
        import logging
        logging.getLogger('agentos.model_router').info('%s', 'AUTO_MODE_RESTORED' if name == AUTO else 'LOCAL_MODEL_SELECTED')
        return catalog | {'active_model':name}
