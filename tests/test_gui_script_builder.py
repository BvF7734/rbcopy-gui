"""Tests for _ScriptExportDialog (rbcopy.gui.script_builder)."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from rbcopy.gui import RobocopyGUI
from tests.helpers import make_fake_self as _make_fake_self

# ---------------------------------------------------------------------------
# _ScriptExportDialog._on_save tests
# ---------------------------------------------------------------------------


def _make_fake_dialog(tmp_path: Path) -> MagicMock:
    """Return a MagicMock suitable as a fake 'self' for _ScriptExportDialog methods."""
    fake: MagicMock = MagicMock()
    fake._cmd = ["robocopy", "C:/src", "C:/dst", "/MIR"]
    fake._type_var.get.return_value = "batch"
    fake._name_var.get.return_value = "my_script"
    fake._dir_var.get.return_value = str(tmp_path)
    return fake


def test_on_save_writes_batch_file(tmp_path: Path) -> None:
    """_on_save must write a .bat file when script type is 'batch'."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)

    with patch("rbcopy.gui.script_builder.messagebox.showinfo"):
        _ScriptExportDialog._on_save(fake)

    out_path = tmp_path / "my_script.bat"
    assert out_path.exists(), "Expected .bat file to be written"
    content = out_path.read_text(encoding="utf-8")
    assert "@echo off" in content
    assert "robocopy" in content


def test_on_save_writes_powershell_file(tmp_path: Path) -> None:
    """_on_save must write a .ps1 file when script type is 'powershell'."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._type_var.get.return_value = "powershell"

    with patch("rbcopy.gui.script_builder.messagebox.showinfo"):
        _ScriptExportDialog._on_save(fake)

    out_path = tmp_path / "my_script.ps1"
    assert out_path.exists(), "Expected .ps1 file to be written"
    content = out_path.read_text(encoding="utf-8")
    assert "exit $exitCode" in content
    assert "robocopy" in content


def test_on_save_adds_bat_extension_when_missing(tmp_path: Path) -> None:
    """_on_save must append .bat when the user omits the extension for batch type."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._name_var.get.return_value = "my_script"  # no extension

    with patch("rbcopy.gui.script_builder.messagebox.showinfo"):
        _ScriptExportDialog._on_save(fake)

    assert (tmp_path / "my_script.bat").exists()


def test_on_save_adds_ps1_extension_when_missing(tmp_path: Path) -> None:
    """_on_save must append .ps1 when the user omits the extension for powershell type."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._type_var.get.return_value = "powershell"
    fake._name_var.get.return_value = "my_script"  # no extension

    with patch("rbcopy.gui.script_builder.messagebox.showinfo"):
        _ScriptExportDialog._on_save(fake)

    assert (tmp_path / "my_script.ps1").exists()


def test_on_save_preserves_bat_extension(tmp_path: Path) -> None:
    """_on_save must not add a second extension when the user already provided .bat."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._name_var.get.return_value = "my_script.bat"

    with patch("rbcopy.gui.script_builder.messagebox.showinfo"):
        _ScriptExportDialog._on_save(fake)

    assert (tmp_path / "my_script.bat").exists()
    assert not (tmp_path / "my_script.bat.bat").exists()


def test_on_save_preserves_cmd_extension(tmp_path: Path) -> None:
    """_on_save must not add .bat when the user already provided .cmd."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._name_var.get.return_value = "my_script.cmd"

    with patch("rbcopy.gui.script_builder.messagebox.showinfo"):
        _ScriptExportDialog._on_save(fake)

    assert (tmp_path / "my_script.cmd").exists()
    assert not (tmp_path / "my_script.cmd.bat").exists()


def test_on_save_shows_warning_when_name_empty(tmp_path: Path) -> None:
    """_on_save must show a warning and not write any file when file name is empty."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._name_var.get.return_value = ""

    with patch("rbcopy.gui.script_builder.messagebox.showwarning") as mock_warn:
        _ScriptExportDialog._on_save(fake)

    mock_warn.assert_called_once()
    # The temporary directory must remain empty – no file was written.
    assert not any(tmp_path.iterdir())


