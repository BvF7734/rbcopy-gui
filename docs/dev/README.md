# Developer Documentation

Welcome to the rbcopy developer documentation. This directory contains guides for working with the project's tools, workflows, and Robocopy-specific features.

## Getting Started

New to this project? Start here:

1. **[Makefile](./makefile.md)** - Essential commands for development, testing, and building
2. **[Dependencies](./dependencies.md)** - Managing project dependencies, virtual environments, and package installation
3. **[Settings](./settings.md)** - Environment configuration and settings management

## Core Features

### [Robocopy Reference](./robocopy.md)

Comprehensive guide to Robocopy flags, common copy patterns, exit codes, and performance tips. Covers both GUI usage and the `sync` CLI subcommand.

## Development Practices

### [Testing](./testing.md)

Comprehensive testing guide covering pytest, fixtures, async testing, mocking, and code coverage.

### [Documentation](./documentation.md)

Standards and best practices for writing and maintaining project documentation.

### [GitHub Actions](./github.md)

CI/CD workflows for testing, linting, building, and deployment automation.

## Architecture Overview

rbcopy is structured in five layers:

| Module | Purpose |
|--------|---------|
| `rbcopy/builder.py` | Pure logic – option tables, `build_command()`, and `build_robocopy_command()`. No GUI dependency; fully unit-testable. |
| `rbcopy/system_check.py` | Pre-flight checks – verifies `robocopy.exe` is on PATH and (on Windows) that the process has Administrator privileges. |
| `rbcopy/logger.py` | Unified logging – configures the `rbcopy` logger with a Rich console handler (INFO+) and a timestamped file handler (DEBUG+). |
| `rbcopy/gui/` | Tkinter GUI package. `main_window.py` imports from `builder.py` and drives the visual layer; sub-modules cover drag-and-drop (`dnd.py`), job history, preferences dialog, and script builder. |
| `rbcopy/cli.py` | Typer CLI with a `sync` subcommand (named options) and a no-args callback that launches the GUI. |

### Robocopy command builder

`build_command(src, dst, flag_selections, param_selections)` in `rbcopy/builder.py` is the single source of truth for translating user selections into a `robocopy` argument list. Both the GUI (`RobocopyGUI._build_command`) and the CLI (`sync` subcommand) call this function, so the logic is never duplicated.

A simplified alternative `build_robocopy_command(source, dest, flags)` accepts a single unified dict where boolean values toggle simple flags and string values supply parameter arguments (e.g. `{"/MIR": True, "/R": "3"}`).

### Pre-flight checks

`run_preflight_checks()` in `rbcopy/system_check.py` is called by the CLI `sync` subcommand before executing robocopy. It verifies that `robocopy.exe` is on PATH (via `shutil.which`) and, on Windows, that the process holds Administrator privileges (via `ctypes`). Pass `--skip-checks` to bypass these checks.

### Unified logging

`setup_logging(log_dir)` in `rbcopy/logger.py` configures the `rbcopy` logger to simultaneously:

* Print **INFO** and above to the terminal using `rich.logging.RichHandler` (coloured, formatted output).
* Write **DEBUG** and above to a timestamped file (`robocopy_job_YYYYMMDD_HHMMSS.log`) under *log_dir* for persistent auditing.

The function is idempotent – calling it multiple times in the same process will not attach duplicate handlers.

### Thread safety

The GUI runs Robocopy in a background `daemon` thread. Output is passed back to the main thread via a `queue.Queue` that is drained every 100 ms by a Tkinter `after()` callback, keeping all widget access on the main thread.

## Quick Reference

- **Setup**: Run `make install` to set up your development environment
- **Testing**: Run `make tests` for full test suite, see [testing.md](./testing.md) for details
- **Formatting**: Run `make chores` before committing to fix formatting issues
- **Configuration**: See [settings.md](./settings.md) for environment variables and settings
- **All Make Commands**: See [makefile.md](./makefile.md) for complete reference
- **Robocopy Flags**: See [robocopy.md](./robocopy.md) for flag reference and common patterns

---

*This documentation is maintained by the development team. If you find issues or have suggestions, please contribute improvements!*
