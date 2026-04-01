"""Tests for the generic JsonStore base class."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List
from unittest.mock import patch

import pytest
from pydantic import TypeAdapter

from rbcopy.storage import JsonStore

# A simple concrete adapter used throughout these tests.
_LIST_STR_ADAPTER: TypeAdapter[List[str]] = TypeAdapter(List[str])


def _make_store(path: Path) -> JsonStore[List[str]]:
    """Construct a JsonStore[List[str]] for use in tests."""
    return JsonStore(adapter=_LIST_STR_ADAPTER, path=path)


# ---------------------------------------------------------------------------
# JsonStore._load_from_disk
# ---------------------------------------------------------------------------


def test_load_from_disk_returns_none_when_file_missing(tmp_path: Path) -> None:
    """Returns None when the target file does not exist."""
    store = _make_store(tmp_path / "missing.json")
    assert store._load_from_disk() is None


def test_load_from_disk_returns_validated_data(tmp_path: Path) -> None:
    """Returns a correctly validated Python object from valid JSON."""
    p = tmp_path / "data.json"
    p.write_text('["alpha", "beta"]', encoding="utf-8")
    store = _make_store(p)
    assert store._load_from_disk() == ["alpha", "beta"]


def test_load_from_disk_returns_none_on_invalid_json(tmp_path: Path) -> None:
    """Returns None without raising when the file contains malformed JSON."""
    p = tmp_path / "data.json"
    p.write_text("not {{ valid json }", encoding="utf-8")
    store = _make_store(p)
    assert store._load_from_disk() is None


def test_load_from_disk_returns_none_on_schema_mismatch(tmp_path: Path) -> None:
    """Returns None when JSON is valid but does not match the TypeAdapter's schema."""
    p = tmp_path / "data.json"
    # A JSON object, but the adapter expects a JSON array.
    p.write_text('{"key": "value"}', encoding="utf-8")
    store = _make_store(p)
    assert store._load_from_disk() is None


def test_load_from_disk_returns_none_on_oserror(tmp_path: Path) -> None:
    """Returns None without raising when the file cannot be read."""
    p = tmp_path / "data.json"
    p.write_text('["item"]', encoding="utf-8")
    store = _make_store(p)
    with patch.object(Path, "read_text", side_effect=OSError("disk error")):
        assert store._load_from_disk() is None


def test_load_from_disk_logs_debug_on_failure(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Logs a DEBUG message when the file exists but cannot be parsed."""
    p = tmp_path / "data.json"
    p.write_text("bad json content", encoding="utf-8")
    store = _make_store(p)
    with caplog.at_level(logging.DEBUG, logger="rbcopy.storage"):
        store._load_from_disk()
    assert any("Failed to load data from" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# JsonStore._persist
# ---------------------------------------------------------------------------


def test_persist_writes_file_and_returns_true(tmp_path: Path) -> None:
    """Returns True and writes the serialised data to the configured path."""
    p = tmp_path / "data.json"
    store = _make_store(p)
    result = store._persist(["hello", "world"])
    assert result is True
    assert p.exists()
    assert json.loads(p.read_text(encoding="utf-8")) == ["hello", "world"]


def test_persist_creates_missing_parent_directories(tmp_path: Path) -> None:
    """Creates any missing ancestor directories before writing."""
    p = tmp_path / "nested" / "deep" / "data.json"
    store = _make_store(p)
    result = store._persist(["item"])
    assert result is True
    assert p.exists()


def test_persist_returns_false_on_oserror(tmp_path: Path) -> None:
    """Returns False without raising when the write fails with an OSError."""
    p = tmp_path / "data.json"
    store = _make_store(p)
    with patch.object(Path, "write_bytes", side_effect=OSError("disk full")):
        result = store._persist(["item"])
    assert result is False


def test_persist_logs_exception_on_oserror(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Logs at EXCEPTION level when the disk write fails."""
    p = tmp_path / "data.json"
    store = _make_store(p)
    with caplog.at_level(logging.ERROR, logger="rbcopy.storage"):
        with patch.object(Path, "write_bytes", side_effect=OSError("disk full")):
            store._persist(["item"])
    assert any("Failed to persist data to" in r.message for r in caplog.records)


def test_persist_round_trips_through_load_from_disk(tmp_path: Path) -> None:
    """Data written by _persist can be recovered by _load_from_disk."""
    p = tmp_path / "data.json"
    store = _make_store(p)
    original = ["path/one", "path/two", "path/three"]
    store._persist(original)
    assert store._load_from_disk() == original
