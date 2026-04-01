"""Parse the Robocopy job summary from an RBCopy session log file.

Robocopy writes a structured summary block at the end of its output
(unless suppressed by ``/NJS``).  Because every robocopy output line is
already written to the session log by ``_async_execute`` via
``logger.debug``, this module reads that summary back from the log file
rather than buffering the entire job output in memory.

Public API
----------
:func:`parse_summary_from_log`
    Read the tail of a log file and return a :class:`RobocopySummary`, or
    ``None`` when no summary section is present (e.g. ``/NJS`` was active,
    the job is still running, or the log is unreadable).

:meth:`RobocopySummary.format_card`
    Return a multi-line string formatted for display in the output panel.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from logging import getLogger
from pathlib import Path

logger = getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# How many bytes to read from the end of the log file when searching for the
# summary.  Robocopy's summary block is a few hundred bytes; 32 KB gives
# generous headroom even when the job-header lines are verbose.
_TAIL_BYTES: int = 32 * 1024

# Robocopy emits a line of 78 dashes to delimit sections of its output.
# The summary block starts immediately after the *last* such line in the job.
_DASH_RE = re.compile(r"^-{20,}\s*$")

# The session log format is:
#   YYYY-MM-DD HH:MM:SS [LEVEL   ] logger.name: <message>
# This pattern strips that prefix so we can work with the raw robocopy text.
_LOG_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[[\w\s]+\] \S+: ?")

# Summary row patterns (applied to lines *after* the prefix is stripped).
# Column order: Total  Copied  Skipped  Mismatch  FAILED  Extras
#
# Unlike Linux tools, robocopy.exe completely ignores Python's LANG environment
# variable.  Its output language is hard-tied to the Windows system display
# language, so on a non-English workstation the summary labels differ from
# the en-US defaults.  Each pattern therefore lists known label variants for
# the major Windows UI locales:
#   en-US  Dirs       / Files     / Bytes  / Times    / Speed   / Ended
#   fr-FR  Répertoires/ Fichiers  / Octets / Durées   / Vitesse / Terminé
#   de-DE  Verzeichnisse / Dateien/ Bytes  / Zeiten   / Geschw. / Ende
#   es-ES  Directorios/ Archivos  / Bytes  / Tiempos  / Veloc.  / Finalizado
#   it-IT  Cartelle   / File      / Byte   / Durate   / Veloc.  / Fine
#   pt-BR  Pastas     / Arquivos  / Bytes  / Intervalos/ Veloc. / Término
#
# Fields whose value is None (pattern did not match) are simply omitted from
# the summary card, so unrecognised locales degrade gracefully.

_DIRS_RE = re.compile(
    r"(?:Dirs|Répertoires|Verzeichnisse|Directorios|Cartelle|Pastas)\s*:\s+"
    r"(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
    re.IGNORECASE,
)
_FILES_RE = re.compile(
    r"(?:Files|Fichiers|Dateien|Archivos|File|Arquivos|Ficheiros|Bestanden)\s*:\s+"
    r"(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
    re.IGNORECASE,
)
# Bytes values may be plain integers or suffixed (e.g. "1.47 k", "3.2 m").
# French uses "Octets", Italian uses "Byte" (no trailing s).
_BYTES_RE = re.compile(
    r"(?:Bytes|Octets|Byte)\s*:\s+"
    r"(\d[\d.,]*(?:\s*[kKmMgGtT])?)\s+(\d[\d.,]*(?:\s*[kKmMgGtT])?)",
    re.IGNORECASE,
)
_TIMES_RE = re.compile(
    r"(?:Times|Durées|Zeiten|Tiempos|Durate|Intervalos)\s*:\s+([\d:.]+)",
    re.IGNORECASE,
)
# Speed: two lines — bytes/sec (integer) then MB/min (decimal).
# Unit variants for bytes/sec: Bytes/sec (en), Octets/s (fr), Bytes/Sek (de), Bytes/s (es/it/pt).
# Unit variants for MB/min:    MegaBytes/min (en), Mégaoctets/min (fr), MB/Min (de), MB/min (es/it/pt).
# Explicit unit alternation prevents the two speed lines from matching each other.
_SPEED_BYTES_RE = re.compile(
    r"(?:Speed|Vitesse|Geschw\.|Veloc\.)\s*:\s+([\d,]+)"
    r"\s+(?:Bytes/sec|Octets/s|Bytes/Sek|Bytes/s|B/s)\.?",
    re.IGNORECASE,
)
_SPEED_MB_RE = re.compile(
    r"(?:Speed|Vitesse|Geschw\.|Veloc\.)\s*:\s+([\d.,]+)"
    r"\s+(?:MegaBytes/min|M[eé]gaoctets/min|MB/[Mm]in|MBit/[Mm]in)\.?",
    re.IGNORECASE,
)
_ENDED_RE = re.compile(
    r"(?:Ended|Terminé|Ende|Finalizado|Fine|Término)\s*:\s+(.+)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class RobocopySummary:
    """Parsed values from a Robocopy job summary block.

    All fields are ``None`` when the corresponding row was absent from the
    summary (e.g. because ``/NJS`` suppressed it, or the pattern did not
    match a locale variant of the output).
    """

    dirs_total: int | None = None
    dirs_copied: int | None = None
    dirs_skipped: int | None = None
    dirs_failed: int | None = None

    files_total: int | None = None
    files_copied: int | None = None
    files_skipped: int | None = None
    files_failed: int | None = None

    # Raw strings such as "768", "1.47 k", "3.2 m" — kept as strings
    # because robocopy uses locale-specific suffixes and rounding that
    # would be lost if converted to integers.
    bytes_total: str | None = None
    bytes_copied: str | None = None

    duration: str | None = None  # e.g. "0:00:01"
    speed_bytes_sec: str | None = None  # e.g. "7,680,000"
    speed_mb_min: str | None = None  # e.g. "439.453"
    ended: str | None = None

    # ------------------------------------------------------------------

    def format_card(self) -> str:
        """Return a multi-line summary card for display in the output panel.

        Uses plain ASCII / Unicode line-drawing characters that render well
        in any monospace font.  Fields that are ``None`` are omitted so the
        card degrades gracefully when robocopy suppresses parts of its output.
        """
        bar = "  " + "─" * 54
        # Empty string sentinels at both ends guarantee that
        # "\n".join(lines) always starts and ends with "\n",
        # regardless of platform or Python build.
        lines: list[str] = ["", bar, "  Job summary", bar]

        def _row(label: str, text: str) -> None:
            lines.append(f"  {label:<10} {text}")

        # Files row
        if self.files_copied is not None:
            failed_label = "FAILED" if (self.files_failed or 0) > 0 else "failed"
            _row(
                "Files",
                f"{self.files_copied} copied   "
                f"{self.files_skipped or 0} skipped   "
                f"{self.files_failed or 0} {failed_label}",
            )

        # Dirs row
        if self.dirs_copied is not None:
            failed_label = "FAILED" if (self.dirs_failed or 0) > 0 else "failed"
            _row(
                "Dirs",
                f"{self.dirs_copied} copied   "
                f"{self.dirs_skipped or 0} skipped   "
                f"{self.dirs_failed or 0} {failed_label}",
            )

        # Bytes row
        if self.bytes_copied is not None and self.bytes_total is not None:
            _row("Bytes", f"{self.bytes_copied} copied of {self.bytes_total} total")
        elif self.bytes_copied is not None:
            _row("Bytes", f"{self.bytes_copied} copied")

        # Speed row — combine both speed values when both are present
        if self.speed_bytes_sec is not None:
            speed_text = f"{self.speed_bytes_sec} Bytes/sec"
            if self.speed_mb_min is not None:
                speed_text += f"  ({self.speed_mb_min} MB/min)"
            _row("Speed", speed_text)

        # Duration
        if self.duration is not None:
            _row("Duration", self.duration)

        lines.append(bar)
        lines.append("")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_tail(log_path: Path) -> list[str]:
    """Return the last ``_TAIL_BYTES`` bytes of *log_path* as a list of lines.

    Returns an empty list when the file cannot be read.
    """
    try:
        size = log_path.stat().st_size
        with log_path.open("rb") as fh:
            if size > _TAIL_BYTES:
                fh.seek(-_TAIL_BYTES, 2)
            content = fh.read()
        return content.decode("utf-8", errors="replace").splitlines()
    except OSError:
        logger.debug("Could not read log tail from %s", log_path, exc_info=True)
        return []


def _strip_prefix(line: str) -> str:
    """Remove the session-log timestamp/level/name prefix from *line*."""
    return _LOG_PREFIX_RE.sub("", line)


def _find_last_dash_index(raw_lines: list[str]) -> int | None:
    """Return the index of the last dash-separator line, or ``None``."""
    last: int | None = None
    for i, line in enumerate(raw_lines):
        if _DASH_RE.match(line):
            last = i
    return last


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_summary_from_log(log_path: Path) -> RobocopySummary | None:
    """Parse the most recent Robocopy summary block from *log_path*.

    Reads only the last :data:`_TAIL_BYTES` bytes of the file so that
    performance is independent of total log size.

    When a single session log contains multiple job runs (which can happen
    when the CLI ``sync`` command is invoked more than once in the same
    process), the *last* summary block is returned — matching the job that
    just completed.

    Args:
        log_path: Path to the session log file produced by
            :func:`rbcopy.logger.setup_logging`.

    Returns:
        A :class:`RobocopySummary` when a parseable summary block is found,
        or ``None`` when the summary was absent or the file could not be read.
    """
    lines = _read_tail(log_path)
    if not lines:
        return None

    raw_lines = [_strip_prefix(line) for line in lines]

    last_dash = _find_last_dash_index(raw_lines)
    if last_dash is None:
        logger.debug("No summary separator found in log tail: %s", log_path)
        return None

    summary = RobocopySummary()
    found_any = False

    for line in raw_lines[last_dash + 1 :]:
        m = _DIRS_RE.search(line)
        if m:
            summary.dirs_total = int(m.group(1))
            summary.dirs_copied = int(m.group(2))
            summary.dirs_skipped = int(m.group(3))
            summary.dirs_failed = int(m.group(5))
            found_any = True
            continue

        m = _FILES_RE.search(line)
        if m:
            summary.files_total = int(m.group(1))
            summary.files_copied = int(m.group(2))
            summary.files_skipped = int(m.group(3))
            summary.files_failed = int(m.group(5))
            found_any = True
            continue

        m = _BYTES_RE.search(line)
        if m:
            summary.bytes_total = m.group(1).strip()
            summary.bytes_copied = m.group(2).strip()
            found_any = True
            continue

        m = _TIMES_RE.search(line)
        if m:
            summary.duration = m.group(1).strip()
            found_any = True
            continue

        m = _SPEED_BYTES_RE.search(line)
        if m:
            summary.speed_bytes_sec = m.group(1).strip()
            continue

        m = _SPEED_MB_RE.search(line)
        if m:
            summary.speed_mb_min = m.group(1).strip()
            continue

        m = _ENDED_RE.search(line)
        if m:
            summary.ended = m.group(1).strip()
            continue

    if not found_any:
        logger.debug("Dash separator found but no summary rows matched in %s", log_path)
        return None

    logger.debug(
        "Parsed summary from %s: files=%s/%s dirs=%s/%s",
        log_path,
        summary.files_copied,
        summary.files_total,
        summary.dirs_copied,
        summary.dirs_total,
    )
    return summary
