"""Tests for rbcopy.gui.dnd – drag-and-drop path entry utilities."""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable
from unittest.mock import MagicMock, patch

import pytest

from rbcopy.gui.dnd import (
    _DND_ACTIVE_STYLE,
    _DND_DEFAULT_STYLE,
    _apply_hover_style,
    _restore_style,
    parse_drop_data,
    setup_entry_drop,
)


# ---------------------------------------------------------------------------
# parse_drop_data – parametrised edge cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "data,expected",
    [
        # Empty / whitespace-only
        ("", ""),
        ("   ", ""),
        # Simple unquoted path
        ("C:/Users/test", "C:/Users/test"),
        # Single brace-quoted path (contains spaces)
        ("{C:/Users/my folder}", "C:/Users/my folder"),
        # Multiple paths – only the first is returned
        ("C:/path1 C:/path2", "C:/path1"),
        ("{C:/path one} C:/path2", "C:/path one"),
        # Leading/trailing whitespace is stripped before parsing
        ("  C:/leading/space  ", "C:/leading/space"),
        # Malformed: opening brace only → empty string
        ("{", ""),
        # Malformed: no closing brace → content after opening brace
        ("{no closing", "no closing"),
    ],
)
def test_parse_drop_data(data: str, expected: str) -> None:
    """parse_drop_data returns the first path for a variety of input formats."""
    assert parse_drop_data(data) == expected


def test_parse_drop_data_windows_backslash() -> None:
    """parse_drop_data handles Windows-style backslash paths correctly."""
    assert parse_drop_data(r"C:\Users\test") == r"C:\Users\test"


def test_parse_drop_data_windows_backslash_with_spaces() -> None:
    """parse_drop_data unwraps brace-quoted Windows paths with spaces."""
    assert parse_drop_data(r"{C:\Users\my folder}") == r"C:\Users\my folder"


def test_parse_drop_data_unc_path() -> None:
    """parse_drop_data returns UNC paths unmodified when they have no spaces."""
    assert parse_drop_data(r"\\server\share\folder") == r"\\server\share\folder"


def test_parse_drop_data_unc_path_with_spaces() -> None:
    """parse_drop_data unwraps brace-quoted UNC paths that contain spaces."""
    assert parse_drop_data(r"{\\server\my share\folder}") == r"\\server\my share\folder"


# ---------------------------------------------------------------------------
# setup_entry_drop – tkinterdnd2 not available
# ---------------------------------------------------------------------------


def test_setup_entry_drop_returns_false_when_no_tkinterdnd2() -> None:
    """setup_entry_drop returns False when tkinterdnd2 is not installed."""
    entry = MagicMock()
    var = MagicMock(spec=tk.StringVar)

    with patch.dict("sys.modules", {"tkinterdnd2": None}):
        result = setup_entry_drop(entry, var)

    assert result is False


def test_setup_entry_drop_does_not_call_register_when_no_tkinterdnd2() -> None:
    """setup_entry_drop never calls drop_target_register when the library is absent."""
    entry = MagicMock()
    var = MagicMock(spec=tk.StringVar)

    with patch.dict("sys.modules", {"tkinterdnd2": None}):
        setup_entry_drop(entry, var)

    entry.drop_target_register.assert_not_called()


# ---------------------------------------------------------------------------
# setup_entry_drop – registration failures
# ---------------------------------------------------------------------------


def test_setup_entry_drop_returns_false_on_tclerror() -> None:
    """setup_entry_drop returns False when drop_target_register raises TclError."""
    entry = MagicMock()
    entry.drop_target_register.side_effect = tk.TclError("not available")
    var = MagicMock(spec=tk.StringVar)
    mock_tkinterdnd2 = MagicMock()

    with patch.dict("sys.modules", {"tkinterdnd2": mock_tkinterdnd2}):
        result = setup_entry_drop(entry, var)

    assert result is False


