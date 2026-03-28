"""Tests for rbcopy.logger – unified logging configuration."""

from __future__ import annotations

import logging
import pytest
from pathlib import Path
from unittest.mock import patch

from rbcopy.logger import setup_logging


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_logger() -> None:
    """Remove all handlers from the rbcopy logger so tests start fresh."""
    log = logging.getLogger("rbcopy")
    for handler in list(log.handlers):
        handler.close()
        log.removeHandler(handler)


# ---------------------------------------------------------------------------
# Basic configuration tests
# ---------------------------------------------------------------------------


def test_setup_logging_returns_logger(tmp_path: Path) -> None:
    _reset_logger()
    log = setup_logging(log_dir=tmp_path)
    assert isinstance(log, logging.Logger)
    assert log.name == "rbcopy"
    _reset_logger()


def test_setup_logging_creates_log_file(tmp_path: Path) -> None:
    _reset_logger()
    setup_logging(log_dir=tmp_path)
    log_files = list(tmp_path.glob("robocopy_job_*.log"))
    assert len(log_files) == 1
    _reset_logger()


def test_log_filename_format(tmp_path: Path) -> None:
    _reset_logger()
    setup_logging(log_dir=tmp_path)
    log_files = list(tmp_path.glob("robocopy_job_*.log"))
    assert len(log_files) == 1
    name = log_files[0].name
    # Expected pattern: robocopy_job_YYYYMMDD_HHMMSS.log
    assert name.startswith("robocopy_job_")
    assert name.endswith(".log")
    timestamp_part = name[len("robocopy_job_") : -len(".log")]
    assert len(timestamp_part) == len("YYYYMMDD_HHMMSS")
    _reset_logger()


def test_setup_logging_attaches_two_handlers(tmp_path: Path) -> None:
    """Exactly two handlers should be attached: RichHandler + FileHandler."""
    _reset_logger()
    log = setup_logging(log_dir=tmp_path)
    assert len(log.handlers) == 2
    _reset_logger()


