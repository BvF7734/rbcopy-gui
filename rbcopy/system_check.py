"""Pre-flight checks for the rbcopy runtime environment.

Call :func:`run_preflight_checks` before launching a robocopy job to verify
that the required binary is available and (on Windows) that the process has the
necessary privileges.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from logging import getLogger

logger = getLogger(__name__)


@dataclass
class PreflightResult:
    """Aggregated outcome of all pre-flight checks.

    Attributes:
        ok: ``True`` when every check passed; ``False`` if any check failed.
        messages: Informational messages from checks that succeeded.
        errors: Error messages from checks that failed.
    """

    ok: bool = True
    messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def status_report(self) -> str:
        """Return a human-readable summary of all check results."""
        lines: list[str] = []
        for msg in self.messages:
            lines.append(f"[OK]    {msg}")
        for err in self.errors:
            lines.append(f"[FAIL]  {err}")
        return "\n".join(lines)


def _check_robocopy_available(result: PreflightResult) -> None:
    """Append a message or error depending on whether robocopy.exe is on PATH."""
    if shutil.which("robocopy") is not None:
        result.messages.append("robocopy.exe found on PATH")
        logger.debug("robocopy.exe found on PATH")
    else:
        result.ok = False
        result.errors.append("robocopy.exe not found on PATH – install or add it to PATH")
        logger.warning("robocopy.exe not found on PATH")


def _check_platform(result: PreflightResult) -> None:
    """Record a fatal error in *result* if not running on Windows.

    robocopy is a Windows-only utility; there is no meaningful way to continue
    on any other platform.  Setting ``result.ok = False`` lets the caller
    surface a proper error dialog rather than terminating the process directly.
    """
    if sys.platform != "win32":
        msg = "RBCopy requires a Windows environment to run."
        result.ok = False
        result.errors.append(msg)
        logger.critical(msg)


def _check_admin_privileges(result: PreflightResult) -> None:
    """Append a message or error depending on whether the process is elevated."""
    # Import ctypes here because ctypes.windll is only available on Windows.
    import ctypes  # noqa: PLC0415

    # Use getattr to avoid a mypy attr-defined error on non-Windows platforms.
    windll = getattr(ctypes, "windll", None)
    try:
        is_admin: bool = bool(windll.shell32.IsUserAnAdmin()) if windll is not None else False
    except AttributeError:
        # Fallback: some stripped Windows environments may not expose this API.
        is_admin = False
        logger.debug("ctypes.windll.shell32.IsUserAnAdmin not available; assuming non-admin")

    if is_admin:
        result.messages.append("Running with Windows Administrator privileges")
        logger.debug("Process is elevated (Administrator)")
    else:
        result.ok = False
        result.errors.append("Not running with Administrator privileges – some operations may fail")
        logger.warning("Process is NOT elevated (not Administrator)")


def run_preflight_checks() -> PreflightResult:
    """Run all pre-flight checks and return a consolidated status report.

    If the host OS is not Windows, the result will have ``ok=False`` and an
    error message explaining this; callers should check ``result.ok`` and bail
    out gracefully rather than relying on a hard process exit.

    Checks performed:

    1. **Platform** – ensures the host OS is Windows.
    2. **robocopy.exe availability** – uses :func:`shutil.which` to confirm the
       binary is accessible on ``PATH``.
    3. **Windows Administrator privileges** – uses :mod:`ctypes` to call
       ``IsUserAnAdmin``.

    Returns:
        A :class:`PreflightResult` whose :attr:`~PreflightResult.ok` attribute
        is ``True`` only when every check passed.
    """
    logger.debug("Starting pre-flight checks")
    result = PreflightResult()
    _check_platform(result)
    if not result.ok:
        return result

    _check_robocopy_available(result)
    _check_admin_privileges(result)

    if result.ok:
        logger.info("All pre-flight checks passed")
    else:
        logger.warning("One or more pre-flight checks failed:\n%s", result.status_report())

    return result
