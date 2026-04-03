"""Tests for rbcopy builder exit_code_label and targeted build_command scenarios."""

from __future__ import annotations

from pathlib import Path


from unittest.mock import patch

from rbcopy.builder import (
    build_command,
    exit_code_label,
    validate_command,
)

# ---------------------------------------------------------------------------
# exit_code_label
# ---------------------------------------------------------------------------


def test_exit_code_label_returns_string() -> None:
    """exit_code_label always returns a str for any input."""

    assert isinstance(exit_code_label(0), str)
    assert isinstance(exit_code_label(-1), str)
    assert isinstance(exit_code_label(999), str)


def test_exit_code_label_minus_one() -> None:
    """exit_code_label describes -1 as an unknown error."""

    assert "Unknown error" in exit_code_label(-1)
    assert "log" in exit_code_label(-1).lower()


def test_exit_code_label_zero() -> None:
    """exit_code_label describes 0 as nothing to do."""

    assert "Nothing to do" in exit_code_label(0)


def test_exit_code_label_one() -> None:
    """exit_code_label describes 1 as files copied successfully."""

    assert "Files copied successfully" in exit_code_label(1)


def test_exit_code_label_two() -> None:
    """exit_code_label describes 2 as extra files at destination."""

    label = exit_code_label(2)
    assert "Extra files" in label
    assert "destination" in label.lower()


def test_exit_code_label_three() -> None:
    """exit_code_label describes 3 as files copied with extra files at destination."""

    label = exit_code_label(3)
    assert "Files copied" in label
    assert "extra files" in label.lower()


def test_exit_code_label_four() -> None:
    """exit_code_label describes 4 as mismatched files."""

    assert "Mismatched" in exit_code_label(4)


def test_exit_code_label_five() -> None:
    """exit_code_label describes 5 as files copied with mismatched files."""

    label = exit_code_label(5)
    assert "Files copied" in label
    assert "mismatched" in label.lower()
    assert "log" in label.lower()


def test_exit_code_label_six() -> None:
    """exit_code_label describes 6 as extra and mismatched files."""

    label = exit_code_label(6)
    assert "mismatched" in label.lower()
    assert "log" in label.lower()


def test_exit_code_label_seven() -> None:
    """exit_code_label describes 7 as files copied with multiple warnings."""

    label = exit_code_label(7)
    assert "Files copied" in label
    assert "log" in label.lower()


def test_exit_code_label_eight() -> None:
    """exit_code_label describes 8 as copy failures."""

    label = exit_code_label(8)
    assert "Copy failures" in label
    assert "log" in label.lower()


def test_exit_code_label_sixteen() -> None:
    """exit_code_label describes 16 as a fatal error."""

    label = exit_code_label(16)
    assert "Fatal error" in label
    assert "log" in label.lower()


def test_exit_code_label_unknown_combination_falls_back_gracefully() -> None:
    """exit_code_label returns a composed fallback for unusual bit combinations."""

    # 9 = 8 + 1 (copy failures + files copied) — not in the explicit lookup table
    label = exit_code_label(9)
    assert isinstance(label, str)
    assert len(label) > 0


def test_exit_code_label_failure_bits_include_check_log() -> None:
    """exit_code_label includes 'Check the log' for any code with bit 8 or 16 set."""

    # Use an unusual combination not in the explicit table to exercise the fallback.
    # 24 = 8 + 16
    label = exit_code_label(24)
    assert "log" in label.lower()


def test_exit_code_label_no_check_log_for_low_codes() -> None:
    """exit_code_label does not append 'Check the log' for codes below 8."""

    # All standard low codes 0-7 should not contain "check the log" except
    # where we have explicitly added it (5, 6, 7 do contain it by design).
    # Code 2 and 4 should not.
    assert "log" not in exit_code_label(2).lower()
    assert "log" not in exit_code_label(4).lower()


# ---------------------------------------------------------------------------
# build_command – targeted scenario tests
# ---------------------------------------------------------------------------
# The tests below are intentionally explicit about the three categories the
# user scenario describes: normal operations, edge cases with redundant flags,
# and missing parameter values.


# ── Normal operations ─────────────────────────────────────────────────────


def test_build_command_normal_source_and_destination() -> None:
    """build_command produces the expected three-token base command for valid paths."""
    with patch("rbcopy.builder.sys.platform", "linux"):
        cmd = build_command("C:/Users/backup", "D:/Backups/users", {}, {})
    assert cmd[0] == "robocopy"
    assert cmd[1] == "C:/Users/backup"
    assert cmd[2] == "D:/Backups/users"
    assert len(cmd) == 3


def test_build_command_normal_with_common_flag_set() -> None:
    """build_command produces a sensible everyday command (mirror + retry settings)."""
    cmd = build_command(
        "C:/source",
        "D:/destination",
        {"/MIR": True, "/NP": True},
        {"/R": (True, "3"), "/W": (True, "10")},
    )
    assert "/MIR" in cmd
    assert "/NP" in cmd
    assert "/R:3" in cmd
    assert "/W:10" in cmd


