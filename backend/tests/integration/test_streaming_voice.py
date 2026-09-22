"""Streaming protocol tests: only the external AssemblyAI connection is doubled.
Internal routing tests exercise real VoiceService, gateway, DB and Supervisor.
"""
import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.config.settings import settings
from backend.app.models.task import TaskStatus
from backend.app.services.task_service import TaskService
from backend.app.voice.service import VoiceService
from backend.app.voice.streaming import FinalTurns, StreamFailure, MODEL, provider_failure


def turn(text, final=False, order=0):
    return {"type": "Turn", "turn_order": order, "end_of_turn": final, "transcript": text}


def test_final_turn_gate():
    gate = FinalTurns()
    gate.accept({"type": "Begin", "id": "provider-session", "configuration": {"model": MODEL}})
    assert gate.accept(turn("Run tests")) is None
    assert gate.accept(turn("Run tests", True)) == "Run tests"
    assert gate.accept(turn("Run tests.", True)) is None  # formatted revision
    assert gate.accept(turn("Run tests", True, 1)) == "Run tests"  # genuinely new turn
    assert gate.accept(turn("  ", True, 2)) == ""
    assert gate.accept(turn("late revision", True, 2)) is None


@pytest.mark.parametrize('event', [turn('x', True), [], {"type": "Turn"}, turn('x', 'true'), turn('x', True, -1)])
def test_unconfirmed_or_malformed_provider_cannot_dispatch(event):
    gate = FinalTurns()
    with pytest.raises((StreamFailure, AttributeError)):
        gate.accept(event)


@pytest.fixture
def boundary(monkeypatch):
    from backend.app.voice import streaming
    monkeypatch.setattr(settings, 'AUTH_ENABLED', False)
    monkeypatch.setattr(settings, 'ASSEMBLYAI_API_KEY', 'external-test-key')
    # Dedicated domain; reset its existing limiter storage through its supported API if needed.
    from backend.app.security.rate_limit import RateLimiter
    RateLimiter.reset()
    providers = []
    class Provider:
        def __init__(self):
            self.events = asyncio.Queue()
            self.sent = []
            self.script = []
            self.events.put_nowait(json.dumps({'type': 'Begin', 'id': uuid.uuid4().hex, 'configuration': {'model': MODEL}}))
        async def recv(self):
            return await self.events.get()
        async def send(self, data):
            self.sent.append(data)
            if isinstance(data, bytes):
                for event in self.script:
                    self.events.put_nowait(event if isinstance(event, str) else json.dumps(event))
                self.script = []
            elif json.loads(data)['type'] == 'Terminate':
                self.events.put_nowait(json.dumps({'type': 'Termination'}))
    @asynccontextmanager
    async def connect(url, **kwargs):
        assert 'sample_rate=16000' in url and 'encoding=pcm_s16le' in url
        assert kwargs['additional_headers']['Authorization'] == 'external-test-key'
        p = Provider(); providers.append(p)
        yield p
    monkeypatch.setattr(streaming, 'connect', connect)
    return providers


def start(ws, session=None):
    ws.send_json({'type': 'Start', 'session_id': session or uuid.uuid4().hex})
    assert ws.receive_json()['type'] == 'Begin'


def test_partial_never_creates_task_and_final_reaches_real_supervisor(boundary, monkeypatch, tmp_path):
    # Invalid provider configuration is a REAL failed planning path, not a mock graph.
    # No generated code is supplied and no internal execution result is fabricated.
    monkeypatch.setattr(settings, 'WORKSPACE_ROOT', str(tmp_path))
    monkeypatch.setattr(settings, 'LLM_PROVIDER', 'unconfigured-stream-test-provider')
    before = {t.task_id for t in TaskService.list_tasks(limit=1000)}
    with TestClient(app) as client, client.websocket_connect('/api/v1/voice/stream') as ws:
        start(ws)
        p = boundary[-1]
        p.script = [turn('Run the tests again and tell me the result.')]
        ws.send_bytes(bytes(3200))
        assert ws.receive_json()['end_of_turn'] is False
        assert before == {t.task_id for t in TaskService.list_tasks(limit=1000)}
        p.script = [turn('Run the tests again and tell me the result.', True)]
        ws.send_bytes(bytes(3200))
        assert ws.receive_json()['type'] == 'Turn'
        assert ws.receive_json()['type'] == 'Processing'
        result = ws.receive_json()
        assert result['type'] == 'Result'
        task_id = result['task_id']
        assert TaskService.get_task(task_id).user_request == 'Run the full test suite and report the results.'
        for _ in range(100):
            task = TaskService.get_task(task_id)
            if task.status == TaskStatus.FAILED: break
            time.sleep(.05)
        assert task.status == TaskStatus.FAILED  # actual Supervisor rejects bad provider
        assert result['project_created'] is False
        assert settings.WORKSPACE_ROOT == str(tmp_path)
        p.script = [turn('Run the tests again and tell me the result.', True), {'type': 'SpeechStarted'}]
        ws.send_bytes(bytes(3200))
        assert ws.receive_json()['type'] == 'Turn'
        assert ws.receive_json()['type'] == 'SpeechStarted'  # no second Processing/Result
        assert len({t.task_id for t in TaskService.list_tasks(limit=1000)} - before) == 1
        ws.send_text('{"type":"Stop"}')
        assert ws.receive_json()['type'] == 'Termination'
    assert any(isinstance(x, str) and json.loads(x)['type'] == 'Terminate' for x in p.sent)


