"""Tests for _JobHistoryWindow._refresh (rbcopy.gui.job_history)."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch


from tests.helpers import make_sync_thread as _make_sync_thread, StringVarStub as _StringVarStub


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
