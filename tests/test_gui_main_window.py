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
from rbcopy.gui.main_window import _SavePresetDialog, _ToolTip, _PresetDropdownTooltip
from tests.helpers import make_fake_self as _make_fake_self, make_mock_async_proc, StringVarStub

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

# ---------------------------------------------------------------------------
# _ToolTip tests (lines 199-230)
# ---------------------------------------------------------------------------


def _make_tooltip_stub(text: str = "tip text") -> _ToolTip:
    """Return a _ToolTip whose widget is a MagicMock (no live Tk needed)."""
    tip: _ToolTip = object.__new__(_ToolTip)
    tip._widget = MagicMock()
    tip._text = text
    tip._tip_window = None
    tip._after_id = None
    return tip


def test_tooltip_schedule_sets_after_id() -> None:
    """_ToolTip._schedule cancels any pending callback then schedules a new one."""
    tip = _make_tooltip_stub()
    tip._widget.after.return_value = "after_id_42"

    tip._schedule(MagicMock())

    tip._widget.after.assert_called_once_with(tip._DELAY_MS, tip._show)
    assert tip._after_id == "after_id_42"


def test_tooltip_cancel_with_after_id_cancels_and_clears() -> None:
    """_ToolTip._cancel calls after_cancel when _after_id is set and then clears it."""
    tip = _make_tooltip_stub()
    tip._after_id = "pending_id"

    tip._cancel(None)

    tip._widget.after_cancel.assert_called_once_with("pending_id")
    assert tip._after_id is None


def test_tooltip_cancel_without_after_id_does_not_call_after_cancel() -> None:
    """_ToolTip._cancel must not call after_cancel when _after_id is None."""
    tip = _make_tooltip_stub()
    tip._after_id = None

    tip._cancel(None)

    tip._widget.after_cancel.assert_not_called()


def test_tooltip_show_creates_toplevel_window() -> None:
    """_ToolTip._show creates a Toplevel window and assigns it to _tip_window."""
    tip = _make_tooltip_stub()
    tip._widget.winfo_rootx.return_value = 100
    tip._widget.winfo_rooty.return_value = 200
    tip._widget.winfo_height.return_value = 30

    mock_tw = MagicMock()
    mock_label = MagicMock()
    with (
        patch("rbcopy.gui.main_window.tk.Toplevel", return_value=mock_tw),
        patch("rbcopy.gui.main_window.tk.Label", return_value=mock_label),
    ):
        tip._show()

    assert tip._tip_window is mock_tw
    mock_tw.wm_overrideredirect.assert_called_once_with(True)
    mock_label.pack.assert_called_once()


def test_tooltip_show_skips_when_already_showing() -> None:
    """_ToolTip._show must be a no-op when _tip_window is already set."""
    tip = _make_tooltip_stub()
    tip._tip_window = MagicMock()  # already showing

    with patch("rbcopy.gui.main_window.tk.Toplevel") as mock_toplevel:
        tip._show()

    mock_toplevel.assert_not_called()


def test_tooltip_hide_destroys_window_and_clears() -> None:
    """_ToolTip._hide destroys the tip window and sets _tip_window to None."""
    tip = _make_tooltip_stub()
    mock_tw = MagicMock()
    tip._tip_window = mock_tw

    tip._hide()

    mock_tw.destroy.assert_called_once()
    assert tip._tip_window is None


def test_tooltip_hide_does_nothing_when_no_window() -> None:
    """_ToolTip._hide must be a no-op when _tip_window is already None."""
    tip = _make_tooltip_stub()
    tip._tip_window = None  # nothing to destroy
    # Should not raise
    tip._hide()


# ---------------------------------------------------------------------------
# launch() – High-DPI awareness failure
# ---------------------------------------------------------------------------


