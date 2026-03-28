"""Tests for rbcopy.notifications."""

from __future__ import annotations

import subprocess
from unittest.mock import patch


from rbcopy.notifications import notify_job_complete


# ---------------------------------------------------------------------------
# Platform guard
# ---------------------------------------------------------------------------


def test_notify_is_noop_on_non_windows() -> None:
    """notify_job_complete must return without calling subprocess on non-Windows."""
    with patch("rbcopy.notifications.sys") as mock_sys:
        mock_sys.platform = "linux"
        with patch("rbcopy.notifications.subprocess.Popen") as mock_popen:
            notify_job_complete("Title", "Message")

    mock_popen.assert_not_called()


def test_notify_is_noop_on_darwin() -> None:
    """notify_job_complete must return without calling subprocess on macOS."""
    with patch("rbcopy.notifications.sys") as mock_sys:
        mock_sys.platform = "darwin"
        with patch("rbcopy.notifications.subprocess.Popen") as mock_popen:
            notify_job_complete("Title", "Message")

    mock_popen.assert_not_called()


# ---------------------------------------------------------------------------
# Windows happy path
# ---------------------------------------------------------------------------


def test_notify_calls_popen_on_windows() -> None:
    """notify_job_complete calls subprocess.Popen on Windows."""
    with patch("rbcopy.notifications.sys") as mock_sys:
        mock_sys.platform = "win32"
        with patch("rbcopy.notifications.subprocess.Popen") as mock_popen:
            notify_job_complete("Job Done", "3 files copied.")

    mock_popen.assert_called_once()


def test_notify_uses_powershell_exe() -> None:
    """The first element of the Popen command list must be 'powershell.exe'."""
    with patch("rbcopy.notifications.sys") as mock_sys:
        mock_sys.platform = "win32"
        with patch("rbcopy.notifications.subprocess.Popen") as mock_popen:
            notify_job_complete("Title", "Body")

    cmd: list[str] = mock_popen.call_args.args[0]
    assert cmd[0] == "powershell.exe"


def test_notify_passes_no_profile_flag() -> None:
    """The PowerShell invocation must include -NoProfile to speed up startup."""
    with patch("rbcopy.notifications.sys") as mock_sys:
        mock_sys.platform = "win32"
        with patch("rbcopy.notifications.subprocess.Popen") as mock_popen:
            notify_job_complete("Title", "Body")

    cmd: list[str] = mock_popen.call_args.args[0]
    assert "-NoProfile" in cmd


def test_notify_passes_hidden_window_style() -> None:
    """The PowerShell invocation must hide the console window."""
    with patch("rbcopy.notifications.sys") as mock_sys:
        mock_sys.platform = "win32"
        with patch("rbcopy.notifications.subprocess.Popen") as mock_popen:
            notify_job_complete("Title", "Body")

    cmd: list[str] = mock_popen.call_args.args[0]
    assert "-WindowStyle" in cmd
    window_style_index = cmd.index("-WindowStyle")
    assert cmd[window_style_index + 1] == "Hidden"


def test_notify_passes_command_flag() -> None:
    """The PowerShell invocation must use -Command to pass inline code."""
    with patch("rbcopy.notifications.sys") as mock_sys:
        mock_sys.platform = "win32"
        with patch("rbcopy.notifications.subprocess.Popen") as mock_popen:
            notify_job_complete("Title", "Body")

    cmd: list[str] = mock_popen.call_args.args[0]
    assert "-Command" in cmd


def test_notify_embeds_title_in_command() -> None:
    """The title string must appear inside the inline PowerShell command."""
    with patch("rbcopy.notifications.sys") as mock_sys:
        mock_sys.platform = "win32"
        with patch("rbcopy.notifications.subprocess.Popen") as mock_popen:
            notify_job_complete("Copy Complete", "All done.")

    cmd: list[str] = mock_popen.call_args.args[0]
    ps_command = cmd[cmd.index("-Command") + 1]
    assert "Copy Complete" in ps_command


