"""Named path bookmarks for the RbCopy GUI.

Provides a :class:`Bookmark` Pydantic model and a :class:`BookmarksStore`
that persists bookmarks to a local JSON file so they survive application
restarts.

Replacing a bookmark with the same name updates the path *in place* (same
position in the list), so user-arranged menu order is preserved.
"""

from __future__ import annotations

import json
from logging import getLogger
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field, field_validator

from rbcopy.app_dirs import get_data_dir

logger = getLogger(__name__)

# Default path for storing bookmarks (~/.rbcopy/bookmarks.json).
_DEFAULT_BOOKMARKS_PATH: Path = get_data_dir() / "bookmarks.json"

# Maximum allowed length for a bookmark name.  Long names render poorly as
# menu items; this keeps the menu readable.
_MAX_NAME_LENGTH: int = 100


class Bookmark(BaseModel):
    """A named path bookmark.

    Attributes:
        name: Human-readable label shown in the Bookmarks menu.
        path: Filesystem path this bookmark points to.
    """

    name: str = Field(
        description="Human-readable label for the bookmark",
        min_length=1,
        max_length=_MAX_NAME_LENGTH,
    )
    path: str = Field(description="Filesystem path this bookmark points to")

    @field_validator("name")
    @classmethod
    def name_must_not_be_whitespace_only(cls, v: str) -> str:
        """Reject names that are empty or contain only whitespace."""
        if not v.strip():
            raise ValueError("name must not be empty or whitespace-only")
        return v


class BookmarksStore:
    """Manages loading and saving :class:`Bookmark` objects to a JSON file.

    On construction the store loads any previously saved bookmarks from *path*.
    If no file exists yet the store starts empty.

    Replacing a bookmark with the same name updates the path in place (same
    position in the list) so that re-bookmarking a path (e.g. "My NAS") keeps
    its position in the menu rather than jumping to the bottom.

    Subsequent calls to :meth:`add_bookmark` and :meth:`remove_bookmark` update
    the in-memory list and immediately persist the change to disk.

    Args:
        path: Path to the JSON file used for persistence.  Defaults to
            ``<data_dir>/bookmarks.json`` when *None* is passed.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path: Path = path if path is not None else _DEFAULT_BOOKMARKS_PATH
        self._bookmarks: List[Bookmark] = []
        self._load()

    def get_bookmarks(self) -> List[Bookmark]:
        """Return a snapshot of the current bookmarks list."""
        return list(self._bookmarks)

    def get_bookmark(self, name: str) -> Bookmark | None:
        """Return the bookmark with *name*, or ``None`` if not found."""
        for bookmark in self._bookmarks:
            if bookmark.name == name:
                return bookmark
        return None

    def add_bookmark(self, name: str, path: str) -> bool:
        """Add *name*/*path* as a bookmark, or update an existing one in place.

        If a bookmark with *name* already exists its path is updated at the
        same list position, preserving menu order.  If it does not exist a new
        entry is appended.

        If the disk write fails the in-memory list is rolled back so it stays
        consistent with what is on disk, and ``False`` is returned.

        Args:
            name: The human-readable bookmark label.
            path: The filesystem path to store.

        Returns:
            ``True`` if the bookmark was persisted successfully, ``False`` otherwise.
        """
        # Construct the model first so Pydantic validates name/path before any
        # mutation of the list.
        bookmark = Bookmark(name=name, path=path)
        previous = list(self._bookmarks)

        # Update in place if the name already exists; otherwise append.
        for i, b in enumerate(self._bookmarks):
            if b.name == name:
                self._bookmarks[i] = bookmark
                break
        else:
            self._bookmarks.append(bookmark)

        if not self._persist():
            self._bookmarks = previous
            return False
        return True

    def remove_bookmark(self, name: str) -> None:
        """Remove the bookmark named *name* and persist the change.

        Args:
            name: The name of the bookmark to remove.  A no-op if not found.
        """
        self._bookmarks = [b for b in self._bookmarks if b.name != name]
        self._persist()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load bookmarks from the JSON file.

        Silently initialises to an empty list when the file does not exist,
        is not valid JSON, or contains records that fail Pydantic validation.
        """
        if not self._path.exists():
            self._bookmarks = []
            return

        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._bookmarks = [Bookmark.model_validate(b) for b in data]
        except (json.JSONDecodeError, ValueError, OSError):
            logger.debug(
                "Failed to load bookmarks from %s; initialising empty",
                self._path,
                exc_info=True,
            )
            self._bookmarks = []

    def _persist(self) -> bool:
        """Write the current bookmarks list to disk.

        Returns:
            ``True`` if the write succeeded, ``False`` otherwise.
        """
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps([b.model_dump() for b in self._bookmarks], indent=2),
                encoding="utf-8",
            )
            return True
        except OSError:
            logger.exception("Failed to persist bookmarks to %s", self._path)
            return False