def test_setup_logging_file_handler_level_is_debug(tmp_path: Path) -> None:
    _reset_logger()
    log = setup_logging(log_dir=tmp_path)
    file_handlers = [h for h in log.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1
    assert file_handlers[0].level == logging.DEBUG
    _reset_logger()


def test_setup_logging_logger_level_is_debug(tmp_path: Path) -> None:
    _reset_logger()
    log = setup_logging(log_dir=tmp_path)
    assert log.level == logging.DEBUG
    _reset_logger()


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_setup_logging_idempotent(tmp_path: Path) -> None:
    """Calling setup_logging twice must not add duplicate handlers."""
    _reset_logger()
    log1 = setup_logging(log_dir=tmp_path)
    handler_count_after_first = len(log1.handlers)
    log2 = setup_logging(log_dir=tmp_path)
    assert log1 is log2
    assert len(log2.handlers) == handler_count_after_first
    _reset_logger()


# ---------------------------------------------------------------------------
# Log file content
# ---------------------------------------------------------------------------


def test_debug_messages_written_to_file(tmp_path: Path) -> None:
    _reset_logger()
    log = setup_logging(log_dir=tmp_path)
    log.debug("debug-sentinel-message")
    log.info("info-sentinel-message")

    # Flush all handlers.
    for handler in log.handlers:
        handler.flush()

    log_file = next(tmp_path.glob("robocopy_job_*.log"))
    content = log_file.read_text(encoding="utf-8")
    assert "debug-sentinel-message" in content
    assert "info-sentinel-message" in content
    _reset_logger()


def test_log_file_path_written_to_log_file(tmp_path: Path) -> None:
    """The log file path must appear in the log file itself (INFO level)."""
    _reset_logger()
    setup_logging(log_dir=tmp_path)

    log_file = next(tmp_path.glob("robocopy_job_*.log"))
    for handler in logging.getLogger("rbcopy").handlers:
        handler.flush()

    content = log_file.read_text(encoding="utf-8")
    # The path of the log file should be written into the log at INFO level.
    assert str(log_file) in content
    _reset_logger()


# ---------------------------------------------------------------------------
# Default log_dir behaviour
# ---------------------------------------------------------------------------


def test_setup_logging_creates_log_dir(tmp_path: Path) -> None:
    """setup_logging must create the log directory if it does not exist."""
    _reset_logger()
    new_dir = tmp_path / "nested" / "logs"
    assert not new_dir.exists()
    setup_logging(log_dir=new_dir)
    assert new_dir.exists()
    _reset_logger()


# ---------------------------------------------------------------------------
# rotate_logs
# ---------------------------------------------------------------------------


def test_rotate_logs_deletes_oldest_files(tmp_path: Path) -> None:
    """rotate_logs must delete the oldest files when count exceeds keep."""
    import time
    from rbcopy.logger import rotate_logs

    files = []
    for i in range(5):
        f = tmp_path / f"robocopy_job_2024010{i + 1}_120000.log"
        f.write_text("x", encoding="utf-8")
        files.append(f)
        # Brief pause so each file gets a distinct mtime on all platforms.
        time.sleep(0.05)

    deleted = rotate_logs(tmp_path, keep=3)

    assert len(deleted) == 2
    assert not files[0].exists()
    assert not files[1].exists()
    assert files[2].exists()
    assert files[3].exists()
    assert files[4].exists()


def test_rotate_logs_does_nothing_when_under_limit(tmp_path: Path) -> None:
    """rotate_logs must not delete any files when count is within keep limit."""
    from rbcopy.logger import rotate_logs

    for i in range(3):
        (tmp_path / f"robocopy_job_2024010{i + 1}_120000.log").write_text("x", encoding="utf-8")

    deleted = rotate_logs(tmp_path, keep=20)

    assert deleted == []
    assert len(list(tmp_path.glob("*.log"))) == 3


def test_rotate_logs_does_nothing_when_exactly_at_limit(tmp_path: Path) -> None:
    """rotate_logs must not delete any files when count equals keep exactly."""
    from rbcopy.logger import rotate_logs

    for i in range(5):
        (tmp_path / f"robocopy_job_2024010{i + 1}_120000.log").write_text("x", encoding="utf-8")

    deleted = rotate_logs(tmp_path, keep=5)

    assert deleted == []


def test_rotate_logs_returns_empty_when_dir_missing(tmp_path: Path) -> None:
    """rotate_logs must return [] gracefully when the directory does not exist."""
    from rbcopy.logger import rotate_logs

    result = rotate_logs(tmp_path / "nonexistent")

    assert result == []


def test_rotate_logs_ignores_non_log_files(tmp_path: Path) -> None:
    """rotate_logs must only count and delete robocopy_job_*.log files."""
    from rbcopy.logger import rotate_logs

    for i in range(5):
        (tmp_path / f"robocopy_job_2024010{i + 1}_120000.log").write_text("x", encoding="utf-8")
    # This file must never be touched.
    other = tmp_path / "notes.txt"
    other.write_text("keep me", encoding="utf-8")

    rotate_logs(tmp_path, keep=3)

    assert other.exists()


def test_rotate_logs_raises_on_invalid_keep(tmp_path: Path) -> None:
    """rotate_logs must raise ValueError when keep is less than 1."""
    from rbcopy.logger import rotate_logs

    with pytest.raises(ValueError, match="keep must be >= 1"):
        rotate_logs(tmp_path, keep=0)


def test_rotate_logs_continues_on_deletion_failure(tmp_path: Path) -> None:
    """rotate_logs must skip undeletable files and still delete the others."""
    import time
    from rbcopy.logger import rotate_logs

    files = []
    for i in range(4):
        f = tmp_path / f"robocopy_job_2024010{i + 1}_120000.log"
        f.write_text("x", encoding="utf-8")
        files.append(f)
        time.sleep(0.05)

    original_unlink = Path.unlink

    def selective_fail(self: Path, missing_ok: bool = False) -> None:
        if self == files[0]:
            raise OSError("permission denied")
        original_unlink(self, missing_ok=missing_ok)

    with patch.object(Path, "unlink", selective_fail):
        rotate_logs(tmp_path, keep=2)

    assert files[0].exists()
    assert not files[1].exists()
