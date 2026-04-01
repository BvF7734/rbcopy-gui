"""Custom preset storage for RbCopy GUI selections.

Provides a :class:`CustomPreset` Pydantic model and a :class:`CustomPresetsStore`
that persists presets to a local JSON file so they survive application restarts.

On first launch (when no user presets file exists) the store is seeded from the
bundled ``presets.json`` shipped with the package so new users see useful starter
presets immediately.
"""

from __future__ import annotations

import json
from importlib import resources
from logging import getLogger
from pathlib import Path
from typing import Any, Dict, List, Tuple

from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator

from rbcopy.app_dirs import get_data_dir
from rbcopy.storage import JsonStore

logger = getLogger(__name__)

# Default path for storing custom presets (~/.rbcopy/presets.json).
_DEFAULT_PRESETS_PATH: Path = get_data_dir() / "presets.json"


class CustomPreset(BaseModel):
    """A saved custom preset capturing all GUI selections.

    Attributes:
        name: Human-readable label used to identify the preset in the menu.
        source: Source directory path.
        destination: Destination directory path.
        flags: Mapping of robocopy flag string to enabled boolean.
        params: Mapping of robocopy flag string to ``(enabled, value)`` tuple.
    """

    name: str = Field(description="Human-readable name for this preset", min_length=1)
    description: str = Field(default="", description="A plain English explanation of the preset")  # <-- Add this line
    source: str = Field(default="", description="Source directory path")
    destination: str = Field(default="", description="Destination directory path")
    flags: Dict[str, bool] = Field(
        default_factory=dict,
        description="Mapping of flag string to enabled boolean",
    )
    params: Dict[str, Tuple[bool, str]] = Field(
        default_factory=dict,
        description="Mapping of flag string to (enabled, value) tuple",
    )
    file_filter: str = Field(
        default="",
        description="Space-separated file patterns to pass as positional robocopy arguments (e.g. *.img *.txt)",
    )

    @field_validator("name")
    @classmethod
    def name_must_not_be_whitespace_only(cls, v: str) -> str:
        """Reject names that are empty or contain only whitespace."""
        if not v.strip():
            raise ValueError("name must not be empty or whitespace-only")
        return v

    @field_validator("source", "destination", mode="before")
    @classmethod
    def must_be_string(cls, v: Any) -> str:
        """Reject non-string values so coercion cannot silently corrupt paths."""
        if not isinstance(v, str):
            raise ValueError(f"must be a string, got {type(v).__name__!r}")
        return v

    @field_validator("flags", mode="before")
    @classmethod
    def flags_must_be_dict_of_str_bool(cls, v: Any) -> Any:
        """Ensure every flag key is a str and every value is a strict bool.

        Integers (0/1) are intentionally rejected: only JSON boolean literals
        (true/false) are valid flag values.
        """
        if not isinstance(v, dict):
            raise ValueError(f"must be a dict, got {type(v).__name__!r}")
        for key, val in v.items():
            if not isinstance(key, str):
                raise ValueError(f"flag key must be a string, got {type(key).__name__!r}")
            # isinstance(1, bool) is False; isinstance(True, int) is True — check bool first.
            if not isinstance(val, bool):
                raise ValueError(f"flag value for {key!r} must be a bool, got {type(val).__name__!r}")
        return v

    @field_validator("params", mode="before")
    @classmethod
    def params_must_be_dict_of_str_to_bool_str_pairs(cls, v: Any) -> Any:
        """Ensure every param key is a str and every value is a (bool, str) pair.

        JSON arrays deserialise to Python lists, so both list and tuple inputs
        are accepted here and Pydantic handles the final list-to-tuple coercion.
        Integers are rejected as the boolean element (same rationale as flags).
        """
        if not isinstance(v, dict):
            raise ValueError(f"must be a dict, got {type(v).__name__!r}")
        for key, val in v.items():
            if not isinstance(key, str):
                raise ValueError(f"param key must be a string, got {type(key).__name__!r}")
            if not isinstance(val, (list, tuple)) or len(val) != 2:
                raise ValueError(f"param value for {key!r} must be a (bool, str) pair, got {type(val).__name__!r}")
            enabled, value = val[0], val[1]
            if not isinstance(enabled, bool):
                raise ValueError(f"first element of param {key!r} must be a bool, got {type(enabled).__name__!r}")
            if not isinstance(value, str):
                raise ValueError(f"second element of param {key!r} must be a str, got {type(value).__name__!r}")
        return v


