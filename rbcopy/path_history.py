"""Path history storage for the RbCopy GUI source and destination fields.

Persists a per-field ordered list of recently used paths so they appear in
the Combobox drop-down the next time the application starts.  The list is
stored as a JSON file alongside other application data.  The most-recently-used
path is always kept at the top so the first dropdown entry reflects the last
successful run.
"""

from __future__ import annotations

import json
import sys
from logging import getLogger
from pathlib import Path
from typing import List

from rbcopy.app_dirs import get_data_dir

logger = getLogger(__name__)

_DEFAULT_HISTORY_PATH: Path = get_data_dir() / "path_history.json"
MAX_PATHS: int = 20

# JSON keys for the two lists.
_KEY_SOURCE: str = "source"
_KEY_DESTINATION: str = "destination"


class PathHistoryStore:
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
        self._path: Path = path if path is not None else _DEFAULT_HISTORY_PATH
        self._source: List[str] = []
        self._destination: List[str] = []
        # True whenever in-memory lists differ from what is on disk.
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

        The path is normalised via :func:`_normalize_path_separators` before
        storage so that equivalent paths using different separators (e.g.
        ``C:/test`` and ``C:\\test`` on Windows) are treated as a single entry
        while preserving the native path form displayed to users.

        Args:
            path: The source path string to record.
        """
        normalized: str = _normalize_path_separators(path)
        self._source = _deduplicate_prepend(self._source, normalized)
        self._dirty = True

    def add_destination(self, path: str) -> None:
        """Prepend *path* to the destination history, deduplicating and trimming.

        If *path* already exists anywhere in the list it is first removed, then
        prepended so it appears at index 0 (the top of the dropdown).  The list
        is then trimmed to at most :data:`MAX_PATHS` entries.

        The path is normalised via :func:`_normalize_path_separators` before
        storage so that equivalent paths using different separators (e.g.
        ``C:/test`` and ``C:\\test`` on Windows) are treated as a single entry
        while preserving the native path form displayed to users.

        Args:
            path: The destination path string to record.
        """
        normalized: str = _normalize_path_separators(path)
        self._destination = _deduplicate_prepend(self._destination, normalized)
        self._dirty = True

    def get_source_paths(self) -> List[str]:
        """Return a snapshot of the current source path history (most-recent first)."""
        return list(self._source)

    def get_destination_paths(self) -> List[str]:
        """Return a snapshot of the current destination path history (most-recent first)."""
        return list(self._destination)

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
            try:
                self._persist()
            except OSError:
                logger.exception("Failed to flush path history to %s", self._path)
            else:
                self._dirty = False

    def clear(self) -> None:
        """Erase all source and destination history entries and persist the change."""
        self._source = []
        self._destination = []
        # Mark dirty first so a failed persist can be retried via flush().
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
        if not self._path.exists():
            return
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            source_raw = data.get(_KEY_SOURCE, [])
            if isinstance(source_raw, list):
                self._source = [str(p) for p in source_raw][:MAX_PATHS]
            else:
                self._source = []
            destination_raw = data.get(_KEY_DESTINATION, [])
            if isinstance(destination_raw, list):
                self._destination = [str(p) for p in destination_raw][:MAX_PATHS]
            else:
                self._destination = []
        except (json.JSONDecodeError, ValueError, OSError, TypeError):
            logger.debug(
                "Failed to load path history from %s; initialising empty lists",
                self._path,
                exc_info=True,
            )
            self._source = []
            self._destination = []

    def _persist(self) -> None:
        """Serialise both lists and write them to the JSON file.

        Raises:
            OSError: If the file cannot be written.  Callers are responsible
                for handling this and deciding whether to retry.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, List[str]] = {
            _KEY_SOURCE: self._source,
            _KEY_DESTINATION: self._destination,
        }
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")


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

    Args:
        paths:    Current list of paths (not mutated).
        new_path: The path to move to the front.

    Returns:
        A new list with *new_path* at index 0 and at most :data:`MAX_PATHS` entries.
    """
    deduped = [p for p in paths if p != new_path]
    return ([new_path] + deduped)[:MAX_PATHS]