def test_on_save_shows_warning_when_directory_empty(tmp_path: Path) -> None:
    """_on_save must show a warning and not write any file when location is empty."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._dir_var.get.return_value = ""

    with patch("rbcopy.gui.script_builder.messagebox.showwarning") as mock_warn:
        _ScriptExportDialog._on_save(fake)

    mock_warn.assert_called_once()


def test_on_save_shows_error_on_write_failure(tmp_path: Path) -> None:
    """_on_save must show an error dialog when the file cannot be written."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)

    with (
        patch("rbcopy.gui.script_builder.messagebox.showerror") as mock_error,
        patch("rbcopy.gui.script_builder.Path.write_text", side_effect=OSError("disk full")),
    ):
        _ScriptExportDialog._on_save(fake)

    mock_error.assert_called_once()
    args = mock_error.call_args.args
    assert "disk full" in args[1]


def test_on_save_sets_saved_flag_on_success(tmp_path: Path) -> None:
    """_on_save must set self._saved = True when the file is written successfully."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)

    with patch("rbcopy.gui.script_builder.messagebox.showinfo"):
        _ScriptExportDialog._on_save(fake)

    assert fake._saved is True


def test_on_save_does_not_set_saved_flag_on_empty_name(tmp_path: Path) -> None:
    """_on_save must NOT set self._saved when validation fails (empty name)."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._name_var.get.return_value = ""
    fake._saved = False  # explicitly set initial state

    with patch("rbcopy.gui.script_builder.messagebox.showwarning"):
        _ScriptExportDialog._on_save(fake)

    assert fake._saved is False


def test_on_save_shows_error_on_unknown_script_type(tmp_path: Path) -> None:
    """_on_save must show an error and write no file when script type is unknown."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._type_var.get.return_value = "unknown_type"
    fake._saved = False

    with patch("rbcopy.gui.script_builder.messagebox.showerror") as mock_error:
        _ScriptExportDialog._on_save(fake)

    mock_error.assert_called_once()
    assert not any(tmp_path.iterdir()), "No file should be written for an unknown type"
    assert fake._saved is False


def test_on_save_rejects_parent_traversal_in_name(tmp_path: Path) -> None:
    """_on_save must show a warning and write no file when the name contains a parent reference."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._name_var.get.return_value = "../evil"
    fake._saved = False

    with (
        patch("rbcopy.gui.script_builder.messagebox.showwarning") as mock_warn,
    ):
        _ScriptExportDialog._on_save(fake)

    mock_warn.assert_called_once()
    assert not any(tmp_path.iterdir()), "No file should be written for a name with parent traversal"
    assert fake._saved is False


