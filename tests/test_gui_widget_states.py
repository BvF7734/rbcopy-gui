"""Tests for RobocopyGUI widget-state and confirmation methods (rbcopy.gui.main_window)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from rbcopy.gui import RobocopyGUI
from tests.helpers import make_fake_self as _make_fake_self, make_mock_async_proc

# ===========================================================================
# Regression-test gaps: added in batch
# ===========================================================================

# ---------------------------------------------------------------------------
# Gap 1: _confirm_destructive_operation – standalone function
# ---------------------------------------------------------------------------


def test_confirm_destructive_op_returns_true_for_empty_dst() -> None:
    """Returns True immediately when the destination string is empty."""
    from rbcopy.gui.main_window import _confirm_destructive_operation

    result = _confirm_destructive_operation("", {"/MIR": True})

    assert result is True


def test_confirm_destructive_op_returns_true_for_whitespace_dst() -> None:
    """Returns True when the destination is whitespace only (treated as empty)."""
    from rbcopy.gui.main_window import _confirm_destructive_operation

    result = _confirm_destructive_operation("   ", {"/MIR": True})

    assert result is True


def test_confirm_destructive_op_returns_true_when_dst_does_not_exist(tmp_path: Path) -> None:
    """Returns True when the destination path does not exist on disk."""
    from rbcopy.gui.main_window import _confirm_destructive_operation

    missing = tmp_path / "nonexistent_dir"

    result = _confirm_destructive_operation(str(missing), {"/MIR": True})

    assert result is True


def test_confirm_destructive_op_returns_true_when_dst_is_empty_dir(tmp_path: Path) -> None:
    """Returns True when the destination exists but is completely empty."""
    from rbcopy.gui.main_window import _confirm_destructive_operation

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    result = _confirm_destructive_operation(str(empty_dir), {"/MIR": True})

    assert result is True


def test_confirm_destructive_op_returns_true_when_no_destructive_flag(tmp_path: Path) -> None:
    """Returns True when destination has content but no destructive flag is active."""
    from rbcopy.gui.main_window import _confirm_destructive_operation

    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "existing.txt").write_text("data", encoding="utf-8")

    result = _confirm_destructive_operation(str(dst), {"/E": True, "/MIR": False})

    assert result is True


def test_confirm_destructive_op_shows_dialog_and_returns_false_on_no(tmp_path: Path) -> None:
    """Shows a warning dialog and returns False when user declines /MIR on non-empty dst."""
    from rbcopy.gui.main_window import _confirm_destructive_operation

    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "existing.txt").write_text("data", encoding="utf-8")

    with patch("rbcopy.gui.main_window.messagebox.askyesno", return_value=False) as mock_ask:
        result = _confirm_destructive_operation(str(dst), {"/MIR": True})

    mock_ask.assert_called_once()
    assert result is False


def test_confirm_destructive_op_shows_dialog_and_returns_true_on_yes(tmp_path: Path) -> None:
    """Returns True when user confirms the destructive operation."""
    from rbcopy.gui.main_window import _confirm_destructive_operation

    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "existing.txt").write_text("data", encoding="utf-8")

    with patch("rbcopy.gui.main_window.messagebox.askyesno", return_value=True):
        result = _confirm_destructive_operation(str(dst), {"/MIR": True})

    assert result is True


def test_confirm_destructive_op_purge_flag_triggers_dialog(tmp_path: Path) -> None:
    """Shows the warning dialog when /PURGE is active and destination has content."""
    from rbcopy.gui.main_window import _confirm_destructive_operation

    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "existing.txt").write_text("data", encoding="utf-8")

    with patch("rbcopy.gui.main_window.messagebox.askyesno", return_value=False) as mock_ask:
        result = _confirm_destructive_operation(str(dst), {"/PURGE": True})

    mock_ask.assert_called_once()
    assert result is False


def test_confirm_destructive_op_uses_no_as_default(tmp_path: Path) -> None:
    """The askyesno call uses messagebox.NO as the default (safety pre-selected)."""
    from tkinter import messagebox as tkinter_messagebox

    from rbcopy.gui.main_window import _confirm_destructive_operation

    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "existing.txt").write_text("data", encoding="utf-8")

    with patch("rbcopy.gui.main_window.messagebox.askyesno", return_value=False) as mock_ask:
        _confirm_destructive_operation(str(dst), {"/MIR": True})

    call_kwargs = mock_ask.call_args.kwargs
    assert call_kwargs.get("default") == tkinter_messagebox.NO


def test_confirm_destructive_op_passes_parent_to_dialog(tmp_path: Path) -> None:
    """The parent kwarg is forwarded to messagebox.askyesno when provided."""
    from rbcopy.gui.main_window import _confirm_destructive_operation

    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "existing.txt").write_text("data", encoding="utf-8")
    mock_parent = MagicMock()

    with patch("rbcopy.gui.main_window.messagebox.askyesno", return_value=True) as mock_ask:
        _confirm_destructive_operation(str(dst), {"/MIR": True}, parent=mock_parent)

    call_kwargs = mock_ask.call_args.kwargs
    assert call_kwargs.get("parent") is mock_parent


# ---------------------------------------------------------------------------
# Gap 2: _get_selections and _build_command (real implementations)
# ---------------------------------------------------------------------------


def test_get_selections_returns_flag_dict() -> None:
    """_get_selections mirrors the current BooleanVar values into a dict."""
    fake = _make_fake_self()
    mir_var = MagicMock()
    mir_var.get.return_value = True
    e_var = MagicMock()
    e_var.get.return_value = False
    fake._flag_vars = {"/MIR": mir_var, "/E": e_var}
    fake._param_vars = {}

    flag_sel, param_sel = RobocopyGUI._get_selections(fake)

    assert flag_sel == {"/MIR": True, "/E": False}
    assert param_sel == {}


def test_get_selections_returns_param_tuples() -> None:
    """_get_selections returns (enabled, value) tuples for all param vars."""
    fake = _make_fake_self()
    fake._flag_vars = {}
    r_enabled = MagicMock()
    r_enabled.get.return_value = True
    r_value = MagicMock()
    r_value.get.return_value = "3"
    w_enabled = MagicMock()
    w_enabled.get.return_value = False
    w_value = MagicMock()
    w_value.get.return_value = "30"
    fake._param_vars = {
        "/R": (r_enabled, r_value, MagicMock()),
        "/W": (w_enabled, w_value, MagicMock()),
    }

    flag_sel, param_sel = RobocopyGUI._get_selections(fake)

    assert flag_sel == {}
    assert param_sel == {"/R": (True, "3"), "/W": (False, "30")}


def test_build_command_calls_through_to_build_command() -> None:
    """_build_command assembles the robocopy command from src/dst/flags/params."""
    from rbcopy.builder import build_command as real_build_command

    fake = _make_fake_self()
    fake.src_var.get.return_value = "C:/src"
    fake.dst_var.get.return_value = "C:/dst"
    fake._get_selections.return_value = ({"/MIR": True}, {})
    fake._file_filter_enabled_var.get.return_value = False
    fake._file_filter_var.get.return_value = ""

    with patch("rbcopy.gui.main_window.build_command", wraps=real_build_command) as mock_bc:
        cmd = RobocopyGUI._build_command(fake)

    mock_bc.assert_called_once_with("C:/src", "C:/dst", {"/MIR": True}, {}, file_filter="")
    assert cmd == ["robocopy", "C:/src", "C:/dst", "/MIR"]


def test_build_command_passes_empty_file_filter_when_disabled() -> None:
    """_build_command passes file_filter='' when the filter checkbox is unchecked."""
    fake = _make_fake_self()
    fake.src_var.get.return_value = "C:/src"
    fake.dst_var.get.return_value = "C:/dst"
    fake._get_selections.return_value = ({}, {})
    fake._file_filter_enabled_var.get.return_value = False
    fake._file_filter_var.get.return_value = "*.img"  # value present but checkbox off

    with patch("rbcopy.gui.main_window.build_command") as mock_bc:
        mock_bc.return_value = ["robocopy", "C:/src", "C:/dst"]
        RobocopyGUI._build_command(fake)

    call_kwargs = mock_bc.call_args.kwargs
    assert call_kwargs.get("file_filter") == ""


def test_build_command_passes_file_filter_when_enabled() -> None:
    """_build_command passes the filter value when the filter checkbox is checked."""
    fake = _make_fake_self()
    fake.src_var.get.return_value = "C:/src"
    fake.dst_var.get.return_value = "C:/dst"
    fake._get_selections.return_value = ({}, {})
    fake._file_filter_enabled_var.get.return_value = True
    fake._file_filter_var.get.return_value = "*.img *.raw"

    with patch("rbcopy.gui.main_window.build_command") as mock_bc:
        mock_bc.return_value = ["robocopy", "C:/src", "C:/dst"]
        RobocopyGUI._build_command(fake)

    call_kwargs = mock_bc.call_args.kwargs
    assert call_kwargs.get("file_filter") == "*.img *.raw"


# ---------------------------------------------------------------------------
# Gap 7: _on_properties_only_toggle (unit level without live GUI)
# ---------------------------------------------------------------------------


def _make_fake_self_for_props_only() -> MagicMock:
    """Return a fake self with full flag/param setup for properties-only tests."""
    from rbcopy.builder import PROPERTIES_ONLY_FLAGS, PROPERTIES_ONLY_PARAMS

    fake = _make_fake_self()
    fake._is_applying_preset = False
    fake._saved_dst = ""
    fake._saved_flags = {}
    fake._saved_params = {}

    # Use real dicts so iteration and item assignment work correctly.
    fake._flag_vars = {}
    fake._param_vars = {}

    for flag in PROPERTIES_ONLY_FLAGS:
        var = MagicMock()
        var.get.return_value = False
        fake._flag_vars[flag] = var

    for flag in PROPERTIES_ONLY_PARAMS:
        ev = MagicMock()
        ev.get.return_value = False
        vv = MagicMock()
        vv.get.return_value = ""
        fake._param_vars[flag] = (ev, vv, MagicMock())

    fake.dst_var.get.return_value = "C:/original"
    return fake


def test_on_properties_only_toggle_activation_saves_dst() -> None:
    """Activating Properties Only saves the current dst_var value."""
    fake = _make_fake_self_for_props_only()
    fake._props_only_var.get.return_value = True

    RobocopyGUI._on_properties_only_toggle(fake)

    assert fake._saved_dst == "C:/original"


def test_on_properties_only_toggle_activation_overrides_dst() -> None:
    """Activating Properties Only sets dst_var to PROPERTIES_ONLY_DST."""
    from rbcopy.builder import PROPERTIES_ONLY_DST

    fake = _make_fake_self_for_props_only()
    fake._props_only_var.get.return_value = True

    RobocopyGUI._on_properties_only_toggle(fake)

    fake.dst_var.set.assert_called_with(PROPERTIES_ONLY_DST)


def test_on_properties_only_toggle_activation_sets_forced_flags() -> None:
    """Activating Properties Only sets every PROPERTIES_ONLY_FLAGS var to True."""
    from rbcopy.builder import PROPERTIES_ONLY_FLAGS

    fake = _make_fake_self_for_props_only()
    fake._props_only_var.get.return_value = True

    RobocopyGUI._on_properties_only_toggle(fake)

    for flag in PROPERTIES_ONLY_FLAGS:
        if flag in fake._flag_vars:
            fake._flag_vars[flag].set.assert_called_with(True)


def test_on_properties_only_toggle_activation_sets_forced_params() -> None:
    """Activating Properties Only sets every PROPERTIES_ONLY_PARAMS value to forced value."""
    from rbcopy.builder import PROPERTIES_ONLY_PARAMS

    fake = _make_fake_self_for_props_only()
    fake._props_only_var.get.return_value = True

    RobocopyGUI._on_properties_only_toggle(fake)

    for flag, forced_value in PROPERTIES_ONLY_PARAMS.items():
        if flag in fake._param_vars:
            _ev, vv, _ = fake._param_vars[flag]
            vv.set.assert_called_with(forced_value)


def test_on_properties_only_toggle_activation_calls_refresh() -> None:
    """Activating Properties Only calls _refresh_widget_states afterwards."""
    fake = _make_fake_self_for_props_only()
    fake._props_only_var.get.return_value = True

    RobocopyGUI._on_properties_only_toggle(fake)

    fake._refresh_widget_states.assert_called_once()


def test_on_properties_only_toggle_deactivation_restores_dst() -> None:
    """Deactivating Properties Only restores the previously-saved dst."""
    fake = _make_fake_self_for_props_only()
    fake._props_only_var.get.return_value = False
    fake._saved_dst = "C:/original"
    fake._saved_flags = {}
    fake._saved_params = {}

    RobocopyGUI._on_properties_only_toggle(fake)

    fake.dst_var.set.assert_called_with("C:/original")


def test_on_properties_only_toggle_deactivation_restores_saved_flags() -> None:
    """Deactivating Properties Only restores previously-saved flag values."""
    from rbcopy.builder import PROPERTIES_ONLY_FLAGS

    fake = _make_fake_self_for_props_only()
    forced_flag = next(iter(PROPERTIES_ONLY_FLAGS))
    fake._props_only_var.get.return_value = False
    fake._saved_dst = ""
    fake._saved_flags = {forced_flag: False}
    fake._saved_params = {}

    RobocopyGUI._on_properties_only_toggle(fake)

    fake._flag_vars[forced_flag].set.assert_called_with(False)


def test_on_properties_only_toggle_deactivation_with_no_saved_state() -> None:
    """Deactivating Properties Only is safe even when saved state is empty."""
    fake = _make_fake_self_for_props_only()
    fake._props_only_var.get.return_value = False
    fake._saved_dst = ""
    fake._saved_flags = {}
    fake._saved_params = {}

    # Must not raise.
    RobocopyGUI._on_properties_only_toggle(fake)


# ---------------------------------------------------------------------------
# Gap 8: _refresh_widget_states (unit level without live GUI)
# ---------------------------------------------------------------------------


def _make_fake_self_for_refresh() -> MagicMock:
    """Return a fake self wired for _refresh_widget_states tests."""
    fake = _make_fake_self()
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = False
    # Provide real dicts so iteration works correctly.
    fake._flag_vars = {}
    fake._flag_cbs = {}
    fake._param_vars = {}
    fake._param_cbs = {}
    for flag in ["/MIR", "/E", "/PURGE", "/ZB", "/Z", "/B", "/MOVE", "/MOV", "/L"]:
        var = MagicMock()
        var.get.return_value = False
        fake._flag_vars[flag] = var
        fake._flag_cbs[flag] = MagicMock()
    return fake


def test_refresh_widget_states_disables_e_when_mir_active() -> None:
    """With /MIR active, the /E checkbutton is configured as disabled."""
    fake = _make_fake_self_for_refresh()
    fake._flag_vars["/MIR"].get.return_value = True

    RobocopyGUI._refresh_widget_states(fake)

    fake._flag_cbs["/E"].config.assert_any_call(state="disabled")


def test_refresh_widget_states_disables_purge_when_mir_active() -> None:
    """With /MIR active, the /PURGE checkbutton is configured as disabled."""
    fake = _make_fake_self_for_refresh()
    fake._flag_vars["/MIR"].get.return_value = True

    RobocopyGUI._refresh_widget_states(fake)

    fake._flag_cbs["/PURGE"].config.assert_any_call(state="disabled")


def test_refresh_widget_states_reenables_when_mir_inactive() -> None:
    """With /MIR inactive, the /E and /PURGE checkbuttons are configured as normal."""
    fake = _make_fake_self_for_refresh()
    fake._flag_vars["/MIR"].get.return_value = False

    RobocopyGUI._refresh_widget_states(fake)

    fake._flag_cbs["/E"].config.assert_any_call(state="normal")
    fake._flag_cbs["/PURGE"].config.assert_any_call(state="normal")


def test_refresh_widget_states_disables_z_and_b_when_zb_active() -> None:
    """With /ZB active, the /Z and /B checkbuttons are configured as disabled."""
    fake = _make_fake_self_for_refresh()
    fake._flag_vars["/ZB"].get.return_value = True

    RobocopyGUI._refresh_widget_states(fake)

    fake._flag_cbs["/Z"].config.assert_any_call(state="disabled")
    fake._flag_cbs["/B"].config.assert_any_call(state="disabled")


def test_refresh_widget_states_disables_mov_when_move_active() -> None:
    """With /MOVE active, the /MOV checkbutton is configured as disabled."""
    fake = _make_fake_self_for_refresh()
    fake._flag_vars["/MOVE"].get.return_value = True

    RobocopyGUI._refresh_widget_states(fake)

    fake._flag_cbs["/MOV"].config.assert_any_call(state="disabled")


def test_refresh_widget_states_early_return_when_applying_preset() -> None:
    """_refresh_widget_states does nothing when _is_applying_preset is True."""
    fake = _make_fake_self_for_refresh()
    fake._is_applying_preset = True
    fake._flag_vars["/MIR"].get.return_value = True  # would normally trigger disable

    RobocopyGUI._refresh_widget_states(fake)

    fake._flag_cbs["/E"].config.assert_not_called()


def test_refresh_widget_states_disables_forced_flags_when_props_only() -> None:
    """Properties Only forced flags are configured as disabled."""
    from rbcopy.builder import PROPERTIES_ONLY_FLAGS

    fake = _make_fake_self_for_refresh()
    fake._props_only_var.get.return_value = True
    for flag in PROPERTIES_ONLY_FLAGS:
        if flag not in fake._flag_vars:
            var = MagicMock()
            var.get.return_value = False
            fake._flag_vars[flag] = var
            fake._flag_cbs[flag] = MagicMock()

    RobocopyGUI._refresh_widget_states(fake)

    for flag in PROPERTIES_ONLY_FLAGS:
        if flag in fake._flag_cbs:
            fake._flag_cbs[flag].config.assert_any_call(state="disabled")


# ---------------------------------------------------------------------------
# Gap 9: _on_file_filter_toggle
# ---------------------------------------------------------------------------


def test_on_file_filter_toggle_enables_entry_when_checked() -> None:
    """_on_file_filter_toggle enables the file filter entry when the var is True."""
    fake = _make_fake_self()
    fake._file_filter_enabled_var.get.return_value = True

    RobocopyGUI._on_file_filter_toggle(fake)

    fake._file_filter_entry.config.assert_called_once_with(state="normal")


def test_on_file_filter_toggle_disables_entry_when_unchecked() -> None:
    """_on_file_filter_toggle disables the file filter entry when the var is False."""
    fake = _make_fake_self()
    fake._file_filter_enabled_var.get.return_value = False

    RobocopyGUI._on_file_filter_toggle(fake)

    fake._file_filter_entry.config.assert_called_once_with(state="disabled")


# ---------------------------------------------------------------------------
# Gap 12: _flush_log_handlers / _get_current_log_file_path
# ---------------------------------------------------------------------------


def test_flush_log_handlers_flushes_file_handler(tmp_path: Path) -> None:
    """_flush_log_handlers calls flush() on every FileHandler on the rbcopy logger."""
    from rbcopy.gui.main_window import _flush_log_handlers

    log_file = tmp_path / "test.log"
    handler = logging.FileHandler(str(log_file))
    rbcopy_logger = logging.getLogger("rbcopy")
    rbcopy_logger.addHandler(handler)

    try:
        with patch.object(handler, "flush") as mock_flush:
            _flush_log_handlers()
        mock_flush.assert_called_once()
    finally:
        handler.close()
        rbcopy_logger.removeHandler(handler)


def test_flush_log_handlers_ignores_stream_handler() -> None:
    """_flush_log_handlers does not call flush() on StreamHandlers."""
    from rbcopy.gui.main_window import _flush_log_handlers

    stream_handler = logging.StreamHandler()
    rbcopy_logger = logging.getLogger("rbcopy")
    rbcopy_logger.addHandler(stream_handler)

    try:
        with patch.object(stream_handler, "flush") as mock_flush:
            _flush_log_handlers()
        mock_flush.assert_not_called()
    finally:
        rbcopy_logger.removeHandler(stream_handler)


def test_get_current_log_file_path_returns_path_when_file_handler(tmp_path: Path) -> None:
    """_get_current_log_file_path returns the path of the FileHandler's log file."""
    from rbcopy.gui.main_window import _get_current_log_file_path

    rbcopy_logger = logging.getLogger("rbcopy")
    original_file_handlers = [h for h in rbcopy_logger.handlers if isinstance(h, logging.FileHandler)]
    for h in original_file_handlers:
        rbcopy_logger.removeHandler(h)

    log_file = tmp_path / "session.log"
    handler = logging.FileHandler(str(log_file))
    rbcopy_logger.addHandler(handler)

    try:
        result = _get_current_log_file_path()
    finally:
        rbcopy_logger.removeHandler(handler)
        handler.close()
        for h in original_file_handlers:
            rbcopy_logger.addHandler(h)

    assert result == Path(handler.baseFilename)


