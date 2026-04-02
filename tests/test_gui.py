"""Tests for the rbcopy GUI module."""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import tkinter as tk
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from rbcopy.gui import RobocopyGUI
from rbcopy.gui.main_window import _MAX_LINES_PER_POLL, _OUTPUT_QUEUE_MAXSIZE
from tests.helpers import make_mock_async_proc


class _StringVarStub:
    """Minimal StringVar replacement that does not require a live Tk root.

    Used in _JobHistoryWindow unit tests to avoid RuntimeError when
    tk.StringVar() is instantiated outside a Tk event loop.
    """

    def __init__(self, value: str = "") -> None:
        self._value = value

    def get(self) -> str:
        return self._value

    def set(self, value: str) -> None:
        self._value = value

    def trace_add(self, *args: object, **kwargs: object) -> None:
        """No-op: traces are not exercised in unit tests."""


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
# RobocopyGUI._execute tests
# ---------------------------------------------------------------------------


def _make_fake_self() -> MagicMock:
    """Return a MagicMock suitable as a fake 'self' for RobocopyGUI methods."""
    fake: MagicMock = MagicMock()
    fake._output_queue = queue.Queue()
    fake._dropped_lines = 0
    fake._last_reported_drops = 0
    fake._dropped_lines_lock = threading.Lock()

    def _fake_append_output(text: str, block: bool = False) -> None:
        # Mirror the real _append_output: for block=True use the eviction
        # strategy; for block=False use put_nowait and track drops.
        # The evicted-line counter is only incremented when get_nowait()
        # actually removed a line; a queue.Empty exception means the queue
        # was concurrently drained so no line was evicted.
        if block:
            if fake._shutdown.is_set():
                return
            try:
                fake._output_queue.put_nowait(text)
            except queue.Full:
                try:
                    fake._output_queue.get_nowait()
                    with fake._dropped_lines_lock:
                        fake._dropped_lines += 1
                except queue.Empty:
                    pass
                try:
                    fake._output_queue.put_nowait(text)
                except queue.Full:
                    with fake._dropped_lines_lock:
                        fake._dropped_lines += 1
        else:
            try:
                fake._output_queue.put_nowait(text)
            except queue.Full:
                with fake._dropped_lines_lock:
                    fake._dropped_lines += 1

    # Wire _append_output so that calls from _async_execute (which uses
    # self._append_output instead of self._output_queue.put directly) still
    # land in the real queue, matching production behaviour without needing a
    # real Tkinter window.
    fake._append_output.side_effect = _fake_append_output
    # Wire _import_patterns_from_file so that calls from the higher-level import
    # helpers (_import_exclusions_from_file, _import_file_filter_from_file) still
    # reach the real implementation without a live Tkinter window.
    fake._import_patterns_from_file.side_effect = lambda *a, **kw: RobocopyGUI._import_patterns_from_file(
        fake, *a, **kw
    )
    fake._shutdown = threading.Event()
    fake._current_proc = None
    fake._job_already_running.return_value = False
    fake._script_builder_var = MagicMock()
    fake._script_builder_var.get.return_value = False
    fake._file_filter_enabled_var = MagicMock()
    fake._file_filter_enabled_var.get.return_value = False
    fake._file_filter_var = MagicMock()
    fake._file_filter_var.get.return_value = ""
    proc_done = threading.Event()
    proc_done.set()
    fake._proc_done_event = proc_done
    # _run now calls _get_selections and reads src/dst before _build_command
    fake._get_selections.return_value = ({}, {})
    fake.src_var.get.return_value = ""
    fake.dst_var.get.return_value = ""
    return fake


def _drain_queue(q: queue.Queue) -> list[str]:
    items: list[str] = []
    while not q.empty():
        items.append(q.get_nowait())
    return items


def test_execute_skips_when_shutdown_set() -> None:
    """_execute must not run the subprocess if the shutdown flag is already set."""
    fake_self = _make_fake_self()
    fake_self._shutdown.set()  # simulate shutdown before thread started

    with patch("rbcopy.gui.main_window.asyncio.create_subprocess_exec") as mock_exec:
        RobocopyGUI._execute(fake_self, ["robocopy", "C:/src", "C:/dst"])

    mock_exec.assert_not_called()


