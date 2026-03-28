"""Script export dialog for saving robocopy commands as standalone scripts."""

from __future__ import annotations

import tkinter as tk
from logging import getLogger
from pathlib import Path, PureWindowsPath
from tkinter import filedialog, messagebox, ttk
from typing import TypedDict

from rbcopy.builder import build_batch_script, build_powershell_script

logger = getLogger("rbcopy.gui.script_builder")


class _PackPadding(TypedDict):
    """Keyword arguments for ttk widget .pack() calls that add consistent spacing."""

    padx: int
    pady: int


class _ScriptExportDialog(tk.Toplevel):
    """Modal dialog for exporting a robocopy command as a standalone script file.

    Prompts the user for:

    * **Script type** – DOS Batch (``.bat``) or PowerShell (``.ps1``).
    * **File name** – base name for the output file (extension added automatically).
    * **Save location** – destination directory chosen via a directory browser.

    After the user clicks *Save* the script is written to disk and the dialog
    closes.  Call :attr:`saved` after the dialog returns to determine whether
    the export completed or was cancelled.
    """

    def __init__(self, parent: tk.Misc, cmd: list[str]) -> None:
        super().__init__(parent)
        self.title("Script Builder – Export Script")
        self.resizable(False, False)
        self._cmd = cmd
        self._saved: bool = False
        self._type_var = tk.StringVar(value="batch")
        self._name_var = tk.StringVar(value="robocopy_job")
        self._dir_var = tk.StringVar()
        self._build_ui()
        self.transient(parent)  # type: ignore[call-overload]  # Tk is both Misc and Wm
        self.grab_set()
        self.wait_window()

    @property
    def saved(self) -> bool:
        """``True`` if the export completed; ``False`` if the user cancelled."""
        return self._saved

    def _build_ui(self) -> None:
        """Assemble the dialog widgets."""
        padding: _PackPadding = {"padx": 8, "pady": 4}

        # ── Script type ───────────────────────────────────────────────
        type_frame = ttk.LabelFrame(self, text="Script Type", padding=6)
        type_frame.pack(fill="x", **padding)
        ttk.Radiobutton(type_frame, text="DOS Batch (.bat)", variable=self._type_var, value="batch").pack(anchor="w")
        ttk.Radiobutton(type_frame, text="PowerShell (.ps1)", variable=self._type_var, value="powershell").pack(
            anchor="w"
        )

        # ── File name ─────────────────────────────────────────────────
        name_frame = ttk.Frame(self)
        name_frame.pack(fill="x", **padding)
        name_frame.columnconfigure(1, weight=1)
        ttk.Label(name_frame, text="File Name:").grid(row=0, column=0, sticky="w")
        ttk.Entry(name_frame, textvariable=self._name_var, width=30).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # ── Save location ─────────────────────────────────────────────
        dir_frame = ttk.Frame(self)
        dir_frame.pack(fill="x", **padding)
        dir_frame.columnconfigure(1, weight=1)
        ttk.Label(dir_frame, text="Location:").grid(row=0, column=0, sticky="w")
        ttk.Entry(dir_frame, textvariable=self._dir_var, width=30).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(dir_frame, text="Browse…", command=self._browse_dir).grid(row=0, column=2)

        # ── Buttons ───────────────────────────────────────────────────
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=8, pady=(8, 8))
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="right", padx=(4, 0))
        ttk.Button(btn_frame, text="Save", command=self._on_save).pack(side="right")

    def _browse_dir(self) -> None:
        path = filedialog.askdirectory(title="Select Save Location", parent=self)
        if path:
            self._dir_var.set(path)

    def _on_save(self) -> None:
        """Validate inputs, write the script file, and close the dialog."""
        script_type = self._type_var.get()
        name = self._name_var.get().strip()
        directory = self._dir_var.get().strip()

        if not name:
            messagebox.showwarning("Missing file name", "Please enter a file name.", parent=self)
            return
        if not directory:
            messagebox.showwarning("Missing location", "Please select a save location.", parent=self)
            return

        # Append the appropriate extension when the user omitted it.
        if script_type == "batch":
            if not (name.lower().endswith(".bat") or name.lower().endswith(".cmd")):
                name += ".bat"
        elif script_type == "powershell":
            if not name.lower().endswith(".ps1"):
                name += ".ps1"
        else:
            messagebox.showerror(
                "Unknown Script Type",
                f"Unknown script type {script_type!r}. Expected 'batch' or 'powershell'.",
                parent=self,
            )
            return

        # Ensure the provided name is a plain filename (no directories or absolute paths).
        # Use Windows path semantics so validation is consistent across platforms,
        # even when running tests on non-Windows systems.
        name_path = PureWindowsPath(name)
        has_multiple_parts = len(name_path.parts) != 1
        has_drive = bool(name_path.drive)
        has_parent_ref = ".." in name_path.parts or name_path.name in {".", ".."}
        if name_path.is_absolute() or has_drive or has_multiple_parts or has_parent_ref or name_path.name != name:
            messagebox.showwarning(
                "Invalid File Name",
                "The file name must not contain folder paths or parent references.\n"
                "Please enter only a file name (for example: robocopy_job.bat).",
                parent=self,
            )
            logger.warning("User entered invalid script file name: %r", name)
            return

        # Build the script content only after the file name has been validated.
        if script_type == "batch":
            content = build_batch_script(self._cmd)
        else:
            # At this point script_type must be "powershell".
            content = build_powershell_script(self._cmd)

        out_path = Path(directory) / name
        try:
            out_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Save Failed", f"Could not write script:\n{exc}", parent=self)
            logger.exception("Failed to write script file: %s", out_path)
            return

        logger.info("Script exported to: %s", out_path)
        messagebox.showinfo("Script Exported", f"Script saved to:\n{out_path}", parent=self)
        self._saved = True
        self.destroy()
