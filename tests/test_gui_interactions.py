"""UI interaction regression tests for RobocopyGUI.

These tests instantiate a real RobocopyGUI window (hidden via withdraw())
and programmatically toggle Tkinter variables to verify that the UI state
rules enforced by ``_refresh_widget_states()`` operate correctly without
requiring a human to click anything.

Two rules are covered:

1. **Properties Only preset** – toggling ``_props_only_var`` must lock the
   destination entry to ``PROPERTIES_ONLY_DST``, force the preset flags
   on, and disable (grey out) every forced checkbutton and param control.

2. **Supersession** – checking ``/MIR`` must grey out the ``/E`` and
   ``/PURGE`` checkbuttons because ``/MIR`` logically implies both.

The entire module is skipped automatically on headless systems where
Tkinter cannot open a display connection.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Iterator

import pytest

from rbcopy.builder import (
    PROPERTIES_ONLY_DST,
    PROPERTIES_ONLY_FLAGS,
    PROPERTIES_ONLY_PARAMS,
    SUPERSEDES,
)
from rbcopy.gui import RobocopyGUI


@pytest.fixture()
def gui() -> Iterator[RobocopyGUI]:
    """Yield a hidden, fully-initialised RobocopyGUI and destroy it on teardown.

    Skips the test automatically when Tkinter cannot open a display connection
    (e.g. headless CI) rather than hard-failing, so the rest of the suite is
    unaffected.  The window is immediately withdrawn so it never appears on
    screen during the test run.
    """
    try:
        app = RobocopyGUI()
    except tk.TclError as exc:
        pytest.skip(f"Tkinter display not available: {exc}")
    app.withdraw()
    yield app
    app.destroy()


# ---------------------------------------------------------------------------
# Properties Only preset rule
# ---------------------------------------------------------------------------


def test_properties_only_disables_dst_entry(gui: RobocopyGUI) -> None:
    """Activating Properties Only must disable the destination entry widget."""
    gui._props_only_var.set(True)

    assert gui._dst_entry.instate(["disabled"]), (
        "_dst_entry must enter the disabled state when Properties Only is active"
    )


def test_properties_only_forces_dst_path(gui: RobocopyGUI) -> None:
    """Activating Properties Only must override the destination path with PROPERTIES_ONLY_DST."""
    gui.dst_var.set(r"C:\original\path")

    gui._props_only_var.set(True)

    assert gui.dst_var.get() == PROPERTIES_ONLY_DST, (
        f"dst_var must be set to {PROPERTIES_ONLY_DST!r} when Properties Only is active; got {gui.dst_var.get()!r}"
    )


def test_properties_only_ticks_forced_flags(gui: RobocopyGUI) -> None:
    """All PROPERTIES_ONLY_FLAGS must be set to True when the preset is activated."""
    gui._props_only_var.set(True)

    for flag in PROPERTIES_ONLY_FLAGS:
        if flag in gui._flag_vars:
            assert gui._flag_vars[flag].get() is True, (
                f"Flag variable for {flag!r} must be True when Properties Only is active"
            )


def test_properties_only_disables_forced_flag_checkbuttons(gui: RobocopyGUI) -> None:
    """Every forced-flag checkbutton must be visually disabled in Properties Only mode."""
    gui._props_only_var.set(True)

    for flag in PROPERTIES_ONLY_FLAGS:
        if flag in gui._flag_cbs:
            cb = gui._flag_cbs[flag]
            assert cb.instate(["disabled"]), (
                f"Checkbutton for {flag!r} must be in disabled state when Properties Only is active"
            )


def test_properties_only_disables_forced_param_checkbuttons(gui: RobocopyGUI) -> None:
    """Forced param checkbuttons must be disabled when Properties Only is active."""
    gui._props_only_var.set(True)

    for flag in PROPERTIES_ONLY_PARAMS:
        if flag in gui._param_cbs:
            param_cb = gui._param_cbs[flag]
            assert param_cb.instate(["disabled"]), (
                f"Param checkbutton for {flag!r} must be disabled when Properties Only is active"
            )


def test_properties_only_deactivation_restores_dst_path(gui: RobocopyGUI) -> None:
    """Deactivating Properties Only must restore the original destination path."""
    original_dst = r"D:\backup\data"
    gui.dst_var.set(original_dst)

    gui._props_only_var.set(True)
    gui._props_only_var.set(False)

    assert gui.dst_var.get() == original_dst, (
        f"dst_var must be restored to {original_dst!r} after Properties Only is deactivated; got {gui.dst_var.get()!r}"
    )


def test_properties_only_deactivation_reenables_dst_entry(gui: RobocopyGUI) -> None:
    """Deactivating Properties Only must re-enable the destination entry widget."""
    gui._props_only_var.set(True)
    gui._props_only_var.set(False)

    assert not gui._dst_entry.instate(["disabled"]), (
        "_dst_entry must leave the disabled state after Properties Only is deactivated"
    )


# ---------------------------------------------------------------------------
# Supersession rule: /MIR supersedes /E and /PURGE
# ---------------------------------------------------------------------------


def test_mir_active_disables_superseded_checkbuttons(gui: RobocopyGUI) -> None:
    """/MIR being checked must grey out every flag it supersedes (/E and /PURGE)."""
    gui._flag_vars["/MIR"].set(True)

    for implied_flag in SUPERSEDES["/MIR"]:
        cb = gui._flag_cbs[implied_flag]
        assert cb.instate(["disabled"]), f"Checkbutton for {implied_flag!r} must be disabled because /MIR supersedes it"


def test_mir_unchecked_reenables_superseded_checkbuttons(gui: RobocopyGUI) -> None:
    """Unchecking /MIR must re-enable every flag it previously superseded."""
    gui._flag_vars["/MIR"].set(True)
    gui._flag_vars["/MIR"].set(False)

    for implied_flag in SUPERSEDES["/MIR"]:
        cb = gui._flag_cbs[implied_flag]
        assert not cb.instate(["disabled"]), (
            f"Checkbutton for {implied_flag!r} must be re-enabled after /MIR is unchecked"
        )


def test_mir_supersession_does_not_disable_unrelated_flags(gui: RobocopyGUI) -> None:
    """Activating /MIR must not disable flags that it does not supersede."""
    gui._flag_vars["/MIR"].set(True)

    superseded_by_mir: frozenset[str] = SUPERSEDES["/MIR"]
    for flag, cb in gui._flag_cbs.items():
        if flag not in superseded_by_mir:
            assert not cb.instate(["disabled"]), (
                f"Flag {flag!r} must not be disabled solely because /MIR is active (it is not superseded by /MIR)"
            )
