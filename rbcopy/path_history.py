"""Path history storage for the RbCopy GUI source and destination fields.

Persists a per-field ordered list of recently used paths so they appear in
the Combobox drop-down the next time the application starts.  The list is
stored as a JSON file alongside other application data.  The most-recently-used
path is always kept at the top so the first dropdown entry reflects the last
successful run.
"""

from __future__ import annotations

import sys
from logging import getLogger
from pathlib import Path
from typing import Any, List

from pydantic import BaseModel, Field, TypeAdapter, field_validator

from rbcopy.app_dirs import get_data_dir
from rbcopy.storage import JsonStore

logger = getLogger(__name__)

_DEFAULT_HISTORY_PATH: Path = get_data_dir() / "path_history.json"
MAX_PATHS: int = 20


class PathHistoryData(BaseModel):
    """Persisted source and destination path history.

    Attributes:
        source:      Ordered list of recently used source paths (MRU first).
        destination: Ordered list of recently used destination paths (MRU first).
    """

    source: List[str] = Field(default_factory=list)
    destination: List[str] = Field(default_factory=list)

    @field_validator("source", "destination", mode="before")
    @classmethod
    def coerce_and_trim(cls, v: Any) -> List[str]:
        """Coerce each element to str, drop non-list values, and cap at MAX_PATHS."""
        if not isinstance(v, list):
            return []
        return [str(item) for item in v][:MAX_PATHS]


# Module-level adapter so the type inspection cost is paid once at import time.
_PATH_HISTORY_ADAPTER: TypeAdapter[PathHistoryData] = TypeAdapter(PathHistoryData)


class PathHistoryStore(JsonStore[PathHistoryData]):
    """Manages recently-used source and destination path lists.

    Paths are persisted to a JSON file so they survive application restarts.
    The store loads its data on construction; mutation methods update the
    in-memory lists and mark the store as dirty.  Call :meth:`flush` to write
    any pending changes to disk (methods such as :meth:`clear` also flush).

    Args:
        path: Path to the JSON file used for persistence.  Defaults to
            ``<data_dir>/path_history.json`` when ``None`` is passed.
    """

    def __init__(self, path: Path | None = None) -> None:
        resolved: Path = path if path is not None else _DEFAULT_HISTORY_PATH
        super().__init__(adapter=_PATH_HISTORY_ADAPTER, path=resolved)
        self._data: PathHistoryData = PathHistoryData()
        # True whenever in-memory state differs from what is on disk.
        self._dirty: bool = False
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_source(self, path: str) -> None:
        """Prepend *path* to the source history, deduplicating and trimming.

        If *path* already exists anywhere in the list it is first removed, then
        prepended so it appears at index 0 (the top of the dropdown).  The list
        is then trimmed to at most :data:`MAX_PATHS` entries.

        Deduplication uses :func:`_normalize_path_separators` for comparison so
        that equivalent paths with different separators (e.g. ``C:/test`` and
        ``C:\\test`` on Windows) are treated as a single entry.  The original
        path string is stored so the value displayed to users is unchanged.

        Args:
            path: The source path string to record.
        """
        self._data.source = _deduplicate_prepend(self._data.source, path)
        self._dirty = True

    def add_destination(self, path: str) -> None:
        """Prepend *path* to the destination history, deduplicating and trimming.

        If *path* already exists anywhere in the list it is first removed, then
        prepended so it appears at index 0 (the top of the dropdown).  The list
        is then trimmed to at most :data:`MAX_PATHS` entries.

        Deduplication uses :func:`_normalize_path_separators` for comparison so
        that equivalent paths with different separators (e.g. ``C:/test`` and
        ``C:\\test`` on Windows) are treated as a single entry.  The original
        path string is stored so the value displayed to users is unchanged.

        Args:
            path: The destination path string to record.
        """
        self._data.destination = _deduplicate_prepend(self._data.destination, path)
        self._dirty = True

    def get_source_paths(self) -> List[str]:
        """Return a snapshot of the current source path history (most-recent first)."""
        return list(self._data.source)

    def get_destination_paths(self) -> List[str]:
        """Return a snapshot of the current destination path history (most-recent first)."""
        return list(self._data.destination)

    def flush(self) -> None:
        """Write pending changes to disk if the in-memory state has changed.

        Call this when the application is about to close (or at any other
        safe checkpoint) to guarantee that paths added via :meth:`add_source`
        and :meth:`add_destination` are durable.  No-op when the store is
        already in sync with disk.

        If the write fails the store remains dirty so the next call to
        :meth:`flush` can retry.
        """
        if self._dirty:
            if self._persist(self._data):
                self._dirty = False
            # On failure: store stays dirty for the next flush() attempt.
            # The base class already logs the exception.

    def clear(self) -> None:
        """Erase all source and destination history entries and persist the change."""
        self._data = PathHistoryData()
        self._dirty = True
        self.flush()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load the history from disk.

        Silently initialises to empty lists on any error (missing file,
        corrupt JSON, non-list values, unexpected data types) so a bad history
        file never prevents the application from starting.
        """
        loaded = self._load_from_disk()
        self._data = loaded if loaded is not None else PathHistoryData()


def _normalize_path_separators(path: str) -> str:
    """Normalize path separators for platform-consistent deduplication.

    On Windows, forward slashes are converted to backslashes so that
    ``C:/test`` and ``C:\\test`` are treated as the same entry while
    preserving the native Windows path form displayed to users.
    On non-Windows platforms the path is returned unchanged.

    Args:
        path: The path string to normalize.

    Returns:
        The path with separators normalized for the current platform.
    """
    if sys.platform == "win32":
        return path.replace("/", "\\")
    return path


def _deduplicate_prepend(paths: List[str], new_path: str) -> List[str]:
    """Remove *new_path* from *paths* if present, prepend it, and trim to MAX_PATHS.

    Comparison is performed on the normalised form of each path (see
    :func:`_normalize_path_separators`) so that paths differing only in
    separator character (e.g. ``C:/test`` vs ``C:\\test`` on Windows) are
    treated as duplicates.  The original *new_path* string is inserted, not the
    normalised form.

    Args:
        paths:    Current list of paths (not mutated).
        new_path: The path to move to the front.

    Returns:
        A new list with *new_path* at index 0 and at most :data:`MAX_PATHS` entries.
    """
    normalized_new = _normalize_path_separators(new_path)
    deduped = [p for p in paths if _normalize_path_separators(p) != normalized_new]
    return ([new_path] + deduped)[:MAX_PATHS]
