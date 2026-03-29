"""Tests for the rbcopy builder module (pure logic, no GUI dependency)."""

from __future__ import annotations

from pathlib import Path

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
    _powershell_quote,
    build_batch_script,
    build_command,
    build_powershell_script,
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
    cmd = build_command("  C:/source  ", "  C:/destination  ", {}, {})
    assert cmd[1] == "C:/source"
    assert cmd[2] == "C:/destination"


def test_build_command_minimal() -> None:
    cmd = build_command("C:/source", "C:/destination", {}, {})
    assert cmd == ["robocopy", "C:/source", "C:/destination"]


def test_build_command_file_filter_single_pattern() -> None:
    """A single file-pattern token appears between dst and any flags."""
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
    cmd = build_command("C:/src", "C:/dst", {}, {}, file_filter="")
    assert cmd == ["robocopy", "C:/src", "C:/dst"]


def test_build_command_file_filter_whitespace_only_adds_no_tokens() -> None:
    """A whitespace-only file_filter string must not add any extra tokens."""
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


# ---------------------------------------------------------------------------
# _powershell_quote – direct unit tests
# ---------------------------------------------------------------------------


def test_powershell_quote_plain_token() -> None:
    """A token without single quotes is wrapped in single quotes unchanged."""
    assert _powershell_quote("robocopy") == "'robocopy'"


def test_powershell_quote_token_with_spaces() -> None:
    """A token with spaces is wrapped in single quotes."""
    assert _powershell_quote("C:/my folder") == "'C:/my folder'"


def test_powershell_quote_empty_string() -> None:
    """An empty token becomes a pair of single quotes (a valid empty PS literal)."""
    assert _powershell_quote("") == "''"


def test_powershell_quote_internal_single_quote() -> None:
    """A single quote inside the token is escaped by doubling it."""
    assert _powershell_quote("it's") == "'it''s'"


def test_powershell_quote_multiple_internal_single_quotes() -> None:
    """Multiple single quotes inside the token are each doubled independently."""
    assert _powershell_quote("it's a 'file'") == "'it''s a ''file'''"


def test_powershell_quote_special_chars_not_escaped() -> None:
    """Shell-special chars like &, |, $, % need no escaping inside ps single-quotes."""
    assert _powershell_quote("C:/R&D|$path%") == "'C:/R&D|$path%'"


# ---------------------------------------------------------------------------
# build_batch_script
# ---------------------------------------------------------------------------


def test_build_batch_script_starts_with_echo_off() -> None:
    """build_batch_script must begin with '@echo off'."""
    script = build_batch_script(["robocopy", "C:/src", "C:/dst"])
    assert script.startswith("@echo off")


def test_build_batch_script_contains_command() -> None:
    """build_batch_script must embed the full robocopy command."""
    cmd = ["robocopy", "C:/src", "C:/dst", "/MIR", "/NP"]
    script = build_batch_script(cmd)
    assert "robocopy" in script
    assert "C:/src" in script
    assert "C:/dst" in script
    assert "/MIR" in script
    assert "/NP" in script


def test_build_batch_script_exits_with_errorlevel() -> None:
    """build_batch_script must propagate the robocopy exit code and pause."""
    script = build_batch_script(["robocopy", "C:/src", "C:/dst"])
    assert "exit /b %ROBOCOPY_EXIT%" in script
    assert "pause" in script


def test_build_batch_script_quotes_paths_with_spaces() -> None:
    """build_batch_script must double-quote tokens that contain spaces."""
    cmd = ["robocopy", "C:/my source", "C:/my dest"]
    script = build_batch_script(cmd)
    assert '"C:/my source"' in script
    assert '"C:/my dest"' in script


def test_build_batch_script_quotes_special_chars_with_spaces() -> None:
    """build_batch_script must wrap tokens with spaces in double-quotes via list2cmdline.

    This also protects batch-special characters (&, |, ^, <, >) that appear
    alongside spaces within the same token.
    """
    cmd = ["robocopy", "C:/R&D folder", "C:/my dest"]
    script = build_batch_script(cmd)
    assert '"C:/R&D folder"' in script
    assert '"C:/my dest"' in script


def test_build_batch_script_uses_crlf_line_endings() -> None:
    """build_batch_script must use Windows-style CRLF line endings."""
    script = build_batch_script(["robocopy", "C:/src", "C:/dst"])
    assert "\r\n" in script


def test_build_batch_script_returns_string() -> None:
    result = build_batch_script(["robocopy", "C:/src", "C:/dst"])
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# build_powershell_script
# ---------------------------------------------------------------------------


def test_build_powershell_script_uses_call_operator() -> None:
    """build_powershell_script must invoke the executable with the '&' operator."""
    script = build_powershell_script(["robocopy", "C:/src", "C:/dst"])
    assert "& 'robocopy'" in script


def test_build_powershell_script_contains_command() -> None:
    """build_powershell_script must embed the full robocopy command."""
    cmd = ["robocopy", "C:/src", "C:/dst", "/MIR", "/NP"]
    script = build_powershell_script(cmd)
    assert "robocopy" in script
    assert "C:/src" in script
    assert "C:/dst" in script
    assert "/MIR" in script
    assert "/NP" in script