def test_on_save_rejects_subdirectory_in_name(tmp_path: Path) -> None:
    """_on_save must show a warning and write no file when the name contains a subdirectory."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._name_var.get.return_value = "subdir/script"
    fake._saved = False

    with (
        patch("rbcopy.gui.script_builder.messagebox.showwarning") as mock_warn,
    ):
        _ScriptExportDialog._on_save(fake)

    mock_warn.assert_called_once()
    assert not any(tmp_path.iterdir()), "No file should be written for a name with a subdirectory component"
    assert fake._saved is False

# ---------------------------------------------------------------------------
# Script Builder – _script_builder_var initialisation
# ---------------------------------------------------------------------------


def test_script_builder_var_initialized_before_build_ui() -> None:
    """_script_builder_var must be set on self *at runtime* before _build_ui() is entered."""
    captured: list[bool] = []

    def spy_build_ui(self: Any) -> None:
        captured.append(hasattr(self, "_script_builder_var"))

    with (
        patch.object(tk.Tk, "__init__", return_value=None),
        patch.object(tk.Tk, "title"),
        patch.object(tk.Tk, "resizable"),
        patch.object(tk.Tk, "minsize"),
        patch.object(tk.Tk, "protocol"),
        patch("rbcopy.gui.main_window.ttk.Style"),
        patch("rbcopy.gui.main_window.tk.BooleanVar"),
        patch("rbcopy.gui.main_window.tk.StringVar"),
        patch.object(RobocopyGUI, "_build_ui", spy_build_ui),
        patch.object(RobocopyGUI, "_apply_preferences"),
        patch.object(RobocopyGUI, "_init_dnd"),
        patch.object(RobocopyGUI, "_poll_output"),
        patch.object(RobocopyGUI, "_restore_geometry"),
    ):
        RobocopyGUI()

    assert captured == [True], "_script_builder_var must be assigned before _build_ui() is called"


def test_file_filter_vars_initialized_before_build_ui() -> None:
    """_file_filter_enabled_var and _file_filter_var must be set before _build_ui() is entered."""
    captured: list[bool] = []

    def spy_build_ui(self: Any) -> None:
        captured.append(hasattr(self, "_file_filter_enabled_var") and hasattr(self, "_file_filter_var"))

    with (
        patch.object(tk.Tk, "__init__", return_value=None),
        patch.object(tk.Tk, "title"),
        patch.object(tk.Tk, "resizable"),
        patch.object(tk.Tk, "minsize"),
        patch.object(tk.Tk, "protocol"),
        patch("rbcopy.gui.main_window.ttk.Style"),
        patch("rbcopy.gui.main_window.tk.BooleanVar"),
        patch("rbcopy.gui.main_window.tk.StringVar"),
        patch.object(RobocopyGUI, "_build_ui", spy_build_ui),
        patch.object(RobocopyGUI, "_apply_preferences"),
        patch.object(RobocopyGUI, "_init_dnd"),
        patch.object(RobocopyGUI, "_poll_output"),
        patch.object(RobocopyGUI, "_restore_geometry"),
    ):
        RobocopyGUI()

    assert captured == [True], "_file_filter vars must be assigned before _build_ui() is called"


# ---------------------------------------------------------------------------
# Script Builder – _run behaviour
# ---------------------------------------------------------------------------


def test_run_calls_export_script_when_script_builder_enabled() -> None:
    """_run must call _export_script (not start a thread) when Script Builder is on."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self()
    fake_self._build_command.return_value = ["robocopy", "C:/src", "C:/dst"]
    fake_self._script_builder_var.get.return_value = True

    with patch("rbcopy.gui.main_window.validate_command", return_value=DryRunResult(ok=True)):
        with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
            RobocopyGUI._run(fake_self)

    mock_thread_cls.assert_not_called()
    fake_self._export_script.assert_called_once_with(["robocopy", "C:/src", "C:/dst"])


def test_run_does_not_call_export_script_when_script_builder_disabled() -> None:
    """_run must start a thread (not call _export_script) when Script Builder is off."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self()
    fake_self._build_command.return_value = ["robocopy", "C:/src", "C:/dst"]

    with patch("rbcopy.gui.main_window.validate_command", return_value=DryRunResult(ok=True)):
        with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            RobocopyGUI._run(fake_self)

    mock_thread_cls.assert_called_once()
    fake_self._export_script.assert_not_called()


# ---------------------------------------------------------------------------
# Script Builder – _export_script
# ---------------------------------------------------------------------------


def test_export_script_opens_dialog() -> None:
    """_export_script must open a _ScriptExportDialog with self and the command."""
    fake_self = _make_fake_self()
    cmd = ["robocopy", "C:/src", "C:/dst"]

    with patch("rbcopy.gui.main_window._ScriptExportDialog") as mock_dialog:
        RobocopyGUI._export_script(fake_self, cmd)

    mock_dialog.assert_called_once_with(fake_self, cmd)


