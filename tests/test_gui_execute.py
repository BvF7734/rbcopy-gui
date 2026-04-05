"""Tests for RobocopyGUI._execute and output helpers (rbcopy.gui.main_window)."""

from __future__ import annotations

import asyncio
import queue
from unittest.mock import AsyncMock, MagicMock, patch


from rbcopy.gui import RobocopyGUI
from rbcopy.gui.main_window import _MAX_LINES_PER_POLL, _OUTPUT_QUEUE_MAXSIZE
from tests.helpers import drain_queue as _drain_queue, make_fake_self as _make_fake_self, make_mock_async_proc


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


def test_async_execute_flushes_path_history_in_finally() -> None:
    """_async_execute must flush path history in its finally block after every job.

    Flushing in the finally block (rather than only in _exit) ensures that
    paths added by _run/_dry_run survive a crash that bypasses the normal
    exit path.
    """
    fake_self = _make_fake_self()
    mock_proc = make_mock_async_proc(returncode=0, output="", pid=42)

    with patch("rbcopy.gui.main_window.asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        with patch("rbcopy.gui.main_window.notify_job_complete"):
            asyncio.run(RobocopyGUI._async_execute(fake_self, ["robocopy", "C:/src", "C:/dst"]))

    fake_self._path_history.flush.assert_called()


def test_async_execute_flushes_path_history_even_on_exception() -> None:
    """_async_execute must flush path history even when the subprocess raises."""
    fake_self = _make_fake_self()

    with patch("rbcopy.gui.main_window.asyncio.create_subprocess_exec", new=AsyncMock(side_effect=OSError("boom"))):
        with patch("rbcopy.gui.main_window.notify_job_complete"):
            asyncio.run(RobocopyGUI._async_execute(fake_self, ["robocopy", "C:/src", "C:/dst"]))

    fake_self._path_history.flush.assert_called()


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
# _execute non-shutdown path (line 1641)
# ---------------------------------------------------------------------------


def test_execute_calls_asyncio_run_when_not_shutdown() -> None:
    """_execute calls asyncio.run() when the shutdown flag is not set."""
    fake_self = _make_fake_self()
    # shutdown NOT set → should proceed to asyncio.run()

    with patch("rbcopy.gui.main_window.asyncio.run") as mock_run:
        RobocopyGUI._execute(fake_self, ["robocopy", "C:/src", "C:/dst"])

    mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# /NJH and /NJS timestamp logging (lines 1662, 1715)
# ---------------------------------------------------------------------------


def test_async_execute_logs_job_started_when_njh_flag_present() -> None:
    """/NJH in cmd triggers a 'Job started' logger.info message."""
    fake_self = _make_fake_self()
    mock_proc = make_mock_async_proc(returncode=0, output="", pid=10)

    with (
        patch("rbcopy.gui.main_window.asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)),
        patch("rbcopy.gui.main_window.notify_job_complete"),
        patch("rbcopy.gui.main_window.logger") as mock_logger,
    ):
        asyncio.run(RobocopyGUI._async_execute(fake_self, ["robocopy", "C:/src", "C:/dst", "/NJH"]))

    info_calls = [str(c) for c in mock_logger.info.call_args_list]
    assert any("Job started" in call for call in info_calls)


def test_async_execute_logs_job_ended_when_njs_flag_present() -> None:
    """/NJS in cmd triggers a 'Job ended' logger.info message."""
    fake_self = _make_fake_self()
    mock_proc = make_mock_async_proc(returncode=0, output="", pid=11)

    with (
        patch("rbcopy.gui.main_window.asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)),
        patch("rbcopy.gui.main_window.notify_job_complete"),
        patch("rbcopy.gui.main_window.logger") as mock_logger,
    ):
        asyncio.run(RobocopyGUI._async_execute(fake_self, ["robocopy", "C:/src", "C:/dst", "/NJS"]))

    info_calls = [str(c) for c in mock_logger.info.call_args_list]
    assert any("Job ended" in call for call in info_calls)


# ---------------------------------------------------------------------------
# _append_output edge cases (lines 1841-1848, 1852-1854)
# ---------------------------------------------------------------------------


def test_append_output_block_true_increments_dropped_lines_when_eviction_fails() -> None:
    """_append_output(block=True) increments _dropped_lines when get_nowait races to Empty."""
    fake_self = _make_fake_self()
    # Simulate a queue that is full on put_nowait, then empty on get_nowait (race),
    # then full again on the retry put_nowait.
    mock_q: MagicMock = MagicMock()
    mock_q.put_nowait.side_effect = [queue.Full, queue.Full]
    mock_q.get_nowait.side_effect = queue.Empty  # concurrent drain happened
    fake_self._output_queue = mock_q  # type: ignore[assignment]
    fake_self._dropped_lines = 0

    RobocopyGUI._append_output(fake_self, "critical\n", block=True)

    # The retry put_nowait also raised Full → line was dropped.
    assert fake_self._dropped_lines >= 1


def test_append_output_block_true_increments_dropped_when_retry_put_fails() -> None:
    """_append_output(block=True) drops the line when eviction succeeds but retry put fails."""
    fake_self = _make_fake_self()
    # put_nowait: first call → Full; second call → still Full
    mock_q: MagicMock = MagicMock()
    mock_q.put_nowait.side_effect = [queue.Full, queue.Full]
    mock_q.get_nowait.return_value = "evicted_line\n"  # eviction succeeds
    fake_self._output_queue = mock_q  # type: ignore[assignment]
    fake_self._dropped_lines = 0

    RobocopyGUI._append_output(fake_self, "msg\n", block=True)

    # evicted line increments _dropped_lines, then retry also fails → two increments
    assert fake_self._dropped_lines >= 2


def test_append_output_non_block_increments_dropped_when_queue_full() -> None:
    """_append_output(block=False) increments _dropped_lines when the queue is full."""
    fake_self = _make_fake_self()
    fake_self._output_queue = queue.Queue(maxsize=1)
    fake_self._output_queue.put_nowait("existing\n")
    fake_self._dropped_lines = 0

    RobocopyGUI._append_output(fake_self, "overflow\n", block=False)

    assert fake_self._dropped_lines == 1


# ---------------------------------------------------------------------------
# _poll_output: dropped-lines notice cannot be enqueued (lines 1887-1890)
# ---------------------------------------------------------------------------


def test_poll_output_does_not_advance_watermark_when_notice_enqueue_fails() -> None:
    """_poll_output must NOT advance _last_reported_drops when the notice cannot be queued."""
    fake_self = _make_fake_self()
    fake_self._dropped_lines = 5
    fake_self._last_reported_drops = 0

    # Use a real empty queue so draining succeeds; then replace it with a mock
    # that raises queue.Full on put_nowait for the dropped-lines notice.
    mock_q: MagicMock = MagicMock()
    mock_q.get_nowait.side_effect = queue.Empty  # nothing to drain
    mock_q.put_nowait.side_effect = queue.Full  # notice cannot be queued
    fake_self._output_queue = mock_q  # type: ignore[assignment]

    RobocopyGUI._poll_output(fake_self)

    # Watermark must NOT have been advanced since the notice was not delivered.
    assert fake_self._last_reported_drops == 0
