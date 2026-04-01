"""Tests for the async subprocess bridge and output-queue logic in main_window.py.

This suite stress-tests the background thread that streams robocopy output into
the bounded ``_output_queue`` without actually launching ``robocopy.exe``.  All
subprocess I/O is replaced with fully in-process async generators so the tests
run on any platform at full CPU speed.

Coverage goals
--------------
1. **Successful run (exit code 1 – Files Copied)** – verify that every decoded
   stdout line produced by the mock process lands in ``_output_queue`` as a
   ``str``, and that the exit-code footer is appended.
2. **Queue-overflow stress test** – verify that when the consumer (Tkinter main
   thread) cannot drain the queue fast enough, ``_async_execute`` gracefully
   increments ``_dropped_lines`` instead of raising ``queue.Full`` or stalling
   the asyncio event loop.
"""

from __future__ import annotations

import asyncio
import queue
import threading
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch


from rbcopy.gui.main_window import RobocopyGUI, _OUTPUT_QUEUE_MAXSIZE
from tests.helpers import make_mock_async_proc

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

# A representative robocopy stdout for a single-file copy job that exits with
# code 1 (at least one file was copied successfully).
_ROBOCOPY_EXIT_1_OUTPUT: str = (
    "-------------------------------------------------------------------------------\n"
    "   ROBOCOPY     ::     Robust File Copy for Windows\n"
    "-------------------------------------------------------------------------------\n"
    "\n"
    "  Started : Tuesday, April 1, 2026 10:00:00 AM\n"
    "   Source : C:\\src\\\n"
    "     Dest : C:\\dst\\\n"
    "\n"
    "    Files : *.*\n"
    "\n"
    "    New File              1024  important_document.txt\n"
    "    New File               512  image.png\n"
    "\n"
    "   Ended : Tuesday, April 1, 2026 10:00:01 AM\n"
)


def _make_fake_self(queue_maxsize: int = _OUTPUT_QUEUE_MAXSIZE) -> MagicMock:
    """Return a MagicMock suitable as 'self' for ``RobocopyGUI._async_execute``.

    A real ``queue.Queue`` with a configurable bounded ``maxsize`` is wired in
    so that overflow behaviour (``queue.Full``) is exercised faithfully.  The
    ``_append_output`` side-effect mirrors the eviction strategy used by the
    real implementation: when ``block=True`` and the queue is full, the oldest
    item is evicted and ``_dropped_lines`` is incremented.

    Args:
        queue_maxsize: ``maxsize`` passed to ``queue.Queue``.  Defaults to the
            production constant ``_OUTPUT_QUEUE_MAXSIZE`` (5000).  Pass a
            smaller value in stress tests to trigger overflow quickly.
    """
    fake: MagicMock = MagicMock()
    fake._output_queue = queue.Queue(maxsize=queue_maxsize)
    fake._dropped_lines = 0
    fake._last_reported_drops = 0
    fake._dropped_lines_lock = threading.Lock()
    fake._shutdown = threading.Event()
    fake._current_proc = None

    def _fake_append_output(text: str, block: bool = False) -> None:
        # Mirror the production eviction strategy so that critical messages
        # (exit-code footer, error notices) always reach the consumer even
        # when the queue is at capacity.
        if block:
            if fake._shutdown.is_set():
                return
            try:
                fake._output_queue.put_nowait(text)
            except queue.Full:
                # Evict the oldest line to make room, counting it as dropped.
                try:
                    fake._output_queue.get_nowait()
                    with fake._dropped_lines_lock:
                        fake._dropped_lines += 1
                except queue.Empty:
                    pass  # Queue was concurrently drained; no eviction needed.
                try:
                    fake._output_queue.put_nowait(text)
                except queue.Full:
                    # Queue refilled between eviction and re-insert; count drop.
                    with fake._dropped_lines_lock:
                        fake._dropped_lines += 1
        else:
            try:
                fake._output_queue.put_nowait(text)
            except queue.Full:
                with fake._dropped_lines_lock:
                    fake._dropped_lines += 1

    fake._append_output.side_effect = _fake_append_output
    return fake


def _drain_queue(q: "queue.Queue[str]") -> List[str]:
    """Drain and return all items currently in *q* without blocking."""
    items: List[str] = []
    while not q.empty():
        items.append(q.get_nowait())
    return items


# ---------------------------------------------------------------------------
# Test 1 – Successful run: exit code 1 (Files Copied)
# ---------------------------------------------------------------------------