def _load_bundled_presets() -> List[CustomPreset]:
    """Load the presets bundled with the package.

    Uses :mod:`importlib.resources` so this works both from a development
    checkout and from a PyInstaller-built executable.

    Returns:
        A list of :class:`CustomPreset` objects, or an empty list if the
        bundled file cannot be read or parsed.
    """
    try:
        package_files = resources.files("rbcopy")
        bundled = package_files.joinpath("presets.json")
        raw = bundled.read_text(encoding="utf-8")
        data = json.loads(raw)
        return [CustomPreset.model_validate(p) for p in data]
    except (FileNotFoundError, json.JSONDecodeError, ValueError, OSError, ValidationError):
        logger.debug("Failed to load bundled presets", exc_info=True)
        return []


# Module-level adapter so the type inspection cost is paid once at import time.
_PRESETS_ADAPTER: TypeAdapter[List[CustomPreset]] = TypeAdapter(List[CustomPreset])


class CustomPresetsStore(JsonStore[List[CustomPreset]]):
    """Manages loading and saving :class:`CustomPreset` objects to a JSON file.

    On construction the store loads any previously saved presets from *path*.
    If no user presets file exists yet, the store is seeded from the bundled
    ``presets.json`` so new users start with useful examples.

    Subsequent calls to :meth:`save_preset` and :meth:`delete_preset` update
    the in-memory list and immediately persist the change to disk.

    Args:
        path: Path to the JSON file used for persistence.  Defaults to
            ``~/.rbcopy/presets.json`` when *None* is passed.
    """

    def __init__(self, path: Path | None = None) -> None:
        resolved: Path = path if path is not None else _DEFAULT_PRESETS_PATH
        super().__init__(adapter=_PRESETS_ADAPTER, path=resolved)
        self._presets: List[CustomPreset] = []
        self._load()

    @property
    def presets(self) -> List[CustomPreset]:
        """Return a snapshot of the current presets list."""
        return list(self._presets)

    def get_preset(self, name: str) -> CustomPreset | None:
        """Return the preset with *name*, or ``None`` if not found."""
        for preset in self._presets:
            if preset.name == name:
                return preset
        return None

    def save_preset(self, preset: CustomPreset) -> bool:
        """Add *preset* (or replace an existing one with the same name) and persist.

        If the disk write fails the in-memory list is rolled back to its previous
        state so it stays consistent with what is on disk, and ``False`` is
        returned.

        Args:
            preset: The :class:`CustomPreset` to store.

        Returns:
            ``True`` if the preset was persisted successfully, ``False`` otherwise.
        """
        previous = list(self._presets)
        self._presets = [p for p in self._presets if p.name != preset.name] + [preset]
        if not self._persist(self._presets):
            self._presets = previous
            return False
        return True

    def delete_preset(self, name: str) -> None:
        """Remove the preset named *name* and persist the change.

        Args:
            name: The name of the preset to remove.  A no-op if not found.
        """
        self._presets = [p for p in self._presets if p.name != name]
        self._persist(self._presets)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load presets from the JSON file.

        If the user presets file does not exist yet, seeds the store from
        the bundled presets shipped with the package.  Silently initialises
        to an empty list if both sources fail.

        When the user file *does* exist, any bundled preset whose name is not
        already in the user list is merged in so that presets added in newer
        application versions are automatically available to existing users.
        User presets whose name matches a bundled preset are never overwritten.
        """
        if not self._path.exists():
            bundled = _load_bundled_presets()
            if bundled:
                logger.debug(
                    "No user presets found at %s; seeding from %d bundled preset(s)",
                    self._path,
                    len(bundled),
                )
                self._presets = bundled
                # Persist immediately so subsequent launches load from disk.
                self._persist(self._presets)
            else:
                self._presets = []
            return

        loaded = self._load_from_disk()
        if loaded is None:
            logger.warning(
                "Failed to load custom presets from %s; the file may be corrupted "
                "or contain invalid data — initialising with empty presets",
                self._path,
            )
            self._presets = []
            return

        self._presets = loaded
        self._merge_bundled_updates()

    def _merge_bundled_updates(self) -> None:
        """Insert bundled presets that are not yet in the user's list.

        Called after a successful load from disk. Any bundled preset whose
        name is not already present is prepended so newly added bundled
        presets appear alongside the existing bundled ones.  Presets that
        the user has kept (including customised copies of bundled names)
        are left completely untouched.

        If the merge yields new presets the updated list is persisted to
        disk immediately.
        """
        bundled = _load_bundled_presets()
        user_names: set[str] = {p.name for p in self._presets}
        new_bundled = [p for p in bundled if p.name not in user_names]
        if not new_bundled:
            return
        logger.debug(
            "Merging %d new bundled preset(s) into user presets at %s",
            len(new_bundled),
            self._path,
        )
        # Prepend so newly shipped bundled presets appear at the top.
        self._presets = new_bundled + self._presets
        self._persist(self._presets)
