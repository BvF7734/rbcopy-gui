"""Unified logging configuration for rbcopy.

Call :func:`setup_logging` once at application start-up to configure the
``rbcopy`` logger so that:

* **INFO** (and above) messages are printed to the terminal using
  :class:`rich.logging.RichHandler` for coloured, formatted output.
* **DEBUG** (and above) messages are saved to a timestamped log file under
  *log_dir* (defaults to the current working directory) for persistent auditing.

The timestamped filename format is ``robocopy_job_YYYYMMDD_HHMMSS.log``.

Call :func:`rotate_logs` after :func:`setup_logging` to prune old log files
and prevent unbounded disk growth.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from rich.logging import RichHandler

# Module-level logger for internal diagnostics.
_internal_logger = logging.getLogger(__name__)

# Filename prefix and glob pattern used by both setup_logging and rotate_logs.
_LOG_PREFIX = "robocopy_job_"
_LOG_GLOB = f"{_LOG_PREFIX}*.log"

# Default number of log files to retain when rotating.
_DEFAULT_KEEP = 20


def setup_logging(log_dir: Path | None = None) -> logging.Logger:
    """Configure and return the root ``rbcopy`` application logger.

    The function is idempotent: if the logger already has handlers attached
    (e.g. because :func:`setup_logging` was called earlier in the same process)
    it returns the existing logger unchanged so that duplicate handlers are not
    added during testing or re-initialisation.

    Args:
        log_dir: Directory in which the timestamped log file will be created.
            Defaults to the current working directory.  The directory is created
            if it does not exist.

    Returns:
        The configured :class:`logging.Logger` for the ``rbcopy`` namespace.
    """
    app_logger = logging.getLogger("rbcopy")

    # Guard against double-initialisation (e.g. in test suites).
    if app_logger.handlers:
        return app_logger

    app_logger.setLevel(logging.DEBUG)

    # ── Console handler (INFO+) via Rich ─────────────────────────────────────
    console_handler = RichHandler(
        level=logging.INFO,
        rich_tracebacks=True,
        show_path=False,
    )
    console_handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))
    app_logger.addHandler(console_handler)

    # ── File handler (DEBUG+) with timestamped filename ───────────────────────
    resolved_dir = log_dir if log_dir is not None else Path.cwd()
    resolved_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = resolved_dir / f"{_LOG_PREFIX}{timestamp}.log"

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    app_logger.addHandler(file_handler)

    # Logged at INFO so the path appears on the console as well as in the
    # file, giving users a clear pointer to the current session's log.
    _internal_logger.info("Log file: %s", log_file)
    return app_logger


def rotate_logs(log_dir: Path, keep: int = _DEFAULT_KEEP) -> list[Path]:
    """Delete old log files in *log_dir*, retaining only the *keep* most recent.

    Files are ordered by modification time so the newest *keep* files are
    always preserved regardless of filename ordering.  Deletion failures are
    logged at WARNING level and silently skipped so a single undeletable file
    never prevents other files from being cleaned up.

    This function is intentionally separate from :func:`setup_logging` so it
    can be called after the new session log file has been created, ensuring
    the current session is always counted among the retained files.

    Args:
        log_dir: Directory to scan for ``robocopy_job_*.log`` files.
        keep: Number of most-recent log files to retain.  Must be >= 1.

    Returns:
        A list of :class:`Path` objects for every file that was successfully
        deleted.  An empty list is returned when no rotation was needed or
        when *log_dir* does not exist.
    """
    if keep < 1:
        raise ValueError(f"keep must be >= 1, got {keep!r}")

    if not log_dir.is_dir():
        return []

    log_files = sorted(
        log_dir.glob(_LOG_GLOB),
        key=lambda p: p.stat().st_mtime,
    )

    to_delete = log_files[:-keep] if len(log_files) > keep else []
    deleted: list[Path] = []

    for path in to_delete:
        try:
            path.unlink()
            deleted.append(path)
            _internal_logger.debug("Rotated old log file: %s", path)
        except OSError:
            _internal_logger.warning(
                "Could not delete old log file during rotation: %s",
                path,
                exc_info=True,
            )

    if deleted:
        _internal_logger.debug(
            "Log rotation complete: deleted %d file(s), keeping %d",
            len(deleted),
            keep,
        )

    return deleted