def test_notify_embeds_message_in_command() -> None:
    """The message string must appear inside the inline PowerShell command."""
    with patch("rbcopy.notifications.sys") as mock_sys:
        mock_sys.platform = "win32"
        with patch("rbcopy.notifications.subprocess.Popen") as mock_popen:
            notify_job_complete("Title", "5 files copied successfully.")

    cmd: list[str] = mock_popen.call_args.args[0]
    ps_command = cmd[cmd.index("-Command") + 1]
    assert "5 files copied successfully." in ps_command


def test_notify_redirects_stdout_and_stderr_to_devnull() -> None:
    """Popen must redirect stdout and stderr to DEVNULL to suppress any output."""
    with patch("rbcopy.notifications.sys") as mock_sys:
        mock_sys.platform = "win32"
        with patch("rbcopy.notifications.subprocess.Popen") as mock_popen:
            notify_job_complete("Title", "Body")

    kwargs = mock_popen.call_args.kwargs
    assert kwargs.get("stdout") == subprocess.DEVNULL
    assert kwargs.get("stderr") == subprocess.DEVNULL


def test_notify_sets_create_no_window_flag() -> None:
    """Popen must set CREATE_NO_WINDOW to prevent a taskbar flash."""
    with patch("rbcopy.notifications.sys") as mock_sys:
        mock_sys.platform = "win32"
        with patch("rbcopy.notifications.subprocess.Popen") as mock_popen:
            with patch("rbcopy.notifications.subprocess.CREATE_NO_WINDOW", 0x08000000, create=True):
                notify_job_complete("Title", "Body")

    kwargs = mock_popen.call_args.kwargs
    assert kwargs.get("creationflags") == 0x08000000


# ---------------------------------------------------------------------------
# Single-quote escaping
# ---------------------------------------------------------------------------


def test_notify_escapes_single_quotes_in_title() -> None:
    """Single quotes in the title must be doubled to avoid breaking PS string literals."""
    with patch("rbcopy.notifications.sys") as mock_sys:
        mock_sys.platform = "win32"
        with patch("rbcopy.notifications.subprocess.Popen") as mock_popen:
            notify_job_complete("It's done", "Body")

    cmd: list[str] = mock_popen.call_args.args[0]
    ps_command = cmd[cmd.index("-Command") + 1]
    assert "It''s done" in ps_command


def test_notify_escapes_single_quotes_in_message() -> None:
    """Single quotes in the message must be doubled to avoid breaking PS string literals."""
    with patch("rbcopy.notifications.sys") as mock_sys:
        mock_sys.platform = "win32"
        with patch("rbcopy.notifications.subprocess.Popen") as mock_popen:
            notify_job_complete("Title", "Can't copy file.")

    cmd: list[str] = mock_popen.call_args.args[0]
    ps_command = cmd[cmd.index("-Command") + 1]
    assert "Can''t copy file." in ps_command


# ---------------------------------------------------------------------------
# Exception safety
# ---------------------------------------------------------------------------


def test_notify_does_not_raise_when_powershell_missing() -> None:
    """notify_job_complete must not raise when powershell.exe is not found."""
    with patch("rbcopy.notifications.sys") as mock_sys:
        mock_sys.platform = "win32"
        with patch("rbcopy.notifications.subprocess.Popen", side_effect=FileNotFoundError):
            # Must not raise.
            notify_job_complete("Title", "Body")


def test_notify_does_not_raise_on_generic_oserror() -> None:
    """notify_job_complete must not raise for any unexpected subprocess error."""
    with patch("rbcopy.notifications.sys") as mock_sys:
        mock_sys.platform = "win32"
        with patch("rbcopy.notifications.subprocess.Popen", side_effect=OSError("access denied")):
            # Must not raise.
            notify_job_complete("Title", "Body")


def test_notify_does_not_raise_on_unexpected_exception() -> None:
    """notify_job_complete must silently swallow any unexpected exception."""
    with patch("rbcopy.notifications.sys") as mock_sys:
        mock_sys.platform = "win32"
        with patch("rbcopy.notifications.subprocess.Popen", side_effect=RuntimeError("unexpected")):
            # Must not raise.
            notify_job_complete("Title", "Body")
