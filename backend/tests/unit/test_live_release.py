"""Live integration boundaries, using provider doubles only (no AssemblyAI credits)."""
import uuid
import pytest
from backend.app.config.settings import settings, PROJECT_ROOT
from backend.app.voice.service import VoiceService
from backend.app.services.task_service import TaskService

@pytest.mark.parametrize('selection',['AGENTOS_AUTO','qwen2.5-coder:3b'])
def test_live_task_captures_user_model_and_current_project(tmp_path,monkeypatch,selection):
    monkeypatch.setattr(settings,'WORKSPACE_ROOT',str(tmp_path))
    monkeypatch.setattr('backend.app.services.local_model_settings.model_preference',lambda user:selection if user=='live-user' else 'wrong-user')
    calls=[]
    def start(instruction,task_id,sync):
        task=TaskService.get_task(task_id)
        calls.append((task.metadata,settings.WORKSPACE_ROOT,instruction))
    monkeypatch.setattr('backend.app.voice.service.MultiAgentService.start_task',start)
    result=VoiceService.process_transcript('Run the tests and tell me the result.',user_id='live-user',session_id=uuid.uuid4().hex,provider='assemblyai-streaming')
    assert result.task_id and len(calls)==1
    metadata,workspace,instruction=calls[0]
    assert metadata['model_selection']==selection and metadata['model_owner']=='live-user'
    assert workspace==str(tmp_path) and 'test' in instruction.lower()


def test_live_disconnected_project_starts_nothing(monkeypatch):
    monkeypatch.setattr(settings,'WORKSPACE_ROOT',str(PROJECT_ROOT/'workspace'))
    def forbidden(*a,**k): raise AssertionError('Disconnected Live must not create a task')
    monkeypatch.setattr(TaskService,'create_task',forbidden)
    result=VoiceService.process_transcript('Run the tests.',session_id=uuid.uuid4().hex,provider='assemblyai-streaming')
    assert result.task_id is None and 'Connect a project' in result.tts_summary


def test_live_approval_uses_ui_even_for_admin(monkeypatch):
    def forbidden(*a,**k): raise AssertionError('Live must not resolve approval')
    monkeypatch.setattr('backend.app.voice.agent.command_router.AgentOSCommandGateway.resolve_approval',forbidden)
    result=VoiceService.process_transcript('Approve action abc123.',user_role='admin',session_id=uuid.uuid4().hex,provider='assemblyai-streaming')
    assert result.task_id is None and 'approval buttons' in result.tts_summary