def test_launch_continues_when_dpi_awareness_raises_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    """launch() must not raise and must still start the GUI when SetProcessDpiAwareness raises OSError."""
    import ctypes

    import rbcopy.gui as gui_module

    mock_windll = MagicMock()
    mock_windll.shcore.SetProcessDpiAwareness.side_effect = OSError("not supported on this platform")
    # raising=False allows the patch to succeed even on platforms that lack windll.
    monkeypatch.setattr(ctypes, "windll", mock_windll, raising=False)

    mock_instance = MagicMock()
    monkeypatch.setattr(gui_module, "RobocopyGUI", MagicMock(return_value=mock_instance))
    monkeypatch.setattr(
        gui_module,
        "setup_logging",
        MagicMock(return_value=logging.getLogger("rbcopy._test_dpi_oserror")),
    )
    monkeypatch.setattr(gui_module, "rotate_logs", MagicMock())

    # Must not raise despite the DPI awareness failure.
    gui_module.launch()

    mock_instance.mainloop.assert_called_once()


# ---------------------------------------------------------------------------
# _PresetDropdownTooltip tests (lines 260-309)
# ---------------------------------------------------------------------------


def _make_preset_tooltip() -> _PresetDropdownTooltip:
    """Return a _PresetDropdownTooltip with mocked combo (no live Tk needed)."""
    tip: _PresetDropdownTooltip = object.__new__(_PresetDropdownTooltip)
    tip._combo = MagicMock()
    tip._get_descriptions = MagicMock(return_value={"Alpha": "desc for alpha", "Beta": ""})
    tip._tip_window = None
    return tip


def test_preset_tooltip_on_opened_binds_motion_on_listbox() -> None:
    """_on_opened successfully finds the listbox and binds <Motion>."""
    tip = _make_preset_tooltip()
    mock_lb = MagicMock()
    tip._combo.tk.eval.return_value = ".popdown"
    tip._combo.nametowidget.return_value = mock_lb

    tip._on_opened(MagicMock())

    mock_lb.bind.assert_any_call("<Motion>", tip._on_motion)


def test_preset_tooltip_on_opened_silences_exception() -> None:
    """_on_opened must not propagate exceptions from the Tk internals."""
    tip = _make_preset_tooltip()
    tip._combo.tk.eval.side_effect = Exception("no popdown")

    # Should not raise.
    tip._on_opened(MagicMock())


def test_preset_tooltip_on_motion_shows_description_for_valid_index() -> None:
    """_on_motion calls _show when the hovered index has a non-empty description."""
    tip = _make_preset_tooltip()
    tip._combo.__getitem__ = MagicMock(return_value=("Alpha", "Beta"))

    event = MagicMock()
    event.widget.nearest.return_value = 0
    event.x_root = 300
    event.y_root = 400

    with patch.object(tip, "_show") as mock_show, patch.object(tip, "_hide") as mock_hide:
        tip._on_motion(event)

    mock_show.assert_called_once_with(300, 400, "desc for alpha")
    mock_hide.assert_not_called()


def test_preset_tooltip_on_motion_hides_when_no_description() -> None:
    """_on_motion calls _hide when the hovered item has no description."""
    tip = _make_preset_tooltip()
    tip._combo.__getitem__ = MagicMock(return_value=("Beta",))

    event = MagicMock()
    event.widget.nearest.return_value = 0

    with patch.object(tip, "_show") as mock_show, patch.object(tip, "_hide") as mock_hide:
        tip._on_motion(event)

    mock_hide.assert_called_once()
    mock_show.assert_not_called()


def test_preset_tooltip_on_motion_hides_when_index_out_of_range() -> None:
    """_on_motion calls _hide when the index is out of range."""
    tip = _make_preset_tooltip()
    tip._combo.__getitem__ = MagicMock(return_value=())

    event = MagicMock()
    event.widget.nearest.return_value = 5  # beyond empty list

    with patch.object(tip, "_hide") as mock_hide:
        tip._on_motion(event)

    mock_hide.assert_called_once()


def test_preset_tooltip_show_creates_toplevel() -> None:
    """_PresetDropdownTooltip._show creates a Toplevel window with the given text."""
    tip = _make_preset_tooltip()
    mock_tw = MagicMock()
    mock_label = MagicMock()
    with (
        patch("rbcopy.gui.main_window.tk.Toplevel", return_value=mock_tw),
        patch("rbcopy.gui.main_window.tk.Label", return_value=mock_label),
    ):
        tip._show(100, 200, "hello")

    assert tip._tip_window is mock_tw
    mock_label.pack.assert_called_once()


