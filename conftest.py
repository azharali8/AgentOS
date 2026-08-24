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
from pathlib import Path


def pytest_configure() -> None:
    repo_root = Path(__file__).resolve().parent
    temp_root = repo_root / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_path = str(temp_root)

    os.environ["TMP"] = temp_path
    os.environ["TEMP"] = temp_path
    os.environ["TMPDIR"] = temp_path
    tempfile.tempdir = temp_path

    # Ensure sdk package is resolvable
    sdk_path = str(repo_root / "sdk")
    if sdk_path not in sys.path:
        sys.path.insert(0, sdk_path)
