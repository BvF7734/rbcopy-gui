"""Tests for rbcopy.app_dirs – application directory resolution."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


import rbcopy.app_dirs as app_dirs_module
from rbcopy.app_dirs import (
    clear_data_dir,
    get_data_dir,
    get_log_dir,
    set_data_dir,
    validate_data_dir,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_bootstrap(tmp_path: Path, data_dir: Path) -> Path:
    """Write a bootstrap pointer file and return its path."""
    bootstrap = tmp_path / ".rbcopy_location"
    bootstrap.write_text(json.dumps({"data_dir": str(data_dir)}), encoding="utf-8")
    return bootstrap


def _env_without(key: str) -> dict[str, str]:
    """Return a copy of the current environment with *key* removed."""
    return {k: v for k, v in os.environ.items() if k != key}


# ---------------------------------------------------------------------------
# get_data_dir – priority 1: environment variable
# ---------------------------------------------------------------------------


def test_get_data_dir_returns_env_var_when_set(tmp_path: Path) -> None:
    """RBCOPY_DATA_DIR env var takes priority over all other sources."""
    expected = tmp_path / "env_override"
    with patch.dict("os.environ", {"RBCOPY_DATA_DIR": str(expected)}):
        result = get_data_dir()
    assert result == expected


def test_get_data_dir_env_var_overrides_bootstrap(tmp_path: Path) -> None:
    """Env var wins even when a valid bootstrap file exists."""
    env_dir = tmp_path / "from_env"
    bootstrap_dir = tmp_path / "from_bootstrap"
    bootstrap = _write_bootstrap(tmp_path, bootstrap_dir)

    with patch.dict("os.environ", {"RBCOPY_DATA_DIR": str(env_dir)}):
        with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
            result = get_data_dir()

    assert result == env_dir


# ---------------------------------------------------------------------------
# get_data_dir – priority 2: bootstrap file
# ---------------------------------------------------------------------------


def test_get_data_dir_reads_bootstrap_when_env_absent(tmp_path: Path) -> None:
    """Bootstrap file is used when RBCOPY_DATA_DIR is not set."""
    data_dir = tmp_path / "from_bootstrap"
    bootstrap = _write_bootstrap(tmp_path, data_dir)

    # Remove only RBCOPY_DATA_DIR so Path.home() keeps working on Windows.
    with patch.dict("os.environ", _env_without("RBCOPY_DATA_DIR"), clear=True):
        with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
            result = get_data_dir()

    assert result == data_dir


def test_get_data_dir_falls_through_on_corrupt_bootstrap(tmp_path: Path) -> None:
    """Corrupt bootstrap JSON is silently ignored; platform default is used."""
    bootstrap = tmp_path / ".rbcopy_location"
    bootstrap.write_text("not valid json", encoding="utf-8")

    with patch.dict("os.environ", _env_without("RBCOPY_DATA_DIR"), clear=True):
        with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
            with patch.object(app_dirs_module, "_platform_default", return_value=tmp_path / "default"):
                result = get_data_dir()

    assert result == tmp_path / "default"


def test_get_data_dir_falls_through_on_missing_data_dir_key(tmp_path: Path) -> None:
    """Bootstrap file with wrong key falls through to platform default."""
    bootstrap = tmp_path / ".rbcopy_location"
    bootstrap.write_text(json.dumps({"other_key": "value"}), encoding="utf-8")

    with patch.dict("os.environ", _env_without("RBCOPY_DATA_DIR"), clear=True):
        with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
            with patch.object(app_dirs_module, "_platform_default", return_value=tmp_path / "default"):
                result = get_data_dir()

    assert result == tmp_path / "default"


def test_get_data_dir_falls_through_on_empty_data_dir_value(tmp_path: Path) -> None:
    """Bootstrap file with empty string value falls through to platform default."""
    bootstrap = tmp_path / ".rbcopy_location"
    bootstrap.write_text(json.dumps({"data_dir": "   "}), encoding="utf-8")

    with patch.dict("os.environ", _env_without("RBCOPY_DATA_DIR"), clear=True):
        with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
            with patch.object(app_dirs_module, "_platform_default", return_value=tmp_path / "default"):
                result = get_data_dir()

    assert result == tmp_path / "default"


# ---------------------------------------------------------------------------
# get_data_dir – priority 3: platform default
# ---------------------------------------------------------------------------


def test_platform_default_windows_uses_localappdata(tmp_path: Path) -> None:
    """On Windows, _platform_default uses %LOCALAPPDATA%\\RBCopy."""
    with patch.object(sys, "platform", "win32"):
        with patch.dict("os.environ", {"LOCALAPPDATA": str(tmp_path)}):
            result = app_dirs_module._platform_default()
    assert result == tmp_path / "RBCopy"


def test_platform_default_windows_fallback_when_no_localappdata() -> None:
    """On Windows without LOCALAPPDATA, falls back to {home}/RBCopy.

    Uses _env_without so USERPROFILE/HOMEPATH/HOMEDRIVE remain set and
    Path.home() can still resolve correctly on Windows.
    """
    with patch.object(sys, "platform", "win32"):
        # Remove only LOCALAPPDATA — do NOT clear all vars or Path.home() raises.
        with patch.dict("os.environ", _env_without("LOCALAPPDATA"), clear=True):
            result = app_dirs_module._platform_default()
    assert result == Path.home() / "RBCopy"


def test_platform_default_non_windows_uses_hidden_dir() -> None:
    """On non-Windows platforms, default is ~/.rbcopy."""
    with patch.object(sys, "platform", "linux"):
        result = app_dirs_module._platform_default()
    assert result == Path.home() / ".rbcopy"


def test_platform_default_macos_uses_hidden_dir() -> None:
    """On macOS, default is ~/.rbcopy (same as Linux)."""
    with patch.object(sys, "platform", "darwin"):
        result = app_dirs_module._platform_default()
    assert result == Path.home() / ".rbcopy"


# ---------------------------------------------------------------------------
# get_log_dir
# ---------------------------------------------------------------------------


def test_get_log_dir_returns_logs_subdirectory(tmp_path: Path) -> None:
    """get_log_dir returns {data_dir}/logs/."""
    with patch.dict("os.environ", {"RBCOPY_DATA_DIR": str(tmp_path)}):
        result = get_log_dir()
    assert result == tmp_path / "logs"


def test_get_log_dir_creates_directory(tmp_path: Path) -> None:
    """get_log_dir creates the logs subdirectory if it does not exist."""
    data_dir = tmp_path / "data"
    with patch.dict("os.environ", {"RBCOPY_DATA_DIR": str(data_dir)}):
        result = get_log_dir()
    assert result.is_dir()


# ---------------------------------------------------------------------------
# set_data_dir
# ---------------------------------------------------------------------------


def test_set_data_dir_writes_bootstrap_file(tmp_path: Path) -> None:
    """set_data_dir writes the configured path to the bootstrap file."""
    bootstrap = tmp_path / ".rbcopy_location"
    new_dir = tmp_path / "custom_data"

    with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
        result = set_data_dir(new_dir)

    assert result is True
    data = json.loads(bootstrap.read_text(encoding="utf-8"))
    assert data["data_dir"] == str(new_dir)


def test_set_data_dir_returns_false_on_write_failure(tmp_path: Path) -> None:
    """set_data_dir returns False when the bootstrap file cannot be written."""
    bootstrap = tmp_path / ".rbcopy_location"

    with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
        with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            result = set_data_dir(tmp_path / "new_dir")

    assert result is False


def test_set_data_dir_then_get_data_dir_round_trip(tmp_path: Path) -> None:
    """set_data_dir followed by get_data_dir returns the configured path."""
    bootstrap = tmp_path / ".rbcopy_location"
    new_dir = tmp_path / "my_custom_dir"

    with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
        with patch.dict("os.environ", _env_without("RBCOPY_DATA_DIR"), clear=True):
            set_data_dir(new_dir)
            result = get_data_dir()

    assert result == new_dir


# ---------------------------------------------------------------------------
# clear_data_dir
# ---------------------------------------------------------------------------


def test_clear_data_dir_removes_bootstrap_file(tmp_path: Path) -> None:
    """clear_data_dir removes the bootstrap pointer file."""
    bootstrap = tmp_path / ".rbcopy_location"
    bootstrap.write_text(json.dumps({"data_dir": str(tmp_path)}), encoding="utf-8")

    with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
        result = clear_data_dir()

    assert result is True
    assert not bootstrap.exists()


def test_clear_data_dir_returns_true_when_file_absent(tmp_path: Path) -> None:
    """clear_data_dir is a no-op (and returns True) when no bootstrap file exists."""
    bootstrap = tmp_path / ".rbcopy_location_nonexistent"

    with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
        result = clear_data_dir()

    assert result is True


def test_clear_data_dir_returns_false_on_unlink_failure(tmp_path: Path) -> None:
    """clear_data_dir returns False when unlink raises OSError."""
    bootstrap = tmp_path / ".rbcopy_location"
    bootstrap.write_text("{}", encoding="utf-8")

    with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
        with patch("pathlib.Path.unlink", side_effect=OSError("permission denied")):
            result = clear_data_dir()

    assert result is False


# ---------------------------------------------------------------------------
# validate_data_dir
# ---------------------------------------------------------------------------


def test_validate_data_dir_accepts_valid_writable_path(tmp_path: Path) -> None:
    """validate_data_dir returns None for a valid, writable absolute path."""
    result = validate_data_dir(tmp_path / "data")
    assert result is None


def test_validate_data_dir_rejects_relative_path() -> None:
    """validate_data_dir rejects relative paths."""
    result = validate_data_dir(Path("relative/path"))
    assert result is not None
    assert "absolute" in result.lower()


def test_validate_data_dir_rejects_home_directory() -> None:
    """validate_data_dir rejects using the home directory itself."""
    result = validate_data_dir(Path.home())
    assert result is not None
    assert "home" in result.lower()


def test_validate_data_dir_creates_directory_for_probe(tmp_path: Path) -> None:
    """validate_data_dir can create a new directory to probe writeability."""
    new_dir = tmp_path / "does" / "not" / "yet" / "exist"
    result = validate_data_dir(new_dir)
    assert result is None
    assert new_dir.is_dir()


def test_validate_data_dir_does_not_leave_probe_file(tmp_path: Path) -> None:
    """validate_data_dir cleans up the probe file after the check."""
    target = tmp_path / "target"
    validate_data_dir(target)
    probe_files = list(target.glob(".rbcopy_write_test"))
    assert probe_files == []


def test_validate_data_dir_returns_error_on_unresolvable_path(tmp_path: Path) -> None:
    """validate_data_dir returns an error string when path.resolve() raises."""
    # tmp_path is always absolute. Simulating a path that cannot be resolved
    # (e.g. a path exceeding MAX_PATH on Windows or a dangling symlink).
    with patch("pathlib.Path.resolve", side_effect=OSError("bad path")):
        result = validate_data_dir(tmp_path / "test_path")
    assert result is not None
    assert "Invalid path" in result


def test_validate_data_dir_continues_when_home_resolve_fails(tmp_path: Path) -> None:
    """validate_data_dir skips the home-dir check if Path.home().resolve() raises."""
    # Patch only Path.home() so that its .resolve() call raises OSError, triggering
    # the 'except OSError: pass' branch. The actual path under test uses tmp_path
    # which is real and writable, so the function should succeed.
    mock_home = MagicMock()
    mock_home.resolve.side_effect = OSError("home unavailable")
    with patch("pathlib.Path.home", return_value=mock_home):
        result = validate_data_dir(tmp_path / "subdir")
    assert result is None


def test_validate_data_dir_returns_error_when_not_writable(tmp_path: Path) -> None:
    """validate_data_dir returns a 'not writable' message when mkdir/write raises."""
    with patch("pathlib.Path.mkdir", side_effect=OSError("read-only filesystem")):
        result = validate_data_dir(tmp_path / "locked_dir")
    assert result is not None
    assert "not writable" in result.lower()
