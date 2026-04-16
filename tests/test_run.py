"""Tests for the run.py entry-point script."""

from __future__ import annotations

import runpy
from pathlib import Path
from unittest.mock import patch


_RUN_PY = str(Path(__file__).parent.parent / "run.py")


def test_run_py_invokes_app_when_run_as_main() -> None:
    """Executing run.py as __main__ must call the CLI app entry point."""
    with patch("rbcopy.cli.app") as mock_app:
        runpy.run_path(_RUN_PY, run_name="__main__")
    mock_app.assert_called_once()


def test_run_py_does_not_invoke_app_on_import() -> None:
    """Importing run.py (run_name != '__main__') must not call app()."""
    with patch("rbcopy.cli.app") as mock_app:
        runpy.run_path(_RUN_PY, run_name="run")
    mock_app.assert_not_called()
