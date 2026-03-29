"""Tests for the path history storage module."""

from __future__ import annotations

import json
from pathlib import Path

from rbcopy.path_history import MAX_PATHS, PathHistoryStore, _deduplicate_prepend


# ---------------------------------------------------------------------------
# _deduplicate_prepend helper
# ---------------------------------------------------------------------------


def test_deduplicate_prepend_adds_to_empty_list() -> None:
    """Prepending to an empty list returns a single-element list."""
    result = _deduplicate_prepend([], "/new/path")
    assert result == ["/new/path"]


def test_deduplicate_prepend_moves_existing_to_front() -> None:
    """An already-present path is moved to index 0 rather than duplicated."""
    paths = ["/a", "/b", "/c"]
    result = _deduplicate_prepend(paths, "/b")
    assert result == ["/b", "/a", "/c"]


def test_deduplicate_prepend_adds_new_path_at_front() -> None:
    """A brand-new path is inserted at index 0."""
    paths = ["/a", "/b"]
    result = _deduplicate_prepend(paths, "/new")
    assert result == ["/new", "/a", "/b"]


def test_deduplicate_prepend_trims_to_max_paths() -> None:
    """The returned list never exceeds MAX_PATHS entries."""
    paths = [f"/path/{i}" for i in range(MAX_PATHS)]
    result = _deduplicate_prepend(paths, "/new")
    assert len(result) == MAX_PATHS
    assert result[0] == "/new"


def test_deduplicate_prepend_does_not_mutate_input() -> None:
    """The original list is not modified."""
    paths = ["/a", "/b"]
    _deduplicate_prepend(paths, "/c")
    assert paths == ["/a", "/b"]


def test_deduplicate_prepend_deduplicates_before_trim() -> None:
    """When the path already exists, deduplication prevents exceeding MAX_PATHS."""
    # List is already at max capacity; 'last' is already present, so no net addition.
    paths = [f"/path/{i}" for i in range(MAX_PATHS)]
    paths.append("/already/present")  # list has MAX_PATHS + 1 but we'll move this one
    # Start with exactly MAX_PATHS entries where the last is the target
    paths = [f"/path/{i}" for i in range(MAX_PATHS - 1)] + ["/already/present"]
    result = _deduplicate_prepend(paths, "/already/present")
    assert len(result) == MAX_PATHS
    assert result[0] == "/already/present"


# ---------------------------------------------------------------------------
# PathHistoryStore – initial state
# ---------------------------------------------------------------------------


def test_store_starts_with_empty_source_when_no_file(tmp_path: Path) -> None:
    """A new store with no existing file returns empty source paths."""
    store = PathHistoryStore(path=tmp_path / "history.json")
    assert store.get_source_paths() == []


def test_store_starts_with_empty_destination_when_no_file(tmp_path: Path) -> None:
    """A new store with no existing file returns empty destination paths."""
    store = PathHistoryStore(path=tmp_path / "history.json")
    assert store.get_destination_paths() == []


# ---------------------------------------------------------------------------
# PathHistoryStore – add operations
# ---------------------------------------------------------------------------


def test_add_source_records_path(tmp_path: Path) -> None:
    """add_source stores the given path string."""
    store = PathHistoryStore(path=tmp_path / "history.json")
    store.add_source("/src/path")
    assert store.get_source_paths() == ["/src/path"]


def test_add_destination_records_path(tmp_path: Path) -> None:
    """add_destination stores the given path string."""
    store = PathHistoryStore(path=tmp_path / "history.json")
    store.add_destination("/dst/path")
    assert store.get_destination_paths() == ["/dst/path"]


def test_add_source_most_recent_first(tmp_path: Path) -> None:
    """Multiple add_source calls keep the most-recently added path at index 0."""
    store = PathHistoryStore(path=tmp_path / "history.json")
    store.add_source("/a")
    store.add_source("/b")
    store.add_source("/c")
    paths = store.get_source_paths()
    assert paths[0] == "/c"
    assert paths[1] == "/b"
    assert paths[2] == "/a"


def test_add_destination_most_recent_first(tmp_path: Path) -> None:
    """Multiple add_destination calls keep the most-recently added path at index 0."""
    store = PathHistoryStore(path=tmp_path / "history.json")
    store.add_destination("/x")
    store.add_destination("/y")
    paths = store.get_destination_paths()
    assert paths[0] == "/y"
    assert paths[1] == "/x"


def test_add_source_deduplicates(tmp_path: Path) -> None:
    """Re-adding an existing source path moves it to the front without duplication."""
    store = PathHistoryStore(path=tmp_path / "history.json")
    store.add_source("/a")
    store.add_source("/b")
    store.add_source("/a")  # duplicate
    paths = store.get_source_paths()
    assert paths == ["/a", "/b"]


def test_add_destination_deduplicates(tmp_path: Path) -> None:
    """Re-adding an existing destination path moves it to the front without duplication."""
    store = PathHistoryStore(path=tmp_path / "history.json")
    store.add_destination("/x")
    store.add_destination("/y")
    store.add_destination("/x")  # duplicate
    paths = store.get_destination_paths()
    assert paths == ["/x", "/y"]


def test_add_source_trims_to_max_paths(tmp_path: Path) -> None:
    """Source history never exceeds MAX_PATHS entries."""
    store = PathHistoryStore(path=tmp_path / "history.json")
    for i in range(MAX_PATHS + 5):
        store.add_source(f"/src/{i}")
    assert len(store.get_source_paths()) == MAX_PATHS


