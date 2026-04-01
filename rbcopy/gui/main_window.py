"""Main application window for the Robocopy GUI."""

from __future__ import annotations

import asyncio
import json
import locale
import logging
import queue
import threading
import tkinter as tk
from datetime import datetime
from functools import partial
from logging import getLogger
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
from typing import Any, Callable, Dict, Literal
from rbcopy.notifications import notify_job_complete
from rbcopy.app_dirs import get_data_dir

from rbcopy.builder import (
    FLAG_OPTIONS,
    FLAG_TOOLTIPS,
    PARAM_OPTIONS,
    PARAM_TOOLTIPS,
    PROPERTIES_ONLY_DST,
    PROPERTIES_ONLY_FLAGS,
    PROPERTIES_ONLY_PARAMS,
    SUPERSEDES,
    build_command,
    exit_code_label,
    validate_command,
)
from rbcopy.bookmarks import BookmarksStore
from rbcopy.path_history import PathHistoryStore
from rbcopy.presets import CustomPreset, CustomPresetsStore

from rbcopy.gui.bookmark_manager import _BookmarkManagerWindow
from rbcopy.gui.job_history import _JobHistoryWindow
from rbcopy.gui.preferences_dialog import _PreferencesDialog
from rbcopy.gui.script_builder import _PackPadding, _ScriptExportDialog
from rbcopy.preferences import PreferencesStore
from rbcopy.robocopy_parser import parse_summary_from_log


# Use the fully-qualified package name rather than __name__ so that the
# logger is always a child of the 'rbcopy' namespace (and therefore
# inherits its FileHandler) even when launched directly.
logger = getLogger("rbcopy.gui")

_GEOMETRY_PATH: Path = get_data_dir() / "geometry.json"

# Maximum lines consumed from the output queue in a single poll cycle.
# Capping this prevents the main thread from blocking for too long when
# robocopy emits a burst of output, which would otherwise freeze the GUI.
_MAX_LINES_PER_POLL: int = 100

# Upper bound on the number of items buffered between the background
# asyncio thread and the Tkinter main thread.  Without a cap, robocopy
# jobs that emit thousands of lines per second (e.g. many small files on
# NVMe) would grow the queue without limit, ballooning memory and keeping
# the UI printing output long after the process has already exited.
_OUTPUT_QUEUE_MAXSIZE: int = 5000

# Flags that can delete files from the destination with no recovery path.
_DESTRUCTIVE_FLAGS: frozenset[str] = frozenset({"/MIR", "/PURGE"})

# Flags/params shown in the simple (default) view, before the Advanced toggle.
# Chosen for being the options a first-time user is most likely to want.
_SIMPLE_FLAGS: frozenset[str] = frozenset({"/E", "/L", "/MIR", "/Z", "/J"})
_SIMPLE_PARAMS: frozenset[str] = frozenset({"/MT", "/W", "/R"})


def _confirm_destructive_operation(
    dst: str,
    flag_selections: dict[str, bool],
    parent: tk.Misc | None = None,
) -> bool:
    """Return ``False`` if the user cancels after seeing a destructive-flag warning.

    Checks whether the destination directory already contains files and whether
    a destructive robocopy flag (``/MIR`` or ``/PURGE``) is active.  If both
    conditions are true, shows a strongly-worded confirmation dialog with *No*
    pre-selected to prevent accidental data loss.

    Safety logic (in order):

    1. If *dst* is empty or does not yet exist, no existing data is at risk —
       return ``True`` immediately (robocopy will create the directory).
    2. If the destination exists but is **empty**, no data can be lost —
       return ``True`` immediately.
    3. If the destination contains files or folders AND a destructive flag
       (``/MIR`` or ``/PURGE``) is active, show a strongly-worded
       ``askyesno`` dialog and return the user's choice.
    4. In all other cases (destination has content, no destructive flag) —
       return ``True`` (a plain copy cannot delete anything).

    Args:
        dst:             Raw destination path string from the GUI StringVar.
        flag_selections: Mapping of robocopy flag string to enabled boolean,
                         e.g. ``{"/MIR": True, "/NP": False}``.
        parent:          Optional Tkinter parent widget for the dialog.
                         Passing the main window keeps the dialog modal.

    Returns:
        ``True`` if it is safe to proceed (or the user confirmed).
        ``False`` if the user cancelled the operation.
    """
    cleaned: str = dst.strip()
    if not cleaned:
        return True

    dst_path: Path = Path(cleaned)

    # Rule 1 – destination does not exist yet; nothing to destroy.
    if not dst_path.exists():
        return True

    # Rule 2 – destination exists but is completely empty.
    # next() with a default is O(1) and avoids materialising the full listing.
    first_child: Path | None = next(dst_path.iterdir(), None)
    if first_child is None:
        return True

    # Rule 3 – destination has content; check for destructive flags.
    active_destructive: list[str] = sorted(flag for flag in _DESTRUCTIVE_FLAGS if flag_selections.get(flag) is True)
    if not active_destructive:
        # Rule 4 – content present but no destructive flag; safe to continue.
        return True

    flags_display: str = " and ".join(active_destructive)

    # Count items for a more informative warning (cap at a safe limit so we
    # never freeze the UI listing a directory with millions of entries).
    _MAX_COUNT: int = 1_000
    item_count: int = min(
        sum(1 for _ in dst_path.iterdir()),
        _MAX_COUNT,
    )
    count_label: str = f"at least {_MAX_COUNT:,}" if item_count >= _MAX_COUNT else str(item_count)

    warning_message: str = (
        f"⚠  DESTRUCTIVE OPERATION WARNING\n\n"
        f"The destination directory already contains {count_label} item(s):\n"
        f"  {cleaned}\n\n"
        f"You have enabled {flags_display}, which means ALL files and folders "
        f"in the destination that do not exist in the source WILL BE "
        f"PERMANENTLY DELETED with no possibility of recovery — "
        f"they will NOT go to the Recycle Bin.\n\n"
        f"Are you absolutely sure you want to continue?"
    )

    if parent is not None:
        proceed: bool = messagebox.askyesno(
            title="⚠  Destructive Flag Detected — Data Loss Risk",
            message=warning_message,
            icon=messagebox.WARNING,
            default=messagebox.NO,  # 'No' is pre-selected for safety
            parent=parent,
        )
    else:
        proceed = messagebox.askyesno(
            title="⚠  Destructive Flag Detected — Data Loss Risk",
            message=warning_message,
            icon=messagebox.WARNING,
            default=messagebox.NO,
        )
    return proceed


def _flush_log_handlers() -> None:
    """Flush all FileHandlers on the rbcopy logger before reading the log file."""
    for handler in logging.getLogger("rbcopy").handlers:
        if isinstance(handler, logging.FileHandler):
            handler.flush()


def _get_current_log_file_path() -> Path | None:
    """Return the active session log file path, or None if no FileHandler is attached."""
    for handler in logging.getLogger("rbcopy").handlers:
        if isinstance(handler, logging.FileHandler):
            return Path(handler.baseFilename)
    return None


class _ToolTip:
    """Simple tooltip that appears near a widget on mouse-enter."""

    _DELAY_MS = 500
    _FONT_SIZE = 9
    _WRAP_LENGTH = 420

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self._widget = widget
        self._text = text
        self._tip_window: tk.Toplevel | None = None
        self._after_id: str | None = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._cancel)
        widget.bind("<ButtonPress>", self._cancel)
        widget.bind("<FocusOut>", self._cancel)

    def _schedule(self, _event: tk.Event[Any]) -> None:
        self._cancel(_event)
        self._after_id = self._widget.after(self._DELAY_MS, self._show)

    def _cancel(self, _event: tk.Event[Any] | None = None) -> None:
        if self._after_id is not None:
            self._widget.after_cancel(self._after_id)
            self._after_id = None
        self._hide()

    def _show(self) -> None:
        if self._tip_window:
            return
        x = self._widget.winfo_rootx() + 20
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._tip_window = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tw,
            text=self._text,
            justify="left",
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            font=("TkDefaultFont", self._FONT_SIZE),
            wraplength=self._WRAP_LENGTH,
        ).pack(ipadx=4, ipady=2)

    def _hide(self) -> None:
        if self._tip_window:
            self._tip_window.destroy()
            self._tip_window = None


