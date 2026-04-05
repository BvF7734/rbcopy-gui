"""Tests for rbcopy.app_dirs – application directory resolution."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


import rbcopy.app_dirs as app_dirs_module
from rbcopy.app_dirs import (
    _u_drive_exists,
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
    bootstrap = tmp_path / ".gl_tools_location"
    bootstrap.write_text(json.dumps({"data_dir": str(data_dir)}), encoding="utf-8")
    return bootstrap


# ---------------------------------------------------------------------------
# _u_drive_exists
# ---------------------------------------------------------------------------


def test_u_drive_exists_returns_false_on_non_windows() -> None:
    """_u_drive_exists is always False on non-Windows platforms."""
    with patch.object(sys, "platform", "linux"):
        assert _u_drive_exists() is False


def test_u_drive_exists_returns_false_on_non_windows_darwin() -> None:
    """_u_drive_exists is always False on macOS."""
    with patch.object(sys, "platform", "darwin"):
        assert _u_drive_exists() is False


def test_u_drive_exists_returns_false_when_drive_absent(tmp_path: Path) -> None:
    """_u_drive_exists returns False when U:\\ path does not exist."""
    with patch.object(sys, "platform", "win32"):
        with patch("pathlib.Path.exists", return_value=False):
            assert _u_drive_exists() is False


def test_u_drive_exists_returns_true_when_drive_present(tmp_path: Path) -> None:
    """_u_drive_exists returns True when U:\\ path reports as existing."""
    with patch.object(sys, "platform", "win32"):
        with patch("pathlib.Path.exists", return_value=True):
            assert _u_drive_exists() is True


def test_u_drive_exists_returns_false_on_oserror() -> None:
    """_u_drive_exists returns False when Path.exists() raises OSError."""
    with patch.object(sys, "platform", "win32"):
        with patch("pathlib.Path.exists", side_effect=OSError("no drive")):
            assert _u_drive_exists() is False


# ---------------------------------------------------------------------------
# _platform_default
# ---------------------------------------------------------------------------


def test_platform_default_windows_uses_localappdata(tmp_path: Path) -> None:
    """On Windows, _platform_default uses %LOCALAPPDATA%\\GL_Tools."""
    with patch.object(sys, "platform", "win32"):
        with patch.dict("os.environ", {"LOCALAPPDATA": str(tmp_path)}):
            result = app_dirs_module._platform_default()
    assert result == tmp_path / "GL_Tools"


def test_platform_default_windows_fallback_when_no_localappdata() -> None:
    """On Windows without LOCALAPPDATA, falls back to {home}/GL_Tools."""
    with patch.object(sys, "platform", "win32"):
        with patch.dict("os.environ", {}, clear=True):
            # Patch home so the test does not depend on the real home path.
            with patch("pathlib.Path.home", return_value=Path("/fake/home")):
                result = app_dirs_module._platform_default()
    assert result == Path("/fake/home") / "GL_Tools"


def test_platform_default_non_windows_uses_hidden_dir() -> None:
    """On non-Windows platforms, default is ~/.gl_tools."""
    with patch.object(sys, "platform", "linux"):
        result = app_dirs_module._platform_default()
    assert result == Path.home() / ".gl_tools"


def test_platform_default_macos_uses_hidden_dir() -> None:
    """On macOS, default is ~/.gl_tools (same as Linux)."""
    with patch.object(sys, "platform", "darwin"):
        result = app_dirs_module._platform_default()
    assert result == Path.home() / ".gl_tools"


# ---------------------------------------------------------------------------
# _resolve_base_dir – priority 1: bootstrap file
# ---------------------------------------------------------------------------


def test_resolve_base_dir_reads_bootstrap_file(tmp_path: Path) -> None:
    """Bootstrap file with a valid data_dir is used as the base directory."""
    configured = tmp_path / "my_base"
    bootstrap = _write_bootstrap(tmp_path, configured)

    with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
        result = app_dirs_module._resolve_base_dir()

    assert result == configured


def test_resolve_base_dir_falls_through_on_corrupt_bootstrap(tmp_path: Path) -> None:
    """Corrupt bootstrap JSON is silently ignored; next priority is used."""
    bootstrap = tmp_path / ".gl_tools_location"
    bootstrap.write_text("not valid json", encoding="utf-8")

    with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
        with patch.object(app_dirs_module, "_u_drive_exists", return_value=False):
            with patch.object(app_dirs_module, "_platform_default", return_value=tmp_path / "default"):
                result = app_dirs_module._resolve_base_dir()

    assert result == tmp_path / "default"


def test_resolve_base_dir_falls_through_on_missing_data_dir_key(tmp_path: Path) -> None:
    """Bootstrap file with wrong key falls through to next priority."""
    bootstrap = tmp_path / ".gl_tools_location"
    bootstrap.write_text(json.dumps({"other_key": "value"}), encoding="utf-8")

    with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
        with patch.object(app_dirs_module, "_u_drive_exists", return_value=False):
            with patch.object(app_dirs_module, "_platform_default", return_value=tmp_path / "default"):
                result = app_dirs_module._resolve_base_dir()

    assert result == tmp_path / "default"


def test_resolve_base_dir_falls_through_on_empty_data_dir_value(tmp_path: Path) -> None:
    """Bootstrap file with blank string value falls through to next priority."""
    bootstrap = tmp_path / ".gl_tools_location"
    bootstrap.write_text(json.dumps({"data_dir": "   "}), encoding="utf-8")

    with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
        with patch.object(app_dirs_module, "_u_drive_exists", return_value=False):
            with patch.object(app_dirs_module, "_platform_default", return_value=tmp_path / "default"):
                result = app_dirs_module._resolve_base_dir()

    assert result == tmp_path / "default"


# ---------------------------------------------------------------------------
# _resolve_base_dir – priority 2: U:\ drive
# ---------------------------------------------------------------------------


def test_resolve_base_dir_uses_network_drive_when_u_exists(tmp_path: Path) -> None:
    """When no bootstrap file exists but U:\\ is available, base is U:\\GL_Tools."""
    bootstrap = tmp_path / ".gl_tools_location_nonexistent"

    with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
        with patch.object(app_dirs_module, "_u_drive_exists", return_value=True):
            result = app_dirs_module._resolve_base_dir()

    assert result == app_dirs_module._NETWORK_DRIVE_BASE


def test_resolve_base_dir_bootstrap_takes_priority_over_u_drive(tmp_path: Path) -> None:
    """A valid bootstrap file wins even when U:\\ drive is available."""
    configured = tmp_path / "bootstrap_base"
    bootstrap = _write_bootstrap(tmp_path, configured)

    with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
        with patch.object(app_dirs_module, "_u_drive_exists", return_value=True):
            result = app_dirs_module._resolve_base_dir()

    assert result == configured


# ---------------------------------------------------------------------------
# _resolve_base_dir – priority 3: platform default
# ---------------------------------------------------------------------------


def test_resolve_base_dir_falls_back_to_platform_default(tmp_path: Path) -> None:
    """When no bootstrap and no U:\\ drive, platform default is used."""
    bootstrap = tmp_path / ".gl_tools_location_nonexistent"
    platform_default = tmp_path / "platform_default"

    with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
        with patch.object(app_dirs_module, "_u_drive_exists", return_value=False):
            with patch.object(app_dirs_module, "_platform_default", return_value=platform_default):
                result = app_dirs_module._resolve_base_dir()

    assert result == platform_default


# ---------------------------------------------------------------------------
# get_data_dir
# ---------------------------------------------------------------------------


def test_get_data_dir_appends_app_name(tmp_path: Path) -> None:
    """get_data_dir returns base_dir / app_name."""
    base = tmp_path / "base"

    with patch.object(app_dirs_module, "_resolve_base_dir", return_value=base):
        result = get_data_dir(app_name="rbcopy")

    assert result == base / "rbcopy"


def test_get_data_dir_creates_app_directory(tmp_path: Path) -> None:
    """get_data_dir creates the application subdirectory."""
    base = tmp_path / "base"

    with patch.object(app_dirs_module, "_resolve_base_dir", return_value=base):
        result = get_data_dir(app_name="rbcopy")

    assert result.is_dir()


def test_get_data_dir_different_app_names(tmp_path: Path) -> None:
    """Different app_name values produce sibling directories under the same base."""
    base = tmp_path / "base"

    with patch.object(app_dirs_module, "_resolve_base_dir", return_value=base):
        rbcopy_dir = get_data_dir(app_name="rbcopy")
        loadv5_dir = get_data_dir(app_name="loadv5")

    assert rbcopy_dir == base / "rbcopy"
    assert loadv5_dir == base / "loadv5"
    assert rbcopy_dir != loadv5_dir


def test_get_data_dir_creates_missing_parents(tmp_path: Path) -> None:
    """get_data_dir creates all missing ancestor directories."""
    base = tmp_path / "deep" / "nested" / "base"

    with patch.object(app_dirs_module, "_resolve_base_dir", return_value=base):
        result = get_data_dir(app_name="myapp")

    assert result.is_dir()


# ---------------------------------------------------------------------------
# get_log_dir
# ---------------------------------------------------------------------------


def test_get_log_dir_returns_logs_subdirectory(tmp_path: Path) -> None:
    """get_log_dir returns {rbcopy_data_dir}/logs/."""
    base = tmp_path / "base"

    with patch.object(app_dirs_module, "_resolve_base_dir", return_value=base):
        result = get_log_dir()

    assert result == base / "rbcopy" / "logs"


def test_get_log_dir_creates_directory(tmp_path: Path) -> None:
    """get_log_dir creates the logs subdirectory if it does not exist."""
    base = tmp_path / "base"

    with patch.object(app_dirs_module, "_resolve_base_dir", return_value=base):
        result = get_log_dir()

    assert result.is_dir()


# ---------------------------------------------------------------------------
# set_data_dir
# ---------------------------------------------------------------------------


def test_set_data_dir_writes_bootstrap_file(tmp_path: Path) -> None:
    """set_data_dir writes the configured path to the bootstrap file."""
    bootstrap = tmp_path / ".gl_tools_location"
    new_dir = tmp_path / "custom_data"

    with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
        result = set_data_dir(new_dir)

    assert result is True
    data = json.loads(bootstrap.read_text(encoding="utf-8"))
    assert data["data_dir"] == str(new_dir)


def test_set_data_dir_returns_false_on_write_failure(tmp_path: Path) -> None:
    """set_data_dir returns False when the bootstrap file cannot be written."""
    bootstrap = tmp_path / ".gl_tools_location"

    with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
        with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            result = set_data_dir(tmp_path / "new_dir")

    assert result is False


def test_set_data_dir_then_get_data_dir_round_trip(tmp_path: Path) -> None:
    """set_data_dir followed by get_data_dir returns the configured path / app_name."""
    bootstrap = tmp_path / ".gl_tools_location"
    new_base = tmp_path / "my_custom_base"

    with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
        with patch.object(app_dirs_module, "_u_drive_exists", return_value=False):
            set_data_dir(new_base)
            result = get_data_dir(app_name="rbcopy")

    assert result == new_base / "rbcopy"


# ---------------------------------------------------------------------------
# clear_data_dir
# ---------------------------------------------------------------------------


def test_clear_data_dir_removes_bootstrap_file(tmp_path: Path) -> None:
    """clear_data_dir removes the bootstrap pointer file."""
    bootstrap = tmp_path / ".gl_tools_location"
    bootstrap.write_text(json.dumps({"data_dir": str(tmp_path)}), encoding="utf-8")

    with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
        result = clear_data_dir()

    assert result is True
    assert not bootstrap.exists()


def test_clear_data_dir_returns_true_when_file_absent(tmp_path: Path) -> None:
    """clear_data_dir is a no-op (and returns True) when no bootstrap file exists."""
    bootstrap = tmp_path / ".gl_tools_location_nonexistent"

    with patch.object(app_dirs_module, "_BOOTSTRAP_PATH", bootstrap):
        result = clear_data_dir()

    assert result is True


def test_clear_data_dir_returns_false_on_unlink_failure(tmp_path: Path) -> None:
    """clear_data_dir returns False when unlink raises OSError."""
    bootstrap = tmp_path / ".gl_tools_location"
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
    probe_files = list(target.glob(".gl_tools_write_test"))
    assert probe_files == []


def test_validate_data_dir_returns_error_on_unresolvable_path(tmp_path: Path) -> None:
    """validate_data_dir returns an error string when path.resolve() raises."""
    with patch("pathlib.Path.resolve", side_effect=OSError("bad path")):
        result = validate_data_dir(tmp_path / "test_path")
    assert result is not None
    assert "Invalid path" in result


def test_validate_data_dir_continues_when_home_resolve_fails(tmp_path: Path) -> None:
    """validate_data_dir skips the home-dir check if Path.home().resolve() raises."""
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
