"""Pure command-building logic for Robocopy – no GUI dependencies.

This module contains only the data tables and the :func:`build_command`
function so they can be imported and tested independently of Tkinter.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path as _Path

# ---------------------------------------------------------------------------
# Option definitions
# ---------------------------------------------------------------------------

# Simple flag options (checkbox only, no parameter value)
FLAG_OPTIONS: list[tuple[str, str]] = [
    ("/S", "Copy subdirectories (non-empty)"),
    ("/E", "Copy subdirectories (including empty)"),
    ("/MIR", "Mirror directory tree (/E + /PURGE)"),
    ("/MOV", "Move files (delete source after copy)"),
    ("/MOVE", "Move files and directories"),
    ("/PURGE", "Delete destination extras"),
    ("/A", "Copy only files with Archive attribute set"),
    ("/M", "Copy Archive files and reset Archive attribute"),
    ("/Z", "Copy files in restartable mode"),
    ("/B", "Copy files in backup mode"),
    ("/ZB", "Use restartable mode; if access denied use backup mode"),
    ("/J", "Copy using unbuffered I/O (recommended for large files)"),
    ("/SEC", "Copy files with security (equivalent to /COPY:DATS)"),
    ("/COPYALL", "Copy all file info"),
    ("/NOCOPY", "Copy no file info (useful with /PURGE)"),
    ("/CREATE", "Create directory tree and zero-length files only"),
    ("/FAT", "Create destination files using 8.3 FAT file names only"),
    ("/256", "Turn off very long path (> 256 chars) support"),
    ("/XO", "Exclude older files"),
    ("/XN", "Exclude newer files"),
    ("/XC", "Exclude changed files"),
    ("/XX", "Exclude extra files and directories"),
    ("/XL", "Exclude lonely files and directories"),
    ("/IS", "Include same files"),
    ("/IT", "Include tweaked files"),
    ("/SL", "Copy symbolic links as links instead of as target"),
    ("/COMPRESS", "Request network compression during file transfer"),
    ("/L", "List only – no actual copy"),
    ("/NP", "No progress percentages"),
    ("/V", "Verbose output"),
    ("/TS", "Include source file timestamps"),
    ("/FP", "Include full pathnames in output"),
    ("/BYTES", "Print file sizes in bytes"),
    ("/NS", "No sizes – don't log file sizes"),
    ("/NC", "No class – don't log file classes"),
    ("/NFL", "No file list – no file names logged"),
    ("/NDL", "No directory list – no dir names logged"),
    ("/TEE", "Output to console window and log file"),
    ("/NJH", "No job header"),
    ("/NJS", "No job summary"),
]

# Options that require a parameter value – shown as checkbox + entry
PARAM_OPTIONS: list[tuple[str, str, str]] = [
    # (flag_prefix, label, placeholder/default)
    ("/MT", "Multi-threaded copies  /MT:n", "8"),
    ("/LEV", "Max directory depth  /LEV:n", ""),
    ("/R", "Retry count  /R:n", "5"),
    ("/W", "Wait between retries (sec)  /W:n", "30"),
    ("/MON", "Monitor source; run again on n changes  /MON:n", ""),
    ("/MOT", "Monitor source; run again in m minutes  /MOT:m", ""),
    ("/RH", "Run hours (when new copies may start)  /RH:hhmm-hhmm", ""),
    ("/IPG", "Inter-packet gap (ms) to free bandwidth  /IPG:n", ""),
    ("/COPY", "File copy flags  /COPY:flags", "DAT"),
    ("/DCOPY", "Directory copy flags  /DCOPY:flags", "DA"),
    ("/IA", "Include only files with given attributes  /IA:flags", ""),
    ("/XA", "Exclude files with given attributes  /XA:flags", ""),
    ("/MAX", "Max file size (bytes)  /MAX:n", ""),
    ("/MIN", "Min file size (bytes)  /MIN:n", ""),
    ("/MAXAGE", "Max file age (days/date)  /MAXAGE:n", ""),
    ("/MINAGE", "Min file age (days/date)  /MINAGE:n", ""),
    ("/XF", "Exclude files (space-separated)  /XF pattern…", ""),
    ("/XD", "Exclude directories (space-separated)  /XD dir…", ""),
    ("/LOG", "Log file path  /LOG:file", ""),
    ("/LOG+", "Append to log file  /LOG+:file", ""),
]

# ---------------------------------------------------------------------------
# Tooltip (hover hint) text for each flag and parameter option.
# Keys match the flag prefix used in FLAG_OPTIONS and PARAM_OPTIONS.
# All values are user-friendly plain-English sentences suitable for display
# in the GUI tooltips without requiring any knowledge of robocopy internals.
# ---------------------------------------------------------------------------

FLAG_TOOLTIPS: dict[str, str] = {
    "/S": "Copies all non-empty subfolders so the folder structure is preserved at the destination.",
    "/E": "Copies all subfolders, including empty ones. Use this to replicate the full directory tree.",
    "/MIR": (
        "Makes the destination an exact mirror of the source — including deleting files at the "
        "destination that no longer exist in the source. Use with caution on non-empty destinations."
    ),
    "/MOV": "Moves files by deleting them from the source after a successful copy.",
    "/MOVE": "Moves files and folders — both are deleted from the source after a successful copy.",
    "/PURGE": (
        "Removes files and folders from the destination that no longer exist in the source. "
        "Does not copy any new files on its own — combine with /E or /MIR."
    ),
    "/A": "Only copies files that have the Archive attribute set (typically files created or modified since the last backup).",
    "/M": "Copies files with the Archive attribute set and then clears it — useful for incremental backups.",
    "/Z": "Copies in restartable mode so an interrupted transfer can resume mid-file rather than starting over from scratch.",
    "/B": "Copies in backup mode, bypassing file access restrictions. Requires elevated (administrator) privileges.",
    "/ZB": "Tries restartable mode (/Z) first; falls back to backup mode (/B) automatically if access is denied.",
    "/J": (
        "Skips the Windows disk cache when reading and writing, which prevents very large files from "
        "flooding system memory. Recommended when copying files over a few gigabytes."
    ),
    "/SEC": "Copies NTFS permissions, ownership, and access control lists (ACLs) alongside file data.",
    "/COPYALL": "Copies everything robocopy supports: data, attributes, timestamps, permissions, owner, and audit information.",
    "/NOCOPY": "Copies no file data. Useful in combination with /PURGE when you only want to remove destination extras.",
    "/CREATE": "Creates the folder tree and zero-length placeholder files at the destination without copying actual content.",
    "/FAT": "Forces 8.3 short filenames at the destination. Required for legacy FAT/FAT32 file systems.",
    "/256": "Disables long-path (>256 character) support. Only needed for compatibility with very old systems or tools.",
    "/XO": "Skips source files that are older than the corresponding file at the destination, preserving the newer copy.",
    "/XN": "Skips source files that are newer than the corresponding file at the destination, keeping the destination's version.",
    "/XC": "Skips files that exist at both locations but differ in size or timestamp (changed files).",
    "/XX": "Skips files and folders that exist only at the destination. They are left untouched — not copied or deleted.",
    "/XL": "Skips files and folders that exist only at the source. Only updates items that already exist at the destination.",
    "/IS": "Forces a re-copy of files even when source and destination appear identical in size and timestamp.",
    "/IT": "Copies files that exist at both locations but have different file attributes (e.g. read-only flag changed).",
    "/SL": "Copies symbolic links as links rather than following them and copying the target content.",
    "/COMPRESS": "Asks the network to compress data in transit, which can reduce bandwidth usage on supported connections.",
    "/L": "List only — simulates the copy and shows what would be transferred without actually moving any files. Safe to use.",
    "/NP": "Hides the per-file progress percentage in the output to reduce visual clutter.",
    "/V": "Verbose mode — shows extra detail in the output, including files that were skipped.",
    "/TS": "Adds the source file's last-modified timestamp to each line of the output log.",
    "/FP": "Shows the full path of each file in the output instead of just the filename.",
    "/BYTES": "Shows file sizes in bytes rather than a human-readable abbreviated format (KB, MB, GB).",
    "/NS": "Hides file sizes from the output.",
    "/NC": "Hides file class labels (e.g. 'New File', 'Older') from the output.",
    "/NFL": "Hides individual file names from the output — only directory names and summary totals are shown.",
    "/NDL": "Hides directory names from the output — useful when copying many folders and only file details matter.",
    "/TEE": "Writes output to both the console window and a log file at the same time.",
    "/NJH": "Suppresses the robocopy job header printed at the start of the output.",
    "/NJS": "Suppresses the summary statistics table printed at the end of the output.",
}

PARAM_TOOLTIPS: dict[str, str] = {
    "/MT": (
        "Copies several files at once using multiple threads to finish the job faster. "
        "Default is 8 threads. Higher values help on fast drives; very high values can overwhelm slow storage."
    ),
    "/LEV": "Limits how many folder levels deep robocopy will descend. 1 = only the top-level folder's files; 2 = one level of subfolders, and so on.",
    "/R": (
        "How many times to retry a failed file copy before giving up. "
        "The built-in robocopy default is 1,000,000 — set this lower for faster failure on network errors."
    ),
    "/W": "How many seconds to wait between retry attempts. Default is 30 seconds.",
    "/MON": "Keeps robocopy running in the background and triggers a new copy whenever the source accumulates this many new or changed files.",
    "/MOT": "Keeps robocopy running in the background and triggers a new copy every n minutes.",
    "/RH": (
        "Restricts when robocopy may start new file copies to the given time window. "
        "Format: HHMM-HHMM in 24-hour time, e.g. 0600-1800 to allow copies only during business hours."
    ),
    "/IPG": "Adds a pause (in milliseconds) between network packets to limit bandwidth usage on congested or slow links.",
    "/COPY": (
        "Controls which file properties are copied alongside data. "
        "Letters: D=Data, A=Attributes, T=Timestamps, S=Security (ACL), O=Owner, U=Auditing. "
        "Default is DAT."
    ),
    "/DCOPY": (
        "Controls which directory properties are copied. Letters: D=Data, A=Attributes, T=Timestamps. Default is DA."
    ),
    "/IA": (
        "Copies only files that have at least one of the specified attributes set. "
        "Attribute letters: R=Read-only, H=Hidden, S=System, A=Archive, C=Compressed, E=Encrypted, T=Temporary."
    ),
    "/XA": "Skips files that have any of the specified attributes set. Uses the same attribute letters as /IA.",
    "/MAX": "Skips files larger than this size (in bytes). Useful for excluding very large files from a copy run.",
    "/MIN": "Skips files smaller than this size (in bytes). Useful for excluding tiny or zero-byte files.",
    "/MAXAGE": "Skips files whose last-modified date is older than this many days (or older than a specific date string). Useful for copying only recent files.",
    "/MINAGE": "Skips files whose last-modified date is more recent than this many days (or a specific date string).",
    "/XF": "Excludes specific files by name or wildcard pattern (e.g. *.tmp thumbs.db). Separate multiple patterns with spaces.",
    "/XD": "Excludes specific directories by name or path. Wildcards are supported. Separate multiple entries with spaces.",
    "/LOG": "Writes robocopy output to the specified log file, replacing its contents each run.",
    "/LOG+": "Appends robocopy output to the specified log file rather than overwriting it.",
}

# Flags/params that are enabled by default
_DEFAULT_FLAGS: frozenset[str] = frozenset()
_DEFAULT_PARAMS: frozenset[str] = frozenset()

# Flags that render other flags redundant when selected.
# Key: superseding flag.  Value: flags that become redundant.
SUPERSEDES: dict[str, frozenset[str]] = {
    "/MIR": frozenset({"/E", "/PURGE"}),
    "/MOVE": frozenset({"/MOV"}),
    "/ZB": frozenset({"/Z", "/B"}),
}

# "Properties Only" preset: dry-run mirror that lists what would change.
PROPERTIES_ONLY_DST: str = r"c:\temp\blank"
PROPERTIES_ONLY_FLAGS: frozenset[str] = frozenset({"/L", "/MIR", "/NFL", "/NDL"})
PROPERTIES_ONLY_PARAMS: dict[str, str] = {"/MT": "48", "/R": "0", "/W": "0"}

# Parameterised options where an empty value is intentional (space-separated
# patterns). These are excluded from the empty-value warning in validate_command.
_PARAM_VALUE_OPTIONAL: frozenset[str] = frozenset({"/XF", "/XD"})


# ---------------------------------------------------------------------------
# Exit code label mapping
# ---------------------------------------------------------------------------

# Human-readable messages for every standard Robocopy exit code.
# Codes are additive bit-flags; well-known combinations are given explicit
# messages so the text reads naturally rather than as a list of bit meanings.
_EXIT_CODE_MESSAGES: dict[int, str] = {
    -1: "Unknown error, check the log.",
    0: "Nothing to do, no files needed copying.",
    1: "Files copied successfully.",
    2: "Extra files found at destination, no files copied.",
    3: "Files copied successfully, extra files found at destination.",
    4: "Mismatched files detected, no files copied.",
    5: "Files copied, some mismatched files detected. Check the log.",
    6: "Extra and mismatched files detected at destination. Check the log.",
    7: "Files copied with warnings. Extra and mismatched files detected. Check the log.",
    8: "Copy failures detected. Some files were not copied. Check the log.",
    16: "Fatal error, no files were copied. Check the log.",
}

# Per-bit fallback labels used when an unusual combination is encountered
# that has no explicit entry in _EXIT_CODE_MESSAGES.
_EXIT_CODE_BITS: dict[int, str] = {
    1: "Files copied",
    2: "Extra files found at destination",
    4: "Mismatched files detected",
    8: "Copy failures detected",
    16: "Fatal error",
}


def exit_code_label(code: int) -> str:
    """Return a human-readable description for a Robocopy exit code.

    Well-known exit codes have explicit, user-friendly messages.  Unusual
    bit-flag combinations not covered by the lookup table are described by
    composing the individual bit labels, with a ``Check the log.`` suffix
    appended whenever a failure bit (8 or 16) is set.

    Args:
        code: The integer exit code returned by robocopy, or ``-1`` when the
              process could not be started.

    Returns:
        A plain-English string suitable for display to a non-technical user.
    """
    if code in _EXIT_CODE_MESSAGES:
        return _EXIT_CODE_MESSAGES[code]
    # Fallback: compose from individual bit descriptions for unusual combinations.
    parts = [label for bit, label in sorted(_EXIT_CODE_BITS.items()) if code & bit]
    suffix = " Check the log." if code & (8 | 16) else ""
    return ("; ".join(parts) + "." + suffix) if parts else f"Exit code {code}."


# ---------------------------------------------------------------------------
# Extended-length path helper
# ---------------------------------------------------------------------------


def _apply_extended_path_prefix(path: str) -> str:
    """Prepend the Windows extended-length path prefix (``\\\\?\\``) to absolute paths.

    Windows historically limits paths to 260 characters (MAX_PATH).  The
    ``\\\\?\\`` prefix instructs the Win32 API to bypass this limit, allowing
    paths up to ~32,767 Unicode characters.  It is safe to apply to paths
    shorter than 260 characters — robocopy and the Win32 API honour the prefix
    for both short and long paths.

    The prefix is only applied when all three conditions hold:

    - The process is running on Windows (``sys.platform == "win32"``).
    - The path is absolute: it begins with a drive letter (``C:\\``) or a
      UNC share (``\\\\server\\share``).
    - The prefix has not already been applied.

    UNC paths (``\\\\server\\share\\…``) require the special
    ``\\\\?\\UNC\\`` form per Microsoft's extended-length path rules, rather
    than the plain ``\\\\?\\`` form used for drive-letter paths.

    This function is a no-op on non-Windows platforms and on relative paths,
    so it is always safe to call regardless of the input.
    """
    if sys.platform != "win32":
        return path

    # Normalise forward slashes to backslashes.  The Win32 extended-length
    # prefix is only defined for backslash-separated paths.
    normalised = path.replace("/", "\\")

    # Avoid double-applying the prefix if it is already present.
    if normalised.startswith("\\\\?\\"):
        return normalised

    # Identify Windows absolute paths without relying on pathlib.is_absolute(),
    # which returns different results on Linux vs Windows for the same string.
    # A drive-letter root looks like "C:\" and a UNC root starts with "\\".
    is_drive_absolute = len(normalised) >= 3 and normalised[1:3] == ":\\"
    is_unc = normalised.startswith("\\\\")

    if not (is_drive_absolute or is_unc):
        # Relative path — the prefix is not applicable.
        return path

    if is_unc:
        # UNC paths must use the \\?\UNC\ form: drop the leading "\\" and
        # replace it with "\\?\UNC\".  Example:
        #   \\server\share\data  →  \\?\UNC\server\share\data
        return "\\\\?\\UNC\\" + normalised[2:]

    # Standard drive-letter path.  Example:  C:\data  →  \\?\C:\data
    return "\\\\?\\" + normalised


# ---------------------------------------------------------------------------
# Pure command-building helper
# ---------------------------------------------------------------------------


def build_command(
    src: str,
    dst: str,
    flag_selections: dict[str, bool],
    param_selections: dict[str, tuple[bool, str]],
    *,
    file_filter: str = "",
) -> list[str]:
    """Return a robocopy command list for the given selections.

    Args:
        src: Source directory path.
        dst: Destination directory path.
        flag_selections: Mapping of flag string to enabled boolean.
        param_selections: Mapping of flag string to (enabled, value) tuple.
        file_filter: Space-separated file patterns inserted between the destination
            and the option flags (e.g. ``"*.img *.raw"``).  An empty string means
            no filter — robocopy will copy all files (its default ``*.*`` behaviour).

    Raises:
        ValueError: If *src* or *dst* is empty.
    """
    src = src.strip()
    dst = dst.strip()
    if not src:
        raise ValueError("Source path is required.")
    if not dst:
        raise ValueError("Destination path is required.")

    # Robocopy handles long paths (> 260 characters) natively via its own
    # internal Win32 extended-path support.  The \\?\ prefix is reserved for
    # direct Win32 API calls; passing it on the command line would cause
    # robocopy to mis-parse the paths (producing errors like \\?\d\path
    # instead of D:\path).
    cmd: list[str] = ["robocopy", src, dst]

    # Positional file patterns come immediately after dst and before all flags.
    patterns = file_filter.strip()
    if patterns:
        cmd.extend(patterns.split())

    for flag, enabled in flag_selections.items():
        if enabled:
            cmd.append(flag)

    for flag, (enabled, raw_value) in param_selections.items():
        if enabled:
            value = raw_value.strip()
            if flag in ("/XF", "/XD"):
                if value:
                    cmd.append(flag)
                    cmd.extend(value.split())
            else:
                if value:
                    cmd.append(f"{flag}:{value}")

    return cmd


@dataclass
class DryRunResult:
    """Result of a dry-run validation of the command inputs.

    Attributes:
        ok: ``True`` when no errors were found; ``False`` if any check failed.
        warnings: Non-fatal issues (e.g., redundant flags that will be ignored).
        errors: Fatal issues that would prevent the command from running correctly.
    """

    ok: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def status_report(self) -> str:
        """Return a human-readable summary of all validation results."""
        lines: list[str] = []
        for msg in self.warnings:
            lines.append(f"[WARN]  {msg}")
        for err in self.errors:
            lines.append(f"[ERROR] {err}")
        return "\n".join(lines)


def validate_command(
    src: str,
    dst: str,
    flag_selections: dict[str, bool],
    param_selections: dict[str, tuple[bool, str]],
    *,
    file_filter: str = "",
) -> DryRunResult:
    """Validate command inputs without executing robocopy.

    Performs a surface-level pre-execution check by verifying path existence
    and detecting suboptimal option combinations.

    Checks performed:

    1. **Source path** – must be non-empty and must exist as a directory.
    2. **Destination path** – must be non-empty; must not exist as a plain file
       (robocopy requires a directory target).
    3. **Redundant flags** – warns when a superseding flag (e.g. ``/MIR``) is
       selected alongside flags it makes redundant (e.g. ``/E``, ``/PURGE``).
    4. **Empty param values** – warns when a parameterised option (e.g. ``/R``)
       is enabled but has no value; robocopy will silently omit the flag.

    Args:
        src: Source directory path.
        dst: Destination directory path.
        flag_selections: Mapping of flag string to enabled boolean.
        param_selections: Mapping of flag string to (enabled, value) tuple.

    Returns:
        A :class:`DryRunResult` whose :attr:`~DryRunResult.ok` attribute is
        ``True`` only when no errors were found.
    """
    result = DryRunResult()

    src = src.strip()
    dst = dst.strip()

    # ── Source path checks ────────────────────────────────────────────────
    if not src:
        result.ok = False
        result.errors.append("Source path is required.")
    elif not _Path(src).is_dir():
        result.ok = False
        result.errors.append(f"Source path does not exist or is not a directory: {src!r}")

    # ── Destination path checks ───────────────────────────────────────────
    dst_path = _Path(dst)
    if not dst:
        result.ok = False
        result.errors.append("Destination path is required.")
    elif dst_path.exists() and not dst_path.is_dir():
        result.ok = False
        result.errors.append(f"Destination path exists but is not a directory: {dst!r}")

    # ── Option combination checks ─────────────────────────────────────────
    enabled_flags = {f for f, enabled in flag_selections.items() if enabled}
    for sup_flag, implied_flags in SUPERSEDES.items():
        if sup_flag in enabled_flags:
            redundant = implied_flags & enabled_flags
            if redundant:
                result.warnings.append(
                    f"{sup_flag} is selected; the following flags are redundant: " + ", ".join(sorted(redundant))
                )

    # ── Param value checks ────────────────────────────────────────────────
    # Warn when a parameterised option is enabled but has no value: robocopy
    # will silently omit the flag, which can surprise users who ticked the box.
    # value is guaranteed to be str by the type annotation, so .strip() is safe.
    for flag, (enabled, value) in param_selections.items():
        if enabled and not value.strip() and flag not in _PARAM_VALUE_OPTIONAL:
            result.warnings.append(f"{flag} is enabled but has no value; it will be omitted from the command.")

    return result


def _powershell_quote(token: str) -> str:
    """Return a PowerShell single-quoted literal for *token*.

    Single-quoted strings in PowerShell are completely literal: no variable
    expansion, no escape sequences, and no shell metacharacters are
    interpreted. The only character that needs escaping is a single quote
    itself, which is doubled (``'`` → ``''``).
    """
    return "'" + token.replace("'", "''") + "'"


def build_batch_script(cmd: list[str]) -> str:
    """Return the content of a Windows batch script for the given robocopy command.

    The generated script can be saved as a ``.bat`` or ``.cmd`` file and run
    independently to repeat the configured robocopy job.

    Args:
        cmd: The robocopy command list as returned by :func:`build_command`.

    Returns:
        A Windows batch script string with ``\\r\\n`` line endings.
    """
    # subprocess.list2cmdline() follows the same quoting rules as the Windows
    # C runtime (CommandLineToArgvW): tokens with spaces/tabs are wrapped in
    # double-quotes and embedded double-quotes are backslash-escaped, making
    # it the standard approach for building a Windows command line string.
    cmd_line = subprocess.list2cmdline(cmd)
    lines: list[str] = [
        "@echo off",
        ":: Generated by rbcopy -- Script Builder",
        "::",
        ":: Run this script to execute the configured robocopy job.",
        ":: You may edit the options below before running.",
        "::",
        "",
        cmd_line,
        "set ROBOCOPY_EXIT=%errorlevel%",
        "",
        "pause",
        "exit /b %ROBOCOPY_EXIT%",
    ]
    return "\r\n".join(lines) + "\r\n"


def build_powershell_script(cmd: list[str]) -> str:
    """Return the content of a PowerShell script for the given robocopy command.

    The generated script can be saved as a ``.ps1`` file and run independently
    to repeat the configured robocopy job.

    Args:
        cmd: The robocopy command list as returned by :func:`build_command`.

    Returns:
        A PowerShell script string with ``\\n`` line endings.
    """
    # Use PowerShell single-quoting for each argument: single-quoted strings
    # are completely literal in PowerShell (no variable expansion, no special
    # characters interpreted), making them safe for paths with spaces, &, |,
    # %, $, etc. Internal single quotes are escaped by doubling them.
    cmd_line = "& " + " ".join(_powershell_quote(t) for t in cmd)
    lines: list[str] = [
        "# Generated by rbcopy -- Script Builder",
        "#",
        "# Run this script to execute the configured robocopy job.",
        "# You may edit the options below before running.",
        "#",
        "",
        cmd_line,
        "$exitCode = $LASTEXITCODE",
        "",
        'Read-Host -Prompt "Press Enter to exit"',
        "exit $exitCode",
    ]
    return "\n".join(lines) + "\n"


def build_robocopy_command(source: str, dest: str, flags: dict[str, str | bool]) -> list[str]:
    """Build a robocopy command list from a simplified unified flags mapping.

    This is a higher-level alternative to :func:`build_command` that accepts a
    single dict where boolean values represent simple on/off flag toggles and
    string values represent parameterised options (e.g. ``{"/R": "5"}``).

    Args:
        source: Source directory path.
        dest: Destination directory path.
        flags: Mapping of robocopy flag to either a :class:`bool` toggle or a
            :class:`str` parameter value.  Examples::

                {"/MIR": True, "/NP": True, "/R": "3", "/W": "10"}

    Returns:
        A list of strings ready to pass to :func:`subprocess.run`.

    Raises:
        ValueError: If *source* or *dest* is empty.
    """
    flag_selections: dict[str, bool] = {}
    param_selections: dict[str, tuple[bool, str]] = {}

    for flag, value in flags.items():
        if isinstance(value, bool):
            flag_selections[flag] = value
        else:
            param_selections[flag] = (True, str(value))

    return build_command(source, dest, flag_selections, param_selections)
