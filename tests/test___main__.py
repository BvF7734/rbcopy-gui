"""Tests for the rbcopy.__main__ entry point (python -m rbcopy)."""

from __future__ import annotations

import runpy
from unittest.mock import patch


def test_main_module_invokes_app() -> None:
    """Running 'python -m rbcopy' calls the CLI app entry point."""
    # Patch rbcopy.cli.app before __main__.py re-imports it so the local
    # binding created by 'from .cli import app' resolves to the mock.
    with patch("rbcopy.cli.app") as mock_app:
        runpy.run_module("rbcopy.__main__", run_name="__main__")
    mock_app.assert_called_once()


def test_main_module_app_not_called_on_import() -> None:
    """When __main__.py is imported (not run), app() is not called."""
    with patch("rbcopy.cli.app") as mock_app:
        runpy.run_module("rbcopy.__main__", run_name="rbcopy.__main__")
    mock_app.assert_not_called()
