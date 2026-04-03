"""Tests for rbcopy.preferences and the _PreferencesDialog."""

from __future__ import annotations

import json
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from rbcopy.preferences import AppPreferences, PreferencesStore


# ---------------------------------------------------------------------------
# AppPreferences – defaults
# ---------------------------------------------------------------------------


def test_app_preferences_default_thread_count() -> None:
    assert AppPreferences().default_thread_count == 8


def test_app_preferences_default_retry_count() -> None:
    assert AppPreferences().default_retry_count == 5


def test_app_preferences_default_wait_seconds() -> None:
    assert AppPreferences().default_wait_seconds == 30


def test_app_preferences_default_log_retention_count() -> None:
    assert AppPreferences().log_retention_count == 20


# ---------------------------------------------------------------------------
# AppPreferences – boundary validation
# ---------------------------------------------------------------------------


def test_app_preferences_accepts_min_thread_count() -> None:
    assert AppPreferences(default_thread_count=1).default_thread_count == 1


def test_app_preferences_accepts_max_thread_count() -> None:
    assert AppPreferences(default_thread_count=128).default_thread_count == 128


def test_app_preferences_rejects_thread_count_below_min() -> None:
    with pytest.raises(ValidationError):
        AppPreferences(default_thread_count=0)


def test_app_preferences_rejects_thread_count_above_max() -> None:
    with pytest.raises(ValidationError):
        AppPreferences(default_thread_count=129)


def test_app_preferences_accepts_zero_retry_count() -> None:
    assert AppPreferences(default_retry_count=0).default_retry_count == 0


def test_app_preferences_rejects_negative_retry_count() -> None:
    with pytest.raises(ValidationError):
        AppPreferences(default_retry_count=-1)


def test_app_preferences_accepts_zero_wait_seconds() -> None:
    assert AppPreferences(default_wait_seconds=0).default_wait_seconds == 0


def test_app_preferences_rejects_wait_seconds_above_max() -> None:
    with pytest.raises(ValidationError):
        AppPreferences(default_wait_seconds=3601)


def test_app_preferences_accepts_min_log_retention() -> None:
    assert AppPreferences(log_retention_count=1).log_retention_count == 1


def test_app_preferences_rejects_zero_log_retention() -> None:
    with pytest.raises(ValidationError):
        AppPreferences(log_retention_count=0)


def test_app_preferences_accepts_max_log_retention() -> None:
    assert AppPreferences(log_retention_count=1000).log_retention_count == 1000


def test_app_preferences_rejects_log_retention_above_max() -> None:
    with pytest.raises(ValidationError):
        AppPreferences(log_retention_count=1001)


# ---------------------------------------------------------------------------
# AppPreferences – round-trip JSON
# ---------------------------------------------------------------------------


def test_app_preferences_round_trips_json() -> None:
    original = AppPreferences(
        default_thread_count=16,
        default_retry_count=3,
        default_wait_seconds=5,
        log_retention_count=50,
    )
    restored = AppPreferences.model_validate(original.model_dump())
    assert restored == original


# ---------------------------------------------------------------------------
# PreferencesStore – construction / loading
# ---------------------------------------------------------------------------


def test_store_uses_defaults_when_file_missing(tmp_path: Path) -> None:
    """A new store with no existing file starts with factory defaults."""
    store = PreferencesStore(path=tmp_path / "prefs.json")
    prefs = store.preferences
    assert prefs == AppPreferences()


def test_store_loads_existing_file(tmp_path: Path) -> None:
    """Preferences written to disk are loaded on construction."""
    prefs_path = tmp_path / "prefs.json"
    saved = AppPreferences(default_thread_count=32, log_retention_count=5)
    prefs_path.write_text(json.dumps(saved.model_dump(), indent=2), encoding="utf-8")

    store = PreferencesStore(path=prefs_path)
    loaded = store.preferences

    assert loaded.default_thread_count == 32
    assert loaded.log_retention_count == 5


def test_store_uses_defaults_on_corrupt_file(tmp_path: Path) -> None:
    """A corrupt JSON file is silently ignored; defaults are used instead."""
    prefs_path = tmp_path / "prefs.json"
    prefs_path.write_text("not valid json", encoding="utf-8")

    store = PreferencesStore(path=prefs_path)
    assert store.preferences == AppPreferences()