def test_preset_tooltip_show_skips_when_same_text_already_showing() -> None:
    """_show must be a no-op when the tooltip already shows the same text."""
    tip = _make_preset_tooltip()
    mock_child = MagicMock()
    mock_child.cget.return_value = "same text"
    mock_tw = MagicMock()
    mock_tw.winfo_children.return_value = [mock_child]
    tip._tip_window = mock_tw

    with patch("rbcopy.gui.main_window.tk.Toplevel") as mock_toplevel:
        tip._show(0, 0, "same text")

    mock_toplevel.assert_not_called()


def test_preset_tooltip_hide_destroys_window() -> None:
    """_PresetDropdownTooltip._hide destroys the tip window and clears the reference."""
    tip = _make_preset_tooltip()
    mock_tw = MagicMock()
    tip._tip_window = mock_tw

    tip._hide()

    mock_tw.destroy.assert_called_once()
    assert tip._tip_window is None


# ---------------------------------------------------------------------------
# _SavePresetDialog tests (lines 324-379)
# ---------------------------------------------------------------------------


def _make_save_preset_dialog_stub(name: str = "", desc: str = "") -> _SavePresetDialog:
    """Return a _SavePresetDialog bypassing __init__ (no live Tk needed)."""
    dlg: _SavePresetDialog = object.__new__(_SavePresetDialog)
    dlg._name_var = StringVarStub(name)
    dlg._desc_var = StringVarStub(desc)
    dlg._confirmed = False
    # Minimal Toplevel stubs so destroy() / showwarning() calls don't raise.
    dlg.destroy = MagicMock()  # type: ignore[assignment]
    return dlg


def test_save_preset_dialog_name_property_returns_none_when_not_confirmed() -> None:
    """_SavePresetDialog.name returns None when the dialog was not confirmed."""
    dlg = _make_save_preset_dialog_stub(name="MyPreset")
    assert dlg.name is None


def test_save_preset_dialog_name_property_returns_stripped_name_when_confirmed() -> None:
    """_SavePresetDialog.name returns the stripped name after confirmation."""
    dlg = _make_save_preset_dialog_stub(name="  MyPreset  ")
    dlg._confirmed = True
    assert dlg.name == "MyPreset"


def test_save_preset_dialog_description_property_returns_stripped_desc() -> None:
    """_SavePresetDialog.description always returns the stripped description."""
    dlg = _make_save_preset_dialog_stub(desc="  My description  ")
    assert dlg.description == "My description"


def test_save_preset_dialog_ok_confirms_and_destroys_when_name_set() -> None:
    """_ok sets _confirmed = True and calls destroy() when a name is entered."""
    dlg = _make_save_preset_dialog_stub(name="Good Name")

    with patch("rbcopy.gui.main_window.messagebox.showwarning") as mock_warn:
        dlg._ok()

    assert dlg._confirmed is True
    dlg.destroy.assert_called_once()
    mock_warn.assert_not_called()


def test_save_preset_dialog_ok_warns_and_does_not_confirm_when_name_empty() -> None:
    """_ok shows a warning and does NOT confirm when the name field is blank."""
    dlg = _make_save_preset_dialog_stub(name="   ")

    with patch("rbcopy.gui.main_window.messagebox.showwarning") as mock_warn:
        dlg._ok()

    assert dlg._confirmed is False
    dlg.destroy.assert_not_called()
    mock_warn.assert_called_once()


def test_save_preset_dialog_cancel_destroys_without_confirming() -> None:
    """_cancel destroys the dialog without marking it as confirmed."""
    dlg = _make_save_preset_dialog_stub()

    dlg._cancel()

    assert dlg._confirmed is False
    dlg.destroy.assert_called_once()


