"""Shared pytest fixtures for the rbcopy test suite."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from rbcopy.logger import setup_logging


@pytest.fixture
def log_dir(tmp_path: Path) -> Iterator[Path]:
    """Provide a fresh rbcopy logger writing to *tmp_path*.

    Resets the logger before each test and flushes/closes all handlers
    afterwards so tests are fully isolated from one another.
    """
    log = logging.getLogger("rbcopy")
    for handler in list(log.handlers):
        handler.close()
        log.removeHandler(handler)

    setup_logging(log_dir=tmp_path)

    yield tmp_path

    for handler in list(log.handlers):
        handler.flush()
        handler.close()
        log.removeHandler(handler)