def test_async_execute_puts_lines_and_exit_code_in_queue() -> None:
    """_async_execute puts stdout lines and the exit-code message into the queue."""
    fake_self = _make_fake_self()
    mock_proc = make_mock_async_proc(returncode=0, output="line1\nline2\n", pid=1234)

    with patch("rbcopy.gui.main_window.asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        with patch("rbcopy.gui.main_window.notify_job_complete"):
            asyncio.run(RobocopyGUI._async_execute(fake_self, ["robocopy", "C:/src", "C:/dst"]))

    items = _drain_queue(fake_self._output_queue)
    assert "line1\n" in items
    assert "line2\n" in items
    assert any("Process exited with code 0" in item for item in items)


def test_execute_file_not_found() -> None:
    """_async_execute puts an error message in the queue when robocopy is not found."""
    fake_self = _make_fake_self()

    with patch("rbcopy.gui.main_window.asyncio.create_subprocess_exec", new=AsyncMock(side_effect=FileNotFoundError)):
        with patch("rbcopy.gui.main_window.notify_job_complete"):
            asyncio.run(RobocopyGUI._async_execute(fake_self, ["robocopy", "C:/src", "C:/dst"]))

    items = _drain_queue(fake_self._output_queue)
    assert any("robocopy" in item and "not found" in item for item in items)


def test_execute_generic_exception() -> None:
    """_async_execute puts a generic error message in the queue for unexpected errors."""
    fake_self = _make_fake_self()

    with patch("rbcopy.gui.main_window.asyncio.create_subprocess_exec", new=AsyncMock(side_effect=OSError("boom"))):
        with patch("rbcopy.gui.main_window.notify_job_complete"):
            asyncio.run(RobocopyGUI._async_execute(fake_self, ["robocopy", "C:/src", "C:/dst"]))

    items = _drain_queue(fake_self._output_queue)
    assert any("boom" in item for item in items)


def test_async_execute_disables_and_reenables_buttons() -> None:
    """_async_execute schedules button disabling before the job and re-enabling in finally."""
    from tests.helpers import make_mock_async_proc

    fake_self = _make_fake_self()
    mock_proc = make_mock_async_proc(returncode=0, output="", pid=42)

    with patch("rbcopy.gui.main_window.asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        with patch("rbcopy.gui.main_window.notify_job_complete"):
            asyncio.run(RobocopyGUI._async_execute(fake_self, ["robocopy", "C:/src", "C:/dst"]))

    states_scheduled: list[str] = []
    for call in fake_self.after.call_args_list:
        # after(0, lambda: self._set_run_buttons_state(...))
        # We invoke the lambda to observe what state it would set.
        callback = call.args[1]
        # Record the state argument the callback would pass.
        captured: list[str] = []
        fake_self._set_run_buttons_state.side_effect = lambda s: captured.append(s)
        callback()
        states_scheduled.extend(captured)
        fake_self._set_run_buttons_state.side_effect = None

    assert "disabled" in states_scheduled
    assert "normal" in states_scheduled


def test_async_execute_injects_np_flag_when_missing() -> None:
    """/NP is appended to the subprocess command when not already present."""
    fake_self = _make_fake_self()
    mock_proc = make_mock_async_proc(returncode=0, output="", pid=99)
    captured_args: list[tuple] = []

    async def _fake_exec(*args, **kwargs):
        captured_args.append(args)
        return mock_proc

    with patch("rbcopy.gui.main_window.asyncio.create_subprocess_exec", new=_fake_exec):
        with patch("rbcopy.gui.main_window.notify_job_complete"):
            asyncio.run(RobocopyGUI._async_execute(fake_self, ["robocopy", "C:/src", "C:/dst"]))

    assert len(captured_args) == 1
    assert "/NP" in captured_args[0]


def test_async_execute_does_not_duplicate_np_flag() -> None:
    """/NP is not added a second time when it is already present in the command."""
    fake_self = _make_fake_self()
    mock_proc = make_mock_async_proc(returncode=0, output="", pid=99)
    captured_args: list[tuple] = []

    async def _fake_exec(*args, **kwargs):
        captured_args.append(args)
        return mock_proc

    with patch("rbcopy.gui.main_window.asyncio.create_subprocess_exec", new=_fake_exec):
        with patch("rbcopy.gui.main_window.notify_job_complete"):
            asyncio.run(RobocopyGUI._async_execute(fake_self, ["robocopy", "C:/src", "C:/dst", "/NP"]))

    assert len(captured_args) == 1
    assert captured_args[0].count("/NP") == 1


# ---------------------------------------------------------------------------
# RobocopyGUI output helper tests
# ---------------------------------------------------------------------------


def test_append_output_enqueues_text() -> None:
    """_append_output puts the given string into _output_queue."""
    fake_self = _make_fake_self()
    RobocopyGUI._append_output(fake_self, "hello")
    assert fake_self._output_queue.get_nowait() == "hello"


def test_append_output_block_true_delivers_when_queue_full() -> None:
    """_append_output(block=True) must deliver the message even when the queue is full.

    The implementation evicts one older line to make room rather than blocking
    indefinitely, so the critical message always reaches the consumer.
    """
    fake_self = _make_fake_self()
    fake_self._output_queue = queue.Queue(maxsize=2)
    fake_self._output_queue.put_nowait("old1\n")
    fake_self._output_queue.put_nowait("old2\n")

    RobocopyGUI._append_output(fake_self, "CRITICAL\n", block=True)

    items = _drain_queue(fake_self._output_queue)
    assert "CRITICAL\n" in items
    # One older line must have been evicted and counted as dropped.
    assert fake_self._dropped_lines >= 1


def test_append_output_block_true_skips_when_shutdown() -> None:
    """_append_output(block=True) must not enqueue anything when shutdown is set."""
    fake_self = _make_fake_self()
    fake_self._shutdown.set()

    RobocopyGUI._append_output(fake_self, "should be ignored\n", block=True)

    assert fake_self._output_queue.empty()


def test_poll_output_drains_queue_and_calls_write() -> None:
    """_poll_output drains the queue, writes all items in one batched call, and reschedules."""
    fake_self = _make_fake_self()
    fake_self._output_queue.put("first\n")
    fake_self._output_queue.put("second\n")

    RobocopyGUI._poll_output(fake_self)

    fake_self._write_output.assert_called_once_with("first\nsecond\n")
    fake_self.after.assert_called_once_with(100, fake_self._poll_output)


def test_poll_output_limits_lines_per_poll() -> None:
    """_poll_output processes at most _MAX_LINES_PER_POLL items per cycle."""
    fake_self = _make_fake_self()
    total_lines = _MAX_LINES_PER_POLL + 10
    for i in range(total_lines):
        fake_self._output_queue.put(f"line{i}\n")

    RobocopyGUI._poll_output(fake_self)

    # Exactly _MAX_LINES_PER_POLL lines should have been written in one call.
    fake_self._write_output.assert_called_once()
    written: str = fake_self._write_output.call_args.args[0]
    assert written.count("\n") == _MAX_LINES_PER_POLL

    # The remaining 10 lines must still be in the queue.
    assert fake_self._output_queue.qsize() == 10


def test_poll_output_does_not_write_when_queue_empty() -> None:
    """_poll_output must not call _write_output when the queue is empty.

    The reschedule via after() must still occur so the polling loop continues.
    """
    fake_self = _make_fake_self()
    # Queue is empty — no items added.

    RobocopyGUI._poll_output(fake_self)

    fake_self._write_output.assert_not_called()
    fake_self.after.assert_called_once_with(100, fake_self._poll_output)


def test_poll_output_injects_dropped_lines_notice() -> None:
    """_poll_output must enqueue a notice and advance the watermark when lines were dropped."""
    fake_self = _make_fake_self()
    fake_self._dropped_lines = 42

    RobocopyGUI._poll_output(fake_self)

    # The dropped-lines notice should now be in the queue.
    items = _drain_queue(fake_self._output_queue)
    assert any("42" in item and "dropped" in item for item in items)
    # Watermark must be advanced so the same drops are not re-reported.
    assert fake_self._last_reported_drops == 42


def test_poll_output_retains_dropped_count_when_queue_full() -> None:
    """_poll_output must advance the watermark once the notice is successfully enqueued."""
    fake_self = _make_fake_self()
    # Use a tiny bounded queue (maxsize=1) and fill it so it must be drained first.
    fake_self._output_queue = queue.Queue(maxsize=1)
    fake_self._output_queue.put_nowait("already full\n")
    fake_self._dropped_lines = 7

    RobocopyGUI._poll_output(fake_self)

    # After draining 1 item, the notice should have been enqueued successfully.
    items = _drain_queue(fake_self._output_queue)
    assert any("7" in item and "dropped" in item for item in items)
    # Watermark must be advanced to match the current drop count.
    assert fake_self._last_reported_drops == 7


def test_async_execute_drops_lines_when_queue_full() -> None:
    """_async_execute increments _dropped_lines instead of blocking when the queue is full."""
    fake_self = _make_fake_self()
    # Fill the queue to capacity so every subsequent put raises queue.Full.
    fake_self._output_queue = queue.Queue(maxsize=2)
    # Two output lines; the queue will hold only the first two.
    mock_proc = make_mock_async_proc(returncode=0, output="line1\nline2\nline3\n", pid=99)

    with patch("rbcopy.gui.main_window.asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        with patch("rbcopy.gui.main_window.notify_job_complete"):
            with patch("rbcopy.gui.main_window.parse_summary_from_log", return_value=None):
                asyncio.run(RobocopyGUI._async_execute(fake_self, ["robocopy", "C:/src", "C:/dst"]))

    # At least one line must have been dropped (queue maxsize=2 but we have
    # 3 output lines plus the exit-code message).
    assert fake_self._dropped_lines >= 1


def test_output_queue_maxsize_is_bounded() -> None:
    """_OUTPUT_QUEUE_MAXSIZE must be a positive finite integer."""
    assert isinstance(_OUTPUT_QUEUE_MAXSIZE, int)
    assert _OUTPUT_QUEUE_MAXSIZE > 0


def test_write_output_configures_widget() -> None:
    """_write_output enables the widget, inserts text, scrolls to end, then disables."""
    fake_self = _make_fake_self()
    RobocopyGUI._write_output(fake_self, "some text")

    fake_self._output.config.assert_any_call(state="normal")
    fake_self._output.insert.assert_called_once_with("end", "some text")
    fake_self._output.see.assert_called_once_with("end")
    fake_self._output.config.assert_called_with(state="disabled")


def test_clear_output_configures_widget() -> None:
    """_clear_output enables the widget, deletes content, then disables."""
    fake_self = _make_fake_self()
    RobocopyGUI._clear_output(fake_self)

    fake_self._output.config.assert_any_call(state="normal")
    fake_self._output.delete.assert_called_once_with("1.0", "end")
    fake_self._output.config.assert_called_with(state="disabled")


# ---------------------------------------------------------------------------
# RobocopyGUI action tests
# ---------------------------------------------------------------------------


def test_preview_appends_command_output() -> None:
    """_preview builds the command and appends a preview line to output."""
    fake_self = _make_fake_self()
    fake_self._build_command.return_value = ["robocopy", "C:/src", "C:/dst"]

    RobocopyGUI._preview(fake_self)

    fake_self._append_output.assert_called_once()
    output_text: str = fake_self._append_output.call_args.args[0]
    assert "robocopy" in output_text


def test_preview_shows_warning_on_value_error() -> None:
    """_preview shows a warning dialog when src or dst is missing."""
    fake_self = _make_fake_self()
    fake_self._build_command.side_effect = ValueError("Source path is required")

    with patch("rbcopy.gui.main_window.messagebox.showwarning") as mock_warn:
        RobocopyGUI._preview(fake_self)

    mock_warn.assert_called_once()
    fake_self._append_output.assert_not_called()


def test_job_already_running_returns_false_when_no_proc() -> None:
    """_job_already_running returns False and shows no warning when no job is running."""
    fake_self = MagicMock()
    fake_self._current_proc = None

    with patch("rbcopy.gui.main_window.messagebox.showwarning") as mock_warn:
        result = RobocopyGUI._job_already_running(fake_self)

    assert result is False
    mock_warn.assert_not_called()


def test_job_already_running_returns_true_and_warns_when_proc_active() -> None:
    """_job_already_running returns True and shows a warning when a job is running."""
    fake_self = MagicMock()
    fake_self._current_proc = MagicMock()  # simulate running process

    with patch("rbcopy.gui.main_window.messagebox.showwarning") as mock_warn:
        result = RobocopyGUI._job_already_running(fake_self)

    assert result is True
    mock_warn.assert_called_once()
    warning_msg: str = mock_warn.call_args.args[1]
    assert "already running" in warning_msg.lower()


def test_run_starts_background_thread() -> None:
    """_run builds the command, logs it, and launches a daemon thread."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self()
    fake_self._build_command.return_value = ["robocopy", "C:/src", "C:/dst"]

    with patch("rbcopy.gui.main_window.validate_command", return_value=DryRunResult(ok=True)):
        with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            RobocopyGUI._run(fake_self)

    mock_thread_cls.assert_called_once_with(
        target=fake_self._execute,
        args=(["robocopy", "C:/src", "C:/dst"],),
        daemon=True,
    )
    mock_thread.start.assert_called_once()


def test_run_shows_warning_on_value_error() -> None:
    """_run shows a warning dialog and does not start a thread when paths are missing."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self()
    fake_self._build_command.side_effect = ValueError("Destination path is required")

    with patch("rbcopy.gui.main_window.validate_command", return_value=DryRunResult(ok=True)):
        with patch("rbcopy.gui.main_window.messagebox.showwarning") as mock_warn:
            with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
                RobocopyGUI._run(fake_self)

    mock_warn.assert_called_once()
    mock_thread_cls.assert_not_called()


def test_run_blocks_concurrent_execution() -> None:
    """_run shows a warning and does not start a thread when a job is already running."""
    fake_self = _make_fake_self()
    fake_self._job_already_running.return_value = True  # simulate a running process

    with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
        RobocopyGUI._run(fake_self)

    mock_thread_cls.assert_not_called()


def test_run_shows_validation_errors_and_aborts() -> None:
    """_run must show a warning and not start a thread when validation fails."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self()
    fake_self.src_var.get.return_value = "/nonexistent/path"
    fake_self.dst_var.get.return_value = "/some/dst"
    fake_self._get_selections.return_value = ({}, {})

    failed_result = DryRunResult(ok=False, errors=["Source path does not exist"])

    with patch("rbcopy.gui.main_window.validate_command", return_value=failed_result):
        with patch("rbcopy.gui.main_window.messagebox.showwarning") as mock_warn:
            with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread:
                RobocopyGUI._run(fake_self)

    mock_warn.assert_called_once()
    mock_thread.assert_not_called()


def test_run_appends_validation_errors_to_output() -> None:
    """_run must write the validation report to the output panel before aborting."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self()
    fake_self.src_var.get.return_value = "/bad/src"
    fake_self.dst_var.get.return_value = "/some/dst"
    fake_self._get_selections.return_value = ({}, {})

    failed_result = DryRunResult(ok=False, errors=["Source path does not exist"])

    with patch("rbcopy.gui.main_window.validate_command", return_value=failed_result):
        with patch("rbcopy.gui.main_window.messagebox.showwarning"):
            RobocopyGUI._run(fake_self)

    all_output = " ".join(call.args[0] for call in fake_self._append_output.call_args_list)
    assert "Source path does not exist" in all_output


def test_run_proceeds_with_warnings_only() -> None:
    """_run must start a thread when validation produces only warnings, not errors."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self()
    fake_self.src_var.get.return_value = "C:/src"
    fake_self.dst_var.get.return_value = "C:/dst"
    fake_self._get_selections.return_value = ({"/MIR": True, "/E": True}, {})
    fake_self._build_command.return_value = ["robocopy", "C:/src", "C:/dst", "/MIR", "/E"]

    warn_result = DryRunResult(ok=True, warnings=["/MIR is selected; /E is redundant"])

    with patch("rbcopy.gui.main_window.validate_command", return_value=warn_result):
        with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            RobocopyGUI._run(fake_self)

    mock_thread.assert_called_once()


def test_run_appends_warnings_to_output_before_proceeding() -> None:
    """_run must write validation warnings to output even when proceeding."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self()
    fake_self.src_var.get.return_value = "C:/src"
    fake_self.dst_var.get.return_value = "C:/dst"
    fake_self._get_selections.return_value = ({"/MIR": True, "/E": True}, {})
    fake_self._build_command.return_value = ["robocopy", "C:/src", "C:/dst"]

    warn_result = DryRunResult(ok=True, warnings=["/MIR is selected; /E is redundant"])

    with patch("rbcopy.gui.main_window.validate_command", return_value=warn_result):
        with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            RobocopyGUI._run(fake_self)

    all_output = " ".join(call.args[0] for call in fake_self._append_output.call_args_list)
    assert "/MIR is selected" in all_output


# ---------------------------------------------------------------------------
# Simulating a user clicking "Run" – unittest.mock walkthrough
# ---------------------------------------------------------------------------
# This section shows the canonical pattern for testing _run() without a live
# Tk display, without spawning a real robocopy process, and without opening
# any dialog boxes.
#
# The approach uses three layers of mocking:
#
#   1. _make_fake_self() – replaces the RobocopyGUI *instance* (self) with a
#      MagicMock whose relevant attributes are pre-configured.  This sidesteps
#      the need to create a Tk root window at all.
#
#   2. patch("rbcopy.gui.main_window.validate_command") – intercepts the
#      validation step so it returns a known DryRunResult without touching
#      the filesystem.
#
#   3. patch("rbcopy.gui.main_window.threading.Thread") – intercepts thread
#      creation so the test can assert *what* would have been launched without
#      actually blocking on a subprocess.
#
# Each test below focuses on one observable side-effect of a click:
#   • Was a thread started?   (happy path)
#   • Was a warning shown?    (validation failure)
#   • Was a thread blocked?   (concurrent protection)
# ---------------------------------------------------------------------------


def test_run_button_click_happy_path() -> None:
    """Simulates a user clicking ▶ Run with valid paths and no active flags.

    The Click:
        User fills in Source = "C:/source" and Destination = "D:/dest"
        then clicks the Run button, which calls RobocopyGUI._run().

    Expected outcome:
        • validate_command passes (ok=True, no errors).
        • _confirm_destructive_operation returns True (no destructive flags).
        • build_command builds ["robocopy", "C:/source", "D:/dest"].
        • A daemon thread is started targeting _execute with that command.
        • No warning dialog is shown to the user.
    """
    from rbcopy.builder import DryRunResult

    # Step 1 – configure the fake GUI instance with populated form fields.
    fake_self = _make_fake_self()
    fake_self.src_var.get.return_value = "C:/source"
    fake_self.dst_var.get.return_value = "D:/dest"
    fake_self._get_selections.return_value = ({}, {})
    fake_self._build_command.return_value = ["robocopy", "C:/source", "D:/dest"]

    # Step 2 – mock validate_command to return a clean result (no filesystem hit).
    ok_result = DryRunResult(ok=True)

    # Step 3 – mock threading.Thread to capture what would have been launched.
    with patch("rbcopy.gui.main_window.validate_command", return_value=ok_result):
        with patch("rbcopy.gui.main_window._confirm_destructive_operation", return_value=True):
            with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
                mock_thread = MagicMock()
                mock_thread_cls.return_value = mock_thread

                # Step 4 – invoke _run() exactly as the button command would.
                RobocopyGUI._run(fake_self)

    # Step 5 – assert the thread was started with the expected command.
    mock_thread_cls.assert_called_once_with(
        target=fake_self._execute,
        args=(["robocopy", "C:/source", "D:/dest"],),
        daemon=True,
    )
    mock_thread.start.assert_called_once()


def test_run_button_click_with_invalid_source() -> None:
    """Simulates a click after the user left Source blank.

    The Click:
        Source is "" (empty), Destination is "D:/dest".
        validate_command returns ok=False because the source is missing.

    Expected outcome:
        • A warning dialog appears; no background thread is launched.
    """
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self()
    fake_self.src_var.get.return_value = ""
    fake_self.dst_var.get.return_value = "D:/dest"
    fake_self._get_selections.return_value = ({}, {})

    # Simulate the validation step returning a path error.
    failed_result = DryRunResult(ok=False, errors=["Source path is required."])

    with patch("rbcopy.gui.main_window.validate_command", return_value=failed_result):
        with patch("rbcopy.gui.main_window.messagebox.showwarning") as mock_warn:
            with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
                RobocopyGUI._run(fake_self)

    # A warning must have been shown to the user.
    mock_warn.assert_called_once()
    # No subprocess should have been started.
    mock_thread_cls.assert_not_called()


def test_run_button_click_blocked_when_job_already_running() -> None:
    """Simulates a second click while a robocopy job is still in progress.

    The Click:
        User clicks Run while self._current_proc is not None
        (i.e. a previous job is still executing).

    Expected outcome:
        • _job_already_running() returns True.
        • _run() returns immediately; no new thread is created.
    """
    fake_self = _make_fake_self()
    # Simulate an already-running process.
    fake_self._job_already_running.return_value = True

    with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
        RobocopyGUI._run(fake_self)

    mock_thread_cls.assert_not_called()


def test_run_button_click_with_redundant_flags_proceeds_with_warning() -> None:
    """Simulates clicking Run when /MIR and /E are both checked (redundant combination).

    The Click:
        User ticked both /MIR and /E, then clicked Run.

    Expected outcome:
        • validate_command emits a warning about /E being redundant.
        • _run() writes the warning to the output panel.
        • The job still launches because warnings are non-fatal (ok=True).
    """
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self()
    fake_self.src_var.get.return_value = "C:/source"
    fake_self.dst_var.get.return_value = "D:/dest"
    fake_self._get_selections.return_value = ({"/MIR": True, "/E": True}, {})
    fake_self._build_command.return_value = ["robocopy", "C:/source", "D:/dest", "/MIR", "/E"]

    warn_result = DryRunResult(ok=True, warnings=["/MIR is selected; /E is redundant"])

    with patch("rbcopy.gui.main_window.validate_command", return_value=warn_result):
        with patch("rbcopy.gui.main_window._confirm_destructive_operation", return_value=True):
            with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
                mock_thread_cls.return_value = MagicMock()
                RobocopyGUI._run(fake_self)

    # The thread must have been created (job proceeds despite warning).
    mock_thread_cls.assert_called_once()
    # The warning must have been surfaced in the output panel.
    all_output = " ".join(call.args[0] for call in fake_self._append_output.call_args_list)
    assert "/MIR is selected" in all_output


# ---------------------------------------------------------------------------
# RobocopyGUI._dry_run tests
# ---------------------------------------------------------------------------


def _make_fake_self_for_dry_run() -> MagicMock:
    """Return a MagicMock suitable for testing _dry_run, with empty option dicts."""
    fake: MagicMock = _make_fake_self()
    fake.src_var.get.return_value = "C:/src"
    fake.dst_var.get.return_value = "C:/dst"
    fake._get_selections.return_value = ({}, {})
    return fake


def _get_thread_cmd(mock_thread_cls: MagicMock) -> list[str]:
    """Extract the command list passed to threading.Thread from a mock call."""
    return mock_thread_cls.call_args.kwargs["args"][0]  # type: ignore[no-any-return]


def test_dry_run_aborts_and_shows_warning_on_validation_error() -> None:
    """_dry_run shows a warning dialog and does not start a thread when validation fails."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self_for_dry_run()
    failed_result = DryRunResult(ok=False, errors=["Source path does not exist"])

    with patch("rbcopy.gui.main_window.validate_command", return_value=failed_result):
        with patch("rbcopy.gui.main_window.messagebox.showwarning") as mock_warn:
            with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
                RobocopyGUI._dry_run(fake_self)

    mock_warn.assert_called_once()
    mock_thread_cls.assert_not_called()


def test_dry_run_blocks_concurrent_execution() -> None:
    """_dry_run shows a warning and does not start a thread when a job is already running."""
    fake_self = _make_fake_self_for_dry_run()
    fake_self._job_already_running.return_value = True  # simulate a running process

    with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
        RobocopyGUI._dry_run(fake_self)

    mock_thread_cls.assert_not_called()


def test_dry_run_outputs_validation_report_on_error() -> None:
    """_dry_run appends the validation report to the output when errors are found."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self_for_dry_run()
    failed_result = DryRunResult(ok=False, errors=["Source path does not exist"])

    with patch("rbcopy.gui.main_window.validate_command", return_value=failed_result):
        with patch("rbcopy.gui.main_window.messagebox.showwarning"):
            RobocopyGUI._dry_run(fake_self)

    fake_self._append_output.assert_called()
    all_output = " ".join(call.args[0] for call in fake_self._append_output.call_args_list)
    assert "Source path does not exist" in all_output


def test_dry_run_appends_warning_to_output() -> None:
    """_dry_run appends non-fatal warnings to the output but still runs."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self_for_dry_run()
    warn_result = DryRunResult(ok=True, warnings=["/MIR is selected; /E is redundant"])

    with patch("rbcopy.gui.main_window.validate_command", return_value=warn_result):
        with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            RobocopyGUI._dry_run(fake_self)

    # Warning should appear in output
    all_output = " ".join(call.args[0] for call in fake_self._append_output.call_args_list)
    assert "/MIR is selected" in all_output
    # A thread should still be launched because ok=True
    mock_thread.start.assert_called_once()


def test_dry_run_adds_l_flag_if_missing() -> None:
    """_dry_run appends /L to the command when it is not already present."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self_for_dry_run()
    # /MIR is enabled, but /L is not — _dry_run must append it.
    fake_self._get_selections.return_value = ({"/MIR": True}, {})
    ok_result = DryRunResult(ok=True)

    with patch("rbcopy.gui.main_window.validate_command", return_value=ok_result):
        with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            RobocopyGUI._dry_run(fake_self)

    cmd_passed: list[str] = _get_thread_cmd(mock_thread_cls)
    assert "/L" in cmd_passed


def test_dry_run_does_not_duplicate_l_flag() -> None:
    """_dry_run does not add /L when it is already present in the command."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self_for_dry_run()
    # /L is already selected in the GUI — _dry_run must not add a second one.
    fake_self._get_selections.return_value = ({"/L": True}, {})
    ok_result = DryRunResult(ok=True)

    with patch("rbcopy.gui.main_window.validate_command", return_value=ok_result):
        with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            RobocopyGUI._dry_run(fake_self)

    cmd_passed: list[str] = _get_thread_cmd(mock_thread_cls)
    assert cmd_passed.count("/L") == 1


def test_dry_run_starts_background_thread() -> None:
    """_dry_run launches a daemon thread to execute the list-only robocopy command."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self_for_dry_run()
    ok_result = DryRunResult(ok=True)

    with patch("rbcopy.gui.main_window.validate_command", return_value=ok_result):
        with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
            with patch("rbcopy.builder.sys.platform", "linux"):
                mock_thread = MagicMock()
                mock_thread_cls.return_value = mock_thread
                RobocopyGUI._dry_run(fake_self)

    mock_thread_cls.assert_called_once_with(
        target=fake_self._execute,
        args=(["robocopy", "C:/src", "C:/dst", "/L"],),
        daemon=True,
    )
    mock_thread.start.assert_called_once()


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
# Custom preset methods – _save_custom_preset
# ---------------------------------------------------------------------------


def _make_fake_self_for_presets() -> MagicMock:
    """Return a fake self with preset-related attributes pre-configured."""
    fake = _make_fake_self()
    fake.src_var.get.return_value = "C:/src"
    fake.dst_var.get.return_value = "C:/dst"
    fake._get_selections.return_value = ({"/MIR": True}, {"/R": (True, "3")})
    return fake


def _mock_dialog(name: str | None, description: str = "") -> MagicMock:
    """Return a mock _SavePresetDialog instance with name and description properties.

    ``name`` is *None* when the dialog is cancelled; a non-empty string otherwise.
    """
    mock = MagicMock()
    type(mock).name = PropertyMock(return_value=name)
    type(mock).description = PropertyMock(return_value=description)
    return mock


def test_save_custom_preset_calls_store(tmp_path: Path) -> None:
    """_save_custom_preset saves the current selections to the presets store."""
    from rbcopy.presets import CustomPresetsStore

    fake = _make_fake_self_for_presets()
    fake._presets_store = CustomPresetsStore(path=tmp_path / "presets.json")

    with (
        patch("rbcopy.gui.main_window._SavePresetDialog", return_value=_mock_dialog("My Preset")),
        patch("rbcopy.gui.main_window.messagebox.showinfo"),
    ):
        RobocopyGUI._save_custom_preset(fake)

    preset = fake._presets_store.get_preset("My Preset")
    assert preset is not None
    assert preset.source == "C:/src"
    assert preset.destination == "C:/dst"
    assert preset.flags == {"/MIR": True}
    assert preset.params == {"/R": (True, "3")}


def test_save_custom_preset_rebuilds_menu(tmp_path: Path) -> None:
    """_save_custom_preset calls _rebuild_custom_menu after saving."""
    from rbcopy.presets import CustomPresetsStore

    fake = _make_fake_self_for_presets()
    fake._presets_store = CustomPresetsStore(path=tmp_path / "presets.json")

    with (
        patch("rbcopy.gui.main_window._SavePresetDialog", return_value=_mock_dialog("P")),
        patch("rbcopy.gui.main_window.messagebox.showinfo"),
    ):
        RobocopyGUI._save_custom_preset(fake)

    fake._rebuild_custom_menu.assert_called_once()


def test_save_custom_preset_shows_info_dialog(tmp_path: Path) -> None:
    """_save_custom_preset shows a success info dialog after saving."""
    from rbcopy.presets import CustomPresetsStore

    fake = _make_fake_self_for_presets()
    fake._presets_store = CustomPresetsStore(path=tmp_path / "presets.json")

    with (
        patch("rbcopy.gui.main_window._SavePresetDialog", return_value=_mock_dialog("Q")),
        patch("rbcopy.gui.main_window.messagebox.showinfo") as mock_info,
    ):
        RobocopyGUI._save_custom_preset(fake)

    mock_info.assert_called_once()


def test_save_custom_preset_cancelled_when_name_empty() -> None:
    """_save_custom_preset does nothing when the dialog returns None (user cancelled)."""
    fake = _make_fake_self_for_presets()

    with patch("rbcopy.gui.main_window._SavePresetDialog", return_value=_mock_dialog(None)):
        RobocopyGUI._save_custom_preset(fake)

    fake._rebuild_custom_menu.assert_not_called()


def test_save_custom_preset_cancelled_when_dialog_dismissed() -> None:
    """_save_custom_preset does nothing when the user cancels the dialog."""
    fake = _make_fake_self_for_presets()

    with patch("rbcopy.gui.main_window._SavePresetDialog", return_value=_mock_dialog(None)):
        RobocopyGUI._save_custom_preset(fake)

    fake._rebuild_custom_menu.assert_not_called()


def test_save_custom_preset_shows_error_on_disk_failure(tmp_path: Path) -> None:
    """_save_custom_preset shows an error dialog when the file write fails."""
    from rbcopy.presets import CustomPresetsStore

    fake = _make_fake_self_for_presets()
    fake._presets_store = CustomPresetsStore(path=tmp_path / "presets.json")

    with (
        patch("rbcopy.gui.main_window._SavePresetDialog", return_value=_mock_dialog("Fail")),
        patch("rbcopy.gui.main_window.messagebox.showerror") as mock_error,
        patch.object(Path, "write_bytes", side_effect=OSError("disk full")),
    ):
        RobocopyGUI._save_custom_preset(fake)

    mock_error.assert_called_once()
    # Menu must NOT be rebuilt when saving fails.
    fake._rebuild_custom_menu.assert_not_called()


def test_save_custom_preset_no_info_dialog_on_failure(tmp_path: Path) -> None:
    """_save_custom_preset must NOT show a success dialog when saving fails."""
    from rbcopy.presets import CustomPresetsStore

    fake = _make_fake_self_for_presets()
    fake._presets_store = CustomPresetsStore(path=tmp_path / "presets.json")

    with (
        patch("rbcopy.gui.main_window._SavePresetDialog", return_value=_mock_dialog("Fail")),
        patch("rbcopy.gui.main_window.messagebox.showinfo") as mock_info,
        patch("rbcopy.gui.main_window.messagebox.showerror"),
        patch.object(Path, "write_bytes", side_effect=OSError("disk full")),
    ):
        RobocopyGUI._save_custom_preset(fake)

    mock_info.assert_not_called()


def test_save_custom_preset_includes_file_filter(tmp_path: Path) -> None:
    """_save_custom_preset persists the current file filter value to the preset."""
    from rbcopy.presets import CustomPresetsStore

    fake = _make_fake_self_for_presets()
    fake._file_filter_enabled_var.get.return_value = True
    fake._file_filter_var.get.return_value = "*.img *.raw"
    fake._presets_store = CustomPresetsStore(path=tmp_path / "presets.json")

    with (
        patch("rbcopy.gui.main_window._SavePresetDialog", return_value=_mock_dialog("Filter Preset")),
        patch("rbcopy.gui.main_window.messagebox.showinfo"),
    ):
        RobocopyGUI._save_custom_preset(fake)

    preset = fake._presets_store.get_preset("Filter Preset")
    assert preset is not None
    assert preset.file_filter == "*.img *.raw"


def test_save_custom_preset_stores_empty_filter_when_disabled(tmp_path: Path) -> None:
    """_save_custom_preset stores an empty file_filter when the filter checkbox is unchecked."""
    from rbcopy.presets import CustomPresetsStore

    fake = _make_fake_self_for_presets()
    fake._file_filter_enabled_var.get.return_value = False
    fake._file_filter_var.get.return_value = "*.img"
    fake._presets_store = CustomPresetsStore(path=tmp_path / "presets.json")

    with (
        patch("rbcopy.gui.main_window._SavePresetDialog", return_value=_mock_dialog("No Filter")),
        patch("rbcopy.gui.main_window.messagebox.showinfo"),
    ):
        RobocopyGUI._save_custom_preset(fake)

    preset = fake._presets_store.get_preset("No Filter")
    assert preset is not None
    assert preset.file_filter == ""


def test_save_custom_preset_stores_description(tmp_path: Path) -> None:
    """_save_custom_preset persists the description entered in the dialog."""
    from rbcopy.presets import CustomPresetsStore

    fake = _make_fake_self_for_presets()
    fake._presets_store = CustomPresetsStore(path=tmp_path / "presets.json")

    with (
        patch(
            "rbcopy.gui.main_window._SavePresetDialog",
            return_value=_mock_dialog("My Preset", "Backs up all files nightly."),
        ),
        patch("rbcopy.gui.main_window.messagebox.showinfo"),
    ):
        RobocopyGUI._save_custom_preset(fake)

    preset = fake._presets_store.get_preset("My Preset")
    assert preset is not None
    assert preset.description == "Backs up all files nightly."


def test_save_custom_preset_stores_empty_description_when_omitted(tmp_path: Path) -> None:
    """_save_custom_preset stores an empty description when the user leaves it blank."""
    from rbcopy.presets import CustomPresetsStore

    fake = _make_fake_self_for_presets()
    fake._presets_store = CustomPresetsStore(path=tmp_path / "presets.json")

    with (
        patch("rbcopy.gui.main_window._SavePresetDialog", return_value=_mock_dialog("Unnamed", "")),
        patch("rbcopy.gui.main_window.messagebox.showinfo"),
    ):
        RobocopyGUI._save_custom_preset(fake)

    preset = fake._presets_store.get_preset("Unnamed")
    assert preset is not None
    assert preset.description == ""


# ---------------------------------------------------------------------------
# Custom preset methods – _apply_custom_preset
# ---------------------------------------------------------------------------


def test_apply_custom_preset_sets_source_and_destination() -> None:
    """_apply_custom_preset sets src_var and dst_var from the preset."""
    from rbcopy.presets import CustomPreset

    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = False
    preset = CustomPreset(name="p", source="/a", destination="/b")

    RobocopyGUI._apply_custom_preset(fake, preset)

    fake.src_var.set.assert_called_once_with("/a")
    fake.dst_var.set.assert_called_once_with("/b")


def test_apply_custom_preset_sets_flag_vars() -> None:
    """_apply_custom_preset updates matching _flag_vars entries."""
    from rbcopy.presets import CustomPreset

    fake = _make_fake_self()
    mir_var = MagicMock()
    fake._flag_vars = {"/MIR": mir_var}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = False
    preset = CustomPreset(name="p", flags={"/MIR": True})

    RobocopyGUI._apply_custom_preset(fake, preset)

    mir_var.set.assert_called_once_with(True)


def test_apply_custom_preset_sets_param_vars() -> None:
    """_apply_custom_preset updates matching _param_vars entries."""
    from rbcopy.presets import CustomPreset

    fake = _make_fake_self()
    fake._flag_vars = {}
    ev = MagicMock()
    vv = MagicMock()
    fake._param_vars = {"/R": (ev, vv, MagicMock())}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = False
    preset = CustomPreset(name="p", params={"/R": (True, "5")})

    RobocopyGUI._apply_custom_preset(fake, preset)

    ev.set.assert_called_once_with(True)
    vv.set.assert_called_once_with("5")


def test_apply_custom_preset_calls_refresh_widget_states() -> None:
    """_apply_custom_preset calls _refresh_widget_states after applying."""
    from rbcopy.presets import CustomPreset

    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = False
    preset = CustomPreset(name="p")

    RobocopyGUI._apply_custom_preset(fake, preset)

    fake._refresh_widget_states.assert_called_once()


def test_apply_custom_preset_ignores_unknown_flags() -> None:
    """_apply_custom_preset silently skips flags that are not in _flag_vars."""
    from rbcopy.presets import CustomPreset

    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = False
    # /UNKNOWN is not in _flag_vars – must not raise.
    preset = CustomPreset(name="p", flags={"/UNKNOWN": True})

    RobocopyGUI._apply_custom_preset(fake, preset)  # should not raise


def test_apply_custom_preset_skips_dst_when_props_only_active() -> None:
    """_apply_custom_preset must not overwrite dst_var when Properties Only is active."""
    from rbcopy.presets import CustomPreset

    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = True  # Properties Only active
    preset = CustomPreset(name="p", source="/src", destination="/new-dst")

    RobocopyGUI._apply_custom_preset(fake, preset)

    fake.src_var.set.assert_called_once_with("/src")
    fake.dst_var.set.assert_not_called()


def test_apply_custom_preset_skips_forced_flags_when_props_only_active() -> None:
    """_apply_custom_preset must not override forced flags when Properties Only is active."""
    from rbcopy.builder import PROPERTIES_ONLY_FLAGS
    from rbcopy.presets import CustomPreset

    fake = _make_fake_self()
    forced_flag = next(iter(PROPERTIES_ONLY_FLAGS))
    forced_var = MagicMock()
    fake._flag_vars = {forced_flag: forced_var}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = True
    preset = CustomPreset(name="p", flags={forced_flag: False})

    RobocopyGUI._apply_custom_preset(fake, preset)

    forced_var.set.assert_not_called()


def test_apply_custom_preset_skips_forced_params_when_props_only_active() -> None:
    """_apply_custom_preset must not override forced params when Properties Only is active."""
    from rbcopy.builder import PROPERTIES_ONLY_PARAMS
    from rbcopy.presets import CustomPreset

    fake = _make_fake_self()
    fake._flag_vars = {}
    forced_param = next(iter(PROPERTIES_ONLY_PARAMS))
    ev = MagicMock()
    vv = MagicMock()
    fake._param_vars = {forced_param: (ev, vv, MagicMock())}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = True
    preset = CustomPreset(name="p", params={forced_param: (False, "999")})

    RobocopyGUI._apply_custom_preset(fake, preset)

    ev.set.assert_not_called()
    vv.set.assert_not_called()


def test_apply_custom_preset_restores_file_filter() -> None:
    """_apply_custom_preset sets file filter vars when the preset has a non-empty file_filter."""
    from rbcopy.presets import CustomPreset

    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = False
    preset = CustomPreset(name="p", file_filter="*.img *.raw")

    RobocopyGUI._apply_custom_preset(fake, preset)

    fake._file_filter_enabled_var.set.assert_called_with(True)
    fake._file_filter_var.set.assert_called_with("*.img *.raw")


def test_apply_custom_preset_clears_file_filter_when_empty() -> None:
    """_apply_custom_preset disables the file filter when the preset has no file_filter."""
    from rbcopy.presets import CustomPreset

    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = False
    preset = CustomPreset(name="p", file_filter="")

    RobocopyGUI._apply_custom_preset(fake, preset)

    fake._file_filter_enabled_var.set.assert_called_with(False)
    fake._file_filter_var.set.assert_called_with("")


# ---------------------------------------------------------------------------
# _reset_options
# ---------------------------------------------------------------------------


def test_reset_options_method_exists() -> None:
    """RobocopyGUI must expose a callable _reset_options method."""
    assert callable(RobocopyGUI._reset_options)


def test_reset_options_clears_all_flag_vars() -> None:
    """_reset_options sets every _flag_vars entry to False."""
    fake = _make_fake_self()
    flag1 = MagicMock()
    flag2 = MagicMock()
    fake._flag_vars = {"/MIR": flag1, "/L": flag2}
    fake._param_vars = {}
    fake._props_only_var.get.return_value = False
    fake._is_applying_preset = False

    RobocopyGUI._reset_options(fake)

    flag1.set.assert_called_with(False)
    flag2.set.assert_called_with(False)


def test_reset_options_clears_all_param_enabled_vars() -> None:
    """_reset_options sets every param enabled_var to False."""
    fake = _make_fake_self()
    fake._flag_vars = {}
    enabled_var = MagicMock()
    value_var = MagicMock()
    fake._param_vars = {"/MT": (enabled_var, value_var, MagicMock())}
    fake._props_only_var.get.return_value = False
    fake._is_applying_preset = False

    RobocopyGUI._reset_options(fake)

    enabled_var.set.assert_called_with(False)


def test_reset_options_restores_param_placeholder_values() -> None:
    """_reset_options resets each param value_var to its default placeholder."""
    from rbcopy.builder import PARAM_OPTIONS

    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = False

    # Use the first PARAM_OPTIONS entry to get a real flag/placeholder pair.
    first_flag, _label, first_placeholder = PARAM_OPTIONS[0]
    enabled_var = MagicMock()
    value_var = MagicMock()
    fake._param_vars = {first_flag: (enabled_var, value_var, MagicMock())}

    RobocopyGUI._reset_options(fake)

    value_var.set.assert_called_with(first_placeholder)


def test_reset_options_deactivates_properties_only_preset() -> None:
    """_reset_options deactivates Properties Only when it is currently active."""
    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = True

    RobocopyGUI._reset_options(fake)

    fake._props_only_var.set.assert_called_with(False)


def test_reset_options_preserves_src_dst_when_properties_only_active() -> None:
    """_reset_options keeps src_var and dst_var unchanged even when Properties Only is deactivated."""
    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = True
    # Simulate src/dst StringVars with known current values.
    fake.src_var = MagicMock()
    fake.src_var.get.return_value = "C:/source"
    fake.dst_var = MagicMock()
    fake.dst_var.get.return_value = r"c:\temp\blank"

    RobocopyGUI._reset_options(fake)

    # src/dst must be restored to their values captured before deactivation.
    fake.src_var.set.assert_called_with("C:/source")
    fake.dst_var.set.assert_called_with(r"c:\temp\blank")


def test_reset_options_calls_refresh_widget_states() -> None:
    """_reset_options calls _refresh_widget_states after resetting all options."""
    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = False

    RobocopyGUI._reset_options(fake)

    fake._refresh_widget_states.assert_called_once()


def test_reset_options_clears_file_filter_vars() -> None:
    """_reset_options resets _file_filter_enabled_var to False and _file_filter_var to empty."""
    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = False

    RobocopyGUI._reset_options(fake)

    fake._file_filter_enabled_var.set.assert_called_with(False)
    fake._file_filter_var.set.assert_called_with("")


# ---------------------------------------------------------------------------
# Custom preset methods – _delete_custom_preset
# ---------------------------------------------------------------------------


def test_delete_custom_preset_removes_preset_after_confirmation(tmp_path: Path) -> None:
    """_delete_custom_preset deletes the preset when the user confirms."""
    from rbcopy.presets import CustomPreset, CustomPresetsStore

    fake = _make_fake_self()
    store = CustomPresetsStore(path=tmp_path / "presets.json")
    store.save_preset(CustomPreset(name="bye"))
    fake._presets_store = store

    with patch("rbcopy.gui.main_window.messagebox.askyesno", return_value=True):
        RobocopyGUI._delete_custom_preset(fake, "bye")

    assert store.get_preset("bye") is None
    fake._rebuild_custom_menu.assert_called_once()


def test_delete_custom_preset_aborts_when_cancelled(tmp_path: Path) -> None:
    """_delete_custom_preset does nothing when the user cancels the confirmation."""
    from rbcopy.presets import CustomPreset, CustomPresetsStore

    fake = _make_fake_self()
    store = CustomPresetsStore(path=tmp_path / "presets.json")
    store.save_preset(CustomPreset(name="stay"))
    fake._presets_store = store

    with patch("rbcopy.gui.main_window.messagebox.askyesno", return_value=False):
        RobocopyGUI._delete_custom_preset(fake, "stay")

    assert store.get_preset("stay") is not None
    fake._rebuild_custom_menu.assert_not_called()


# ---------------------------------------------------------------------------
# Custom preset methods – _rebuild_custom_menu
# ---------------------------------------------------------------------------


def test_rebuild_custom_menu_shows_placeholder_when_empty() -> None:
    """_rebuild_custom_menu adds a disabled placeholder when there are no presets."""
    from rbcopy.presets import CustomPresetsStore

    fake = _make_fake_self()
    fake._presets_store = MagicMock(spec=CustomPresetsStore)
    fake._presets_store.presets = []
    fake._custom_menu = MagicMock()

    RobocopyGUI._rebuild_custom_menu(fake)

    fake._custom_menu.delete.assert_called_once_with(0, "end")
    fake._custom_menu.add_command.assert_called_once()
    args = fake._custom_menu.add_command.call_args.kwargs
    assert args.get("state") == "disabled"


def test_rebuild_custom_menu_adds_cascade_per_preset() -> None:
    """_rebuild_custom_menu adds a cascade entry for each saved preset."""
    from rbcopy.presets import CustomPreset, CustomPresetsStore

    fake = _make_fake_self()
    fake._presets_store = MagicMock(spec=CustomPresetsStore)
    fake._presets_store.presets = [CustomPreset(name="A"), CustomPreset(name="B")]
    fake._custom_menu = MagicMock()

    with patch("rbcopy.gui.main_window.tk.Menu"):
        RobocopyGUI._rebuild_custom_menu(fake)

    assert fake._custom_menu.add_cascade.call_count == 2
    labels = [call.kwargs["label"] for call in fake._custom_menu.add_cascade.call_args_list]
    assert "A" in labels
    assert "B" in labels


def test_rebuild_custom_menu_shows_description_as_info_item() -> None:
    """_rebuild_custom_menu adds a disabled \u2139 item when the preset has a description."""
    from rbcopy.presets import CustomPreset, CustomPresetsStore

    fake = _make_fake_self()
    fake._presets_store = MagicMock(spec=CustomPresetsStore)
    fake._presets_store.presets = [
        CustomPreset(name="Mirror Sync", description="Keeps destination in sync with source.")
    ]
    fake._custom_menu = MagicMock()

    sub_mock = MagicMock()
    with patch("rbcopy.gui.main_window.tk.Menu", return_value=sub_mock):
        RobocopyGUI._rebuild_custom_menu(fake)

    sub_mock.add_command.assert_any_call(label="\u2139  Keeps destination in sync with source.", state="disabled")


def test_rebuild_custom_menu_no_info_item_when_description_empty() -> None:
    """_rebuild_custom_menu does NOT add an \u2139 item when description is empty."""
    from rbcopy.presets import CustomPreset, CustomPresetsStore

    fake = _make_fake_self()
    fake._presets_store = MagicMock(spec=CustomPresetsStore)
    fake._presets_store.presets = [CustomPreset(name="Plain")]
    fake._custom_menu = MagicMock()

    sub_mock = MagicMock()
    with patch("rbcopy.gui.main_window.tk.Menu", return_value=sub_mock):
        RobocopyGUI._rebuild_custom_menu(fake)

    for call in sub_mock.add_command.call_args_list:
        label = call.kwargs.get("label", "")
        assert "\u2139" not in label, f"Unexpected info item found: {label!r}"


# ---------------------------------------------------------------------------
# Job history – module-level helper tests
# ---------------------------------------------------------------------------


def test_exit_code_label_zero() -> None:
    """exit_code_label returns the correct message for exit code 0."""
    from rbcopy.builder import exit_code_label

    assert "Nothing to do" in exit_code_label(0)


def test_exit_code_label_one() -> None:
    """exit_code_label describes exit code 1 as files copied successfully."""
    from rbcopy.builder import exit_code_label

    assert "Files copied successfully" in exit_code_label(1)


def test_exit_code_label_additive() -> None:
    """exit_code_label combines descriptions for additive codes."""
    from rbcopy.builder import exit_code_label

    label = exit_code_label(3)
    assert "Files copied" in label
    assert "extra files" in label.lower()


def test_exit_code_label_fatal() -> None:
    """exit_code_label includes 'Fatal error' for exit code 16."""
    from rbcopy.builder import exit_code_label

    assert "Fatal error" in exit_code_label(16)


def test_parse_log_exit_code_nonzero(tmp_path: Path) -> None:
    """_parse_log_exit_code extracts a non-zero exit code from a log file."""
    from rbcopy.gui.job_history import _parse_log_exit_code

    log = tmp_path / "robocopy_job_20240101_120000.log"
    log.write_text(
        "2024-01-01 12:00:00 [INFO    ] rbcopy.gui: robocopy finished with exit code 3\n",
        encoding="utf-8",
    )
    assert _parse_log_exit_code(log) == 3


def test_parse_log_exit_code_zero(tmp_path: Path) -> None:
    """_parse_log_exit_code extracts exit code 0 from a 'completed successfully' line."""
    from rbcopy.gui.job_history import _parse_log_exit_code

    log = tmp_path / "robocopy_job_20240101_120001.log"
    log.write_text(
        "2024-01-01 12:00:01 [INFO    ] rbcopy.gui: robocopy completed successfully (exit code 0)\n",
        encoding="utf-8",
    )
    assert _parse_log_exit_code(log) == 0


def test_parse_log_exit_code_missing(tmp_path: Path) -> None:
    """_parse_log_exit_code returns None when no exit code line is present."""
    from rbcopy.gui.job_history import _parse_log_exit_code

    log = tmp_path / "robocopy_job_20240101_120002.log"
    log.write_text("2024-01-01 12:00:02 [DEBUG   ] rbcopy.gui: some debug line\n", encoding="utf-8")
    assert _parse_log_exit_code(log) is None


def test_parse_log_exit_code_unreadable(tmp_path: Path) -> None:
    """_parse_log_exit_code returns None for a path that cannot be read."""
    from rbcopy.gui.job_history import _parse_log_exit_code

    result = _parse_log_exit_code(tmp_path / "does_not_exist.log")
    assert result is None


# ---------------------------------------------------------------------------
# Job history – RobocopyGUI method tests
# ---------------------------------------------------------------------------


def test_job_history_method_exists() -> None:
    """RobocopyGUI must expose a callable _open_job_history method."""
    assert callable(RobocopyGUI._open_job_history)


def test_get_log_dir_returns_none_without_file_handler() -> None:
    """_get_log_dir returns None when the rbcopy logger has no FileHandler."""
    fake = _make_fake_self()

    with patch("rbcopy.gui.main_window.logging.getLogger") as mock_get_logger:
        mock_logger = MagicMock()
        mock_logger.handlers = []
        mock_get_logger.return_value = mock_logger
        result = RobocopyGUI._get_log_dir(fake)

    assert result is None


def test_get_log_dir_returns_parent_of_handler_file(tmp_path: Path) -> None:
    """_get_log_dir returns the directory of the FileHandler's log file."""
    fake = _make_fake_self()
    log_file = tmp_path / "robocopy_job_20240101_120000.log"
    log_file.touch()

    handler = logging.FileHandler(str(log_file))
    try:
        with patch("rbcopy.gui.main_window.logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_logger.handlers = [handler]
            mock_get_logger.return_value = mock_logger
            result = RobocopyGUI._get_log_dir(fake)
    finally:
        handler.close()

    assert result == tmp_path


def test_open_job_history_shows_info_when_no_log_dir() -> None:
    """_open_job_history shows an info dialog when no log directory is available."""
    fake = _make_fake_self()
    # _open_job_history calls self._get_log_dir(); set it on the MagicMock directly
    # so the call goes to our mock, not the real method.
    fake._get_log_dir.return_value = None

    with patch("rbcopy.gui.main_window.messagebox.showinfo") as mock_info:
        RobocopyGUI._open_job_history(fake)

    mock_info.assert_called_once()


def test_open_job_history_opens_window_when_log_dir_exists(tmp_path: Path) -> None:
    """_open_job_history creates a _JobHistoryWindow when a log directory is available."""
    fake = _make_fake_self()
    fake._get_log_dir.return_value = tmp_path

    with patch("rbcopy.gui.main_window._JobHistoryWindow") as mock_window_cls:
        RobocopyGUI._open_job_history(fake)

    mock_window_cls.assert_called_once_with(fake, tmp_path)


# ---------------------------------------------------------------------------
# Job history – _JobHistoryWindow._refresh tests
# ---------------------------------------------------------------------------


def _make_sync_thread(*_args: Any, **kwargs: Any) -> MagicMock:
    """Thread factory that runs the target synchronously on ``start()``."""
    target = kwargs.get("target")
    thread_args = kwargs.get("args", ())
    m = MagicMock()
    if target is not None:
        m.start.side_effect = lambda: target(*thread_args)
    return m


def test_job_history_window_refresh_empty_dir(tmp_path: Path) -> None:
    """_JobHistoryWindow._refresh shows a placeholder row when no log files exist."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    mock_tree = MagicMock()
    mock_tree.get_children.return_value = []

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._log_dir = tmp_path
    win._log_file_map = {}
    win._refresh_generation = 0
    win._tree = mock_tree
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    # No files → no background thread is started; after() is never called.
    win._refresh()

    mock_tree.insert.assert_called_once()
    values = mock_tree.insert.call_args.kwargs.get(
        "values", mock_tree.insert.call_args.args[-1] if mock_tree.insert.call_args.args else ()
    )
    assert "No log files found" in str(values)


def test_job_history_window_refresh_populates_rows(tmp_path: Path) -> None:
    """_JobHistoryWindow._refresh adds one row per matching log file."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    (tmp_path / "robocopy_job_20240101_120000.log").write_text(
        "2024-01-01 12:00:00 [INFO    ] rbcopy.gui: robocopy finished with exit code 1\n",
        encoding="utf-8",
    )
    (tmp_path / "robocopy_job_20240102_090000.log").write_text(
        "2024-01-02 09:00:00 [INFO    ] rbcopy.gui: robocopy completed successfully (exit code 0)\n",
        encoding="utf-8",
    )

    mock_tree = MagicMock()
    mock_tree.get_children.return_value = []
    _counter: list[int] = [0]

    def _insert(*_args: Any, **_kwargs: Any) -> str:
        _counter[0] += 1
        return str(_counter[0])

    mock_tree.insert.side_effect = _insert

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._log_dir = tmp_path
    win._log_file_map = {}
    win._refresh_generation = 0
    win._tree = mock_tree
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win.after = lambda ms, fn, *a: fn(*a)

    with patch("threading.Thread", side_effect=_make_sync_thread):
        win._refresh()

    assert mock_tree.insert.call_count == 2


def test_job_history_window_refresh_shows_exit_code(tmp_path: Path) -> None:
    """_JobHistoryWindow._refresh updates the exit-code column after background parsing."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    (tmp_path / "robocopy_job_20240101_120000.log").write_text(
        "2024-01-01 12:00:00 [INFO    ] rbcopy.gui: robocopy finished with exit code 8\n",
        encoding="utf-8",
    )

    mock_tree = MagicMock()
    mock_tree.get_children.return_value = []
    mock_tree.insert.return_value = "1"

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._log_dir = tmp_path
    win._log_file_map = {}
    win._refresh_generation = 0
    win._tree = mock_tree
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win.after = lambda ms, fn, *a: fn(*a)

    with patch("threading.Thread", side_effect=_make_sync_thread):
        win._refresh()

    # Row was initially inserted with "…"; background worker calls tree.set to update.
    set_values = {call.args[1]: call.args[2] for call in mock_tree.set.call_args_list}
    assert set_values.get("exit_code") == "8"


def test_job_history_window_refresh_unknown_code_for_in_progress(tmp_path: Path) -> None:
    """_JobHistoryWindow._refresh shows 'In progress / unknown' for files with no exit code."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    (tmp_path / "robocopy_job_20240101_120000.log").write_text(
        "2024-01-01 12:00:00 [INFO    ] rbcopy.gui: Job started\n",
        encoding="utf-8",
    )

    mock_tree = MagicMock()
    mock_tree.get_children.return_value = []
    mock_tree.insert.return_value = "1"

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._log_dir = tmp_path
    win._log_file_map = {}
    win._refresh_generation = 0
    win._tree = mock_tree
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win.after = lambda ms, fn, *a: fn(*a)

    with patch("threading.Thread", side_effect=_make_sync_thread):
        win._refresh()

    set_values = {call.args[1]: call.args[2] for call in mock_tree.set.call_args_list}
    assert set_values.get("status") == "In progress / unknown"


def test_job_history_window_refresh_cancels_stale_worker(tmp_path: Path) -> None:
    """Stale worker updates are dropped when a second _refresh() call supersedes the first.

    Simulates rapid repeated refreshes: the first worker's ``_update`` callback
    is captured but not yet invoked.  A second ``_refresh()`` increments the
    generation before ``_update`` runs.  The callback must detect the stale
    generation and skip the ``tree.set()`` call entirely.
    """
    from rbcopy.gui.job_history import _JobHistoryWindow

    (tmp_path / "robocopy_job_20240101_120000.log").write_text(
        "2024-01-01 12:00:00 [INFO    ] rbcopy.gui: robocopy finished with exit code 1\n",
        encoding="utf-8",
    )

    mock_tree = MagicMock()
    mock_tree.get_children.return_value = []
    mock_tree.insert.return_value = "1"

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._log_dir = tmp_path
    win._log_file_map = {}
    win._refresh_generation = 0
    win._tree = mock_tree
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1

    # Collect _update callbacks without invoking them immediately.
    deferred: list[Any] = []
    win.after = lambda ms, fn, *a: deferred.append((fn, a))

    with patch("threading.Thread", side_effect=_make_sync_thread):
        win._refresh()  # generation → 1, worker runs, queues _update in deferred

    assert len(deferred) == 1, "Expected one deferred _update callback"
    stale_update, stale_args = deferred[0]

    # A second refresh supersedes the first (generation → 2).
    # We don't need to run the new worker, just prove the stale update is ignored.
    win._refresh_generation += 1

    # Invoking the stale callback now: tree.set must NOT be called.
    mock_tree.set.reset_mock()
    stale_update(*stale_args)
    mock_tree.set.assert_not_called()


def test_job_history_window_refresh_with_active_filter_parses_all_entries(tmp_path: Path) -> None:
    """_refresh() with an active filter must still parse all log files, not just visible ones.

    Regression: previously ``pending`` was built from ``_log_file_map`` (only
    currently-visible rows), so entries hidden by the filter were never parsed.
    Clearing the filter afterwards would reveal those rows with "…" placeholders
    that no running worker could fill in.  The fix builds ``pending`` from
    ``_all_entries`` so every file is always resolved.
    """
    from rbcopy.gui.job_history import _JobHistoryWindow

    # Two log files with different dates.
    (tmp_path / "robocopy_job_20240101_120000.log").write_text(
        "2024-01-01 12:00:00 [INFO    ] rbcopy.gui: robocopy finished with exit code 1\n",
        encoding="utf-8",
    )
    (tmp_path / "robocopy_job_20240201_090000.log").write_text(
        "2024-02-01 09:00:00 [INFO    ] rbcopy.gui: robocopy finished with exit code 0\n",
        encoding="utf-8",
    )

    mock_tree = MagicMock()
    mock_tree.get_children.return_value = []
    _counter: list[int] = [0]

    def _insert(*_args: Any, **kwargs: Any) -> str:
        _counter[0] += 1
        iid = kwargs.get("iid", str(_counter[0]))
        return iid

    mock_tree.insert.side_effect = _insert

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._log_dir = tmp_path
    win._log_file_map = {}
    win._refresh_generation = 0
    win._tree = mock_tree
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    # Active keyword filter that matches only the January log.
    win._filter_var = _StringVarStub("2024-01")
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win.after = lambda ms, fn, *a: fn(*a)

    with patch("threading.Thread", side_effect=_make_sync_thread):
        win._refresh()

    # Both entries must be in _resolved, even though only the January entry was
    # visible while the filter was active.
    assert len(win._resolved) == 2, (
        "Background worker must resolve all entries, not just those visible through the filter"
    )
    resolved_statuses = {v[0] for v in win._resolved.values()}
    assert "1" in resolved_statuses
    assert "0" in resolved_statuses


# ---------------------------------------------------------------------------
# Job history – _parse_log_exit_code last-match tests
# ---------------------------------------------------------------------------


def test_parse_log_exit_code_returns_last_match(tmp_path: Path) -> None:
    """_parse_log_exit_code returns the last exit code when a log contains multiple jobs."""
    from rbcopy.gui.job_history import _parse_log_exit_code

    log = tmp_path / "robocopy_job_20240101_120000.log"
    log.write_text(
        "2024-01-01 12:00:00 [INFO    ] rbcopy.gui: robocopy finished with exit code 1\n"
        "2024-01-01 13:00:00 [INFO    ] rbcopy.gui: robocopy finished with exit code 8\n",
        encoding="utf-8",
    )
    # Second job in the same file wins.
    assert _parse_log_exit_code(log) == 8


# ---------------------------------------------------------------------------
# Job history – _parse_log_exit_code RBCOPY_METADATA footer tests
# ---------------------------------------------------------------------------


def test_parse_log_exit_code_metadata_nonzero(tmp_path: Path) -> None:
    """_parse_log_exit_code extracts exit code from the RBCOPY_METADATA JSON footer."""
    from rbcopy.gui.job_history import _parse_log_exit_code

    log = tmp_path / "robocopy_job_20240102_120000.log"
    log.write_text(
        '2024-01-02 12:00:00 [DEBUG   ] rbcopy.gui: === RBCOPY_METADATA: {"exit_code": 3} ===\n',
        encoding="utf-8",
    )
    assert _parse_log_exit_code(log) == 3


def test_parse_log_exit_code_metadata_zero(tmp_path: Path) -> None:
    """_parse_log_exit_code extracts exit code 0 from the RBCOPY_METADATA JSON footer."""
    from rbcopy.gui.job_history import _parse_log_exit_code

    log = tmp_path / "robocopy_job_20240102_120001.log"
    log.write_text(
        '2024-01-02 12:00:01 [DEBUG   ] rbcopy.gui: === RBCOPY_METADATA: {"exit_code": 0} ===\n',
        encoding="utf-8",
    )
    assert _parse_log_exit_code(log) == 0


def test_parse_log_exit_code_metadata_takes_precedence(tmp_path: Path) -> None:
    """Metadata footer exit code wins over legacy regex when both are present."""
    from rbcopy.gui.job_history import _parse_log_exit_code

    log = tmp_path / "robocopy_job_20240102_120002.log"
    log.write_text(
        "2024-01-02 12:00:02 [INFO    ] rbcopy.gui: robocopy finished with exit code 1\n"
        '2024-01-02 12:00:03 [DEBUG   ] rbcopy.gui: === RBCOPY_METADATA: {"exit_code": 8} ===\n',
        encoding="utf-8",
    )
    # Metadata footer value wins.
    assert _parse_log_exit_code(log) == 8


def test_parse_log_exit_code_metadata_last_entry_wins(tmp_path: Path) -> None:
    """When multiple RBCOPY_METADATA footers exist, the last one wins."""
    from rbcopy.gui.job_history import _parse_log_exit_code

    log = tmp_path / "robocopy_job_20240102_120003.log"
    log.write_text(
        '2024-01-02 12:00:00 [DEBUG   ] rbcopy.gui: === RBCOPY_METADATA: {"exit_code": 1} ===\n'
        '2024-01-02 13:00:00 [DEBUG   ] rbcopy.gui: === RBCOPY_METADATA: {"exit_code": 4} ===\n',
        encoding="utf-8",
    )
    assert _parse_log_exit_code(log) == 4


def test_parse_log_exit_code_metadata_malformed_falls_back(tmp_path: Path) -> None:
    """Malformed JSON in RBCOPY_METADATA is ignored; legacy regex is used as fallback."""
    from rbcopy.gui.job_history import _parse_log_exit_code

    log = tmp_path / "robocopy_job_20240102_120004.log"
    log.write_text(
        "2024-01-02 12:00:00 [DEBUG   ] rbcopy.gui: === RBCOPY_METADATA: NOT_JSON ===\n"
        "2024-01-02 12:00:01 [INFO    ] rbcopy.gui: robocopy finished with exit code 2\n",
        encoding="utf-8",
    )
    assert _parse_log_exit_code(log) == 2


def test_parse_log_exit_code_metadata_missing_key_falls_back(tmp_path: Path) -> None:
    """JSON without 'exit_code' key is ignored; legacy regex is used as fallback."""
    from rbcopy.gui.job_history import _parse_log_exit_code

    log = tmp_path / "robocopy_job_20240102_120005.log"
    log.write_text(
        '2024-01-02 12:00:00 [DEBUG   ] rbcopy.gui: === RBCOPY_METADATA: {"status": "ok"} ===\n'
        "2024-01-02 12:00:01 [INFO    ] rbcopy.gui: robocopy finished with exit code 5\n",
        encoding="utf-8",
    )
    assert _parse_log_exit_code(log) == 5


# ---------------------------------------------------------------------------
# Job history – _JobHistoryWindow._on_select tail-reading tests
# ---------------------------------------------------------------------------


def test_job_history_window_on_select_small_file_shows_full_content(tmp_path: Path) -> None:
    """_on_select loads the entire content for files under the preview limit."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    log = tmp_path / "robocopy_job_20240101_120000.log"
    log.write_text("hello world\n", encoding="utf-8")

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item1",)

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._tree = mock_tree
    win._log_file_map = {"item1": log}
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1

    win._on_select(MagicMock())

    # _set_content is called; check the text inserted into the widget.
    win._content.config.assert_called()
    calls = win._content.insert.call_args_list
    inserted = "".join(str(c.args[-1]) for c in calls)
    assert "hello world" in inserted


def test_job_history_window_on_select_large_file_shows_tail(tmp_path: Path) -> None:
    """_on_select shows only the tail and a truncation notice for large files."""
    import rbcopy.gui.job_history as job_history_module
    from rbcopy.gui.job_history import _JobHistoryWindow

    log = tmp_path / "robocopy_job_20240101_120000.log"
    # Write a file that exceeds _MAX_LOG_PREVIEW_BYTES.
    sentinel = b"LAST_LINE_SENTINEL"
    padding = b"x" * (2 * job_history_module._MAX_LOG_PREVIEW_BYTES)
    log.write_bytes(padding + sentinel)

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item1",)

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._tree = mock_tree
    win._log_file_map = {"item1": log}
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1

    win._on_select(MagicMock())

    calls = win._content.insert.call_args_list
    inserted = "".join(str(c.args[-1]) for c in calls)
    assert "showing last" in inserted
    assert "LAST_LINE_SENTINEL" in inserted


# ---------------------------------------------------------------------------
# Job history – _JobHistoryWindow._open_externally tests
# ---------------------------------------------------------------------------


def test_job_history_window_open_externally_no_selection_is_noop(tmp_path: Path) -> None:
    """_open_externally does nothing when no row is selected."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ()

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {}

    # Should return early without raising.
    win._open_externally()


def test_job_history_window_open_externally_calls_platform_command(tmp_path: Path) -> None:
    """_open_externally invokes the OS-appropriate command to open the file."""
    import rbcopy.gui.job_history as job_history_module
    from rbcopy.gui.job_history import _JobHistoryWindow

    log = tmp_path / "robocopy_job_20240101_120000.log"
    log.touch()

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item1",)

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {"item1": log}

    # Patch whichever opener the current platform would use.
    if hasattr(job_history_module.os, "startfile"):
        with patch.object(job_history_module.os, "startfile") as mock_open:
            win._open_externally()
        mock_open.assert_called_once_with(str(log))
    else:
        with patch.object(job_history_module.subprocess, "Popen") as mock_popen:
            win._open_externally()
        mock_popen.assert_called_once()


# ---------------------------------------------------------------------------
# Simple / Advanced mode toggle – _toggle_advanced
# ---------------------------------------------------------------------------


def test_toggle_advanced_shows_frame() -> None:
    """_toggle_advanced packs the advanced frame when currently hidden."""
    fake = _make_fake_self()
    fake._advanced_visible = False

    RobocopyGUI._toggle_advanced(fake)

    fake._advanced_frame.pack.assert_called_once_with(fill="x")
    assert fake._advanced_visible is True


def test_toggle_advanced_hides_frame() -> None:
    """_toggle_advanced removes the advanced frame when currently visible."""
    fake = _make_fake_self()
    fake._advanced_visible = True

    RobocopyGUI._toggle_advanced(fake)

    fake._advanced_frame.pack_forget.assert_called_once_with()
    assert fake._advanced_visible is False


def test_toggle_advanced_expand_updates_button_text() -> None:
    """_toggle_advanced sets button label to the down-pointing variant on expand."""
    fake = _make_fake_self()
    fake._advanced_visible = False

    RobocopyGUI._toggle_advanced(fake)

    fake._btn_advanced.config.assert_called_once_with(text="\u2699 Advanced \u25be")


def test_toggle_advanced_collapse_updates_button_text() -> None:
    """_toggle_advanced sets button label to the right-pointing variant on collapse."""
    fake = _make_fake_self()
    fake._advanced_visible = True

    RobocopyGUI._toggle_advanced(fake)

    fake._btn_advanced.config.assert_called_once_with(text="\u2699 Advanced \u25b8")


# ---------------------------------------------------------------------------
# Simple / Advanced mode toggle – _on_preset_selected
# ---------------------------------------------------------------------------


def test_on_preset_selected_properties_only() -> None:
    """_on_preset_selected activates the Properties Only preset when chosen."""
    fake = _make_fake_self()
    fake._preset_var.get.return_value = "Properties Only"

    RobocopyGUI._on_preset_selected(fake, MagicMock())

    fake._props_only_var.set.assert_called_once_with(True)


def test_on_preset_selected_custom_preset() -> None:
    """_on_preset_selected calls _apply_custom_preset with the matching preset object."""
    from rbcopy.presets import CustomPreset, CustomPresetsStore

    fake = _make_fake_self()
    preset = CustomPreset(name="My Preset")
    fake._preset_var.get.return_value = "My Preset"
    fake._presets_store = MagicMock(spec=CustomPresetsStore)
    fake._presets_store.get_preset.return_value = preset

    RobocopyGUI._on_preset_selected(fake, MagicMock())

    fake._presets_store.get_preset.assert_called_once_with("My Preset")
    fake._apply_custom_preset.assert_called_once_with(preset)


def test_on_preset_selected_resets_combo() -> None:
    """_on_preset_selected resets both the StringVar and the Combobox after applying."""
    fake = _make_fake_self()
    fake._preset_var.get.return_value = "Properties Only"

    RobocopyGUI._on_preset_selected(fake, MagicMock())

    fake._preset_var.set.assert_called_once_with("")
    fake._preset_combo.set.assert_called_once_with("")


def test_on_preset_selected_ignores_empty() -> None:
    """_on_preset_selected is a no-op when the selection resolves to an empty string."""
    fake = _make_fake_self()
    fake._preset_var.get.return_value = ""

    RobocopyGUI._on_preset_selected(fake, MagicMock())

    fake._props_only_var.set.assert_not_called()
    fake._apply_custom_preset.assert_not_called()
    fake._preset_var.set.assert_not_called()


# ---------------------------------------------------------------------------
# Simple / Advanced mode toggle – _refresh_preset_combo
# ---------------------------------------------------------------------------


def test_refresh_preset_combo_sets_values() -> None:
    """_refresh_preset_combo populates the combo with Properties Only plus presets."""
    from rbcopy.presets import CustomPreset, CustomPresetsStore

    fake = _make_fake_self()
    fake._preset_combo = MagicMock()
    fake._presets_store = MagicMock(spec=CustomPresetsStore)
    fake._presets_store.presets = [CustomPreset(name="Alpha"), CustomPreset(name="Beta")]

    RobocopyGUI._refresh_preset_combo(fake)

    fake._preset_combo.__setitem__.assert_called_once_with("values", ["Properties Only", "Alpha", "Beta"])


def test_refresh_preset_combo_skips_when_none() -> None:
    """_refresh_preset_combo returns immediately when _preset_combo is None."""
    fake = _make_fake_self()
    fake._preset_combo = None

    # Must not raise.
    RobocopyGUI._refresh_preset_combo(fake)


def test_job_history_window_open_externally_uses_startfile_on_windows(tmp_path: Path) -> None:
    """_open_externally calls os.startfile when it is available (Windows path)."""
    import rbcopy.gui.job_history as job_history_module
    from rbcopy.gui.job_history import _JobHistoryWindow

    log = tmp_path / "robocopy_job_20240101_120000.log"
    log.touch()

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item1",)

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {"item1": log}

    mock_startfile = MagicMock()
    # create=True adds startfile even on non-Windows where it doesn't exist.
    with patch.object(job_history_module.os, "startfile", mock_startfile, create=True):
        win._open_externally()

    mock_startfile.assert_called_once_with(str(log))


def test_job_history_window_open_externally_uses_open_on_macos(tmp_path: Path) -> None:
    """_open_externally calls 'open' via subprocess when sys.platform is 'darwin' and os.startfile is unavailable."""
    import rbcopy.gui.job_history as job_history_module
    from rbcopy.gui.job_history import _JobHistoryWindow

    if hasattr(job_history_module.os, "startfile"):
        # On Windows os.startfile always takes precedence; this branch cannot be reached
        # without deleting the built-in attribute.  Skip instead of breaking the os module.
        pytest.skip("macOS branch not reachable on platforms where os.startfile exists")

    log = tmp_path / "robocopy_job_20240101_120000.log"
    log.touch()

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item1",)

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {"item1": log}

    # On non-Windows platforms os.startfile is absent, so patching sys.platform to
    # "darwin" causes the elif-darwin branch to be taken.
    with (
        patch.object(job_history_module.subprocess, "Popen") as mock_popen,
        patch.object(job_history_module, "sys") as mock_sys,
    ):
        mock_sys.platform = "darwin"
        win._open_externally()

    mock_popen.assert_called_once_with(["open", str(log)], shell=False)


# ---------------------------------------------------------------------------
# Job history – _JobHistoryWindow._export_log tests
# ---------------------------------------------------------------------------


def test_job_history_window_export_log_no_selection_is_noop() -> None:
    """_export_log does nothing when no row is selected."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ()

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {}

    # Should return early without raising or opening a dialog.
    with patch("rbcopy.gui.job_history.filedialog.asksaveasfilename") as mock_dialog:
        win._export_log()
    mock_dialog.assert_not_called()


def test_job_history_window_export_log_cancelled_dialog_is_noop(tmp_path: Path) -> None:
    """_export_log does nothing when the save-file dialog is cancelled."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    log = tmp_path / "robocopy_job_20240101_120000.log"
    log.write_text("content\n", encoding="utf-8")

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item1",)

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {"item1": log}

    with patch("rbcopy.gui.job_history.filedialog.asksaveasfilename", return_value=""):
        with patch("rbcopy.gui.job_history.shutil.copy2") as mock_copy:
            win._export_log()

    mock_copy.assert_not_called()
    # Source file must remain untouched.
    assert log.read_text(encoding="utf-8") == "content\n"


def test_job_history_window_export_log_copies_file(tmp_path: Path) -> None:
    """_export_log copies the selected log to the chosen destination."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    src = tmp_path / "robocopy_job_20240101_120000.log"
    src.write_text("log content here\n", encoding="utf-8")
    dest = tmp_path / "exported.log"

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item1",)

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {"item1": src}

    with patch("rbcopy.gui.job_history.filedialog.asksaveasfilename", return_value=str(dest)):
        with patch("rbcopy.gui.job_history.messagebox.showinfo") as mock_info:
            win._export_log()

    assert dest.read_text(encoding="utf-8") == "log content here\n"
    mock_info.assert_called_once()


def test_job_history_window_export_log_shows_error_on_failure(tmp_path: Path) -> None:
    """_export_log shows an error dialog when the copy fails."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    src = tmp_path / "robocopy_job_20240101_120000.log"
    src.write_text("log content\n", encoding="utf-8")
    dest = tmp_path / "exported.log"

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item1",)

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {"item1": src}

    with patch("rbcopy.gui.job_history.filedialog.asksaveasfilename", return_value=str(dest)):
        with patch("rbcopy.gui.job_history.shutil.copy2", side_effect=OSError("disk full")):
            with patch("rbcopy.gui.job_history.messagebox.showerror") as mock_err:
                win._export_log()

    mock_err.assert_called_once()
    assert "disk full" in mock_err.call_args.args[1]


# ---------------------------------------------------------------------------
# Job history – _JobHistoryWindow._on_select edge-case tests
# ---------------------------------------------------------------------------


def test_job_history_window_on_select_no_selection_is_noop() -> None:
    """_on_select does nothing when no row is selected."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ()

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {}
    win._content = MagicMock()

    win._on_select(MagicMock())

    win._content.insert.assert_not_called()


def test_job_history_window_on_select_path_not_in_map_is_noop() -> None:
    """_on_select does nothing when the selected item has no corresponding log path."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item_with_no_path",)

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._tree = mock_tree
    win._log_file_map = {}  # empty – no mapping for the selected item
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1

    win._on_select(MagicMock())

    win._content.insert.assert_not_called()


def test_job_history_window_on_select_shows_error_on_read_failure(tmp_path: Path) -> None:
    """_on_select shows an error message in the content pane when the log file cannot be read."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    nonexistent = tmp_path / "missing.log"

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item1",)

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._tree = mock_tree
    win._log_file_map = {"item1": nonexistent}
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1

    win._on_select(MagicMock())

    calls = win._content.insert.call_args_list
    inserted = "".join(str(c.args[-1]) for c in calls)
    assert "Error reading file" in inserted


# ---------------------------------------------------------------------------
# Job history – _JobHistoryWindow._open_externally edge-case tests
# ---------------------------------------------------------------------------


def test_job_history_window_open_externally_path_not_in_map_is_noop() -> None:
    """_open_externally does nothing when the selected item has no corresponding log path."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item_not_in_map",)

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {}

    with patch("rbcopy.gui.job_history.subprocess.Popen") as mock_popen:
        win._open_externally()

    mock_popen.assert_not_called()


