"""Tkinter GUI for Windows Robocopy.

This package is structured as follows:

* :mod:`rbcopy.gui.job_history` – job history viewer and log-file parsing helpers.
* :mod:`rbcopy.gui.script_builder` – script export dialog.
* :mod:`rbcopy.gui.main_window` – main application window (``RobocopyGUI``).

The public API is re-exported here for backward compatibility.
"""

from __future__ import annotations

import logging
from logging import getLogger
from pathlib import Path

from rbcopy.gui.main_window import RobocopyGUI
from rbcopy.logger import rotate_logs, setup_logging

logger = getLogger(__name__)

__all__ = [
    "RobocopyGUI",
    "launch",
]


def launch() -> None:
    """Launch the RBCopy GUI."""
    from rbcopy.app_dirs import get_log_dir
    from rbcopy.preferences import PreferencesStore

    log_dir = get_log_dir()
    log = setup_logging(log_dir=log_dir)

    # Prune old log files now that the new session log has been created.
    rotate_logs(log_dir, keep=PreferencesStore().preferences.log_retention_count)

    file_handlers = [h for h in log.handlers if isinstance(h, logging.FileHandler)]
    if file_handlers:
        handler_path = Path(file_handlers[0].baseFilename)
        current_log_dir = handler_path.parent
        if current_log_dir != log_dir:
            logger.warning(
                "Logging already configured; GUI will use existing log directory %s instead of requested %s",
                current_log_dir,
                log_dir,
            )

    app = RobocopyGUI()

    if file_handlers:
        app._append_output(f"Session log: {file_handlers[0].baseFilename}\n")

    app.mainloop()
