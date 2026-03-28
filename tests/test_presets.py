"""Tests for the custom preset storage module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from rbcopy.presets import CustomPreset, CustomPresetsStore, _load_bundled_presets


# ---------------------------------------------------------------------------
# CustomPreset model tests
# ---------------------------------------------------------------------------


def test_custom_preset_required_name() -> None:
    """CustomPreset must require a non-empty name."""
    preset = CustomPreset(name="my preset")
    assert preset.name == "my preset"


def test_custom_preset_rejects_empty_name() -> None:
    """CustomPreset must reject an empty name string."""
    with pytest.raises(ValidationError):
        CustomPreset(name="")


def test_custom_preset_rejects_whitespace_only_name() -> None:
    """CustomPreset must reject a name that is whitespace only."""
    with pytest.raises(ValidationError):
        CustomPreset(name="   ")


def test_custom_preset_default_source_empty() -> None:
    """source defaults to an empty string."""
    preset = CustomPreset(name="x")
    assert preset.source == ""


def test_custom_preset_default_destination_empty() -> None:
    """destination defaults to an empty string."""
    preset = CustomPreset(name="x")
    assert preset.destination == ""


def test_custom_preset_default_flags_empty() -> None:
    """flags defaults to an empty dict."""
    preset = CustomPreset(name="x")
    assert preset.flags == {}


def test_custom_preset_default_params_empty() -> None:
    """params defaults to an empty dict."""
    preset = CustomPreset(name="x")
    assert preset.params == {}


def test_custom_preset_stores_flags() -> None:
    """flags are stored and retrieved correctly."""
    flags: Dict[str, bool] = {"/MIR": True, "/NP": False, "/L": True}
    preset = CustomPreset(name="p", flags=flags)
    assert preset.flags == flags


def test_custom_preset_stores_params() -> None:
    """params are stored and retrieved correctly."""
    params: Dict[str, Tuple[bool, str]] = {"/MT": (True, "8"), "/R": (False, "5")}
    preset = CustomPreset(name="p", params=params)
    assert preset.params == params


def test_custom_preset_round_trips_json() -> None:
    """CustomPreset serialises to and deserialises from JSON without data loss."""
    original = CustomPreset(
        name="backup",
        source=r"C:\src",
        destination=r"C:\dst",
        flags={"/MIR": True, "/NP": True, "/L": False},
        params={"/MT": (True, "16"), "/R": (True, "3"), "/W": (False, "30")},
    )
    data = original.model_dump()
    restored = CustomPreset.model_validate(data)
    assert restored == original


def test_custom_preset_file_filter_defaults_to_empty() -> None:
    """file_filter defaults to an empty string when not specified."""
    preset = CustomPreset(name="x")
    assert preset.file_filter == ""


def test_custom_preset_round_trips_file_filter() -> None:
    """file_filter is preserved through serialisation and deserialisation."""
    original = CustomPreset(name="x", file_filter="*.img *.raw")
    restored = CustomPreset.model_validate(original.model_dump())
    assert restored.file_filter == "*.img *.raw"


def test_custom_preset_loads_without_file_filter_field() -> None:
    """Old presets serialised without file_filter deserialise cleanly (default empty)."""
    data: Dict[str, Any] = {
        "name": "old",
        "source": "",
        "destination": "",
        "flags": {},
        "params": {},
    }
    preset = CustomPreset.model_validate(data)
    assert preset.file_filter == ""


def test_custom_preset_description_defaults_to_empty() -> None:
    """description defaults to an empty string when not specified."""
    preset = CustomPreset(name="x")
    assert preset.description == ""


def test_custom_preset_round_trips_description() -> None:
    """description is preserved through serialisation and deserialisation."""
    original = CustomPreset(name="x", description="Copies all files safely.")
    restored = CustomPreset.model_validate(original.model_dump())
    assert restored.description == "Copies all files safely."


def test_custom_preset_loads_without_description_field() -> None:
    """Old presets serialised without description deserialise cleanly (default empty)."""
    data: Dict[str, Any] = {
        "name": "old",
        "source": "",
        "destination": "",
        "flags": {},
        "params": {},
    }
    preset = CustomPreset.model_validate(data)
    assert preset.description == ""


# ---------------------------------------------------------------------------
# CustomPresetsStore – construction / loading
# ---------------------------------------------------------------------------


def test_store_starts_empty_when_no_file(tmp_path: Path) -> None:
    """A new store with no existing file and no bundled presets has no presets."""
    with patch("rbcopy.presets._load_bundled_presets", return_value=[]):
        store = CustomPresetsStore(path=tmp_path / "presets.json")
    assert store.presets == []


def test_store_loads_existing_presets(tmp_path: Path) -> None:
    """Presets written to the JSON file are loaded on construction."""
    presets_path = tmp_path / "presets.json"
    preset = CustomPreset(name="saved", source="/a", destination="/b")
    presets_path.write_text(json.dumps([preset.model_dump()]), encoding="utf-8")

    with patch("rbcopy.presets._load_bundled_presets", return_value=[]):
        store = CustomPresetsStore(path=presets_path)
    assert len(store.presets) == 1
    assert store.presets[0].name == "saved"
    assert store.presets[0].source == "/a"


def test_store_recovers_from_corrupt_file(tmp_path: Path) -> None:
    """A corrupt JSON file is silently ignored; the store starts empty."""
    presets_path = tmp_path / "presets.json"
    presets_path.write_text("not valid json", encoding="utf-8")

    # Bundled merge is skipped when the file is corrupt (no merge without a clean load).
    with patch("rbcopy.presets._load_bundled_presets", return_value=[]):
        store = CustomPresetsStore(path=presets_path)
    assert store.presets == []


def test_store_merges_new_bundled_presets_into_existing_file(tmp_path: Path) -> None:
    """New bundled presets are inserted when an existing user file lacks them."""
    presets_path = tmp_path / "presets.json"
    user_preset = CustomPreset(name="My Custom", source="/home")
    presets_path.write_text(json.dumps([user_preset.model_dump()]), encoding="utf-8")

    bundled_a = CustomPreset(name="Bundled A")
    bundled_b = CustomPreset(name="Bundled B")

    with patch("rbcopy.presets._load_bundled_presets", return_value=[bundled_a, bundled_b]):
        store = CustomPresetsStore(path=presets_path)

    names = [p.name for p in store.presets]
    assert "Bundled A" in names
    assert "Bundled B" in names
    assert "My Custom" in names
    assert len(names) == 3


def test_store_merge_prepends_new_bundled_before_user_presets(tmp_path: Path) -> None:
    """New bundled presets are placed before existing user presets in the list."""
    presets_path = tmp_path / "presets.json"
    user_preset = CustomPreset(name="My Custom")
    presets_path.write_text(json.dumps([user_preset.model_dump()]), encoding="utf-8")

    new_bundled = CustomPreset(name="New Bundled")

    with patch("rbcopy.presets._load_bundled_presets", return_value=[new_bundled]):
        store = CustomPresetsStore(path=presets_path)

    assert store.presets[0].name == "New Bundled"
    assert store.presets[1].name == "My Custom"


def test_store_does_not_overwrite_user_preset_with_bundled_name(tmp_path: Path) -> None:
    """A user preset keeps its data even if a bundled preset shares its name."""
    presets_path = tmp_path / "presets.json"
    # User has customised "Mirror Sync" — their version has a specific source.
    user_mirror = CustomPreset(name="Mirror Sync", source="/user/custom/src")
    presets_path.write_text(json.dumps([user_mirror.model_dump()]), encoding="utf-8")

    bundled_mirror = CustomPreset(name="Mirror Sync", source="")

    with patch("rbcopy.presets._load_bundled_presets", return_value=[bundled_mirror]):
        store = CustomPresetsStore(path=presets_path)

    result = store.get_preset("Mirror Sync")
    assert result is not None
    assert result.source == "/user/custom/src"
    assert len(store.presets) == 1  # no duplicate added


def test_store_persists_after_merging_new_bundled_presets(tmp_path: Path) -> None:
    """The merged list is written to disk so future launches find it already merged."""
    presets_path = tmp_path / "presets.json"
    user_preset = CustomPreset(name="Mine")
    presets_path.write_text(json.dumps([user_preset.model_dump()]), encoding="utf-8")

    new_bundled = CustomPreset(name="New Bundled")

    with patch("rbcopy.presets._load_bundled_presets", return_value=[new_bundled]):
        CustomPresetsStore(path=presets_path)

    # Reload fresh — no bundled presets returned now, simulating a second launch
    # where the merged preset is already on disk.
    with patch("rbcopy.presets._load_bundled_presets", return_value=[]):
        store2 = CustomPresetsStore(path=presets_path)

    names = [p.name for p in store2.presets]
    assert "New Bundled" in names
    assert "Mine" in names


def test_store_no_extra_persist_when_no_new_bundled(tmp_path: Path) -> None:
    """No disk write occurs during merge when all bundled presets are already present."""
    presets_path = tmp_path / "presets.json"
    existing = CustomPreset(name="Already Here")
    presets_path.write_text(json.dumps([existing.model_dump()]), encoding="utf-8")

    # All bundled names already present → no merge → no persist call.
    with patch("rbcopy.presets._load_bundled_presets", return_value=[existing]):
        with patch.object(Path, "write_text") as mock_write:
            CustomPresetsStore(path=presets_path)

    mock_write.assert_not_called()


def test_save_preset_rolls_back_in_memory_on_disk_failure(tmp_path: Path) -> None:
    """save_preset must revert the in-memory list when the disk write fails."""
    store = CustomPresetsStore(path=tmp_path / "presets.json")
    store.save_preset(CustomPreset(name="existing"))

    with patch.object(Path, "write_text", side_effect=OSError("disk full")):
        result = store.save_preset(CustomPreset(name="new_preset"))

    assert result is False
    # In-memory list must not contain the failed preset.
    assert store.get_preset("new_preset") is None
    # The original preset must still be present.
    assert store.get_preset("existing") is not None


def test_save_preset_rollback_preserves_original_on_replace_failure(tmp_path: Path) -> None:
    """When replacing an existing preset fails, the original must be restored."""
    store = CustomPresetsStore(path=tmp_path / "presets.json")
    store.save_preset(CustomPreset(name="my_preset", source="/original"))

    with patch.object(Path, "write_text", side_effect=OSError("disk full")):
        result = store.save_preset(CustomPreset(name="my_preset", source="/replacement"))

    assert result is False
    # The original must still be intact, not the replacement.
    preset = store.get_preset("my_preset")
    assert preset is not None
    assert preset.source == "/original"


def test_save_preset_in_memory_consistent_with_disk_after_failure(tmp_path: Path) -> None:
    """After a failed save, reloading from disk must match the in-memory state."""
    presets_path = tmp_path / "presets.json"
    store = CustomPresetsStore(path=presets_path)
    store.save_preset(CustomPreset(name="good_preset"))

    with patch.object(Path, "write_text", side_effect=OSError("disk full")):
        store.save_preset(CustomPreset(name="failed_preset"))

    # Reload from disk and compare.
    reloaded = CustomPresetsStore(path=presets_path)
    assert [p.name for p in store.presets] == [p.name for p in reloaded.presets]


# ---------------------------------------------------------------------------
# CustomPresetsStore.save_preset
# ---------------------------------------------------------------------------


def test_save_preset_adds_new_preset(tmp_path: Path) -> None:
    """save_preset adds a new preset to the in-memory list."""
    with patch("rbcopy.presets._load_bundled_presets", return_value=[]):
        store = CustomPresetsStore(path=tmp_path / "presets.json")
    result = store.save_preset(CustomPreset(name="first"))
    assert result is True
    assert len(store.presets) == 1
    assert store.presets[0].name == "first"


def test_save_preset_persists_to_file(tmp_path: Path) -> None:
    """save_preset writes the preset to the JSON file immediately."""
    presets_path = tmp_path / "presets.json"
    with patch("rbcopy.presets._load_bundled_presets", return_value=[]):
        store = CustomPresetsStore(path=presets_path)
    store.save_preset(CustomPreset(name="p", source="/src"))

    data = json.loads(presets_path.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["name"] == "p"
    assert data[0]["source"] == "/src"


def test_save_preset_replaces_existing_by_name(tmp_path: Path) -> None:
    """save_preset overwrites a preset that already has the same name."""
    with patch("rbcopy.presets._load_bundled_presets", return_value=[]):
        store = CustomPresetsStore(path=tmp_path / "presets.json")
    store.save_preset(CustomPreset(name="dup", source="/old"))
    store.save_preset(CustomPreset(name="dup", source="/new"))

    assert len(store.presets) == 1
    assert store.presets[0].source == "/new"


def test_save_multiple_presets(tmp_path: Path) -> None:
    """Multiple presets with distinct names are all retained."""
    with patch("rbcopy.presets._load_bundled_presets", return_value=[]):
        store = CustomPresetsStore(path=tmp_path / "presets.json")
    store.save_preset(CustomPreset(name="a"))
    store.save_preset(CustomPreset(name="b"))
    store.save_preset(CustomPreset(name="c"))
    assert [p.name for p in store.presets] == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# CustomPresetsStore.delete_preset
# ---------------------------------------------------------------------------


def test_delete_preset_removes_it(tmp_path: Path) -> None:
    """delete_preset removes the named preset from the list."""
    with patch("rbcopy.presets._load_bundled_presets", return_value=[]):
        store = CustomPresetsStore(path=tmp_path / "presets.json")
    store.save_preset(CustomPreset(name="keep"))
    store.save_preset(CustomPreset(name="remove"))
    store.delete_preset("remove")

    names = [p.name for p in store.presets]
    assert "remove" not in names
    assert "keep" in names


def test_delete_preset_persists_change(tmp_path: Path) -> None:
    """delete_preset updates the JSON file so the removal survives a reload."""
    presets_path = tmp_path / "presets.json"
    with patch("rbcopy.presets._load_bundled_presets", return_value=[]):
        store = CustomPresetsStore(path=presets_path)
    store.save_preset(CustomPreset(name="stay"))
    store.save_preset(CustomPreset(name="go"))
    store.delete_preset("go")

    data = json.loads(presets_path.read_text(encoding="utf-8"))
    assert all(d["name"] != "go" for d in data)


def test_delete_nonexistent_preset_is_noop(tmp_path: Path) -> None:
    """Deleting a name that does not exist does not raise and leaves the list intact."""
    with patch("rbcopy.presets._load_bundled_presets", return_value=[]):
        store = CustomPresetsStore(path=tmp_path / "presets.json")
    store.save_preset(CustomPreset(name="only"))
    store.delete_preset("ghost")
    assert len(store.presets) == 1


# ---------------------------------------------------------------------------
# CustomPresetsStore.get_preset
# ---------------------------------------------------------------------------


def test_get_preset_returns_matching_preset(tmp_path: Path) -> None:
    """get_preset returns the preset with the given name."""
    store = CustomPresetsStore(path=tmp_path / "presets.json")
    store.save_preset(CustomPreset(name="target", destination="/dest"))
    found = store.get_preset("target")
    assert found is not None
    assert found.destination == "/dest"


def test_get_preset_returns_none_when_missing(tmp_path: Path) -> None:
    """get_preset returns None when no preset matches the name."""
    store = CustomPresetsStore(path=tmp_path / "presets.json")
    assert store.get_preset("missing") is None


# ---------------------------------------------------------------------------
# CustomPresetsStore – persistence directory creation
# ---------------------------------------------------------------------------


def test_store_creates_parent_directory(tmp_path: Path) -> None:
    """save_preset creates the parent directory when it does not yet exist."""
    nested_path = tmp_path / "deep" / "nested" / "presets.json"
    with patch("rbcopy.presets._load_bundled_presets", return_value=[]):
        store = CustomPresetsStore(path=nested_path)
    store.save_preset(CustomPreset(name="x"))
    assert nested_path.exists()


# ---------------------------------------------------------------------------
# CustomPresetsStore – OS error handling
# ---------------------------------------------------------------------------


def test_store_logs_on_write_failure(tmp_path: Path) -> None:
    """_persist logs an exception and does not raise when write fails."""
    with patch("rbcopy.presets._load_bundled_presets", return_value=[]):
        store = CustomPresetsStore(path=tmp_path / "presets.json")
    with patch.object(Path, "write_text", side_effect=OSError("disk full")):
        # Should not raise; must return False to signal failure.
        result = store.save_preset(CustomPreset(name="oops"))
    assert result is False


# ---------------------------------------------------------------------------
# Built-in preset seeding
# ---------------------------------------------------------------------------


def test_store_seeds_from_bundled_presets_on_first_launch(tmp_path: Path) -> None:
    """When no user file exists, the store seeds itself from the bundled presets."""
    bundled = [
        CustomPreset(name="Mirror Sync"),
        CustomPreset(name="Safe Backup"),
    ]
    with patch("rbcopy.presets._load_bundled_presets", return_value=bundled):
        store = CustomPresetsStore(path=tmp_path / "presets.json")

    assert len(store.presets) == 2
    assert store.get_preset("Mirror Sync") is not None
    assert store.get_preset("Safe Backup") is not None


def test_store_persists_seeded_presets_to_disk(tmp_path: Path) -> None:
    """Seeded presets must be written to disk so subsequent launches load from file."""
    presets_path = tmp_path / "presets.json"
    bundled = [CustomPreset(name="Mirror Sync")]

    with patch("rbcopy.presets._load_bundled_presets", return_value=bundled):
        CustomPresetsStore(path=presets_path)

    assert presets_path.exists()
    data = json.loads(presets_path.read_text(encoding="utf-8"))
    assert any(d["name"] == "Mirror Sync" for d in data)


def test_store_does_not_reseed_when_user_file_exists(tmp_path: Path) -> None:
    """When a user file exists, user presets are preserved and new bundled presets are merged in.

    This verifies the update-safe merge: the user's own preset survives, while a
    bundled preset whose name is not yet in the user list is added alongside it.
    """
    presets_path = tmp_path / "presets.json"
    user_preset = CustomPreset(name="My Custom Preset")
    presets_path.write_text(json.dumps([user_preset.model_dump()]), encoding="utf-8")

    bundled = [CustomPreset(name="Mirror Sync")]
    with patch("rbcopy.presets._load_bundled_presets", return_value=bundled):
        store = CustomPresetsStore(path=presets_path)

    # User preset must be preserved.
    assert store.get_preset("My Custom Preset") is not None
    # New bundled preset is merged in for the updated application.
    assert store.get_preset("Mirror Sync") is not None
    assert len(store.presets) == 2


def test_store_starts_empty_when_bundled_presets_unavailable(tmp_path: Path) -> None:
    """If the bundled presets cannot be loaded, the store starts empty gracefully."""
    with patch("rbcopy.presets._load_bundled_presets", return_value=[]):
        store = CustomPresetsStore(path=tmp_path / "presets.json")

    assert store.presets == []


def test_load_bundled_presets_returns_list() -> None:
    """_load_bundled_presets must return a non-empty list from the real package file."""
    from rbcopy.presets import _load_bundled_presets

    result = _load_bundled_presets()
    assert isinstance(result, list)
    assert len(result) > 0
    assert all(isinstance(p, CustomPreset) for p in result)


def test_load_bundled_presets_returns_empty_on_bad_json(tmp_path: Path) -> None:
    """_load_bundled_presets must return [] when the resource cannot be parsed."""
    mock_file = MagicMock()
    mock_file.read_text.return_value = "not valid json"
    mock_files = MagicMock()
    mock_files.joinpath.return_value = mock_file

    with patch("rbcopy.presets.resources.files", return_value=mock_files):
        result = _load_bundled_presets()

    assert result == []


def test_load_bundled_presets_returns_empty_on_invalid_preset_data() -> None:
    """_load_bundled_presets must return [] when JSON is valid but preset data fails validation."""
    # An empty name violates the CustomPreset min_length=1 validator.
    invalid_data = json.dumps([{"name": "", "source": "", "destination": ""}])

    mock_file = MagicMock()
    mock_file.read_text.return_value = invalid_data
    mock_files = MagicMock()
    mock_files.joinpath.return_value = mock_file

    with patch("rbcopy.presets.resources.files", return_value=mock_files):
        result = _load_bundled_presets()

    assert result == []


def test_load_bundled_presets_returns_empty_on_oserror() -> None:
    """_load_bundled_presets must return [] when reading the bundled file raises OSError."""
    mock_file = MagicMock()
    mock_file.read_text.side_effect = OSError("resource not accessible")
    mock_files = MagicMock()
    mock_files.joinpath.return_value = mock_file

    with patch("rbcopy.presets.resources.files", return_value=mock_files):
        result = _load_bundled_presets()

    assert result == []


def test_store_no_persist_when_bundled_empty_and_user_file_exists(tmp_path: Path) -> None:
    """No disk write occurs during merge when _load_bundled_presets returns empty.

    When bundled is empty, _merge_bundled_updates calculates new_bundled=[]
    and returns early without calling _persist(), so the file must not be touched.
    """
    presets_path = tmp_path / "presets.json"
    existing = CustomPreset(name="User Preset")
    presets_path.write_text(json.dumps([existing.model_dump()]), encoding="utf-8")

    with patch("rbcopy.presets._load_bundled_presets", return_value=[]):
        with patch.object(Path, "write_text") as mock_write:
            CustomPresetsStore(path=presets_path)

    mock_write.assert_not_called()