def test_store_uses_defaults_on_partial_file(tmp_path: Path) -> None:
    """A file with only some fields uses defaults for the rest."""
    prefs_path = tmp_path / "prefs.json"
    prefs_path.write_text(json.dumps({"default_thread_count": 64}), encoding="utf-8")

    store = PreferencesStore(path=prefs_path)
    prefs = store.preferences

    assert prefs.default_thread_count == 64
    assert prefs.default_retry_count == 5  # default


# ---------------------------------------------------------------------------
# PreferencesStore – save
# ---------------------------------------------------------------------------


def test_store_save_returns_true_on_success(tmp_path: Path) -> None:
    store = PreferencesStore(path=tmp_path / "prefs.json")
    result = store.save(AppPreferences(default_thread_count=16))
    assert result is True


def test_store_save_persists_to_disk(tmp_path: Path) -> None:
    prefs_path = tmp_path / "prefs.json"
    store = PreferencesStore(path=prefs_path)
    store.save(AppPreferences(default_thread_count=16, log_retention_count=10))

    data = json.loads(prefs_path.read_text(encoding="utf-8"))
    assert data["default_thread_count"] == 16
    assert data["log_retention_count"] == 10


def test_store_save_updates_in_memory_preferences(tmp_path: Path) -> None:
    store = PreferencesStore(path=tmp_path / "prefs.json")
    new_prefs = AppPreferences(default_thread_count=64)
    store.save(new_prefs)
    assert store.preferences.default_thread_count == 64


def test_store_save_returns_false_on_disk_failure(tmp_path: Path) -> None:
    store = PreferencesStore(path=tmp_path / "prefs.json")

    with patch.object(Path, "write_text", side_effect=OSError("disk full")):
        result = store.save(AppPreferences(default_thread_count=16))

    assert result is False


def test_store_save_rolls_back_on_disk_failure(tmp_path: Path) -> None:
    """When save fails the in-memory preferences are reverted."""
    store = PreferencesStore(path=tmp_path / "prefs.json")
    original_count = store.preferences.default_thread_count

    with patch.object(Path, "write_text", side_effect=OSError("disk full")):
        store.save(AppPreferences(default_thread_count=64))

    assert store.preferences.default_thread_count == original_count


def test_store_save_in_memory_consistent_with_disk_after_failure(tmp_path: Path) -> None:
    """After a failed save, reloading from disk matches the in-memory state."""
    prefs_path = tmp_path / "prefs.json"
    store = PreferencesStore(path=prefs_path)
    store.save(AppPreferences(default_thread_count=8))  # successful first save

    with patch.object(Path, "write_text", side_effect=OSError("disk full")):
        store.save(AppPreferences(default_thread_count=64))  # this must be rolled back

    reloaded = PreferencesStore(path=prefs_path)
    assert store.preferences == reloaded.preferences


def test_store_save_creates_parent_directory(tmp_path: Path) -> None:
    """save creates the parent directory if it does not already exist."""
    nested_path = tmp_path / "deep" / "nested" / "prefs.json"
    store = PreferencesStore(path=nested_path)
    store.save(AppPreferences())
    assert nested_path.exists()


# ---------------------------------------------------------------------------
# PreferencesStore – preferences property returns a copy
# ---------------------------------------------------------------------------


def test_store_preferences_returns_copy(tmp_path: Path) -> None:
    """Mutating the returned preferences object must not affect the store."""
    store = PreferencesStore(path=tmp_path / "prefs.json")
    prefs = store.preferences
    # Pydantic models are immutable by default, but we verify model_copy semantics.
    assert prefs is not store.preferences


# ---------------------------------------------------------------------------
# _PreferencesDialog._on_save – happy path
# ---------------------------------------------------------------------------


def _make_fake_dialog(tmp_path: Path) -> MagicMock:
    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake: MagicMock = MagicMock()
    fake._store = PreferencesStore(path=tmp_path / "prefs.json")
    fake._on_saved = MagicMock()
    fake._saved = False
    fake._thread_var.get.return_value = "8"
    fake._retry_var.get.return_value = "5"
    fake._wait_var.get.return_value = "30"
    fake._log_var.get.return_value = "20"
    fake._THREAD_MIN = _PreferencesDialog._THREAD_MIN
    fake._THREAD_MAX = _PreferencesDialog._THREAD_MAX
    fake._RETRY_MIN = _PreferencesDialog._RETRY_MIN
    fake._RETRY_MAX = _PreferencesDialog._RETRY_MAX
    fake._WAIT_MIN = _PreferencesDialog._WAIT_MIN
    fake._WAIT_MAX = _PreferencesDialog._WAIT_MAX
    fake._LOG_MIN = _PreferencesDialog._LOG_MIN
    fake._LOG_MAX = _PreferencesDialog._LOG_MAX
    # Bind the real _parse_int so validation actually executes.
    # Without this, fake._parse_int() returns a MagicMock (truthy),
    # so _on_save never sees a None return and skips all validation.
    fake._parse_int = types.MethodType(_PreferencesDialog._parse_int, fake)
    return fake


