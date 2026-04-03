"""Tests for RobocopyGUI (rbcopy.gui.main_window)."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import tkinter as tk
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rbcopy.gui import RobocopyGUI
from tests.helpers import make_fake_self as _make_fake_self, make_mock_async_proc

# ---------------------------------------------------------------------------
# Menu structure tests
# ---------------------------------------------------------------------------


def test_build_menu_method_exists() -> None:
    """RobocopyGUI must expose a _build_menu method for the menu bar."""
    assert callable(RobocopyGUI._build_menu)


def test_props_only_var_initialized_before_build_ui() -> None:
    """_props_only_var must be set on self *at runtime* before _build_ui() is entered."""
    captured: list[bool] = []

    def spy_build_ui(self: Any) -> None:
        captured.append(hasattr(self, "_props_only_var"))

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

    assert captured == [True], "_props_only_var must be assigned before _build_ui() is called"


# ---------------------------------------------------------------------------
# _exit tests
# ---------------------------------------------------------------------------


def test_exit_method_exists() -> None:
    """RobocopyGUI must expose a callable _exit method."""
    assert callable(RobocopyGUI._exit)


def test_exit_terminates_running_process() -> None:
    """_exit must call terminate() on a live subprocess then destroy the window."""
    fake_self = _make_fake_self()
    mock_proc = MagicMock()
    mock_proc.returncode = None  # process is still running
    mock_proc.pid = 1234
    fake_self._current_proc = mock_proc

    RobocopyGUI._exit(fake_self)

    mock_proc.terminate.assert_called_once()
    fake_self.destroy.assert_called_once()


def test_exit_sets_shutdown_flag() -> None:
    """_exit must set the _shutdown event before destroying the window."""
    fake_self = _make_fake_self()
    fake_self._current_proc = None

    RobocopyGUI._exit(fake_self)

    assert fake_self._shutdown.is_set()
    fake_self.destroy.assert_called_once()


def test_exit_kills_process_on_timeout() -> None:
    """_exit must call kill() when the process does not exit within the timeout."""
    fake_self = _make_fake_self()
    mock_proc = MagicMock()
    mock_proc.returncode = None
    mock_proc.pid = 9999
    fake_self._current_proc = mock_proc

    # Replace proc_done_event with one that never gets set (simulates timeout).
    never_done = threading.Event()
    fake_self._proc_done_event = never_done

    with patch.object(never_done, "wait", return_value=False):
        RobocopyGUI._exit(fake_self)

    mock_proc.terminate.assert_called_once()
    mock_proc.kill.assert_called_once()
    fake_self.destroy.assert_called_once()


def test_exit_skips_terminate_when_process_finished() -> None:
    """_exit must NOT call terminate() when the subprocess has already exited."""
    fake_self = _make_fake_self()
    mock_proc = MagicMock()
    mock_proc.returncode = 0  # process already finished
    fake_self._current_proc = mock_proc

    RobocopyGUI._exit(fake_self)

    mock_proc.terminate.assert_not_called()
    fake_self.destroy.assert_called_once()


def test_exit_no_process() -> None:
    """_exit must only destroy the window when no subprocess was ever started."""
    fake_self = _make_fake_self()
    fake_self._current_proc = None

    RobocopyGUI._exit(fake_self)

    fake_self.destroy.assert_called_once()


def test_launch_creates_gui_and_calls_mainloop(monkeypatch: pytest.MonkeyPatch) -> None:
    """launch() should instantiate RobocopyGUI and call mainloop()."""
    import rbcopy.gui as gui_module

    mock_instance = MagicMock()
    mock_cls = MagicMock(return_value=mock_instance)
    monkeypatch.setattr(gui_module, "RobocopyGUI", mock_cls)
    # Prevent writing to the real AppData log directory and deleting real log files.
    monkeypatch.setattr(
        gui_module,
        "setup_logging",
        MagicMock(return_value=logging.getLogger("rbcopy._test_launch_stub")),
    )
    monkeypatch.setattr(gui_module, "rotate_logs", MagicMock())
    gui_module.launch()

    mock_cls.assert_called_once()
    mock_instance.mainloop.assert_called_once()


def test_launch_uses_configured_log_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """launch() must pass get_log_dir() to setup_logging() on every launch."""
    import rbcopy.gui as gui_module
    from rbcopy.app_dirs import get_log_dir

    monkeypatch.setattr(gui_module, "RobocopyGUI", MagicMock(return_value=MagicMock()))
    # Prevent rotate_logs from deleting real log files in the AppData directory.
    monkeypatch.setattr(gui_module, "rotate_logs", MagicMock())
    captured: list[Path] = []

    dummy_logger = logging.getLogger("rbcopy._test_launch_stub")

    def stubbed_setup(log_dir: Path | None = None) -> logging.Logger:
        captured.append(log_dir)
        return dummy_logger

    monkeypatch.setattr(gui_module, "setup_logging", stubbed_setup)
    gui_module.launch()

    assert len(captured) == 1
    assert captured[0] == get_log_dir(), (
        "launch() must pass get_log_dir() to setup_logging() — "
        "hardcoding '.rbcopy' or any other literal path is incorrect."
    )


# ---------------------------------------------------------------------------
# Window geometry persistence
# ---------------------------------------------------------------------------


def test_save_geometry_writes_file(tmp_path: Path) -> None:
    """_save_geometry must write the current geometry string to disk."""
    fake_self = _make_fake_self()
    fake_self.geometry.return_value = "800x600+100+200"

    with patch("rbcopy.gui.main_window._GEOMETRY_PATH", tmp_path / "geometry.json"):
        RobocopyGUI._save_geometry(fake_self)

    data = json.loads((tmp_path / "geometry.json").read_text(encoding="utf-8"))
    assert data["geometry"] == "800x600+100+200"


def test_save_geometry_creates_parent_directory(tmp_path: Path) -> None:
    """_save_geometry must create the parent directory if it does not exist."""
    fake_self = _make_fake_self()
    fake_self.geometry.return_value = "800x600+0+0"
    nested = tmp_path / "deep" / "nested" / "geometry.json"

    with patch("rbcopy.gui.main_window._GEOMETRY_PATH", nested):
        RobocopyGUI._save_geometry(fake_self)

    assert nested.exists()


def test_save_geometry_silent_on_oserror(tmp_path: Path) -> None:
    """_save_geometry must not raise when the disk write fails."""
    fake_self = _make_fake_self()
    fake_self.geometry.return_value = "800x600+0+0"

    with patch("rbcopy.gui.main_window._GEOMETRY_PATH", tmp_path / "geometry.json"):
        with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            # Must not raise.
            RobocopyGUI._save_geometry(fake_self)


def test_restore_geometry_applies_saved_value(tmp_path: Path) -> None:
    """_restore_geometry must call self.geometry() with the saved string."""
    fake_self = _make_fake_self()
    geometry_file = tmp_path / "geometry.json"
    geometry_file.write_text(json.dumps({"geometry": "1024x768+50+50"}), encoding="utf-8")

    with patch("rbcopy.gui.main_window._GEOMETRY_PATH", geometry_file):
        RobocopyGUI._restore_geometry(fake_self)

    fake_self.geometry.assert_called_once_with("1024x768+50+50")


def test_restore_geometry_silent_when_file_missing(tmp_path: Path) -> None:
    """_restore_geometry must do nothing when no geometry file exists."""
    fake_self = _make_fake_self()

    with patch("rbcopy.gui.main_window._GEOMETRY_PATH", tmp_path / "geometry.json"):
        RobocopyGUI._restore_geometry(fake_self)

    fake_self.geometry.assert_not_called()


def test_restore_geometry_silent_on_corrupt_file(tmp_path: Path) -> None:
    """_restore_geometry must not raise when the geometry file is corrupt."""
    fake_self = _make_fake_self()
    geometry_file = tmp_path / "geometry.json"
    geometry_file.write_text("not valid json", encoding="utf-8")

    with patch("rbcopy.gui.main_window._GEOMETRY_PATH", geometry_file):
        RobocopyGUI._restore_geometry(fake_self)

    fake_self.geometry.assert_not_called()


def test_restore_geometry_silent_when_geometry_key_missing(tmp_path: Path) -> None:
    """_restore_geometry must not raise when the geometry key is absent."""
    fake_self = _make_fake_self()
    geometry_file = tmp_path / "geometry.json"
    geometry_file.write_text(json.dumps({"other": "value"}), encoding="utf-8")

    with patch("rbcopy.gui.main_window._GEOMETRY_PATH", geometry_file):
        RobocopyGUI._restore_geometry(fake_self)

    fake_self.geometry.assert_not_called()


def test_exit_saves_geometry_before_destroying(tmp_path: Path) -> None:
    """_exit must call _save_geometry before destroying the window."""
    fake_self = _make_fake_self()
    fake_self._current_proc = None
    call_order: list[str] = []

    fake_self._save_geometry.side_effect = lambda: call_order.append("save")
    fake_self.destroy.side_effect = lambda: call_order.append("destroy")

    RobocopyGUI._exit(fake_self)

    assert call_order == ["save", "destroy"]


# ---------------------------------------------------------------------------
# Logger name regression test
# ---------------------------------------------------------------------------


def test_gui_module_logger_name_is_rbcopy_gui() -> None:
    """gui.py module-level logger must always be 'rbcopy.gui', NOT '__main__'.

    When gui.py is launched directly (e.g. 'python gui.py' or via pythonw.exe),
    __name__ == '__main__', so getLogger(__name__) would create a logger that
    propagates to the root logger instead of to 'rbcopy'.  That breaks log-file
    capture because the FileHandler is attached to 'rbcopy', not to root.
    Using the hard-coded name 'rbcopy.gui' ensures propagation is always correct.
    """
    import rbcopy.gui.main_window as gui_module

    assert gui_module.logger.name == "rbcopy.gui"
    assert gui_module.logger.name != "__main__"
    # Must be a descendant of the 'rbcopy' namespace logger.
    assert gui_module.logger.name.startswith("rbcopy.")


def test_execute_writes_output_to_log_file(log_dir: Path) -> None:
    """_async_execute must mirror every robocopy stdout line to the log file."""
    sample_output = "   Source : C:\\src\\\n   Dest : C:\\dst\\\n   New File   test.txt\n"
    fake_self = _make_fake_self()
    mock_proc = make_mock_async_proc(returncode=1, output=sample_output, pid=1234)

    with patch("rbcopy.gui.main_window.asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        with patch("rbcopy.gui.main_window.notify_job_complete"):
            asyncio.run(RobocopyGUI._async_execute(fake_self, ["robocopy", "C:/src", "C:/dst"]))

    for h in logging.getLogger("rbcopy").handlers:
        h.flush()

    log_file = next(log_dir.glob("robocopy_job_*.log"))
    content = log_file.read_text(encoding="utf-8")
    assert "Source : C:\\src\\" in content
    assert "Dest : C:\\dst\\" in content
    assert "New File   test.txt" in content
    assert "exit code 1" in content


# launch() – pre-configured logging warning
# ---------------------------------------------------------------------------


def test_launch_warns_when_log_dir_differs_from_requested(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """launch() logs a warning when the active FileHandler writes to a different directory."""
    import logging

    import rbcopy.gui as gui_module

    monkeypatch.setattr(gui_module, "RobocopyGUI", MagicMock(return_value=MagicMock()))

    # Build a logger with a FileHandler pointing to a directory that is NOT ~/.rbcopy.
    other_log_file = tmp_path / "other_dir" / "session.log"
    other_log_file.parent.mkdir()
    other_log_file.touch()
    handler = logging.FileHandler(str(other_log_file))
    dummy_logger = logging.getLogger("rbcopy._test_launch_diff_dir")
    dummy_logger.addHandler(handler)

    try:

        def stubbed_setup(log_dir: Path | None = None) -> logging.Logger:
            return dummy_logger

        monkeypatch.setattr(gui_module, "setup_logging", stubbed_setup)

        with caplog.at_level(logging.WARNING, logger="rbcopy.gui"):
            gui_module.launch()

    finally:
        handler.close()
        dummy_logger.removeHandler(handler)

    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("already configured" in msg.lower() for msg in warning_messages)


def test_stop_method_exists() -> None:
    """RobocopyGUI must expose a callable _stop method."""
    assert callable(RobocopyGUI._stop)


def test_stop_terminates_running_process() -> None:
    """_stop must call terminate() on the live subprocess."""
    fake_self = _make_fake_self()
    mock_proc = MagicMock()
    mock_proc.returncode = None  # still running
    mock_proc.pid = 1234
    fake_self._current_proc = mock_proc

    RobocopyGUI._stop(fake_self)

    mock_proc.terminate.assert_called_once()


def test_stop_does_nothing_when_no_process() -> None:
    """_stop must be a no-op when no job is running."""
    fake_self = _make_fake_self()
    fake_self._current_proc = None

    # Should not raise
    RobocopyGUI._stop(fake_self)


def test_stop_does_nothing_when_process_already_finished() -> None:
    """_stop must not call terminate() when the process has already exited."""
    fake_self = _make_fake_self()
    mock_proc = MagicMock()
    mock_proc.returncode = 0  # already done
    fake_self._current_proc = mock_proc

    RobocopyGUI._stop(fake_self)

    mock_proc.terminate.assert_not_called()


def test_set_run_buttons_state_disables_stop_when_normal() -> None:
    """When state='normal', the Stop button should be disabled."""
    fake_self = _make_fake_self()

    RobocopyGUI._set_run_buttons_state(fake_self, "normal")

    # Verify Stop button got "disabled"
    stop_calls = [
        call for call in fake_self._btn_stop.configure.call_args_list if call.kwargs.get("state") == "disabled"
    ]
    assert stop_calls


def test_set_run_buttons_state_enables_stop_when_disabled() -> None:
    """When state='disabled' (job running), the Stop button should be enabled."""
    fake_self = _make_fake_self()

    RobocopyGUI._set_run_buttons_state(fake_self, "disabled")

    stop_calls = [call for call in fake_self._btn_stop.configure.call_args_list if call.kwargs.get("state") == "normal"]
    assert stop_calls


# ---------------------------------------------------------------------------
# _init_dnd tests
# ---------------------------------------------------------------------------


def test_init_dnd_method_exists() -> None:
    """RobocopyGUI must expose a callable _init_dnd method."""
    assert callable(RobocopyGUI._init_dnd)


def test_init_dnd_is_noop_when_tkinterdnd2_missing() -> None:
    """_init_dnd must not raise when tkinterdnd2 is not installed."""
    fake_self = _make_fake_self()

    with patch.dict("sys.modules", {"tkinterdnd2": None}):
        RobocopyGUI._init_dnd(fake_self)  # Must not raise.


def test_init_dnd_calls_setup_entry_drop_for_both_entries() -> None:
    """_init_dnd registers DnD on both _src_entry and _dst_entry when TkDND loads."""
    fake_self = _make_fake_self()
    mock_tkinterdnd2 = MagicMock()

    with patch.dict("sys.modules", {"tkinterdnd2": mock_tkinterdnd2}):
        with patch("rbcopy.gui.dnd.setup_entry_drop") as mock_setup:
            mock_setup.return_value = True
            RobocopyGUI._init_dnd(fake_self)

    assert mock_setup.call_count == 2
    called_entries = {call.args[0] for call in mock_setup.call_args_list}
    assert fake_self._src_entry in called_entries
    assert fake_self._dst_entry in called_entries


def test_init_dnd_passes_correct_string_vars() -> None:
    """_init_dnd passes src_var to _src_entry and dst_var to _dst_entry."""
    fake_self = _make_fake_self()
    mock_tkinterdnd2 = MagicMock()

    with patch.dict("sys.modules", {"tkinterdnd2": mock_tkinterdnd2}):
        with patch("rbcopy.gui.dnd.setup_entry_drop") as mock_setup:
            mock_setup.return_value = True
            RobocopyGUI._init_dnd(fake_self)

    calls = mock_setup.call_args_list
    src_call = next(c for c in calls if c.args[0] is fake_self._src_entry)
    dst_call = next(c for c in calls if c.args[0] is fake_self._dst_entry)
    assert src_call.args[1] is fake_self.src_var
    assert dst_call.args[1] is fake_self.dst_var


def test_init_dnd_is_noop_when_require_raises() -> None:
    """_init_dnd must not raise when TkinterDnD._require fails."""
    fake_self = _make_fake_self()
    mock_tkinterdnd2 = MagicMock()
    mock_tkinterdnd2.TkinterDnD._require.side_effect = Exception("TkDND not found")

    with patch.dict("sys.modules", {"tkinterdnd2": mock_tkinterdnd2}):
        with patch("rbcopy.gui.dnd.setup_entry_drop") as mock_setup:
            RobocopyGUI._init_dnd(fake_self)  # Must not raise.

    mock_setup.assert_not_called()


def test_init_dnd_configures_hover_style() -> None:
    """_init_dnd registers a DnDActive.TEntry style when TkDND initialises successfully."""
    fake_self = _make_fake_self()
    mock_tkinterdnd2 = MagicMock()

    with patch.dict("sys.modules", {"tkinterdnd2": mock_tkinterdnd2}):
        with patch("rbcopy.gui.dnd.setup_entry_drop", return_value=True):
            with patch("rbcopy.gui.main_window.ttk.Style") as mock_style_cls:
                mock_style = MagicMock()
                mock_style_cls.return_value = mock_style
                RobocopyGUI._init_dnd(fake_self)

    configure_calls = mock_style.configure.call_args_list
    style_names = [c.args[0] for c in configure_calls if c.args]
    assert "DnDActive.TEntry" in style_names


# ---------------------------------------------------------------------------
# Preferences – _apply_preferences
# ---------------------------------------------------------------------------


def test_apply_preferences_method_exists() -> None:
    """RobocopyGUI must expose a callable _apply_preferences method."""
    assert callable(RobocopyGUI._apply_preferences)


def test_open_preferences_method_exists() -> None:
    """RobocopyGUI must expose a callable _open_preferences method."""
    assert callable(RobocopyGUI._open_preferences)


def test_apply_preferences_sets_mt_value() -> None:
    """_apply_preferences writes the thread count preference to the /MT value var."""
    from rbcopy.preferences import AppPreferences, PreferencesStore

    fake_self = _make_fake_self()
    mt_value_var = MagicMock()
    fake_self._param_vars = {"/MT": (MagicMock(), mt_value_var, MagicMock())}
    fake_self._prefs_store = MagicMock(spec=PreferencesStore)
    fake_self._prefs_store.preferences.return_value = AppPreferences(default_thread_count=32)
    fake_self._prefs_store.preferences = AppPreferences(default_thread_count=32)

    RobocopyGUI._apply_preferences(fake_self)

    mt_value_var.set.assert_called_once_with("32")


def test_apply_preferences_sets_r_value() -> None:
    """_apply_preferences writes the retry count preference to the /R value var."""
    from rbcopy.preferences import AppPreferences, PreferencesStore

    fake_self = _make_fake_self()
    r_value_var = MagicMock()
    fake_self._param_vars = {"/R": (MagicMock(), r_value_var, MagicMock())}
    fake_self._prefs_store = MagicMock(spec=PreferencesStore)
    fake_self._prefs_store.preferences = AppPreferences(default_retry_count=3)

    RobocopyGUI._apply_preferences(fake_self)

    r_value_var.set.assert_called_once_with("3")


def test_apply_preferences_sets_w_value() -> None:
    """_apply_preferences writes the wait seconds preference to the /W value var."""
    from rbcopy.preferences import AppPreferences, PreferencesStore

    fake_self = _make_fake_self()
    w_value_var = MagicMock()
    fake_self._param_vars = {"/W": (MagicMock(), w_value_var, MagicMock())}
    fake_self._prefs_store = MagicMock(spec=PreferencesStore)
    fake_self._prefs_store.preferences = AppPreferences(default_wait_seconds=10)

    RobocopyGUI._apply_preferences(fake_self)

    w_value_var.set.assert_called_once_with("10")


def test_apply_preferences_ignores_missing_flags() -> None:
    """_apply_preferences must not raise when a flag is absent from _param_vars."""
    from rbcopy.preferences import AppPreferences, PreferencesStore

    fake_self = _make_fake_self()
    fake_self._param_vars = {}  # no /MT, /R, /W entries
    fake_self._prefs_store = MagicMock(spec=PreferencesStore)
    fake_self._prefs_store.preferences = AppPreferences()

    RobocopyGUI._apply_preferences(fake_self)  # must not raise


def test_open_preferences_opens_dialog() -> None:
    """_open_preferences must open a _PreferencesDialog with self and the store."""
    from rbcopy.preferences import PreferencesStore

    fake_self = _make_fake_self()
    fake_self._prefs_store = MagicMock(spec=PreferencesStore)

    with patch("rbcopy.gui.main_window._PreferencesDialog") as mock_dialog:
        RobocopyGUI._open_preferences(fake_self)

    mock_dialog.assert_called_once_with(
        parent=fake_self,
        store=fake_self._prefs_store,
        on_saved=fake_self._apply_preferences,
        on_clear_history=fake_self._clear_path_history,
        on_clear_bookmarks=fake_self._clear_bookmarks,
    )


# ---------------------------------------------------------------------------
