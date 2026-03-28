"""Windows desktop toast notifications for rbcopy.

Provides a single public function, :func:`notify_job_complete`, that sends a
native Windows toast notification via an inline PowerShell command.  The
implementation intentionally avoids writing any ``.ps1`` file to disk, so it
is not subject to PowerShell script-file execution-policy restrictions.

On non-Windows platforms the function is a no-op so the rest of the
application remains fully portable.  All exceptions are caught and logged so
a notification failure can never propagate into or abort a running copy job.
"""

from __future__ import annotations

import subprocess
import sys
from logging import getLogger

logger = getLogger(__name__)

# PowerShell's own registered Windows Application User Model ID (AUMID).
#
# Windows requires the app ID passed to ToastNotificationManager to be
# registered in the Windows registry.  Using an unregistered ID (e.g. the
# package name "rbcopy") causes Windows to silently discard the toast even
# though the PowerShell process exits cleanly and the log shows "dispatched".
#
# PowerShell is always registered on any Windows system that has it installed,
# so borrowing its AUMID is the most reliable zero-dependency approach.
_APP_ID: str = "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"


def notify_job_complete(title: str, message: str) -> None:
    """Send a native Windows toast notification.

    Spawns a hidden PowerShell process with an inline ``-Command`` string that
    uses the WinRT ``ToastNotificationManager`` API.  Because the notification
    code is passed as a command string rather than a script file, it bypasses
    file-based execution-policy signing requirements entirely.

    The call is fire-and-forget: the subprocess is not waited on, so the
    calling coroutine or thread returns immediately.  Any failure — including
    PowerShell not being found, WinRT being unavailable, or Constrained
    Language Mode blocking type access — is caught, logged at DEBUG level, and
    silently discarded so the copy job result is never affected.

    On non-Windows platforms this function returns immediately without doing
    anything.

    Args:
        title:   Short notification title shown in bold at the top of the toast.
        message: Body text shown beneath the title.
    """
    if sys.platform != "win32":
        logger.debug("Toast notifications are only supported on Windows; skipping.")
        return

    # Escape single quotes in caller-supplied strings so they cannot break out
    # of the PowerShell single-quoted string literals used below.
    safe_title: str = title.replace("'", "''")
    safe_message: str = message.replace("'", "''")

    # The inline PowerShell command builds a minimal toast XML payload and
    # dispatches it through the WinRT ToastNotificationManager.  PowerShell's
    # own AUMID is used because it is always registered on any system that has
    # PowerShell installed, guaranteeing that Windows will display the toast
    # rather than silently discarding it.
    ps_command: str = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime]"
        " | Out-Null; "
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime]"
        " | Out-Null; "
        "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument; "
        f'$xml.LoadXml(\'<toast><visual><binding template="ToastGeneric">'
        f"<text>{safe_title}</text>"
        f"<text>{safe_message}</text>"
        f"</binding></visual></toast>'); "
        f"$toast = [Windows.UI.Notifications.ToastNotification]::new($xml); "
        f"[Windows.UI.Notifications.ToastNotificationManager]"
        f"::CreateToastNotifier('{_APP_ID}').Show($toast)"
    )

    try:
        subprocess.Popen(  # noqa: S603
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle",
                "Hidden",
                "-Command",
                ps_command,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            # Prevent the PowerShell window from briefly appearing in the taskbar.
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        logger.debug("Toast notification dispatched: %r / %r", title, message)
    except FileNotFoundError:
        logger.debug("powershell.exe not found; toast notification skipped.")
    except Exception:
        logger.debug("Failed to dispatch toast notification.", exc_info=True)