def test_save_preset_dialog_init_creates_window_with_real_tk() -> None:
    """_SavePresetDialog.__init__ runs without error (covers lines 324-369).

    Requires a live Tk display; skipped automatically on headless systems.
    ``wait_window`` and ``grab_set`` are patched to avoid blocking the test loop.
    """
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError as exc:
        pytest.skip(f"Tkinter display not available: {exc}")

    try:
        with (
            patch.object(_SavePresetDialog, "wait_window"),
            patch.object(_SavePresetDialog, "grab_set"),
        ):
            dlg = _SavePresetDialog(root)
        assert hasattr(dlg, "_name_var")
        assert hasattr(dlg, "_desc_var")
        assert hasattr(dlg, "_confirmed")
    finally:
        try:
            dlg.destroy()  # type: ignore[possibly-undefined]
        except Exception:
            pass
        root.destroy()


# ---------------------------------------------------------------------------
# _build_flags / _build_params early-return tests (lines 770, 815)
# ---------------------------------------------------------------------------


def test_build_flags_returns_early_when_all_flags_already_registered() -> None:
    """_build_flags returns without creating widgets when flags_to_render is empty."""
    from rbcopy.builder import FLAG_OPTIONS

    fake_self = _make_fake_self()
    # Pre-register every flag so flags_to_render will be empty.
    fake_self._flag_vars = {flag: MagicMock() for flag, _ in FLAG_OPTIONS}
    fake_self._flag_cbs = {flag: MagicMock() for flag, _ in FLAG_OPTIONS}

    mock_parent = MagicMock()
    # include=None means "render remaining flags"; since all are registered, list is empty.
    RobocopyGUI._build_flags(fake_self, mock_parent, {})

    # No LabelFrame (or child widget) should have been created.
    mock_parent.assert_not_called()


def test_build_params_returns_early_when_all_params_already_registered() -> None:
    """_build_params returns without creating widgets when params_to_render is empty."""
    from rbcopy.builder import PARAM_OPTIONS

    fake_self = _make_fake_self()
    # Pre-register every param so params_to_render will be empty.
    fake_self._param_vars = {flag: (MagicMock(), MagicMock(), MagicMock()) for flag, _, _ in PARAM_OPTIONS}

    mock_parent = MagicMock()
    RobocopyGUI._build_params(fake_self, mock_parent, {})

    mock_parent.assert_not_called()


# ---------------------------------------------------------------------------
# _stop OSError test (lines 1805-1806)
# ---------------------------------------------------------------------------


def test_stop_swallows_oserror_from_terminate() -> None:
    """_stop must not propagate an OSError raised by proc.terminate()."""
    fake_self = _make_fake_self()
    mock_proc = MagicMock()
    mock_proc.returncode = None  # process is live
    mock_proc.terminate.side_effect = OSError("already gone")
    fake_self._current_proc = mock_proc

    # Must not raise.
    RobocopyGUI._stop(fake_self)

    mock_proc.terminate.assert_called_once()


# ---------------------------------------------------------------------------
# _exit OSError test (lines 1785-1786)
# ---------------------------------------------------------------------------


def test_exit_swallows_oserror_from_kill() -> None:
    """_exit must not propagate an OSError raised by proc.kill() after timeout."""
    fake_self = _make_fake_self()
    mock_proc = MagicMock()
    mock_proc.returncode = None
    mock_proc.pid = 9999
    mock_proc.kill.side_effect = OSError("process already gone")
    fake_self._current_proc = mock_proc

    never_done = threading.Event()
    fake_self._proc_done_event = never_done

    with patch.object(never_done, "wait", return_value=False):
        RobocopyGUI._exit(fake_self)

    mock_proc.kill.assert_called_once()
    fake_self.destroy.assert_called_once()


# ---------------------------------------------------------------------------
# _exit – no _proc_done_event (branch L1780->1787)
# ---------------------------------------------------------------------------


def test_exit_with_running_process_and_no_done_event() -> None:
    """_exit terminates the process and proceeds even when _proc_done_event is None
    (false branch of 'if done is not None:', branch L1780->1787)."""
    fake_self = _make_fake_self()
    mock_proc = MagicMock()
    mock_proc.returncode = None
    mock_proc.pid = 1111
    fake_self._current_proc = mock_proc
    fake_self._proc_done_event = None  # no event set up

    RobocopyGUI._exit(fake_self)

    mock_proc.terminate.assert_called_once()
    # kill() must NOT be called since we could not wait for the process.
    mock_proc.kill.assert_not_called()
    fake_self.destroy.assert_called_once()


