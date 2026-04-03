"""Tests for RobocopyGUI job-history helpers and advanced-mode methods (rbcopy.gui.main_window)."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rbcopy.gui import RobocopyGUI
from tests.helpers import make_fake_self as _make_fake_self

# ---------------------------------------------------------------------------
# Job history – module-level helper tests
# ---------------------------------------------------------------------------


def test_exit_code_label_zero() -> None:
    """exit_code_label returns the correct message for exit code 0."""
    from rbcopy.builder import exit_code_label

    assert "Nothing to do" in exit_code_label(0)


def test_exit_code_label_one() -> None:
    """exit_code_label describes exit code 1 as files copied successfully."""
    from rbcopy.builder import exit_code_label

    assert "Files copied successfully" in exit_code_label(1)


def test_exit_code_label_additive() -> None:
    """exit_code_label combines descriptions for additive codes."""
    from rbcopy.builder import exit_code_label

    label = exit_code_label(3)
    assert "Files copied" in label
    assert "extra files" in label.lower()


def test_exit_code_label_fatal() -> None:
    """exit_code_label includes 'Fatal error' for exit code 16."""
    from rbcopy.builder import exit_code_label

    assert "Fatal error" in exit_code_label(16)


def test_parse_log_exit_code_nonzero(tmp_path: Path) -> None:
    """_parse_log_exit_code extracts a non-zero exit code from a log file."""
    from rbcopy.gui.job_history import _parse_log_exit_code

    log = tmp_path / "robocopy_job_20240101_120000.log"
    log.write_text(
        "2024-01-01 12:00:00 [INFO    ] rbcopy.gui: robocopy finished with exit code 3\n",
        encoding="utf-8",
    )
    assert _parse_log_exit_code(log) == 3


def test_parse_log_exit_code_zero(tmp_path: Path) -> None:
    """_parse_log_exit_code extracts exit code 0 from a 'completed successfully' line."""
    from rbcopy.gui.job_history import _parse_log_exit_code

    log = tmp_path / "robocopy_job_20240101_120001.log"
    log.write_text(
        "2024-01-01 12:00:01 [INFO    ] rbcopy.gui: robocopy completed successfully (exit code 0)\n",
        encoding="utf-8",
    )
    assert _parse_log_exit_code(log) == 0


def test_parse_log_exit_code_missing(tmp_path: Path) -> None:
    """_parse_log_exit_code returns None when no exit code line is present."""
    from rbcopy.gui.job_history import _parse_log_exit_code

    log = tmp_path / "robocopy_job_20240101_120002.log"
    log.write_text("2024-01-01 12:00:02 [DEBUG   ] rbcopy.gui: some debug line\n", encoding="utf-8")
    assert _parse_log_exit_code(log) is None


def test_parse_log_exit_code_unreadable(tmp_path: Path) -> None:
    """_parse_log_exit_code returns None for a path that cannot be read."""
    from rbcopy.gui.job_history import _parse_log_exit_code

    result = _parse_log_exit_code(tmp_path / "does_not_exist.log")
    assert result is None


# ---------------------------------------------------------------------------
# Job history – RobocopyGUI method tests
# ---------------------------------------------------------------------------


def test_job_history_method_exists() -> None:
    """RobocopyGUI must expose a callable _open_job_history method."""
    assert callable(RobocopyGUI._open_job_history)


def test_get_log_dir_returns_none_without_file_handler() -> None:
    """_get_log_dir returns None when the rbcopy logger has no FileHandler."""
    fake = _make_fake_self()

    with patch("rbcopy.gui.main_window.logging.getLogger") as mock_get_logger:
        mock_logger = MagicMock()
        mock_logger.handlers = []
        mock_get_logger.return_value = mock_logger
        result = RobocopyGUI._get_log_dir(fake)

    assert result is None


def test_get_log_dir_returns_parent_of_handler_file(tmp_path: Path) -> None:
    """_get_log_dir returns the directory of the FileHandler's log file."""
    fake = _make_fake_self()
    log_file = tmp_path / "robocopy_job_20240101_120000.log"
    log_file.touch()

    handler = logging.FileHandler(str(log_file))
    try:
        with patch("rbcopy.gui.main_window.logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_logger.handlers = [handler]
            mock_get_logger.return_value = mock_logger
            result = RobocopyGUI._get_log_dir(fake)
    finally:
        handler.close()

    assert result == tmp_path


def test_open_job_history_shows_info_when_no_log_dir() -> None:
    """_open_job_history shows an info dialog when no log directory is available."""
    fake = _make_fake_self()
    # _open_job_history calls self._get_log_dir(); set it on the MagicMock directly
    # so the call goes to our mock, not the real method.
    fake._get_log_dir.return_value = None

    with patch("rbcopy.gui.main_window.messagebox.showinfo") as mock_info:
        RobocopyGUI._open_job_history(fake)

    mock_info.assert_called_once()


def test_open_job_history_opens_window_when_log_dir_exists(tmp_path: Path) -> None:
    """_open_job_history creates a _JobHistoryWindow when a log directory is available."""
    fake = _make_fake_self()
    fake._get_log_dir.return_value = tmp_path

    with patch("rbcopy.gui.main_window._JobHistoryWindow") as mock_window_cls:
        RobocopyGUI._open_job_history(fake)

    mock_window_cls.assert_called_once_with(fake, tmp_path)



# ---------------------------------------------------------------------------
# Simple / Advanced mode toggle – _toggle_advanced
# ---------------------------------------------------------------------------


def test_toggle_advanced_shows_frame() -> None:
    """_toggle_advanced packs the advanced frame when currently hidden."""
    fake = _make_fake_self()
    fake._advanced_visible = False

    RobocopyGUI._toggle_advanced(fake)

    fake._advanced_frame.pack.assert_called_once_with(fill="x")
    assert fake._advanced_visible is True


def test_toggle_advanced_hides_frame() -> None:
    """_toggle_advanced removes the advanced frame when currently visible."""
    fake = _make_fake_self()
    fake._advanced_visible = True

    RobocopyGUI._toggle_advanced(fake)

    fake._advanced_frame.pack_forget.assert_called_once_with()
    assert fake._advanced_visible is False


def test_toggle_advanced_expand_updates_button_text() -> None:
    """_toggle_advanced sets button label to the down-pointing variant on expand."""
    fake = _make_fake_self()
    fake._advanced_visible = False

    RobocopyGUI._toggle_advanced(fake)

    fake._btn_advanced.config.assert_called_once_with(text="\u2699 Advanced \u25be")


def test_toggle_advanced_collapse_updates_button_text() -> None:
    """_toggle_advanced sets button label to the right-pointing variant on collapse."""
    fake = _make_fake_self()
    fake._advanced_visible = True

    RobocopyGUI._toggle_advanced(fake)

    fake._btn_advanced.config.assert_called_once_with(text="\u2699 Advanced \u25b8")


# ---------------------------------------------------------------------------
# Simple / Advanced mode toggle – _on_preset_selected
# ---------------------------------------------------------------------------


def test_on_preset_selected_properties_only() -> None:
    """_on_preset_selected activates the Properties Only preset when chosen."""
    fake = _make_fake_self()
    fake._preset_var.get.return_value = "Properties Only"

    RobocopyGUI._on_preset_selected(fake, MagicMock())

    fake._props_only_var.set.assert_called_once_with(True)


def test_on_preset_selected_custom_preset() -> None:
    """_on_preset_selected calls _apply_custom_preset with the matching preset object."""
    from rbcopy.presets import CustomPreset, CustomPresetsStore

    fake = _make_fake_self()
    preset = CustomPreset(name="My Preset")
    fake._preset_var.get.return_value = "My Preset"
    fake._presets_store = MagicMock(spec=CustomPresetsStore)
    fake._presets_store.get_preset.return_value = preset

    RobocopyGUI._on_preset_selected(fake, MagicMock())

    fake._presets_store.get_preset.assert_called_once_with("My Preset")
    fake._apply_custom_preset.assert_called_once_with(preset)


def test_on_preset_selected_resets_combo() -> None:
    """_on_preset_selected resets both the StringVar and the Combobox after applying."""
    fake = _make_fake_self()
    fake._preset_var.get.return_value = "Properties Only"

    RobocopyGUI._on_preset_selected(fake, MagicMock())

    fake._preset_var.set.assert_called_once_with("")
    fake._preset_combo.set.assert_called_once_with("")


def test_on_preset_selected_ignores_empty() -> None:
    """_on_preset_selected is a no-op when the selection resolves to an empty string."""
    fake = _make_fake_self()
    fake._preset_var.get.return_value = ""

    RobocopyGUI._on_preset_selected(fake, MagicMock())

    fake._props_only_var.set.assert_not_called()
    fake._apply_custom_preset.assert_not_called()
    fake._preset_var.set.assert_not_called()


# ---------------------------------------------------------------------------
# Simple / Advanced mode toggle – _refresh_preset_combo
# ---------------------------------------------------------------------------


def test_refresh_preset_combo_sets_values() -> None:
    """_refresh_preset_combo populates the combo with Properties Only plus presets."""
    from rbcopy.presets import CustomPreset, CustomPresetsStore

    fake = _make_fake_self()
    fake._preset_combo = MagicMock()
    fake._presets_store = MagicMock(spec=CustomPresetsStore)
    fake._presets_store.presets = [CustomPreset(name="Alpha"), CustomPreset(name="Beta")]

    RobocopyGUI._refresh_preset_combo(fake)

    fake._preset_combo.__setitem__.assert_called_once_with("values", ["Properties Only", "Alpha", "Beta"])


def test_refresh_preset_combo_skips_when_none() -> None:
    """_refresh_preset_combo returns immediately when _preset_combo is None."""
    fake = _make_fake_self()
    fake._preset_combo = None

    # Must not raise.
    RobocopyGUI._refresh_preset_combo(fake)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Gap 11: _get_preset_description_map
# ---------------------------------------------------------------------------


def test_get_preset_description_map_includes_properties_only() -> None:
    """_get_preset_description_map always includes 'Properties Only' with a description."""
    from rbcopy.presets import CustomPresetsStore

    fake = _make_fake_self()
    fake._presets_store = MagicMock(spec=CustomPresetsStore)
    fake._presets_store.presets = []

    result = RobocopyGUI._get_preset_description_map(fake)

    assert "Properties Only" in result
    assert result["Properties Only"]  # non-empty description


def test_get_preset_description_map_includes_presets_with_description() -> None:
    """_get_preset_description_map includes custom presets that have a description."""
    from rbcopy.presets import CustomPreset, CustomPresetsStore

    fake = _make_fake_self()
    fake._presets_store = MagicMock(spec=CustomPresetsStore)
    fake._presets_store.presets = [
        CustomPreset(name="With Desc", description="Backs up docs nightly."),
        CustomPreset(name="No Desc", description=""),
    ]

    result = RobocopyGUI._get_preset_description_map(fake)

    assert "With Desc" in result
    assert result["With Desc"] == "Backs up docs nightly."


def test_get_preset_description_map_omits_presets_without_description() -> None:
    """_get_preset_description_map omits custom presets with an empty description."""
    from rbcopy.presets import CustomPreset, CustomPresetsStore

    fake = _make_fake_self()
    fake._presets_store = MagicMock(spec=CustomPresetsStore)
    fake._presets_store.presets = [CustomPreset(name="No Desc", description="")]

    result = RobocopyGUI._get_preset_description_map(fake)

    assert "No Desc" not in result