def test_job_history_window_open_externally_shows_error_on_oserror(tmp_path: Path) -> None:
    """_open_externally shows an error dialog when the system open command fails."""
    import contextlib

    import rbcopy.gui.job_history as job_history_module
    from rbcopy.gui.job_history import _JobHistoryWindow

    log = tmp_path / "robocopy_job_20240101_120000.log"
    log.touch()

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item1",)

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {"item1": log}

    # Patch whichever opener the current platform would use so the OSError path is exercised.
    # On Windows os.startfile is used; on other platforms subprocess.Popen is used.
    with contextlib.ExitStack() as stack:
        if hasattr(job_history_module.os, "startfile"):
            stack.enter_context(patch.object(job_history_module.os, "startfile", side_effect=OSError("no editor")))
        else:
            stack.enter_context(patch.object(job_history_module.subprocess, "Popen", side_effect=OSError("no editor")))
        mock_err = stack.enter_context(patch("rbcopy.gui.job_history.messagebox.showerror"))
        win._open_externally()

    mock_err.assert_called_once()
    assert "no editor" in mock_err.call_args.args[1]


# ---------------------------------------------------------------------------
# Job history – _JobHistoryWindow._export_log edge-case tests
# ---------------------------------------------------------------------------


def test_job_history_window_export_log_path_not_in_map_is_noop() -> None:
    """_export_log does nothing when the selected item has no corresponding log path."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item_not_in_map",)

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {}

    with patch("rbcopy.gui.job_history.filedialog.asksaveasfilename") as mock_dialog:
        win._export_log()

    mock_dialog.assert_not_called()


# ---------------------------------------------------------------------------
# Job history – _JobHistoryWindow._refresh edge-case tests
# ---------------------------------------------------------------------------


def test_job_history_window_refresh_deletes_existing_rows(tmp_path: Path) -> None:
    """_refresh clears existing Treeview rows before repopulating the list."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    mock_tree = MagicMock()
    mock_tree.get_children.return_value = ["old_row_1", "old_row_2"]

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._log_dir = tmp_path
    win._log_file_map = {}
    win._refresh_generation = 0
    win._tree = mock_tree
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1

    win._refresh()

    mock_tree.delete.assert_called_once_with("old_row_1", "old_row_2")


