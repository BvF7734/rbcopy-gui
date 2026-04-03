"""Tests for RobocopyGUI._run, _dry_run and action helpers (rbcopy.gui.main_window)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from rbcopy.gui import RobocopyGUI
from tests.helpers import make_fake_self as _make_fake_self

# ---------------------------------------------------------------------------
# RobocopyGUI action tests
# ---------------------------------------------------------------------------


def test_preview_appends_command_output() -> None:
    """_preview builds the command and appends a preview line to output."""
    fake_self = _make_fake_self()
    fake_self._build_command.return_value = ["robocopy", "C:/src", "C:/dst"]

    RobocopyGUI._preview(fake_self)

    fake_self._append_output.assert_called_once()
    output_text: str = fake_self._append_output.call_args.args[0]
    assert "robocopy" in output_text


def test_preview_shows_warning_on_value_error() -> None:
    """_preview shows a warning dialog when src or dst is missing."""
    fake_self = _make_fake_self()
    fake_self._build_command.side_effect = ValueError("Source path is required")

    with patch("rbcopy.gui.main_window.messagebox.showwarning") as mock_warn:
        RobocopyGUI._preview(fake_self)

    mock_warn.assert_called_once()
    fake_self._append_output.assert_not_called()


def test_job_already_running_returns_false_when_no_proc() -> None:
    """_job_already_running returns False and shows no warning when no job is running."""
    fake_self = MagicMock()
    fake_self._current_proc = None

    with patch("rbcopy.gui.main_window.messagebox.showwarning") as mock_warn:
        result = RobocopyGUI._job_already_running(fake_self)

    assert result is False
    mock_warn.assert_not_called()


def test_job_already_running_returns_true_and_warns_when_proc_active() -> None:
    """_job_already_running returns True and shows a warning when a job is running."""
    fake_self = MagicMock()
    fake_self._current_proc = MagicMock()  # simulate running process

    with patch("rbcopy.gui.main_window.messagebox.showwarning") as mock_warn:
        result = RobocopyGUI._job_already_running(fake_self)

    assert result is True
    mock_warn.assert_called_once()
    warning_msg: str = mock_warn.call_args.args[1]
    assert "already running" in warning_msg.lower()


def test_run_starts_background_thread() -> None:
    """_run builds the command, logs it, and launches a daemon thread."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self()
    fake_self._build_command.return_value = ["robocopy", "C:/src", "C:/dst"]

    with patch("rbcopy.gui.main_window.validate_command", return_value=DryRunResult(ok=True)):
        with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            RobocopyGUI._run(fake_self)

    mock_thread_cls.assert_called_once_with(
        target=fake_self._execute,
        args=(["robocopy", "C:/src", "C:/dst"],),
        daemon=True,
    )
    mock_thread.start.assert_called_once()


def test_run_shows_warning_on_value_error() -> None:
    """_run shows a warning dialog and does not start a thread when paths are missing."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self()
    fake_self._build_command.side_effect = ValueError("Destination path is required")

    with patch("rbcopy.gui.main_window.validate_command", return_value=DryRunResult(ok=True)):
        with patch("rbcopy.gui.main_window.messagebox.showwarning") as mock_warn:
            with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
                RobocopyGUI._run(fake_self)

    mock_warn.assert_called_once()
    mock_thread_cls.assert_not_called()


def test_run_blocks_concurrent_execution() -> None:
    """_run shows a warning and does not start a thread when a job is already running."""
    fake_self = _make_fake_self()
    fake_self._job_already_running.return_value = True  # simulate a running process

    with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
        RobocopyGUI._run(fake_self)

    mock_thread_cls.assert_not_called()


def test_run_shows_validation_errors_and_aborts() -> None:
    """_run must show a warning and not start a thread when validation fails."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self()
    fake_self.src_var.get.return_value = "/nonexistent/path"
    fake_self.dst_var.get.return_value = "/some/dst"
    fake_self._get_selections.return_value = ({}, {})

    failed_result = DryRunResult(ok=False, errors=["Source path does not exist"])

    with patch("rbcopy.gui.main_window.validate_command", return_value=failed_result):
        with patch("rbcopy.gui.main_window.messagebox.showwarning") as mock_warn:
            with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread:
                RobocopyGUI._run(fake_self)

    mock_warn.assert_called_once()
    mock_thread.assert_not_called()


