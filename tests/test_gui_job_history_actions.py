"""Tests for _JobHistoryWindow action methods (rbcopy.gui.job_history)."""

from __future__ import annotations

from typing import Any
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import StringVarStub as _StringVarStub

import contextlib
import rbcopy.gui.job_history as job_history_module
from rbcopy.gui.job_history import _JobHistoryWindow

# ---------------------------------------------------------------------------
# Job history – _JobHistoryWindow._open_externally tests
# ---------------------------------------------------------------------------


def test_job_history_window_open_externally_no_selection_is_noop(tmp_path: Path) -> None:
    """_open_externally does nothing when no row is selected."""

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ()

    win: Any = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {}

    # Should return early without raising.
    win._open_externally()


def test_job_history_window_open_externally_calls_platform_command(tmp_path: Path) -> None:
    """_open_externally invokes the OS-appropriate command to open the file."""

    log = tmp_path / "robocopy_job_20240101_120000.log"
    log.touch()

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item1",)

    win: Any = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {"item1": log}

    # Patch whichever opener the current platform would use.
    if hasattr(job_history_module.os, "startfile"):
        with patch.object(job_history_module.os, "startfile") as mock_open:
            win._open_externally()
        mock_open.assert_called_once_with(str(log))
    else:
        with patch.object(job_history_module.subprocess, "Popen") as mock_popen:
            win._open_externally()
        mock_popen.assert_called_once()


def test_job_history_window_open_externally_uses_startfile_on_windows(tmp_path: Path) -> None:
    """_open_externally calls os.startfile when it is available (Windows path)."""

    log = tmp_path / "robocopy_job_20240101_120000.log"
    log.touch()

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item1",)

    win: Any = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {"item1": log}

    mock_startfile = MagicMock()
    # create=True adds startfile even on non-Windows where it doesn't exist.
    with patch.object(job_history_module.os, "startfile", mock_startfile, create=True):
        win._open_externally()

    mock_startfile.assert_called_once_with(str(log))


def test_job_history_window_open_externally_uses_open_on_macos(tmp_path: Path) -> None:
    """_open_externally calls 'open' via subprocess when sys.platform is 'darwin' and os.startfile is unavailable."""

    if hasattr(job_history_module.os, "startfile"):
        # On Windows os.startfile always takes precedence; this branch cannot be reached
        # without deleting the built-in attribute.  Skip instead of breaking the os module.
        pytest.skip("macOS branch not reachable on platforms where os.startfile exists")

    log = tmp_path / "robocopy_job_20240101_120000.log"
    log.touch()

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item1",)

    win: Any = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {"item1": log}

    # On non-Windows platforms os.startfile is absent, so patching sys.platform to
    # "darwin" causes the elif-darwin branch to be taken.
    with (
        patch.object(job_history_module.subprocess, "Popen") as mock_popen,
        patch.object(job_history_module, "sys") as mock_sys,
    ):
        mock_sys.platform = "darwin"
        win._open_externally()

    mock_popen.assert_called_once_with(["open", str(log)], shell=False)


# ---------------------------------------------------------------------------
# Job history – _JobHistoryWindow._export_log tests
# ---------------------------------------------------------------------------


def test_job_history_window_export_log_no_selection_is_noop() -> None:
    """_export_log does nothing when no row is selected."""

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ()

    win: Any = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {}

    # Should return early without raising or opening a dialog.
    with patch("rbcopy.gui.job_history.filedialog.asksaveasfilename") as mock_dialog:
        win._export_log()
    mock_dialog.assert_not_called()


def test_job_history_window_export_log_cancelled_dialog_is_noop(tmp_path: Path) -> None:
    """_export_log does nothing when the save-file dialog is cancelled."""

    log = tmp_path / "robocopy_job_20240101_120000.log"
    log.write_text("content\n", encoding="utf-8")

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item1",)

    win: Any = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {"item1": log}

    with patch("rbcopy.gui.job_history.filedialog.asksaveasfilename", return_value=""):
        with patch("rbcopy.gui.job_history.shutil.copy2") as mock_copy:
            win._export_log()

    mock_copy.assert_not_called()
    # Source file must remain untouched.
    assert log.read_text(encoding="utf-8") == "content\n"