def test_setup_entry_drop_returns_false_on_attribute_error() -> None:
    """setup_entry_drop returns False when the entry lacks the DnD methods."""
    entry = MagicMock()
    entry.drop_target_register.side_effect = AttributeError("no such method")
    var = MagicMock(spec=tk.StringVar)
    mock_tkinterdnd2 = MagicMock()

    with patch.dict("sys.modules", {"tkinterdnd2": mock_tkinterdnd2}):
        result = setup_entry_drop(entry, var)

    assert result is False


# ---------------------------------------------------------------------------
# setup_entry_drop – successful registration
# ---------------------------------------------------------------------------


def test_setup_entry_drop_returns_true_on_success() -> None:
    """setup_entry_drop returns True when registration completes without error."""
    entry = MagicMock()
    var = MagicMock(spec=tk.StringVar)
    mock_tkinterdnd2 = MagicMock()

    with patch.dict("sys.modules", {"tkinterdnd2": mock_tkinterdnd2}):
        result = setup_entry_drop(entry, var)

    assert result is True


def test_setup_entry_drop_registers_with_dnd_files() -> None:
    """setup_entry_drop passes DND_FILES to drop_target_register."""
    entry = MagicMock()
    var = MagicMock(spec=tk.StringVar)
    sentinel = object()
    mock_tkinterdnd2 = MagicMock()
    mock_tkinterdnd2.DND_FILES = sentinel

    with patch.dict("sys.modules", {"tkinterdnd2": mock_tkinterdnd2}):
        setup_entry_drop(entry, var)

    entry.drop_target_register.assert_called_once_with(sentinel)


def test_setup_entry_drop_binds_drop_event() -> None:
    """setup_entry_drop binds the <<Drop>> event."""
    entry = MagicMock()
    var = MagicMock(spec=tk.StringVar)
    mock_tkinterdnd2 = MagicMock()

    with patch.dict("sys.modules", {"tkinterdnd2": mock_tkinterdnd2}):
        setup_entry_drop(entry, var)

    bound_events = {call.args[0] for call in entry.dnd_bind.call_args_list}
    assert "<<Drop>>" in bound_events


def test_setup_entry_drop_binds_drag_enter_event() -> None:
    """setup_entry_drop binds the <<DragEnter>> event."""
    entry = MagicMock()
    var = MagicMock(spec=tk.StringVar)
    mock_tkinterdnd2 = MagicMock()

    with patch.dict("sys.modules", {"tkinterdnd2": mock_tkinterdnd2}):
        setup_entry_drop(entry, var)

    bound_events = {call.args[0] for call in entry.dnd_bind.call_args_list}
    assert "<<DragEnter>>" in bound_events


def test_setup_entry_drop_binds_drag_leave_event() -> None:
    """setup_entry_drop binds the <<DragLeave>> event."""
    entry = MagicMock()
    var = MagicMock(spec=tk.StringVar)
    mock_tkinterdnd2 = MagicMock()

    with patch.dict("sys.modules", {"tkinterdnd2": mock_tkinterdnd2}):
        setup_entry_drop(entry, var)

    bound_events = {call.args[0] for call in entry.dnd_bind.call_args_list}
    assert "<<DragLeave>>" in bound_events


# ---------------------------------------------------------------------------
# Callback extraction helper
# ---------------------------------------------------------------------------


def _make_mock_entry(widget_class: str = "TEntry") -> MagicMock:
    """Return a MagicMock that behaves like a ttk.Entry/Combobox for DnD purposes.

    ``cget("style")`` returns ``""`` (no explicit style, so winfo_class() is used),
    ``cget("state")`` returns ``"normal"``, and ``winfo_class()`` returns
    *widget_class*.
    """
    entry = MagicMock()
    entry.cget.side_effect = lambda key: "" if key == "style" else "normal"
    entry.winfo_class.return_value = widget_class
    return entry


def _register_and_get_callback(event_name: str) -> tuple[MagicMock, MagicMock, Callable[..., Any]]:
    """Register DnD on a fresh entry/var pair and return (entry, var, callback).

    The returned callback is the one bound to *event_name*.
    """
    entry = _make_mock_entry()
    var = MagicMock(spec=tk.StringVar)
    mock_tkinterdnd2 = MagicMock()

    with patch.dict("sys.modules", {"tkinterdnd2": mock_tkinterdnd2}):
        setup_entry_drop(entry, var)

    for call in entry.dnd_bind.call_args_list:
        if call.args[0] == event_name:
            return entry, var, call.args[1]

    raise AssertionError(f"No callback found for event {event_name!r}")