def test_job_history_window_refresh_handles_invalid_date_in_filename(tmp_path: Path) -> None:
    """_refresh falls back to the raw stem when the filename date cannot be parsed."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    # Create a log file whose date portion is not in the expected format.
    (tmp_path / "robocopy_job_BADDATE.log").write_text("content\n", encoding="utf-8")

    mock_tree = MagicMock()
    mock_tree.get_children.return_value = []
    mock_tree.insert.return_value = "1"

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._log_dir = tmp_path
    win._log_file_map = {}
    win._refresh_generation = 0
    win._tree = mock_tree
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win.after = lambda ms, fn, *a: fn(*a)

    with patch("threading.Thread", side_effect=_make_sync_thread):
        win._refresh()

    mock_tree.insert.assert_called_once()
    # The display value should contain the raw stem (fallback) instead of a formatted date.
    call_values = mock_tree.insert.call_args.kwargs.get(
        "values", mock_tree.insert.call_args.args[-1] if mock_tree.insert.call_args.args else ()
    )
    assert "BADDATE" in str(call_values)


def test_job_history_window_refresh_parse_worker_aborts_on_changed_generation(tmp_path: Path) -> None:
    """The parse worker returns early when the generation changes mid-loop (second file skipped)."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    (tmp_path / "robocopy_job_20240101_120000.log").write_text("job1\n", encoding="utf-8")
    (tmp_path / "robocopy_job_20240101_120001.log").write_text("job2\n", encoding="utf-8")

    mock_tree = MagicMock()
    mock_tree.get_children.return_value = []
    _counter: list[int] = [0]

    def _insert(*_args: Any, **_kwargs: Any) -> str:
        _counter[0] += 1
        return str(_counter[0])

    mock_tree.insert.side_effect = _insert

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._log_dir = tmp_path
    win._log_file_map = {}
    win._refresh_generation = 0
    win._tree = mock_tree
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1

    after_calls: list[int] = [0]

    def after_that_bumps_generation(ms: int, fn: Any, *a: Any) -> None:
        after_calls[0] += 1
        if after_calls[0] == 1:
            # Simulate a second refresh starting while the first worker is still looping.
            win._refresh_generation += 1
        fn(*a)

    win.after = after_that_bumps_generation

    with patch("threading.Thread", side_effect=_make_sync_thread):
        win._refresh()

    # Only the first file should have triggered an `after()` call; the second
    # is skipped because the generation check aborts the worker loop.
    assert after_calls[0] == 1