def test_async_execute_returncode_1_queues_decoded_lines() -> None:
    """_async_execute places every decoded stdout line into _output_queue.

    Exit code 1 is the most common real-world outcome: robocopy copied at
    least one file successfully.  The test verifies that:

    * Each line from the mock stdout arrives in the queue as a ``str``
      (not as raw ``bytes``), confirming the ``decode()`` step runs.
    * Representative header and file-listing lines are all present.
    * The ``[Process exited with code 1]`` footer generated inside
      ``_async_execute`` is also enqueued.
    * No lines were dropped (the output fits within ``_OUTPUT_QUEUE_MAXSIZE``).
    """
    fake_self = _make_fake_self()
    mock_proc = make_mock_async_proc(
        returncode=1,
        output=_ROBOCOPY_EXIT_1_OUTPUT,
        pid=9001,
    )

    with (
        patch(
            "rbcopy.gui.main_window.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ),
        patch("rbcopy.gui.main_window.notify_job_complete"),
    ):
        asyncio.run(
            RobocopyGUI._async_execute(
                fake_self,
                ["robocopy", "C:\\src", "C:\\dst"],
            )
        )

    items = _drain_queue(fake_self._output_queue)

    # ── Every item must be a plain str, not bytes ──────────────────────────
    assert all(isinstance(item, str) for item in items), (
        "All items in _output_queue must be str; "
        f"got types: {[type(i).__name__ for i in items if not isinstance(i, str)]}"
    )

    # ── Key output lines must survive into the queue ───────────────────────
    assert any("ROBOCOPY" in line for line in items), "Robocopy banner line was not found in the output queue."
    assert any("important_document.txt" in line for line in items), (
        "File-listing line for 'important_document.txt' missing from queue."
    )
    assert any("image.png" in line for line in items), "File-listing line for 'image.png' missing from queue."

    # ── Exit-code footer must be present ──────────────────────────────────
    assert any("Process exited with code 1" in line for line in items), (
        "Exit-code footer '[Process exited with code 1]' not found in queue."
    )

    # ── Nothing should have been dropped for this small output ────────────
    assert fake_self._dropped_lines == 0, f"Expected 0 dropped lines but got {fake_self._dropped_lines}."


# ---------------------------------------------------------------------------
# Test 2 – Stress test: queue overflow increments _dropped_lines, no crash
# ---------------------------------------------------------------------------

# Number of lines to emit *beyond* the tiny test queue's capacity.
_OVERFLOW_AMOUNT: int = 50
# Deliberately small so the overflow triggers without emitting thousands of
# lines, keeping the test fast while still exercising the drop-counter path.
_STRESS_QUEUE_SIZE: int = 10


def test_async_execute_stress_overflow_increments_dropped_lines() -> None:
    """_dropped_lines is incremented for every line that cannot fit in the queue.

    Simulates a robocopy job that emits output faster than the Tkinter main
    thread can consume it, by:

    * Setting up a very small bounded queue (``_STRESS_QUEUE_SIZE`` slots).
    * Feeding ``_STRESS_QUEUE_SIZE + _OVERFLOW_AMOUNT`` lines through the mock
      stdout without ever draining the queue on the consumer side.

    Acceptance criteria:
    * ``asyncio.run()`` returns normally — no ``queue.Full`` is propagated and
      the event loop is never deadlocked.
    * ``_dropped_lines`` is at least ``_OVERFLOW_AMOUNT``, confirming that all
      excess lines were silently counted rather than raised as exceptions.
    * The queue itself holds exactly ``_STRESS_QUEUE_SIZE`` items (it is full
      but not overflowed in memory).
    """
    total_lines = _STRESS_QUEUE_SIZE + _OVERFLOW_AMOUNT
    # Build a burst of unique file-copy lines so every line is identifiable.
    burst_output: str = "".join(
        f"    New File            {i:08d}  stress_file_{i:06d}.dat\n" for i in range(total_lines)
    )

    # Use a tiny bounded queue to force overflow quickly.
    fake_self = _make_fake_self(queue_maxsize=_STRESS_QUEUE_SIZE)
    mock_proc = make_mock_async_proc(returncode=1, output=burst_output, pid=1337)

    # The queue is intentionally NOT drained during execution to simulate a
    # slow UI thread that cannot keep up with the subprocess output rate.
    with (
        patch(
            "rbcopy.gui.main_window.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ),
        patch("rbcopy.gui.main_window.notify_job_complete"),
    ):
        # This must complete without raising any exception.
        asyncio.run(
            RobocopyGUI._async_execute(
                fake_self,
                ["robocopy", "C:\\src", "C:\\dst"],
            )
        )

    # ── No lines must escape the queue as exceptions ───────────────────────
    # (asyncio.run() returning normally is the implicit assertion above.)

    # ── Overflow lines must be counted, not raised ─────────────────────────
    # _dropped_lines counts lines dropped during streaming.  The
    # _append_output(block=True) eviction path for the exit-code footer may
    # add one extra drop, so >= is the correct comparison.
    assert fake_self._dropped_lines >= _OVERFLOW_AMOUNT, (
        f"Expected _dropped_lines >= {_OVERFLOW_AMOUNT} but got {fake_self._dropped_lines}."
    )

    # ── Queue is full but not over-allocated in memory ─────────────────────
    # The eviction strategy for the exit-code footer keeps the item count at
    # exactly _STRESS_QUEUE_SIZE (one eviction, one insert).
    assert fake_self._output_queue.qsize() == _STRESS_QUEUE_SIZE, (
        f"Expected queue size {_STRESS_QUEUE_SIZE} but got {fake_self._output_queue.qsize()}."
    )


# ---------------------------------------------------------------------------
# Test 3 – _dropped_lines type safety: always an int after overflow
# ---------------------------------------------------------------------------


def test_dropped_lines_remains_int_after_stress() -> None:
    """_dropped_lines must be an int (not a MagicMock attribute) after overflow.

    Guards against regressions where the MagicMock setup accidentally shadows
    the integer with a mock object, causing silent failures in downstream code
    that compares ``_dropped_lines`` numerically (e.g. ``_poll_output``).
    """
    total_lines = _STRESS_QUEUE_SIZE + _OVERFLOW_AMOUNT
    burst_output = "".join(f"line {i}\n" for i in range(total_lines))
    fake_self = _make_fake_self(queue_maxsize=_STRESS_QUEUE_SIZE)
    mock_proc = make_mock_async_proc(returncode=1, output=burst_output, pid=42)

    with (
        patch(
            "rbcopy.gui.main_window.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ),
        patch("rbcopy.gui.main_window.notify_job_complete"),
    ):
        asyncio.run(
            RobocopyGUI._async_execute(
                fake_self,
                ["robocopy", "C:\\src", "C:\\dst"],
            )
        )

    assert isinstance(fake_self._dropped_lines, int), (
        f"_dropped_lines must be int; got {type(fake_self._dropped_lines).__name__}."
    )
    assert fake_self._dropped_lines > 0
