"""Shared pytest fixtures for the rbcopy test suite."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from rbcopy.bookmarks import BookmarksStore
from rbcopy.logger import setup_logging
from rbcopy.path_history import PathHistoryStore
from rbcopy.preferences import PreferencesStore
from rbcopy.presets import CustomPresetsStore


@pytest.fixture
def log_dir(tmp_path: Path) -> Iterator[Path]:
    """Provide a fresh rbcopy logger writing to *tmp_path*.

    Resets the logger before each test and flushes/closes all handlers
    afterwards so tests are fully isolated from one another.
    """
    log = logging.getLogger("rbcopy")
    for handler in list(log.handlers):
        handler.close()
        log.removeHandler(handler)

    setup_logging(log_dir=tmp_path)

    yield tmp_path

    for handler in list(log.handlers):
        handler.flush()
        handler.close()
        log.removeHandler(handler)


@pytest.fixture
def prefs_store(tmp_path: Path) -> PreferencesStore:
    """Return a :class:`~rbcopy.preferences.PreferencesStore` backed by *tmp_path*."""
    return PreferencesStore(path=tmp_path / "prefs.json")


@pytest.fixture
def bookmarks_store(tmp_path: Path) -> BookmarksStore:
    """Return a :class:`~rbcopy.bookmarks.BookmarksStore` backed by *tmp_path*."""
    return BookmarksStore(path=tmp_path / "bookmarks.json")


@pytest.fixture
def presets_store(tmp_path: Path) -> CustomPresetsStore:
    """Return a :class:`~rbcopy.presets.CustomPresetsStore` backed by *tmp_path*."""
    return CustomPresetsStore(path=tmp_path / "presets.json")


@pytest.fixture
def path_history_store(tmp_path: Path) -> PathHistoryStore:
    """Return a :class:`~rbcopy.path_history.PathHistoryStore` backed by *tmp_path*."""
    return PathHistoryStore(path=tmp_path / "path_history.json")