def test_on_save_persists_valid_preferences(tmp_path: Path) -> None:
    """_on_save writes valid preferences to disk."""
    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake = _make_fake_dialog(tmp_path)
    fake._thread_var.get.return_value = "16"
    fake._log_var.get.return_value = "10"

    with patch("rbcopy.gui.preferences_dialog.messagebox.showinfo", create=True):
        _PreferencesDialog._on_save(fake)

    reloaded = PreferencesStore(path=tmp_path / "prefs.json")
    assert reloaded.preferences.default_thread_count == 16
    assert reloaded.preferences.log_retention_count == 10


def test_on_save_sets_saved_flag_on_success(tmp_path: Path) -> None:
    """_on_save sets self._saved = True when all fields are valid."""
    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake = _make_fake_dialog(tmp_path)
    _PreferencesDialog._on_save(fake)
    assert fake._saved is True


def test_on_save_calls_on_saved_callback(tmp_path: Path) -> None:
    """_on_save invokes the on_saved callback after a successful save."""
    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake = _make_fake_dialog(tmp_path)
    _PreferencesDialog._on_save(fake)
    fake._on_saved.assert_called_once()


def test_on_save_destroys_dialog_on_success(tmp_path: Path) -> None:
    """_on_save calls destroy() after a successful save."""
    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake = _make_fake_dialog(tmp_path)
    _PreferencesDialog._on_save(fake)
    fake.destroy.assert_called_once()


# ---------------------------------------------------------------------------
# _PreferencesDialog._on_save – thread count validation
# ---------------------------------------------------------------------------


def test_on_save_shows_warning_on_non_numeric_thread_count(tmp_path: Path) -> None:
    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake = _make_fake_dialog(tmp_path)
    fake._thread_var.get.return_value = "abc"

    with patch("rbcopy.gui.preferences_dialog.messagebox.showwarning") as mock_warn:
        _PreferencesDialog._on_save(fake)

    mock_warn.assert_called_once()
    assert fake._saved is False


def test_on_save_shows_warning_on_thread_count_too_low(tmp_path: Path) -> None:
    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake = _make_fake_dialog(tmp_path)
    fake._thread_var.get.return_value = "0"

    with patch("rbcopy.gui.preferences_dialog.messagebox.showwarning") as mock_warn:
        _PreferencesDialog._on_save(fake)

    mock_warn.assert_called_once()
    assert fake._saved is False


def test_on_save_shows_warning_on_thread_count_too_high(tmp_path: Path) -> None:
    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake = _make_fake_dialog(tmp_path)
    fake._thread_var.get.return_value = "129"

    with patch("rbcopy.gui.preferences_dialog.messagebox.showwarning") as mock_warn:
        _PreferencesDialog._on_save(fake)

    mock_warn.assert_called_once()
    assert fake._saved is False


# ---------------------------------------------------------------------------
# _PreferencesDialog._on_save – retry count validation
# ---------------------------------------------------------------------------


def test_on_save_shows_warning_on_non_numeric_retry_count(tmp_path: Path) -> None:
    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake = _make_fake_dialog(tmp_path)
    fake._retry_var.get.return_value = "five"

    with patch("rbcopy.gui.preferences_dialog.messagebox.showwarning") as mock_warn:
        _PreferencesDialog._on_save(fake)

    mock_warn.assert_called_once()
    assert fake._saved is False


def test_on_save_shows_warning_on_negative_retry_count(tmp_path: Path) -> None:
    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake = _make_fake_dialog(tmp_path)
    fake._retry_var.get.return_value = "-1"

    with patch("rbcopy.gui.preferences_dialog.messagebox.showwarning") as mock_warn:
        _PreferencesDialog._on_save(fake)

    mock_warn.assert_called_once()
    assert fake._saved is False


# ---------------------------------------------------------------------------
# _PreferencesDialog._on_save – wait seconds validation
# ---------------------------------------------------------------------------


