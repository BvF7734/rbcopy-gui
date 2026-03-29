# rbcopy

A Windows GUI wrapper for [Robocopy](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/robocopy) — the built-in Windows file-copy tool. rbcopy lets you build, preview, and run Robocopy commands from a graphical interface, and also exposes a `sync` CLI subcommand for scripted use.

## Features

- **Graphical interface** — toggle Robocopy flags and parameters via checkboxes and entry fields; view the generated command in real time
- **Simple / Advanced view** — beginners see a curated set of the most-used flags; advanced mode reveals the full flag list
- **Presets** — save and load named configurations (bundled starter presets included)
- **Bookmarks** — save frequently used source/destination paths for quick access
- **Path history** — source and destination dropdowns remember recently used paths across sessions
- **Drag-and-drop** — drag folders from Windows Explorer onto the source/destination fields
- **Script export** — export the current command as a standalone `.bat` or `.ps1` file
- **Job history** — browse and re-open previous session log files
- **Live output** — streaming Robocopy output displayed in the GUI as the job runs
- **Desktop notifications** — native Windows toast notification when a job completes
- **CLI mode** — `rbcopy sync --source <src> --dest <dst>` for scripting and automation
- **Dry-run** — preview what would be copied without moving any files (`--dry-run` / `/L`)

## Requirements

- **Windows** — Robocopy is a Windows built-in; the GUI and toast notifications are Windows-only
- **robocopy.exe** must be on `PATH` (present on all modern Windows installations by default)
- Administrator privileges are recommended for jobs that copy file security or ownership

## Installation

### Option 1 – Download the pre-built executable

Download `rbcopy.exe` from the [latest GitHub release](../../releases/latest) and run it directly — no Python installation required.

### Option 2 – Install with pip / uv

```powershell
pip install rbcopy
# or
uv tool install rbcopy
```

## Usage

### GUI mode

Launch the graphical interface with no arguments:

```powershell
rbcopy
# or
python -m rbcopy
```

### CLI mode

```powershell
# Mirror C:\Users to D:\Backup
rbcopy sync --source C:\Users --dest D:\Backup

# Short-form aliases (-s / -d)
rbcopy sync -s C:\Users -d D:\Backup

# Preview without copying (adds /L)
rbcopy sync -s C:\Users -d D:\Backup --dry-run

# Skip pre-flight checks (robocopy on PATH + admin check)
rbcopy sync -s C:\Users -d D:\Backup --skip-checks
```

## Developer Documentation

Comprehensive developer documentation is available in [`docs/dev/`](./docs/dev/) covering testing, configuration, deployment, and all project features.

### Quick Start for Developers

```bash
# Install development environment
make install

# Run tests
make tests

# Auto-fix formatting
make chores

# Build a versioned Windows executable
make build VERSION=v1.0.0
```

See the [developer documentation](./docs/dev/README.md) for complete guides and reference.