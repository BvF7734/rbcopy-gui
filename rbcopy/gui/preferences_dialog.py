"""Preferences dialog for configuring rbcopy application settings."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from logging import getLogger
from tkinter import messagebox, ttk

from rbcopy.gui.types import _PackPadding
from rbcopy.preferences import AppPreferences, PreferencesStore

logger = getLogger("rbcopy.gui")


class _PreferencesDialog(tk.Toplevel):
    """Modal dialog for editing application preferences.

    Presents four fields grouped into two sections:

    * **Robocopy Defaults** – default values written into the ``/MT``, ``/R``,
      and ``/W`` param entry fields when the application starts or after
      preferences are saved.
    * **Logging** – the number of session log files to retain on disk before
      the oldest are pruned.

    After the user clicks *Save* the preferences are written to disk, the
    ``on_saved`` callback is invoked so the main window can refresh its
    widgets, and the dialog closes.  Clicking *Cancel* closes the dialog
    without making any changes.

    Args:
        parent: The parent Tk widget (the main window).
        store: The :class:`~rbcopy.preferences.PreferencesStore` instance
            that owns the preferences file.
        on_saved: Zero-argument callable invoked after a successful save so
            the caller can react (e.g. re-apply defaults to param fields).
        on_clear_history: Optional zero-argument callable invoked when the
            user confirms "Reset path history".  The caller is responsible
            for flushing the in-memory store and refreshing any dropdowns.
        on_clear_bookmarks: Optional zero-argument callable invoked when the
            user confirms "Reset bookmarks".
    """

    _THREAD_MIN: int = 1
    _THREAD_MAX: int = 128
    _RETRY_MIN: int = 0
    _RETRY_MAX: int = 1_000_000
    _WAIT_MIN: int = 0
    _WAIT_MAX: int = 3600
    _LOG_MIN: int = 1
    _LOG_MAX: int = 1000

    def __init__(
        self,
        parent: tk.Misc,
        store: PreferencesStore,
        on_saved: Callable[[], None],
        on_clear_history: Callable[[], None] | None = None,
        on_clear_bookmarks: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("Preferences")
        self.resizable(False, False)
        self._store = store
        self._on_saved = on_saved
        self._on_clear_history = on_clear_history
        self._on_clear_bookmarks = on_clear_bookmarks
        self._saved: bool = False

        prefs = store.preferences
        self._thread_var = tk.StringVar(value=str(prefs.default_thread_count))
        self._retry_var = tk.StringVar(value=str(prefs.default_retry_count))
        self._wait_var = tk.StringVar(value=str(prefs.default_wait_seconds))
        self._log_var = tk.StringVar(value=str(prefs.log_retention_count))

        self._build_ui()
        self.transient(parent)  # type: ignore[call-overload]
        self.grab_set()
        self.wait_window()

    @property
    def saved(self) -> bool:
        """``True`` if preferences were successfully saved; ``False`` if cancelled."""
        return self._saved

    def _build_ui(self) -> None:
        """Assemble the dialog widgets."""
        padding: _PackPadding = {"padx": 8, "pady": 4}

        # ── Robocopy defaults ─────────────────────────────────────────
        rc_frame = ttk.LabelFrame(self, text="Robocopy Defaults", padding=6)
        rc_frame.pack(fill="x", **padding)
        rc_frame.columnconfigure(1, weight=1)

        self._add_field(rc_frame, 0, "Thread count  /MT:", self._thread_var, f"1–{self._THREAD_MAX}")
        self._add_field(rc_frame, 1, "Retry count  /R:", self._retry_var, "0–1 000 000")
        self._add_field(rc_frame, 2, "Wait seconds  /W:", self._wait_var, f"0–{self._WAIT_MAX}")

        # ── Logging ──────────────────────────────────────────────
        log_frame = ttk.LabelFrame(self, text="Logging", padding=6)
        log_frame.pack(fill="x", **padding)
        log_frame.columnconfigure(1, weight=1)

        self._add_field(log_frame, 0, "Log files to keep:", self._log_var, f"1–{self._LOG_MAX}")

        # ── Data ─────────────────────────────────────────────────
        data_frame = ttk.LabelFrame(self, text="Data", padding=6)
        data_frame.pack(fill="x", **padding)

        ttk.Button(
            data_frame,
            text="Reset path history…",
            command=self._on_reset_history,
            state="normal" if self._on_clear_history else "disabled",
        ).pack(anchor="w", pady=2, fill="x")
        ttk.Button(
            data_frame,
            text="Reset bookmarks…",
            command=self._on_reset_bookmarks,
            state="normal" if self._on_clear_bookmarks else "disabled",
        ).pack(anchor="w", pady=2, fill="x")

        # ── Buttons ───────────────────────────────────────────────────
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=8, pady=(8, 8))
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="right", padx=(4, 0))
        ttk.Button(btn_frame, text="Save", command=self._on_save).pack(side="right")

    @staticmethod
    def _add_field(
        parent: ttk.LabelFrame,
        row: int,
        label: str,
        var: tk.StringVar,
        hint: str,
    ) -> None:
        """Add a labelled entry row to *parent* at *row*."""
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(parent, textvariable=var, width=12).grid(row=row, column=1, sticky="w", padx=(8, 0))
        ttk.Label(parent, text=f"({hint})", foreground="gray").grid(row=row, column=2, sticky="w", padx=(6, 0))

    def _parse_int(
        self,
        var: tk.StringVar,
        label: str,
        min_val: int,
        max_val: int,
    ) -> int | None:
        """Parse and range-check a single integer field.

        Shows a warning dialog and returns ``None`` on the first error
        encountered so the user can correct one problem at a time.

        Args:
            var: The :class:`~tkinter.StringVar` whose value is parsed.
            label: Human-readable field name used in the warning message.
            min_val: Inclusive lower bound.
            max_val: Inclusive upper bound.

        Returns:
            The parsed integer, or ``None`` if parsing or range validation
            failed.
        """
        raw = var.get().strip()
        try:
            value = int(raw)
        except ValueError:
            messagebox.showwarning(
                "Invalid Value",
                f"{label} must be a whole number.",
                parent=self,
            )
            return None
        if not (min_val <= value <= max_val):
            messagebox.showwarning(
                "Invalid Value",
                f"{label} must be between {min_val:,} and {max_val:,}.",
                parent=self,
            )
            return None
        return value

    def _on_save(self) -> None:
        """Validate all fields, persist preferences, invoke the callback, and close."""
        thread_count = self._parse_int(self._thread_var, "Thread count", self._THREAD_MIN, self._THREAD_MAX)
        if thread_count is None:
            return

        retry_count = self._parse_int(self._retry_var, "Retry count", self._RETRY_MIN, self._RETRY_MAX)
        if retry_count is None:
            return

        wait_seconds = self._parse_int(self._wait_var, "Wait seconds", self._WAIT_MIN, self._WAIT_MAX)
        if wait_seconds is None:
            return

        log_retention = self._parse_int(self._log_var, "Log files to keep", self._LOG_MIN, self._LOG_MAX)
        if log_retention is None:
            return

        new_prefs = AppPreferences(
            default_thread_count=thread_count,
            default_retry_count=retry_count,
            default_wait_seconds=wait_seconds,
            log_retention_count=log_retention,
        )

        if not self._store.save(new_prefs):
            messagebox.showerror(
                "Save Failed",
                "Preferences could not be saved to disk.\nCheck available disk space and file permissions.",
                parent=self,
            )
            return

        logger.info("Preferences saved: %s", new_prefs.model_dump())
        self._saved = True
        self._on_saved()
        self.destroy()

    def _on_reset_history(self) -> None:
        """Ask for confirmation, then invoke the clear-history callback."""
        if self._on_clear_history is None:
            return
        confirmed = messagebox.askyesno(
            "Reset Path History",
            "Clear all saved source and destination path history?\n\nThis cannot be undone.",
            icon=messagebox.WARNING,
            default=messagebox.NO,
            parent=self,
        )
        if confirmed:
            self._on_clear_history()
            messagebox.showinfo("Done", "Path history has been cleared.", parent=self)

    def _on_reset_bookmarks(self) -> None:
        """Ask for confirmation, then invoke the clear-bookmarks callback."""
        if self._on_clear_bookmarks is None:
            return
        confirmed = messagebox.askyesno(
            "Reset Bookmarks",
            "Delete all saved bookmarks?\n\nThis cannot be undone.",
            icon=messagebox.WARNING,
            default=messagebox.NO,
            parent=self,
        )
        if confirmed:
            self._on_clear_bookmarks()
            messagebox.showinfo("Done", "All bookmarks have been deleted.", parent=self)
