"""Tests for _JobHistoryWindow filter and search (rbcopy.gui.job_history)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch


from tests.helpers import make_sync_thread as _make_sync_thread, StringVarStub as _StringVarStub

from rbcopy.gui.job_history import _JobHistoryWindow


def test_job_history_filter_hides_non_matching_rows(tmp_path: Path) -> None:
    """Rows whose date string does not contain the keyword are hidden."""

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
# _apply_tree_filter edge cases (lines 255-256, 261, 265-267, 281-283)
# ---------------------------------------------------------------------------


def _make_filter_win(tmp_path: Path) -> Any:
    """Return a minimal _JobHistoryWindow stub for _apply_tree_filter tests."""
    win: Any = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._log_dir = tmp_path
    win._log_file_map = {}
    win._refresh_generation = 0
    win._all_entries = []
    win._resolved = {}
    mock_tree = MagicMock()
    mock_tree.get_children.return_value = []
    win._tree = mock_tree
    win._content = MagicMock()
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    return win


def test_apply_tree_filter_ignores_invalid_to_date(tmp_path: Path) -> None:
    """_apply_tree_filter silently ignores an unparseable 'To' date (covers except ValueError at line 255-256).

    When ``_date_to_var`` contains a non-date string the filter must not raise
    and must still display all entries.
    """
    (tmp_path / "robocopy_job_20240601_120000.log").write_text("x", encoding="utf-8")

    win = _make_filter_win(tmp_path)
    insert_count: list[int] = [0]

    def _insert(*_args: Any, **_kwargs: Any) -> str:
        insert_count[0] += 1
        return str(insert_count[0])

    win._tree.insert.side_effect = _insert
    win._all_entries = [
        ("entry_robocopy_job_20240601_120000", "2024-06-01  12:00:00", tmp_path / "robocopy_job_20240601_120000.log")
    ]

    # Set an invalid "to" date – this must not raise and must be silently ignored.
    win._date_to_var.set("not-a-date")
    win._apply_tree_filter()

    # Entry should still appear (invalid filter is ignored).
    assert insert_count[0] == 1


def test_apply_tree_filter_deletes_existing_tree_children(tmp_path: Path) -> None:
    """_apply_tree_filter removes pre-existing rows before re-inserting (line 261).

    When ``_tree.get_children()`` returns a non-empty tuple the implementation
    must call ``_tree.delete(*children)`` to clear the old rows.
    """
    (tmp_path / "robocopy_job_20240601_120000.log").write_text("x", encoding="utf-8")

    win = _make_filter_win(tmp_path)
    # Simulate the tree already containing two stale rows.
    win._tree.get_children.return_value = ("old1", "old2")
    win._all_entries = [
        ("entry_robocopy_job_20240601_120000", "2024-06-01  12:00:00", tmp_path / "robocopy_job_20240601_120000.log")
    ]

    win._apply_tree_filter()

    win._tree.delete.assert_called_once_with("old1", "old2")


def test_apply_tree_filter_shows_placeholder_when_no_entries(tmp_path: Path) -> None:
    """_apply_tree_filter inserts a 'No log files found' row when _all_entries is empty (lines 265-267).

    This covers the ``if not self._all_entries:`` branch that can only be reached
    by calling ``_apply_tree_filter`` directly when the list has not been
    populated (e.g. immediately after construction via ``__new__``).
    """
    win = _make_filter_win(tmp_path)
    # _all_entries is already [] from _make_filter_win.
    win._apply_tree_filter()

    win._tree.insert.assert_called_once()
    inserted_values = win._tree.insert.call_args.kwargs.get(
        "values", win._tree.insert.call_args.args[-1] if win._tree.insert.call_args.args else ()
    )
    assert "No log files found" in str(inserted_values)
    # Filter count label must be cleared.
    assert win._filter_count_var.get() == ""


def test_apply_tree_filter_includes_unparseable_filename_when_date_filter_active(tmp_path: Path) -> None:
    """_apply_tree_filter includes rows with unparseable filenames when a date filter is set (lines 281-283).

    If a log filename does not match the expected date format the ``except
    ValueError: pass`` branch fires, and the row is included (not silently
    hidden) so users can still see unusual log files.
    """
    bad_name_log = tmp_path / "robocopy_job_BADFORMAT.log"
    bad_name_log.write_text("x", encoding="utf-8")

    win = _make_filter_win(tmp_path)
    insert_count: list[int] = [0]

    def _insert(*_args: Any, **_kwargs: Any) -> str:
        insert_count[0] += 1
        return str(insert_count[0])

    win._tree.insert.side_effect = _insert
    win._all_entries = [("entry_robocopy_job_BADFORMAT", "robocopy_job_BADFORMAT", bad_name_log)]

    # Activate the date filter; the badly-named file cannot be parsed so the
    # except-ValueError branch runs and the row must still appear.
    win._date_from_var.set("2024-01-01")
    win._apply_tree_filter()

    assert insert_count[0] == 1, "Unparseable log filename must not be silently excluded by date filter"


# ---------------------------------------------------------------------------
# _run_search backwards-with-position branch (line 374) and
# _scroll_to_match empty-list branch (line 382)
# ---------------------------------------------------------------------------


def test_search_prev_from_existing_position_goes_one_backward() -> None:
    """_search_prev from a non-(-1) position decrements by one (line 374).

    The branch at line 374 (``self._search_current = (prev_current - 1) % count``)
    is only reached when ``forward=False`` AND ``prev_current != -1``.  This
    test reaches it by calling _search_prev twice: the first call establishes a
    current position (count-1), the second decrements it.
    """
    win = _make_search_win()
    win._search_var.set("x")
    # Two matches so index math is unambiguous.
    win._content.search.side_effect = ["1.0", "3.0", ""]

    # First call: prev_current == -1 → goes to last match (index 1).
    win._search_prev()
    assert win._search_current == 1

    # Reset content.search so the second _run_search call re-finds matches.
    win._content.search.side_effect = ["1.0", "3.0", ""]

    # Second call: prev_current == 1 → decrements to index 0 (line 374 executes).
    win._search_prev()
    assert win._search_current == 0


def test_scroll_to_match_returns_early_when_no_matches() -> None:
    """_scroll_to_match does nothing when _search_matches is empty (line 382).

    The guard ``if not self._search_matches: return`` prevents an IndexError
    when the list is empty.  This path is unlikely during normal use (it is
    only triggered by calling _scroll_to_match directly with an empty list) but
    must be covered for completeness.
    """
    win = _make_search_win()
    win._search_matches = []  # explicitly empty

    # Must not raise even though index 0 does not exist.
    win._scroll_to_match(0)

    win._content.see.assert_not_called()
    win._content.mark_set.assert_not_called()
