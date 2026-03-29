"""Tests for the bookmarks storage module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from rbcopy.bookmarks import Bookmark, BookmarksStore, _MAX_NAME_LENGTH


# ---------------------------------------------------------------------------
# Bookmark model tests
# ---------------------------------------------------------------------------


def test_bookmark_stores_name_and_path() -> None:
    """Bookmark accepts a valid name and path."""
    b = Bookmark(name="My NAS", path=r"\\nas\share")
    assert b.name == "My NAS"
    assert b.path == r"\\nas\share"


def test_bookmark_rejects_empty_name() -> None:
    """Bookmark must reject an empty name string."""
    with pytest.raises(ValidationError):
        Bookmark(name="", path="/some/path")


def test_bookmark_rejects_whitespace_only_name() -> None:
    """Bookmark must reject a name that is whitespace only."""
    with pytest.raises(ValidationError):
        Bookmark(name="   ", path="/some/path")


def test_bookmark_rejects_name_exceeding_max_length() -> None:
    """Bookmark must reject a name longer than _MAX_NAME_LENGTH characters."""
    long_name = "x" * (_MAX_NAME_LENGTH + 1)
    with pytest.raises(ValidationError):
        Bookmark(name=long_name, path="/some/path")


def test_bookmark_accepts_name_at_max_length() -> None:
    """Bookmark must accept a name exactly _MAX_NAME_LENGTH characters long."""
    max_name = "a" * _MAX_NAME_LENGTH
    b = Bookmark(name=max_name, path="/some/path")
    assert len(b.name) == _MAX_NAME_LENGTH


def test_bookmark_round_trips_json() -> None:
    """Bookmark serialises to and deserialises from JSON without data loss."""
    original = Bookmark(name="Backup Drive", path=r"D:\backup")
    restored = Bookmark.model_validate(original.model_dump())
    assert restored == original


# ---------------------------------------------------------------------------
# BookmarksStore – construction / loading
# ---------------------------------------------------------------------------


def test_store_starts_empty_when_no_file(tmp_path: Path) -> None:
    """A new store with no existing file starts with no bookmarks."""
    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    assert store.get_bookmarks() == []


def test_store_loads_existing_bookmarks(tmp_path: Path) -> None:
    """Bookmarks written to the JSON file are loaded on construction."""
    bookmarks_path = tmp_path / "bookmarks.json"
    b = Bookmark(name="My NAS", path=r"\\nas\docs")
    bookmarks_path.write_text(json.dumps([b.model_dump()]), encoding="utf-8")

    store = BookmarksStore(path=bookmarks_path)

    assert len(store.get_bookmarks()) == 1
    assert store.get_bookmarks()[0].name == "My NAS"
    assert store.get_bookmarks()[0].path == r"\\nas\docs"


def test_store_recovers_from_corrupt_file(tmp_path: Path) -> None:
    """A corrupt JSON file is silently ignored; the store starts empty."""
    bookmarks_path = tmp_path / "bookmarks.json"
    bookmarks_path.write_text("not valid json {{ }", encoding="utf-8")

    store = BookmarksStore(path=bookmarks_path)

    assert store.get_bookmarks() == []


def test_store_recovers_from_valid_json_invalid_schema(tmp_path: Path) -> None:
    """Records that fail Pydantic validation are silently ignored; store starts empty."""
    bookmarks_path = tmp_path / "bookmarks.json"
    # name is empty — violates min_length=1
    bookmarks_path.write_text(json.dumps([{"name": "", "path": "/x"}]), encoding="utf-8")

    store = BookmarksStore(path=bookmarks_path)

    assert store.get_bookmarks() == []


# ---------------------------------------------------------------------------
# BookmarksStore – add_bookmark
# ---------------------------------------------------------------------------


def test_add_bookmark_stores_new_entry(tmp_path: Path) -> None:
    """add_bookmark persists a new bookmark and returns True."""
    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    result = store.add_bookmark("Work", r"C:\work")

    assert result is True
    assert store.get_bookmark("Work") is not None
    assert store.get_bookmark("Work").path == r"C:\work"  # type: ignore[union-attr]


def test_add_bookmark_replaces_existing_in_place(tmp_path: Path) -> None:
    """add_bookmark with the same name updates the path AND keeps the same position."""
    bookmarks_path = tmp_path / "bookmarks.json"
    store = BookmarksStore(path=bookmarks_path)
    store.add_bookmark("First", r"C:\first")
    store.add_bookmark("My NAS", r"\\nas\old")
    store.add_bookmark("Last", r"C:\last")

    # The second position should be "My NAS". Now update it.
    store.add_bookmark("My NAS", r"\\nas\new")

    bookmarks = store.get_bookmarks()
    assert len(bookmarks) == 3
    # Position preserved — "My NAS" is still at index 1.
    assert bookmarks[1].name == "My NAS"
    assert bookmarks[1].path == r"\\nas\new"


def test_add_bookmark_appends_when_name_is_new(tmp_path: Path) -> None:
    """add_bookmark appends when the name does not already exist."""
    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("Alpha", r"C:\alpha")
    store.add_bookmark("Beta", r"C:\beta")

    bookmarks = store.get_bookmarks()
    assert len(bookmarks) == 2
    assert bookmarks[0].name == "Alpha"
    assert bookmarks[1].name == "Beta"


def test_add_bookmark_rolls_back_on_disk_failure(tmp_path: Path) -> None:
    """add_bookmark reverts in-memory state when the disk write fails."""
    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("existing", r"C:\existing")

    with patch.object(Path, "write_text", side_effect=OSError("disk full")):
        result = store.add_bookmark("new_bm", r"C:\new")

    assert result is False
    assert store.get_bookmark("new_bm") is None
    assert store.get_bookmark("existing") is not None


def test_add_bookmark_rollback_preserves_original_path_on_replace_failure(tmp_path: Path) -> None:
    """When replacing an existing bookmark fails, the original path is restored."""
    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("My NAS", r"\\nas\original")

    with patch.object(Path, "write_text", side_effect=OSError("disk full")):
        result = store.add_bookmark("My NAS", r"\\nas\replacement")

    assert result is False
    bookmark = store.get_bookmark("My NAS")
    assert bookmark is not None
    assert bookmark.path == r"\\nas\original"


# ---------------------------------------------------------------------------
# BookmarksStore – remove_bookmark
# ---------------------------------------------------------------------------


def test_remove_bookmark_deletes_entry(tmp_path: Path) -> None:
    """remove_bookmark removes the named entry from the store."""
    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("To Remove", r"C:\temp")
    store.remove_bookmark("To Remove")

    assert store.get_bookmark("To Remove") is None
    assert store.get_bookmarks() == []


def test_remove_bookmark_is_noop_for_unknown_name(tmp_path: Path) -> None:
    """remove_bookmark does not raise when the name is not found."""
    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("Keep", r"C:\keep")
    store.remove_bookmark("NonExistent")  # must not raise

    assert store.get_bookmark("Keep") is not None


# ---------------------------------------------------------------------------
# BookmarksStore – get_bookmark
# ---------------------------------------------------------------------------


def test_get_bookmark_returns_none_when_empty(tmp_path: Path) -> None:
    """get_bookmark returns None when no bookmarks exist."""
    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    assert store.get_bookmark("anything") is None


def test_get_bookmark_returns_correct_entry(tmp_path: Path) -> None:
    """get_bookmark returns the matching bookmark by name."""
    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("Alpha", r"C:\alpha")
    store.add_bookmark("Beta", r"C:\beta")

    result = store.get_bookmark("Beta")

    assert result is not None
    assert result.path == r"C:\beta"


# ---------------------------------------------------------------------------
# BookmarksStore – persistence
# ---------------------------------------------------------------------------


def test_bookmarks_survive_reload(tmp_path: Path) -> None:
    """Bookmarks written by one store instance are visible after a fresh load."""
    bookmarks_path = tmp_path / "bookmarks.json"
    store1 = BookmarksStore(path=bookmarks_path)
    store1.add_bookmark("NAS", r"\\nas\share")
    store1.add_bookmark("Local", r"C:\local")

    store2 = BookmarksStore(path=bookmarks_path)

    names = [b.name for b in store2.get_bookmarks()]
    assert "NAS" in names
    assert "Local" in names
    assert len(names) == 2


def test_remove_persists_across_reload(tmp_path: Path) -> None:
    """After remove_bookmark, a fresh load does not see the deleted bookmark."""
    bookmarks_path = tmp_path / "bookmarks.json"
    store1 = BookmarksStore(path=bookmarks_path)
    store1.add_bookmark("Keep", r"C:\keep")
    store1.add_bookmark("Remove", r"C:\remove")
    store1.remove_bookmark("Remove")

    store2 = BookmarksStore(path=bookmarks_path)

    assert store2.get_bookmark("Remove") is None
    assert store2.get_bookmark("Keep") is not None


def test_replace_persists_new_path_across_reload(tmp_path: Path) -> None:
    """The updated path after an in-place replace is written to disk."""
    bookmarks_path = tmp_path / "bookmarks.json"
    store1 = BookmarksStore(path=bookmarks_path)
    store1.add_bookmark("NAS", r"\\nas\old")
    store1.add_bookmark("NAS", r"\\nas\new")

    store2 = BookmarksStore(path=bookmarks_path)

    bookmark = store2.get_bookmark("NAS")
    assert bookmark is not None
    assert bookmark.path == r"\\nas\new"


def test_store_creates_parent_directory_on_persist(tmp_path: Path) -> None:
    """BookmarksStore creates the parent directory when persisting for the first time."""
    nested_path = tmp_path / "nested" / "dir" / "bookmarks.json"
    store = BookmarksStore(path=nested_path)
    result = store.add_bookmark("entry", r"C:\some\path")

    assert result is True
    assert nested_path.exists()


# ---------------------------------------------------------------------------
# BookmarksStore – clear
# ---------------------------------------------------------------------------


def test_clear_removes_all_bookmarks(tmp_path: Path) -> None:
    """clear() leaves the in-memory list empty."""
    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.add_bookmark("A", r"C:\a")
    store.add_bookmark("B", r"C:\b")
    store.clear()

    assert store.get_bookmarks() == []


def test_clear_persists_to_disk(tmp_path: Path) -> None:
    """After clear(), a fresh store load sees no bookmarks."""
    bm_path = tmp_path / "bookmarks.json"
    store = BookmarksStore(path=bm_path)
    store.add_bookmark("X", r"C:\x")
    store.clear()

    store2 = BookmarksStore(path=bm_path)
    assert store2.get_bookmarks() == []


def test_clear_on_empty_store_is_noop(tmp_path: Path) -> None:
    """clear() on an already-empty store does not raise."""
    store = BookmarksStore(path=tmp_path / "bookmarks.json")
    store.clear()  # must not raise
    assert store.get_bookmarks() == []
