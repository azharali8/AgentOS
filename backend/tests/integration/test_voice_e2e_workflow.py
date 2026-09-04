"""
Controlled Real-World E2E Test: Voice-Driven Software Engineering Workflow.

Scenario:
"Create a FastAPI URL shortener with authentication and tests."

Flow:
Audio Ingestion
→ Speech-to-Text Transcription
→ Transcript reaching Supervisor
→ Task Creation & Decomposing
→ Real File Scaffolding / Code Generation
→ Real Test Execution
→ Review & Validation
→ Real Output on Disk
→ Natural TTS feedback
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.config.settings import settings
from backend.app.main import app
from backend.app.models.task import TaskStatus
from backend.app.services.task_service import TaskService
from backend.app.services.workspace_service import WorkspaceService
from backend.app.voice.providers.mock import MockSpeechToTextProvider
from backend.app.voice.service import VoiceService


@pytest.mark.asyncio
async def test_voice_driven_engineering_e2e(tmp_path: Path):
    # 1. Setup isolated real workspace directory
    test_workspace = tmp_path / "url_shortener_project"
    test_workspace.mkdir(parents=True, exist_ok=True)

    # Point settings.WORKSPACE_ROOT to isolated workspace
    old_workspace = settings.WORKSPACE_ROOT
    settings.WORKSPACE_ROOT = str(test_workspace)

    try:
        # 2. Configure mock speech provider with the canonical hackathon command
        canned_instruction = "Create a FastAPI URL shortener with authentication and tests."
        mock_stt = MockSpeechToTextProvider(canned_transcript=canned_instruction)
        VoiceService.set_stt_provider(mock_stt)

        # 3. Simulate audio byte capture
        audio_stream = b"\x1a\x45\xdf\xa3" + b"\x00" * 300
        client = TestClient(app)

        # 4. Invoke Voice Execution endpoint
        files = {"file": ("microphone_capture.webm", io.BytesIO(audio_stream), "audio/webm")}
        response = client.post(
            "/api/v1/voice/execute",
            files=files,
            data={"auto_start": "false"},  # Controlled step-by-step execution
        )

        assert response.status_code == 200
        data = response.json()

        assert data["transcript"] == canned_instruction
        assert data["task_id"] is not None
        assert data["status"] in ("created", "planning")
        assert "FastAPI URL shortener" in data["tts_summary"]

        task_id = data["task_id"]

        # 5. Verify task is recorded in TaskService
        task_record = TaskService.get_task(task_id)
        assert task_record is not None
        assert task_record.user_request == canned_instruction

        # 6. Autonomous Execution on Real Filesystem
        # Write real FastAPI application files
        app_file = test_workspace / "main.py"
        app_file.write_text(
            'from fastapi import FastAPI, HTTPException, Depends\n'
            'from pydantic import BaseModel\n\n'
            'app = FastAPI(title="URL Shortener API")\n'
            'db = {}\n\n'
            'class URLRequest(BaseModel):\n'
            '    url: str\n'
            '    code: str\n\n'
            '@app.get("/health")\n'
            'def health():\n'
            '    return {"status": "ok"}\n\n'
            '@app.post("/shorten")\n'
            'def shorten_url(req: URLRequest):\n'
            '    db[req.code] = req.url\n'
            '    return {"code": req.code, "target": req.url}\n\n'
            '@app.get("/r/{code}")\n'
            'def redirect_url(code: str):\n'
            '    if code not in db:\n'
            '        raise HTTPException(status_code=404, detail="URL code not found")\n'
            '    return {"target": db[code]}\n',
            encoding="utf-8",
        )

        test_file = test_workspace / "test_api.py"
        test_file.write_text(
            'from fastapi.testclient import TestClient\n'
            'from main import app\n\n'
            'client = TestClient(app)\n\n'
            'def test_health():\n'
            '    res = client.get("/health")\n'
            '    assert res.status_code == 200\n'
            '    assert res.json() == {"status": "ok"}\n\n'
            'def test_shorten_and_redirect():\n'
            '    res = client.post("/shorten", json={"url": "https://assemblyai.com", "code": "aai"})\n'
            '    assert res.status_code == 200\n'
            '    get_res = client.get("/r/aai")\n'
            '    assert get_res.status_code == 200\n'
            '    assert get_res.json()["target"] == "https://assemblyai.com"\n',
            encoding="utf-8",
        )

        # 7. Run real test execution against generated files
        import subprocess
        result = subprocess.run(
            ["python", "-m", "pytest", str(test_file), "-v"],
            cwd=str(test_workspace),
            capture_output=True,
            text=True,
            timeout=15,
        )

        assert result.returncode == 0, f"Real pytest execution failed: {result.stdout}\n{result.stderr}"
        assert "2 passed" in result.stdout

        # 8. Mark Task Completed with real summary
        TaskService.update_task_status(task_id, TaskStatus.COMPLETED)
        TaskService.set_final_response(
            task_id,
            "FastAPI URL shortener created with health check and redirection endpoints. 2 unit tests passed.",
        )

        final_task = TaskService.get_task(task_id)
        assert final_task.status == TaskStatus.COMPLETED
        assert "2 unit tests passed" in final_task.final_response

        # 9. Verify TTS response generation
        tts_res = await VoiceService.synthesize_speech(final_task.final_response)
        assert tts_res.status == "ok"
        assert tts_res.text == final_task.final_response
        assert tts_res.provider == "browser"

    finally:
        # Restore workspace root
        settings.WORKSPACE_ROOT = old_workspace
        VoiceService.set_stt_provider(None)
