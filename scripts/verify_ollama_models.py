"""Explicit, bounded model verification; never run by a health endpoint or background poll.

Run from repository root: python scripts/verify_ollama_models.py
Sends at most two tiny generation requests per distinct installed model. Writes
account-specific, expiring verification to settings.MODEL_VERIFICATION_FILE.
Generated Python tests execute only inside a newly-created temporary probe folder.
"""
import json
import sys
import tempfile
import time
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from backend.app.config.settings import settings
from backend.app.llm.ollama import OllamaProvider
from backend.app.llm.structured import GeneratedFiles, generate_structured
from backend.app.llm.proposal_validation import validate_python_proposal
from backend.app.services.cloud_model_pool import provider_failure


def main():
    endpoint = settings.OLLAMA_BASE_URL.rstrip('/')
    response = httpx.get(endpoint + '/api/tags', timeout=10)
    response.raise_for_status()
    settings.LLM_TIMEOUT_SECONDS = min(settings.LLM_TIMEOUT_SECONDS, 90)
    settings.LLM_STRUCTURED_ATTEMPTS = 1
    settings.OLLAMA_NUM_PREDICT = 1200
    records, seen = [], set()
    for entry in response.json()['models']:
        identity = entry.get('digest') or entry['name']
        if identity in seen: continue
        seen.add(identity)
        name = entry['name']
        cloud = bool(entry.get('remote_host')) or name.endswith((':cloud', '-cloud'))
        metadata = httpx.post(endpoint + '/api/show', json={'model': name}, timeout=10)
        if not cloud and (metadata.status_code != 200 or 'completion' not in metadata.json().get('capabilities', [])):
            continue
        row = {'model': name, 'cloud': cloud, 'status': 'UNAVAILABLE', 'chat': False,
               'structured': False, 'coding': False, 'debugging': False, 'compatible': False,
               'remaining_quota': None}
        start = time.monotonic()
        try:
            provider = OllamaProvider(model=name)
            row['chat'] = bool(provider.generate('Reply with exactly OK.').strip())
            prompt = ('Return only JSON files under the schema. Source calc.py: def add(a,b): return a-b. '
                      'Failing test: assert add(2,3)==5; actual -1. Repair calc.py and create test_add.py '
                      'with a real pytest test importing add from calc and asserting add(2,3)==5. '
                      'Return exactly these two complete files. Include a comment identifying the subtraction mismatch.')
            proposal = generate_structured(provider, prompt, GeneratedFiles,
                lambda r: validate_python_proposal(r, {}, require_tests=True))
            row['structured'] = True
            row['compatible'] = True
            if {f.path for f in proposal.files} != {'calc.py', 'test_add.py'}:
                raise ValueError('Multi-file instruction mismatch')
            with tempfile.TemporaryDirectory(prefix='agentos-model-probe-') as tmp:
                for file in proposal.files:
                    Path(tmp, file.path).write_text(file.content, encoding='utf-8')
                # Independent checks prevent a vacuous generated test from qualifying a model.
                check = subprocess.run([sys.executable, '-c',
                    'from calc import add; assert add(2,3)==5; assert add(-2,3)==1'],
                    cwd=tmp, capture_output=True, text=True, timeout=20)
                test = subprocess.run([sys.executable, '-m', 'pytest', 'test_add.py', '-q', '-p', 'no:cacheprovider'],
                    cwd=tmp, capture_output=True, text=True, timeout=30)
                row['coding'] = check.returncode == 0 and test.returncode == 0
                row['debugging'] = row['coding']
                row['status'] = 'HEALTHY' if row['coding'] else 'DEGRADED'
        except Exception as exc:
            classified = provider_failure(exc)
            row['status'] = classified[0] if classified else ('INCOMPATIBLE' if row['chat'] else 'UNAVAILABLE')
            # Do not write raw provider error bodies or account identifiers.
            row['error_type'] = type(exc).__name__
        row['latency_seconds'] = round(time.monotonic() - start, 2)
        records.append(row)
        print(name, row['status'], row['latency_seconds'], flush=True)
    target = Path(settings.MODEL_VERIFICATION_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps({'endpoint': endpoint, 'checked_at': time.time(), 'models': records}, indent=2), encoding='utf-8')
    temporary.replace(target)


if __name__ == '__main__':
    main()
