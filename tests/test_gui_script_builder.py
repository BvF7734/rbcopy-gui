"""Tests for _ScriptExportDialog (rbcopy.gui.script_builder)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# _ScriptExportDialog._on_save tests
# ---------------------------------------------------------------------------


def _make_fake_dialog(tmp_path: Path) -> MagicMock:
    """Return a MagicMock suitable as a fake 'self' for _ScriptExportDialog methods."""
    fake: MagicMock = MagicMock()
    fake._cmd = ["robocopy", "C:/src", "C:/dst", "/MIR"]
    fake._type_var.get.return_value = "batch"
    fake._name_var.get.return_value = "my_script"
    fake._dir_var.get.return_value = str(tmp_path)
    return fake


def test_on_save_writes_batch_file(tmp_path: Path) -> None:
    """_on_save must write a .bat file when script type is 'batch'."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)

    with patch("rbcopy.gui.script_builder.messagebox.showinfo"):
        _ScriptExportDialog._on_save(fake)

    out_path = tmp_path / "my_script.bat"
    assert out_path.exists(), "Expected .bat file to be written"
    content = out_path.read_text(encoding="utf-8")
    assert "@echo off" in content
    assert "robocopy" in content


def test_on_save_writes_powershell_file(tmp_path: Path) -> None:
    """_on_save must write a .ps1 file when script type is 'powershell'."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._type_var.get.return_value = "powershell"

    with patch("rbcopy.gui.script_builder.messagebox.showinfo"):
        _ScriptExportDialog._on_save(fake)

    out_path = tmp_path / "my_script.ps1"
    assert out_path.exists(), "Expected .ps1 file to be written"
    content = out_path.read_text(encoding="utf-8")
    assert "exit $exitCode" in content
    assert "robocopy" in content


def test_on_save_adds_bat_extension_when_missing(tmp_path: Path) -> None:
    """_on_save must append .bat when the user omits the extension for batch type."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._name_var.get.return_value = "my_script"  # no extension

    with patch("rbcopy.gui.script_builder.messagebox.showinfo"):
        _ScriptExportDialog._on_save(fake)

    assert (tmp_path / "my_script.bat").exists()


def test_on_save_adds_ps1_extension_when_missing(tmp_path: Path) -> None:
    """_on_save must append .ps1 when the user omits the extension for powershell type."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._type_var.get.return_value = "powershell"
    fake._name_var.get.return_value = "my_script"  # no extension

    with patch("rbcopy.gui.script_builder.messagebox.showinfo"):
        _ScriptExportDialog._on_save(fake)

    assert (tmp_path / "my_script.ps1").exists()


def test_on_save_preserves_bat_extension(tmp_path: Path) -> None:
    """_on_save must not add a second extension when the user already provided .bat."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._name_var.get.return_value = "my_script.bat"

    with patch("rbcopy.gui.script_builder.messagebox.showinfo"):
        _ScriptExportDialog._on_save(fake)

    assert (tmp_path / "my_script.bat").exists()
    assert not (tmp_path / "my_script.bat.bat").exists()


def test_on_save_preserves_cmd_extension(tmp_path: Path) -> None:
    """_on_save must not add .bat when the user already provided .cmd."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._name_var.get.return_value = "my_script.cmd"

    with patch("rbcopy.gui.script_builder.messagebox.showinfo"):
        _ScriptExportDialog._on_save(fake)

    assert (tmp_path / "my_script.cmd").exists()
    assert not (tmp_path / "my_script.cmd.bat").exists()


def test_on_save_shows_warning_when_name_empty(tmp_path: Path) -> None:
    """_on_save must show a warning and not write any file when file name is empty."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._name_var.get.return_value = ""

    with patch("rbcopy.gui.script_builder.messagebox.showwarning") as mock_warn:
        _ScriptExportDialog._on_save(fake)

    mock_warn.assert_called_once()
    # The temporary directory must remain empty – no file was written.
    assert not any(tmp_path.iterdir())


def test_on_save_shows_warning_when_directory_empty(tmp_path: Path) -> None:
    """_on_save must show a warning and not write any file when location is empty."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._dir_var.get.return_value = ""

    with patch("rbcopy.gui.script_builder.messagebox.showwarning") as mock_warn:
        _ScriptExportDialog._on_save(fake)

    mock_warn.assert_called_once()


def test_on_save_shows_error_on_write_failure(tmp_path: Path) -> None:
    """_on_save must show an error dialog when the file cannot be written."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)

    with (
        patch("rbcopy.gui.script_builder.messagebox.showerror") as mock_error,
        patch("rbcopy.gui.script_builder.Path.write_text", side_effect=OSError("disk full")),
    ):
        _ScriptExportDialog._on_save(fake)

    mock_error.assert_called_once()
    args = mock_error.call_args.args
    assert "disk full" in args[1]


def test_on_save_sets_saved_flag_on_success(tmp_path: Path) -> None:
    """_on_save must set self._saved = True when the file is written successfully."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)

    with patch("rbcopy.gui.script_builder.messagebox.showinfo"):
        _ScriptExportDialog._on_save(fake)

    assert fake._saved is True


def test_on_save_does_not_set_saved_flag_on_empty_name(tmp_path: Path) -> None:
    """_on_save must NOT set self._saved when validation fails (empty name)."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._name_var.get.return_value = ""
    fake._saved = False  # explicitly set initial state

    with patch("rbcopy.gui.script_builder.messagebox.showwarning"):
        _ScriptExportDialog._on_save(fake)

    assert fake._saved is False


def test_on_save_shows_error_on_unknown_script_type(tmp_path: Path) -> None:
    """_on_save must show an error and write no file when script type is unknown."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._type_var.get.return_value = "unknown_type"
    fake._saved = False

    with patch("rbcopy.gui.script_builder.messagebox.showerror") as mock_error:
        _ScriptExportDialog._on_save(fake)

    mock_error.assert_called_once()
    assert not any(tmp_path.iterdir()), "No file should be written for an unknown type"
    assert fake._saved is False


def test_on_save_rejects_parent_traversal_in_name(tmp_path: Path) -> None:
    """_on_save must show a warning and write no file when the name contains a parent reference."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._name_var.get.return_value = "../evil"
    fake._saved = False

    with (
        patch("rbcopy.gui.script_builder.messagebox.showwarning") as mock_warn,
    ):
        _ScriptExportDialog._on_save(fake)

    mock_warn.assert_called_once()
    assert not any(tmp_path.iterdir()), "No file should be written for a name with parent traversal"
    assert fake._saved is False


def test_on_save_rejects_subdirectory_in_name(tmp_path: Path) -> None:
    """_on_save must show a warning and write no file when the name contains a subdirectory."""
    from rbcopy.gui.script_builder import _ScriptExportDialog

    fake = _make_fake_dialog(tmp_path)
    fake._name_var.get.return_value = "subdir/script"
    fake._saved = False

    with (
        patch("rbcopy.gui.script_builder.messagebox.showwarning") as mock_warn,
    ):
        _ScriptExportDialog._on_save(fake)

    mock_warn.assert_called_once()
    assert not any(tmp_path.iterdir()), "No file should be written for a name with a subdirectory component"
    assert fake._saved is False