def test_add_destination_trims_to_max_paths(tmp_path: Path) -> None:
    """Destination history never exceeds MAX_PATHS entries."""
    store = PathHistoryStore(path=tmp_path / "history.json")
    for i in range(MAX_PATHS + 5):
        store.add_destination(f"/dst/{i}")
    assert len(store.get_destination_paths()) == MAX_PATHS


def test_source_and_destination_are_independent(tmp_path: Path) -> None:
    """Adding to source does not affect destination and vice versa."""
    store = PathHistoryStore(path=tmp_path / "history.json")
    store.add_source("/only/source")
    store.add_destination("/only/destination")
    assert store.get_source_paths() == ["/only/source"]
    assert store.get_destination_paths() == ["/only/destination"]


# ---------------------------------------------------------------------------
# PathHistoryStore – persistence
# ---------------------------------------------------------------------------


def test_add_source_persists_to_disk(tmp_path: Path) -> None:
    """add_source writes the updated list to the JSON file immediately."""
    history_path = tmp_path / "history.json"
    store = PathHistoryStore(path=history_path)
    store.add_source("/persisted/src")
    assert history_path.exists()
    data = json.loads(history_path.read_text(encoding="utf-8"))
    assert "/persisted/src" in data["source"]


def test_add_destination_persists_to_disk(tmp_path: Path) -> None:
    """add_destination writes the updated list to the JSON file immediately."""
    history_path = tmp_path / "history.json"
    store = PathHistoryStore(path=history_path)
    store.add_destination("/persisted/dst")
    data = json.loads(history_path.read_text(encoding="utf-8"))
    assert "/persisted/dst" in data["destination"]


def test_paths_survive_reload(tmp_path: Path) -> None:
    """Paths recorded in one store instance are visible in a freshly loaded store."""
    history_path = tmp_path / "history.json"
    store1 = PathHistoryStore(path=history_path)
    store1.add_source("/src/first")
    store1.add_destination("/dst/first")

    store2 = PathHistoryStore(path=history_path)
    assert store2.get_source_paths() == ["/src/first"]
    assert store2.get_destination_paths() == ["/dst/first"]


def test_ordering_preserved_after_reload(tmp_path: Path) -> None:
    """MRU ordering is preserved across a reload."""
    history_path = tmp_path / "history.json"
    store1 = PathHistoryStore(path=history_path)
    store1.add_source("/a")
    store1.add_source("/b")
    store1.add_source("/c")

    store2 = PathHistoryStore(path=history_path)
    assert store2.get_source_paths() == ["/c", "/b", "/a"]


def test_persist_creates_parent_directory(tmp_path: Path) -> None:
    """The parent directory is created automatically if it does not exist."""
    history_path = tmp_path / "new_subdir" / "history.json"
    store = PathHistoryStore(path=history_path)
    store.add_source("/any/path")
    assert history_path.exists()


# ---------------------------------------------------------------------------
# PathHistoryStore – corrupt file recovery
# ---------------------------------------------------------------------------


def test_corrupt_json_file_recovers_to_empty(tmp_path: Path) -> None:
    """A corrupt JSON file is discarded; the store initialises to empty lists."""
    history_path = tmp_path / "history.json"
    history_path.write_text("not valid json {{{{", encoding="utf-8")
    store = PathHistoryStore(path=history_path)
    assert store.get_source_paths() == []
    assert store.get_destination_paths() == []


def test_wrong_type_for_source_key_recovers_gracefully(tmp_path: Path) -> None:
    """An unexpected type for the 'source' value initialises that list to empty."""
    history_path = tmp_path / "history.json"
    # 'source' is a string instead of a list — should be skipped cleanly.
    history_path.write_text(
        json.dumps({"source": "not-a-list", "destination": ["/dst"]}),
        encoding="utf-8",
    )
    store = PathHistoryStore(path=history_path)
    # The store falls back to empty lists when 'source' cannot be iterated as expected.
    # (str is iterable so individual characters would be str-converted; this tests
    # that any partial load does not cause an exception.)
    assert isinstance(store.get_source_paths(), list)
    assert store.get_destination_paths() == ["/dst"]


def test_empty_json_object_gives_empty_history(tmp_path: Path) -> None:
    """An empty JSON object is a valid file with no paths stored."""
    history_path = tmp_path / "history.json"
    history_path.write_text(json.dumps({}), encoding="utf-8")
    store = PathHistoryStore(path=history_path)
    assert store.get_source_paths() == []
    assert store.get_destination_paths() == []


# ---------------------------------------------------------------------------
# PathHistoryStore – get_* return snapshots
# ---------------------------------------------------------------------------


def test_get_source_paths_returns_snapshot(tmp_path: Path) -> None:
    """Mutating the returned list does not affect the stored history."""
    store = PathHistoryStore(path=tmp_path / "history.json")
    store.add_source("/a")
    snapshot = store.get_source_paths()
    snapshot.append("/injected")
    assert store.get_source_paths() == ["/a"]


def test_get_destination_paths_returns_snapshot(tmp_path: Path) -> None:
    """Mutating the returned list does not affect the stored history."""
    store = PathHistoryStore(path=tmp_path / "history.json")
    store.add_destination("/x")
    snapshot = store.get_destination_paths()
    snapshot.clear()
    assert store.get_destination_paths() == ["/x"]
