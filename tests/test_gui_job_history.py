"""Tests for _JobHistoryWindow (rbcopy.gui.job_history)."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


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
