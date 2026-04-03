"""UI interaction regression tests for RobocopyGUI.

These tests instantiate a real RobocopyGUI window (hidden via withdraw())
and programmatically toggle Tkinter variables to verify that the UI state
rules enforced by ``_refresh_widget_states()`` operate correctly without
requiring a human to click anything.

Three rules are covered:

1. **Properties Only preset** – toggling ``_props_only_var`` must lock the
   destination entry to ``PROPERTIES_ONLY_DST``, force the preset flags
   on, and disable (grey out) every forced checkbutton and param control.

2. **Supersession** – checking a superseding flag (e.g. ``/MIR``) must grey
   out the flags it logically replaces (e.g. ``/E`` and ``/PURGE``).

3. **Preset clearing** – applying a new preset must reset all flags and
   params not listed in that preset so that residual selections from a
   previous preset or manual interaction do not bleed through.

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
from rbcopy.presets import CustomPreset


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

    assert gui._dst_entry.instate(["disabled"]), (  # type: ignore[no-untyped-call]
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
            assert cb.instate(["disabled"]), (  # type: ignore[no-untyped-call]
                f"Checkbutton for {flag!r} must be in disabled state when Properties Only is active"
            )


def test_properties_only_disables_forced_param_checkbuttons(gui: RobocopyGUI) -> None:
    """Forced param checkbuttons must be disabled when Properties Only is active."""
    gui._props_only_var.set(True)

    for flag in PROPERTIES_ONLY_PARAMS:
        if flag in gui._param_cbs:
            param_cb = gui._param_cbs[flag]
            assert param_cb.instate(["disabled"]), (  # type: ignore[no-untyped-call]
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

    assert not gui._dst_entry.instate(["disabled"]), (  # type: ignore[no-untyped-call]
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
        assert cb.instate(["disabled"]), f"Checkbutton for {implied_flag!r} must be disabled because /MIR supersedes it"  # type: ignore[no-untyped-call]


def test_mir_unchecked_reenables_superseded_checkbuttons(gui: RobocopyGUI) -> None:
    """Unchecking /MIR must re-enable every flag it previously superseded."""
    gui._flag_vars["/MIR"].set(True)
    gui._flag_vars["/MIR"].set(False)

    for implied_flag in SUPERSEDES["/MIR"]:
        cb = gui._flag_cbs[implied_flag]
        assert not cb.instate(["disabled"]), (  # type: ignore[no-untyped-call]
            f"Checkbutton for {implied_flag!r} must be re-enabled after /MIR is unchecked"
        )


def test_mir_supersession_does_not_disable_unrelated_flags(gui: RobocopyGUI) -> None:
    """Activating /MIR must not disable flags that it does not supersede."""
    gui._flag_vars["/MIR"].set(True)

    superseded_by_mir: frozenset[str] = SUPERSEDES["/MIR"]
    for flag, cb in gui._flag_cbs.items():
        if flag not in superseded_by_mir:
            assert not cb.instate(["disabled"]), (  # type: ignore[no-untyped-call]
                f"Flag {flag!r} must not be disabled solely because /MIR is active (it is not superseded by /MIR)"
            )


# ---------------------------------------------------------------------------
# Preset clearing: applying a preset must reset flags/params not in the preset
# ---------------------------------------------------------------------------


def _make_preset(**kwargs: object) -> CustomPreset:
    """Build a minimal CustomPreset for testing, forwarding any field overrides."""
    defaults: dict[str, object] = dict(name="test", source="", destination="", flags={}, params={}, file_filter="")
    defaults.update(kwargs)
    return CustomPreset(**defaults)


def test_apply_preset_clears_flags_not_in_preset(gui: RobocopyGUI) -> None:
    """Flags set manually (or by a previous preset) must be cleared when a new preset is applied."""
    # Manually enable a flag that the new preset does not mention.
    gui._flag_vars["/J"].set(True)
    gui._flag_vars["/NP"].set(True)

    # Apply a preset that only enables /E and says nothing about /J or /NP.
    gui._apply_custom_preset(_make_preset(name="only-e", flags={"/E": True}))

    assert gui._flag_vars["/J"].get() is False, "/J must be reset to False by a preset that does not include it"
    assert gui._flag_vars["/NP"].get() is False, "/NP must be reset to False by a preset that does not include it"
    assert gui._flag_vars["/E"].get() is True, "/E must remain enabled as listed in the preset"


def test_apply_preset_clears_params_not_in_preset(gui: RobocopyGUI) -> None:
    """Param checkboxes enabled manually must be cleared when a new preset is applied."""
    # Manually enable params that the new preset does not mention.
    ev_r, _vv_r, _ = gui._param_vars["/R"]
    ev_r.set(True)
    ev_mon, _vv_mon, _ = gui._param_vars["/MON"]
    ev_mon.set(True)

    # Apply a preset that only sets /MAXAGE and says nothing about /R or /MON.
    gui._apply_custom_preset(_make_preset(name="maxage-only", params={"/MAXAGE": (True, "7")}))

    ev_r2, _, _ = gui._param_vars["/R"]
    assert ev_r2.get() is False, "/R must be reset to False by a preset that does not include it"
    ev_mon2, _, _ = gui._param_vars["/MON"]
    assert ev_mon2.get() is False, "/MON must be reset to False by a preset that does not include it"
    ev_maxage, vv_maxage, _ = gui._param_vars["/MAXAGE"]
    assert ev_maxage.get() is True, "/MAXAGE must be enabled as listed in the preset"
    assert vv_maxage.get() == "7", "/MAXAGE value must be set to the preset value"


def test_apply_second_preset_does_not_inherit_first_preset_flags(gui: RobocopyGUI) -> None:
    """Flags enabled by one preset must not carry over when a different preset is applied."""
    # Apply a first preset that enables several flags.
    gui._apply_custom_preset(_make_preset(name="first", flags={"/E": True, "/Z": True, "/J": True, "/NP": True}))
    # Apply a second preset that only uses /E and /MAXAGE.
    gui._apply_custom_preset(_make_preset(name="second", flags={"/E": True}, params={"/MAXAGE": (True, "7")}))

    assert gui._flag_vars["/Z"].get() is False, "/Z from the first preset must be cleared by the second preset"
    assert gui._flag_vars["/J"].get() is False, "/J from the first preset must be cleared by the second preset"
    assert gui._flag_vars["/NP"].get() is False, "/NP from the first preset must be cleared by the second preset"
    assert gui._flag_vars["/E"].get() is True, "/E is also in the second preset and must remain enabled"


def test_apply_preset_preserves_forced_flags_when_props_only_active(gui: RobocopyGUI) -> None:
    """Forced Properties Only flags must not be cleared or overridden when applying a preset."""
    gui._props_only_var.set(True)

    # Apply a preset that explicitly tries to disable a forced flag.
    gui._apply_custom_preset(_make_preset(name="try-disable-l", flags={"/L": False}))

    for flag in PROPERTIES_ONLY_FLAGS:
        if flag in gui._flag_vars:
            assert gui._flag_vars[flag].get() is True, (
                f"Forced flag {flag!r} must remain True after preset application when Properties Only is active"
            )


# ---------------------------------------------------------------------------
# Gap 14: Additional supersession rules
# ---------------------------------------------------------------------------


def test_zb_disables_z_checkbutton(gui: RobocopyGUI) -> None:
    """/ZB active must grey out the /Z checkbutton."""
    gui._flag_vars["/ZB"].set(True)
    gui._refresh_widget_states()

    assert gui._flag_cbs["/Z"].instate(["disabled"]), "/Z must be disabled when /ZB is active"  # type: ignore[no-untyped-call]


def test_zb_disables_b_checkbutton(gui: RobocopyGUI) -> None:
    """/ZB active must grey out the /B checkbutton."""
    gui._flag_vars["/ZB"].set(True)
    gui._refresh_widget_states()

    assert gui._flag_cbs["/B"].instate(["disabled"]), "/B must be disabled when /ZB is active"  # type: ignore[no-untyped-call]


def test_zb_reenables_z_when_unchecked(gui: RobocopyGUI) -> None:
    """Unchecking /ZB must re-enable the /Z checkbutton."""
    gui._flag_vars["/ZB"].set(True)
    gui._refresh_widget_states()
    gui._flag_vars["/ZB"].set(False)
    gui._refresh_widget_states()

    assert not gui._flag_cbs["/Z"].instate(["disabled"]), "/Z must be re-enabled when /ZB is unchecked"  # type: ignore[no-untyped-call]


def test_zb_reenables_b_when_unchecked(gui: RobocopyGUI) -> None:
    """Unchecking /ZB must re-enable the /B checkbutton."""
    gui._flag_vars["/ZB"].set(True)
    gui._refresh_widget_states()
    gui._flag_vars["/ZB"].set(False)
    gui._refresh_widget_states()

    assert not gui._flag_cbs["/B"].instate(["disabled"]), "/B must be re-enabled when /ZB is unchecked"  # type: ignore[no-untyped-call]


def test_move_disables_mov_checkbutton(gui: RobocopyGUI) -> None:
    """/MOVE active must grey out the /MOV checkbutton."""
    gui._flag_vars["/MOVE"].set(True)
    gui._refresh_widget_states()

    assert gui._flag_cbs["/MOV"].instate(["disabled"]), "/MOV must be disabled when /MOVE is active"  # type: ignore[no-untyped-call]


def test_move_reenables_mov_when_unchecked(gui: RobocopyGUI) -> None:
    """Unchecking /MOVE must re-enable the /MOV checkbutton."""
    gui._flag_vars["/MOVE"].set(True)
    gui._refresh_widget_states()
    gui._flag_vars["/MOVE"].set(False)
    gui._refresh_widget_states()

    assert not gui._flag_cbs["/MOV"].instate(["disabled"]), "/MOV must be re-enabled when /MOVE is unchecked"  # type: ignore[no-untyped-call]


def test_mir_supersession_does_not_affect_zb_state(gui: RobocopyGUI) -> None:
    """/MIR supersession must not change the /ZB checkbutton state."""
    gui._flag_vars["/ZB"].set(True)
    gui._flag_vars["/MIR"].set(True)
    gui._refresh_widget_states()

    # /ZB is not superseded by /MIR – it must remain normally interactive
    # (its own superseded children /Z and /B should still be disabled by /ZB).
    assert not gui._flag_cbs["/ZB"].instate(["disabled"]), "/ZB must not be disabled by /MIR"  # type: ignore[no-untyped-call]
