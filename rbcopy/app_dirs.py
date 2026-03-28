"""Application directory resolution for RBCopy.

This module is the single source of truth for the data directory in which
logs, presets, preferences, geometry, and all other persistent files are
stored.  No other module in the package should hardcode a path under
``~/.rbcopy`` or any similar literal — they must call :func:`get_data_dir`
instead.

Resolution priority (first match wins):

1. ``RBCOPY_DATA_DIR`` environment variable — intended for CI, testing, and
   power users who want a non-standard location without touching the UI.
2. ``~/.rbcopy_location`` bootstrap pointer file — written by
   :func:`set_data_dir` when the user changes the data directory via
   *File -> Preferences -> Storage*.  This is the only file that lives
   permanently outside the configurable data directory.
3. Platform default -- ``%LOCALAPPDATA%\\RBCopy`` on Windows,
   ``~/.rbcopy`` on all other platforms.

Logs are stored in a ``logs/`` subdirectory of the data directory so that
JSON configuration files and log files remain clearly separated.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from rbcopy.conf.settings import Settings

logger = logging.getLogger(__name__)

_BOOTSTRAP_PATH: Path = Path.home() / ".rbcopy_location"
_APP_DIR_NAME_WINDOWS: str = "RBCopy"
_APP_DIR_NAME_UNIX: str = ".rbcopy"


def _platform_default() -> Path:
    """Return the platform-appropriate default data directory."""
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            return Path(local_app_data) / _APP_DIR_NAME_WINDOWS
        return Path.home() / _APP_DIR_NAME_WINDOWS
    return Path.home() / _APP_DIR_NAME_UNIX


def get_data_dir() -> Path:
    """Return the resolved data directory path.

    The directory is not guaranteed to exist — callers that need it to be
    present should call ``.mkdir(parents=True, exist_ok=True)`` first.
    :func:`get_log_dir` does this automatically.
    """
    env_override: Path | None = Settings().data_dir
    if env_override is not None:
        logger.debug("Data dir from RBCOPY_DATA_DIR env var: %s", env_override)
        return env_override

    if _BOOTSTRAP_PATH.exists():
        try:
            data = json.loads(_BOOTSTRAP_PATH.read_text(encoding="utf-8"))
            configured = data.get("data_dir", "").strip()
            if configured:
                logger.debug("Data dir from bootstrap file: %s", configured)
                return Path(configured)
        except (OSError, json.JSONDecodeError, ValueError):
            logger.debug(
                "Bootstrap location file unreadable; falling back to platform default",
                exc_info=True,
            )

    default = _platform_default()
    logger.debug("Data dir from platform default: %s", default)
    return default


def get_log_dir() -> Path:
    """Return the log subdirectory, creating it if necessary.

    Log files live in ``{data_dir}/logs/`` so JSON config files and
    timestamped log files are clearly separated at the top level.
    """
    log_dir = get_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def set_data_dir(path: Path) -> bool:
    """Write *path* to the bootstrap pointer file.

    The change takes effect on next launch; the running session continues
    to use the directory that was resolved at startup.

    Returns:
        ``True`` on success, ``False`` if an ``OSError`` prevented the write.
    """
    try:
        _BOOTSTRAP_PATH.write_text(
            json.dumps({"data_dir": str(path)}, indent=2),
            encoding="utf-8",
        )
        logger.info("Data directory configured: %s  (bootstrap: %s)", path, _BOOTSTRAP_PATH)
        return True
    except OSError:
        logger.exception("Failed to write bootstrap file: %s", _BOOTSTRAP_PATH)
        return False


def clear_data_dir() -> bool:
    """Remove the bootstrap pointer file, reverting to the platform default.

    Returns:
        ``True`` if the file was removed or did not exist, ``False`` on error.
    """
    if not _BOOTSTRAP_PATH.exists():
        return True
    try:
        _BOOTSTRAP_PATH.unlink()
        logger.info("Data directory reset to platform default")
        return True
    except OSError:
        logger.exception("Failed to remove bootstrap file: %s", _BOOTSTRAP_PATH)
        return False


def validate_data_dir(path: Path) -> str | None:
    """Return ``None`` if *path* is acceptable, or a human-readable error string.

    Checks (in order):

    1. Must be absolute.
    2. Must be resolvable on this OS.
    3. Must not be the home directory itself.
    4. Must be creatable and writable (probe file written and deleted).
    """
    if not path.is_absolute():
        return (
            "The path must be absolute "
            r"(for example: C:\Users\you\RBCopy or /home/you/.rbcopy)."
        )

    try:
        resolved = path.resolve()
    except (OSError, ValueError) as exc:
        return f"Invalid path: {exc}"

    try:
        if resolved == Path.home().resolve():
            return "Cannot use the home directory itself as the data directory."
    except OSError:
        pass

    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".rbcopy_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return f"Directory is not writable: {exc}"

    return None
