"""Tests for _JobHistoryWindow parse and on-select helpers (rbcopy.gui.job_history)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import StringVarStub as _StringVarStub

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


