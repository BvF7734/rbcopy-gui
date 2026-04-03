"""Tests for RobocopyGUI bookmark and path-browse methods (rbcopy.gui.main_window)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


from rbcopy.gui import RobocopyGUI
from tests.helpers import make_fake_self as _make_fake_self

# Bookmark manager – RobocopyGUI._open_bookmark_manager
# ---------------------------------------------------------------------------


def test_open_bookmark_manager_method_exists() -> None:
    """RobocopyGUI must expose a callable _open_bookmark_manager method."""
    assert callable(RobocopyGUI._open_bookmark_manager)


def test_open_bookmark_manager_opens_window() -> None:
    """_open_bookmark_manager must instantiate _BookmarkManagerWindow."""
    from rbcopy.bookmarks import BookmarksStore

    fake = _make_fake_self()
    fake._bookmarks_store = MagicMock(spec=BookmarksStore)

    with patch("rbcopy.gui.main_window._BookmarkManagerWindow") as mock_cls:
        RobocopyGUI._open_bookmark_manager(fake)

    mock_cls.assert_called_once()
    call_kwargs = mock_cls.call_args.kwargs
    assert call_kwargs["store"] is fake._bookmarks_store
    assert callable(call_kwargs["on_change"])
    assert callable(call_kwargs["on_apply"])


def test_open_bookmark_manager_on_change_calls_rebuild_menu() -> None:
    """The on_change callback passed to _BookmarkManagerWindow calls _rebuild_bookmarks_menu."""
    from rbcopy.bookmarks import BookmarksStore

    fake = _make_fake_self()
    fake._bookmarks_store = MagicMock(spec=BookmarksStore)

    with patch("rbcopy.gui.main_window._BookmarkManagerWindow") as mock_cls:
        RobocopyGUI._open_bookmark_manager(fake)

    on_change = mock_cls.call_args.kwargs["on_change"]
    on_change()
    fake._rebuild_bookmarks_menu.assert_called_once()


def test_open_bookmark_manager_on_apply_sets_source() -> None:
    """The on_apply callback sets src_var when field='source'."""
    from rbcopy.bookmarks import BookmarksStore

    fake = _make_fake_self()
    fake._bookmarks_store = MagicMock(spec=BookmarksStore)

    with patch("rbcopy.gui.main_window._BookmarkManagerWindow") as mock_cls:
        RobocopyGUI._open_bookmark_manager(fake)

    on_apply = mock_cls.call_args.kwargs["on_apply"]
    on_apply("source", r"C:\my\source")
    fake.src_var.set.assert_called_once_with(r"C:\my\source")


def test_open_bookmark_manager_on_apply_sets_destination() -> None:
    """The on_apply callback sets dst_var when field='destination'."""
    from rbcopy.bookmarks import BookmarksStore

    fake = _make_fake_self()
    fake._bookmarks_store = MagicMock(spec=BookmarksStore)

    with patch("rbcopy.gui.main_window._BookmarkManagerWindow") as mock_cls:
        RobocopyGUI._open_bookmark_manager(fake)

    on_apply = mock_cls.call_args.kwargs["on_apply"]
    on_apply("destination", r"C:\my\dest")
    fake.dst_var.set.assert_called_once_with(r"C:\my\dest")


# ---------------------------------------------------------------------------
def test_rebuild_bookmarks_menu_includes_manage_bookmarks() -> None:
    """_rebuild_bookmarks_menu must always add a 'Manage Bookmarks…' entry."""
    from rbcopy.bookmarks import BookmarksStore

    fake = _make_fake_self()
    fake._bookmarks_store = MagicMock(spec=BookmarksStore)
    fake._bookmarks_store.get_bookmarks.return_value = []
    fake._bookmarks_menu = MagicMock()

    RobocopyGUI._rebuild_bookmarks_menu(fake)

    labels = [call.kwargs.get("label", "") for call in fake._bookmarks_menu.add_command.call_args_list]
    assert any("Manage Bookmarks" in label for label in labels)


# ---------------------------------------------------------------------------
# Gap 3: _browse_src / _browse_dst
# ---------------------------------------------------------------------------


def test_browse_src_updates_var_when_path_chosen() -> None:
    """_browse_src sets src_var to the chosen directory path."""
    fake = _make_fake_self()

    with patch("rbcopy.gui.main_window.filedialog.askdirectory", return_value="/chosen/src"):
        RobocopyGUI._browse_src(fake)

    fake.src_var.set.assert_called_once_with("/chosen/src")


def test_browse_src_does_nothing_when_cancelled() -> None:
    """_browse_src leaves src_var untouched when the dialog is cancelled."""
    fake = _make_fake_self()

    with patch("rbcopy.gui.main_window.filedialog.askdirectory", return_value=""):
        RobocopyGUI._browse_src(fake)

    fake.src_var.set.assert_not_called()


def test_browse_dst_updates_var_when_path_chosen() -> None:
    """_browse_dst sets dst_var to the chosen directory path."""
    fake = _make_fake_self()

    with patch("rbcopy.gui.main_window.filedialog.askdirectory", return_value="D:/chosen/dst"):
        RobocopyGUI._browse_dst(fake)

    fake.dst_var.set.assert_called_once_with("D:/chosen/dst")


def test_browse_dst_does_nothing_when_cancelled() -> None:
    """_browse_dst leaves dst_var untouched when the dialog is cancelled."""
    fake = _make_fake_self()

    with patch("rbcopy.gui.main_window.filedialog.askdirectory", return_value=""):
        RobocopyGUI._browse_dst(fake)

    fake.dst_var.set.assert_not_called()


# ---------------------------------------------------------------------------
# Gap 4: _bookmark_field
# ---------------------------------------------------------------------------


def test_bookmark_field_source_saves_path(tmp_path: Path) -> None:
    """_bookmark_field saves the source path as a named bookmark."""
    from rbcopy.bookmarks import BookmarksStore

    fake = _make_fake_self()
    fake.src_var.get.return_value = "C:/source"
    fake._bookmarks_store = BookmarksStore(path=tmp_path / "bm.json")

    with patch("rbcopy.gui.main_window.simpledialog.askstring", return_value="My Source"):
        RobocopyGUI._bookmark_field(fake, "source")

    saved = fake._bookmarks_store.get_bookmark("My Source")
    assert saved is not None
    assert saved.path == "C:/source"


def test_bookmark_field_destination_saves_path(tmp_path: Path) -> None:
    """_bookmark_field saves the destination path as a named bookmark."""
    from rbcopy.bookmarks import BookmarksStore

    fake = _make_fake_self()
    fake.dst_var.get.return_value = "D:/dest"
    fake._bookmarks_store = BookmarksStore(path=tmp_path / "bm.json")

    with patch("rbcopy.gui.main_window.simpledialog.askstring", return_value="My Dest"):
        RobocopyGUI._bookmark_field(fake, "destination")

    saved = fake._bookmarks_store.get_bookmark("My Dest")
    assert saved is not None
    assert saved.path == "D:/dest"


def test_bookmark_field_does_nothing_when_name_cancelled() -> None:
    """_bookmark_field is a no-op when the name dialog is cancelled (returns None)."""
    fake = _make_fake_self()
    fake.src_var.get.return_value = "C:/source"

    with patch("rbcopy.gui.main_window.simpledialog.askstring", return_value=None):
        RobocopyGUI._bookmark_field(fake, "source")

    fake._rebuild_bookmarks_menu.assert_not_called()


def test_bookmark_field_shows_error_when_path_empty(tmp_path: Path) -> None:
    """_bookmark_field shows an error dialog when the field path is empty."""
    from rbcopy.bookmarks import BookmarksStore

    fake = _make_fake_self()
    fake.src_var.get.return_value = ""  # empty path
    fake._bookmarks_store = BookmarksStore(path=tmp_path / "bm.json")

    with (
        patch("rbcopy.gui.main_window.simpledialog.askstring", return_value="My Bookmark"),
        patch("rbcopy.gui.main_window.messagebox.showerror") as mock_err,
    ):
        RobocopyGUI._bookmark_field(fake, "source")

    mock_err.assert_called_once()
    fake._rebuild_bookmarks_menu.assert_not_called()


def test_bookmark_field_rebuilds_menu_after_save(tmp_path: Path) -> None:
    """_bookmark_field calls _rebuild_bookmarks_menu after successfully saving."""
    from rbcopy.bookmarks import BookmarksStore

    fake = _make_fake_self()
    fake.src_var.get.return_value = "C:/source"
    fake._bookmarks_store = BookmarksStore(path=tmp_path / "bm.json")

    with patch("rbcopy.gui.main_window.simpledialog.askstring", return_value="My Source"):
        RobocopyGUI._bookmark_field(fake, "source")

    fake._rebuild_bookmarks_menu.assert_called_once()


# ---------------------------------------------------------------------------
# Gap 5: _rebuild_bookmarks_menu – full menu shape
# ---------------------------------------------------------------------------


def test_rebuild_bookmarks_menu_adds_cascade_for_each_bookmark() -> None:
    """_rebuild_bookmarks_menu adds a cascade entry for each saved bookmark."""
    from rbcopy.bookmarks import Bookmark, BookmarksStore

    fake = _make_fake_self()
    fake._bookmarks_store = MagicMock(spec=BookmarksStore)
    fake._bookmarks_store.get_bookmarks.return_value = [
        Bookmark(name="Work NAS", path=r"\\nas\work"),
        Bookmark(name="Backup", path=r"D:\backup"),
    ]
    fake._bookmarks_menu = MagicMock()

    with patch("rbcopy.gui.main_window.tk.Menu", return_value=MagicMock()):
        RobocopyGUI._rebuild_bookmarks_menu(fake)

    cascade_labels = [call.kwargs["label"] for call in fake._bookmarks_menu.add_cascade.call_args_list]
    assert "Work NAS" in cascade_labels
    assert "Backup" in cascade_labels


def test_rebuild_bookmarks_menu_submenu_has_source_and_destination() -> None:
    """Each bookmark submenu has 'Set as source' and 'Set as destination' commands."""
    from rbcopy.bookmarks import Bookmark, BookmarksStore

    fake = _make_fake_self()
    fake._bookmarks_store = MagicMock(spec=BookmarksStore)
    fake._bookmarks_store.get_bookmarks.return_value = [Bookmark(name="A", path="C:/path")]
    fake._bookmarks_menu = MagicMock()

    sub_mock = MagicMock()
    with patch("rbcopy.gui.main_window.tk.Menu", return_value=sub_mock):
        RobocopyGUI._rebuild_bookmarks_menu(fake)

    submenu_labels = [call.kwargs["label"] for call in sub_mock.add_command.call_args_list]
    assert "Set as source" in submenu_labels
    assert "Set as destination" in submenu_labels


def test_rebuild_bookmarks_menu_adds_separator() -> None:
    """_rebuild_bookmarks_menu adds at least one separator between sections."""
    from rbcopy.bookmarks import BookmarksStore

    fake = _make_fake_self()
    fake._bookmarks_store = MagicMock(spec=BookmarksStore)
    fake._bookmarks_store.get_bookmarks.return_value = []
    fake._bookmarks_menu = MagicMock()

    RobocopyGUI._rebuild_bookmarks_menu(fake)

    assert fake._bookmarks_menu.add_separator.call_count >= 1


def test_rebuild_bookmarks_menu_placeholder_when_empty() -> None:
    """_rebuild_bookmarks_menu adds a disabled placeholder when no bookmarks exist."""
    from rbcopy.bookmarks import BookmarksStore

    fake = _make_fake_self()
    fake._bookmarks_store = MagicMock(spec=BookmarksStore)
    fake._bookmarks_store.get_bookmarks.return_value = []
    fake._bookmarks_menu = MagicMock()

    RobocopyGUI._rebuild_bookmarks_menu(fake)

    disabled_calls = [
        call for call in fake._bookmarks_menu.add_command.call_args_list if call.kwargs.get("state") == "disabled"
    ]
    assert len(disabled_calls) == 1


def test_rebuild_bookmarks_menu_clears_existing_entries() -> None:
    """_rebuild_bookmarks_menu deletes all old entries before repopulating."""
    from rbcopy.bookmarks import BookmarksStore

    fake = _make_fake_self()
    fake._bookmarks_store = MagicMock(spec=BookmarksStore)
    fake._bookmarks_store.get_bookmarks.return_value = []
    fake._bookmarks_menu = MagicMock()

    RobocopyGUI._rebuild_bookmarks_menu(fake)

    fake._bookmarks_menu.delete.assert_called_once_with(0, "end")


# ---------------------------------------------------------------------------
# Gap 6: _refresh_path_dropdowns
# ---------------------------------------------------------------------------


def test_refresh_path_dropdowns_sets_src_entry_values() -> None:
    """_refresh_path_dropdowns sets _src_entry['values'] from path history sources."""
    from rbcopy.path_history import PathHistoryStore

    fake = _make_fake_self()
    ph = MagicMock(spec=PathHistoryStore)
    ph.get_source_paths.return_value = ["C:/src1", "C:/src2"]
    ph.get_destination_paths.return_value = []
    fake._path_history = ph

    RobocopyGUI._refresh_path_dropdowns(fake)

    fake._src_entry.__setitem__.assert_any_call("values", ["C:/src1", "C:/src2"])


def test_refresh_path_dropdowns_sets_dst_entry_values() -> None:
    """_refresh_path_dropdowns sets _dst_entry['values'] from path history destinations."""
    from rbcopy.path_history import PathHistoryStore

    fake = _make_fake_self()
    ph = MagicMock(spec=PathHistoryStore)
    ph.get_source_paths.return_value = []
    ph.get_destination_paths.return_value = ["D:/dst1", "D:/dst2"]
    fake._path_history = ph

    RobocopyGUI._refresh_path_dropdowns(fake)

    fake._dst_entry.__setitem__.assert_any_call("values", ["D:/dst1", "D:/dst2"])


# ---------------------------------------------------------------------------
# Gap 10: _clear_path_history / _clear_bookmarks
# ---------------------------------------------------------------------------


def test_clear_path_history_calls_path_history_clear() -> None:
    """_clear_path_history calls clear() on the path history store."""
    from rbcopy.path_history import PathHistoryStore

    fake = _make_fake_self()
    fake._path_history = MagicMock(spec=PathHistoryStore)

    RobocopyGUI._clear_path_history(fake)

    fake._path_history.clear.assert_called_once()


def test_clear_path_history_resets_src_entry_values() -> None:
    """_clear_path_history sets _src_entry['values'] to an empty list."""
    from rbcopy.path_history import PathHistoryStore

    fake = _make_fake_self()
    fake._path_history = MagicMock(spec=PathHistoryStore)

    RobocopyGUI._clear_path_history(fake)

    fake._src_entry.__setitem__.assert_any_call("values", [])


def test_clear_path_history_resets_dst_entry_values() -> None:
    """_clear_path_history sets _dst_entry['values'] to an empty list."""
    from rbcopy.path_history import PathHistoryStore

    fake = _make_fake_self()
    fake._path_history = MagicMock(spec=PathHistoryStore)

    RobocopyGUI._clear_path_history(fake)

    fake._dst_entry.__setitem__.assert_any_call("values", [])


def test_clear_bookmarks_calls_bookmarks_store_clear() -> None:
    """_clear_bookmarks calls clear() on the bookmarks store."""
    from rbcopy.bookmarks import BookmarksStore

    fake = _make_fake_self()
    fake._bookmarks_store = MagicMock(spec=BookmarksStore)

    RobocopyGUI._clear_bookmarks(fake)

    fake._bookmarks_store.clear.assert_called_once()


def test_clear_bookmarks_rebuilds_menu() -> None:
    """_clear_bookmarks calls _rebuild_bookmarks_menu after clearing."""
    from rbcopy.bookmarks import BookmarksStore

    fake = _make_fake_self()
    fake._bookmarks_store = MagicMock(spec=BookmarksStore)

    RobocopyGUI._clear_bookmarks(fake)

    fake._rebuild_bookmarks_menu.assert_called_once()