def test_on_save_shows_warning_on_non_numeric_wait_seconds(tmp_path: Path) -> None:
    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake = _make_fake_dialog(tmp_path)
    fake._wait_var.get.return_value = "1.5"

    with patch("rbcopy.gui.preferences_dialog.messagebox.showwarning") as mock_warn:
        _PreferencesDialog._on_save(fake)

    mock_warn.assert_called_once()
    assert fake._saved is False


def test_on_save_shows_warning_on_wait_seconds_above_max(tmp_path: Path) -> None:
    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake = _make_fake_dialog(tmp_path)
    fake._wait_var.get.return_value = "3601"

    with patch("rbcopy.gui.preferences_dialog.messagebox.showwarning") as mock_warn:
        _PreferencesDialog._on_save(fake)

    mock_warn.assert_called_once()
    assert fake._saved is False


# ---------------------------------------------------------------------------
# _PreferencesDialog._on_save – log retention validation
# ---------------------------------------------------------------------------


def test_on_save_shows_warning_on_non_numeric_log_retention(tmp_path: Path) -> None:
    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake = _make_fake_dialog(tmp_path)
    fake._log_var.get.return_value = ""

    with patch("rbcopy.gui.preferences_dialog.messagebox.showwarning") as mock_warn:
        _PreferencesDialog._on_save(fake)

    mock_warn.assert_called_once()
    assert fake._saved is False


def test_on_save_shows_warning_on_log_retention_zero(tmp_path: Path) -> None:
    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake = _make_fake_dialog(tmp_path)
    fake._log_var.get.return_value = "0"

    with patch("rbcopy.gui.preferences_dialog.messagebox.showwarning") as mock_warn:
        _PreferencesDialog._on_save(fake)

    mock_warn.assert_called_once()
    assert fake._saved is False


def test_on_save_shows_warning_on_log_retention_above_max(tmp_path: Path) -> None:
    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake = _make_fake_dialog(tmp_path)
    fake._log_var.get.return_value = "1001"

    with patch("rbcopy.gui.preferences_dialog.messagebox.showwarning") as mock_warn:
        _PreferencesDialog._on_save(fake)

    mock_warn.assert_called_once()
    assert fake._saved is False


# ---------------------------------------------------------------------------
# _PreferencesDialog._on_save – disk failure
# ---------------------------------------------------------------------------


def test_on_save_shows_error_on_disk_failure(tmp_path: Path) -> None:
    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake = _make_fake_dialog(tmp_path)

    with patch.object(Path, "write_text", side_effect=OSError("disk full")):
        with patch("rbcopy.gui.preferences_dialog.messagebox.showerror") as mock_err:
            _PreferencesDialog._on_save(fake)

    mock_err.assert_called_once()
    assert fake._saved is False


def test_on_save_does_not_call_on_saved_on_disk_failure(tmp_path: Path) -> None:
    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake = _make_fake_dialog(tmp_path)

    with patch.object(Path, "write_text", side_effect=OSError("disk full")):
        with patch("rbcopy.gui.preferences_dialog.messagebox.showerror"):
            _PreferencesDialog._on_save(fake)

    fake._on_saved.assert_not_called()


def test_on_save_does_not_destroy_on_disk_failure(tmp_path: Path) -> None:
    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake = _make_fake_dialog(tmp_path)

    with patch.object(Path, "write_text", side_effect=OSError("disk full")):
        with patch("rbcopy.gui.preferences_dialog.messagebox.showerror"):
            _PreferencesDialog._on_save(fake)

    fake.destroy.assert_not_called()


# ---------------------------------------------------------------------------
# _PreferencesDialog._on_save – only one warning shown per validation failure
# ---------------------------------------------------------------------------


def test_on_save_stops_after_first_invalid_field(tmp_path: Path) -> None:
    """_on_save must show exactly one warning and stop when thread count is invalid."""
    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake = _make_fake_dialog(tmp_path)
    fake._thread_var.get.return_value = "bad"
    fake._retry_var.get.return_value = "also_bad"

    with patch("rbcopy.gui.preferences_dialog.messagebox.showwarning") as mock_warn:
        _PreferencesDialog._on_save(fake)

    assert mock_warn.call_count == 1


# ---------------------------------------------------------------------------
# Gap 15: _PreferencesDialog._on_reset_history / _on_reset_bookmarks
# ---------------------------------------------------------------------------