def test_run_appends_validation_errors_to_output() -> None:
    """_run must write the validation report to the output panel before aborting."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self()
    fake_self.src_var.get.return_value = "/bad/src"
    fake_self.dst_var.get.return_value = "/some/dst"
    fake_self._get_selections.return_value = ({}, {})

    failed_result = DryRunResult(ok=False, errors=["Source path does not exist"])

    with patch("rbcopy.gui.main_window.validate_command", return_value=failed_result):
        with patch("rbcopy.gui.main_window.messagebox.showwarning"):
            RobocopyGUI._run(fake_self)

    all_output = " ".join(call.args[0] for call in fake_self._append_output.call_args_list)
    assert "Source path does not exist" in all_output


def test_run_proceeds_with_warnings_only() -> None:
    """_run must start a thread when validation produces only warnings, not errors."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self()
    fake_self.src_var.get.return_value = "C:/src"
    fake_self.dst_var.get.return_value = "C:/dst"
    fake_self._get_selections.return_value = ({"/MIR": True, "/E": True}, {})
    fake_self._build_command.return_value = ["robocopy", "C:/src", "C:/dst", "/MIR", "/E"]

    warn_result = DryRunResult(ok=True, warnings=["/MIR is selected; /E is redundant"])

    with patch("rbcopy.gui.main_window.validate_command", return_value=warn_result):
        with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            RobocopyGUI._run(fake_self)

    mock_thread.assert_called_once()