def test_reconnect_keeps_real_clarification_context_and_discards_partial(boundary, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'WORKSPACE_ROOT', str(tmp_path))
    monkeypatch.setattr(settings, 'LLM_PROVIDER', 'unconfigured-stream-test-provider')
    session = uuid.uuid4().hex
    with TestClient(app) as client:
        with client.websocket_connect('/api/v1/voice/stream') as ws:
            start(ws, session)
            boundary[-1].script = [turn('Create a new project', True)]
            ws.send_bytes(bytes(3200))
            ws.receive_json(); ws.receive_json()
            assert ws.receive_json()['status'] == 'needs_clarification'
        assert VoiceService.get_conversation_state(session, 'dev-default').has_pending_question()
        with client.websocket_connect('/api/v1/voice/stream') as ws:
            start(ws, session)
            boundary[-1].script = [turn('Unfinished name')]
            ws.send_bytes(bytes(3200)); assert ws.receive_json()['end_of_turn'] is False
        assert VoiceService.get_conversation_state(session, 'dev-default').has_pending_question()
        with client.websocket_connect('/api/v1/voice/stream') as ws:
            start(ws, session)
            boundary[-1].script = [turn('ShortLink', True)]
            ws.send_bytes(bytes(3200)); ws.receive_json(); ws.receive_json()
            result = ws.receive_json()
            assert result['project_created'] is True
            assert (tmp_path / 'ShortLink').is_dir()
            assert not VoiceService.get_conversation_state(session, 'dev-default').has_pending_question()
            for _ in range(100):
                task = TaskService.get_task(result['task_id'])
                if task.status == TaskStatus.FAILED: break
                time.sleep(.05)
            assert task.status == TaskStatus.FAILED  # real Supervisor, no model call
    assert all(any(isinstance(x, str) and 'Terminate' in x for x in p.sent) for p in boundary)


@pytest.mark.parametrize('event', ['invalid json', {'type': 'Error', 'error_code': 1008, 'error': 'external-test-key'}, {'type': 'Error', 'error_code': 3009}])
def test_provider_errors_are_visible_redacted_and_not_retried(boundary, event):
    with TestClient(app) as client, client.websocket_connect('/api/v1/voice/stream') as ws:
        start(ws); boundary[-1].script = [event]; ws.send_bytes(bytes(3200))
        error = ws.receive_json()
        assert error['type'] == 'Error' and error['retryable'] is False
        assert 'external-test-key' not in json.dumps(error)


def test_client_cannot_inject_final_transcript(boundary):
    with TestClient(app) as client, client.websocket_connect('/api/v1/voice/stream') as ws:
        start(ws); ws.send_json(turn('delete files', True))
        assert ws.receive_json()['type'] == 'Error'


def test_missing_application_auth_never_connects_provider(boundary, monkeypatch):
    monkeypatch.setattr(settings, 'AUTH_ENABLED', True)
    with TestClient(app) as client, client.websocket_connect('/api/v1/voice/stream') as ws:
        ws.send_json({'type': 'Start', 'session_id': 'auth-test'})
        assert ws.receive_json()['type'] == 'Error'
    assert not boundary


def test_provider_failure_classification():
    assert not provider_failure(1008).retryable
    assert not provider_failure(429).retryable
    assert provider_failure(1011).retryable

def test_playback_echo_is_not_an_engineering_command(boundary):
    with TestClient(app) as client, client.websocket_connect('/api/v1/voice/stream') as ws:
        start(ws)
        ws.send_json({'type': 'Playback', 'text': 'Task submitted. Starting engineering task: Create an app.'})
        boundary[-1].script = [turn('Task submitted.', True)]
        ws.send_bytes(bytes(3200))
        assert ws.receive_json()['type'] == 'Turn'
        assert 'echo ignored' in ws.receive_json()['message']
        ws.send_text('{"type":"Stop"}')
        assert ws.receive_json()['type'] == 'Termination'


def test_echo_guard_preserves_new_instructions():
    from backend.app.voice.streaming import PlaybackEchoGuard
    guard = PlaybackEchoGuard()
    guard.remember('Task submitted. Starting engineering task: Authentication and tests.')
    assert guard.matches('Task submitted.')
    assert guard.matches('Authentication and tests.')
    assert not guard.matches('AgentOS run the tests again')