def test_job_history_window_update_callback_suppresses_tclerror(tmp_path: Path) -> None:
    """The _update callback silently ignores TclError raised when the window is closed."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    (tmp_path / "robocopy_job_20240101_120000.log").write_text(
        "2024-01-01 12:00:00 [INFO] rbcopy.gui: robocopy finished with exit code 1\n",
        encoding="utf-8",
    )

    mock_tree = MagicMock()
    mock_tree.get_children.return_value = []
    mock_tree.insert.return_value = "1"
    # Simulate window being destroyed: tree.set() raises TclError.
    mock_tree.set.side_effect = tk.TclError("invalid command name")

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._log_dir = tmp_path
    win._log_file_map = {}
    win._refresh_generation = 0
    win._tree = mock_tree
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win.after = lambda ms, fn, *a: fn(*a)

    # Must complete without raising TclError.
    with patch("threading.Thread", side_effect=_make_sync_thread):
        win._refresh()


def test_job_history_window_parse_worker_aborts_on_tclerror_in_after(tmp_path: Path) -> None:
    """The parse worker returns early when after() raises TclError (window destroyed)."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    (tmp_path / "robocopy_job_20240101_120000.log").write_text("content\n", encoding="utf-8")

    mock_tree = MagicMock()
    mock_tree.get_children.return_value = []
    mock_tree.insert.return_value = "1"

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._log_dir = tmp_path
    win._log_file_map = {}
    win._refresh_generation = 0
    win._tree = mock_tree
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1

    def raising_after(ms: int, fn: Any, *a: Any) -> None:
        raise tk.TclError("window destroyed")

    win.after = raising_after

    # Must complete without raising TclError.
    with patch("threading.Thread", side_effect=_make_sync_thread):
        win._refresh()


