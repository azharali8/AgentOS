"""Pytest bootstrap for AgentOS.

The hosted Windows environment used for this workspace does not always grant
pytest access to the default user temp directory.  Redirect pytest's temp root
into the repository so `tmp_path` and related fixtures remain available for the
full suite.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def pytest_configure() -> None:
    temp_root = Path(__file__).resolve().parent / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_path = str(temp_root)

    os.environ["TMP"] = temp_path
    os.environ["TEMP"] = temp_path
    os.environ["TMPDIR"] = temp_path
    tempfile.tempdir = temp_path
