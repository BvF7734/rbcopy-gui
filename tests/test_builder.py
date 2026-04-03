"""Tests for the rbcopy builder module (pure logic, no GUI dependency)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from rbcopy.builder import (
    FLAG_OPTIONS,
    FLAG_TOOLTIPS,
    PARAM_OPTIONS,
    PARAM_TOOLTIPS,
    PROPERTIES_ONLY_DST,
    PROPERTIES_ONLY_FLAGS,
    PROPERTIES_ONLY_PARAMS,
    SUPERSEDES,
    _DEFAULT_FLAGS,
    _DEFAULT_PARAMS,
    build_command,
    build_robocopy_command,
    DryRunResult,
    validate_command,
)


# ---------------------------------------------------------------------------
# Option table sanity checks
# ---------------------------------------------------------------------------


def test_flag_options_not_empty() -> None:
    assert len(FLAG_OPTIONS) > 0


def test_flag_options_structure() -> None:
    for flag, label in FLAG_OPTIONS:
        assert flag.startswith("/"), f"Flag {flag!r} should start with '/'"
        assert label, "Label must not be empty"


def test_param_options_not_empty() -> None:
    assert len(PARAM_OPTIONS) > 0


def test_param_options_structure() -> None:
    for flag, label, _default in PARAM_OPTIONS:
        assert flag.startswith("/"), f"Flag {flag!r} should start with '/'"
        assert label, "Label must not be empty"


def test_flag_tooltips_keys_are_valid_flags() -> None:
    """Every key in FLAG_TOOLTIPS must correspond to a flag in FLAG_OPTIONS."""
    known_flags = {flag for flag, _ in FLAG_OPTIONS}
    for flag in FLAG_TOOLTIPS:
        assert flag in known_flags, f"Tooltip key {flag!r} is not a known FLAG_OPTIONS flag"


def test_flag_tooltips_values_are_non_empty_strings() -> None:
    """Every FLAG_TOOLTIPS value must be a non-empty string."""
    for flag, tip in FLAG_TOOLTIPS.items():
        assert isinstance(tip, str) and tip.strip(), f"Tooltip for {flag!r} must be a non-empty string"


def test_flag_tooltips_covers_all_flags() -> None:
    """Every flag in FLAG_OPTIONS should have a tooltip entry."""
    known_flags = {flag for flag, _ in FLAG_OPTIONS}
    missing = known_flags - FLAG_TOOLTIPS.keys()
    assert not missing, f"Flags missing tooltips: {sorted(missing)}"


def test_param_tooltips_keys_are_valid_params() -> None:
    """Every key in PARAM_TOOLTIPS must correspond to a flag in PARAM_OPTIONS."""
    known_params = {flag for flag, _, _ in PARAM_OPTIONS}
    for flag in PARAM_TOOLTIPS:
        assert flag in known_params, f"Tooltip key {flag!r} is not a known PARAM_OPTIONS flag"


def test_param_tooltips_values_are_non_empty_strings() -> None:
    """Every PARAM_TOOLTIPS value must be a non-empty string."""
    for flag, tip in PARAM_TOOLTIPS.items():
        assert isinstance(tip, str) and tip.strip(), f"Tooltip for {flag!r} must be a non-empty string"


def test_param_tooltips_covers_all_params() -> None:
    """Every param in PARAM_OPTIONS should have a tooltip entry."""
    known_params = {flag for flag, _, _ in PARAM_OPTIONS}
    missing = known_params - PARAM_TOOLTIPS.keys()
    assert not missing, f"Params missing tooltips: {sorted(missing)}"


# ---------------------------------------------------------------------------
# Default flag/param set checks
# ---------------------------------------------------------------------------


def test_default_flags_empty() -> None:
    """No flags are selected by default; all options start unchecked."""
    assert _DEFAULT_FLAGS == frozenset()


def test_default_params_empty() -> None:
    """No params are selected by default; all options start unchecked."""
    assert _DEFAULT_PARAMS == frozenset()


# ---------------------------------------------------------------------------
# build_command logic
# ---------------------------------------------------------------------------


def test_build_command_requires_src() -> None:
    with pytest.raises(ValueError, match="Source path is required"):
        build_command("", "C:/dst", {}, {})


def test_build_command_requires_dst() -> None:
    with pytest.raises(ValueError, match="Destination path is required"):
        build_command("C:/src", "", {}, {})


def test_build_command_strips_whitespace() -> None:
    """Leading/trailing whitespace in paths is stripped before validation."""
    with patch("rbcopy.builder.sys.platform", "linux"):
        cmd = build_command("  C:/source  ", "  C:/destination  ", {}, {})
    assert cmd[1] == "C:/source"
    assert cmd[2] == "C:/destination"


def test_build_command_minimal() -> None:
    with patch("rbcopy.builder.sys.platform", "linux"):
        cmd = build_command("C:/source", "C:/destination", {}, {})
    assert cmd == ["robocopy", "C:/source", "C:/destination"]


def test_build_command_file_filter_single_pattern() -> None:
    """A single file-pattern token appears between dst and any flags."""
    with patch("rbcopy.builder.sys.platform", "linux"):
        cmd = build_command("C:/src", "C:/dst", {}, {}, file_filter="*.img")
    assert cmd == ["robocopy", "C:/src", "C:/dst", "*.img"]


def test_build_command_file_filter_multiple_patterns() -> None:
    """Multiple space-separated patterns are each inserted as a separate token."""
    cmd = build_command("C:/src", "C:/dst", {}, {}, file_filter="*.img *.raw")
    assert "*.img" in cmd
    assert "*.raw" in cmd


def test_build_command_file_filter_appears_before_flags() -> None:
    """File-pattern tokens must come before any flags in the command."""
    cmd = build_command("C:/src", "C:/dst", {"/MIR": True}, {}, file_filter="*.img")
    assert cmd.index("*.img") < cmd.index("/MIR")


def test_build_command_file_filter_empty_adds_no_tokens() -> None:
    """An empty file_filter must not add any extra tokens to the command."""
    with patch("rbcopy.builder.sys.platform", "linux"):
        cmd = build_command("C:/src", "C:/dst", {}, {}, file_filter="")
    assert cmd == ["robocopy", "C:/src", "C:/dst"]


def test_build_command_file_filter_whitespace_only_adds_no_tokens() -> None:
    """A whitespace-only file_filter string must not add any extra tokens."""
    with patch("rbcopy.builder.sys.platform", "linux"):
        cmd = build_command("C:/src", "C:/dst", {}, {}, file_filter="   ")
    assert cmd == ["robocopy", "C:/src", "C:/dst"]


def test_build_command_flag_enabled() -> None:
    cmd = build_command("C:/source", "C:/destination", {"/MIR": True}, {})
    assert "/MIR" in cmd


def test_build_command_flag_disabled() -> None:
    cmd = build_command("C:/source", "C:/destination", {"/MIR": False}, {})
    assert "/MIR" not in cmd


def test_build_command_flag_option() -> None:
    cmd = build_command("C:/source", "C:/destination", {"/MIR": True, "/S": False}, {})
    assert "/MIR" in cmd
    assert "/S" not in cmd


def test_build_command_param_option() -> None:
    cmd = build_command("C:/source", "C:/destination", {}, {"/R": (True, "5")})
    assert "/R:5" in cmd


def test_build_command_param_copy_flags() -> None:
    cmd = build_command("C:/source", "C:/destination", {}, {"/COPY": (True, "DAT")})
    assert "/COPY:DAT" in cmd


def test_build_command_xf_multivalue() -> None:
    cmd = build_command("C:/source", "C:/destination", {}, {"/XF": (True, "*.tmp *.bak")})
    assert "/XF" in cmd
    assert "*.tmp" in cmd
    assert "*.bak" in cmd


def test_build_command_xd_multivalue() -> None:
    cmd = build_command("C:/source", "C:/destination", {}, {"/XD": (True, "Temp Cache")})
    assert "/XD" in cmd
    assert "Temp" in cmd
    assert "Cache" in cmd


def test_build_command_log_path() -> None:
    cmd = build_command("C:/source", "C:/destination", {}, {"/LOG": (True, "C:/log.txt")})
    assert "/LOG:C:/log.txt" in cmd


def test_build_command_param_disabled_not_included() -> None:
    cmd = build_command("C:/source", "C:/destination", {}, {"/R": (False, "5")})
    assert not any(arg.startswith("/R:") for arg in cmd)


def test_build_command_param_empty_value_not_included() -> None:
    cmd = build_command("C:/source", "C:/destination", {}, {"/MAXSIZE": (True, "")})
    assert not any(arg.startswith("/MAXSIZE") for arg in cmd)


def test_build_command_xf_empty_value_not_included() -> None:
    """Empty /XF value should not add the flag at all."""
    cmd = build_command("C:/source", "C:/destination", {}, {"/XF": (True, "")})
    assert "/XF" not in cmd


def test_build_command_multiple_flags() -> None:
    cmd = build_command("C:/src", "C:/dst", {"/MIR": True, "/NP": True, "/Z": False}, {})
    assert "/MIR" in cmd
    assert "/NP" in cmd
    assert "/Z" not in cmd


def test_build_command_multiple_params() -> None:
    cmd = build_command("C:/src", "C:/dst", {}, {"/R": (True, "3"), "/W": (True, "10")})
    assert "/R:3" in cmd
    assert "/W:10" in cmd


# ---------------------------------------------------------------------------
# SUPERSEDES constant checks
# ---------------------------------------------------------------------------


def test_supersedes_structure() -> None:
    """Every key and every value in SUPERSEDES must be a known flag."""
    all_flags = {flag for flag, _ in FLAG_OPTIONS}
    for sup_flag, implied in SUPERSEDES.items():
        assert sup_flag in all_flags, f"Superseding flag {sup_flag!r} not in FLAG_OPTIONS"
        for implied_flag in implied:
            assert implied_flag in all_flags, f"Implied flag {implied_flag!r} not in FLAG_OPTIONS"


def test_supersedes_mir_implies_e_and_purge() -> None:
    assert "/E" in SUPERSEDES["/MIR"]
    assert "/PURGE" in SUPERSEDES["/MIR"]


def test_supersedes_move_implies_mov() -> None:
    assert "/MOV" in SUPERSEDES["/MOVE"]


def test_supersedes_zb_implies_z_and_b() -> None:
    assert "/Z" in SUPERSEDES["/ZB"]
    assert "/B" in SUPERSEDES["/ZB"]


# ---------------------------------------------------------------------------
# Properties Only preset constant checks
# ---------------------------------------------------------------------------


def test_properties_only_dst_is_string() -> None:
    assert isinstance(PROPERTIES_ONLY_DST, str) and PROPERTIES_ONLY_DST


def test_properties_only_flags_subset_of_flag_options() -> None:
    all_flags = {flag for flag, _ in FLAG_OPTIONS}
    assert PROPERTIES_ONLY_FLAGS.issubset(all_flags), "PROPERTIES_ONLY_FLAGS must be a subset of FLAG_OPTIONS flags"


def test_properties_only_flags_contains_required() -> None:
    required = {"/L", "/MIR", "/NFL", "/NDL"}
    assert required == PROPERTIES_ONLY_FLAGS


def test_properties_only_params_subset_of_param_options() -> None:
    all_params = {flag for flag, _, _ in PARAM_OPTIONS}
    for flag in PROPERTIES_ONLY_PARAMS:
        assert flag in all_params, f"PROPERTIES_ONLY_PARAMS flag {flag!r} not in PARAM_OPTIONS"


def test_properties_only_params_contains_required() -> None:
    assert PROPERTIES_ONLY_PARAMS["/MT"] == "48"
    assert PROPERTIES_ONLY_PARAMS["/R"] == "0"
    assert PROPERTIES_ONLY_PARAMS["/W"] == "0"


# ---------------------------------------------------------------------------
# build_robocopy_command – simplified unified API
# ---------------------------------------------------------------------------


def test_build_robocopy_command_minimal() -> None:
    with patch("rbcopy.builder.sys.platform", "linux"):
        cmd = build_robocopy_command("C:/source", "C:/dest", {})
    assert cmd == ["robocopy", "C:/source", "C:/dest"]


def test_build_robocopy_command_bool_flag_true() -> None:
    cmd = build_robocopy_command("C:/src", "C:/dst", {"/MIR": True})
    assert "/MIR" in cmd


def test_build_robocopy_command_bool_flag_false() -> None:
    cmd = build_robocopy_command("C:/src", "C:/dst", {"/MIR": False})
    assert "/MIR" not in cmd


def test_build_robocopy_command_str_param() -> None:
    cmd = build_robocopy_command("C:/src", "C:/dst", {"/R": "3"})
    assert "/R:3" in cmd


def test_build_robocopy_command_mixed() -> None:
    cmd = build_robocopy_command("C:/src", "C:/dst", {"/MIR": True, "/NP": True, "/R": "5", "/W": "10"})
    assert "/MIR" in cmd
    assert "/NP" in cmd
    assert "/R:5" in cmd
    assert "/W:10" in cmd


def test_build_robocopy_command_requires_source() -> None:
    with pytest.raises(ValueError, match="Source path is required"):
        build_robocopy_command("", "C:/dst", {})


def test_build_robocopy_command_requires_dest() -> None:
    with pytest.raises(ValueError, match="Destination path is required"):
        build_robocopy_command("C:/src", "", {})


def test_build_robocopy_command_xf_str() -> None:
    cmd = build_robocopy_command("C:/src", "C:/dst", {"/XF": "*.tmp *.bak"})
    assert "/XF" in cmd
    assert "*.tmp" in cmd
    assert "*.bak" in cmd


# ---------------------------------------------------------------------------
# DryRunResult dataclass
# ---------------------------------------------------------------------------


def test_dry_run_result_ok_by_default() -> None:
    result = DryRunResult()
    assert result.ok is True
    assert result.warnings == []
    assert result.errors == []


def test_dry_run_result_status_report_empty_when_no_issues() -> None:
    result = DryRunResult()
    assert result.status_report() == ""


def test_dry_run_result_status_report_warning() -> None:
    result = DryRunResult(warnings=["something suboptimal"])
    report = result.status_report()
    assert "[WARN]" in report
    assert "something suboptimal" in report


def test_dry_run_result_status_report_error() -> None:
    result = DryRunResult(ok=False, errors=["path missing"])
    report = result.status_report()
    assert "[ERROR]" in report
    assert "path missing" in report


def test_dry_run_result_status_report_both_warning_and_error() -> None:
    result = DryRunResult(ok=False, warnings=["minor issue"], errors=["fatal issue"])
    report = result.status_report()
    assert "[WARN]" in report
    assert "[ERROR]" in report
    assert "minor issue" in report
    assert "fatal issue" in report


# ---------------------------------------------------------------------------
# validate_command
# ---------------------------------------------------------------------------


def test_validate_command_empty_src(tmp_path: Path) -> None:
    result = validate_command("", str(tmp_path), {}, {})
    assert not result.ok
    assert any("Source" in e for e in result.errors)


def test_validate_command_empty_dst(tmp_path: Path) -> None:
    result = validate_command(str(tmp_path), "", {}, {})
    assert not result.ok
    assert any("Destination" in e for e in result.errors)


def test_validate_command_both_empty() -> None:
    result = validate_command("", "", {}, {})
    assert not result.ok
    assert len(result.errors) == 2


def test_validate_command_nonexistent_src(tmp_path: Path) -> None:
    result = validate_command(str(tmp_path / "nonexistent"), str(tmp_path), {}, {})
    assert not result.ok
    assert any("not exist" in e for e in result.errors)


def test_validate_command_src_is_a_file_not_dir(tmp_path: Path) -> None:
    src_file = tmp_path / "notadir.txt"
    src_file.write_text("x")
    result = validate_command(str(src_file), str(tmp_path), {}, {})
    assert not result.ok
    assert any("not a directory" in e for e in result.errors)


def test_validate_command_dst_is_a_file_not_dir(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    dst_file = tmp_path / "dst.txt"
    dst_file.write_text("x")
    result = validate_command(str(src), str(dst_file), {}, {})
    assert not result.ok
    assert any("not a directory" in e for e in result.errors)


def test_validate_command_valid_paths(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    # dst does not need to exist; robocopy creates it
    result = validate_command(str(src), str(tmp_path / "dst"), {}, {})
    assert result.ok
    assert not result.errors


def test_validate_command_valid_existing_dst(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "dst"
    dst.mkdir()
    result = validate_command(str(src), str(dst), {}, {})
    assert result.ok
    assert not result.errors


def test_validate_command_strips_whitespace(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    result = validate_command(f"  {src}  ", f"  {tmp_path / 'dst'}  ", {}, {})
    assert result.ok


def test_validate_command_warns_on_redundant_flag_e_with_mir(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    # /MIR supersedes /E; selecting both should produce a warning
    result = validate_command(str(src), str(tmp_path / "dst"), {"/MIR": True, "/E": True}, {})
    assert result.ok  # warnings do not make ok=False
    assert any("/E" in w for w in result.warnings)


def test_validate_command_warns_on_redundant_flag_purge_with_mir(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    result = validate_command(str(src), str(tmp_path / "dst"), {"/MIR": True, "/PURGE": True}, {})
    assert any("/PURGE" in w for w in result.warnings)


def test_validate_command_warns_on_redundant_flag_mov_with_move(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    result = validate_command(str(src), str(tmp_path / "dst"), {"/MOVE": True, "/MOV": True}, {})
    assert any("/MOV" in w for w in result.warnings)


def test_validate_command_warns_on_redundant_flags_z_and_b_with_zb(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    result = validate_command(str(src), str(tmp_path / "dst"), {"/ZB": True, "/Z": True, "/B": True}, {})
    assert any("/Z" in w or "/B" in w for w in result.warnings)


def test_validate_command_no_warning_when_superseded_flag_disabled(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    # /MIR enabled, /E disabled → no warning
    result = validate_command(str(src), str(tmp_path / "dst"), {"/MIR": True, "/E": False}, {})
    assert result.ok
    assert not result.warnings


def test_validate_command_no_warning_when_superseding_flag_disabled(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    # /MIR disabled, /E enabled → no supersession warning
    result = validate_command(str(src), str(tmp_path / "dst"), {"/MIR": False, "/E": True}, {})
    assert result.ok
    assert not result.warnings


# ---------------------------------------------------------------------------
# validate_command – param value checks
# ---------------------------------------------------------------------------


def test_validate_command_warns_on_enabled_param_with_empty_value(tmp_path: Path) -> None:
    """validate_command must warn when an enabled param has no value (it will be omitted)."""
    src = tmp_path / "src"
    src.mkdir()
    result = validate_command(str(src), str(tmp_path / "dst"), {}, {"/R": (True, "")})
    assert result.ok  # only a warning, not an error
    assert any("/R" in w for w in result.warnings)


def test_validate_command_no_warning_when_param_disabled_with_empty_value(tmp_path: Path) -> None:
    """validate_command must not warn when a param is disabled (empty value doesn't matter)."""
    src = tmp_path / "src"
    src.mkdir()
    result = validate_command(str(src), str(tmp_path / "dst"), {}, {"/R": (False, "")})
    assert result.ok
    assert not result.warnings


def test_validate_command_no_warning_when_param_has_value(tmp_path: Path) -> None:
    """validate_command must not warn when an enabled param has a non-empty value."""
    src = tmp_path / "src"
    src.mkdir()
    result = validate_command(str(src), str(tmp_path / "dst"), {}, {"/R": (True, "3")})
    assert result.ok
    assert not result.warnings


def test_validate_command_no_warning_for_xf_with_empty_value(tmp_path: Path) -> None:
    """/XF and /XD are pattern lists; an empty value is valid and must not warn."""
    src = tmp_path / "src"
    src.mkdir()
    result = validate_command(str(src), str(tmp_path / "dst"), {}, {"/XF": (True, ""), "/XD": (True, "")})
    assert result.ok
    assert not result.warnings


def test_validate_command_warns_for_redundant_flag_and_empty_param_simultaneously(tmp_path: Path) -> None:
    """Both a redundant-flag warning and an empty-param warning are produced together.

    Exercises the two independent warning loops in validate_command to confirm
    they each fire when their respective conditions are met in the same call.
    """
    src = tmp_path / "src"
    src.mkdir()
    result = validate_command(
        str(src),
        str(tmp_path / "dst"),
        {"/MIR": True, "/E": True},  # /MIR supersedes /E → redundant-flag warning
        {"/R": (True, "")},  # /R enabled but empty value → empty-param warning
    )
    assert result.ok  # warnings only, not errors
    assert any("/E" in w or "redundant" in w for w in result.warnings)
    assert any("/R" in w for w in result.warnings)
    assert len(result.warnings) >= 2
