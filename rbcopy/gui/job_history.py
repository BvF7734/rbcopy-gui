"""Job history viewer window and log-file parsing helpers."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from logging import getLogger
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Any

from rbcopy.builder import exit_code_label

logger = getLogger("rbcopy.gui.job_history")

# ---------------------------------------------------------------------------
# Log file parsing helpers
# ---------------------------------------------------------------------------

_LOG_FILENAME_PREFIX = "robocopy_job_"
_LOG_FILENAME_PATTERN = f"{_LOG_FILENAME_PREFIX}*.log"
_LOG_DATE_FORMAT = "%Y%m%d_%H%M%S"

_MAX_LOG_PREVIEW_BYTES: int = 512 * 1024

_EXIT_CODE_RE = re.compile(
    r"rbcopy\.\w+: robocopy (?:finished with exit code (\d+)"
    r"|completed successfully \(exit code (\d+)\))"
)

_METADATA_TAG = "=== RBCOPY_METADATA:"
_METADATA_RE = re.compile(r"=== RBCOPY_METADATA: (.+?) ===")


def _parse_log_exit_code(log_path: Path) -> int | None:
    """Return the last Robocopy exit code recorded in *log_path*, or ``None``."""
    last_exit_code: int | None = None
    try:
        with log_path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if _METADATA_TAG in line:
                    m = _METADATA_RE.search(line)
                    if m:
                        try:
                            payload = json.loads(m.group(1))
                        except ValueError:
                            logger.debug("Failed to parse RBCOPY_METADATA JSON in %s", log_path)
                            continue
                        try:
                            last_exit_code = int(payload["exit_code"])
                        except (KeyError, TypeError, ValueError):
                            logger.debug(
                                "RBCOPY_METADATA payload has missing or invalid 'exit_code' in %s",
                                log_path,
                            )
                    continue
                m = _EXIT_CODE_RE.search(line)
                if m:
                    raw = m.group(1) or m.group(2)
                    last_exit_code = int(raw)
    except OSError:
        return None
    return last_exit_code


# ---------------------------------------------------------------------------
# Job history viewer window
# ---------------------------------------------------------------------------


class _JobHistoryWindow(tk.Toplevel):
    """Non-modal window listing past robocopy job log files with search and filter."""

    _DATE_COL = "date"
    _CODE_COL = "exit_code"
    _STATUS_COL = "status"

    # Highlight tag name used by the content search feature.
    _SEARCH_TAG = "search_highlight"

    def __init__(self, parent: tk.Misc, log_dir: Path) -> None:
        super().__init__(parent)
        self.title("Job History")
        self.minsize(900, 500)
        self._log_dir = log_dir
        self._log_file_map: dict[str, Path] = {}
        self._refresh_generation: int = 0

        # Stores the full unfiltered list produced by _refresh() so that
        # _apply_tree_filter() can re-derive filtered rows without re-scanning
        # the directory.  Each entry is (iid, date_display, path).
        self._all_entries: list[tuple[str, str, Path]] = []

        # Cache of already-resolved (code_display, status) values keyed by iid.
        # Populated by the background parse worker; consulted by _apply_tree_filter
        # so that re-filtering after the worker finishes does not revert cells to "…".
        self._resolved: dict[str, tuple[str, str]] = {}

        self._build_ui()
        self._refresh()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Assemble the history viewer widgets."""

        # ── Toolbar (row 0) ──────────────────────────────────────────
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=8, pady=(8, 0))
        ttk.Label(toolbar, text=f"Log directory:  {self._log_dir}").pack(side="left")
        ttk.Button(toolbar, text="Refresh", command=self._refresh).pack(side="right")
        ttk.Button(toolbar, text="Open in editor", command=self._open_externally).pack(side="right", padx=(0, 4))
        ttk.Button(toolbar, text="Export log…", command=self._export_log).pack(side="right", padx=(0, 4))

        # ── File-list filter bar (row 1) ─────────────────────────────
        filter_frame = ttk.Frame(self)
        filter_frame.pack(fill="x", padx=8, pady=(4, 0))

        ttk.Label(filter_frame, text="Filter:").pack(side="left")

        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", lambda *_: self._apply_tree_filter())
        filter_entry = ttk.Entry(filter_frame, textvariable=self._filter_var, width=20)
        filter_entry.pack(side="left", padx=(4, 12))

        ttk.Label(filter_frame, text="From:").pack(side="left")
        self._date_from_var = tk.StringVar()
        self._date_from_var.trace_add("write", lambda *_: self._apply_tree_filter())
        ttk.Entry(filter_frame, textvariable=self._date_from_var, width=12).pack(side="left", padx=(4, 0))
        ttk.Label(filter_frame, text="YYYY-MM-DD", foreground="gray").pack(side="left", padx=(2, 12))

        ttk.Label(filter_frame, text="To:").pack(side="left")
        self._date_to_var = tk.StringVar()
        self._date_to_var.trace_add("write", lambda *_: self._apply_tree_filter())
        ttk.Entry(filter_frame, textvariable=self._date_to_var, width=12).pack(side="left", padx=(4, 0))
        ttk.Label(filter_frame, text="YYYY-MM-DD", foreground="gray").pack(side="left", padx=(2, 12))

        ttk.Button(filter_frame, text="Clear", command=self._clear_filter).pack(side="left")

        # Filter match counter (updated by _apply_tree_filter).
        self._filter_count_var = tk.StringVar(value="")
        ttk.Label(filter_frame, textvariable=self._filter_count_var, foreground="gray").pack(side="left", padx=(8, 0))

        # ── Horizontal split pane (row 2) ────────────────────────────
        pane = ttk.PanedWindow(self, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=8, pady=8)

        # ── Left: scrollable job list ─────────────────────────────────
        list_frame = ttk.Frame(pane)
        pane.add(list_frame, weight=1)

        columns = (self._DATE_COL, self._CODE_COL, self._STATUS_COL)
        self._tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        self._tree.heading(self._DATE_COL, text="Date / Time")
        self._tree.heading(self._CODE_COL, text="Exit Code")
        self._tree.heading(self._STATUS_COL, text="Status")
        self._tree.column(self._DATE_COL, width=160, stretch=False)
        self._tree.column(self._CODE_COL, width=80, anchor="center", stretch=False)
        self._tree.column(self._STATUS_COL, width=200)

        tree_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=tree_scroll.set)
        self._tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # ── Right: log content with search bar ───────────────────────
        content_frame = ttk.LabelFrame(pane, text="Log Content", padding=4)
        pane.add(content_frame, weight=2)

        # Search bar inside the content frame, above the text widget.
        search_bar = ttk.Frame(content_frame)
        search_bar.pack(fill="x", pady=(0, 4))

        ttk.Label(search_bar, text="Search:").pack(side="left")

        self._search_var = tk.StringVar()
        search_entry = ttk.Entry(search_bar, textvariable=self._search_var, width=24)
        search_entry.pack(side="left", padx=(4, 4))
        # Pressing Enter runs a forward search.
        search_entry.bind("<Return>", lambda _e: self._search_next())

        ttk.Button(search_bar, text="Find", command=self._search_next).pack(side="left", padx=(0, 2))
        ttk.Button(search_bar, text="▲", width=2, command=self._search_prev).pack(side="left", padx=(0, 2))
        ttk.Button(search_bar, text="▼", width=2, command=self._search_next).pack(side="left", padx=(0, 8))
        ttk.Button(search_bar, text="Clear", command=self._clear_search).pack(side="left")

        # Match counter label.
        self._search_count_var = tk.StringVar(value="")
        ttk.Label(search_bar, textvariable=self._search_count_var, foreground="gray").pack(side="left", padx=(8, 0))

        # The log content text widget.
        self._content = scrolledtext.ScrolledText(
            content_frame,
            state="disabled",
            wrap="none",
            font=("Courier New", 9),
        )
        self._content.pack(fill="both", expand=True)

        # Configure the highlight tag used by content search.
        self._content.tag_configure(
            self._SEARCH_TAG,
            background="#FFC107",
            foreground="#000000",
        )

        # Internal state for content search navigation.
        # Stores (start_index, end_index) tuples for every current match.
        self._search_matches: list[tuple[str, str]] = []
        self._search_current: int = -1

    # ------------------------------------------------------------------
    # File-list filter
    # ------------------------------------------------------------------

    def _apply_tree_filter(self) -> None:
        """Repopulate the tree using only entries that match the current filter.

        Three filter conditions are applied together (AND logic):

        * **Keyword** — the date/time display string must contain the keyword
          (case-insensitive).  This lets users type e.g. "2024-06" to see
          only June 2024 sessions.
        * **From date** — the session date must be on or after this date.
        * **To date** — the session date must be on or before this date.

        Any filter field that is empty or contains an unparseable date is
        ignored so partial input does not hide all rows.
        """
        keyword = self._filter_var.get().strip().lower()
        from_str = self._date_from_var.get().strip()
        to_str = self._date_to_var.get().strip()

        date_from: datetime | None = None
        date_to: datetime | None = None
        try:
            if from_str:
                date_from = datetime.strptime(from_str, "%Y-%m-%d")
        except ValueError:
            pass
        try:
            if to_str:
                date_to = datetime.strptime(to_str, "%Y-%m-%d")
        except ValueError:
            pass

        # Clear the tree and the iid→path map.
        children = self._tree.get_children()
        if children:
            self._tree.delete(*children)
        self._log_file_map.clear()

        if not self._all_entries:
            self._tree.insert("", "end", values=("No log files found", "", ""))
            self._filter_count_var.set("")
            return

        matched: list[tuple[str, str, Path]] = []
        for iid, date_display, path in self._all_entries:
            # Keyword check (matches against the displayed date string).
            if keyword and keyword not in date_display.lower():
                continue

            # Date range check — parse the date from the filename stem.
            if date_from is not None or date_to is not None:
                stem = path.stem  # e.g. "robocopy_job_20240601_120000"
                dt_str = stem[len(_LOG_FILENAME_PREFIX) :]
                try:
                    entry_date = datetime.strptime(dt_str, _LOG_DATE_FORMAT)
                except ValueError:
                    # Unparseable filename: include it (don't silently hide it).
                    pass
                else:
                    if date_from is not None and entry_date < date_from:
                        continue
                    if date_to is not None and entry_date.date() > date_to.date():
                        continue

            matched.append((iid, date_display, path))

        if not matched:
            self._tree.insert("", "end", values=("No matching log files", "", ""))
            self._filter_count_var.set("0 matches")
            return

        # Re-insert matching rows, re-using the original iids so that the
        # background exit-code update workers (which key on iid) still work.
        # Use already-resolved values when available so that re-filtering after
        # the worker completes does not revert cells to placeholder "…".
        for iid, date_display, path in matched:
            code_display, status = self._resolved.get(iid, ("…", "…"))
            new_iid = self._tree.insert("", "end", iid=iid, values=(date_display, code_display, status))
            self._log_file_map[new_iid] = path

        total = len(self._all_entries)
        shown = len(matched)
        self._filter_count_var.set("" if shown == total else f"{shown} of {total}")

    def _clear_filter(self) -> None:
        """Reset all filter fields and show the full file list."""
        self._filter_var.set("")
        self._date_from_var.set("")
        self._date_to_var.set("")
        self._filter_count_var.set("")

    # ------------------------------------------------------------------
    # Content search
    # ------------------------------------------------------------------

    def _search_next(self) -> None:
        """Move to the next search match, wrapping at end of file."""
        self._run_search(forward=True)

    def _search_prev(self) -> None:
        """Move to the previous search match, wrapping at start of file."""
        self._run_search(forward=False)

    def _run_search(self, *, forward: bool) -> None:
        """Highlight all occurrences of the search term and navigate.

        The previous cursor position is preserved across calls so that
        repeated presses of the \u25b2/\u25bc buttons step through matches one
        at a time rather than always landing on the first or last match.
        """
        term = self._search_var.get()
        if not term:
            self._clear_search()
            return

        # Capture the cursor position BEFORE rebuilding the match list so
        # that navigation arithmetic is relative to where the user was.
        prev_current = self._search_current

        self._content.tag_remove(self._SEARCH_TAG, "1.0", "end")
        self._search_matches = []

        # Find all matches throughout the document.
        start = "1.0"
        while True:
            pos = self._content.search(term, start, stopindex="end", nocase=True)
            if not pos:
                break
            end_pos = f"{pos}+{len(term)}c"
            self._content.tag_add(self._SEARCH_TAG, pos, end_pos)
            self._search_matches.append((pos, end_pos))
            start = end_pos

        count = len(self._search_matches)
        if count == 0:
            self._search_current = -1
            self._search_count_var.set("0 matches")
            return

        # Advance the cursor.  When no position is current (prev == -1),
        # the down arrow goes to the first match and the up arrow goes to
        # the last -- the most natural behaviour when starting a search.
        if forward:
            self._search_current = (prev_current + 1) % count
        else:
            if prev_current == -1:
                self._search_current = count - 1
            else:
                self._search_current = (prev_current - 1) % count

        self._scroll_to_match(self._search_current)
        self._search_count_var.set(f"{self._search_current + 1} of {count}")

    def _scroll_to_match(self, index: int) -> None:
        """Scroll the content pane to the match at *index* and select it."""
        if not self._search_matches:
            return
        start, end = self._search_matches[index]
        self._content.see(start)
        self._content.mark_set("insert", start)

    def _clear_search(self) -> None:
        """Remove all search highlights and reset the search state."""
        self._content.tag_remove(self._SEARCH_TAG, "1.0", "end")
        self._search_matches = []
        self._search_current = -1
        self._search_var.set("")
        self._search_count_var.set("")

    # ------------------------------------------------------------------
    # Refresh / populate
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        """Re-scan the log directory and repopulate the job list.

        Stores the full unfiltered entry list in ``self._all_entries`` so
        that the filter can be re-applied without hitting the filesystem
        again.  After populating, re-applies any active filter so that the
        visible rows remain consistent with the current filter state.
        """
        self._refresh_generation += 1
        my_generation = self._refresh_generation

        self._all_entries = []
        self._log_file_map.clear()
        self._resolved.clear()
        self._set_content("")
        self._clear_search()

        children = self._tree.get_children()
        if children:
            self._tree.delete(*children)

        log_files = sorted(self._log_dir.glob(_LOG_FILENAME_PATTERN), reverse=True)
        if not log_files:
            self._tree.insert("", "end", values=("No log files found", "", ""))
            self._filter_count_var.set("")
            return

        # Build the full entry list first, then apply the filter.
        for path in log_files:
            stem = path.stem
            dt_str = stem[len(_LOG_FILENAME_PREFIX) :]
            try:
                dt = datetime.strptime(dt_str, _LOG_DATE_FORMAT)
                date_display = dt.strftime("%Y-%m-%d  %H:%M:%S")
            except ValueError:
                date_display = stem

            # Use a temporary placeholder iid; _apply_tree_filter will
            # re-insert with the same string so workers can still update it.
            placeholder_iid = f"entry_{stem}"
            self._all_entries.append((placeholder_iid, date_display, path))

        # Apply the current filter (populates _tree and _log_file_map).
        self._apply_tree_filter()

        # Collect all currently visible iids for the background parse worker.
        pending: list[tuple[str, Path]] = [(iid, path) for iid, path in self._log_file_map.items()]

        def _parse_worker(items: list[tuple[str, Path]], generation: int) -> None:
            for iid, path in items:
                if self._refresh_generation != generation:
                    return
                exit_code = _parse_log_exit_code(path)
                code_display = str(exit_code) if exit_code is not None else "—"
                status = exit_code_label(exit_code) if exit_code is not None else "In progress / unknown"

                def _update(
                    i: str = iid,
                    c: str = code_display,
                    s: str = status,
                    g: int = generation,
                ) -> None:
                    if self._refresh_generation != g:
                        return
                    # Persist resolved values so _apply_tree_filter can use them
                    # if the user re-filters after the worker has already run.
                    self._resolved[i] = (c, s)
                    try:
                        self._tree.set(i, self._CODE_COL, c)
                        self._tree.set(i, self._STATUS_COL, s)
                    except tk.TclError:
                        pass

                try:
                    self.after(0, _update)
                except tk.TclError:
                    return

        threading.Thread(target=_parse_worker, args=(pending, my_generation), daemon=True).start()

    # ------------------------------------------------------------------
    # Row selection and content display
    # ------------------------------------------------------------------

    def _on_select(self, _event: tk.Event[Any]) -> None:
        """Load the selected log file into the right pane."""
        selection = self._tree.selection()
        if not selection:
            return
        path = self._log_file_map.get(selection[0])
        if path is None:
            return
        try:
            size = path.stat().st_size
            if size > _MAX_LOG_PREVIEW_BYTES:
                with path.open("rb") as fh:
                    fh.seek(-_MAX_LOG_PREVIEW_BYTES, 2)
                    tail_bytes = fh.read()
                preview_kb = _MAX_LOG_PREVIEW_BYTES // 1024
                text = (
                    f"[File is {size:,} bytes — showing last {preview_kb} KB  |  "
                    "Use 'Open in editor' to view the full file]\n"
                    + "─" * 72
                    + "\n"
                    + tail_bytes.decode("utf-8", errors="replace")
                )
            else:
                text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            text = f"[Error reading file: {exc}]"
            logger.exception("Failed to read log file: %s", path)

        self._set_content(text)
        # Clear any previous search highlights when a new file is loaded.
        self._clear_search()

    def _open_externally(self) -> None:
        """Open the selected log file in the system's default text editor."""
        selection = self._tree.selection()
        if not selection:
            return
        path = self._log_file_map.get(selection[0])
        if path is None:
            return
        try:
            if hasattr(os, "startfile"):
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)], shell=False)
            else:
                subprocess.Popen(["xdg-open", str(path)], shell=False)
        except OSError as exc:
            logger.exception("Failed to open log file externally: %s", path)
            messagebox.showerror("Error", f"Could not open file:\n{exc}", parent=self)

    def _export_log(self) -> None:
        """Copy the selected log file to a user-chosen destination."""
        selection = self._tree.selection()
        if not selection:
            return
        src = self._log_file_map.get(selection[0])
        if src is None:
            return
        dest_str = filedialog.asksaveasfilename(
            parent=self,
            title="Export log file",
            initialfile=src.name,
            defaultextension=".log",
            filetypes=[
                ("Log files", "*.log"),
                ("Text files", "*.txt"),
                ("All files", "*.*"),
            ],
        )
        if not dest_str:
            return
        dest = Path(dest_str)
        try:
            shutil.copy2(src, dest)
            messagebox.showinfo("Log Exported", f"Log exported to:\n{dest}", parent=self)
        except OSError as exc:
            logger.exception("Failed to export log file %s -> %s", src, dest)
            messagebox.showerror("Export Failed", f"Could not export file:\n{exc}", parent=self)

    def _set_content(self, text: str) -> None:
        """Replace the text displayed in the log content viewer."""
        self._content.config(state="normal")
        self._content.delete("1.0", "end")
        self._content.insert("end", text)
        self._content.config(state="disabled")