def test_run_appends_warnings_to_output_before_proceeding() -> None:
    """_run must write validation warnings to output even when proceeding."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self()
    fake_self.src_var.get.return_value = "C:/src"
    fake_self.dst_var.get.return_value = "C:/dst"
    fake_self._get_selections.return_value = ({"/MIR": True, "/E": True}, {})
    fake_self._build_command.return_value = ["robocopy", "C:/src", "C:/dst"]

    warn_result = DryRunResult(ok=True, warnings=["/MIR is selected; /E is redundant"])

    with patch("rbcopy.gui.main_window.validate_command", return_value=warn_result):
        with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            RobocopyGUI._run(fake_self)

    all_output = " ".join(call.args[0] for call in fake_self._append_output.call_args_list)
    assert "/MIR is selected" in all_output


# ---------------------------------------------------------------------------
# Simulating a user clicking "Run" – unittest.mock walkthrough
# ---------------------------------------------------------------------------
# This section shows the canonical pattern for testing _run() without a live
# Tk display, without spawning a real robocopy process, and without opening
# any dialog boxes.
#
# The approach uses three layers of mocking:
#
#   1. _make_fake_self() – replaces the RobocopyGUI *instance* (self) with a
#      MagicMock whose relevant attributes are pre-configured.  This sidesteps
#      the need to create a Tk root window at all.
#
#   2. patch("rbcopy.gui.main_window.validate_command") – intercepts the
#      validation step so it returns a known DryRunResult without touching
#      the filesystem.
#
#   3. patch("rbcopy.gui.main_window.threading.Thread") – intercepts thread
#      creation so the test can assert *what* would have been launched without
#      actually blocking on a subprocess.
#
# Each test below focuses on one observable side-effect of a click:
#   • Was a thread started?   (happy path)
#   • Was a warning shown?    (validation failure)
#   • Was a thread blocked?   (concurrent protection)
# ---------------------------------------------------------------------------


def test_run_button_click_happy_path() -> None:
    """Simulates a user clicking ▶ Run with valid paths and no active flags.

    The Click:
        User fills in Source = "C:/source" and Destination = "D:/dest"
        then clicks the Run button, which calls RobocopyGUI._run().

    Expected outcome:
        • validate_command passes (ok=True, no errors).
        • _confirm_destructive_operation returns True (no destructive flags).
        • build_command builds ["robocopy", "C:/source", "D:/dest"].
        • A daemon thread is started targeting _execute with that command.
        • No warning dialog is shown to the user.
    """
    from rbcopy.builder import DryRunResult

    # Step 1 – configure the fake GUI instance with populated form fields.
    fake_self = _make_fake_self()
    fake_self.src_var.get.return_value = "C:/source"
    fake_self.dst_var.get.return_value = "D:/dest"
    fake_self._get_selections.return_value = ({}, {})
    fake_self._build_command.return_value = ["robocopy", "C:/source", "D:/dest"]

    # Step 2 – mock validate_command to return a clean result (no filesystem hit).
    ok_result = DryRunResult(ok=True)

    # Step 3 – mock threading.Thread to capture what would have been launched.
    with patch("rbcopy.gui.main_window.validate_command", return_value=ok_result):
        with patch("rbcopy.gui.main_window._confirm_destructive_operation", return_value=True):
            with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
                mock_thread = MagicMock()
                mock_thread_cls.return_value = mock_thread

                # Step 4 – invoke _run() exactly as the button command would.
                RobocopyGUI._run(fake_self)

    # Step 5 – assert the thread was started with the expected command.
    mock_thread_cls.assert_called_once_with(
        target=fake_self._execute,
        args=(["robocopy", "C:/source", "D:/dest"],),
        daemon=True,
    )
    mock_thread.start.assert_called_once()


def test_run_button_click_with_invalid_source() -> None:
    """Simulates a click after the user left Source blank.

    The Click:
        Source is "" (empty), Destination is "D:/dest".
        validate_command returns ok=False because the source is missing.

    Expected outcome:
        • A warning dialog appears; no background thread is launched.
    """
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self()
    fake_self.src_var.get.return_value = ""
    fake_self.dst_var.get.return_value = "D:/dest"
    fake_self._get_selections.return_value = ({}, {})

    # Simulate the validation step returning a path error.
    failed_result = DryRunResult(ok=False, errors=["Source path is required."])

    with patch("rbcopy.gui.main_window.validate_command", return_value=failed_result):
        with patch("rbcopy.gui.main_window.messagebox.showwarning") as mock_warn:
            with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
                RobocopyGUI._run(fake_self)

    # A warning must have been shown to the user.
    mock_warn.assert_called_once()
    # No subprocess should have been started.
    mock_thread_cls.assert_not_called()


def test_run_button_click_blocked_when_job_already_running() -> None:
    """Simulates a second click while a robocopy job is still in progress.

    The Click:
        User clicks Run while self._current_proc is not None
        (i.e. a previous job is still executing).

    Expected outcome:
        • _job_already_running() returns True.
        • _run() returns immediately; no new thread is created.
    """
    fake_self = _make_fake_self()
    # Simulate an already-running process.
    fake_self._job_already_running.return_value = True

    with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
        RobocopyGUI._run(fake_self)

    mock_thread_cls.assert_not_called()


def test_run_button_click_with_redundant_flags_proceeds_with_warning() -> None:
    """Simulates clicking Run when /MIR and /E are both checked (redundant combination).

    The Click:
        User ticked both /MIR and /E, then clicked Run.

    Expected outcome:
        • validate_command emits a warning about /E being redundant.
        • _run() writes the warning to the output panel.
        • The job still launches because warnings are non-fatal (ok=True).
    """
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self()
    fake_self.src_var.get.return_value = "C:/source"
    fake_self.dst_var.get.return_value = "D:/dest"
    fake_self._get_selections.return_value = ({"/MIR": True, "/E": True}, {})
    fake_self._build_command.return_value = ["robocopy", "C:/source", "D:/dest", "/MIR", "/E"]

    warn_result = DryRunResult(ok=True, warnings=["/MIR is selected; /E is redundant"])

    with patch("rbcopy.gui.main_window.validate_command", return_value=warn_result):
        with patch("rbcopy.gui.main_window._confirm_destructive_operation", return_value=True):
            with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
                mock_thread_cls.return_value = MagicMock()
                RobocopyGUI._run(fake_self)

    # The thread must have been created (job proceeds despite warning).
    mock_thread_cls.assert_called_once()
    # The warning must have been surfaced in the output panel.
    all_output = " ".join(call.args[0] for call in fake_self._append_output.call_args_list)
    assert "/MIR is selected" in all_output


# ---------------------------------------------------------------------------
# RobocopyGUI._dry_run tests
# ---------------------------------------------------------------------------


def _make_fake_self_for_dry_run() -> MagicMock:
    """Return a MagicMock suitable for testing _dry_run, with empty option dicts."""
    fake: MagicMock = _make_fake_self()
    fake.src_var.get.return_value = "C:/src"
    fake.dst_var.get.return_value = "C:/dst"
    fake._get_selections.return_value = ({}, {})
    return fake


def _get_thread_cmd(mock_thread_cls: MagicMock) -> list[str]:
    """Extract the command list passed to threading.Thread from a mock call."""
    return mock_thread_cls.call_args.kwargs["args"][0]  # type: ignore[no-any-return]


def test_dry_run_aborts_and_shows_warning_on_validation_error() -> None:
    """_dry_run shows a warning dialog and does not start a thread when validation fails."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self_for_dry_run()
    failed_result = DryRunResult(ok=False, errors=["Source path does not exist"])

    with patch("rbcopy.gui.main_window.validate_command", return_value=failed_result):
        with patch("rbcopy.gui.main_window.messagebox.showwarning") as mock_warn:
            with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
                RobocopyGUI._dry_run(fake_self)

    mock_warn.assert_called_once()
    mock_thread_cls.assert_not_called()