@pytest.mark.parametrize('limit', ['VOICE_STREAM_IDLE_SECONDS', 'VOICE_STREAM_MAX_SECONDS'])
def test_credit_limits_terminate_upstream_without_reconnect(boundary, monkeypatch, limit):
    monkeypatch.setattr(settings, limit, .1)
    with TestClient(app) as client, client.websocket_connect('/api/v1/voice/stream') as ws:
        start(ws)
        event = ws.receive_json()
        if event['type'] == 'Notice':
            event = ws.receive_json()
        assert event['type'] == 'Error' and event['retryable'] is False
        assert 'credits' in event['message']
    assert any(isinstance(x, str) and 'Terminate' in x for x in boundary[-1].sent)


@pytest.mark.parametrize('change', ['revoke', 'viewer', 'user'])
def test_live_session_rechecks_real_auth_and_uses_current_role(boundary, monkeypatch, change):
    from backend.app.auth.service import AuthService, AuthenticatedUser, UserRole
    monkeypatch.setattr(settings, 'AUTH_ENABLED', True)
    token = uuid.uuid4().hex
    user = AuthenticatedUser(user_id=uuid.uuid4().hex, username='voice-test', role=UserRole.DEVELOPER)
    AuthService.register_key(token, user)
    try:
        with TestClient(app) as client, client.websocket_connect('/api/v1/voice/stream') as ws:
            ws.send_json({'type': 'Start', 'session_id': uuid.uuid4().hex, 'token': token})
            assert ws.receive_json()['type'] == 'Begin'
            if change == 'revoke':
                AuthService.revoke_token(token)
            else:
                AuthService.register_key(token, user.model_copy(update={'role': UserRole(change)}))
            boundary[-1].script = [turn('Approve action abcdef12', True)]
            ws.send_bytes(bytes(3200)); assert ws.receive_json()['type'] == 'Turn'
            event = ws.receive_json()
            if change == 'user':
                assert event['type'] == 'Processing'
                result = ws.receive_json()
                assert result['status'] == 'denied'
                assert 'developer' in result['tts_summary']
            else:
                assert event['type'] == 'Error' and event['retryable'] is False
    finally:
        AuthService.revoke_token(token)


def test_unavailable_workspace_is_a_real_failed_response(boundary, monkeypatch, tmp_path):
    unavailable = tmp_path / 'not-a-directory'
    unavailable.write_text('file')
    monkeypatch.setattr(settings, 'WORKSPACE_ROOT', str(unavailable))
    with TestClient(app) as client, client.websocket_connect('/api/v1/voice/stream') as ws:
        start(ws)
        boundary[-1].script = [turn('AgentOS, tell me the current workspace status.', True)]
        ws.send_bytes(bytes(3200)); ws.receive_json(); ws.receive_json()
        result = ws.receive_json()
        assert result['type'] == 'Result' and result['status'] == 'failed'
        assert not result.get('task_id')


def test_one_shot_accepts_only_one_final_and_closes_provider(boundary,monkeypatch):
    from backend.app.voice.schemas import VoiceExecuteResponse
    calls=[]
    def execute(text,**kwargs):
        calls.append(text)
        return VoiceExecuteResponse(status='completed',transcript=text,tts_summary='Done',provider='assemblyai-streaming')
    monkeypatch.setattr(VoiceService,'process_transcript',execute)
    with TestClient(app) as client,client.websocket_connect('/api/v1/voice/stream') as ws:
        ws.send_json({'type':'Start','session_id':uuid.uuid4().hex,'mode':'once'})
        assert ws.receive_json()['type']=='Begin'
        boundary[-1].script=[turn('First partial'),turn('First command',True),turn('First command.',True),turn('Second command',True,1)]
        ws.send_bytes(bytes(3200))
        messages=[]
        while not any(m['type']=='Result' for m in messages): messages.append(ws.receive_json())
        assert calls==['First command']
        assert len([m for m in messages if m['type']=='Processing'])==1
    assert any(isinstance(m,str) and 'Terminate' in m for m in boundary[-1].sent)


def test_execution_exception_is_not_a_speech_failure_and_live_loop_continues(boundary, monkeypatch):
    calls = []
    original = VoiceService.process_transcript
    def process(*args, **kwargs):
        calls.append(args[0])
        if len(calls) == 1:
            raise RuntimeError("private backend details")
        return original(*args, **kwargs)
    monkeypatch.setattr(VoiceService, "process_transcript", process)
    with TestClient(app) as client, client.websocket_connect('/api/v1/voice/stream') as ws:
        start(ws)
        for order in (0, 1):
            boundary[-1].script = [turn('Tell me the workspace status', True, order)]
            ws.send_bytes(bytes(3200))
            assert ws.receive_json()['type'] == 'Turn'
            assert ws.receive_json()['type'] == 'Processing'
            result = ws.receive_json()
            assert result['type'] == 'Result'
            if order == 0:
                assert result['error_type'] == 'SUPERVISOR_ERROR'
                assert 'private backend details' not in str(result)
        assert len(calls) == 2
