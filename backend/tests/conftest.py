"""Pytest bootstrap for AgentOS.

The hosted Windows environment used for this workspace does not always grant
pytest access to the default user temp directory.  Redirect pytest's temp root
into the repository so `tmp_path` and related fixtures remain available for the
full suite.
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path


def pytest_configure(config) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    temp_root = repo_root / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_path = str(temp_root)

    os.environ["TMP"] = temp_path
    os.environ["TEMP"] = temp_path
    os.environ["TMPDIR"] = temp_path
    tempfile.tempdir = temp_path
    if not config.option.basetemp:
        # Unique per run: avoid cross-user ACLs and concurrent-run deletion.
        config.option.basetemp = str(temp_root / f"pytest-{uuid.uuid4().hex}")

    # Set before test collection imports settings/engine; never use the user's DB.
    database_path = temp_root / f"test-session-{uuid.uuid4().hex}" / "agentos.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    # Ordinary regression tests must never invoke the user's installed model.
    # Provider contract tests instantiate/patch their adapter explicitly; live
    # acceptance is run separately against the real configured provider.
    os.environ["LLM_PROVIDER"] = "mock"

    # Ensure repository root and sdk package are resolvable
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    sdk_path = str(repo_root / "sdk")
    if sdk_path not in sys.path:
        sys.path.insert(0, sdk_path)


import pytest

@pytest.fixture(scope="session", autouse=True)
def initialize_test_database():
    from backend.app.db.database import init_db, engine
    init_db()
    yield
    engine.dispose()

@pytest.fixture(autouse=True)
def reset_workspace_root_setting():
    from backend.app.config.settings import PROJECT_ROOT, settings
    default_ws = str(PROJECT_ROOT / "workspace")
    old_setting = settings.WORKSPACE_ROOT
    old_env = os.environ.get("WORKSPACE_ROOT")
    # Ensure standard workspace root before each test starts
    settings.WORKSPACE_ROOT = default_ws
    os.environ["WORKSPACE_ROOT"] = default_ws
    yield
    # Unconditionally restore to default workspace root to prevent test leakage
    settings.WORKSPACE_ROOT = default_ws
    if old_env is not None and "pytest" not in old_env.lower():
        os.environ["WORKSPACE_ROOT"] = old_env
    else:
        os.environ["WORKSPACE_ROOT"] = default_ws


@pytest.fixture(autouse=True)
def enforce_mock_voice_provider():
    """Guarantee AssemblyAI credits are protected during automated test execution."""
    from backend.app.voice.service import VoiceService
    from backend.app.voice.providers.mock import MockSpeechToTextProvider, BrowserTextToSpeechProvider
    VoiceService.set_stt_provider(MockSpeechToTextProvider())
    VoiceService.set_tts_provider(BrowserTextToSpeechProvider())
    yield
    VoiceService.set_stt_provider(None)
    VoiceService.set_tts_provider(None)