def test_job_history_filter_hides_non_matching_rows(tmp_path: Path) -> None:
    """Rows whose date string does not contain the keyword are hidden."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    (tmp_path / "robocopy_job_20240601_120000.log").write_text("x", encoding="utf-8")
    (tmp_path / "robocopy_job_20240715_090000.log").write_text("x", encoding="utf-8")

    mock_tree = MagicMock()
    mock_tree.get_children.return_value = []
    inserted_values: list[tuple[Any, ...]] = []

    def _insert(*args: Any, **kwargs: Any) -> str:
        vals = kwargs.get("values", ())
        inserted_values.append(vals)
        return kwargs.get("iid", str(len(inserted_values)))

    mock_tree.insert.side_effect = _insert

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._log_dir = tmp_path
    win._log_file_map = {}
    win._refresh_generation = 0
    win._tree = mock_tree
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win.after = lambda ms, fn, *a: fn(*a)

    with patch("threading.Thread", side_effect=_make_sync_thread):
        win._refresh()

    # Now apply a keyword that matches only June.
    inserted_values.clear()
    mock_tree.get_children.return_value = []
    mock_tree.insert.side_effect = _insert

    win._filter_var.set("2024-06")
    win._apply_tree_filter()

    assert len(inserted_values) == 1
    assert "2024-06-01" in str(inserted_values[0])


def test_job_history_filter_shows_all_when_empty(tmp_path: Path) -> None:
    """Clearing the filter shows all entries."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    (tmp_path / "robocopy_job_20240601_120000.log").write_text("x", encoding="utf-8")
    (tmp_path / "robocopy_job_20240715_090000.log").write_text("x", encoding="utf-8")

    mock_tree = MagicMock()
    mock_tree.get_children.return_value = []
    insert_count: list[int] = [0]

    def _insert(*args: Any, **kwargs: Any) -> str:
        insert_count[0] += 1
        return kwargs.get("iid", str(insert_count[0]))

    mock_tree.insert.side_effect = _insert

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._log_dir = tmp_path
    win._log_file_map = {}
    win._refresh_generation = 0
    win._tree = mock_tree
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win.after = lambda ms, fn, *a: fn(*a)

    with patch("threading.Thread", side_effect=_make_sync_thread):
        win._refresh()

    assert insert_count[0] == 2


def test_job_history_filter_date_from_excludes_earlier(tmp_path: Path) -> None:
    """Entries before the From date are excluded."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    (tmp_path / "robocopy_job_20240101_120000.log").write_text("x", encoding="utf-8")
    (tmp_path / "robocopy_job_20240601_120000.log").write_text("x", encoding="utf-8")

    mock_tree = MagicMock()
    mock_tree.get_children.return_value = []
    inserted_values: list[tuple[Any, ...]] = []

    def _insert(*args: Any, **kwargs: Any) -> str:
        vals = kwargs.get("values", ())
        inserted_values.append(vals)
        return kwargs.get("iid", str(len(inserted_values)))

    mock_tree.insert.side_effect = _insert

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._log_dir = tmp_path
    win._log_file_map = {}
    win._refresh_generation = 0
    win._tree = mock_tree
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win.after = lambda ms, fn, *a: fn(*a)

    with patch("threading.Thread", side_effect=_make_sync_thread):
        win._refresh()

    inserted_values.clear()
    mock_tree.get_children.return_value = []
    mock_tree.insert.side_effect = _insert

    win._date_from_var.set("2024-03-01")
    win._apply_tree_filter()

    assert len(inserted_values) == 1
    assert "2024-06-01" in str(inserted_values[0])


def test_job_history_filter_date_to_excludes_later(tmp_path: Path) -> None:
    """Entries after the To date are excluded."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    (tmp_path / "robocopy_job_20240101_120000.log").write_text("x", encoding="utf-8")
    (tmp_path / "robocopy_job_20240601_120000.log").write_text("x", encoding="utf-8")

    mock_tree = MagicMock()
    mock_tree.get_children.return_value = []
    inserted_values: list[tuple[Any, ...]] = []

    def _insert(*args: Any, **kwargs: Any) -> str:
        vals = kwargs.get("values", ())
        inserted_values.append(vals)
        return kwargs.get("iid", str(len(inserted_values)))

    mock_tree.insert.side_effect = _insert

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._log_dir = tmp_path
    win._log_file_map = {}
    win._refresh_generation = 0
    win._tree = mock_tree
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win.after = lambda ms, fn, *a: fn(*a)

    with patch("threading.Thread", side_effect=_make_sync_thread):
        win._refresh()

    inserted_values.clear()
    mock_tree.get_children.return_value = []
    mock_tree.insert.side_effect = _insert

    win._date_to_var.set("2024-03-01")
    win._apply_tree_filter()

    assert len(inserted_values) == 1
    assert "2024-01-01" in str(inserted_values[0])


