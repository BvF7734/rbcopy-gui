"""Tests for rbcopy.conf.settings – application settings via pydantic-settings."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch


from rbcopy.conf.settings import Settings


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


def test_settings_data_dir_defaults_to_none() -> None:
    """data_dir must be None when RBCOPY_DATA_DIR is not set."""
    env = {k: v for k, v in os.environ.items() if k != "RBCOPY_DATA_DIR"}
    with patch.dict("os.environ", env, clear=True):
        settings = Settings()
    assert settings.data_dir is None


# ---------------------------------------------------------------------------
# RBCOPY_DATA_DIR env var
# ---------------------------------------------------------------------------


def test_settings_data_dir_reads_env_var(tmp_path: Path) -> None:
    """data_dir returns the Path from RBCOPY_DATA_DIR when set."""
    with patch.dict("os.environ", {"RBCOPY_DATA_DIR": str(tmp_path)}):
        settings = Settings()
    assert settings.data_dir == tmp_path


def test_settings_data_dir_is_path_type(tmp_path: Path) -> None:
    """data_dir must be a Path instance, not a plain string."""
    with patch.dict("os.environ", {"RBCOPY_DATA_DIR": str(tmp_path)}):
        settings = Settings()
    assert isinstance(settings.data_dir, Path)


def test_settings_data_dir_keyword_override(tmp_path: Path) -> None:
    """data_dir can be supplied directly as a keyword argument (useful for tests)."""
    settings = Settings(data_dir=tmp_path)
    assert settings.data_dir == tmp_path


# ---------------------------------------------------------------------------
# extra env vars are silently ignored
# ---------------------------------------------------------------------------


def test_settings_ignores_unknown_env_vars() -> None:
    """Extra environment variables must not raise a ValidationError."""
    with patch.dict("os.environ", {"RBCOPY_NONEXISTENT_KEY": "some_value"}):
        settings = Settings()
    # No exception raised; data_dir falls back to None.
    assert settings.data_dir is None
