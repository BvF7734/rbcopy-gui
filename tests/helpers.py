"""Shared test helpers for the rbcopy test suite."""

from __future__ import annotations

import queue
import threading
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock



def make_mock_async_proc(
    returncode: int = 0,
    output: str = "",
    pid: int | None = None,
) -> MagicMock:
    """Return a MagicMock that mimics asyncio.subprocess.Process for robocopy streaming.

    Args:
        returncode: The exit code the mock process should report.
        output: The stdout content the mock process should yield, as a plain string.
        pid: Optional PID to assign to the mock process.
    """
    mock_proc = MagicMock()
    mock_proc.returncode = returncode
    if pid is not None:
        mock_proc.pid = pid

    # Encode output lines as bytes to match asyncio subprocess byte output.
    lines = [line.encode("utf-8") for line in output.splitlines(keepends=True)]

    async def _aiter_stdout() -> AsyncGenerator[bytes, None]:
        for line in lines:
            yield line

    mock_proc.stdout = _aiter_stdout()
    mock_proc.wait = AsyncMock(return_value=returncode)
    return mock_proc


def make_fake_self() -> MagicMock:
    """Return a MagicMock suitable as a fake 'self' for RobocopyGUI methods."""
    from rbcopy.gui import RobocopyGUI

    fake: MagicMock = MagicMock()
    fake._output_queue = queue.Queue()
    fake._dropped_lines = 0
    fake._last_reported_drops = 0
    fake._dropped_lines_lock = threading.Lock()

    def _fake_append_output(text: str, block: bool = False) -> None:
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

    fake._append_output.side_effect = _fake_append_output
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
    fake._get_selections.return_value = ({}, {})
    fake.src_var.get.return_value = ""
    fake.dst_var.get.return_value = ""
    return fake


def drain_queue(q: queue.Queue) -> list[str]:
    """Drain all items from a queue and return them as a list."""
    items: list[str] = []
    while not q.empty():
        items.append(q.get_nowait())
    return items


class StringVarStub:
    """Minimal StringVar replacement that does not require a live Tk root."""

    def __init__(self, value: str = "") -> None:
        self._value = value

    def get(self) -> str:
        return self._value

    def set(self, value: str) -> None:
        self._value = value

    def trace_add(self, *args: object, **kwargs: object) -> None:
        """No-op: traces are not exercised in unit tests."""


def make_sync_thread(*_args: Any, **kwargs: Any) -> MagicMock:
    """Thread factory that runs the target synchronously on ``start()``."""
    target = kwargs.get("target")
    thread_args = kwargs.get("args", ())
    m = MagicMock()
    if target is not None:
        m.start.side_effect = lambda: target(*thread_args)
    return m