def _make_fake_dialog_with_callbacks(tmp_path: Path) -> MagicMock:
    """Return a fake _PreferencesDialog with reset callbacks attached."""
    import types

    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake: MagicMock = MagicMock()
    fake._store = PreferencesStore(path=tmp_path / "prefs.json")
    fake._on_clear_history = MagicMock()
    fake._on_clear_bookmarks = MagicMock()
    # Bind the real reset methods so they actually execute.
    fake._on_reset_history = types.MethodType(_PreferencesDialog._on_reset_history, fake)
    fake._on_reset_bookmarks = types.MethodType(_PreferencesDialog._on_reset_bookmarks, fake)
    return fake


def test_on_reset_history_calls_clear_history_when_confirmed(tmp_path: Path) -> None:
    """_on_reset_history invokes on_clear_history when the user confirms."""
    fake = _make_fake_dialog_with_callbacks(tmp_path)

    with (
        patch("rbcopy.gui.preferences_dialog.messagebox.askyesno", return_value=True),
        patch("rbcopy.gui.preferences_dialog.messagebox.showinfo"),
    ):
        fake._on_reset_history()

    fake._on_clear_history.assert_called_once()


def test_on_reset_history_shows_info_after_clearing(tmp_path: Path) -> None:
    """_on_reset_history shows a success info dialog after clearing path history."""
    fake = _make_fake_dialog_with_callbacks(tmp_path)

    with (
        patch("rbcopy.gui.preferences_dialog.messagebox.askyesno", return_value=True),
        patch("rbcopy.gui.preferences_dialog.messagebox.showinfo") as mock_info,
    ):
        fake._on_reset_history()

    mock_info.assert_called_once()


def test_on_reset_history_does_not_clear_when_cancelled(tmp_path: Path) -> None:
    """_on_reset_history does nothing when the user cancels the confirmation dialog."""
    fake = _make_fake_dialog_with_callbacks(tmp_path)

    with patch("rbcopy.gui.preferences_dialog.messagebox.askyesno", return_value=False):
        fake._on_reset_history()

    fake._on_clear_history.assert_not_called()


def test_on_reset_history_noop_when_callback_is_none() -> None:
    """_on_reset_history is a no-op when _on_clear_history is None."""
    import types

    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake: MagicMock = MagicMock()
    fake._on_clear_history = None
    fake._on_reset_history = types.MethodType(_PreferencesDialog._on_reset_history, fake)

    # Must not raise.
    fake._on_reset_history()


def test_on_reset_bookmarks_calls_clear_bookmarks_when_confirmed(tmp_path: Path) -> None:
    """_on_reset_bookmarks invokes on_clear_bookmarks when the user confirms."""
    fake = _make_fake_dialog_with_callbacks(tmp_path)

    with (
        patch("rbcopy.gui.preferences_dialog.messagebox.askyesno", return_value=True),
        patch("rbcopy.gui.preferences_dialog.messagebox.showinfo"),
    ):
        fake._on_reset_bookmarks()

    fake._on_clear_bookmarks.assert_called_once()


def test_on_reset_bookmarks_shows_info_after_clearing(tmp_path: Path) -> None:
    """_on_reset_bookmarks shows a success info dialog after clearing bookmarks."""
    fake = _make_fake_dialog_with_callbacks(tmp_path)

    with (
        patch("rbcopy.gui.preferences_dialog.messagebox.askyesno", return_value=True),
        patch("rbcopy.gui.preferences_dialog.messagebox.showinfo") as mock_info,
    ):
        fake._on_reset_bookmarks()

    mock_info.assert_called_once()


def test_on_reset_bookmarks_does_not_clear_when_cancelled(tmp_path: Path) -> None:
    """_on_reset_bookmarks does nothing when the user cancels the confirmation dialog."""
    fake = _make_fake_dialog_with_callbacks(tmp_path)

    with patch("rbcopy.gui.preferences_dialog.messagebox.askyesno", return_value=False):
        fake._on_reset_bookmarks()

    fake._on_clear_bookmarks.assert_not_called()


def test_on_reset_bookmarks_noop_when_callback_is_none() -> None:
    """_on_reset_bookmarks is a no-op when _on_clear_bookmarks is None."""
    import types

    from rbcopy.gui.preferences_dialog import _PreferencesDialog

    fake: MagicMock = MagicMock()
    fake._on_clear_bookmarks = None
    fake._on_reset_bookmarks = types.MethodType(_PreferencesDialog._on_reset_bookmarks, fake)

    # Must not raise.
    fake._on_reset_bookmarks()
