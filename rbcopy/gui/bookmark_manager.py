"""Bookmark manager window for the RbCopy GUI.

Provides :class:`_BookmarkManagerWindow`, a non-modal Toplevel that lets the
user view, add, edit, delete, and reorder named path bookmarks.  Any change
is immediately persisted via the :class:`~rbcopy.bookmarks.BookmarksStore`
and, when an *on_change* callback is supplied, the caller is notified so it
can, for example, rebuild the Bookmarks menu.
"""

from __future__ import annotations

import tkinter as tk
from logging import getLogger
from tkinter import messagebox, ttk
from typing import Callable

from rbcopy.bookmarks import Bookmark, BookmarksStore

logger = getLogger(__name__)


class _EditBookmarkDialog(tk.Toplevel):
    """Modal dialog for adding or editing a single bookmark.

    After construction the dialog blocks (via ``wait_window``) until the user
    either confirms or cancels.  Inspect :attr:`name` and :attr:`path` once
    the constructor returns.

    Args:
        parent: The parent Tk widget.
        initial_name: Pre-filled name value (used when editing).
        initial_path: Pre-filled path value (used when editing).
    """

    def __init__(
        self,
        parent: tk.Misc,
        initial_name: str = "",
        initial_path: str = "",
    ) -> None:
        super().__init__(parent)
        self.title("Edit Bookmark" if initial_name else "Add Bookmark")
        self.resizable(False, False)

        self._name_var = tk.StringVar(value=initial_name)
        self._path_var = tk.StringVar(value=initial_path)
        self._confirmed: bool = False

        self._build_ui()
        self.transient(parent)  # type: ignore[call-overload]
        self.grab_set()
        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self._cancel())
        self.wait_window()

    @property
    def name(self) -> str | None:
        """The entered name, or *None* if the dialog was cancelled."""
        return self._name_var.get().strip() if self._confirmed else None

    @property
    def path(self) -> str:
        """The entered path (stripped)."""
        return self._path_var.get().strip()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)

        ttk.Label(frame, text="Name:").grid(row=0, column=0, sticky="w")
        name_entry = ttk.Entry(frame, textvariable=self._name_var, width=44)
        name_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        name_entry.focus_set()

        ttk.Label(frame, text="Path:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self._path_var, width=44).grid(
            row=1, column=1, sticky="ew", padx=(8, 0), pady=(8, 0)
        )

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=(12, 0), sticky="e")
        ttk.Button(btn_frame, text="OK", command=self._ok).pack(side="right", padx=(4, 0))
        ttk.Button(btn_frame, text="Cancel", command=self._cancel).pack(side="right")

        frame.columnconfigure(1, weight=1)

    def _ok(self) -> None:
        if not self._name_var.get().strip():
            messagebox.showwarning("Name Required", "Please enter a bookmark name.", parent=self)
            return
        self._confirmed = True
        self.destroy()

    def _cancel(self) -> None:
        self.destroy()


