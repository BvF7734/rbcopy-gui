"""Tests for _BookmarkManagerWindow (rbcopy.gui.bookmark_manager)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

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
