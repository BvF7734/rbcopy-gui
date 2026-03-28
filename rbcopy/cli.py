"""Console script for rbcopy."""

import asyncio
import locale
import logging
from pathlib import Path
from datetime import datetime
from logging import getLogger
from rbcopy.notifications import notify_job_complete

import typer

from rbcopy.logger import rotate_logs, setup_logging
from rbcopy.system_check import run_preflight_checks

app = typer.Typer(no_args_is_help=False)

# Use the fully-qualified package name rather than __name__ so that the
# logger is always a child of the 'rbcopy' namespace (and therefore
# inherits its FileHandler) even when cli.py is executed directly as
# __main__ (e.g. via 'python cli.py').
logger = getLogger("rbcopy.cli")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """rbcopy – Robocopy GUI wrapper.

    Run without arguments to launch the graphical interface.
    Use the ``sync`` subcommand to copy files directly from the command line.
    """
    if ctx.invoked_subcommand is None:
        from rbcopy.gui import launch

        launch()


async def _run_robocopy(cmd: list[str]) -> int:
    """Stream robocopy output asynchronously and return the exit code.

    Using asyncio.create_subprocess_exec keeps the event loop free during
    I/O waits, preventing the process from blocking the calling coroutine.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert proc.stdout is not None
    async for line_bytes in proc.stdout:
        line = line_bytes.decode(locale.getpreferredencoding(False), errors="replace")
        stripped = line.rstrip("\n")
        typer.echo(stripped)
        logger.debug("%s", stripped)
    await proc.wait()
    assert proc.returncode is not None
    return proc.returncode


@app.command("sync")
def sync_cmd(
    source: str = typer.Option(..., "--source", "-s", help="Source directory path."),
    dest: str = typer.Option(..., "--dest", "-d", help="Destination directory path."),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview the command without copying (adds /L flag)."),
    skip_checks: bool = typer.Option(False, "--skip-checks", help="Skip pre-flight environment checks."),
) -> None:
    """Sync source to destination using robocopy."""
    from rbcopy.builder import build_command, exit_code_label

    from rbcopy.app_dirs import get_log_dir

    log = setup_logging(log_dir=get_log_dir())

    file_handlers = [h for h in log.handlers if isinstance(h, logging.FileHandler)]

    # Prune old log files now that the current session file exists.
    # Failures are non-fatal: a rotation error must never abort a copy job.
    if file_handlers:
        try:
            from rbcopy.preferences import PreferencesStore

            rotate_logs(
                Path(file_handlers[0].baseFilename).parent,
                keep=PreferencesStore().preferences.log_retention_count,
            )
        except Exception:
            logger.debug("Log rotation failed; continuing", exc_info=True)

    # Show the user exactly which log file is being written.
    if file_handlers:
        typer.echo(f"Session log: {file_handlers[0].baseFilename}")

    if not skip_checks:
        preflight = run_preflight_checks()
        if not preflight.ok:
            typer.echo(preflight.status_report(), err=True)
            raise typer.Exit(code=1)

    flag_selections: dict[str, bool] = {"/L": True} if dry_run else {}
    cmd = build_command(source, dest, flag_selections, {})

    logger.info("Robocopy command: %s", " ".join(cmd))
    typer.echo("Command: " + " ".join(cmd))

    if dry_run:
        typer.echo("(Dry run – no files will be copied)")
        raise typer.Exit(code=0)

    if "/NJH" in cmd:
        logger.info("Job started: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    exit_code = asyncio.run(_run_robocopy(cmd))

    if exit_code == 0:
        logger.info("robocopy completed successfully (exit code 0)")
    else:
        logger.info("robocopy finished with exit code %d", exit_code)

    notify_job_complete(
        title="RBCopy – Job Complete",
        message=exit_code_label(exit_code),
    )

    if "/NJS" in cmd:
        logger.info("Job ended: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    raise typer.Exit(code=exit_code)


if __name__ == "__main__":
    app()
