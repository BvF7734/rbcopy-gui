"""Shared test helpers for the rbcopy test suite."""

from __future__ import annotations

from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock


def make_mock_async_proc(
    returncode: int = 0,
    output: str = "",
    pid: int | None = None,
) -> MagicMock:
    """Return a MagicMock that mimics asyncio.subprocess.Process for robocopy streaming.

    Args:
        returncode: The exit code the mock process should report.
        output: The stdout content the mock process should yield, as a plain string.
        pid: Optional PID to assign to the mock process.
    """
    mock_proc = MagicMock()
    mock_proc.returncode = returncode
    if pid is not None:
        mock_proc.pid = pid

    # Encode output lines as bytes to match asyncio subprocess byte output.
    lines = [line.encode("utf-8") for line in output.splitlines(keepends=True)]

    async def _aiter_stdout() -> AsyncGenerator[bytes, None]:
        for line in lines:
            yield line

    mock_proc.stdout = _aiter_stdout()
    mock_proc.wait = AsyncMock(return_value=returncode)
    return mock_proc