class _PresetDropdownTooltip:
    """Per-item description tooltips for the Preset combobox dropdown.

    When the dropdown list is open, hovering over an item that has a
    description shows it in a small tooltip window beside the cursor.
    Falls back silently if the Tk internal popdown widget cannot be
    located (e.g. on an unusual Tk build).

    Args:
        combo:            The combobox to attach to.
        get_descriptions: Callable that returns a ``{name: description}``
                          mapping.  Called lazily at hover time so it
                          always reflects the live preset list.
    """

    _FONT_SIZE: int = 9
    _WRAP_LENGTH: int = 320

    def __init__(self, combo: ttk.Combobox, get_descriptions: Callable[[], Dict[str, str]]) -> None:
        self._combo = combo
        self._get_descriptions = get_descriptions
        self._tip_window: tk.Toplevel | None = None
        combo.bind("<<ComboboxOpened>>", self._on_opened)
        combo.bind("<<ComboboxClosed>>", lambda _e: self._hide())

    def _on_opened(self, _event: tk.Event[Any]) -> None:
        """Bind motion on the internal listbox once the dropdown is open."""
        try:
            popdown: str = self._combo.tk.eval(f"ttk::combobox::PopdownWindow {self._combo}")
            # Access the internal Listbox via the Tk widget registry.  The cast
            # is necessary because tk.nametowidget lives on Misc, not TkappType.
            lb: tk.Listbox = self._combo.nametowidget(f"{popdown}.f.l")
            lb.bind("<Motion>", self._on_motion)
            lb.bind("<Leave>", lambda _e: self._hide())
        except Exception:
            logger.debug("_PresetDropdownTooltip: could not bind to popdown listbox", exc_info=True)

    def _on_motion(self, event: tk.Event[Any]) -> None:
        """Show the description for the list item under the cursor."""
        lb: tk.Listbox = event.widget
        idx: int = lb.nearest(event.y)  # type: ignore[no-untyped-call]
        values: list[str] = list(self._combo["values"])
        if idx < 0 or idx >= len(values):
            self._hide()
            return
        desc: str = self._get_descriptions().get(values[idx], "")
        if not desc:
            self._hide()
            return
        self._show(event.x_root, event.y_root, desc)

    def _show(self, x: int, y: int, text: str) -> None:
        """Display the tooltip window offset from (*x*, *y*)."""
        # Skip re-creation if the same text is already showing — avoids flicker.
        if self._tip_window is not None:
            children = self._tip_window.winfo_children()
            if children and children[0].cget("text") == text:
                return
        self._hide()
        self._tip_window = tw = tk.Toplevel(self._combo)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x + 16}+{y + 4}")
        tk.Label(
            tw,
            text=text,
            justify="left",
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            font=("TkDefaultFont", self._FONT_SIZE),
            wraplength=self._WRAP_LENGTH,
        ).pack(ipadx=4, ipady=2)

    def _hide(self) -> None:
        if self._tip_window is not None:
            self._tip_window.destroy()
            self._tip_window = None


class _SavePresetDialog(tk.Toplevel):
    """Modal dialog that collects a preset name and optional description.

    After construction the dialog blocks (via ``wait_window``) until the user
    either confirms or cancels.  Inspect :attr:`name` and :attr:`description`
    once the constructor returns.

    Args:
        parent: The parent Tk widget (the main window).
    """

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title("Save Preset")
        self.resizable(False, False)

        self._name_var = tk.StringVar()
        self._desc_var = tk.StringVar()
        self._confirmed: bool = False

        self._build_ui()
        self.transient(parent)  # type: ignore[call-overload]
        self.grab_set()
        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self._cancel())
        self.wait_window()

    @property
    def name(self) -> str | None:
        """The entered preset name, or *None* if the dialog was cancelled."""
        return self._name_var.get().strip() if self._confirmed else None

    @property
    def description(self) -> str:
        """The entered preset description (stripped; may be empty)."""
        return self._desc_var.get().strip()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)

        ttk.Label(frame, text="Name:").grid(row=0, column=0, sticky="w")
        name_entry = ttk.Entry(frame, textvariable=self._name_var, width=40)
        name_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        name_entry.focus_set()

        ttk.Label(frame, text="Description:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self._desc_var, width=40).grid(
            row=1, column=1, sticky="ew", padx=(8, 0), pady=(8, 0)
        )

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=(12, 0), sticky="e")
        ttk.Button(btn_frame, text="Save", command=self._ok).pack(side="right", padx=(4, 0))
        ttk.Button(btn_frame, text="Cancel", command=self._cancel).pack(side="right")

        frame.columnconfigure(1, weight=1)

    def _ok(self) -> None:
        if not self._name_var.get().strip():
            messagebox.showwarning("Name Required", "Please enter a preset name.", parent=self)
            return
        self._confirmed = True
        self.destroy()

    def _cancel(self) -> None:
        self.destroy()


