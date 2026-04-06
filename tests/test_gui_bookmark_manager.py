"""Tests for _BookmarkManagerWindow (rbcopy.gui.bookmark_manager)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

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


# ---------------------------------------------------------------------------
# _EditBookmarkDialog – lightweight tests via __new__ (no display required)
# ---------------------------------------------------------------------------


def _make_edit_dialog() -> Any:
    """Return a _EditBookmarkDialog instance with mocked Tkinter state."""
    from rbcopy.gui.bookmark_manager import _EditBookmarkDialog

    dlg = _EditBookmarkDialog.__new__(_EditBookmarkDialog)
    dlg._name_var = MagicMock()
    dlg._path_var = MagicMock()
    dlg._confirmed = False
    dlg.destroy = MagicMock()
    return dlg


def test_edit_dialog_name_returns_stripped_value_when_confirmed() -> None:
    """name property returns the stripped text when the dialog was confirmed."""
    dlg = _make_edit_dialog()
    dlg._confirmed = True
    dlg._name_var.get.return_value = "  My Bookmark  "

    assert dlg.name == "My Bookmark"


def test_edit_dialog_path_returns_stripped_value() -> None:
    """path property always returns the stripped path text."""
    dlg = _make_edit_dialog()
    dlg._path_var.get.return_value = r"  C:\Work\Projects  "

    assert dlg.path == r"C:\Work\Projects"


def test_edit_dialog_ok_shows_warning_when_name_empty() -> None:
    """_ok must show a warning and leave _confirmed False when the name is blank."""
    dlg = _make_edit_dialog()
    dlg._name_var.get.return_value = "   "

    with patch("rbcopy.gui.bookmark_manager.messagebox.showwarning") as mock_warn:
        dlg._ok()

    mock_warn.assert_called_once()
    assert dlg._confirmed is False
    dlg.destroy.assert_not_called()


def test_edit_dialog_ok_confirms_and_destroys_when_name_given() -> None:
    """_ok must set _confirmed=True and call destroy when the name is non-empty."""
    dlg = _make_edit_dialog()
    dlg._name_var.get.return_value = "ValidName"

    dlg._ok()

    assert dlg._confirmed is True
    dlg.destroy.assert_called_once()


def test_edit_dialog_cancel_destroys_without_confirming() -> None:
    """_cancel must call destroy without setting _confirmed."""
    dlg = _make_edit_dialog()

    dlg._cancel()

    assert dlg._confirmed is False
    dlg.destroy.assert_called_once()


# ---------------------------------------------------------------------------
# _EditBookmarkDialog and _BookmarkManagerWindow – real Tkinter
# ---------------------------------------------------------------------------


@pytest.fixture
def tk_root() -> Iterator[tk.Tk]:
    """Yield a hidden Tk root; skip the test if no display is available."""
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError as exc:
        pytest.skip(f"Tkinter display not available: {exc}")
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


def test_edit_dialog_initialises_correctly(tk_root: tk.Tk) -> None:
    """_EditBookmarkDialog.__init__ sets initial state without blocking."""
    from rbcopy.gui.bookmark_manager import _EditBookmarkDialog

    with patch.object(_EditBookmarkDialog, "wait_window"):
        dlg = _EditBookmarkDialog(parent=tk_root, initial_name="Alpha", initial_path=r"C:\alpha")

    assert dlg._confirmed is False
    assert dlg._name_var.get() == "Alpha"
    assert dlg._path_var.get() == r"C:\alpha"
    dlg.destroy()


def test_bookmark_manager_window_can_be_opened(tk_root: tk.Tk, tmp_path: Path) -> None:
    """_BookmarkManagerWindow can be constructed and immediately destroyed."""
    from rbcopy.bookmarks import BookmarksStore
    from rbcopy.gui.bookmark_manager import _BookmarkManagerWindow

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    win = _BookmarkManagerWindow(parent=tk_root, store=store)
    win.destroy()


# ---------------------------------------------------------------------------
# _refresh – additional paths (prior selection and existing children)
# ---------------------------------------------------------------------------


def test_bookmark_manager_refresh_preserves_prior_selection(tmp_path: Path) -> None:
    """_refresh re-selects the previously-selected row after repopulating the tree."""
    from rbcopy.bookmarks import BookmarksStore

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("Alpha", r"C:\alpha")
    store.add_bookmark("Beta", r"C:\beta")

    win = _make_bookmark_manager_win(store)
    win._tree.selection.return_value = ("iid_old",)
    # set() returns "Alpha" so that is recorded as the previously-selected name.
    win._tree.set = MagicMock(return_value="Alpha")
    # One existing child so delete(*children) is triggered.
    win._tree.get_children.return_value = ("iid_old",)
    # insert() returns distinct iids so the matching Alpha row can be identified.
    win._tree.insert = MagicMock(side_effect=["iid_new_alpha", "iid_new_beta"])

    win._refresh()

    # Existing children were cleared first (line 204).
    win._tree.delete.assert_called_with("iid_old")
    # The matching bookmark was re-selected (lines 218-219).
    win._tree.selection_set.assert_called_once_with("iid_new_alpha")
    win._tree.see.assert_called_once_with("iid_new_alpha")


# ---------------------------------------------------------------------------
# _selected_index – additional paths
# ---------------------------------------------------------------------------


def test_bookmark_manager_selected_index_returns_none_when_nothing_selected(tmp_path: Path) -> None:
    """_selected_index returns None when the treeview has no selected row."""
    from rbcopy.bookmarks import BookmarksStore

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    win = _make_bookmark_manager_win(store)
    win._tree.selection.return_value = ()

    assert win._selected_index() is None


def test_bookmark_manager_selected_index_returns_none_when_iid_not_in_children(tmp_path: Path) -> None:
    """_selected_index returns None when the selected iid is absent from get_children()."""
    from rbcopy.bookmarks import BookmarksStore

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    win = _make_bookmark_manager_win(store)
    win._tree.selection.return_value = ("iid_ghost",)
    win._tree.get_children.return_value = ("iid_other",)  # ghost not present → ValueError

    assert win._selected_index() is None


# ---------------------------------------------------------------------------
# _add – save failure path
# ---------------------------------------------------------------------------


def test_bookmark_manager_add_shows_error_when_save_fails(tmp_path: Path) -> None:
    """_add shows an error dialog and does not notify when the store refuses to save."""
    from rbcopy.bookmarks import BookmarksStore
    from rbcopy.gui.bookmark_manager import _EditBookmarkDialog

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    win = _make_bookmark_manager_win(store)
    win._refresh = MagicMock()

    mock_dlg = MagicMock(spec=_EditBookmarkDialog)
    mock_dlg.name = "New"
    mock_dlg.path = r"C:\new"

    with patch("rbcopy.gui.bookmark_manager._EditBookmarkDialog", return_value=mock_dlg):
        with patch.object(store, "add_bookmark", return_value=False):
            with patch("rbcopy.gui.bookmark_manager.messagebox.showerror") as mock_err:
                win._add()

    mock_err.assert_called_once()
    win._on_change.assert_not_called()
    win._refresh.assert_not_called()


# ---------------------------------------------------------------------------
# _edit – additional paths
# ---------------------------------------------------------------------------


def test_bookmark_manager_edit_noop_when_no_bookmark_selected(tmp_path: Path) -> None:
    """_edit does nothing when no row is selected in the treeview."""
    from rbcopy.bookmarks import BookmarksStore

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    win = _make_bookmark_manager_win(store)
    win._tree.selection.return_value = ()
    win._refresh = MagicMock()

    win._edit()

    win._on_change.assert_not_called()
    win._refresh.assert_not_called()


def test_bookmark_manager_edit_shows_error_on_invalid_bookmark(tmp_path: Path) -> None:
    """_edit shows an error and aborts when Bookmark construction raises ValueError.

    Having 'Other' appear before 'Target' in the store ensures the
    ``else: updated.append(b)`` branch (for non-matching bookmarks) is also
    exercised before the exception is raised.
    """
    from rbcopy.bookmarks import BookmarksStore
    from rbcopy.gui.bookmark_manager import _EditBookmarkDialog

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("Other", r"C:\other")  # processed via the else branch first
    store.add_bookmark("Target", r"C:\target")  # triggers the ValueError when updated

    win = _make_bookmark_manager_win(store)
    win._tree.selection.return_value = ("iid1",)
    win._tree.set = MagicMock(return_value="Target")
    win._refresh = MagicMock()

    mock_dlg = MagicMock(spec=_EditBookmarkDialog)
    mock_dlg.name = "Updated"
    mock_dlg.path = r"C:\updated"

    with patch("rbcopy.gui.bookmark_manager._EditBookmarkDialog", return_value=mock_dlg):
        with patch("rbcopy.gui.bookmark_manager.Bookmark", side_effect=ValueError("invalid name")):
            with patch("rbcopy.gui.bookmark_manager.messagebox.showerror") as mock_err:
                win._edit()

    mock_err.assert_called_once()
    win._on_change.assert_not_called()
    win._refresh.assert_not_called()


def test_bookmark_manager_edit_shows_error_when_save_fails(tmp_path: Path) -> None:
    """_edit shows an error and does not notify when replace_all returns False."""
    from rbcopy.bookmarks import BookmarksStore
    from rbcopy.gui.bookmark_manager import _EditBookmarkDialog

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("First", r"C:\first")
    store.add_bookmark("Second", r"C:\second")

    win = _make_bookmark_manager_win(store)
    win._tree.selection.return_value = ("iid1",)
    win._tree.set = MagicMock(return_value="First")
    win._refresh = MagicMock()
    win._select_by_name = MagicMock()

    mock_dlg = MagicMock(spec=_EditBookmarkDialog)
    mock_dlg.name = "Updated"
    mock_dlg.path = r"C:\updated"

    with patch("rbcopy.gui.bookmark_manager._EditBookmarkDialog", return_value=mock_dlg):
        with patch.object(store, "replace_all", return_value=False):
            with patch("rbcopy.gui.bookmark_manager.messagebox.showerror") as mock_err:
                win._edit()

    mock_err.assert_called_once()
    win._on_change.assert_not_called()
    win._refresh.assert_not_called()


# ---------------------------------------------------------------------------
# _move_up / _move_down – save failure paths
# ---------------------------------------------------------------------------


def test_bookmark_manager_move_up_shows_error_when_save_fails(tmp_path: Path) -> None:
    """_move_up shows an error and does not notify when replace_all returns False."""
    from rbcopy.bookmarks import BookmarksStore

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("First", r"C:\first")
    store.add_bookmark("Second", r"C:\second")

    win = _make_bookmark_manager_win(store)
    win._tree.get_children.return_value = ("iid0", "iid1")
    win._tree.selection.return_value = ("iid1",)
    win._refresh = MagicMock()

    with patch.object(store, "replace_all", return_value=False):
        with patch("rbcopy.gui.bookmark_manager.messagebox.showerror") as mock_err:
            win._move_up()

    mock_err.assert_called_once()
    win._on_change.assert_not_called()
    win._refresh.assert_not_called()


def test_bookmark_manager_move_down_shows_error_when_save_fails(tmp_path: Path) -> None:
    """_move_down shows an error and does not notify when replace_all returns False."""
    from rbcopy.bookmarks import BookmarksStore

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("First", r"C:\first")
    store.add_bookmark("Second", r"C:\second")

    win = _make_bookmark_manager_win(store)
    win._tree.get_children.return_value = ("iid0", "iid1")
    win._tree.selection.return_value = ("iid0",)
    win._refresh = MagicMock()

    with patch.object(store, "replace_all", return_value=False):
        with patch("rbcopy.gui.bookmark_manager.messagebox.showerror") as mock_err:
            win._move_down()

    mock_err.assert_called_once()
    win._on_change.assert_not_called()
    win._refresh.assert_not_called()


# ---------------------------------------------------------------------------
# _set_as_destination – no-selection path
# ---------------------------------------------------------------------------


def test_bookmark_manager_set_as_destination_noop_when_no_selection(tmp_path: Path) -> None:
    """_set_as_destination does nothing when no row is selected."""
    from rbcopy.bookmarks import BookmarksStore

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    win = _make_bookmark_manager_win(store)
    win._tree.selection.return_value = ()

    win._set_as_destination()

    win._on_apply.assert_not_called()


# ---------------------------------------------------------------------------
# _select_by_name – match path
# ---------------------------------------------------------------------------


def test_bookmark_manager_select_by_name_selects_matching_row(tmp_path: Path) -> None:
    """_select_by_name selects the treeview row whose Name column matches the given name."""
    from rbcopy.bookmarks import BookmarksStore

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    win = _make_bookmark_manager_win(store)

    name_map = {"iid0": "Alpha", "iid1": "Beta", "iid2": "Gamma"}
    win._tree.get_children.return_value = ("iid0", "iid1", "iid2")
    win._tree.set = MagicMock(side_effect=lambda iid, col: name_map.get(iid, ""))

    win._select_by_name("Beta")

    win._tree.selection_set.assert_called_once_with("iid1")
    win._tree.see.assert_called_once_with("iid1")


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

    bm = store.get_bookmark("NewBM")
    assert bm is not None
    assert bm.path == r"C:\new\path"
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
    bm = store.get_bookmark("NewName")
    assert bm is not None
    assert bm.path == r"C:\new"
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


# ---------------------------------------------------------------------------
# _BookmarkManagerWindow.__init__ – without a real display
# ---------------------------------------------------------------------------


def test_bookmark_manager_init_stores_attributes(tmp_path: Path) -> None:
    """__init__ assigns store/on_change/on_apply and calls _build_ui then _refresh."""
    from rbcopy.bookmarks import BookmarksStore
    from rbcopy.gui.bookmark_manager import _BookmarkManagerWindow

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    on_change = MagicMock()
    on_apply = MagicMock()
    build_calls: list[bool] = []
    refresh_calls: list[bool] = []

    def _spy_build(self: Any) -> None:
        build_calls.append(True)

    def _spy_refresh(self: Any) -> None:
        refresh_calls.append(True)

    with (
        patch.object(tk.Toplevel, "__init__", return_value=None),
        patch.object(tk.Toplevel, "title"),
        patch.object(tk.Toplevel, "minsize"),
        patch.object(_BookmarkManagerWindow, "_build_ui", _spy_build),
        patch.object(_BookmarkManagerWindow, "_refresh", _spy_refresh),
    ):
        win = _BookmarkManagerWindow(MagicMock(), store, on_change=on_change, on_apply=on_apply)

    assert win._store is store
    assert win._on_change is on_change
    assert win._on_apply is on_apply
    assert build_calls == [True]
    assert refresh_calls == [True]


# ---------------------------------------------------------------------------
# _BookmarkManagerWindow._build_ui – without a real display
# ---------------------------------------------------------------------------


def test_bookmark_manager_build_ui_assigns_tree_attribute(tmp_path: Path) -> None:
    """_build_ui creates a Treeview and assigns it to self._tree."""
    import rbcopy.gui.bookmark_manager as bm_module
    from rbcopy.bookmarks import BookmarksStore

    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    win = _make_bookmark_manager_win(store)

    mock_treeview = MagicMock()

    with (
        patch.object(bm_module.ttk, "Frame", return_value=MagicMock()),
        patch.object(bm_module.ttk, "Button", return_value=MagicMock()),
        patch.object(bm_module.ttk, "Separator", return_value=MagicMock()),
        patch.object(bm_module.ttk, "Treeview", return_value=mock_treeview),
        patch.object(bm_module.ttk, "Scrollbar", return_value=MagicMock()),
    ):
        win._build_ui()

    assert win._tree is mock_treeview
