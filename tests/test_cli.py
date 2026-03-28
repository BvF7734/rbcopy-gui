"""Tests for the rbcopy CLI module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from rbcopy.cli import app
from rbcopy.system_check import PreflightResult
from tests.helpers import make_mock_async_proc

runner = CliRunner()

# ---------------------------------------------------------------------------
# Shared patches
# ---------------------------------------------------------------------------

# All sync-subcommand tests patch setup_logging and run_preflight_checks so
# that log files are not created during tests and the robocopy PATH check does
# not fail on Linux / CI environments.
_PATCH_LOGGING = patch("rbcopy.cli.setup_logging")
_PATCH_PREFLIGHT = patch(
    "rbcopy.cli.run_preflight_checks",
    return_value=PreflightResult(ok=True, messages=["mocked"], errors=[]),
)
# Patch notify_job_complete so tests never attempt to spawn a real PowerShell
# process.  Without this patch, on Windows the function calls subprocess.Popen
# with powershell.exe, which is not controlled by the test and can cause
# unexpected side-effects inside Typer's runner.invoke.
_PATCH_NOTIFY = patch("rbcopy.cli.notify_job_complete")


# ---------------------------------------------------------------------------
# Basic invocation
# ---------------------------------------------------------------------------


def test_cli_no_args_does_not_crash_import():
    """The app object is importable and is a Typer instance."""
    import typer

    assert isinstance(app, typer.Typer)


# ---------------------------------------------------------------------------
# sync subcommand – dry-run mode
# ---------------------------------------------------------------------------


def test_dry_run_prints_command_and_exits_zero():
    with _PATCH_LOGGING, _PATCH_PREFLIGHT, _PATCH_NOTIFY:
        result = runner.invoke(app, ["sync", "--source", "C:/src", "--dest", "C:/dst", "--dry-run"])
    assert result.exit_code == 0
    assert "robocopy" in result.output
    assert "/L" in result.output
    assert "Dry run" in result.output


def test_dry_run_short_flags():
    with _PATCH_LOGGING, _PATCH_PREFLIGHT, _PATCH_NOTIFY:
        result = runner.invoke(app, ["sync", "-s", "C:/src", "-d", "C:/dst", "-n"])
    assert result.exit_code == 0
    assert "/L" in result.output


def test_dry_run_includes_src_and_dst():
    with _PATCH_LOGGING, _PATCH_PREFLIGHT, _PATCH_NOTIFY:
        result = runner.invoke(app, ["sync", "--source", "C:/source", "--dest", "C:/destination", "--dry-run"])
    assert "C:/source" in result.output
    assert "C:/destination" in result.output


# ---------------------------------------------------------------------------
# sync subcommand – normal mode
# ---------------------------------------------------------------------------


def test_sync_runs_subprocess():
    """When --source and --dest are supplied, asyncio.create_subprocess_exec is called."""
    mock_proc = make_mock_async_proc(returncode=0)
    with _PATCH_LOGGING, _PATCH_PREFLIGHT, _PATCH_NOTIFY:
        with patch("rbcopy.cli.asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)) as mock_create:
            result = runner.invoke(app, ["sync", "--source", "C:/src", "--dest", "C:/dst"])
    assert result.exit_code == 0
    mock_create.assert_called_once()
    call_args = mock_create.call_args[0]
    assert call_args[0] == "robocopy"
    assert "C:/src" in call_args
    assert "C:/dst" in call_args
    # /L must NOT be present in a normal (non-dry-run) run
    assert "/L" not in call_args


def test_sync_propagates_exit_code():
    """Exit code from robocopy is forwarded to the caller."""
    mock_proc = make_mock_async_proc(returncode=1)
    with _PATCH_LOGGING, _PATCH_PREFLIGHT, _PATCH_NOTIFY:
        with patch("rbcopy.cli.asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
            result = runner.invoke(app, ["sync", "--source", "C:/src", "--dest", "C:/dst"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# sync subcommand – robocopy output logging
# ---------------------------------------------------------------------------


_PATCH_ROTATE = patch("rbcopy.cli.rotate_logs")


def test_sync_echoes_session_log_path(log_dir: Path):
    mock_proc = make_mock_async_proc(returncode=0)
    with _PATCH_PREFLIGHT, _PATCH_ROTATE, _PATCH_NOTIFY:
        with patch("rbcopy.cli.asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
            result = runner.invoke(app, ["sync", "--source", "C:/src", "--dest", "C:/dst"])
    assert "Session log:" in result.output
    log_file = next(log_dir.glob("robocopy_job_*.log"))
    assert str(log_file) in result.output


def test_sync_writes_robocopy_output_to_log_file(log_dir: Path):
    sample_output = "   Source : C:\\src\\\n   Dest : C:\\dst\\\n"
    mock_proc = make_mock_async_proc(returncode=0, output=sample_output)
    with _PATCH_PREFLIGHT, _PATCH_ROTATE, _PATCH_NOTIFY:
        with patch("rbcopy.cli.asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
            runner.invoke(app, ["sync", "--source", "C:/src", "--dest", "C:/dst"])

    log_file = next(log_dir.glob("robocopy_job_*.log"))
    content = log_file.read_text(encoding="utf-8")
    assert "Source : C:\\src\\" in content
    assert "Dest : C:\\dst\\" in content


def test_sync_logs_start_timestamp_when_njh_active(log_dir: Path):
    mock_proc = make_mock_async_proc(returncode=0)
    with _PATCH_PREFLIGHT, _PATCH_ROTATE, _PATCH_NOTIFY:
        with patch("rbcopy.cli.asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
            with patch("rbcopy.builder.build_command", return_value=["robocopy", "C:/src", "C:/dst", "/NJH"]):
                runner.invoke(app, ["sync", "--source", "C:/src", "--dest", "C:/dst"])

    log_file = next(log_dir.glob("robocopy_job_*.log"))
    content = log_file.read_text(encoding="utf-8")
    assert "Job started:" in content


def test_sync_logs_end_timestamp_when_njs_active(log_dir: Path):
    mock_proc = make_mock_async_proc(returncode=0)
    with _PATCH_PREFLIGHT, _PATCH_ROTATE, _PATCH_NOTIFY:
        with patch("rbcopy.cli.asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
            with patch("rbcopy.builder.build_command", return_value=["robocopy", "C:/src", "C:/dst", "/NJS"]):
                runner.invoke(app, ["sync", "--source", "C:/src", "--dest", "C:/dst"])

    log_file = next(log_dir.glob("robocopy_job_*.log"))
    content = log_file.read_text(encoding="utf-8")
    assert "Job ended:" in content


# ---------------------------------------------------------------------------
# sync subcommand – preflight check integration
# ---------------------------------------------------------------------------


def test_sync_aborts_when_preflight_fails():
    """When pre-flight checks fail, the sync command should exit with code 1."""
    failed_result = PreflightResult(ok=False, errors=["robocopy not found"])
    with _PATCH_LOGGING, _PATCH_NOTIFY:
        with patch("rbcopy.cli.run_preflight_checks", return_value=failed_result):
            with patch("rbcopy.cli.asyncio.create_subprocess_exec", new=AsyncMock()) as mock_create:
                result = runner.invoke(app, ["sync", "--source", "C:/src", "--dest", "C:/dst"])
    assert result.exit_code == 1
    mock_create.assert_not_called()


def test_sync_skip_checks_bypasses_preflight():
    """--skip-checks must suppress the preflight check call."""
    mock_proc = make_mock_async_proc(returncode=0)
    with _PATCH_LOGGING, _PATCH_NOTIFY:
        with patch("rbcopy.cli.run_preflight_checks") as mock_preflight:
            with patch("rbcopy.cli.asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
                result = runner.invoke(
                    app,
                    ["sync", "--source", "C:/src", "--dest", "C:/dst", "--skip-checks"],
                )
    mock_preflight.assert_not_called()
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# sync subcommand – error cases
# ---------------------------------------------------------------------------


def test_missing_dest_shows_error():
    result = runner.invoke(app, ["sync", "--source", "C:/src"])
    assert result.exit_code != 0


def test_missing_source_shows_error():
    result = runner.invoke(app, ["sync", "--dest", "C:/dst"])
    assert result.exit_code != 0


def test_missing_source_and_dest_shows_error():
    result = runner.invoke(app, ["sync"])
    assert result.exit_code != 0