def test_dry_run_blocks_concurrent_execution() -> None:
    """_dry_run shows a warning and does not start a thread when a job is already running."""
    fake_self = _make_fake_self_for_dry_run()
    fake_self._job_already_running.return_value = True  # simulate a running process

    with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
        RobocopyGUI._dry_run(fake_self)

    mock_thread_cls.assert_not_called()


def test_dry_run_outputs_validation_report_on_error() -> None:
    """_dry_run appends the validation report to the output when errors are found."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self_for_dry_run()
    failed_result = DryRunResult(ok=False, errors=["Source path does not exist"])

    with patch("rbcopy.gui.main_window.validate_command", return_value=failed_result):
        with patch("rbcopy.gui.main_window.messagebox.showwarning"):
            RobocopyGUI._dry_run(fake_self)

    fake_self._append_output.assert_called()
    all_output = " ".join(call.args[0] for call in fake_self._append_output.call_args_list)
    assert "Source path does not exist" in all_output


def test_dry_run_appends_warning_to_output() -> None:
    """_dry_run appends non-fatal warnings to the output but still runs."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self_for_dry_run()
    warn_result = DryRunResult(ok=True, warnings=["/MIR is selected; /E is redundant"])

    with patch("rbcopy.gui.main_window.validate_command", return_value=warn_result):
        with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            RobocopyGUI._dry_run(fake_self)

    # Warning should appear in output
    all_output = " ".join(call.args[0] for call in fake_self._append_output.call_args_list)
    assert "/MIR is selected" in all_output
    # A thread should still be launched because ok=True
    mock_thread.start.assert_called_once()


def test_dry_run_adds_l_flag_if_missing() -> None:
    """_dry_run appends /L to the command when it is not already present."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self_for_dry_run()
    # /MIR is enabled, but /L is not — _dry_run must append it.
    fake_self._get_selections.return_value = ({"/MIR": True}, {})
    ok_result = DryRunResult(ok=True)

    with patch("rbcopy.gui.main_window.validate_command", return_value=ok_result):
        with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            RobocopyGUI._dry_run(fake_self)

    cmd_passed: list[str] = _get_thread_cmd(mock_thread_cls)
    assert "/L" in cmd_passed


def test_dry_run_does_not_duplicate_l_flag() -> None:
    """_dry_run does not add /L when it is already present in the command."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self_for_dry_run()
    # /L is already selected in the GUI — _dry_run must not add a second one.
    fake_self._get_selections.return_value = ({"/L": True}, {})
    ok_result = DryRunResult(ok=True)

    with patch("rbcopy.gui.main_window.validate_command", return_value=ok_result):
        with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            RobocopyGUI._dry_run(fake_self)

    cmd_passed: list[str] = _get_thread_cmd(mock_thread_cls)
    assert cmd_passed.count("/L") == 1


def test_dry_run_starts_background_thread() -> None:
    """_dry_run launches a daemon thread to execute the list-only robocopy command."""
    from rbcopy.builder import DryRunResult

    fake_self = _make_fake_self_for_dry_run()
    ok_result = DryRunResult(ok=True)

    with patch("rbcopy.gui.main_window.validate_command", return_value=ok_result):
        with patch("rbcopy.gui.main_window.threading.Thread") as mock_thread_cls:
            with patch("rbcopy.builder.sys.platform", "linux"):
                mock_thread = MagicMock()
                mock_thread_cls.return_value = mock_thread
                RobocopyGUI._dry_run(fake_self)

    mock_thread_cls.assert_called_once_with(
        target=fake_self._execute,
        args=(["robocopy", "C:/src", "C:/dst", "/L"],),
        daemon=True,
    )
    mock_thread.start.assert_called_once()