def test_job_history_window_export_log_copies_file(tmp_path: Path) -> None:
    """_export_log copies the selected log to the chosen destination."""

    src = tmp_path / "robocopy_job_20240101_120000.log"
    src.write_text("log content here\n", encoding="utf-8")
    dest = tmp_path / "exported.log"

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item1",)

    win: Any = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {"item1": src}

    with patch("rbcopy.gui.job_history.filedialog.asksaveasfilename", return_value=str(dest)):
        with patch("rbcopy.gui.job_history.messagebox.showinfo") as mock_info:
            win._export_log()

    assert dest.read_text(encoding="utf-8") == "log content here\n"
    mock_info.assert_called_once()


def test_job_history_window_export_log_shows_error_on_failure(tmp_path: Path) -> None:
    """_export_log shows an error dialog when the copy fails."""

    src = tmp_path / "robocopy_job_20240101_120000.log"
    src.write_text("log content\n", encoding="utf-8")
    dest = tmp_path / "exported.log"

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item1",)

    win: Any = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {"item1": src}

    with patch("rbcopy.gui.job_history.filedialog.asksaveasfilename", return_value=str(dest)):
        with patch("rbcopy.gui.job_history.shutil.copy2", side_effect=OSError("disk full")):
            with patch("rbcopy.gui.job_history.messagebox.showerror") as mock_err:
                win._export_log()

    mock_err.assert_called_once()
    assert "disk full" in mock_err.call_args.args[1]


# ---------------------------------------------------------------------------
# Job history – _JobHistoryWindow._on_select edge-case tests
# ---------------------------------------------------------------------------


def test_job_history_window_on_select_no_selection_is_noop() -> None:
    """_on_select does nothing when no row is selected."""

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ()

    win: Any = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {}
    win._content = MagicMock()

    win._on_select(MagicMock())

    win._content.insert.assert_not_called()


def test_job_history_window_on_select_path_not_in_map_is_noop() -> None:
    """_on_select does nothing when the selected item has no corresponding log path."""

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item_with_no_path",)

    win: Any = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._tree = mock_tree
    win._log_file_map = {}  # empty – no mapping for the selected item
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1

    win._on_select(MagicMock())

    win._content.insert.assert_not_called()


def test_job_history_window_on_select_shows_error_on_read_failure(tmp_path: Path) -> None:
    """_on_select shows an error message in the content pane when the log file cannot be read."""

    nonexistent = tmp_path / "missing.log"

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item1",)

    win: Any = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._tree = mock_tree
    win._log_file_map = {"item1": nonexistent}
    win._content = MagicMock()
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1

    win._on_select(MagicMock())

    calls = win._content.insert.call_args_list
    inserted = "".join(str(c.args[-1]) for c in calls)
    assert "Error reading file" in inserted


# ---------------------------------------------------------------------------
# Job history – _JobHistoryWindow._open_externally edge-case tests
# ---------------------------------------------------------------------------


def test_job_history_window_open_externally_path_not_in_map_is_noop() -> None:
    """_open_externally does nothing when the selected item has no corresponding log path."""

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item_not_in_map",)

    win: Any = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {}

    with patch("rbcopy.gui.job_history.subprocess.Popen") as mock_popen:
        win._open_externally()

    mock_popen.assert_not_called()


def test_job_history_window_open_externally_shows_error_on_oserror(tmp_path: Path) -> None:
    """_open_externally shows an error dialog when the system open command fails."""

    log = tmp_path / "robocopy_job_20240101_120000.log"
    log.touch()

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item1",)

    win: Any = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {"item1": log}

    # Patch whichever opener the current platform would use so the OSError path is exercised.
    # On Windows os.startfile is used; on other platforms subprocess.Popen is used.
    with contextlib.ExitStack() as stack:
        if hasattr(job_history_module.os, "startfile"):
            stack.enter_context(patch.object(job_history_module.os, "startfile", side_effect=OSError("no editor")))
        else:
            stack.enter_context(patch.object(job_history_module.subprocess, "Popen", side_effect=OSError("no editor")))
        mock_err = stack.enter_context(patch("rbcopy.gui.job_history.messagebox.showerror"))
        win._open_externally()

    mock_err.assert_called_once()
    assert "no editor" in mock_err.call_args.args[1]