# ---------------------------------------------------------------------------
# launch() – same log dir does not produce a warning (branch L44->58)
# ---------------------------------------------------------------------------


def test_launch_same_log_dir_does_not_warn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """launch() does not log a warning when the FileHandler already writes to the
    requested log directory (false branch of 'if current_log_dir != log_dir:', L44->58)."""
    import rbcopy.gui as gui_module

    monkeypatch.setattr(gui_module, "RobocopyGUI", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(gui_module, "rotate_logs", MagicMock())

    # FileHandler pointing to tmp_path — same directory that setup_logging would return.
    log_file = tmp_path / "session.log"
    log_file.touch()
    handler = logging.FileHandler(str(log_file))
    dummy_logger = logging.getLogger("rbcopy._test_same_dir")
    dummy_logger.addHandler(handler)

    try:

        def stubbed_setup(log_dir: Any = None) -> logging.Logger:
            # Return the logger whose handler points to the same dir as log_dir.
            return dummy_logger

        monkeypatch.setattr(gui_module, "setup_logging", stubbed_setup)
        # Patch get_log_dir to return tmp_path (same as the handler dir).
        monkeypatch.setattr(
            "rbcopy.app_dirs.get_log_dir",
            MagicMock(return_value=tmp_path),
        )

        with caplog.at_level(logging.WARNING, logger="rbcopy.gui"):
            gui_module.launch()

    finally:
        handler.close()
        dummy_logger.removeHandler(handler)

    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert not any("already configured" in msg.lower() for msg in warning_messages)


# ---------------------------------------------------------------------------
# launch() – windll is None (branch L63->68)
# ---------------------------------------------------------------------------


def test_launch_skips_dpi_when_windll_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """launch() must not raise when ctypes.windll is None (non-Windows or old platform),
    covering the false branch of 'if windll is not None:' (branch L63->68)."""
    import rbcopy.gui as gui_module

    monkeypatch.setattr(gui_module, "RobocopyGUI", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(gui_module, "rotate_logs", MagicMock())

    dummy_logger = logging.getLogger("rbcopy._test_windll_none")
    monkeypatch.setattr(gui_module, "setup_logging", MagicMock(return_value=dummy_logger))

    # Force getattr(ctypes, "windll", None) to return None.
    import ctypes as ctypes_mod

    monkeypatch.setattr(ctypes_mod, "windll", None, raising=False)

    # Should not raise.
    gui_module.launch()


# ---------------------------------------------------------------------------
# _PresetDropdownTooltip._show – text changed while window is visible (L289->291)
# ---------------------------------------------------------------------------


def test_preset_dropdown_tooltip_show_recreates_when_text_changes() -> None:
    """_PresetDropdownTooltip._show calls _hide and recreates the window when the
    tooltip text differs from what is currently displayed (branch L289->291)."""
    from rbcopy.gui.main_window import _PresetDropdownTooltip

    tip: Any = _PresetDropdownTooltip.__new__(_PresetDropdownTooltip)
    tip._combo = MagicMock()
    tip._get_descriptions = MagicMock(return_value={})
    tip._FONT_SIZE = 9
    tip._WRAP_LENGTH = 320

    # Simulate an existing tooltip window showing "old text".
    mock_tip_window = MagicMock()
    mock_label = MagicMock()
    mock_label.cget.return_value = "old text"
    mock_tip_window.winfo_children.return_value = [mock_label]
    tip._tip_window = mock_tip_window

    tip._hide = MagicMock()

    with (
        patch("rbcopy.gui.main_window.tk.Toplevel") as mock_toplevel,
        patch("rbcopy.gui.main_window.tk.Label") as mock_label_cls,
    ):
        mock_tw = MagicMock()
        mock_toplevel.return_value = mock_tw
        mock_label_cls.return_value = MagicMock()
        # Show with a DIFFERENT text — the early-return guard should NOT trigger.
        tip._show(100, 200, "new text")

    # _hide must be called once to destroy the old window before creating a new one.
    tip._hide.assert_called_once()
