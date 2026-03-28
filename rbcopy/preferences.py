"""User-configurable application preferences for RBCopy.

Preferences are persisted to ``preferences.json`` inside the configured data
directory (resolved by :func:`rbcopy.app_dirs.get_data_dir`) and loaded on
every application start.  The :class:`AppPreferences` model declares the
schema and default values; :class:`PreferencesStore` handles loading and
saving.

The data directory itself is *not* stored here — it lives in the separate
bootstrap pointer file managed by :mod:`rbcopy.app_dirs`.
"""

from __future__ import annotations

import json
from logging import getLogger
from pathlib import Path

from pydantic import BaseModel, Field

from rbcopy.app_dirs import get_data_dir

logger = getLogger(__name__)


class AppPreferences(BaseModel):
    """Persistent user preferences for the RBCopy application.

    Attributes:
        default_thread_count: Default value for the ``/MT`` robocopy flag.
            Controls the number of multi-threaded copy threads (1-128).
        default_retry_count: Default value for the ``/R`` robocopy flag.
            Controls how many times robocopy retries a failed copy (0-1 000 000).
        default_wait_seconds: Default value for the ``/W`` robocopy flag.
            Controls the wait time in seconds between retries (0-3600).
        log_retention_count: Number of most-recent session log files to keep
            in the log directory before older ones are deleted (1-1000).
    """

    default_thread_count: int = Field(default=8, ge=1, le=128)
    default_retry_count: int = Field(default=5, ge=0, le=1_000_000)
    default_wait_seconds: int = Field(default=30, ge=0, le=3600)
    log_retention_count: int = Field(default=20, ge=1, le=1000)


class PreferencesStore:
    """Loads and saves :class:`AppPreferences` to a JSON file.

    If the preferences file does not exist on construction the store uses
    factory defaults.  Subsequent calls to :meth:`save` update the file
    atomically (write then replace).

    Args:
        path: Path to the JSON file used for persistence.  Defaults to
            ``preferences.json`` inside the configured data directory when
            ``None`` is passed.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path: Path = path if path is not None else get_data_dir() / "preferences.json"
        self._prefs: AppPreferences = AppPreferences()
        self._load()

    @property
    def preferences(self) -> AppPreferences:
        """Return a copy of the current preferences."""
        return self._prefs.model_copy()

    def save(self, prefs: AppPreferences) -> bool:
        """Persist *prefs* to disk and update the in-memory state.

        If the disk write fails the in-memory state is rolled back to its
        previous value so it stays consistent with what is on disk.

        Args:
            prefs: The new :class:`AppPreferences` to store.

        Returns:
            ``True`` on success, ``False`` if the write failed.
        """
        previous = self._prefs
        self._prefs = prefs
        if not self._persist():
            self._prefs = previous
            return False
        return True

    def _load(self) -> None:
        """Load preferences from the JSON file, falling back to defaults on error."""
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._prefs = AppPreferences.model_validate(data)
        except (json.JSONDecodeError, ValueError, OSError):
            logger.debug(
                "Failed to load preferences from %s; using defaults",
                self._path,
                exc_info=True,
            )

    def _persist(self) -> bool:
        """Serialise preferences and write them to the JSON file.

        Returns:
            ``True`` on success, ``False`` if the write failed.
        """
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._prefs.model_dump(), indent=2),
                encoding="utf-8",
            )
            return True
        except OSError:
            logger.exception("Failed to save preferences to %s", self._path)
            return False