# ---------------------------------------------------------------------------
# <<Drop>> callback behaviour
# ---------------------------------------------------------------------------


def test_drop_callback_sets_string_var() -> None:
    """The <<Drop>> callback writes the dropped path to string_var."""
    entry, var, callback = _register_and_get_callback("<<Drop>>")
    # Default cget("state") returns a MagicMock which != "disabled" → proceeds.
    event = MagicMock()
    event.data = "C:/Users/test"
    callback(event)
    var.set.assert_called_once_with("C:/Users/test")


def test_drop_callback_ignores_empty_data() -> None:
    """The <<Drop>> callback does nothing when dropped data is empty."""
    entry, var, callback = _register_and_get_callback("<<Drop>>")
    event = MagicMock()
    event.data = ""
    callback(event)
    var.set.assert_not_called()


def test_drop_callback_ignores_whitespace_data() -> None:
    """The <<Drop>> callback does nothing when dropped data is only whitespace."""
    entry, var, callback = _register_and_get_callback("<<Drop>>")
    event = MagicMock()
    event.data = "   "
    callback(event)
    var.set.assert_not_called()


def test_drop_callback_unwraps_braced_path() -> None:
    """The <<Drop>> callback strips curly-brace quoting from paths with spaces."""
    entry, var, callback = _register_and_get_callback("<<Drop>>")
    event = MagicMock()
    event.data = "{C:/Users/my folder}"
    callback(event)
    var.set.assert_called_once_with("C:/Users/my folder")


def test_drop_callback_takes_first_of_multiple_paths() -> None:
    """The <<Drop>> callback uses only the first path when multiple are dropped."""
    entry, var, callback = _register_and_get_callback("<<Drop>>")
    event = MagicMock()
    event.data = "C:/path1 C:/path2 C:/path3"
    callback(event)
    var.set.assert_called_once_with("C:/path1")


def test_drop_callback_restores_style_after_drop() -> None:
    """The <<Drop>> callback clears the hover highlight regardless of data content."""
    entry, var, callback = _register_and_get_callback("<<Drop>>")
    event = MagicMock()
    event.data = "C:/test"
    callback(event)
    styles_applied = [c.kwargs.get("style") for c in entry.configure.call_args_list]
    assert _DND_DEFAULT_STYLE in styles_applied


def test_drop_callback_restores_style_even_on_empty_data() -> None:
    """The <<Drop>> callback clears the hover highlight even when data is empty."""
    entry, var, callback = _register_and_get_callback("<<Drop>>")
    event = MagicMock()
    event.data = ""
    callback(event)
    styles_applied = [c.kwargs.get("style") for c in entry.configure.call_args_list]
    assert _DND_DEFAULT_STYLE in styles_applied


def test_drop_callback_skips_disabled_entry() -> None:
    """The <<Drop>> callback does not update string_var when the entry is disabled."""
    entry, var, callback = _register_and_get_callback("<<Drop>>")
    # Override the side_effect so the state check inside _on_drop sees "disabled".
    entry.cget.side_effect = lambda key: "disabled"
    event = MagicMock()
    event.data = "C:/some/path"
    callback(event)
    var.set.assert_not_called()


def test_drop_callback_proceeds_when_entry_is_normal() -> None:
    """The <<Drop>> callback updates string_var when the entry state is 'normal'."""
    entry, var, callback = _register_and_get_callback("<<Drop>>")
    # Default side_effect already returns "normal" for the "state" key.
    event = MagicMock()
    event.data = "C:/some/path"
    callback(event)
    var.set.assert_called_once_with("C:/some/path")


def test_drop_callback_handles_tclerror_from_cget() -> None:
    """The <<Drop>> callback returns silently if cget raises TclError."""
    entry, var, callback = _register_and_get_callback("<<Drop>>")
    entry.cget.side_effect = tk.TclError("widget gone")
    event = MagicMock()
    event.data = "C:/test"
    callback(event)  # Must not raise.
    var.set.assert_not_called()


