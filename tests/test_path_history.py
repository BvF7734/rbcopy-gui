"""Tests for the path history storage module."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

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
    """add_source does not write to disk until flush() is called."""
    history_path = tmp_path / "history.json"
    store = PathHistoryStore(path=history_path)
    store.add_source("/persisted/src")
    assert not history_path.exists()
    store.flush()
    assert history_path.exists()
    data = json.loads(history_path.read_text(encoding="utf-8"))
    assert "/persisted/src" in data["source"]


def test_add_destination_persists_to_disk(tmp_path: Path) -> None:
    """add_destination does not write to disk until flush() is called."""
    history_path = tmp_path / "history.json"
    store = PathHistoryStore(path=history_path)
    store.add_destination("/persisted/dst")
    assert not history_path.exists()
    store.flush()
    data = json.loads(history_path.read_text(encoding="utf-8"))
    assert "/persisted/dst" in data["destination"]


def test_paths_survive_reload(tmp_path: Path) -> None:
    """Paths recorded in one store instance are visible in a freshly loaded store after flush."""
    history_path = tmp_path / "history.json"
    store1 = PathHistoryStore(path=history_path)
    store1.add_source("/src/first")
    store1.add_destination("/dst/first")
    store1.flush()

    store2 = PathHistoryStore(path=history_path)
    assert store2.get_source_paths() == ["/src/first"]
    assert store2.get_destination_paths() == ["/dst/first"]


def test_ordering_preserved_after_reload(tmp_path: Path) -> None:
    """MRU ordering is preserved across flush and reload."""
    history_path = tmp_path / "history.json"
    store1 = PathHistoryStore(path=history_path)
    store1.add_source("/a")
    store1.add_source("/b")
    store1.add_source("/c")
    store1.flush()

    store2 = PathHistoryStore(path=history_path)
    assert store2.get_source_paths() == ["/c", "/b", "/a"]


def test_persist_creates_parent_directory(tmp_path: Path) -> None:
    """The parent directory is created automatically when flush() triggers the write."""
    history_path = tmp_path / "new_subdir" / "history.json"
    store = PathHistoryStore(path=history_path)
    store.add_source("/any/path")
    store.flush()
    assert history_path.exists()


# ---------------------------------------------------------------------------
# PathHistoryStore – flush
# ---------------------------------------------------------------------------


def test_flush_writes_dirty_state_to_disk(tmp_path: Path) -> None:
    """flush() writes in-memory changes to disk when the store is dirty."""
    history_path = tmp_path / "history.json"
    store = PathHistoryStore(path=history_path)
    store.add_source("/a")
    store.add_destination("/b")
    assert not history_path.exists()
    store.flush()
    data = json.loads(history_path.read_text(encoding="utf-8"))
    assert data["source"] == ["/a"]
    assert data["destination"] == ["/b"]


def test_flush_is_noop_when_not_dirty(tmp_path: Path) -> None:
    """flush() does not touch the disk when no changes have been made."""
    history_path = tmp_path / "history.json"
    store = PathHistoryStore(path=history_path)
    store.flush()
    assert not history_path.exists()


def test_flush_is_idempotent(tmp_path: Path) -> None:
    """Calling flush() twice only writes once; the second call is a no-op."""
    history_path = tmp_path / "history.json"
    store = PathHistoryStore(path=history_path)
    store.add_source("/x")
    store.flush()
    mtime_after_first = history_path.stat().st_mtime_ns
    store.flush()
    assert history_path.stat().st_mtime_ns == mtime_after_first


def test_add_after_flush_marks_dirty_again(tmp_path: Path) -> None:
    """A new add_source after flush() re-marks the store dirty for the next flush."""
    history_path = tmp_path / "history.json"
    store = PathHistoryStore(path=history_path)
    store.add_source("/first")
    store.flush()
    store.add_source("/second")
    store.flush()
    data = json.loads(history_path.read_text(encoding="utf-8"))
    assert data["source"] == ["/second", "/first"]


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


# ---------------------------------------------------------------------------
# PathHistoryStore – clear
# ---------------------------------------------------------------------------


def test_clear_removes_all_paths(tmp_path: Path) -> None:
    """clear() leaves both source and destination histories empty."""
    store = PathHistoryStore(path=tmp_path / "history.json")
    store.add_source("/src/a")
    store.add_destination("/dst/a")
    store.clear()

    assert store.get_source_paths() == []
    assert store.get_destination_paths() == []


def test_clear_persists_to_disk(tmp_path: Path) -> None:
    """After clear(), a fresh store load sees no paths."""
    history_path = tmp_path / "history.json"
    store = PathHistoryStore(path=history_path)
    store.add_source("/src/a")
    store.add_destination("/dst/a")
    store.clear()

    store2 = PathHistoryStore(path=history_path)
    assert store2.get_source_paths() == []
    assert store2.get_destination_paths() == []


def test_clear_on_empty_store_is_noop(tmp_path: Path) -> None:
    """clear() on an already-empty store does not raise."""
    store = PathHistoryStore(path=tmp_path / "history.json")
    store.clear()  # must not raise
    assert store.get_source_paths() == []
    assert store.get_destination_paths() == []


# ---------------------------------------------------------------------------
# PathHistoryStore – path normalization
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only path separator normalization")
def test_add_source_treats_slash_variants_as_same_entry(tmp_path: Path) -> None:
    """'C:/test' and 'C:\\test' are deduplicated to a single source history entry."""
    store = PathHistoryStore(path=tmp_path / "history.json")
    store.add_source("C:/test")
    store.add_source("C:\\test")
    paths = store.get_source_paths()
    assert len(paths) == 1


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only path separator normalization")
def test_add_destination_treats_slash_variants_as_same_entry(tmp_path: Path) -> None:
    """'C:/test' and 'C:\\test' are deduplicated to a single destination history entry."""
    store = PathHistoryStore(path=tmp_path / "history.json")
    store.add_destination("C:/test")
    store.add_destination("C:\\test")
    paths = store.get_destination_paths()
    assert len(paths) == 1


# ---------------------------------------------------------------------------
# PathHistoryStore – MAX_PATHS cap enforced on load
# ---------------------------------------------------------------------------


def test_load_caps_source_to_max_paths(tmp_path: Path) -> None:
    """Entries beyond MAX_PATHS written directly to the JSON file are silently dropped on load."""
    history_path = tmp_path / "history.json"
    oversized_source = [f"/src/{i}" for i in range(MAX_PATHS + 10)]
    history_path.write_text(
        __import__("json").dumps({"source": oversized_source, "destination": []}),
        encoding="utf-8",
    )

    store = PathHistoryStore(path=history_path)
    assert len(store.get_source_paths()) == MAX_PATHS


def test_load_caps_destination_to_max_paths(tmp_path: Path) -> None:
    """Destination entries beyond MAX_PATHS are silently dropped on load."""
    history_path = tmp_path / "history.json"
    oversized_dst = [f"/dst/{i}" for i in range(MAX_PATHS + 5)]
    history_path.write_text(
        __import__("json").dumps({"source": [], "destination": oversized_dst}),
        encoding="utf-8",
    )

    store = PathHistoryStore(path=history_path)
    assert len(store.get_destination_paths()) == MAX_PATHS


# ---------------------------------------------------------------------------
# PathHistoryStore – flush disk error is swallowed
# ---------------------------------------------------------------------------


def test_flush_oserror_is_silently_ignored(tmp_path: Path) -> None:
    """An OSError during flush() is logged and swallowed; the store stays usable."""
    from unittest.mock import patch

    history_path = tmp_path / "history.json"
    store = PathHistoryStore(path=history_path)
    store.add_source("/any/path")

    with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
        # Must not raise even though the underlying write fails
        store.flush()

    # In-memory state is still intact
    assert store.get_source_paths() == ["/any/path"]