class RobocopyGUI(tk.Tk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title("RbCopy – Robocopy GUI")
        self.resizable(True, True)
        self.minsize(800, 700)

        # Style
        style = ttk.Style(self)
        style.theme_use("clam")

        # Thread-safe queue for subprocess output; polled by the main thread.
        # Bounded to _OUTPUT_QUEUE_MAXSIZE so that fast robocopy jobs cannot
        # exhaust memory.  Lines that arrive when the queue is full are counted
        # and a summary notice is injected by _poll_output once space frees up.
        self._output_queue: queue.Queue[str] = queue.Queue(maxsize=_OUTPUT_QUEUE_MAXSIZE)

        # Count of output lines dropped because the queue was full.  Written
        # by the asyncio/background thread; read and reset by the main thread
        # inside _poll_output.  Relies on CPython's GIL for safe unsynchronised
        # access (reads/writes are atomic at the bytecode level).
        self._dropped_lines: int = 0

        # Guard to prevent re-entrant _refresh_widget_states calls while
        # _on_properties_only_toggle is batch-updating multiple variables.
        self._is_applying_preset: bool = False

        # Saved state for the Properties Only preset (populated on first activation).
        self._saved_dst: str = ""
        self._saved_flags: dict[str, bool] = {}
        self._saved_params: dict[str, tuple[bool, str]] = {}

        # Props-only var must exist before _build_ui/_build_menu are called.
        self._props_only_var = tk.BooleanVar(value=False)

        # Script Builder var must also exist before _build_ui/_build_menu are called.
        self._script_builder_var = tk.BooleanVar(value=False)

        # File filter vars must exist before _build_ui is called.
        self._file_filter_enabled_var = tk.BooleanVar(value=False)
        self._file_filter_var = tk.StringVar(value="")

        # Application preferences store – must exist before _build_menu is called.
        self._prefs_store: PreferencesStore = PreferencesStore()

        # Custom presets store and menu reference must exist before _build_menu is called.
        self._presets_store: CustomPresetsStore = CustomPresetsStore()
        self._custom_menu: tk.Menu  # assigned in _build_menu

        # Bookmarks store and menu reference must exist before _build_menu is called.
        self._bookmarks_store: BookmarksStore = BookmarksStore()
        self._bookmarks_menu: tk.Menu  # assigned in _build_menu

        # Path history store for source/destination Combobox dropdowns.
        self._path_history: PathHistoryStore = PathHistoryStore()

        # Reference to the currently-running robocopy subprocess, if any.
        # Set by _async_execute on the worker thread; read by _exit on the main thread.
        self._current_proc: asyncio.subprocess.Process | None = None

        # Event signalled by _async_execute (in its finally block) when the
        # subprocess has fully exited.  Used by _exit() to wait for clean shutdown.
        self._proc_done_event: threading.Event | None = None

        # Shutdown flag: set by _exit() before destroying the window.
        # Checked by _execute() to avoid spawning a new process after close.
        self._shutdown: threading.Event = threading.Event()

        # Widget/variable registries populated by _build_flags and _build_params;
        # must be initialised before _build_ui is called.
        self._flag_vars: dict[str, tk.BooleanVar] = {}
        self._flag_cbs: dict[str, ttk.Checkbutton] = {}
        self._param_vars: dict[str, tuple[tk.BooleanVar, tk.StringVar, ttk.Entry]] = {}
        self._param_cbs: dict[str, ttk.Checkbutton] = {}

        # Simple / advanced mode state.
        self._preset_var: tk.StringVar = tk.StringVar(value="")
        self._preset_combo: ttk.Combobox | None = None
        self._advanced_visible: bool = False

        # Path vars must be initialised before _build_ui so that _rebuild_bookmarks_menu
        # (called from _build_menu, which runs first) can reference them safely.
        self.src_var: tk.StringVar = tk.StringVar()
        self.dst_var: tk.StringVar = tk.StringVar()

        self._build_ui()
        self._apply_preferences()

        # Initialise drag-and-drop for path entries.  Must come after _build_ui
        # so that _src_entry and _dst_entry are already constructed.
        self._init_dnd()

        # Ensure the window-close button (×) also terminates any live process.
        self.protocol("WM_DELETE_WINDOW", self._exit)

        # Begin polling the output queue so background threads can write safely.
        self._poll_output()

        # Restore window geometry from the previous session if available.
        self._restore_geometry()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Assemble all UI sections."""
        padding: _PackPadding = {"padx": 8, "pady": 4}

        # ── Menu bar ───────────────────────────────────────────────────
        self._build_menu()

        # ── Main scrollable canvas (allows scrolling anywhere in the window) ──
        main_canvas = tk.Canvas(self, highlightthickness=0)
        v_scroll = ttk.Scrollbar(self, orient="vertical", command=main_canvas.yview)
        main_canvas.configure(yscrollcommand=v_scroll.set)
        v_scroll.pack(side="right", fill="y")
        main_canvas.pack(side="left", fill="both", expand=True)

        content = ttk.Frame(main_canvas)
        _cw = main_canvas.create_window((0, 0), window=content, anchor="nw")

        content.bind("<Configure>", lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all")))
        main_canvas.bind("<Configure>", lambda e: main_canvas.itemconfig(_cw, width=e.width))

        # Scroll main canvas on mouse-wheel from anywhere; disabled while mouse
        # is over the output console so that widget can scroll independently.
        def _scroll_main(e: tk.Event[Any]) -> None:
            main_canvas.yview_scroll(-1 * (e.delta // 120), "units")

        self.bind_all("<MouseWheel>", _scroll_main)

        # ── Source / Destination ──────────────────────────────────────
        path_frame = ttk.LabelFrame(content, text="Paths", padding=6)
        path_frame.pack(fill="x", **padding)
        path_frame.columnconfigure(1, weight=1)

        ttk.Label(path_frame, text="Source:").grid(row=0, column=0, sticky="w", pady=2)
        # Keep a reference so _init_dnd can register the source entry as a drop target.
        # ttk.Combobox inherits from ttk.Entry so DnD registration is unchanged.
        self._src_entry = ttk.Combobox(path_frame, textvariable=self.src_var, values=[])
        self._src_entry["postcommand"] = self._refresh_path_dropdowns
        self._src_entry.grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(path_frame, text="Browse…", command=self._browse_src).grid(row=0, column=2)
        _src_bm_btn = ttk.Button(
            path_frame,
            text="★",
            width=2,
            command=lambda: self._bookmark_field("source"),
        )
        _src_bm_btn.grid(row=0, column=3, padx=(2, 0))
        _ToolTip(_src_bm_btn, "Bookmark this source path.\nSaved bookmarks appear in the Bookmarks menu.")

        ttk.Label(path_frame, text="Destination:").grid(row=1, column=0, sticky="w", pady=2)
        self._dst_entry = ttk.Combobox(path_frame, textvariable=self.dst_var, values=[])
        self._dst_entry["postcommand"] = self._refresh_path_dropdowns
        self._dst_entry.grid(row=1, column=1, sticky="ew", padx=4)
        self._dst_browse_btn = ttk.Button(path_frame, text="Browse…", command=self._browse_dst)
        self._dst_browse_btn.grid(row=1, column=2)
        _dst_bm_btn = ttk.Button(
            path_frame,
            text="★",
            width=2,
            command=lambda: self._bookmark_field("destination"),
        )
        _dst_bm_btn.grid(row=1, column=3, padx=(2, 0))
        _ToolTip(_dst_bm_btn, "Bookmark this destination path.\nSaved bookmarks appear in the Bookmarks menu.")

        # ── File Filter ───────────────────────────────────────────────
        self._file_filter_cb = ttk.Checkbutton(
            path_frame,
            text="File filter:",
            variable=self._file_filter_enabled_var,
        )
        self._file_filter_cb.grid(row=2, column=0, sticky="w", pady=(4, 0))
        self._file_filter_entry = ttk.Entry(
            path_frame,
            textvariable=self._file_filter_var,
            width=30,
            state="disabled",
        )
        self._file_filter_entry.grid(row=2, column=1, sticky="ew", padx=4, pady=(4, 0))
        _file_filter_import_btn = ttk.Button(
            path_frame,
            text="Import…",
            width=8,
            command=self._import_file_filter_from_file,
        )
        _file_filter_import_btn.grid(row=2, column=2, padx=(0, 0), pady=(4, 0))
        _ToolTip(
            self._file_filter_cb,
            "Space-separated file patterns passed directly to robocopy.\n"
            "Only files matching these patterns will be copied.\n"
            "Example: *.img  *.raw  backup_*.zip",
        )
        _ToolTip(
            _file_filter_import_btn,
            "Import a .txt file with one file pattern per line (e.g. *.img).\n"
            "Blank lines and lines starting with '#' are ignored.\n"
            "Imported patterns are appended to any value already in the field.",
        )

        def _toggle_file_filter_entry(*_args: object) -> None:
            self._file_filter_entry.config(state="normal" if self._file_filter_enabled_var.get() else "disabled")

        self._file_filter_enabled_var.trace_add("write", _toggle_file_filter_entry)

        # ── Preset selector ───────────────────────────────────────────
        ttk.Label(path_frame, text="Preset:").grid(row=3, column=0, sticky="w", pady=(4, 0))
        self._preset_combo = ttk.Combobox(path_frame, textvariable=self._preset_var, state="readonly", width=30)
        self._preset_combo.grid(row=3, column=1, sticky="ew", padx=4, pady=(4, 0))
        self._preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)
        _PresetDropdownTooltip(self._preset_combo, self._get_preset_description_map)

        self._param_vars = {}
        self._flag_cbs = {}
        self._param_cbs = {}

        # ── Action buttons ────────────────────────────────────────────────
        btn_frame = ttk.Frame(content)
        btn_frame.pack(fill="x", **padding)

        _btn_preview = ttk.Button(btn_frame, text="Preview Command", command=self._preview)
        _btn_preview.pack(side="left", padx=(0, 6))
        _ToolTip(
            _btn_preview,
            "Builds the robocopy command from the current settings and prints it to the output — nothing is copied.",
        )
        self._btn_dry_run = ttk.Button(btn_frame, text="🔍 Dry Run", command=self._dry_run)
        self._btn_dry_run.pack(side="left", padx=(0, 6))
        _ToolTip(
            self._btn_dry_run,
            "Runs robocopy with /L (list only). Shows which files would be copied without making any changes to disk.",
        )
        self._btn_run = ttk.Button(btn_frame, text="▶  Run", command=self._run)
        self._btn_run.pack(side="left", padx=(0, 6))
        self._btn_stop = ttk.Button(btn_frame, text="⏹  Stop", command=self._stop, state="disabled")
        self._btn_stop.pack(side="left")
        ttk.Button(btn_frame, text="Clear Output", command=self._clear_output).pack(side="right")
        self._btn_advanced = ttk.Button(btn_frame, text="⚙ Advanced ▸", command=self._toggle_advanced)
        self._btn_advanced.pack(side="right", padx=(0, 4))
        _ToolTip(self._btn_advanced, "Show or hide additional robocopy flags and parameters.")

        # ── Output console ────────────────────────────────────────────
        out_frame = ttk.LabelFrame(content, text="Output", padding=4)
        out_frame.pack(fill="both", expand=True, **padding)

        self._output = scrolledtext.ScrolledText(
            out_frame, state="disabled", wrap="word", height=10, font=("Courier New", 9)
        )
        self._output.pack(fill="both", expand=True)

        # Suspend global scroll while mouse is over the output console
        self._output.bind("<Enter>", lambda e: self.unbind_all("<MouseWheel>"))
        self._output.bind("<Leave>", lambda e: self.bind_all("<MouseWheel>", _scroll_main))

        # ── Common options (always visible) ───────────────────────────────
        self._build_flags(content, padding, include=_SIMPLE_FLAGS)
        self._build_params(content, padding, include=_SIMPLE_PARAMS)

        # ── Advanced section (hidden by default, revealed by toggle button) ──
        self._advanced_frame = ttk.Frame(content)
        # Do not pack here – frame starts hidden in simple mode.
        # include=None → renders all flags/params not yet registered (the remainder).
        self._build_flags(self._advanced_frame, padding)
        self._build_params(self._advanced_frame, padding)

        # Populate the preset combo now that _presets_store is available.
        self._refresh_preset_combo()

        # Add supersession traces: when a superseding flag changes, refresh widget states.
        for sup_flag in SUPERSEDES:
            if sup_flag in self._flag_vars:
                self._flag_vars[sup_flag].trace_add("write", lambda *_: self._refresh_widget_states())

        # Apply initial widget states (supersession rules may grey out redundant flags).
        self._refresh_widget_states()

    def _build_menu(self) -> None:
        """Assemble the application menu bar."""
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        # ── File menu ─────────────────────────────────────────────────
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Preferences…", command=self._open_preferences)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._exit)

        # ── View menu ─────────────────────────────────────────────────
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Job History…", command=self._open_job_history)
        view_menu.add_separator()
        view_menu.add_command(label="Reset Options", command=self._reset_options)

        # ── Presets menu ──────────────────────────────────────────────
        presets_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Presets", menu=presets_menu)
        presets_menu.add_checkbutton(
            label="Properties Only",
            variable=self._props_only_var,
        )
        presets_menu.add_separator()
        # Brief description of what the preset does so the information
        # previously shown via tooltip remains visible from the menu.
        presets_menu.add_command(
            label="ℹ  Sets dst → c:\\temp\\blank, forces /L /MIR /NFL /NDL /MT:48 /R:0 /W:0",
            state="disabled",
        )
        presets_menu.add_separator()
        presets_menu.add_checkbutton(
            label="Script Builder",
            variable=self._script_builder_var,
        )
        presets_menu.add_separator()
        # Description shown as a disabled item so the user understands what
        # Script Builder does without needing to run it first.
        presets_menu.add_command(
            label="ℹ  When checked, clicking Run exports a script file instead of running robocopy",
            state="disabled",
        )

        # ── Custom presets ─────────────────────────────────────────────
        presets_menu.add_separator()
        self._custom_menu = tk.Menu(presets_menu, tearoff=0)
        presets_menu.add_cascade(label="Custom", menu=self._custom_menu)
        presets_menu.add_separator()
        presets_menu.add_command(label="Save Current as Preset…", command=self._save_custom_preset)

        self._props_only_var.trace_add("write", self._on_properties_only_toggle)
        self._rebuild_custom_menu()

        # ── Bookmarks menu ─────────────────────────────────────────────
        self._bookmarks_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Bookmarks", menu=self._bookmarks_menu)
        self._rebuild_bookmarks_menu()

    def _build_flags(
        self,
        parent: ttk.Frame,
        padding: _PackPadding,
        include: frozenset[str] | None = None,
    ) -> None:
        """Build a flag-checkboxes section.

        Args:
            parent:  Widget to pack the LabelFrame into.
            padding: Standard pack padding to apply.
            include: If given, render only flags in this set ("common" view).
                     If ``None``, render every flag not yet registered in
                     ``_flag_vars`` (i.e. the remaining/advanced flags).
        """
        title = "Common Options" if include is not None else "More Options"
        flags_to_render = [
            (flag, label)
            for flag, label in FLAG_OPTIONS
            if (include is not None and flag in include) or (include is None and flag not in self._flag_vars)
        ]
        if not flags_to_render:
            return

        content_frame = ttk.LabelFrame(parent, text=title, padding=6)
        content_frame.pack(fill="x", **padding)
        content_frame.columnconfigure(0, weight=1)
        content_frame.columnconfigure(1, weight=1)

        left = ttk.Frame(content_frame)
        right = ttk.Frame(content_frame)
        left.grid(row=0, column=0, sticky="nw", padx=(0, 12))
        right.grid(row=0, column=1, sticky="nw")

        mid = len(flags_to_render) // 2 + len(flags_to_render) % 2
        for i, (flag, label) in enumerate(flags_to_render):
            var = tk.BooleanVar(value=False)
            self._flag_vars[flag] = var
            col_frame = left if i < mid else right
            cb = ttk.Checkbutton(col_frame, text=f"{flag}  {label}", variable=var)
            cb.pack(anchor="w")
            self._flag_cbs[flag] = cb
            if flag in FLAG_TOOLTIPS:
                _ToolTip(cb, FLAG_TOOLTIPS[flag])

    def _build_params(
        self,
        parent: ttk.Frame,
        padding: _PackPadding,
        include: frozenset[str] | None = None,
    ) -> None:
        """Build a param (checkbox + entry) options section.

        Args:
            parent:  Widget to pack the LabelFrame into.
            padding: Standard pack padding to apply.
            include: If given, render only params in this set ("common" view).
                     If ``None``, render every param not yet registered in
                     ``_param_vars`` (i.e. the remaining/advanced params).
        """
        title = "Common Options with Values" if include is not None else "More Options with Values"
        params_to_render = [
            (flag, label, placeholder)
            for flag, label, placeholder in PARAM_OPTIONS
            if (include is not None and flag in include) or (include is None and flag not in self._param_vars)
        ]
        if not params_to_render:
            return

        content_frame = ttk.LabelFrame(parent, text=title, padding=4)
        content_frame.pack(fill="x", **padding)
        content_frame.columnconfigure(1, weight=1)

        for row_idx, (flag, label, placeholder) in enumerate(params_to_render):
            enabled_var = tk.BooleanVar(value=False)
            value_var = tk.StringVar(value=placeholder)
            cb = ttk.Checkbutton(content_frame, text=label, variable=enabled_var)
            cb.grid(row=row_idx, column=0, sticky="w", pady=1)
            self._param_cbs[flag] = cb
            entry = ttk.Entry(
                content_frame,
                textvariable=value_var,
                width=22,
                state="disabled",
            )
            entry.grid(row=row_idx, column=1, sticky="ew", padx=(4, 0), pady=1)

            def _on_toggle(*_args: object, e: ttk.Entry = entry, v: tk.BooleanVar = enabled_var) -> None:
                e.config(state="normal" if v.get() else "disabled")

            enabled_var.trace_add("write", _on_toggle)
            self._param_vars[flag] = (enabled_var, value_var, entry)
            if flag in PARAM_TOOLTIPS:
                _ToolTip(cb, PARAM_TOOLTIPS[flag])

            # Add an import button for flags that accept space-separated lists so
            # users can load dozens of patterns from a .txt file without hand-editing.
            if flag in ("/XF", "/XD"):
                import_btn = ttk.Button(
                    content_frame,
                    text="Import…",
                    width=8,
                    command=partial(self._import_exclusions_from_file, flag, enabled_var, value_var, entry),
                )
                import_btn.grid(row=row_idx, column=2, padx=(4, 0), pady=1)
                _ToolTip(
                    import_btn,
                    f"Import a .txt file with one exclusion pattern per line for {flag}.\n"
                    "Blank lines and lines starting with '#' are ignored.\n"
                    "Imported patterns are appended to any value already in the field.",
                )

    def _toggle_advanced(self) -> None:
        """Show or hide the advanced flags/params section."""
        if self._advanced_visible:
            self._advanced_frame.pack_forget()
            self._advanced_visible = False
            self._btn_advanced.config(text="⚙ Advanced ▸")
        else:
            self._advanced_frame.pack(fill="x")
            self._advanced_visible = True
            self._btn_advanced.config(text="⚙ Advanced ▾")

    def _on_preset_selected(self, _event: tk.Event[Any]) -> None:
        """Apply the preset chosen in the Preset combo and reset the combo."""
        name = self._preset_var.get()
        if not name:
            return
        if name == "Properties Only":
            self._props_only_var.set(True)
        else:
            preset = self._presets_store.get_preset(name)
            if preset is not None:
                self._apply_custom_preset(preset)
        # Reset the combo to a blank selection; preset state lives in the checkboxes.
        self._preset_var.set("")
        if self._preset_combo is not None:
            self._preset_combo.set("")

    def _refresh_preset_combo(self) -> None:
        """Sync the Preset combo values with the current presets store."""
        if self._preset_combo is None:
            return
        names = ["Properties Only"] + [p.name for p in self._presets_store.presets]
        self._preset_combo["values"] = names

    def _get_preset_description_map(self) -> Dict[str, str]:
        """Return a ``{name: description}`` map for all available presets.

        Used by :class:`_PresetDropdownTooltip` to display per-item
        descriptions while the user hovers inside the Preset dropdown.
        Custom presets without a description are omitted so the tooltip
        only appears when there is something useful to say.
        """
        descriptions: Dict[str, str] = {
            "Properties Only": (
                f"Sets destination to {PROPERTIES_ONLY_DST} and forces "
                "/L /MIR /NFL /NDL /MT:48 /R:0 /W:0.\n"
                "Safe: lists file differences without copying anything."
            ),
        }
        for preset in self._presets_store.presets:
            if preset.description:
                descriptions[preset.name] = preset.description
        return descriptions

    # ------------------------------------------------------------------
    # Drag-and-drop
    # ------------------------------------------------------------------

    def _init_dnd(self) -> None:
        """Attempt to initialise TkDND and register path entries as drop targets.

        Loads the TkDND Tcl extension into the current Tk interpreter via
        :mod:`tkinterdnd2` and then registers both the source and destination
        entry widgets so the user can drag folders directly from the OS file
        manager onto them.

        If :mod:`tkinterdnd2` is not installed, or if the TkDND extension
        cannot be loaded on this platform (e.g. headless CI environments),
        this method logs a debug message and returns without raising an
        exception.  The rest of the GUI is completely unaffected.

        Note:
            ``TkinterDnD._require`` mirrors the initialisation performed by
            ``TkinterDnD.Tk.__init__`` when used as a base class.  Calling it
            here lets us keep ``tk.Tk`` as the base class and avoid disrupting
            existing tests and the class hierarchy.
        """
        try:
            from tkinterdnd2 import TkinterDnD  # type: ignore[import-untyped]

            # Retrofit TkDND support onto this existing Tk root window.
            TkinterDnD._require(self)
        except Exception as exc:
            logger.debug("TkDND not available; drag-and-drop disabled: %s", exc)
            return

        from rbcopy.gui.dnd import setup_entry_drop

        # Register a subtle hover highlight style that appears while a drag
        # is hovering over an entry to signal that the drop will be accepted.
        style = ttk.Style(self)
        style.configure("DnDActive.TEntry", fieldbackground="#d0eeff")

        src_ok = setup_entry_drop(self._src_entry, self.src_var)
        dst_ok = setup_entry_drop(self._dst_entry, self.dst_var)
        logger.debug(
            "Drag-and-drop setup complete (src=%s, dst=%s)",
            "ok" if src_ok else "failed",
            "ok" if dst_ok else "failed",
        )

    # ------------------------------------------------------------------
    # Properties Only preset & widget-state management
    # ------------------------------------------------------------------

    def _on_properties_only_toggle(self, *_args: object) -> None:
        """Apply or revert the 'Properties Only' preset."""
        self._is_applying_preset = True
        try:
            enabled = self._props_only_var.get()
            if enabled:
                # Save current state before applying preset.
                self._saved_dst = self.dst_var.get()
                self._saved_flags = {f: bool(v.get()) for f, v in self._flag_vars.items()}
                self._saved_params = {f: (bool(bv.get()), sv.get()) for f, (bv, sv, _) in self._param_vars.items()}
                # Apply forced destination.
                self.dst_var.set(PROPERTIES_ONLY_DST)
                # Apply forced flags; leave all other flags at their current values.
                for flag in PROPERTIES_ONLY_FLAGS:
                    if flag in self._flag_vars:
                        self._flag_vars[flag].set(True)
                # Apply forced params with their forced values.
                for flag, forced_value in PROPERTIES_ONLY_PARAMS.items():
                    if flag in self._param_vars:
                        pev, pvv, _ = self._param_vars[flag]
                        pev.set(True)
                        pvv.set(forced_value)
            else:
                # Restore previously saved state.
                self.dst_var.set(self._saved_dst)
                for flag, saved_val in self._saved_flags.items():
                    if flag in self._flag_vars:
                        self._flag_vars[flag].set(saved_val)
                for flag, (saved_en, saved_str) in self._saved_params.items():
                    if flag in self._param_vars:
                        restore_ev, restore_vv, _ = self._param_vars[flag]
                        restore_ev.set(saved_en)
                        restore_vv.set(saved_str)
        finally:
            self._is_applying_preset = False
        self._refresh_widget_states()

    def _refresh_widget_states(self, *_args: object) -> None:
        """Update enabled/disabled state of all option widgets.

        Applies two rules in priority order:
        1. Properties Only mode: forced options are locked; all others remain
           freely editable.
        2. Supersession: when a flag that implies other flags is selected, the
           implied (redundant) flags are greyed out.
        """
        if self._is_applying_preset:
            return

        props_only = self._props_only_var.get()

        # Compute which flags are superseded by currently-selected flags.
        superseded: set[str] = set()
        for sup_flag, implied in SUPERSEDES.items():
            if sup_flag in self._flag_vars and self._flag_vars[sup_flag].get():
                superseded.update(implied)

        # ── Flag checkbuttons ──────────────────────────────────────────
        for flag, cb in self._flag_cbs.items():
            if props_only and flag in PROPERTIES_ONLY_FLAGS:
                # Forced-on flags are visually disabled so the user cannot uncheck them.
                state = "disabled"
            elif flag in superseded:
                state = "disabled"
            else:
                state = "normal"
            cb.config(state=state)

        # ── Param checkbuttons and entries ────────────────────────────
        for flag, (ev, _vv, entry) in self._param_vars.items():
            param_cb: ttk.Checkbutton | None = self._param_cbs.get(flag)
            if props_only and flag in PROPERTIES_ONLY_PARAMS:
                # Forced param: both the checkbox and entry are locked.
                if param_cb:
                    param_cb.config(state="disabled")
                entry.config(state="disabled")
            else:
                # Normal mode (and Properties Only non-forced): checkbox is always
                # enabled; entry state follows the checkbox.
                if param_cb:
                    param_cb.config(state="normal")
                entry.config(state="normal" if ev.get() else "disabled")

        # ── Destination entry and browse button ───────────────────────
        dst_state = "disabled" if props_only else "normal"
        self._dst_entry.config(state=dst_state)
        self._dst_browse_btn.config(state=dst_state)

    def _reset_options(self) -> None:
        """Uncheck all flag and param option checkboxes and reset param values to defaults.

        Source and destination paths are left untouched.  If the Properties
        Only preset is currently active it is first deactivated so that its
        forced options are no longer locked before the reset is applied.
        """
        if self._props_only_var.get():
            # Deactivating Properties Only may restore a previously-saved
            # destination (and other option state). Preserve the currently
            # visible src/dst values so that this method truly leaves them
            # untouched while still unlocking forced options.
            current_src: str = self.src_var.get()
            current_dst: str = self.dst_var.get()
            self._props_only_var.set(False)
            self.src_var.set(current_src)
            self.dst_var.set(current_dst)

        # Build a flag-to-placeholder map once for O(1) lookup inside the loop.
        param_defaults: dict[str, str] = {flag: ph for flag, _lbl, ph in PARAM_OPTIONS}

        self._is_applying_preset = True
        try:
            for var in self._flag_vars.values():
                var.set(False)
            for flag, (enabled_var, value_var, _entry) in self._param_vars.items():
                enabled_var.set(False)
                value_var.set(param_defaults.get(flag, ""))
            self._file_filter_enabled_var.set(False)
            self._file_filter_var.set("")
        finally:
            self._is_applying_preset = False

        self._refresh_widget_states()

    # ------------------------------------------------------------------
    # Browse helpers
    # ------------------------------------------------------------------

    def _browse_src(self) -> None:
        path = filedialog.askdirectory(title="Select Source Directory")
        if path:
            self.src_var.set(path)

    def _browse_dst(self) -> None:
        path = filedialog.askdirectory(title="Select Destination Directory")
        if path:
            self.dst_var.set(path)

    def _import_exclusions_from_file(
        self,
        flag: str,
        enabled_var: tk.BooleanVar,
        value_var: tk.StringVar,
        entry: ttk.Entry,
    ) -> None:
        """Import exclusion patterns from a .txt file and append them to *flag*'s value.

        Opens a file chooser restricted to .txt files, reads each line as a
        pattern, discards blank lines and lines beginning with ``#``, then
        appends the resulting tokens to any text already in *value_var*.  The
        flag's checkbox and entry widget are enabled automatically so the
        imported patterns are included in the next robocopy run.

        Args:
            flag:        The robocopy flag receiving the import (``/XF`` or ``/XD``).
            enabled_var: The BooleanVar bound to the flag's checkbox.
            value_var:   The StringVar bound to the flag's entry field.
            entry:       The ttk.Entry widget whose state must mirror the checkbox.
        """
        path_str = filedialog.askopenfilename(
            title=f"Import exclusions for {flag}",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            parent=self,
        )
        if not path_str:
            return

        try:
            raw = Path(path_str).read_text(encoding="utf-8")
        except OSError:
            logger.exception("Could not read exclusions file: %s", path_str)
            messagebox.showerror(
                "Import Failed",
                f"Could not read:\n{path_str}",
                parent=self,
            )
            return

        patterns: list[str] = [
            line.strip() for line in raw.splitlines() if line.strip() and not line.strip().startswith("#")
        ]
        if not patterns:
            messagebox.showinfo(
                "No Patterns Found",
                "The selected file contained no usable patterns.\nBlank lines and lines starting with '#' are ignored.",
                parent=self,
            )
            return

        existing = value_var.get().strip()
        combined = (existing + " " + " ".join(patterns)).strip() if existing else " ".join(patterns)
        value_var.set(combined)
        enabled_var.set(True)
        entry.config(state="normal")
        logger.info("Imported %d exclusion pattern(s) for %s from %s", len(patterns), flag, path_str)

    def _import_file_filter_from_file(self) -> None:
        """Import include-file patterns from a .txt file into the file filter field.

        Opens a file chooser restricted to .txt files, reads each line as a
        pattern, discards blank lines and lines beginning with ``#``, then
        appends the resulting tokens to any text already in the file filter
        entry.  The file filter checkbox and entry are enabled automatically.
        """
        path_str = filedialog.askopenfilename(
            title="Import file filter patterns",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            parent=self,
        )
        if not path_str:
            return

        try:
            raw = Path(path_str).read_text(encoding="utf-8")
        except OSError:
            logger.exception("Could not read file filter patterns file: %s", path_str)
            messagebox.showerror(
                "Import Failed",
                f"Could not read:\n{path_str}",
                parent=self,
            )
            return

        patterns: list[str] = [
            line.strip() for line in raw.splitlines() if line.strip() and not line.strip().startswith("#")
        ]
        if not patterns:
            messagebox.showinfo(
                "No Patterns Found",
                "The selected file contained no usable patterns.\nBlank lines and lines starting with '#' are ignored.",
                parent=self,
            )
            return

        existing = self._file_filter_var.get().strip()
        combined = (existing + " " + " ".join(patterns)).strip() if existing else " ".join(patterns)
        self._file_filter_var.set(combined)
        self._file_filter_enabled_var.set(True)
        self._file_filter_entry.config(state="normal")
        logger.info("Imported %d file filter pattern(s) from %s", len(patterns), path_str)

    def _refresh_path_dropdowns(self) -> None:
        """Sync both path Combobox value lists from the path history store."""
        self._src_entry["values"] = self._path_history.get_source_paths()
        self._dst_entry["values"] = self._path_history.get_destination_paths()

    def _save_geometry(self) -> None:
        """Persist the current window size and position to disk.

        Failures are silently logged so a geometry write error never
        prevents the application from closing cleanly.
        """
        try:
            _GEOMETRY_PATH.parent.mkdir(parents=True, exist_ok=True)
            geometry = self.geometry()
            _GEOMETRY_PATH.write_text(
                json.dumps({"geometry": geometry}),
                encoding="utf-8",
            )
            logger.debug("Saved window geometry: %s", geometry)
        except OSError:
            logger.debug("Could not save window geometry", exc_info=True)

    def _restore_geometry(self) -> None:
        """Restore window size and position from disk if available.

        Silently falls back to the default geometry if the file is missing,
        corrupt, or contains an invalid geometry string.
        """
        if not _GEOMETRY_PATH.exists():
            return
        try:
            data = json.loads(_GEOMETRY_PATH.read_text(encoding="utf-8"))
            geometry = data.get("geometry", "")
            if geometry:
                self.geometry(geometry)
                logger.debug("Restored window geometry: %s", geometry)
        except (OSError, json.JSONDecodeError, ValueError):
            logger.debug("Could not restore window geometry", exc_info=True)

    # ------------------------------------------------------------------
    # Custom preset management
    # ------------------------------------------------------------------

    def _save_custom_preset(self) -> None:
        """Prompt for a name and description, then save the current GUI selections as a custom preset."""
        dialog = _SavePresetDialog(self)
        if dialog.name is None:
            return
        name = dialog.name

        flag_selections, param_selections = self._get_selections()
        preset = CustomPreset(
            name=name,
            description=dialog.description,
            source=self.src_var.get(),
            destination=self.dst_var.get(),
            flags=flag_selections,
            params=param_selections,
            file_filter=self._file_filter_var.get() if self._file_filter_enabled_var.get() else "",
        )
        if not self._presets_store.save_preset(preset):
            messagebox.showerror(
                "Save Failed",
                f"Preset '{name}' could not be saved to disk.\nCheck available disk space and file permissions.",
                parent=self,
            )
            return
        self._rebuild_custom_menu()
        messagebox.showinfo("Preset Saved", f"Preset '{name}' saved successfully.", parent=self)

    def _apply_custom_preset(self, preset: CustomPreset) -> None:
        """Apply *preset* to the GUI, restoring all saved selections.

        When "Properties Only" mode is active, forced values (destination, forced
        flags, and forced params) are left untouched so the preset does not
        silently break the Properties Only invariants.

        Args:
            preset: The :class:`~rbcopy.presets.CustomPreset` to apply.
        """
        props_only = self._props_only_var.get()
        self._is_applying_preset = True
        try:
            self.src_var.set(preset.source)
            # Do not overwrite the forced destination while Properties Only is active.
            if not props_only:
                self.dst_var.set(preset.destination)
            for flag, enabled in preset.flags.items():
                if flag in self._flag_vars:
                    # Do not override forced-on flags while Properties Only is active.
                    if props_only and flag in PROPERTIES_ONLY_FLAGS:
                        continue
                    self._flag_vars[flag].set(enabled)
            for flag, (enabled, value) in preset.params.items():
                if flag in self._param_vars:
                    # Do not override forced params while Properties Only is active.
                    if props_only and flag in PROPERTIES_ONLY_PARAMS:
                        continue
                    ev, vv, _ = self._param_vars[flag]
                    ev.set(enabled)
                    vv.set(value)
        finally:
            self._is_applying_preset = False
        # Restore file filter from preset.
        if preset.file_filter:
            self._file_filter_enabled_var.set(True)
            self._file_filter_var.set(preset.file_filter)
        else:
            self._file_filter_enabled_var.set(False)
            self._file_filter_var.set("")
        self._refresh_widget_states()

    def _delete_custom_preset(self, name: str) -> None:
        """Ask for confirmation, then delete the named custom preset.

        Args:
            name: Name of the preset to delete.
        """
        confirmed = messagebox.askyesno(
            "Delete Preset",
            f"Delete preset '{name}'?",
            parent=self,
        )
        if not confirmed:
            return
        self._presets_store.delete_preset(name)
        self._rebuild_custom_menu()

    def _rebuild_custom_menu(self) -> None:
        """Repopulate the Custom presets submenu from the current presets store.

        Each saved preset gets a nested submenu with *Load* and *Delete* entries.
        When no presets have been saved yet a disabled placeholder label is shown.
        """
        self._custom_menu.delete(0, "end")
        presets = self._presets_store.presets
        if not presets:
            self._custom_menu.add_command(label="(no saved presets)", state="disabled")
            self._refresh_preset_combo()
            return
        for preset in presets:
            sub = tk.Menu(self._custom_menu, tearoff=0)
            self._custom_menu.add_cascade(label=preset.name, menu=sub)
            if preset.description:
                sub.add_command(label=f"\u2139  {preset.description}", state="disabled")
                sub.add_separator()
            sub.add_command(
                label=f"Load '{preset.name}'",
                command=partial(self._apply_custom_preset, preset),
            )
            sub.add_separator()
            sub.add_command(
                label=f"Delete '{preset.name}'",
                command=partial(self._delete_custom_preset, preset.name),
            )
        self._refresh_preset_combo()

    # ------------------------------------------------------------------
    # Bookmark management
    # ------------------------------------------------------------------

    def _bookmark_field(self, field: Literal["source", "destination"]) -> None:
        """Prompt for a name and save the current field path as a bookmark.

        Args:
            field: Which path field to bookmark — ``"source"`` or ``"destination"``.
        """
        raw_path = self.src_var.get() if field == "source" else self.dst_var.get()
        path = raw_path.strip()
        name = simpledialog.askstring(
            "Add Bookmark",
            f"Enter a name for this {field} bookmark:",
            parent=self,
        )
        if not name or not name.strip():
            return
        name_stripped = name.strip()
        if not path:
            messagebox.showerror(
                "Save Failed",
                f"Cannot bookmark an empty {field} path.",
                parent=self,
            )
            return
        if not self._bookmarks_store.add_bookmark(name_stripped, path):
            messagebox.showerror(
                "Save Failed",
                f"Bookmark '{name_stripped}' could not be saved to disk.\n"
                "Check available disk space and file permissions.",
                parent=self,
            )
            return
        self._rebuild_bookmarks_menu()

    def _rebuild_bookmarks_menu(self) -> None:
        """Repopulate the Bookmarks menu from the current bookmarks store.

        The menu always starts with two quick-bookmark commands, followed by a
        separator, then the stored bookmarks (each with a submenu offering
        "Set as source" / "Set as destination").  A disabled placeholder is
        shown when no bookmarks exist yet.  The menu is always closed by a
        separator and a "Manage Bookmarks\u2026" command.
        """
        self._bookmarks_menu.delete(0, "end")
        self._bookmarks_menu.add_command(
            label="Bookmark source path\u2026",
            command=lambda: self._bookmark_field("source"),
        )
        self._bookmarks_menu.add_command(
            label="Bookmark destination path\u2026",
            command=lambda: self._bookmark_field("destination"),
        )
        self._bookmarks_menu.add_separator()
        bookmarks = self._bookmarks_store.get_bookmarks()
        if not bookmarks:
            self._bookmarks_menu.add_command(label="(no bookmarks)", state="disabled")
        else:
            for bookmark in bookmarks:
                sub = tk.Menu(self._bookmarks_menu, tearoff=0)
                self._bookmarks_menu.add_cascade(label=bookmark.name, menu=sub)
                sub.add_command(
                    label="Set as source",
                    command=partial(self.src_var.set, bookmark.path),
                )
                sub.add_command(
                    label="Set as destination",
                    command=partial(self.dst_var.set, bookmark.path),
                )
        self._bookmarks_menu.add_separator()
        self._bookmarks_menu.add_command(
            label="Manage Bookmarks\u2026",
            command=self._open_bookmark_manager,
        )

    def _open_bookmark_manager(self) -> None:
        """Open the Bookmark Manager window (Bookmarks → Manage Bookmarks…)."""

        def _on_apply(field: str, path: str) -> None:
            if field == "source":
                self.src_var.set(path)
            else:
                self.dst_var.set(path)

        _BookmarkManagerWindow(
            self,
            store=self._bookmarks_store,
            on_change=self._rebuild_bookmarks_menu,
            on_apply=_on_apply,
        )

    def _get_selections(self) -> tuple[dict[str, bool], dict[str, tuple[bool, str]]]:
        """Return the current flag and param selections from the UI widgets."""
        flag_selections = {flag: var.get() for flag, var in self._flag_vars.items()}
        param_selections = {
            flag: (enabled_var.get(), value_var.get())
            for flag, (enabled_var, value_var, _entry) in self._param_vars.items()
        }
        return flag_selections, param_selections

    def _build_command(self) -> list[str]:
        """Assemble the robocopy command as a list of arguments."""
        src = self.src_var.get().strip()
        dst = self.dst_var.get().strip()
        flag_selections, param_selections = self._get_selections()
        file_filter = self._file_filter_var.get() if self._file_filter_enabled_var.get() else ""
        return build_command(src, dst, flag_selections, param_selections, file_filter=file_filter)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _preview(self) -> None:
        """Show the command that would be run."""
        try:
            cmd = self._build_command()
        except ValueError as exc:
            messagebox.showwarning("Missing paths", str(exc))
            return
        self._append_output("Preview command:\n  " + " ".join(cmd) + "\n")

    def _job_already_running(self) -> bool:
        """Return ``True`` and show a warning if a job is currently executing.

        Call at the top of ``_run`` and ``_dry_run`` to prevent concurrent
        subprocess launches.
        """
        if self._current_proc is not None:
            messagebox.showwarning(
                "Job Already Running",
                "A job is already running. Please wait for it to finish or cancel it.",
            )
            return True
        return False

    def _dry_run(self) -> None:
        """Validate paths and options, then run robocopy in list-only (/L) mode.

        Performs a surface-level dry run by:

        1. Checking that the source path exists as a directory.
        2. Checking that the destination path is not an existing plain file.
        3. Warning about redundant option combinations (e.g. ``/E`` alongside
           ``/MIR``).
        4. Running robocopy with ``/L`` (list only) so no files are copied or
           deleted, but the full job output is shown.

        If any validation errors are found the run is aborted and the errors
        are shown in the output panel.
        """
        if self._job_already_running():
            return

        src = self.src_var.get().strip()
        dst = self.dst_var.get().strip()
        flag_selections, param_selections = self._get_selections()
        file_filter = self._file_filter_var.get() if self._file_filter_enabled_var.get() else ""

        result = validate_command(src, dst, flag_selections, param_selections, file_filter=file_filter)
        report = result.status_report()
        if report:
            self._append_output("Dry run validation:\n" + report + "\n")

        if not result.ok:
            messagebox.showwarning("Dry Run", "Validation failed – see output for details.")
            return

        cmd = build_command(src, dst, flag_selections, param_selections, file_filter=file_filter)

        # Ensure /L is present so robocopy lists files without copying.
        if "/L" not in cmd:
            cmd.append("/L")

        self._append_output("Dry run command:\n  " + " ".join(cmd) + "\n")
        logger.info("Launching dry run: %s", " ".join(cmd))
        self._path_history.add_source(src)
        self._path_history.add_destination(dst)
        threading.Thread(target=self._execute, args=(cmd,), daemon=True).start()

    def _run(self) -> None:
        """Run robocopy in a background thread, or export a script if Script Builder is enabled."""
        if self._job_already_running():
            return

        src = self.src_var.get().strip()
        dst = self.dst_var.get().strip()
        flag_selections, param_selections = self._get_selections()
        file_filter = self._file_filter_var.get() if self._file_filter_enabled_var.get() else ""

        result = validate_command(src, dst, flag_selections, param_selections, file_filter=file_filter)
        report = result.status_report()
        if report:
            self._append_output("Pre-run validation:\n" + report + "\n")

        if not result.ok:
            messagebox.showwarning("Cannot Run", "Validation failed – see output for details.")
            return

        # ── Destructive-flag safety gate ──────────────────────────────
        # Runs after validate_command (paths are surface-checked) but before
        # build_command so the subprocess is never launched if the user cancels.
        if not _confirm_destructive_operation(dst, flag_selections, parent=self):
            self._append_output("[Aborted] User cancelled due to destructive flag warning.\n")
            return
        # ── End safety gate ───────────────────────────────────────────

        try:
            cmd = self._build_command()
        except ValueError as exc:
            messagebox.showwarning("Missing paths", str(exc))
            return

        if self._script_builder_var.get():
            self._export_script(cmd)
            return

        logger.info("Launching robocopy: %s", " ".join(cmd))
        self._append_output("Running: " + " ".join(cmd) + "\n")
        self._path_history.add_source(src)
        self._path_history.add_destination(dst)
        threading.Thread(target=self._execute, args=(cmd,), daemon=True).start()

    def _export_script(self, cmd: list[str]) -> None:
        """Open the Script Builder export dialog for the given command."""
        _ScriptExportDialog(self, cmd)

    def _execute(self, cmd: list[str]) -> None:
        """Run the async execute coroutine inside its own event loop.

        Called from a daemon thread so that the Tkinter event loop is never
        blocked.  asyncio.run() creates a fresh event loop for each job,
        which is the correct pattern when asyncio is used inside a thread.

        Skips execution if the application shutdown flag has already been set
        (e.g., the user clicked close before the thread started running).
        """
        if self._shutdown.is_set():
            return
        asyncio.run(self._async_execute(cmd))

    async def _async_execute(self, cmd: list[str]) -> None:
        """Execute the command and stream output to the console widget via the queue.

        asyncio.create_subprocess_exec is used so that I/O waits are
        non-blocking within the event loop, keeping the implementation
        aligned with the async-first preference of the codebase.
        """
        # Signal _exit() once this coroutine finishes (whether normally or by
        # exception) so that it knows the process has fully exited and can
        # safely destroy the window.
        done_event = threading.Event()
        self._proc_done_event = done_event
        # Disable Run/Dry Run buttons on the main thread while the job is active.
        self.after(0, lambda: self._set_run_buttons_state("disabled"))
        exit_code: int = -1
        try:
            # When /NJH suppresses robocopy's job header (which contains the
            # start time), record the start timestamp manually.
            if "/NJH" in cmd:
                logger.info("Job started: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            self._current_proc = proc
            assert proc.stdout is not None
            async for line_bytes in proc.stdout:
                line = line_bytes.decode(locale.getpreferredencoding(False), errors="replace")
                # Use non-blocking put_nowait so the asyncio event loop is
                # never stalled waiting for queue headroom.  Lines dropped
                # when the buffer is full are counted; _poll_output will
                # surface a notice to the user once space becomes available.
                try:
                    self._output_queue.put_nowait(line)
                except queue.Full:
                    self._dropped_lines += 1
                # Mirror every output line to the logger so the log file
                # captures the full robocopy job header and job summary.
                logger.debug("%s", line.rstrip("\n"))
            await proc.wait()
            assert proc.returncode is not None
            exit_code = proc.returncode
            self._append_output(f"\n[Process exited with code {exit_code}]\n")
            if exit_code == 0:
                logger.info("robocopy completed successfully (exit code 0)")
            else:
                logger.info("robocopy finished with exit code %d", exit_code)
            # Machine-readable footer used by _parse_log_exit_code to reliably
            # extract the exit code without relying on locale-specific strings.
            logger.debug("=== RBCOPY_METADATA: %s ===", json.dumps({"exit_code": exit_code}))

            _flush_log_handlers()
            _log_path = _get_current_log_file_path()
            if _log_path is not None:
                _summary = parse_summary_from_log(_log_path)
                if _summary is not None:
                    self._append_output(_summary.format_card())

            # When /NJS suppresses robocopy's job summary (which contains the
            # end time), record the end timestamp manually.
            if "/NJS" in cmd:
                logger.info("Job ended: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        except FileNotFoundError:
            self._append_output("[Error] 'robocopy' was not found. This application requires Windows.\n")
            logger.error("robocopy executable not found")
        except Exception as exc:  # noqa: BLE001
            self._append_output(f"[Error] {exc}\n")
            logger.exception("Unexpected error while running robocopy")
        finally:
            self._current_proc = None
            done_event.set()
            self._proc_done_event = None
            self.after(0, lambda: self._set_run_buttons_state("normal"))
            notify_job_complete(
                title="RBCopy – Job Complete",
                message=exit_code_label(exit_code),
            )

    def _set_run_buttons_state(self, state: Literal["disabled", "normal"]) -> None:
        """Enable or disable the Run, Dry Run, and Stop buttons.

        Run and Dry Run are enabled when idle; Stop is enabled only when
        a job is actively running. Must be called from the main thread.
        """
        self._btn_run.configure(state=state)
        self._btn_dry_run.configure(state=state)
        # Stop is the inverse: enabled while a job runs, disabled while idle.
        stop_state: Literal["disabled", "normal"] = "normal" if state == "disabled" else "disabled"
        self._btn_stop.configure(state=stop_state)

    def _get_log_dir(self) -> Path | None:
        """Return the directory where job log files are stored, or ``None``.

        The directory is resolved from the :class:`~logging.FileHandler`
        attached to the ``rbcopy`` logger by :func:`~rbcopy.logger.setup_logging`.
        Returns ``None`` when no file handler is present (e.g. in testing).
        """
        app_log = logging.getLogger("rbcopy")
        for handler in app_log.handlers:
            if isinstance(handler, logging.FileHandler):
                return Path(handler.baseFilename).parent
        return None

    def _open_job_history(self) -> None:
        """Open the Job History viewer (View → Job History…)."""
        log_dir = self._get_log_dir()
        if log_dir is None:
            messagebox.showinfo(
                "Job History",
                "No log directory is available yet.\n\nLaunch the application normally so that a log file is created.",
                parent=self,
            )
            return
        _JobHistoryWindow(self, log_dir)

    def _exit(self) -> None:
        """Terminate any running robocopy subprocess and close the application."""
        self._shutdown.set()
        proc = self._current_proc
        if proc is not None and proc.returncode is None:
            logger.info("Terminating running robocopy process (PID %d)", proc.pid)
            proc.terminate()
            done = self._proc_done_event
            if done is not None:
                if not done.wait(timeout=5.0):
                    logger.warning("Process did not exit within 5 s; forcibly killing it")
                    try:
                        proc.kill()
                    except OSError:
                        logger.debug("kill() failed (process may have already exited)")
        self._path_history.flush()
        self._save_geometry()
        self.destroy()

    def _stop(self) -> None:
        """Terminate the currently running robocopy subprocess.

        Sends SIGTERM (terminate) to the process. The existing _async_execute
        finally block handles cleanup: clearing _current_proc, signalling
        _proc_done_event, and re-enabling the Run/Dry Run buttons.
        """
        proc = self._current_proc
        if proc is None or proc.returncode is not None:
            return
        logger.info("User requested stop; terminating robocopy process (PID %d)", proc.pid)
        self._append_output("\n[Job cancelled by user]\n")
        try:
            proc.terminate()
        except OSError:
            logger.debug("terminate() failed; process may have already exited")

    def _append_output(self, text: str) -> None:
        """Enqueue *text* for display in the output console.

        Thread-safe: may be called from the Tkinter main thread or from the
        background asyncio thread.  Uses ``put_nowait`` so the caller is never
        blocked; if the queue is full the line is silently dropped and
        ``_dropped_lines`` is incremented so that ``_poll_output`` can surface
        a notice to the user.
        """
        try:
            self._output_queue.put_nowait(text)
        except queue.Full:
            self._dropped_lines += 1

    def _poll_output(self) -> None:
        """Drain the output queue and write any pending text to the console.

        Scheduled repeatedly via :py:meth:`after` so it always runs on the
        main thread, preventing concurrent Tkinter widget access from worker
        threads.

        At most :data:`_MAX_LINES_PER_POLL` lines are consumed per cycle so
        that a burst of robocopy output cannot block the event loop long enough
        to freeze the GUI.  Any remaining lines are processed in subsequent
        cycles.  Collected lines are written in a single batched call to avoid
        repeated enable/disable toggling of the output widget.
        """
        lines: list[str] = []
        try:
            for _ in range(_MAX_LINES_PER_POLL):
                lines.append(self._output_queue.get_nowait())
        except queue.Empty:
            pass
        if lines:
            self._write_output("".join(lines))
        # After draining, inject a notice if any lines were dropped since the
        # last poll cycle.  Done after draining to maximise queue headroom.
        # Read then reset so a concurrent increment loses at most one count.
        dropped = self._dropped_lines
        if dropped > 0:
            self._dropped_lines = 0
            try:
                self._output_queue.put_nowait(f"[{dropped} line(s) dropped — output buffer full]\n")
            except queue.Full:
                # Queue still full; restore the counter so we retry next cycle.
                self._dropped_lines += dropped
        # Reschedule; 100 ms keeps the UI responsive without burning CPU.
        self.after(100, self._poll_output)

    def _write_output(self, text: str) -> None:
        self._output.config(state="normal")
        self._output.insert("end", text)
        self._output.see("end")
        self._output.config(state="disabled")

    def _clear_output(self) -> None:
        self._output.config(state="normal")
        self._output.delete("1.0", "end")
        self._output.config(state="disabled")

    def _apply_preferences(self) -> None:
        """Apply stored preference defaults to the /MT, /R, and /W param fields.

        Called once at startup and again whenever preferences are saved so
        the entry fields always reflect the user's chosen defaults.  Only
        the *value* StringVar is touched — the enabled checkbox is left
        untouched so the user retains full control over which flags are active.
        """
        prefs = self._prefs_store.preferences
        param_overrides = {
            "/MT": str(prefs.default_thread_count),
            "/R": str(prefs.default_retry_count),
            "/W": str(prefs.default_wait_seconds),
        }
        for flag, value in param_overrides.items():
            if flag in self._param_vars:
                _, value_var, _ = self._param_vars[flag]
                value_var.set(value)

    def _open_preferences(self) -> None:
        """Open the Preferences dialog (File → Preferences…)."""
        _PreferencesDialog(
            parent=self,
            store=self._prefs_store,
            on_saved=self._apply_preferences,
            on_clear_history=self._clear_path_history,
            on_clear_bookmarks=self._clear_bookmarks,
        )

    def _clear_path_history(self) -> None:
        """Erase all path history and refresh the Combobox dropdowns."""
        self._path_history.clear()
        self._src_entry["values"] = []
        self._dst_entry["values"] = []

    def _clear_bookmarks(self) -> None:
        """Erase all bookmarks and rebuild the Bookmarks menu."""
        self._bookmarks_store.clear()
        self._rebuild_bookmarks_menu()