def test_build_command_normal_preserves_path_order() -> None:
    """Source always comes before destination in the built command."""
    with patch("rbcopy.builder.sys.platform", "linux"):
        cmd = build_command("C:/source", "D:/destination", {}, {})
    assert cmd.index("C:/source") < cmd.index("D:/destination")


# ── Edge cases: redundant flag combinations ──────────────────────────────
# build_command does NOT validate for redundancy; that is validate_command's
# responsibility.  These tests confirm that build_command faithfully includes
# every enabled flag so that callers can decide whether to warn or not.


def test_build_command_includes_both_mir_and_e_when_both_enabled() -> None:
    """/MIR and /E both appear in the command when both ticked; no silent removal."""
    cmd = build_command("C:/src", "C:/dst", {"/MIR": True, "/E": True}, {})
    assert "/MIR" in cmd
    assert "/E" in cmd


def test_build_command_includes_both_mir_and_purge_when_both_enabled() -> None:
    """/MIR and /PURGE both appear when both ticked (/MIR supersedes /PURGE logically,
    but build_command does not suppress redundant flags)."""
    cmd = build_command("C:/src", "C:/dst", {"/MIR": True, "/PURGE": True}, {})
    assert "/MIR" in cmd
    assert "/PURGE" in cmd


def test_build_command_includes_both_move_and_mov_when_both_enabled() -> None:
    """/MOVE and /MOV both appear when both ticked (redundancy not stripped by build_command)."""
    cmd = build_command("C:/src", "C:/dst", {"/MOVE": True, "/MOV": True}, {})
    assert "/MOVE" in cmd
    assert "/MOV" in cmd


def test_validate_command_mir_e_warns_but_is_still_ok(tmp_path: Path) -> None:
    """/MIR + /E is a warning-level issue, not a fatal error: ok remains True."""
    src = tmp_path / "src"
    src.mkdir()
    result = validate_command(str(src), str(tmp_path / "dst"), {"/MIR": True, "/E": True}, {})
    assert result.ok is True
    assert any("redundant" in w.lower() or "/E" in w for w in result.warnings)
    assert result.errors == []


def test_validate_command_mir_e_warning_names_redundant_flag(tmp_path: Path) -> None:
    """The redundancy warning for /MIR + /E must mention the redundant flag /E by name."""
    src = tmp_path / "src"
    src.mkdir()
    result = validate_command(str(src), str(tmp_path / "dst"), {"/MIR": True, "/E": True}, {})
    combined = " ".join(result.warnings)
    assert "/E" in combined


# ── Edge cases: missing parameter values ─────────────────────────────────


def test_build_command_omits_r_when_enabled_with_blank_value() -> None:
    """Enabling /R with an empty value must not add any /R token to the command.

    robocopy would silently ignore a bare '/R:' argument; omitting it entirely
    is the safer and more predictable behaviour.
    """
    cmd = build_command("C:/src", "C:/dst", {}, {"/R": (True, "")})
    assert not any(arg.startswith("/R") for arg in cmd)


def test_build_command_omits_w_when_enabled_with_whitespace_only_value() -> None:
    """A whitespace-only value for /W must be treated the same as an empty value."""
    cmd = build_command("C:/src", "C:/dst", {}, {"/W": (True, "   ")})
    assert not any(arg.startswith("/W") for arg in cmd)


def test_build_command_includes_r_when_enabled_with_valid_value() -> None:
    """/R:n must appear when enabled and a numeric value is provided."""
    cmd = build_command("C:/src", "C:/dst", {}, {"/R": (True, "5")})
    assert "/R:5" in cmd


def test_validate_command_warns_r_enabled_with_blank_value(tmp_path: Path) -> None:
    """/R enabled with a blank value must produce a warning inside validate_command."""
    src = tmp_path / "src"
    src.mkdir()
    result = validate_command(str(src), str(tmp_path / "dst"), {}, {"/R": (True, "")})
    assert result.ok is True  # warning, not a fatal error
    assert any("/R" in w for w in result.warnings)


def test_validate_command_warns_w_enabled_with_blank_value(tmp_path: Path) -> None:
    """/W enabled with a blank value must also produce a warning."""
    src = tmp_path / "src"
    src.mkdir()
    result = validate_command(str(src), str(tmp_path / "dst"), {}, {"/W": (True, "")})
    assert result.ok is True
    assert any("/W" in w for w in result.warnings)


def test_validate_command_multiple_blank_params_produce_one_warning_each(tmp_path: Path) -> None:
    """Each enabled param with a blank value generates its own independent warning."""
    src = tmp_path / "src"
    src.mkdir()
    result = validate_command(
        str(src),
        str(tmp_path / "dst"),
        {},
        {"/R": (True, ""), "/W": (True, ""), "/LEV": (True, "")},
    )
    assert result.ok is True
    r_warnings = [w for w in result.warnings if "/R" in w]
    w_warnings = [w for w in result.warnings if "/W" in w]
    lev_warnings = [w for w in result.warnings if "/LEV" in w]
    assert len(r_warnings) >= 1
    assert len(w_warnings) >= 1
    assert len(lev_warnings) >= 1
