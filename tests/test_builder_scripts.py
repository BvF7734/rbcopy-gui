"""Tests for rbcopy builder script-export helpers."""

from __future__ import annotations


from unittest.mock import patch


from rbcopy.builder import (
    _apply_extended_path_prefix,
    _powershell_quote,
    build_batch_script,
    build_command,
    build_powershell_script,
)

# ---------------------------------------------------------------------------
# _apply_extended_path_prefix – direct unit tests
# ---------------------------------------------------------------------------


def test_apply_extended_path_prefix_noop_on_non_windows() -> None:
    """The function must return the path unchanged on non-Windows platforms."""
    with patch("rbcopy.builder.sys.platform", "linux"):
        assert _apply_extended_path_prefix("C:/source") == "C:/source"
        assert _apply_extended_path_prefix("/home/user/data") == "/home/user/data"


def test_apply_extended_path_prefix_drive_letter_path() -> None:
    """An absolute drive-letter path gains the \\\\?\\ prefix on Windows."""
    with patch("rbcopy.builder.sys.platform", "win32"):
        result = _apply_extended_path_prefix("C:\\Users\\data")
    assert result == "\\\\?\\C:\\Users\\data"


def test_apply_extended_path_prefix_normalises_forward_slashes() -> None:
    """Forward slashes in an otherwise absolute Windows path are converted to backslashes."""
    with patch("rbcopy.builder.sys.platform", "win32"):
        result = _apply_extended_path_prefix("C:/Users/data")
    assert result == "\\\\?\\C:\\Users\\data"


def test_apply_extended_path_prefix_unc_path() -> None:
    """A UNC path gains the \\\\?\\UNC\\ prefix (not a plain \\\\?\\\\\\\\ prefix)."""
    with patch("rbcopy.builder.sys.platform", "win32"):
        result = _apply_extended_path_prefix("\\\\server\\share\\docs")
    assert result == "\\\\?\\UNC\\server\\share\\docs"


def test_apply_extended_path_prefix_already_prefixed_not_doubled() -> None:
    """A path that already carries the prefix is returned unchanged."""
    already_prefixed = "\\\\?\\C:\\long\\path"
    with patch("rbcopy.builder.sys.platform", "win32"):
        result = _apply_extended_path_prefix(already_prefixed)
    assert result == already_prefixed


def test_apply_extended_path_prefix_relative_path_unchanged() -> None:
    """A relative path must not receive the prefix even on Windows."""
    with patch("rbcopy.builder.sys.platform", "win32"):
        result = _apply_extended_path_prefix("relative\\path\\file")
    assert result == "relative\\path\\file"


def test_apply_extended_path_prefix_not_applied_in_build_command() -> None:
    """build_command does NOT apply the extended-length prefix to paths.

    Robocopy handles long paths natively; the \\?\\ prefix is for direct
    Win32 API calls and causes robocopy to mis-parse path arguments.
    """
    with patch("rbcopy.builder.sys.platform", "win32"):
        cmd = build_command("C:/source", "C:/destination", {}, {})
    assert cmd[0] == "robocopy"
    assert cmd[1] == "C:/source"
    assert cmd[2] == "C:/destination"


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
