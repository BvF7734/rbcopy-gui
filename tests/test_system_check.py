"""Tests for rbcopy.system_check – pre-flight environment checks."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

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
# run_preflight_checks – platform guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_run_preflight_checks_non_windows_fails(platform: str) -> None:
    """On non-Windows platforms the function must return a failed PreflightResult."""
    with patch("rbcopy.system_check.sys.platform", platform):
        result = run_preflight_checks()

    assert result.ok is False
    assert any("Windows" in e for e in result.errors)


# ---------------------------------------------------------------------------
# run_preflight_checks – robocopy availability
# ---------------------------------------------------------------------------


def _mock_ctypes_admin(is_admin: bool) -> MagicMock:
    """Return a mock ctypes module whose IsUserAnAdmin reports *is_admin*."""
    mock_ctypes = MagicMock()
    mock_ctypes.windll.shell32.IsUserAnAdmin.return_value = int(is_admin)
    return mock_ctypes


def test_run_preflight_checks_robocopy_found() -> None:
    """When robocopy is on PATH, the check should pass."""
    with patch("rbcopy.system_check.sys.platform", "win32"):
        with patch("rbcopy.system_check.shutil.which", return_value="C:\\Windows\\robocopy.exe"):
            with patch.dict("sys.modules", {"ctypes": _mock_ctypes_admin(True)}):
                result = run_preflight_checks()

    assert result.ok is True
    assert any("robocopy" in m for m in result.messages)
    assert result.errors == []


def test_run_preflight_checks_robocopy_not_found() -> None:
    """When robocopy is absent from PATH, the check should fail."""
    with patch("rbcopy.system_check.sys.platform", "win32"):
        with patch("rbcopy.system_check.shutil.which", return_value=None):
            with patch.dict("sys.modules", {"ctypes": _mock_ctypes_admin(True)}):
                result = run_preflight_checks()

    assert result.ok is False
    assert any("robocopy" in e for e in result.errors)


# ---------------------------------------------------------------------------
# run_preflight_checks – admin privileges
# ---------------------------------------------------------------------------


def test_run_preflight_checks_admin_ok() -> None:
    """When the process is elevated, the admin check should pass."""
    with patch("rbcopy.system_check.sys.platform", "win32"):
        with patch("rbcopy.system_check.shutil.which", return_value="C:\\Windows\\robocopy.exe"):
            with patch.dict("sys.modules", {"ctypes": _mock_ctypes_admin(True)}):
                result = run_preflight_checks()

    assert result.ok is True
    assert any("Administrator" in m for m in result.messages)


def test_run_preflight_checks_not_admin() -> None:
    """When the process is not elevated, the admin check should fail."""
    with patch("rbcopy.system_check.sys.platform", "win32"):
        with patch("rbcopy.system_check.shutil.which", return_value="C:\\Windows\\robocopy.exe"):
            with patch.dict("sys.modules", {"ctypes": _mock_ctypes_admin(False)}):
                result = run_preflight_checks()

    assert result.ok is False
    assert any("Administrator" in e for e in result.errors)


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


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only code path")
def test_run_preflight_checks_admin_attribute_error_fallback() -> None:
    """IsUserAnAdmin raising AttributeError is handled; process is treated as non-admin."""
    import ctypes

    with patch("rbcopy.system_check.shutil.which", return_value="C:\\Windows\\System32\\robocopy.exe"):
        # Simulate a stripped Windows environment where IsUserAnAdmin is unavailable
        # by making the call to it raise AttributeError.
        with patch.object(ctypes.windll.shell32, "IsUserAnAdmin", side_effect=AttributeError()):  # type: ignore[attr-defined]
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
