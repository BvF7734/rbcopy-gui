"""End-to-end filesystem integration tests for rbcopy.

These tests create real temporary directories, run robocopy via the system
subprocess, and verify that files are copied correctly.  They are skipped
automatically on non-Windows platforms where robocopy is unavailable.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from rbcopy.builder import build_robocopy_command

# Robocopy exit codes where a non-zero value does not indicate failure:
#   0 – No files were copied (source and destination are in sync)
#   1 – One or more files were copied successfully
#   2 – Extra files/directories were detected in the destination
#   3 – Combination of 1 and 2
# Codes >= 8 indicate an error.
_ROBOCOPY_SUCCESS_CODES: frozenset[int] = frozenset({0, 1, 2, 3})


@pytest.mark.skipif(sys.platform != "win32", reason="robocopy is only available on Windows")
def test_robocopy_copies_files_to_destination(tmp_path: Path) -> None:
    """Robocopy successfully copies source files to the destination directory.

    Sets up three dummy text files in a temporary source directory, issues a
    robocopy command using :func:`build_robocopy_command`, executes it via
    :func:`subprocess.run`, and then asserts that:

    * The return code is a recognised Robocopy success code (0–3).
    * Each of the three source files now exists in the destination directory.
    * The content of each destination file matches its source counterpart.
    """
    source_dir: Path = tmp_path / "Source"
    dest_dir: Path = tmp_path / "Destination"
    source_dir.mkdir()
    dest_dir.mkdir()

    # Create three dummy text files in the source directory.
    file_data: dict[str, str] = {
        "alpha.txt": "Hello from alpha",
        "beta.txt": "Hello from beta",
        "gamma.txt": "Hello from gamma",
    }
    for filename, content in file_data.items():
        (source_dir / filename).write_text(content, encoding="utf-8")

    cmd: list[str] = build_robocopy_command(
        source=str(source_dir),
        dest=str(dest_dir),
        flags={
            # /NP: suppress progress percentages for cleaner test output
            # /NJH and /NJS: suppress job header/summary in captured output
            "/NP": True,
            "/NJH": True,
            "/NJS": True,
        },
    )

    result: subprocess.CompletedProcess[str] = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,  # robocopy uses non-zero exit codes for success; do not raise
    )

    assert result.returncode in _ROBOCOPY_SUCCESS_CODES, (
        f"robocopy exited with unexpected code {result.returncode}.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    for filename, expected_content in file_data.items():
        dest_file: Path = dest_dir / filename
        assert dest_file.exists(), f"Expected {filename!r} to exist in destination, but it does not."
        actual_content: str = dest_file.read_text(encoding="utf-8")
        assert actual_content == expected_content, (
            f"Content mismatch for {filename!r}: expected {expected_content!r}, got {actual_content!r}"
        )


@pytest.mark.skipif(sys.platform != "win32", reason="robocopy is only available on Windows")
def test_robocopy_mir_deletes_extra_files_in_destination(tmp_path: Path) -> None:
    """The /MIR flag purges files from the destination that do not exist in the source.

    Sets up a source directory containing a single file (``keep_me.txt``) and a
    destination directory that contains an extra file (``delete_me.txt``) absent
    from the source.  After the mirrored robocopy run the test asserts that:

    * The return code is a recognised Robocopy success code (0–3).
    * ``delete_me.txt`` no longer exists in the destination (purged by /MIR).
    * ``keep_me.txt`` was copied from the source and exists in the destination.
    """
    source_dir: Path = tmp_path / "Source"
    dest_dir: Path = tmp_path / "Destination"
    source_dir.mkdir()
    dest_dir.mkdir()

    keep_file: Path = source_dir / "keep_me.txt"
    keep_file.write_text("I should be copied.", encoding="utf-8")

    # Pre-populate the destination with a stray file that the mirror must purge.
    stray_file: Path = dest_dir / "delete_me.txt"
    stray_file.write_text("I should be deleted.", encoding="utf-8")

    cmd: list[str] = build_robocopy_command(
        source=str(source_dir),
        dest=str(dest_dir),
        flags={
            "/MIR": True,
            "/NP": True,
            "/NJH": True,
            "/NJS": True,
        },
    )

    result: subprocess.CompletedProcess[str] = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,  # robocopy uses non-zero exit codes for success; do not raise
    )

    assert result.returncode in _ROBOCOPY_SUCCESS_CODES, (
        f"robocopy exited with unexpected code {result.returncode}.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    assert not stray_file.exists(), (
        "Expected 'delete_me.txt' to be purged from the destination by /MIR, but it still exists."
    )

    dest_keep_file: Path = dest_dir / "keep_me.txt"
    assert dest_keep_file.exists(), (
        "Expected 'keep_me.txt' to be present in the destination after /MIR copy, but it is missing."
    )
