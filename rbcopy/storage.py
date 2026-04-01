"""Generic JSON-backed persistent store base class.

Provides :class:`JsonStore` which centralises file-path resolution,
``OSError`` handling, and JSON decoding so that concrete stores only need
to implement their own public API and domain-specific seeding or fallback
logic.  Any future cross-cutting concern (e.g. file locking to prevent
multi-instance corruption) only needs to be written here once.
"""

from __future__ import annotations

import json
from logging import getLogger
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import TypeAdapter, ValidationError

logger = getLogger(__name__)

T = TypeVar("T")


class JsonStore(Generic[T]):
    """Generic base class for JSON file-backed data stores.

    Concrete subclasses pass a :class:`~pydantic.TypeAdapter` and a
    :class:`~pathlib.Path` to ``super().__init__``.  They then call
    :meth:`_load_from_disk` and :meth:`_persist` instead of
    re-implementing the same file I/O and error-handling boilerplate.

    Args:
        adapter: Pydantic ``TypeAdapter`` for the stored data type.
        path:    Path to the JSON file used for persistence.
    """

    def __init__(self, adapter: TypeAdapter[T], path: Path) -> None:
        self._adapter: TypeAdapter[T] = adapter
        self._path: Path = path

    def _load_from_disk(self) -> T | None:
        """Read the JSON file and validate it against the store's type.

        Returns:
            The validated data object on success, or ``None`` when the file
            does not exist, cannot be read, contains invalid JSON, or fails
            Pydantic validation.  The caller is responsible for providing a
            suitable fallback.
        """
        if not self._path.exists():
            return None
        try:
            raw = self._path.read_text(encoding="utf-8")
            return self._adapter.validate_json(raw)
        except (json.JSONDecodeError, ValueError, OSError, ValidationError):
            logger.debug(
                "Failed to load data from %s",
                self._path,
                exc_info=True,
            )
            return None

    def _persist(self, data: T) -> bool:
        """Serialise *data* with the adapter and write it to disk.

        Creates any missing parent directories before writing.

        Args:
            data: The data object to serialise.

        Returns:
            ``True`` if the write succeeded, ``False`` if an :exc:`OSError`
            was raised.
        """
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_bytes(self._adapter.dump_json(data, indent=2))
            return True
        except OSError:
            logger.exception("Failed to persist data to %s", self._path)
            return False