def test_job_history_filter_invalid_date_is_ignored(tmp_path: Path) -> None:
    """An unparseable date string in From/To is treated as absent (no filtering)."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    (tmp_path / "robocopy_job_20240601_120000.log").write_text("x", encoding="utf-8")
    (tmp_path / "robocopy_job_20240715_090000.log").write_text("x", encoding="utf-8")

    mock_tree = MagicMock()
    mock_tree.get_children.return_value = []
    insert_count: list[int] = [0]

    def _insert(*args: Any, **kwargs: Any) -> str:
        insert_count[0] += 1
        return kwargs.get("iid", str(insert_count[0]))

    mock_tree.insert.side_effect = _insert

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._log_dir = tmp_path
    win._log_file_map = {}
    win._refresh_generation = 0
    win._tree = mock_tree
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win.after = lambda ms, fn, *a: fn(*a)

    with patch("threading.Thread", side_effect=_make_sync_thread):
        win._refresh()

    insert_count[0] = 0
    mock_tree.get_children.return_value = []
    mock_tree.insert.side_effect = _insert

    win._date_from_var.set("not-a-date")
    win._apply_tree_filter()

    assert insert_count[0] == 2


def test_job_history_filter_no_matches_inserts_placeholder(tmp_path: Path) -> None:
    """When no entries match, a single placeholder row is inserted."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    (tmp_path / "robocopy_job_20240601_120000.log").write_text("x", encoding="utf-8")

    mock_tree = MagicMock()
    mock_tree.get_children.return_value = []
    inserted_values: list[tuple[Any, ...]] = []

    def _insert(*args: Any, **kwargs: Any) -> str:
        vals = kwargs.get("values", ())
        inserted_values.append(vals)
        return str(len(inserted_values))

    mock_tree.insert.side_effect = _insert

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._log_dir = tmp_path
    win._log_file_map = {}
    win._refresh_generation = 0
    win._tree = mock_tree
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win.after = lambda ms, fn, *a: fn(*a)

    with patch("threading.Thread", side_effect=_make_sync_thread):
        win._refresh()

    inserted_values.clear()
    mock_tree.get_children.return_value = []
    mock_tree.insert.side_effect = _insert

    win._filter_var.set("ZZZNOMATCH")
    win._apply_tree_filter()

    assert len(inserted_values) == 1
    assert "No matching" in str(inserted_values[0])


def test_job_history_clear_filter_resets_all_vars(tmp_path: Path) -> None:
    """_clear_filter empties all three filter StringVars."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._log_dir = tmp_path
    win._log_file_map = {}
    win._refresh_generation = 0
    win._tree = MagicMock()
    win._tree.get_children.return_value = []
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub(value="june")
    win._date_from_var = _StringVarStub(value="2024-01-01")
    win._date_to_var = _StringVarStub(value="2024-12-31")
    win._filter_count_var = _StringVarStub(value="3 of 10")
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1

    win._clear_filter()

    assert win._filter_var.get() == ""
    assert win._date_from_var.get() == ""
    assert win._date_to_var.get() == ""
    assert win._filter_count_var.get() == ""


def _make_search_win() -> Any:
    """Return a minimal _JobHistoryWindow stub wired for search tests."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    win = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._search_matches = []
    win._search_current = -1
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._content.search.side_effect = ["3.5", ""]
    return win


def test_search_next_applies_highlight_tag() -> None:
    """_search_next adds the highlight tag to matches."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    win = _make_search_win()
    win._content.search.side_effect = ["3.5", ""]
    win._search_var.set("error")

    win._search_next()

    win._content.tag_add.assert_called()
    first_call = win._content.tag_add.call_args_list[0]
    assert _JobHistoryWindow._SEARCH_TAG in first_call.args


def test_search_next_updates_count_label() -> None:
    """_search_next sets the count label to '1 of N'."""
    win = _make_search_win()
    win._content.search.side_effect = ["3.5", ""]
    win._search_var.set("warn")

    win._search_next()

    assert win._search_count_var.get() == "1 of 1"


def test_search_no_term_clears_state() -> None:
    """_search_next with an empty term calls _clear_search."""
    win = _make_search_win()
    win._search_var.set("")

    win._search_next()

    win._content.tag_add.assert_not_called()
    assert win._search_count_var.get() == ""


def test_search_no_matches_shows_zero() -> None:
    """_search_next with a term that has no matches shows '0 matches'."""
    win = _make_search_win()
    win._content.search.side_effect = [""]
    win._search_var.set("ZZZNOMATCH")

    win._search_next()

    assert win._search_count_var.get() == "0 matches"


def test_clear_search_removes_tag_and_resets_state() -> None:
    """_clear_search removes the highlight tag and empties all state."""
    from rbcopy.gui.job_history import _JobHistoryWindow

    win = _make_search_win()
    win._search_matches = [("1.0", "1.5"), ("2.0", "2.5")]
    win._search_current = 0
    win._search_var.set("something")
    win._search_count_var.set("1 of 2")

    win._clear_search()

    win._content.tag_remove.assert_called_once_with(_JobHistoryWindow._SEARCH_TAG, "1.0", "end")
    assert win._search_matches == []
    assert win._search_current == -1
    assert win._search_var.get() == ""
    assert win._search_count_var.get() == ""


def test_search_prev_wraps_to_last_match() -> None:
    """_search_prev from position 0 wraps around to the last match."""
    win = _make_search_win()
    win._search_var.set("x")
    win._content.search.side_effect = ["1.0", "3.0", ""]

    win._search_prev()

    # Going back from -1 (no current) lands on the last match (index 1).
    assert win._search_current == 1


# ---------------------------------------------------------------------------
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
# Bookmark manager – RobocopyGUI._open_bookmark_manager
# ---------------------------------------------------------------------------


def test_open_bookmark_manager_method_exists() -> None:
    """RobocopyGUI must expose a callable _open_bookmark_manager method."""
    assert callable(RobocopyGUI._open_bookmark_manager)


def test_open_bookmark_manager_opens_window() -> None:
    """_open_bookmark_manager must instantiate _BookmarkManagerWindow."""
    from rbcopy.bookmarks import BookmarksStore

    fake = _make_fake_self()
    fake._bookmarks_store = MagicMock(spec=BookmarksStore)

    with patch("rbcopy.gui.main_window._BookmarkManagerWindow") as mock_cls:
        RobocopyGUI._open_bookmark_manager(fake)

    mock_cls.assert_called_once()
    call_kwargs = mock_cls.call_args.kwargs
    assert call_kwargs["store"] is fake._bookmarks_store
    assert callable(call_kwargs["on_change"])
    assert callable(call_kwargs["on_apply"])


def test_open_bookmark_manager_on_change_calls_rebuild_menu() -> None:
    """The on_change callback passed to _BookmarkManagerWindow calls _rebuild_bookmarks_menu."""
    from rbcopy.bookmarks import BookmarksStore

    fake = _make_fake_self()
    fake._bookmarks_store = MagicMock(spec=BookmarksStore)

    with patch("rbcopy.gui.main_window._BookmarkManagerWindow") as mock_cls:
        RobocopyGUI._open_bookmark_manager(fake)

    on_change = mock_cls.call_args.kwargs["on_change"]
    on_change()
    fake._rebuild_bookmarks_menu.assert_called_once()


def test_open_bookmark_manager_on_apply_sets_source() -> None:
    """The on_apply callback sets src_var when field='source'."""
    from rbcopy.bookmarks import BookmarksStore

    fake = _make_fake_self()
    fake._bookmarks_store = MagicMock(spec=BookmarksStore)

    with patch("rbcopy.gui.main_window._BookmarkManagerWindow") as mock_cls:
        RobocopyGUI._open_bookmark_manager(fake)

    on_apply = mock_cls.call_args.kwargs["on_apply"]
    on_apply("source", r"C:\my\source")
    fake.src_var.set.assert_called_once_with(r"C:\my\source")


def test_open_bookmark_manager_on_apply_sets_destination() -> None:
    """The on_apply callback sets dst_var when field='destination'."""
    from rbcopy.bookmarks import BookmarksStore

    fake = _make_fake_self()
    fake._bookmarks_store = MagicMock(spec=BookmarksStore)

    with patch("rbcopy.gui.main_window._BookmarkManagerWindow") as mock_cls:
        RobocopyGUI._open_bookmark_manager(fake)

    on_apply = mock_cls.call_args.kwargs["on_apply"]
    on_apply("destination", r"C:\my\dest")
    fake.dst_var.set.assert_called_once_with(r"C:\my\dest")


# ---------------------------------------------------------------------------
# Bookmark manager – _BookmarkManagerWindow unit tests
# ---------------------------------------------------------------------------


def _make_bookmark_manager_win(store: Any) -> Any:
    """Return a _BookmarkManagerWindow instance injected with mock widgets."""
    from rbcopy.gui.bookmark_manager import _BookmarkManagerWindow

    win = _BookmarkManagerWindow.__new__(_BookmarkManagerWindow)
    win._store = store
    win._on_change = MagicMock()
    win._on_apply = MagicMock()

    mock_tree = MagicMock()
    # Default: nothing selected.
    mock_tree.selection.return_value = ()
    mock_tree.get_children.return_value = []
    win._tree = mock_tree
    return win


def test_bookmark_manager_refresh_shows_placeholder_when_empty(tmp_path: Path) -> None:
    """_refresh inserts a placeholder row when the store has no bookmarks."""
    from rbcopy.bookmarks import BookmarksStore

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    win = _make_bookmark_manager_win(store)

    win._refresh()

    win._tree.insert.assert_called_once()
    values = win._tree.insert.call_args.kwargs.get(
        "values", win._tree.insert.call_args.args[-1] if win._tree.insert.call_args.args else ()
    )
    assert "(no bookmarks)" in str(values)


def test_bookmark_manager_refresh_populates_rows(tmp_path: Path) -> None:
    """_refresh inserts one row per stored bookmark."""
    from rbcopy.bookmarks import BookmarksStore

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("Alpha", r"C:\alpha")
    store.add_bookmark("Beta", r"C:\beta")

    win = _make_bookmark_manager_win(store)
    win._refresh()

    assert win._tree.insert.call_count == 2
    inserted_values = [call.kwargs.get("values", ()) for call in win._tree.insert.call_args_list]
    names = [v[0] for v in inserted_values]
    assert "Alpha" in names
    assert "Beta" in names


def test_bookmark_manager_delete_removes_selected(tmp_path: Path) -> None:
    """_delete removes the selected bookmark after confirmation."""
    from rbcopy.bookmarks import BookmarksStore

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("ToDelete", r"C:\gone")
    store.add_bookmark("Keep", r"C:\keep")

    win = _make_bookmark_manager_win(store)
    win._tree.selection.return_value = ("iid1",)
    win._tree.set = MagicMock(return_value="ToDelete")
    win._refresh = MagicMock()

    with patch("rbcopy.gui.bookmark_manager.messagebox.askyesno", return_value=True):
        win._delete()

    assert store.get_bookmark("ToDelete") is None
    assert store.get_bookmark("Keep") is not None
    win._on_change.assert_called_once()
    win._refresh.assert_called_once()


def test_bookmark_manager_delete_aborts_when_cancelled(tmp_path: Path) -> None:
    """_delete does nothing when the user cancels the confirmation dialog."""
    from rbcopy.bookmarks import BookmarksStore

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("Stay", r"C:\stay")

    win = _make_bookmark_manager_win(store)
    win._tree.selection.return_value = ("iid1",)
    win._tree.set = MagicMock(return_value="Stay")
    win._refresh = MagicMock()

    with patch("rbcopy.gui.bookmark_manager.messagebox.askyesno", return_value=False):
        win._delete()

    assert store.get_bookmark("Stay") is not None
    win._on_change.assert_not_called()
    win._refresh.assert_not_called()


def test_bookmark_manager_delete_noop_when_nothing_selected(tmp_path: Path) -> None:
    """_delete does nothing when no row is selected."""
    from rbcopy.bookmarks import BookmarksStore

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("A", r"C:\a")

    win = _make_bookmark_manager_win(store)
    # No selection
    win._tree.selection.return_value = ()
    win._refresh = MagicMock()

    win._delete()

    assert store.get_bookmark("A") is not None
    win._on_change.assert_not_called()


def test_bookmark_manager_move_up_reorders(tmp_path: Path) -> None:
    """_move_up shifts the selected bookmark one position towards the top."""
    from rbcopy.bookmarks import BookmarksStore

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("First", r"C:\first")
    store.add_bookmark("Second", r"C:\second")

    win = _make_bookmark_manager_win(store)
    win._tree.get_children.return_value = ("iid0", "iid1")
    win._tree.selection.return_value = ("iid1",)
    win._refresh = MagicMock()

    win._move_up()

    names = [b.name for b in store.get_bookmarks()]
    assert names == ["Second", "First"]
    win._on_change.assert_called_once()
    win._refresh.assert_called_once()


def test_bookmark_manager_move_up_noop_at_top(tmp_path: Path) -> None:
    """_move_up does nothing when the first item is already selected."""
    from rbcopy.bookmarks import BookmarksStore

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("First", r"C:\first")
    store.add_bookmark("Second", r"C:\second")

    win = _make_bookmark_manager_win(store)
    win._tree.get_children.return_value = ("iid0", "iid1")
    win._tree.selection.return_value = ("iid0",)
    win._refresh = MagicMock()

    win._move_up()

    names = [b.name for b in store.get_bookmarks()]
    assert names == ["First", "Second"]
    win._on_change.assert_not_called()


def test_bookmark_manager_move_down_reorders(tmp_path: Path) -> None:
    """_move_down shifts the selected bookmark one position towards the bottom."""
    from rbcopy.bookmarks import BookmarksStore

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("First", r"C:\first")
    store.add_bookmark("Second", r"C:\second")

    win = _make_bookmark_manager_win(store)
    win._tree.get_children.return_value = ("iid0", "iid1")
    win._tree.selection.return_value = ("iid0",)
    win._refresh = MagicMock()

    win._move_down()

    names = [b.name for b in store.get_bookmarks()]
    assert names == ["Second", "First"]
    win._on_change.assert_called_once()
    win._refresh.assert_called_once()


def test_bookmark_manager_move_down_noop_at_bottom(tmp_path: Path) -> None:
    """_move_down does nothing when the last item is already selected."""
    from rbcopy.bookmarks import BookmarksStore

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("First", r"C:\first")
    store.add_bookmark("Second", r"C:\second")

    win = _make_bookmark_manager_win(store)
    win._tree.get_children.return_value = ("iid0", "iid1")
    win._tree.selection.return_value = ("iid1",)
    win._refresh = MagicMock()

    win._move_down()

    names = [b.name for b in store.get_bookmarks()]
    assert names == ["First", "Second"]
    win._on_change.assert_not_called()


def test_bookmark_manager_set_as_source_calls_on_apply(tmp_path: Path) -> None:
    """_set_as_source calls on_apply with ('source', path)."""
    from rbcopy.bookmarks import BookmarksStore

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("MySrc", r"C:\my\src")

    win = _make_bookmark_manager_win(store)
    win._tree.selection.return_value = ("iid1",)
    win._tree.set = MagicMock(return_value="MySrc")

    win._set_as_source()

    win._on_apply.assert_called_once_with("source", r"C:\my\src")


def test_bookmark_manager_set_as_destination_calls_on_apply(tmp_path: Path) -> None:
    """_set_as_destination calls on_apply with ('destination', path)."""
    from rbcopy.bookmarks import BookmarksStore

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("MyDst", r"C:\my\dst")

    win = _make_bookmark_manager_win(store)
    win._tree.selection.return_value = ("iid1",)
    win._tree.set = MagicMock(return_value="MyDst")

    win._set_as_destination()

    win._on_apply.assert_called_once_with("destination", r"C:\my\dst")


def test_bookmark_manager_set_as_source_noop_when_no_selection(tmp_path: Path) -> None:
    """_set_as_source does nothing when no row is selected."""
    from rbcopy.bookmarks import BookmarksStore

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    win = _make_bookmark_manager_win(store)
    win._tree.selection.return_value = ()

    win._set_as_source()

    win._on_apply.assert_not_called()


def test_bookmark_manager_add_calls_store_and_notifies(tmp_path: Path) -> None:
    """_add calls add_bookmark and notifies on_change when the dialog is confirmed."""
    from rbcopy.bookmarks import BookmarksStore
    from rbcopy.gui.bookmark_manager import _EditBookmarkDialog

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    win = _make_bookmark_manager_win(store)
    win._refresh = MagicMock()
    win._select_by_name = MagicMock()

    mock_dlg = MagicMock(spec=_EditBookmarkDialog)
    mock_dlg.name = "NewBM"
    mock_dlg.path = r"C:\new\path"

    with patch("rbcopy.gui.bookmark_manager._EditBookmarkDialog", return_value=mock_dlg):
        win._add()

    assert store.get_bookmark("NewBM") is not None
    assert store.get_bookmark("NewBM").path == r"C:\new\path"
    win._on_change.assert_called_once()
    win._refresh.assert_called_once()


def test_bookmark_manager_add_cancelled_when_name_is_none(tmp_path: Path) -> None:
    """_add does nothing when the dialog is cancelled (name is None)."""
    from rbcopy.bookmarks import BookmarksStore
    from rbcopy.gui.bookmark_manager import _EditBookmarkDialog

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    win = _make_bookmark_manager_win(store)
    win._refresh = MagicMock()

    mock_dlg = MagicMock(spec=_EditBookmarkDialog)
    mock_dlg.name = None

    with patch("rbcopy.gui.bookmark_manager._EditBookmarkDialog", return_value=mock_dlg):
        win._add()

    assert store.get_bookmarks() == []
    win._on_change.assert_not_called()
    win._refresh.assert_not_called()


def test_bookmark_manager_edit_updates_name_and_path(tmp_path: Path) -> None:
    """_edit replaces the selected bookmark's name and path in place."""
    from rbcopy.bookmarks import BookmarksStore
    from rbcopy.gui.bookmark_manager import _EditBookmarkDialog

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("OldName", r"C:\old")

    win = _make_bookmark_manager_win(store)
    win._tree.selection.return_value = ("iid1",)
    win._tree.set = MagicMock(return_value="OldName")
    win._refresh = MagicMock()
    win._select_by_name = MagicMock()

    mock_dlg = MagicMock(spec=_EditBookmarkDialog)
    mock_dlg.name = "NewName"
    mock_dlg.path = r"C:\new"

    with patch("rbcopy.gui.bookmark_manager._EditBookmarkDialog", return_value=mock_dlg):
        win._edit()

    assert store.get_bookmark("OldName") is None
    assert store.get_bookmark("NewName") is not None
    assert store.get_bookmark("NewName").path == r"C:\new"
    win._on_change.assert_called_once()
    win._refresh.assert_called_once()


