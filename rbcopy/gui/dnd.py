"""Drag-and-drop support for path entry widgets.

Provides optional OS-level file/folder drop support via :mod:`tkinterdnd2`.
If the library is unavailable the setup functions are silent no-ops, so the
application continues to work without drag-and-drop capability.

Call :func:`setup_entry_drop` for each :class:`~tkinter.ttk.Entry` that
should accept dropped files or folders.  The caller is responsible for
ensuring that TkDND has been initialised on the root :class:`~tkinter.Tk`
window (see :meth:`~rbcopy.gui.main_window.RobocopyGUI._init_dnd`) before
calling this function.
"""

from __future__ import annotations

import tkinter as tk
from logging import getLogger
from tkinter import ttk
from typing import Any

logger = getLogger(__name__)

# ttk style names used to give visual feedback during a drag.
_DND_ACTIVE_STYLE: str = "DnDActive.TEntry"
_DND_DEFAULT_STYLE: str = "TEntry"


def parse_drop_data(data: str) -> str:
    """Return the first file path from a tkinterdnd2 drop-event data string.

    :mod:`tkinterdnd2` encodes dropped paths as a space-separated list.
    Paths that contain spaces are wrapped in curly braces so they can be
    distinguished from the space separator::

        # Single path, no spaces
        C:/Users/test

        # Single path with spaces (braces added by tkinterdnd2)
        {C:/Users/my folder}

        # Multiple paths — only the first is returned
        C:/path1 {C:/path with spaces}

    Args:
        data: Raw ``event.data`` string from a tkinterdnd2 ``<<Drop>>`` event.

    Returns:
        The first filesystem path as a plain string.  Returns an empty
        string when *data* is empty or cannot be parsed.
    """
    data = data.strip()
    if not data:
        return ""
    if data.startswith("{"):
        # Brace-quoted path: find the matching closing brace.
        end = data.find("}")
        return data[1:end] if end != -1 else data[1:]
    # Unquoted path: take everything up to the first whitespace token.
    return data.split()[0]


def setup_entry_drop(entry: ttk.Entry, string_var: tk.StringVar) -> bool:
    """Register OS-level file/folder drop handling on *entry*.

    Binds ``<<Drop>>``, ``<<DragEnter>>``, and ``<<DragLeave>>`` events so
    that the user can drag a file or directory from the OS file manager
    directly onto the entry widget.

    When a path is dropped:

    * The first dropped path replaces *string_var*'s current value.
    * Drops on a disabled entry are silently ignored, preserving constraints
      such as the "Properties Only" preset that locks the destination field.
    * A subtle background highlight is applied while the drag hovers over the
      widget and removed after the drop or when the drag leaves.

    This function is a no-op when :mod:`tkinterdnd2` is not installed or when
    DnD registration fails (e.g. the Tk root was not initialised with TkDND
    support).

    Args:
        entry: The entry widget to configure as a drop target.
        string_var: The :class:`~tkinter.StringVar` backing the entry; its
            value is updated on a successful drop.

    Returns:
        ``True`` if DnD was successfully registered, ``False`` otherwise.
    """
    try:
        from tkinterdnd2 import DND_FILES  # type: ignore[import-untyped]
    except ImportError:
        logger.debug("tkinterdnd2 not installed; drag-and-drop skipped for this entry")
        return False

    def _on_drop(event: Any) -> None:
        _restore_style(entry)
        # Respect the widget's disabled state so that locked fields (e.g. the
        # destination in "Properties Only" mode) cannot be overwritten via DnD.
        try:
            if str(entry.cget("state")) == "disabled":
                return
        except tk.TclError:
            return
        path = parse_drop_data(event.data)
        if path:
            string_var.set(path)
            logger.debug("Drag-and-drop: path set to %r", path)

    def _on_enter(event: Any) -> None:
        _apply_hover_style(entry)

    def _on_leave(event: Any) -> None:
        _restore_style(entry)

    try:
        entry.drop_target_register(DND_FILES)  # type: ignore[attr-defined]
        entry.dnd_bind("<<Drop>>", _on_drop)  # type: ignore[attr-defined]
        entry.dnd_bind("<<DragEnter>>", _on_enter)  # type: ignore[attr-defined]
        entry.dnd_bind("<<DragLeave>>", _on_leave)  # type: ignore[attr-defined]
    except (tk.TclError, AttributeError) as exc:
        logger.debug("Could not register drop target on entry: %s", exc)
        return False

    logger.debug("Drag-and-drop registered for entry widget")
    return True


def _apply_hover_style(entry: ttk.Entry) -> None:
    """Apply the DnD-hover style to *entry*, swallowing any :exc:`~tkinter.TclError`."""
    try:
        entry.configure(style=_DND_ACTIVE_STYLE)
    except tk.TclError:
        pass


def _restore_style(entry: ttk.Entry) -> None:
    """Restore the default ttk Entry style on *entry*, swallowing any :exc:`~tkinter.TclError`."""
    try:
        entry.configure(style=_DND_DEFAULT_STYLE)
    except tk.TclError:
        pass