class _BookmarkManagerWindow(tk.Toplevel):
    """Non-modal window for viewing and managing saved bookmarks.

    Displays all bookmarks as rows in a :class:`~tkinter.ttk.Treeview` with
    *Name* and *Path* columns.  The toolbar exposes Add, Edit, Delete, Move Up
    and Move Down actions.  Buttons at the bottom let the user apply a selected
    bookmark directly to the source or destination field in the calling window.

    Any mutation is immediately persisted through *store* and *on_change* is
    called so the Bookmarks menu in the parent window is kept up to date.

    Args:
        parent:    Parent Tk widget (the main window).
        store:     Live :class:`BookmarksStore` shared with the main window.
        on_change: Optional callable invoked after every successful mutation so
                   that callers can, for example, rebuild their Bookmarks menu.
        on_apply:  Optional callable called with ``(field, path)`` when the
                   user clicks "Set as Source" or "Set as Destination".
                   *field* is either ``"source"`` or ``"destination"``.
    """

    _NAME_COL = "name"
    _PATH_COL = "path"

    def __init__(
        self,
        parent: tk.Misc,
        store: BookmarksStore,
        on_change: Callable[[], None] | None = None,
        on_apply: Callable[[str, str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("Bookmark Manager")
        self.minsize(620, 350)
        self._store = store
        self._on_change = on_change
        self._on_apply = on_apply

        self._build_ui()
        self._refresh()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Assemble the bookmark manager widgets."""

        # ── Toolbar ───────────────────────────────────────────────────
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=8, pady=(8, 0))

        ttk.Button(toolbar, text="Add…", command=self._add).pack(side="left", padx=(0, 2))
        ttk.Button(toolbar, text="Edit…", command=self._edit).pack(side="left", padx=(0, 2))
        ttk.Button(toolbar, text="Delete", command=self._delete).pack(side="left", padx=(0, 8))
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", pady=2, padx=(0, 8))
        ttk.Button(toolbar, text="▲  Move Up", command=self._move_up).pack(side="left", padx=(0, 2))
        ttk.Button(toolbar, text="▼  Move Down", command=self._move_down).pack(side="left")

        # ── Treeview ──────────────────────────────────────────────────
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=8, pady=(6, 0))

        columns = (self._NAME_COL, self._PATH_COL)
        self._tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        self._tree.heading(self._NAME_COL, text="Name")
        self._tree.heading(self._PATH_COL, text="Path")
        self._tree.column(self._NAME_COL, width=200, stretch=False)
        self._tree.column(self._PATH_COL, width=380)

        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=tree_scroll.set)
        self._tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        self._tree.bind("<Double-1>", lambda _e: self._edit())
        self._tree.bind("<Return>", lambda _e: self._edit())
        self._tree.bind("<Delete>", lambda _e: self._delete())

        # ── Apply buttons ─────────────────────────────────────────────
        apply_frame = ttk.Frame(self)
        apply_frame.pack(fill="x", padx=8, pady=8)

        ttk.Button(apply_frame, text="Set as Source", command=self._set_as_source).pack(side="left", padx=(0, 4))
        ttk.Button(apply_frame, text="Set as Destination", command=self._set_as_destination).pack(side="left")
        ttk.Button(apply_frame, text="Close", command=self.destroy).pack(side="right")

    # ------------------------------------------------------------------
    # Data refresh
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        """Repopulate the treeview from the store.

        The current selection is preserved by name when the selected bookmark
        still exists after the refresh.
        """
        # Remember which name was selected so we can re-select it.
        selected_name: str | None = None
        selection = self._tree.selection()
        if selection:
            selected_name = self._tree.set(selection[0], self._NAME_COL)

        children = self._tree.get_children()
        if children:
            self._tree.delete(*children)

        bookmarks = self._store.get_bookmarks()
        if not bookmarks:
            self._tree.insert("", "end", values=("(no bookmarks)", ""))
            return

        target_iid: str | None = None
        for bookmark in bookmarks:
            iid = self._tree.insert("", "end", values=(bookmark.name, bookmark.path))
            if bookmark.name == selected_name:
                target_iid = iid

        if target_iid is not None:
            self._tree.selection_set(target_iid)
            self._tree.see(target_iid)

    # ------------------------------------------------------------------
    # Selection helpers
    # ------------------------------------------------------------------

    def _selected_index(self) -> int | None:
        """Return the 0-based index of the currently selected row, or *None*."""
        selection = self._tree.selection()
        if not selection:
            return None
        children = self._tree.get_children()
        try:
            return list(children).index(selection[0])
        except ValueError:
            return None

    def _selected_bookmark(self) -> Bookmark | None:
        """Return the :class:`Bookmark` for the currently selected row, or *None*."""
        selection = self._tree.selection()
        if not selection:
            return None
        name = self._tree.set(selection[0], self._NAME_COL)
        return self._store.get_bookmark(name)

    # ------------------------------------------------------------------
    # CRUD actions
    # ------------------------------------------------------------------

    def _add(self) -> None:
        """Open the Add Bookmark dialog and persist the new entry."""
        dlg = _EditBookmarkDialog(self)
        if dlg.name is None:
            return

        if not self._store.add_bookmark(dlg.name, dlg.path):
            messagebox.showerror(
                "Save Failed",
                "The bookmark could not be saved to disk.\nCheck available disk space and file permissions.",
                parent=self,
            )
            return

        self._notify_change()
        self._refresh()
        self._select_by_name(dlg.name)

    def _edit(self) -> None:
        """Open the Edit Bookmark dialog for the currently selected bookmark."""
        bookmark = self._selected_bookmark()
        if bookmark is None:
            return

        # Check for the placeholder row that appears when the store is empty.
        if bookmark.name == "(no bookmarks)":
            return

        original_name = bookmark.name
        dlg = _EditBookmarkDialog(self, initial_name=bookmark.name, initial_path=bookmark.path)
        if dlg.name is None:
            return

        new_name = dlg.name
        new_path = dlg.path

        # If the name changed, remove the old entry first so the new name
        # takes the same position.  We persist by rebuilding the full list.
        bookmarks = self._store.get_bookmarks()
        updated: list[Bookmark] = []
        for b in bookmarks:
            if b.name == original_name:
                try:
                    updated.append(Bookmark(name=new_name, path=new_path))
                except ValueError as exc:
                    messagebox.showerror("Invalid Input", str(exc), parent=self)
                    return
            else:
                updated.append(b)

        if not self._store.replace_all(updated):
            messagebox.showerror(
                "Save Failed",
                "The bookmark could not be saved to disk.\nCheck available disk space and file permissions.",
                parent=self,
            )
            return

        self._notify_change()
        self._refresh()
        self._select_by_name(new_name)

    def _delete(self) -> None:
        """Delete the currently selected bookmark after confirmation."""
        bookmark = self._selected_bookmark()
        if bookmark is None:
            return
        if bookmark.name == "(no bookmarks)":
            return

        confirmed = messagebox.askyesno(
            "Delete Bookmark",
            f'Delete bookmark "{bookmark.name}"?',
            default=messagebox.NO,
            parent=self,
        )
        if not confirmed:
            return

        self._store.remove_bookmark(bookmark.name)
        self._notify_change()
        self._refresh()

    # ------------------------------------------------------------------
    # Reorder actions
    # ------------------------------------------------------------------

    def _move_up(self) -> None:
        """Move the selected bookmark one position up in the list."""
        idx = self._selected_index()
        if idx is None or idx == 0:
            return

        bookmarks = self._store.get_bookmarks()
        bookmarks.insert(idx - 1, bookmarks.pop(idx))

        if not self._store.replace_all(bookmarks):
            messagebox.showerror(
                "Save Failed",
                "The bookmark order could not be saved to disk.",
                parent=self,
            )
            return

        self._notify_change()
        self._refresh()

    def _move_down(self) -> None:
        """Move the selected bookmark one position down in the list."""
        idx = self._selected_index()
        bookmarks = self._store.get_bookmarks()
        if idx is None or idx >= len(bookmarks) - 1:
            return

        bookmarks.insert(idx + 1, bookmarks.pop(idx))

        if not self._store.replace_all(bookmarks):
            messagebox.showerror(
                "Save Failed",
                "The bookmark order could not be saved to disk.",
                parent=self,
            )
            return

        self._notify_change()
        self._refresh()

    # ------------------------------------------------------------------
    # Apply actions
    # ------------------------------------------------------------------

    def _set_as_source(self) -> None:
        """Apply the selected bookmark's path to the source field."""
        bookmark = self._selected_bookmark()
        if bookmark is None or bookmark.name == "(no bookmarks)":
            return
        if self._on_apply is not None:
            self._on_apply("source", bookmark.path)

    def _set_as_destination(self) -> None:
        """Apply the selected bookmark's path to the destination field."""
        bookmark = self._selected_bookmark()
        if bookmark is None or bookmark.name == "(no bookmarks)":
            return
        if self._on_apply is not None:
            self._on_apply("destination", bookmark.path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _notify_change(self) -> None:
        """Invoke the on_change callback if one was provided."""
        if self._on_change is not None:
            self._on_change()

    def _select_by_name(self, name: str) -> None:
        """Select the treeview row whose Name column matches *name*."""
        for iid in self._tree.get_children():
            if self._tree.set(iid, self._NAME_COL) == name:
                self._tree.selection_set(iid)
                self._tree.see(iid)
                return