def test_get_current_log_file_path_returns_none_when_no_file_handler() -> None:
    """_get_current_log_file_path returns None when no FileHandler is attached."""
    from rbcopy.gui.main_window import _get_current_log_file_path

    rbcopy_logger = logging.getLogger("rbcopy")
    original_handlers = list(rbcopy_logger.handlers)
    for h in original_handlers:
        rbcopy_logger.removeHandler(h)

    try:
        result = _get_current_log_file_path()
    finally:
        for h in original_handlers:
            rbcopy_logger.addHandler(h)

    assert result is None


# ---------------------------------------------------------------------------
# Gap 13: _async_execute – notify and summary integration
# ---------------------------------------------------------------------------


def test_async_execute_calls_notify_job_complete() -> None:
    """_async_execute calls notify_job_complete in the finally block after any job."""
    fake_self = _make_fake_self()
    mock_proc = make_mock_async_proc(returncode=1, output="some output\n", pid=42)

    with patch("rbcopy.gui.main_window.asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        with patch("rbcopy.gui.main_window.notify_job_complete") as mock_notify:
            with patch("rbcopy.gui.main_window._flush_log_handlers"):
                with patch("rbcopy.gui.main_window._get_current_log_file_path", return_value=None):
                    asyncio.run(RobocopyGUI._async_execute(fake_self, ["robocopy", "C:/s", "C:/d"]))

    mock_notify.assert_called_once()


def test_async_execute_notify_called_with_exit_code_message() -> None:
    """notify_job_complete is called with a message matching the exit code label."""
    from rbcopy.builder import exit_code_label

    fake_self = _make_fake_self()
    mock_proc = make_mock_async_proc(returncode=0, output="", pid=1)

    with patch("rbcopy.gui.main_window.asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        with patch("rbcopy.gui.main_window.notify_job_complete") as mock_notify:
            with patch("rbcopy.gui.main_window._flush_log_handlers"):
                with patch("rbcopy.gui.main_window._get_current_log_file_path", return_value=None):
                    asyncio.run(RobocopyGUI._async_execute(fake_self, ["robocopy", "C:/s", "C:/d"]))

    call_kwargs = mock_notify.call_args.kwargs
    assert call_kwargs["message"] == exit_code_label(0)


def test_async_execute_notify_called_even_on_file_not_found() -> None:
    """notify_job_complete is called even when robocopy is not found (uses exit code -1)."""
    from rbcopy.builder import exit_code_label

    fake_self = _make_fake_self()

    with patch("rbcopy.gui.main_window.asyncio.create_subprocess_exec", new=AsyncMock(side_effect=FileNotFoundError)):
        with patch("rbcopy.gui.main_window.notify_job_complete") as mock_notify:
            asyncio.run(RobocopyGUI._async_execute(fake_self, ["robocopy", "C:/s", "C:/d"]))

    mock_notify.assert_called_once()
    call_kwargs = mock_notify.call_args.kwargs
    assert call_kwargs["message"] == exit_code_label(-1)


def test_async_execute_appends_summary_card_when_parse_succeeds(tmp_path: Path) -> None:
    """_async_execute appends the formatted summary card to output when available."""
    from rbcopy.robocopy_parser import RobocopySummary

    fake_self = _make_fake_self()
    mock_proc = make_mock_async_proc(returncode=1, output="output\n", pid=9)
    summary = RobocopySummary(files_copied=5, files_skipped=2, files_failed=0)

    with patch("rbcopy.gui.main_window.asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        with patch("rbcopy.gui.main_window.notify_job_complete"):
            with patch("rbcopy.gui.main_window._flush_log_handlers"):
                with patch("rbcopy.gui.main_window._get_current_log_file_path", return_value=tmp_path / "x.log"):
                    with patch("rbcopy.gui.main_window.parse_summary_from_log", return_value=summary):
                        asyncio.run(RobocopyGUI._async_execute(fake_self, ["robocopy", "C:/s", "C:/d"]))

    all_output = " ".join(call.args[0] for call in fake_self._append_output.call_args_list)
    assert "Job summary" in all_output


def test_async_execute_skips_summary_card_when_parse_returns_none(tmp_path: Path) -> None:
    """_async_execute does not append a summary card when parse_summary_from_log returns None."""
    fake_self = _make_fake_self()
    mock_proc = make_mock_async_proc(returncode=1, output="output\n", pid=10)

    with patch("rbcopy.gui.main_window.asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        with patch("rbcopy.gui.main_window.notify_job_complete"):
            with patch("rbcopy.gui.main_window._flush_log_handlers"):
                with patch("rbcopy.gui.main_window._get_current_log_file_path", return_value=tmp_path / "x.log"):
                    with patch("rbcopy.gui.main_window.parse_summary_from_log", return_value=None):
                        asyncio.run(RobocopyGUI._async_execute(fake_self, ["robocopy", "C:/s", "C:/d"]))

    all_output = " ".join(call.args[0] for call in fake_self._append_output.call_args_list)
    assert "Job summary" not in all_output
