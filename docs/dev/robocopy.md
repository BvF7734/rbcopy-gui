# Robocopy Reference

This document covers common usage patterns, available flags, and tips for getting the most out of rbcopy – both through the GUI and the command-line interface.

## Quick Start

### GUI Mode

Launch the graphical interface with no arguments:

```powershell
rbcopy
# or
python -m rbcopy
```

The GUI lets you pick source and destination folders, toggle flags with checkboxes, preview the generated command, and run it with live streaming output.

### CLI Mode

Use the `sync` subcommand to copy files directly from a terminal or script:

```powershell
# Mirror C:\Users to D:\Backup
rbcopy sync --source C:\Users --dest D:\Backup

# Short-form aliases (-s / -d)
rbcopy sync -s C:\Users -d D:\Backup

# Preview the command without copying (adds /L)
rbcopy sync --source C:\Users --dest D:\Backup --dry-run
rbcopy sync -s C:\Users -d D:\Backup -n
```

## Robocopy Exit Codes

Robocopy uses non-zero exit codes for informational outcomes – these are **not** errors:

| Code | Meaning |
|------|---------|
| `0`  | No files were copied. No files were mismatched. No failures. |
| `1`  | One or more files were successfully copied. |
| `2`  | Extra files or directories were detected. No copy failures. |
| `4`  | Some mismatched files or directories were detected. |
| `8`  | Some files or directories could not be copied. |
| `16` | Fatal error – no files were copied. Check source/dest paths. |

Exit codes are additive (e.g., `3` = files copied **and** extras detected). rbcopy forwards the raw Robocopy exit code to the calling shell.

## Common Flag Combinations

### Full Mirror (most common)

Keeps the destination an exact copy of the source – deletes extras, copies empties.

```
/MIR /NP /MT:8
```

Equivalent flags: `/E /PURGE` (both are implied by `/MIR`).

### Large-File Copy

Use unbuffered I/O to avoid polluting the Windows cache with large files:

```
/MIR /J /NP /MT:8
```

### Network Copy with Restartable Mode

Tolerates dropped connections by resuming interrupted files:

```
/MIR /Z /NP /MT:8 /R:3 /W:10
```

### Audit / Properties Only (GUI Preset)

Dry-run that shows what *would* change without touching any files. The GUI "Properties Only" checkbox activates this preset automatically:

```
robocopy C:\source c:\temp\blank /L /MIR /NFL /NDL /MT:48 /R:0 /W:0
```

- `/L` – list only, no actual copy
- `c:\temp\blank` – harmless placeholder destination (must exist)
- `/NFL /NDL` – suppress file/directory listing for clean output
- `/MT:48` – maximum threads to enumerate quickly
- `/R:0 /W:0` – no retries (speed up listing)

### Copy with Logging

```
/MIR /NP /MT:8 /LOG:C:\logs\backup.log /TEE
```

- `/LOG:file` – write output to a log file (overwrite)
- `/LOG+:file` – append to an existing log file
- `/TEE` – also display output in the console

## Flag Reference

### File Copy Behaviour

| Flag | Description |
|------|-------------|
| `/S` | Copy subdirectories, excluding empty ones |
| `/E` | Copy subdirectories including empty ones |
| `/MIR` | Mirror – equivalent to `/E /PURGE` |
| `/MOV` | Move files (delete source files after copy) |
| `/MOVE` | Move files and directories |
| `/PURGE` | Delete destination files/dirs that no longer exist in source |
| `/CREATE` | Create directory tree and zero-length placeholder files |

### Copy Mode

| Flag | Description |
|------|-------------|
| `/Z` | Restartable mode – can resume if interrupted |
| `/B` | Backup mode – bypasses file ACL restrictions |
| `/ZB` | Try restartable; fall back to backup mode on access denied |
| `/J` | Unbuffered I/O – best for large files (avoids cache pollution) |
| `/COMPRESS` | Request SMB network compression during transfer |

### File Selection Filters

| Flag | Description |
|------|-------------|
| `/A` | Copy only files with Archive attribute set |
| `/M` | Copy Archive files and reset the Archive attribute |
| `/XO` | Exclude older files (source is older than destination) |
| `/XN` | Exclude newer files (source is newer than destination) |
| `/XC` | Exclude changed files |
| `/XX` | Exclude extra files (exist in dest but not source) |
| `/XL` | Exclude lonely files (exist in source but not dest) |
| `/IS` | Include same files (overwrite even if unchanged) |
| `/IT` | Include tweaked files (same data, different attributes) |
| `/SL` | Copy symbolic links as links rather than their targets |
| `/XF pattern…` | Exclude files matching pattern(s) (wildcards OK, space-separated) |
| `/XD dir…` | Exclude directories matching name(s) (space-separated) |
| `/MAX:n` | Maximum file size in bytes |
| `/MIN:n` | Minimum file size in bytes |
| `/MAXAGE:n` | Maximum file age in days (or YYYYMMDD date) |
| `/MINAGE:n` | Minimum file age in days (or YYYYMMDD date) |

### What Gets Copied

| Flag | Description |
|------|-------------|
| `/COPY:flags` | File copy flags: **D**ata **A**ttributes **T**imestamps **S**ecurity **O**wner **U**-auditing (default: `DAT`) |
| `/DCOPY:flags` | Directory copy flags: **D**ata **A**ttributes **T**imestamps (default: `DA`) |
| `/SEC` | Copy security (equivalent to `/COPY:DATS`) |
| `/COPYALL` | Copy all file information (`/COPY:DATSOU`) |
| `/NOCOPY` | Copy no file information – useful with `/PURGE` alone |

### Performance

| Flag / Option | Description |
|---------------|-------------|
| `/MT:n` | Multi-threaded copies using `n` threads (default 8, max 128) |
| `/IPG:n` | Inter-packet gap in milliseconds – throttles bandwidth |
| `/R:n` | Retry count on failed copies (default 1,000,000) |
| `/W:n` | Wait time in seconds between retries (default 30) |
| `/MON:n` | Monitor source and re-run when `n` or more changes detected |
| `/MOT:m` | Monitor source and re-run every `m` minutes |
| `/RH:hhmm-hhmm` | Only start new copies during this run-hour window |

### Output Control

| Flag | Description |
|------|-------------|
| `/L` | List only – show what *would* be copied without actually doing it |
| `/NP` | No progress – suppress per-file percentage display |
| `/V` | Verbose – show skipped files |
| `/TS` | Include source timestamps in output |
| `/FP` | Full pathnames in output |
| `/BYTES` | Print file sizes in bytes |
| `/NS` | No size logging |
| `/NC` | No file-class logging |
| `/NFL` | No file-name listing in output |
| `/NDL` | No directory-name listing in output |
| `/NJH` | No job header |
| `/NJS` | No job summary |
| `/TEE` | Write to both the log file and the console |
| `/LOG:file` | Log output to `file` (overwrites) |
| `/LOG+:file` | Append log output to `file` |

## Tips

- **Always test first** – run with `/L` (or `--dry-run`) to preview what will be copied or deleted before committing.
- **Avoid `/PURGE` without `/MIR` awareness** – `/MIR` already includes `/PURGE`; adding both is harmless but redundant.
- **`/MT` thread count** – values between 8–32 are typical. Very high values can saturate disk I/O or network adapters. For a NAS, `/MT:16` is often a good starting point.
- **Restartable vs backup mode** – use `/ZB` when you need both resilience and the ability to bypass access-denied errors (requires elevated privileges for backup semantics).
- **Log files for automation** – combine `/LOG:path` with `/NJH /NJS` to produce a clean file list suitable for auditing or scripting.