def test_build_powershell_script_exits_with_lastexitcode() -> None:
    """build_powershell_script must propagate the robocopy exit code and pause."""
    script = build_powershell_script(["robocopy", "C:/src", "C:/dst"])
    assert "exit $exitCode" in script
    assert "Read-Host" in script


def test_build_powershell_script_quotes_paths_with_spaces() -> None:
    """build_powershell_script must single-quote every argument, protecting special chars.

    Single-quoted strings in PowerShell are completely literal (no variable
    expansion, no metacharacter interpretation), making them safe for paths
    containing spaces, &, |, %, $, etc.
    """
    cmd = ["robocopy", "C:/my source", "C:/my dest"]
    script = build_powershell_script(cmd)
    assert "'C:/my source'" in script
    assert "'C:/my dest'" in script


def test_build_powershell_script_escapes_internal_single_quotes() -> None:
    """build_powershell_script must escape single quotes inside tokens by doubling them."""
    cmd = ["robocopy", "C:/it's a folder", "C:/dst"]
    script = build_powershell_script(cmd)
    # Internal ' is escaped as '' in a PowerShell single-quoted string.
    assert "'C:/it''s a folder'" in script


def test_build_powershell_script_returns_string() -> None:
    result = build_powershell_script(["robocopy", "C:/src", "C:/dst"])
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# exit_code_label
# ---------------------------------------------------------------------------


def test_exit_code_label_returns_string() -> None:
    """exit_code_label always returns a str for any input."""
    from rbcopy.builder import exit_code_label

    assert isinstance(exit_code_label(0), str)
    assert isinstance(exit_code_label(-1), str)
    assert isinstance(exit_code_label(999), str)


def test_exit_code_label_minus_one() -> None:
    """exit_code_label describes -1 as an unknown error."""
    from rbcopy.builder import exit_code_label

    assert "Unknown error" in exit_code_label(-1)
    assert "log" in exit_code_label(-1).lower()


def test_exit_code_label_zero() -> None:
    """exit_code_label describes 0 as nothing to do."""
    from rbcopy.builder import exit_code_label

    assert "Nothing to do" in exit_code_label(0)


def test_exit_code_label_one() -> None:
    """exit_code_label describes 1 as files copied successfully."""
    from rbcopy.builder import exit_code_label

    assert "Files copied successfully" in exit_code_label(1)


def test_exit_code_label_two() -> None:
    """exit_code_label describes 2 as extra files at destination."""
    from rbcopy.builder import exit_code_label

    label = exit_code_label(2)
    assert "Extra files" in label
    assert "destination" in label.lower()


def test_exit_code_label_three() -> None:
    """exit_code_label describes 3 as files copied with extra files at destination."""
    from rbcopy.builder import exit_code_label

    label = exit_code_label(3)
    assert "Files copied" in label
    assert "extra files" in label.lower()


def test_exit_code_label_four() -> None:
    """exit_code_label describes 4 as mismatched files."""
    from rbcopy.builder import exit_code_label

    assert "Mismatched" in exit_code_label(4)


def test_exit_code_label_five() -> None:
    """exit_code_label describes 5 as files copied with mismatched files."""
    from rbcopy.builder import exit_code_label

    label = exit_code_label(5)
    assert "Files copied" in label
    assert "mismatched" in label.lower()
    assert "log" in label.lower()


def test_exit_code_label_six() -> None:
    """exit_code_label describes 6 as extra and mismatched files."""
    from rbcopy.builder import exit_code_label

    label = exit_code_label(6)
    assert "mismatched" in label.lower()
    assert "log" in label.lower()


def test_exit_code_label_seven() -> None:
    """exit_code_label describes 7 as files copied with multiple warnings."""
    from rbcopy.builder import exit_code_label

    label = exit_code_label(7)
    assert "Files copied" in label
    assert "log" in label.lower()


def test_exit_code_label_eight() -> None:
    """exit_code_label describes 8 as copy failures."""
    from rbcopy.builder import exit_code_label

    label = exit_code_label(8)
    assert "Copy failures" in label
    assert "log" in label.lower()


def test_exit_code_label_sixteen() -> None:
    """exit_code_label describes 16 as a fatal error."""
    from rbcopy.builder import exit_code_label

    label = exit_code_label(16)
    assert "Fatal error" in label
    assert "log" in label.lower()


def test_exit_code_label_unknown_combination_falls_back_gracefully() -> None:
    """exit_code_label returns a composed fallback for unusual bit combinations."""
    from rbcopy.builder import exit_code_label

    # 9 = 8 + 1 (copy failures + files copied) — not in the explicit lookup table
    label = exit_code_label(9)
    assert isinstance(label, str)
    assert len(label) > 0


def test_exit_code_label_failure_bits_include_check_log() -> None:
    """exit_code_label includes 'Check the log' for any code with bit 8 or 16 set."""
    from rbcopy.builder import exit_code_label

    # Use an unusual combination not in the explicit table to exercise the fallback.
    # 24 = 8 + 16
    label = exit_code_label(24)
    assert "log" in label.lower()


def test_exit_code_label_no_check_log_for_low_codes() -> None:
    """exit_code_label does not append 'Check the log' for codes below 8."""
    from rbcopy.builder import exit_code_label

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
