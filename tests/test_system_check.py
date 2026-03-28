"""Tests for rbcopy.system_check – pre-flight environment checks."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from rbcopy.system_check import PreflightResult, run_preflight_checks


# ---------------------------------------------------------------------------
# PreflightResult dataclass
# ---------------------------------------------------------------------------


def test_preflight_result_defaults() -> None:
    result = PreflightResult()
    assert result.ok is True
    assert result.messages == []
    assert result.errors == []


def test_preflight_result_status_report_ok() -> None:
    result = PreflightResult(ok=True, messages=["robocopy found"], errors=[])
    report = result.status_report()
    assert "[OK]" in report
    assert "robocopy found" in report


def test_preflight_result_status_report_error() -> None:
    result = PreflightResult(ok=False, messages=[], errors=["robocopy not found"])
    report = result.status_report()
    assert "[FAIL]" in report
    assert "robocopy not found" in report


def test_preflight_result_status_report_mixed() -> None:
    result = PreflightResult(
        ok=False,
        messages=["Something passed"],
        errors=["Something failed"],
    )
    report = result.status_report()
    assert "[OK]" in report
    assert "[FAIL]" in report


# ---------------------------------------------------------------------------
# run_preflight_checks – robocopy availability
# ---------------------------------------------------------------------------


def test_run_preflight_checks_robocopy_found() -> None:
    """When robocopy is on PATH, the check should pass."""
    with patch("rbcopy.system_check.shutil.which", return_value="/usr/bin/robocopy"):
        with patch("rbcopy.system_check.sys.platform", "linux"):
            result = run_preflight_checks()

    assert result.ok is True
    assert any("robocopy" in m for m in result.messages)
    assert result.errors == []


def test_run_preflight_checks_robocopy_not_found() -> None:
    """When robocopy is absent from PATH, the check should fail."""
    with patch("rbcopy.system_check.shutil.which", return_value=None):
        with patch("rbcopy.system_check.sys.platform", "linux"):
            result = run_preflight_checks()

    assert result.ok is False
    assert any("robocopy" in e for e in result.errors)


# ---------------------------------------------------------------------------
# run_preflight_checks – admin privileges (non-Windows skipped)
# ---------------------------------------------------------------------------


def test_run_preflight_checks_admin_skipped_on_linux() -> None:
    """On non-Windows platforms the admin check is skipped (always informational)."""
    with patch("rbcopy.system_check.shutil.which", return_value="/usr/bin/robocopy"):
        with patch("rbcopy.system_check.sys.platform", "linux"):
            result = run_preflight_checks()

    assert any("skipped" in m.lower() for m in result.messages)


@pytest.mark.skipif(sys.platform == "win32", reason="simulates non-Windows path")
def test_run_preflight_checks_non_windows_still_ok() -> None:
    """Full run on non-Windows with robocopy present should pass."""
    with patch("rbcopy.system_check.shutil.which", return_value="/usr/bin/robocopy"):
        result = run_preflight_checks()

    # On non-Windows the admin check is always skipped so ok depends only on
    # robocopy being found.
    assert result.ok is True


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only code path")
def test_run_preflight_checks_admin_true_on_windows() -> None:
    """Simulate an elevated Windows process."""
    import ctypes

    with patch("rbcopy.system_check.shutil.which", return_value="C:\\Windows\\System32\\robocopy.exe"):
        with patch.object(ctypes.windll.shell32, "IsUserAnAdmin", return_value=1):  # type: ignore[attr-defined]
            result = run_preflight_checks()

    assert result.ok is True
    assert any("Administrator" in m for m in result.messages)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only code path")
def test_run_preflight_checks_admin_false_on_windows() -> None:
    """Simulate a non-elevated Windows process."""
    import ctypes

    with patch("rbcopy.system_check.shutil.which", return_value="C:\\Windows\\System32\\robocopy.exe"):
        with patch.object(ctypes.windll.shell32, "IsUserAnAdmin", return_value=0):  # type: ignore[attr-defined]
            result = run_preflight_checks()

    assert result.ok is False
    assert any("Administrator" in e for e in result.errors)


# ---------------------------------------------------------------------------
# status_report round-trip
# ---------------------------------------------------------------------------


def test_status_report_contains_all_messages_and_errors() -> None:
    result = PreflightResult(
        ok=False,
        messages=["check-a passed", "check-b passed"],
        errors=["check-c failed"],
    )
    report = result.status_report()
    assert "check-a passed" in report
    assert "check-b passed" in report
    assert "check-c failed" in report
