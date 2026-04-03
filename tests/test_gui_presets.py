"""Tests for RobocopyGUI custom preset methods (rbcopy.gui.main_window)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch


from rbcopy.gui import RobocopyGUI
from tests.helpers import make_fake_self as _make_fake_self

# ---------------------------------------------------------------------------
# Custom preset methods – _save_custom_preset
# ---------------------------------------------------------------------------


def _make_fake_self_for_presets() -> MagicMock:
    """Return a fake self with preset-related attributes pre-configured."""
    fake = _make_fake_self()
    fake.src_var.get.return_value = "C:/src"
    fake.dst_var.get.return_value = "C:/dst"
    fake._get_selections.return_value = ({"/MIR": True}, {"/R": (True, "3")})
    return fake


def _mock_dialog(name: str | None, description: str = "") -> MagicMock:
    """Return a mock _SavePresetDialog instance with name and description properties.

    ``name`` is *None* when the dialog is cancelled; a non-empty string otherwise.
    """
    mock = MagicMock()
    type(mock).name = PropertyMock(return_value=name)
    type(mock).description = PropertyMock(return_value=description)
    return mock


def test_save_custom_preset_calls_store(tmp_path: Path) -> None:
    """_save_custom_preset saves the current selections to the presets store."""
    from rbcopy.presets import CustomPresetsStore

    fake = _make_fake_self_for_presets()
    fake._presets_store = CustomPresetsStore(path=tmp_path / "presets.json")

    with (
        patch("rbcopy.gui.main_window._SavePresetDialog", return_value=_mock_dialog("My Preset")),
        patch("rbcopy.gui.main_window.messagebox.showinfo"),
    ):
        RobocopyGUI._save_custom_preset(fake)

    preset = fake._presets_store.get_preset("My Preset")
    assert preset is not None
    assert preset.source == "C:/src"
    assert preset.destination == "C:/dst"
    assert preset.flags == {"/MIR": True}
    assert preset.params == {"/R": (True, "3")}


def test_save_custom_preset_rebuilds_menu(tmp_path: Path) -> None:
    """_save_custom_preset calls _rebuild_custom_menu after saving."""
    from rbcopy.presets import CustomPresetsStore

    fake = _make_fake_self_for_presets()
    fake._presets_store = CustomPresetsStore(path=tmp_path / "presets.json")

    with (
        patch("rbcopy.gui.main_window._SavePresetDialog", return_value=_mock_dialog("P")),
        patch("rbcopy.gui.main_window.messagebox.showinfo"),
    ):
        RobocopyGUI._save_custom_preset(fake)

    fake._rebuild_custom_menu.assert_called_once()


def test_save_custom_preset_shows_info_dialog(tmp_path: Path) -> None:
    """_save_custom_preset shows a success info dialog after saving."""
    from rbcopy.presets import CustomPresetsStore

    fake = _make_fake_self_for_presets()
    fake._presets_store = CustomPresetsStore(path=tmp_path / "presets.json")

    with (
        patch("rbcopy.gui.main_window._SavePresetDialog", return_value=_mock_dialog("Q")),
        patch("rbcopy.gui.main_window.messagebox.showinfo") as mock_info,
    ):
        RobocopyGUI._save_custom_preset(fake)

    mock_info.assert_called_once()


def test_save_custom_preset_cancelled_when_name_empty() -> None:
    """_save_custom_preset does nothing when the dialog returns None (user cancelled)."""
    fake = _make_fake_self_for_presets()

    with patch("rbcopy.gui.main_window._SavePresetDialog", return_value=_mock_dialog(None)):
        RobocopyGUI._save_custom_preset(fake)

    fake._rebuild_custom_menu.assert_not_called()


def test_save_custom_preset_cancelled_when_dialog_dismissed() -> None:
    """_save_custom_preset does nothing when the user cancels the dialog."""
    fake = _make_fake_self_for_presets()

    with patch("rbcopy.gui.main_window._SavePresetDialog", return_value=_mock_dialog(None)):
        RobocopyGUI._save_custom_preset(fake)

    fake._rebuild_custom_menu.assert_not_called()


def test_save_custom_preset_shows_error_on_disk_failure(tmp_path: Path) -> None:
    """_save_custom_preset shows an error dialog when the file write fails."""
    from rbcopy.presets import CustomPresetsStore

    fake = _make_fake_self_for_presets()
    fake._presets_store = CustomPresetsStore(path=tmp_path / "presets.json")

    with (
        patch("rbcopy.gui.main_window._SavePresetDialog", return_value=_mock_dialog("Fail")),
        patch("rbcopy.gui.main_window.messagebox.showerror") as mock_error,
        patch.object(Path, "write_bytes", side_effect=OSError("disk full")),
    ):
        RobocopyGUI._save_custom_preset(fake)

    mock_error.assert_called_once()
    # Menu must NOT be rebuilt when saving fails.
    fake._rebuild_custom_menu.assert_not_called()


def test_save_custom_preset_no_info_dialog_on_failure(tmp_path: Path) -> None:
    """_save_custom_preset must NOT show a success dialog when saving fails."""
    from rbcopy.presets import CustomPresetsStore

    fake = _make_fake_self_for_presets()
    fake._presets_store = CustomPresetsStore(path=tmp_path / "presets.json")

    with (
        patch("rbcopy.gui.main_window._SavePresetDialog", return_value=_mock_dialog("Fail")),
        patch("rbcopy.gui.main_window.messagebox.showinfo") as mock_info,
        patch("rbcopy.gui.main_window.messagebox.showerror"),
        patch.object(Path, "write_bytes", side_effect=OSError("disk full")),
    ):
        RobocopyGUI._save_custom_preset(fake)

    mock_info.assert_not_called()


def test_save_custom_preset_includes_file_filter(tmp_path: Path) -> None:
    """_save_custom_preset persists the current file filter value to the preset."""
    from rbcopy.presets import CustomPresetsStore

    fake = _make_fake_self_for_presets()
    fake._file_filter_enabled_var.get.return_value = True
    fake._file_filter_var.get.return_value = "*.img *.raw"
    fake._presets_store = CustomPresetsStore(path=tmp_path / "presets.json")

    with (
        patch("rbcopy.gui.main_window._SavePresetDialog", return_value=_mock_dialog("Filter Preset")),
        patch("rbcopy.gui.main_window.messagebox.showinfo"),
    ):
        RobocopyGUI._save_custom_preset(fake)

    preset = fake._presets_store.get_preset("Filter Preset")
    assert preset is not None
    assert preset.file_filter == "*.img *.raw"


def test_save_custom_preset_stores_empty_filter_when_disabled(tmp_path: Path) -> None:
    """_save_custom_preset stores an empty file_filter when the filter checkbox is unchecked."""
    from rbcopy.presets import CustomPresetsStore

    fake = _make_fake_self_for_presets()
    fake._file_filter_enabled_var.get.return_value = False
    fake._file_filter_var.get.return_value = "*.img"
    fake._presets_store = CustomPresetsStore(path=tmp_path / "presets.json")

    with (
        patch("rbcopy.gui.main_window._SavePresetDialog", return_value=_mock_dialog("No Filter")),
        patch("rbcopy.gui.main_window.messagebox.showinfo"),
    ):
        RobocopyGUI._save_custom_preset(fake)

    preset = fake._presets_store.get_preset("No Filter")
    assert preset is not None
    assert preset.file_filter == ""


def test_save_custom_preset_stores_description(tmp_path: Path) -> None:
    """_save_custom_preset persists the description entered in the dialog."""
    from rbcopy.presets import CustomPresetsStore

    fake = _make_fake_self_for_presets()
    fake._presets_store = CustomPresetsStore(path=tmp_path / "presets.json")

    with (
        patch(
            "rbcopy.gui.main_window._SavePresetDialog",
            return_value=_mock_dialog("My Preset", "Backs up all files nightly."),
        ),
        patch("rbcopy.gui.main_window.messagebox.showinfo"),
    ):
        RobocopyGUI._save_custom_preset(fake)

    preset = fake._presets_store.get_preset("My Preset")
    assert preset is not None
    assert preset.description == "Backs up all files nightly."


def test_save_custom_preset_stores_empty_description_when_omitted(tmp_path: Path) -> None:
    """_save_custom_preset stores an empty description when the user leaves it blank."""
    from rbcopy.presets import CustomPresetsStore

    fake = _make_fake_self_for_presets()
    fake._presets_store = CustomPresetsStore(path=tmp_path / "presets.json")

    with (
        patch("rbcopy.gui.main_window._SavePresetDialog", return_value=_mock_dialog("Unnamed", "")),
        patch("rbcopy.gui.main_window.messagebox.showinfo"),
    ):
        RobocopyGUI._save_custom_preset(fake)

    preset = fake._presets_store.get_preset("Unnamed")
    assert preset is not None
    assert preset.description == ""


# ---------------------------------------------------------------------------
# Custom preset methods – _apply_custom_preset
# ---------------------------------------------------------------------------


def test_apply_custom_preset_sets_source_and_destination() -> None:
    """_apply_custom_preset sets src_var and dst_var from the preset."""
    from rbcopy.presets import CustomPreset

    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = False
    preset = CustomPreset(name="p", source="/a", destination="/b")

    RobocopyGUI._apply_custom_preset(fake, preset)

    fake.src_var.set.assert_called_once_with("/a")
    fake.dst_var.set.assert_called_once_with("/b")


def test_apply_custom_preset_sets_flag_vars() -> None:
    """_apply_custom_preset updates matching _flag_vars entries.

    The method first resets all flags to False and then applies the preset
    values, so set() is called twice per flag: once to reset and once to
    apply.  The final call must use the preset value.
    """
    from rbcopy.presets import CustomPreset

    fake = _make_fake_self()
    mir_var = MagicMock()
    fake._flag_vars = {"/MIR": mir_var}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = False
    preset = CustomPreset(name="p", flags={"/MIR": True})

    RobocopyGUI._apply_custom_preset(fake, preset)

    # First call resets to False; second call applies the preset value True.
    assert mir_var.set.call_count == 2
    mir_var.set.assert_called_with(True)


def test_apply_custom_preset_sets_param_vars() -> None:
    """_apply_custom_preset updates matching _param_vars entries.

    The method first resets all params to (False, placeholder) and then
    applies the preset values, so each set() is called twice.  The final
    call must use the preset value.
    """
    from rbcopy.presets import CustomPreset

    fake = _make_fake_self()
    fake._flag_vars = {}
    ev = MagicMock()
    vv = MagicMock()
    fake._param_vars = {"/R": (ev, vv, MagicMock())}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = False
    preset = CustomPreset(name="p", params={"/R": (True, "5")})

    RobocopyGUI._apply_custom_preset(fake, preset)

    # First call resets to False/""; second call applies the preset value.
    assert ev.set.call_count == 2
    ev.set.assert_called_with(True)
    assert vv.set.call_count == 2
    vv.set.assert_called_with("5")


def test_apply_custom_preset_calls_refresh_widget_states() -> None:
    """_apply_custom_preset calls _refresh_widget_states after applying."""
    from rbcopy.presets import CustomPreset

    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = False
    preset = CustomPreset(name="p")

    RobocopyGUI._apply_custom_preset(fake, preset)

    fake._refresh_widget_states.assert_called_once()


def test_apply_custom_preset_ignores_unknown_flags() -> None:
    """_apply_custom_preset silently skips flags that are not in _flag_vars."""
    from rbcopy.presets import CustomPreset

    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = False
    # /UNKNOWN is not in _flag_vars – must not raise.
    preset = CustomPreset(name="p", flags={"/UNKNOWN": True})

    RobocopyGUI._apply_custom_preset(fake, preset)  # should not raise


def test_apply_custom_preset_skips_dst_when_props_only_active() -> None:
    """_apply_custom_preset must not overwrite dst_var when Properties Only is active."""
    from rbcopy.presets import CustomPreset

    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = True  # Properties Only active
    preset = CustomPreset(name="p", source="/src", destination="/new-dst")

    RobocopyGUI._apply_custom_preset(fake, preset)

    fake.src_var.set.assert_called_once_with("/src")
    fake.dst_var.set.assert_not_called()


def test_apply_custom_preset_skips_forced_flags_when_props_only_active() -> None:
    """_apply_custom_preset must not override forced flags when Properties Only is active."""
    from rbcopy.builder import PROPERTIES_ONLY_FLAGS
    from rbcopy.presets import CustomPreset

    fake = _make_fake_self()
    forced_flag = next(iter(PROPERTIES_ONLY_FLAGS))
    forced_var = MagicMock()
    fake._flag_vars = {forced_flag: forced_var}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = True
    preset = CustomPreset(name="p", flags={forced_flag: False})

    RobocopyGUI._apply_custom_preset(fake, preset)

    forced_var.set.assert_not_called()


def test_apply_custom_preset_skips_forced_params_when_props_only_active() -> None:
    """_apply_custom_preset must not override forced params when Properties Only is active."""
    from rbcopy.builder import PROPERTIES_ONLY_PARAMS
    from rbcopy.presets import CustomPreset

    fake = _make_fake_self()
    fake._flag_vars = {}
    forced_param = next(iter(PROPERTIES_ONLY_PARAMS))
    ev = MagicMock()
    vv = MagicMock()
    fake._param_vars = {forced_param: (ev, vv, MagicMock())}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = True
    preset = CustomPreset(name="p", params={forced_param: (False, "999")})

    RobocopyGUI._apply_custom_preset(fake, preset)

    ev.set.assert_not_called()
    vv.set.assert_not_called()


def test_apply_custom_preset_restores_file_filter() -> None:
    """_apply_custom_preset sets file filter vars when the preset has a non-empty file_filter."""
    from rbcopy.presets import CustomPreset

    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = False
    preset = CustomPreset(name="p", file_filter="*.img *.raw")

    RobocopyGUI._apply_custom_preset(fake, preset)

    fake._file_filter_enabled_var.set.assert_called_with(True)
    fake._file_filter_var.set.assert_called_with("*.img *.raw")


def test_apply_custom_preset_clears_file_filter_when_empty() -> None:
    """_apply_custom_preset disables the file filter when the preset has no file_filter."""
    from rbcopy.presets import CustomPreset

    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = False
    preset = CustomPreset(name="p", file_filter="")

    RobocopyGUI._apply_custom_preset(fake, preset)

    fake._file_filter_enabled_var.set.assert_called_with(False)
    fake._file_filter_var.set.assert_called_with("")


# ---------------------------------------------------------------------------
# _reset_options
# ---------------------------------------------------------------------------


def test_reset_options_method_exists() -> None:
    """RobocopyGUI must expose a callable _reset_options method."""
    assert callable(RobocopyGUI._reset_options)


def test_reset_options_clears_all_flag_vars() -> None:
    """_reset_options sets every _flag_vars entry to False."""
    fake = _make_fake_self()
    flag1 = MagicMock()
    flag2 = MagicMock()
    fake._flag_vars = {"/MIR": flag1, "/L": flag2}
    fake._param_vars = {}
    fake._props_only_var.get.return_value = False
    fake._is_applying_preset = False

    RobocopyGUI._reset_options(fake)

    flag1.set.assert_called_with(False)
    flag2.set.assert_called_with(False)


def test_reset_options_clears_all_param_enabled_vars() -> None:
    """_reset_options sets every param enabled_var to False."""
    fake = _make_fake_self()
    fake._flag_vars = {}
    enabled_var = MagicMock()
    value_var = MagicMock()
    fake._param_vars = {"/MT": (enabled_var, value_var, MagicMock())}
    fake._props_only_var.get.return_value = False
    fake._is_applying_preset = False

    RobocopyGUI._reset_options(fake)

    enabled_var.set.assert_called_with(False)


def test_reset_options_restores_param_placeholder_values() -> None:
    """_reset_options resets each param value_var to its default placeholder."""
    from rbcopy.builder import PARAM_OPTIONS

    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = False

    # Use the first PARAM_OPTIONS entry to get a real flag/placeholder pair.
    first_flag, _label, first_placeholder = PARAM_OPTIONS[0]
    enabled_var = MagicMock()
    value_var = MagicMock()
    fake._param_vars = {first_flag: (enabled_var, value_var, MagicMock())}

    RobocopyGUI._reset_options(fake)

    value_var.set.assert_called_with(first_placeholder)


def test_reset_options_deactivates_properties_only_preset() -> None:
    """_reset_options deactivates Properties Only when it is currently active."""
    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = True

    RobocopyGUI._reset_options(fake)

    fake._props_only_var.set.assert_called_with(False)


def test_reset_options_preserves_src_dst_when_properties_only_active() -> None:
    """_reset_options keeps src_var and dst_var unchanged even when Properties Only is deactivated."""
    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = True
    # Simulate src/dst StringVars with known current values.
    fake.src_var = MagicMock()
    fake.src_var.get.return_value = "C:/source"
    fake.dst_var = MagicMock()
    fake.dst_var.get.return_value = r"c:\temp\blank"

    RobocopyGUI._reset_options(fake)

    # src/dst must be restored to their values captured before deactivation.
    fake.src_var.set.assert_called_with("C:/source")
    fake.dst_var.set.assert_called_with(r"c:\temp\blank")


def test_reset_options_calls_refresh_widget_states() -> None:
    """_reset_options calls _refresh_widget_states after resetting all options."""
    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = False

    RobocopyGUI._reset_options(fake)

    fake._refresh_widget_states.assert_called_once()


def test_reset_options_clears_file_filter_vars() -> None:
    """_reset_options resets _file_filter_enabled_var to False and _file_filter_var to empty."""
    fake = _make_fake_self()
    fake._flag_vars = {}
    fake._param_vars = {}
    fake._is_applying_preset = False
    fake._props_only_var.get.return_value = False

    RobocopyGUI._reset_options(fake)

    fake._file_filter_enabled_var.set.assert_called_with(False)
    fake._file_filter_var.set.assert_called_with("")


# ---------------------------------------------------------------------------
# Custom preset methods – _delete_custom_preset
# ---------------------------------------------------------------------------


def test_delete_custom_preset_removes_preset_after_confirmation(tmp_path: Path) -> None:
    """_delete_custom_preset deletes the preset when the user confirms."""
    from rbcopy.presets import CustomPreset, CustomPresetsStore

    fake = _make_fake_self()
    store = CustomPresetsStore(path=tmp_path / "presets.json")
    store.save_preset(CustomPreset(name="bye"))
    fake._presets_store = store

    with patch("rbcopy.gui.main_window.messagebox.askyesno", return_value=True):
        RobocopyGUI._delete_custom_preset(fake, "bye")

    assert store.get_preset("bye") is None
    fake._rebuild_custom_menu.assert_called_once()


def test_delete_custom_preset_aborts_when_cancelled(tmp_path: Path) -> None:
    """_delete_custom_preset does nothing when the user cancels the confirmation."""
    from rbcopy.presets import CustomPreset, CustomPresetsStore

    fake = _make_fake_self()
    store = CustomPresetsStore(path=tmp_path / "presets.json")
    store.save_preset(CustomPreset(name="stay"))
    fake._presets_store = store

    with patch("rbcopy.gui.main_window.messagebox.askyesno", return_value=False):
        RobocopyGUI._delete_custom_preset(fake, "stay")

    assert store.get_preset("stay") is not None
    fake._rebuild_custom_menu.assert_not_called()


# ---------------------------------------------------------------------------
# Custom preset methods – _rebuild_custom_menu
# ---------------------------------------------------------------------------


def test_rebuild_custom_menu_shows_placeholder_when_empty() -> None:
    """_rebuild_custom_menu adds a disabled placeholder when there are no presets."""
    from rbcopy.presets import CustomPresetsStore

    fake = _make_fake_self()
    fake._presets_store = MagicMock(spec=CustomPresetsStore)
    fake._presets_store.presets = []
    fake._custom_menu = MagicMock()

    RobocopyGUI._rebuild_custom_menu(fake)

    fake._custom_menu.delete.assert_called_once_with(0, "end")
    fake._custom_menu.add_command.assert_called_once()
    args = fake._custom_menu.add_command.call_args.kwargs
    assert args.get("state") == "disabled"


def test_rebuild_custom_menu_adds_cascade_per_preset() -> None:
    """_rebuild_custom_menu adds a cascade entry for each saved preset."""
    from rbcopy.presets import CustomPreset, CustomPresetsStore

    fake = _make_fake_self()
    fake._presets_store = MagicMock(spec=CustomPresetsStore)
    fake._presets_store.presets = [CustomPreset(name="A"), CustomPreset(name="B")]
    fake._custom_menu = MagicMock()

    with patch("rbcopy.gui.main_window.tk.Menu"):
        RobocopyGUI._rebuild_custom_menu(fake)

    assert fake._custom_menu.add_cascade.call_count == 2
    labels = [call.kwargs["label"] for call in fake._custom_menu.add_cascade.call_args_list]
    assert "A" in labels
    assert "B" in labels


def test_rebuild_custom_menu_shows_description_as_info_item() -> None:
    """_rebuild_custom_menu adds a disabled \u2139 item when the preset has a description."""
    from rbcopy.presets import CustomPreset, CustomPresetsStore

    fake = _make_fake_self()
    fake._presets_store = MagicMock(spec=CustomPresetsStore)
    fake._presets_store.presets = [
        CustomPreset(name="Mirror Sync", description="Keeps destination in sync with source.")
    ]
    fake._custom_menu = MagicMock()

    sub_mock = MagicMock()
    with patch("rbcopy.gui.main_window.tk.Menu", return_value=sub_mock):
        RobocopyGUI._rebuild_custom_menu(fake)

    sub_mock.add_command.assert_any_call(label="\u2139  Keeps destination in sync with source.", state="disabled")


def test_rebuild_custom_menu_no_info_item_when_description_empty() -> None:
    """_rebuild_custom_menu does NOT add an \u2139 item when description is empty."""
    from rbcopy.presets import CustomPreset, CustomPresetsStore

    fake = _make_fake_self()
    fake._presets_store = MagicMock(spec=CustomPresetsStore)
    fake._presets_store.presets = [CustomPreset(name="Plain")]
    fake._custom_menu = MagicMock()

    sub_mock = MagicMock()
    with patch("rbcopy.gui.main_window.tk.Menu", return_value=sub_mock):
        RobocopyGUI._rebuild_custom_menu(fake)

    for call in sub_mock.add_command.call_args_list:
        label = call.kwargs.get("label", "")
        assert "\u2139" not in label, f"Unexpected info item found: {label!r}"