# ---------------------------------------------------------------------------
# Job history – _JobHistoryWindow._export_log edge-case tests
# ---------------------------------------------------------------------------


def test_job_history_window_export_log_path_not_in_map_is_noop() -> None:
    """_export_log does nothing when the selected item has no corresponding log path."""

    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item_not_in_map",)

    win: Any = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {}

    with patch("rbcopy.gui.job_history.filedialog.asksaveasfilename") as mock_dialog:
        win._export_log()

    mock_dialog.assert_not_called()


# ---------------------------------------------------------------------------
# Job history – _open_externally non-Windows branches (lines 529-532)
# ---------------------------------------------------------------------------


def _make_mock_win_for_open(log_path: Path) -> Any:
    """Return a minimal _JobHistoryWindow stub whose selection points at *log_path*."""
    mock_tree = MagicMock()
    mock_tree.selection.return_value = ("item1",)

    win: Any = _JobHistoryWindow.__new__(_JobHistoryWindow)
    win._all_entries = []
    win._resolved = {}
    win._filter_var = _StringVarStub()
    win._date_from_var = _StringVarStub()
    win._date_to_var = _StringVarStub()
    win._filter_count_var = _StringVarStub()
    win._search_var = _StringVarStub()
    win._search_count_var = _StringVarStub()
    win._search_matches = []
    win._search_current = -1
    win._tree = mock_tree
    win._log_file_map = {"item1": log_path}
    return win


def test_job_history_window_open_externally_calls_open_on_darwin(tmp_path: Path) -> None:
    """_open_externally calls 'open' via subprocess.Popen on macOS (sys.platform == 'darwin').

    The test replaces the module-level ``os`` object with a spec that excludes
    ``startfile`` so that ``hasattr(os, 'startfile')`` evaluates to ``False``,
    forcing execution of the elif-darwin branch (line 529-530).
    """
    import os as _real_os

    log = tmp_path / "robocopy_job_20240101_120000.log"
    log.touch()
    win = _make_mock_win_for_open(log)

    # Build a mock os namespace without 'startfile' so lines 529-530 execute.
    spec_attrs = [x for x in dir(_real_os) if x != "startfile"]
    mock_os = MagicMock(spec=spec_attrs)

    with (
        patch.object(job_history_module, "os", mock_os),
        patch.object(job_history_module, "sys") as mock_sys,
        patch.object(job_history_module.subprocess, "Popen") as mock_popen,
    ):
        mock_sys.platform = "darwin"
        win._open_externally()

    mock_popen.assert_called_once_with(["open", str(log)], shell=False)


def test_job_history_window_open_externally_calls_xdg_open_on_linux(tmp_path: Path) -> None:
    """_open_externally calls 'xdg-open' via subprocess.Popen on Linux (else branch, line 531-532).

    The test replaces the module-level ``os`` object with a spec that excludes
    ``startfile`` and sets ``sys.platform`` to "linux" to reach the else branch.
    """
    import os as _real_os

    log = tmp_path / "robocopy_job_20240101_120000.log"
    log.touch()
    win = _make_mock_win_for_open(log)

    spec_attrs = [x for x in dir(_real_os) if x != "startfile"]
    mock_os = MagicMock(spec=spec_attrs)

    with (
        patch.object(job_history_module, "os", mock_os),
        patch.object(job_history_module, "sys") as mock_sys,
        patch.object(job_history_module.subprocess, "Popen") as mock_popen,
    ):
        mock_sys.platform = "linux"
        win._open_externally()

    mock_popen.assert_called_once_with(["xdg-open", str(log)], shell=False)