def test_bookmark_manager_edit_cancelled_does_nothing(tmp_path: Path) -> None:
    """_edit makes no changes when the dialog is cancelled."""
    from rbcopy.bookmarks import BookmarksStore
    from rbcopy.gui.bookmark_manager import _EditBookmarkDialog

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("Stay", r"C:\stay")

    win = _make_bookmark_manager_win(store)
    win._tree.selection.return_value = ("iid1",)
    win._tree.set = MagicMock(return_value="Stay")
    win._refresh = MagicMock()

    mock_dlg = MagicMock(spec=_EditBookmarkDialog)
    mock_dlg.name = None

    with patch("rbcopy.gui.bookmark_manager._EditBookmarkDialog", return_value=mock_dlg):
        win._edit()

    assert store.get_bookmark("Stay") is not None
    win._on_change.assert_not_called()
    win._refresh.assert_not_called()


def test_rebuild_bookmarks_menu_includes_manage_bookmarks() -> None:
    """_rebuild_bookmarks_menu must always add a 'Manage Bookmarks…' entry."""
    from rbcopy.bookmarks import BookmarksStore

    fake = _make_fake_self()
    fake._bookmarks_store = MagicMock(spec=BookmarksStore)
    fake._bookmarks_store.get_bookmarks.return_value = []
    fake._bookmarks_menu = MagicMock()

    RobocopyGUI._rebuild_bookmarks_menu(fake)

    labels = [call.kwargs.get("label", "") for call in fake._bookmarks_menu.add_command.call_args_list]
    assert any("Manage Bookmarks" in label for label in labels)


# ---------------------------------------------------------------------------
# _import_exclusions_from_file tests
# ---------------------------------------------------------------------------


def _make_import_vars() -> tuple[MagicMock, MagicMock, MagicMock]:
    """Return (enabled_var, value_var, entry) mocks for import tests."""
    enabled_var = MagicMock()
    enabled_var.get.return_value = False
    value_var = MagicMock()
    value_var.get.return_value = ""
    entry = MagicMock()
    return enabled_var, value_var, entry


def test_import_exclusions_cancels_when_no_file_selected() -> None:
    """Cancelling the file dialog must leave vars untouched."""
    fake = _make_fake_self()
    enabled_var, value_var, entry = _make_import_vars()

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=""):
        RobocopyGUI._import_exclusions_from_file(fake, "/XF", enabled_var, value_var, entry)

    value_var.set.assert_not_called()
    enabled_var.set.assert_not_called()
    entry.config.assert_not_called()


def test_import_exclusions_sets_patterns_into_empty_field(tmp_path: Path) -> None:
    """Patterns from the file are written to value_var when the field is empty."""
    txt = tmp_path / "exclusions.txt"
    txt.write_text("*.tmp\n*.bak\n", encoding="utf-8")

    fake = _make_fake_self()
    enabled_var, value_var, entry = _make_import_vars()

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)):
        RobocopyGUI._import_exclusions_from_file(fake, "/XF", enabled_var, value_var, entry)

    value_var.set.assert_called_once_with("*.tmp *.bak")
    enabled_var.set.assert_called_once_with(True)
    entry.config.assert_called_once_with(state="normal")


def test_import_exclusions_appends_to_existing_value(tmp_path: Path) -> None:
    """New patterns are appended to whatever is already in value_var."""
    txt = tmp_path / "exclusions.txt"
    txt.write_text("*.iso\n", encoding="utf-8")

    fake = _make_fake_self()
    enabled_var, value_var, entry = _make_import_vars()
    value_var.get.return_value = "*.img"

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)):
        RobocopyGUI._import_exclusions_from_file(fake, "/XF", enabled_var, value_var, entry)

    value_var.set.assert_called_once_with("*.img *.iso")


def test_import_exclusions_skips_blank_and_comment_lines(tmp_path: Path) -> None:
    """Blank lines and '#' comment lines must not be imported as patterns."""
    txt = tmp_path / "exclusions.txt"
    txt.write_text("# this is a comment\n\n*.log\n  \n# another comment\n*.tmp\n", encoding="utf-8")

    fake = _make_fake_self()
    enabled_var, value_var, entry = _make_import_vars()

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)):
        RobocopyGUI._import_exclusions_from_file(fake, "/XD", enabled_var, value_var, entry)

    value_var.set.assert_called_once_with("*.log *.tmp")


def test_import_exclusions_shows_info_when_file_has_no_usable_patterns(tmp_path: Path) -> None:
    """An info dialog is shown when every line in the file is blank or a comment."""
    txt = tmp_path / "exclusions.txt"
    txt.write_text("# only comments\n\n# another\n", encoding="utf-8")

    fake = _make_fake_self()
    enabled_var, value_var, entry = _make_import_vars()

    with (
        patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)),
        patch("rbcopy.gui.main_window.messagebox.showinfo") as mock_info,
    ):
        RobocopyGUI._import_exclusions_from_file(fake, "/XF", enabled_var, value_var, entry)

    mock_info.assert_called_once()
    value_var.set.assert_not_called()
    enabled_var.set.assert_not_called()


def test_import_exclusions_shows_error_on_read_failure(tmp_path: Path) -> None:
    """An error dialog is shown when the chosen file cannot be read."""
    fake = _make_fake_self()
    enabled_var, value_var, entry = _make_import_vars()

    with (
        patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(tmp_path / "missing.txt")),
        patch("rbcopy.gui.main_window.messagebox.showerror") as mock_err,
    ):
        RobocopyGUI._import_exclusions_from_file(fake, "/XF", enabled_var, value_var, entry)

    mock_err.assert_called_once()
    value_var.set.assert_not_called()
    enabled_var.set.assert_not_called()


def test_import_exclusions_method_exists() -> None:
    """RobocopyGUI must expose a callable _import_exclusions_from_file method."""
    assert callable(RobocopyGUI._import_exclusions_from_file)


# ---------------------------------------------------------------------------
# _import_file_filter_from_file tests
# ---------------------------------------------------------------------------


def test_import_file_filter_method_exists() -> None:
    """RobocopyGUI must expose a callable _import_file_filter_from_file method."""
    assert callable(RobocopyGUI._import_file_filter_from_file)


def test_import_file_filter_cancels_when_no_file_selected() -> None:
    """Cancelling the file dialog must leave file filter vars untouched."""
    fake = _make_fake_self()

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=""):
        RobocopyGUI._import_file_filter_from_file(fake)

    fake._file_filter_var.set.assert_not_called()
    fake._file_filter_enabled_var.set.assert_not_called()


def test_import_file_filter_sets_patterns_into_empty_field(tmp_path: Path) -> None:
    """Patterns from the file are written to _file_filter_var when field is empty."""
    txt = tmp_path / "includes.txt"
    txt.write_text("*.img\n*.raw\n", encoding="utf-8")

    fake = _make_fake_self()
    fake._file_filter_var.get.return_value = ""
    fake._file_filter_entry = MagicMock()

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)):
        RobocopyGUI._import_file_filter_from_file(fake)

    fake._file_filter_var.set.assert_called_once_with("*.img *.raw")
    fake._file_filter_enabled_var.set.assert_called_once_with(True)
    fake._file_filter_entry.config.assert_called_once_with(state="normal")


def test_import_file_filter_appends_to_existing_value(tmp_path: Path) -> None:
    """New patterns are appended to whatever is already in _file_filter_var."""
    txt = tmp_path / "includes.txt"
    txt.write_text("*.iso\n", encoding="utf-8")

    fake = _make_fake_self()
    fake._file_filter_var.get.return_value = "*.img"
    fake._file_filter_entry = MagicMock()

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)):
        RobocopyGUI._import_file_filter_from_file(fake)

    fake._file_filter_var.set.assert_called_once_with("*.img *.iso")


def test_import_file_filter_skips_blank_and_comment_lines(tmp_path: Path) -> None:
    """Blank lines and '#' comment lines must not be imported as patterns."""
    txt = tmp_path / "includes.txt"
    txt.write_text("# header\n\n*.zip\n  \n# note\n*.tar\n", encoding="utf-8")

    fake = _make_fake_self()
    fake._file_filter_var.get.return_value = ""
    fake._file_filter_entry = MagicMock()

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)):
        RobocopyGUI._import_file_filter_from_file(fake)

    fake._file_filter_var.set.assert_called_once_with("*.zip *.tar")


def test_import_file_filter_shows_info_when_no_usable_patterns(tmp_path: Path) -> None:
    """An info dialog is shown when every line is blank or a comment."""
    txt = tmp_path / "includes.txt"
    txt.write_text("# only comments\n\n", encoding="utf-8")

    fake = _make_fake_self()
    fake._file_filter_var.get.return_value = ""
    fake._file_filter_entry = MagicMock()

    with (
        patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)),
        patch("rbcopy.gui.main_window.messagebox.showinfo") as mock_info,
    ):
        RobocopyGUI._import_file_filter_from_file(fake)

    mock_info.assert_called_once()
    fake._file_filter_var.set.assert_not_called()
    fake._file_filter_enabled_var.set.assert_not_called()


def test_import_file_filter_shows_error_on_read_failure(tmp_path: Path) -> None:
    """An error dialog is shown when the chosen file cannot be read."""
    fake = _make_fake_self()
    fake._file_filter_var.get.return_value = ""
    fake._file_filter_entry = MagicMock()

    with (
        patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(tmp_path / "missing.txt")),
        patch("rbcopy.gui.main_window.messagebox.showerror") as mock_err,
    ):
        RobocopyGUI._import_file_filter_from_file(fake)

    mock_err.assert_called_once()
    fake._file_filter_var.set.assert_not_called()
    fake._file_filter_enabled_var.set.assert_not_called()


# ---------------------------------------------------------------------------
# Quoting and encoding tests shared by both import helpers
# ---------------------------------------------------------------------------


def test_import_exclusions_quotes_patterns_with_spaces(tmp_path: Path) -> None:
    """Patterns containing spaces must be wrapped in double-quotes."""
    txt = tmp_path / "exclusions.txt"
    txt.write_text("My Folder\nnormal\nAnother Dir\n", encoding="utf-8")

    fake = _make_fake_self()
    enabled_var, value_var, entry = _make_import_vars()

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)):
        RobocopyGUI._import_exclusions_from_file(fake, "/XD", enabled_var, value_var, entry)

    value_var.set.assert_called_once_with('"My Folder" normal "Another Dir"')


def test_import_exclusions_does_not_double_quote_already_quoted(tmp_path: Path) -> None:
    """Patterns already wrapped in double-quotes must not be quoted again."""
    txt = tmp_path / "exclusions.txt"
    txt.write_text('"Already Quoted"\nnormal\n', encoding="utf-8")

    fake = _make_fake_self()
    enabled_var, value_var, entry = _make_import_vars()

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)):
        RobocopyGUI._import_exclusions_from_file(fake, "/XD", enabled_var, value_var, entry)

    value_var.set.assert_called_once_with('"Already Quoted" normal')


def test_import_exclusions_handles_unicode_decode_error(tmp_path: Path) -> None:
    """A UnicodeDecodeError when reading the file must show an error dialog."""
    txt = tmp_path / "exclusions.txt"
    txt.write_bytes(b"\xff\xfe invalid utf-8 \x00")

    fake = _make_fake_self()
    enabled_var, value_var, entry = _make_import_vars()

    with (
        patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)),
        patch("rbcopy.gui.main_window.messagebox.showerror") as mock_err,
    ):
        RobocopyGUI._import_exclusions_from_file(fake, "/XF", enabled_var, value_var, entry)

    mock_err.assert_called_once()
    value_var.set.assert_not_called()


def test_import_file_filter_quotes_patterns_with_spaces(tmp_path: Path) -> None:
    """File filter patterns containing spaces must be wrapped in double-quotes."""
    txt = tmp_path / "filters.txt"
    txt.write_text("My Report.docx\nplain.txt\n", encoding="utf-8")

    fake = _make_fake_self()
    fake._file_filter_var.get.return_value = ""
    fake._file_filter_entry = MagicMock()

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)):
        RobocopyGUI._import_file_filter_from_file(fake)

    fake._file_filter_var.set.assert_called_once_with('"My Report.docx" plain.txt')


def test_import_file_filter_handles_unicode_decode_error(tmp_path: Path) -> None:
    """A UnicodeDecodeError when reading the file must show an error dialog."""
    txt = tmp_path / "filters.txt"
    txt.write_bytes(b"\xff\xfe invalid utf-8 \x00")

    fake = _make_fake_self()
    fake._file_filter_var.get.return_value = ""
    fake._file_filter_entry = MagicMock()

    with (
        patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)),
        patch("rbcopy.gui.main_window.messagebox.showerror") as mock_err,
    ):
        RobocopyGUI._import_file_filter_from_file(fake)

    mock_err.assert_called_once()
    fake._file_filter_var.set.assert_not_called()
