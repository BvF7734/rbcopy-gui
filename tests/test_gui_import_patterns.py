"""Tests for RobocopyGUI import-pattern helpers (rbcopy.gui.main_window)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rbcopy.gui import RobocopyGUI
from tests.helpers import make_fake_self as _make_fake_self



def _make_import_vars() -> tuple[MagicMock, MagicMock, MagicMock]:
    """Return (enabled_var, value_var, entry) mocks for import tests."""
    enabled_var = MagicMock()
    enabled_var.get.return_value = False
    value_var = MagicMock()
    value_var.get.return_value = ""
    entry = MagicMock()
    return enabled_var, value_var, entry


def test_import_exclusions_cancels_when_no_file_selected() -> None:
    """Cancelling the file dialog must leave vars untouched."""
    fake = _make_fake_self()
    enabled_var, value_var, entry = _make_import_vars()

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=""):
        RobocopyGUI._import_exclusions_from_file(fake, "/XF", enabled_var, value_var, entry)

    value_var.set.assert_not_called()
    enabled_var.set.assert_not_called()
    entry.config.assert_not_called()


def test_import_exclusions_sets_patterns_into_empty_field(tmp_path: Path) -> None:
    """Patterns from the file are written to value_var when the field is empty."""
    txt = tmp_path / "exclusions.txt"
    txt.write_text("*.tmp\n*.bak\n", encoding="utf-8")

    fake = _make_fake_self()
    enabled_var, value_var, entry = _make_import_vars()

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)):
        RobocopyGUI._import_exclusions_from_file(fake, "/XF", enabled_var, value_var, entry)

    value_var.set.assert_called_once_with("*.tmp *.bak")
    enabled_var.set.assert_called_once_with(True)
    entry.config.assert_called_once_with(state="normal")


def test_import_exclusions_appends_to_existing_value(tmp_path: Path) -> None:
    """New patterns are appended to whatever is already in value_var."""
    txt = tmp_path / "exclusions.txt"
    txt.write_text("*.iso\n", encoding="utf-8")

    fake = _make_fake_self()
    enabled_var, value_var, entry = _make_import_vars()
    value_var.get.return_value = "*.img"

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)):
        RobocopyGUI._import_exclusions_from_file(fake, "/XF", enabled_var, value_var, entry)

    value_var.set.assert_called_once_with("*.img *.iso")


def test_import_exclusions_skips_blank_and_comment_lines(tmp_path: Path) -> None:
    """Blank lines and '#' comment lines must not be imported as patterns."""
    txt = tmp_path / "exclusions.txt"
    txt.write_text("# this is a comment\n\n*.log\n  \n# another comment\n*.tmp\n", encoding="utf-8")

    fake = _make_fake_self()
    enabled_var, value_var, entry = _make_import_vars()

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)):
        RobocopyGUI._import_exclusions_from_file(fake, "/XD", enabled_var, value_var, entry)

    value_var.set.assert_called_once_with("*.log *.tmp")


def test_import_exclusions_shows_info_when_file_has_no_usable_patterns(tmp_path: Path) -> None:
    """An info dialog is shown when every line in the file is blank or a comment."""
    txt = tmp_path / "exclusions.txt"
    txt.write_text("# only comments\n\n# another\n", encoding="utf-8")

    fake = _make_fake_self()
    enabled_var, value_var, entry = _make_import_vars()

    with (
        patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)),
        patch("rbcopy.gui.main_window.messagebox.showinfo") as mock_info,
    ):
        RobocopyGUI._import_exclusions_from_file(fake, "/XF", enabled_var, value_var, entry)

    mock_info.assert_called_once()
    value_var.set.assert_not_called()
    enabled_var.set.assert_not_called()


def test_import_exclusions_shows_error_on_read_failure(tmp_path: Path) -> None:
    """An error dialog is shown when the chosen file cannot be read."""
    fake = _make_fake_self()
    enabled_var, value_var, entry = _make_import_vars()

    with (
        patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(tmp_path / "missing.txt")),
        patch("rbcopy.gui.main_window.messagebox.showerror") as mock_err,
    ):
        RobocopyGUI._import_exclusions_from_file(fake, "/XF", enabled_var, value_var, entry)

    mock_err.assert_called_once()
    value_var.set.assert_not_called()
    enabled_var.set.assert_not_called()


def test_import_exclusions_method_exists() -> None:
    """RobocopyGUI must expose a callable _import_exclusions_from_file method."""
    assert callable(RobocopyGUI._import_exclusions_from_file)


# ---------------------------------------------------------------------------
# _import_file_filter_from_file tests
# ---------------------------------------------------------------------------


def test_import_file_filter_method_exists() -> None:
    """RobocopyGUI must expose a callable _import_file_filter_from_file method."""
    assert callable(RobocopyGUI._import_file_filter_from_file)


def test_import_file_filter_cancels_when_no_file_selected() -> None:
    """Cancelling the file dialog must leave file filter vars untouched."""
    fake = _make_fake_self()

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=""):
        RobocopyGUI._import_file_filter_from_file(fake)

    fake._file_filter_var.set.assert_not_called()
    fake._file_filter_enabled_var.set.assert_not_called()


def test_import_file_filter_sets_patterns_into_empty_field(tmp_path: Path) -> None:
    """Patterns from the file are written to _file_filter_var when field is empty."""
    txt = tmp_path / "includes.txt"
    txt.write_text("*.img\n*.raw\n", encoding="utf-8")

    fake = _make_fake_self()
    fake._file_filter_var.get.return_value = ""
    fake._file_filter_entry = MagicMock()

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)):
        RobocopyGUI._import_file_filter_from_file(fake)

    fake._file_filter_var.set.assert_called_once_with("*.img *.raw")
    fake._file_filter_enabled_var.set.assert_called_once_with(True)
    fake._file_filter_entry.config.assert_called_once_with(state="normal")


def test_import_file_filter_appends_to_existing_value(tmp_path: Path) -> None:
    """New patterns are appended to whatever is already in _file_filter_var."""
    txt = tmp_path / "includes.txt"
    txt.write_text("*.iso\n", encoding="utf-8")

    fake = _make_fake_self()
    fake._file_filter_var.get.return_value = "*.img"
    fake._file_filter_entry = MagicMock()

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)):
        RobocopyGUI._import_file_filter_from_file(fake)

    fake._file_filter_var.set.assert_called_once_with("*.img *.iso")


def test_import_file_filter_skips_blank_and_comment_lines(tmp_path: Path) -> None:
    """Blank lines and '#' comment lines must not be imported as patterns."""
    txt = tmp_path / "includes.txt"
    txt.write_text("# header\n\n*.zip\n  \n# note\n*.tar\n", encoding="utf-8")

    fake = _make_fake_self()
    fake._file_filter_var.get.return_value = ""
    fake._file_filter_entry = MagicMock()

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)):
        RobocopyGUI._import_file_filter_from_file(fake)

    fake._file_filter_var.set.assert_called_once_with("*.zip *.tar")


def test_import_file_filter_shows_info_when_no_usable_patterns(tmp_path: Path) -> None:
    """An info dialog is shown when every line is blank or a comment."""
    txt = tmp_path / "includes.txt"
    txt.write_text("# only comments\n\n", encoding="utf-8")

    fake = _make_fake_self()
    fake._file_filter_var.get.return_value = ""
    fake._file_filter_entry = MagicMock()

    with (
        patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)),
        patch("rbcopy.gui.main_window.messagebox.showinfo") as mock_info,
    ):
        RobocopyGUI._import_file_filter_from_file(fake)

    mock_info.assert_called_once()
    fake._file_filter_var.set.assert_not_called()
    fake._file_filter_enabled_var.set.assert_not_called()


def test_import_file_filter_shows_error_on_read_failure(tmp_path: Path) -> None:
    """An error dialog is shown when the chosen file cannot be read."""
    fake = _make_fake_self()
    fake._file_filter_var.get.return_value = ""
    fake._file_filter_entry = MagicMock()

    with (
        patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(tmp_path / "missing.txt")),
        patch("rbcopy.gui.main_window.messagebox.showerror") as mock_err,
    ):
        RobocopyGUI._import_file_filter_from_file(fake)

    mock_err.assert_called_once()
    fake._file_filter_var.set.assert_not_called()
    fake._file_filter_enabled_var.set.assert_not_called()


# ---------------------------------------------------------------------------
# Quoting and encoding tests shared by both import helpers
# ---------------------------------------------------------------------------


def test_import_exclusions_quotes_patterns_with_spaces(tmp_path: Path) -> None:
    """Patterns containing spaces must be wrapped in double-quotes."""
    txt = tmp_path / "exclusions.txt"
    txt.write_text("My Folder\nnormal\nAnother Dir\n", encoding="utf-8")

    fake = _make_fake_self()
    enabled_var, value_var, entry = _make_import_vars()

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)):
        RobocopyGUI._import_exclusions_from_file(fake, "/XD", enabled_var, value_var, entry)

    value_var.set.assert_called_once_with('"My Folder" normal "Another Dir"')


def test_import_exclusions_does_not_double_quote_already_quoted(tmp_path: Path) -> None:
    """Patterns already wrapped in double-quotes must not be quoted again."""
    txt = tmp_path / "exclusions.txt"
    txt.write_text('"Already Quoted"\nnormal\n', encoding="utf-8")

    fake = _make_fake_self()
    enabled_var, value_var, entry = _make_import_vars()

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)):
        RobocopyGUI._import_exclusions_from_file(fake, "/XD", enabled_var, value_var, entry)

    value_var.set.assert_called_once_with('"Already Quoted" normal')


def test_import_exclusions_handles_unicode_decode_error(tmp_path: Path) -> None:
    """A UnicodeDecodeError when reading the file must show an error dialog."""
    txt = tmp_path / "exclusions.txt"
    txt.write_bytes(b"\xff\xfe invalid utf-8 \x00")

    fake = _make_fake_self()
    enabled_var, value_var, entry = _make_import_vars()

    with (
        patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)),
        patch("rbcopy.gui.main_window.messagebox.showerror") as mock_err,
    ):
        RobocopyGUI._import_exclusions_from_file(fake, "/XF", enabled_var, value_var, entry)

    mock_err.assert_called_once()
    value_var.set.assert_not_called()


def test_import_file_filter_quotes_patterns_with_spaces(tmp_path: Path) -> None:
    """File filter patterns containing spaces must be wrapped in double-quotes."""
    txt = tmp_path / "filters.txt"
    txt.write_text("My Report.docx\nplain.txt\n", encoding="utf-8")

    fake = _make_fake_self()
    fake._file_filter_var.get.return_value = ""
    fake._file_filter_entry = MagicMock()

    with patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)):
        RobocopyGUI._import_file_filter_from_file(fake)

    fake._file_filter_var.set.assert_called_once_with('"My Report.docx" plain.txt')


def test_import_file_filter_handles_unicode_decode_error(tmp_path: Path) -> None:
    """A UnicodeDecodeError when reading the file must show an error dialog."""
    txt = tmp_path / "filters.txt"
    txt.write_bytes(b"\xff\xfe invalid utf-8 \x00")

    fake = _make_fake_self()
    fake._file_filter_var.get.return_value = ""
    fake._file_filter_entry = MagicMock()

    with (
        patch("rbcopy.gui.main_window.filedialog.askopenfilename", return_value=str(txt)),
        patch("rbcopy.gui.main_window.messagebox.showerror") as mock_err,
    ):
        RobocopyGUI._import_file_filter_from_file(fake)

    mock_err.assert_called_once()
    fake._file_filter_var.set.assert_not_called()