# ---------------------------------------------------------------------------
# <<DragEnter>> and <<DragLeave>> callback behaviour
# ---------------------------------------------------------------------------


def test_drag_enter_callback_applies_hover_style() -> None:
    """The <<DragEnter>> callback applies the DnD active style to the entry."""
    entry, _, callback = _register_and_get_callback("<<DragEnter>>")
    callback(MagicMock())
    entry.configure.assert_called_with(style=_DND_ACTIVE_STYLE)


def test_drag_leave_callback_restores_default_style() -> None:
    """The <<DragLeave>> callback restores the default entry style."""
    entry, _, callback = _register_and_get_callback("<<DragLeave>>")
    callback(MagicMock())
    entry.configure.assert_called_with(style=_DND_DEFAULT_STYLE)


# ---------------------------------------------------------------------------
# Style helper functions
# ---------------------------------------------------------------------------


def test_apply_hover_style_sets_active_style() -> None:
    """_apply_hover_style configures the entry with the DnD active style name."""
    entry = MagicMock()
    _apply_hover_style(entry)
    entry.configure.assert_called_once_with(style=_DND_ACTIVE_STYLE)


def test_restore_style_sets_default_style() -> None:
    """_restore_style configures the entry with the standard TEntry style name."""
    entry = MagicMock()
    _restore_style(entry)
    entry.configure.assert_called_once_with(style=_DND_DEFAULT_STYLE)


def test_apply_hover_style_swallows_tclerror() -> None:
    """_apply_hover_style does not propagate TclError when the widget is gone."""
    entry = MagicMock()
    entry.configure.side_effect = tk.TclError("invalid command name")
    _apply_hover_style(entry)  # Must not raise.


def test_restore_style_swallows_tclerror() -> None:
    """_restore_style does not propagate TclError when the widget is gone."""
    entry = MagicMock()
    entry.configure.side_effect = tk.TclError("invalid command name")
    _restore_style(entry)  # Must not raise.


# ---------------------------------------------------------------------------
# Combobox-specific style behaviour
# ---------------------------------------------------------------------------


def _register_combobox_and_get_callback(
    event_name: str,
) -> tuple[MagicMock, MagicMock, Callable[..., Any]]:
    """Like _register_and_get_callback but simulates a ttk.Combobox widget."""
    entry = _make_mock_entry(widget_class="TCombobox")
    var = MagicMock(spec=tk.StringVar)
    mock_tkinterdnd2 = MagicMock()

    with patch.dict("sys.modules", {"tkinterdnd2": mock_tkinterdnd2}):
        setup_entry_drop(entry, var)

    for call in entry.dnd_bind.call_args_list:
        if call.args[0] == event_name:
            return entry, var, call.args[1]

    raise AssertionError(f"No callback found for event {event_name!r}")


def test_drop_callback_restores_combobox_style() -> None:
    """A drop on a Combobox restores TCombobox style, not the TEntry default."""
    entry, var, callback = _register_combobox_and_get_callback("<<Drop>>")
    entry.configure.reset_mock()
    event = MagicMock()
    event.data = "C:/test"
    callback(event)
    styles_applied = [c.kwargs.get("style") for c in entry.configure.call_args_list]
    assert "TCombobox" in styles_applied
    assert _DND_DEFAULT_STYLE not in styles_applied


def test_drag_enter_combobox_applies_combobox_hover_style() -> None:
    """<<DragEnter>> on a Combobox uses the DnDActive.TCombobox style."""
    entry, _, callback = _register_combobox_and_get_callback("<<DragEnter>>")
    entry.configure.reset_mock()
    callback(MagicMock())
    entry.configure.assert_called_with(style="DnDActive.TCombobox")


def test_drag_leave_combobox_restores_combobox_style() -> None:
    """<<DragLeave>> on a Combobox restores TCombobox, not TEntry."""
    entry, _, callback = _register_combobox_and_get_callback("<<DragLeave>>")
    entry.configure.reset_mock()
    callback(MagicMock())
    entry.configure.assert_called_with(style="TCombobox")
