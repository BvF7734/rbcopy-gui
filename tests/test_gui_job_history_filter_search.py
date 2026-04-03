"""Tests for _JobHistoryWindow filter and search (rbcopy.gui.job_history)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch


from tests.helpers import make_sync_thread as _make_sync_thread, StringVarStub as _StringVarStub


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
