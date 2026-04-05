"""Application directory resolution for GL_Tools applications.

This module is the single source of truth for the data directory in which
logs, presets, preferences, geometry, and all other persistent files are
stored.  No other module in the package should hardcode a path directly —
they must call :func:`get_data_dir` instead.

Resolution priority for the GL_Tools base directory (first match wins):

1. ``~/.gl_tools_location`` bootstrap pointer file — written by
   :func:`set_data_dir` when the user changes the data directory via
   *File -> Preferences -> Storage*.  This is the only file that lives
   permanently outside the configurable data directory.
2. ``U:\\GL_Tools`` — used when the ``U:`` drive is available (e.g. a
   network share or mapped drive used for shared team configuration).
3. Platform default — ``%LOCALAPPDATA%\\GL_Tools`` on Windows,
   ``~/.gl_tools`` on all other platforms.

:func:`get_data_dir` accepts an *app_name* argument (e.g. ``'rbcopy'`` or
``'loadv5'``) and returns ``{base_dir}/{app_name}``, creating that
subdirectory if it does not already exist.

Logs are stored in a ``logs/`` subdirectory of the data directory so that
JSON configuration files and log files remain clearly separated.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_BOOTSTRAP_PATH: Path = Path.home() / ".gl_tools_location"
_NETWORK_DRIVE_BASE: Path = Path("U:/GL_Tools")
_BASE_DIR_NAME_WINDOWS: str = "GL_Tools"
_BASE_DIR_NAME_UNIX: str = ".gl_tools"


def _u_drive_exists() -> bool:
    """Return ``True`` when the ``U:\\`` drive is accessible on this system."""
    if sys.platform != "win32":
        return False
    try:
        return Path("U:/").exists()
    except OSError:
        return False


def _platform_default() -> Path:
    """Return the platform-appropriate default GL_Tools base directory."""
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            return Path(local_app_data) / _BASE_DIR_NAME_WINDOWS
        return Path.home() / _BASE_DIR_NAME_WINDOWS
    return Path.home() / _BASE_DIR_NAME_UNIX


def _resolve_base_dir() -> Path:
    """Return the GL_Tools base directory using the three-step priority."""
    if _BOOTSTRAP_PATH.exists():
        try:
            data = json.loads(_BOOTSTRAP_PATH.read_text(encoding="utf-8"))
            configured = data.get("data_dir", "").strip()
            if configured:
                logger.debug("Base dir from bootstrap file: %s", configured)
                return Path(configured)
        except (OSError, json.JSONDecodeError, ValueError):
            logger.debug(
                "Bootstrap location file unreadable; proceeding to next source",
                exc_info=True,
            )

    if _u_drive_exists():
        logger.debug("Base dir from U:\\ drive: %s", _NETWORK_DRIVE_BASE)
        return _NETWORK_DRIVE_BASE

    default = _platform_default()
    logger.debug("Base dir from platform default: %s", default)
    return default


def get_data_dir(app_name: str) -> Path:
    """Return the resolved data directory for *app_name*, creating it if needed.

    The returned path is ``{base_dir}/{app_name}`` where ``base_dir`` is
    resolved via :func:`_resolve_base_dir`.  The directory (including any
    missing parents) is created before being returned.
    """
    app_dir = _resolve_base_dir() / app_name
    app_dir.mkdir(parents=True, exist_ok=True)
    logger.debug("Data dir for %r: %s", app_name, app_dir)
    return app_dir


def get_log_dir() -> Path:
    """Return the log subdirectory for this application, creating it if needed.

    Log files live in ``{data_dir}/logs/`` so JSON config files and
    timestamped log files are clearly separated at the top level.
    """
    log_dir = get_data_dir(app_name="rbcopy") / "logs"
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
            r"(for example: C:\Users\you\GL_Tools or /home/you/.gl_tools)."
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
        probe = path / ".gl_tools_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return f"Directory is not writable: {exc}"

    return None
