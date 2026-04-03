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


# ---------------------------------------------------------------------------
# Gap 16: Additional E2E tests covering more flags and scenarios
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="robocopy is only available on Windows")
def test_robocopy_e_flag_copies_empty_subdirectories(tmp_path: Path) -> None:
    """The /E flag replicates the full directory tree, including empty subdirectories."""
    source_dir: Path = tmp_path / "Source"
    dest_dir: Path = tmp_path / "Destination"
    source_dir.mkdir()
    dest_dir.mkdir()

    # Create a non-empty and an empty subdirectory in the source.
    non_empty_sub: Path = source_dir / "non_empty"
    non_empty_sub.mkdir()
    (non_empty_sub / "file.txt").write_text("content", encoding="utf-8")
    empty_sub: Path = source_dir / "empty_sub"
    empty_sub.mkdir()

    cmd: list[str] = build_robocopy_command(
        source=str(source_dir),
        dest=str(dest_dir),
        flags={"/E": True, "/NP": True, "/NJH": True, "/NJS": True},
    )
    result: subprocess.CompletedProcess[str] = subprocess.run(cmd, capture_output=True, text=True, check=False)

    assert result.returncode in _ROBOCOPY_SUCCESS_CODES, (
        f"robocopy /E exited {result.returncode}.\nstdout:\n{result.stdout}"
    )
    assert (dest_dir / "non_empty" / "file.txt").exists(), "File inside non-empty subdir must be copied."
    assert (dest_dir / "empty_sub").is_dir(), "/E must copy the empty subdirectory."


@pytest.mark.skipif(sys.platform != "win32", reason="robocopy is only available on Windows")
def test_robocopy_s_flag_skips_empty_subdirectories(tmp_path: Path) -> None:
    """The /S flag copies non-empty subdirectories but skips empty ones."""
    source_dir: Path = tmp_path / "Source"
    dest_dir: Path = tmp_path / "Destination"
    source_dir.mkdir()
    dest_dir.mkdir()

    non_empty_sub: Path = source_dir / "with_files"
    non_empty_sub.mkdir()
    (non_empty_sub / "data.txt").write_text("data", encoding="utf-8")
    empty_sub: Path = source_dir / "empty_sub"
    empty_sub.mkdir()

    cmd: list[str] = build_robocopy_command(
        source=str(source_dir),
        dest=str(dest_dir),
        flags={"/S": True, "/NP": True, "/NJH": True, "/NJS": True},
    )
    result: subprocess.CompletedProcess[str] = subprocess.run(cmd, capture_output=True, text=True, check=False)

    assert result.returncode in _ROBOCOPY_SUCCESS_CODES, (
        f"robocopy /S exited {result.returncode}.\nstdout:\n{result.stdout}"
    )
    assert (dest_dir / "with_files" / "data.txt").exists(), "Non-empty subdir must be copied by /S."
    assert not (dest_dir / "empty_sub").exists(), "/S must NOT copy empty subdirectories."


@pytest.mark.skipif(sys.platform != "win32", reason="robocopy is only available on Windows")
def test_robocopy_l_flag_does_not_copy_files(tmp_path: Path) -> None:
    """The /L flag lists files without actually copying them; destination stays empty."""
    source_dir: Path = tmp_path / "Source"
    dest_dir: Path = tmp_path / "Destination"
    source_dir.mkdir()
    dest_dir.mkdir()

    (source_dir / "test.txt").write_text("should not appear in dest", encoding="utf-8")

    cmd: list[str] = build_robocopy_command(
        source=str(source_dir),
        dest=str(dest_dir),
        flags={"/L": True, "/NP": True, "/NJH": True, "/NJS": True},
    )
    result: subprocess.CompletedProcess[str] = subprocess.run(cmd, capture_output=True, text=True, check=False)

    assert result.returncode in _ROBOCOPY_SUCCESS_CODES, (
        f"robocopy /L exited {result.returncode}.\nstdout:\n{result.stdout}"
    )
    assert not (dest_dir / "test.txt").exists(), "/L is list-only and must not create destination files."


@pytest.mark.skipif(sys.platform != "win32", reason="robocopy is only available on Windows")
def test_robocopy_xf_excludes_matching_files(tmp_path: Path) -> None:
    """The /XF flag prevents files matching the pattern from being copied."""
    source_dir: Path = tmp_path / "Source"
    dest_dir: Path = tmp_path / "Destination"
    source_dir.mkdir()
    dest_dir.mkdir()

    (source_dir / "keep.txt").write_text("keep", encoding="utf-8")
    (source_dir / "skip.log").write_text("skip", encoding="utf-8")

    cmd: list[str] = build_robocopy_command(
        source=str(source_dir),
        dest=str(dest_dir),
        flags={"/XF": "*.log", "/NP": True, "/NJH": True, "/NJS": True},
    )
    result: subprocess.CompletedProcess[str] = subprocess.run(cmd, capture_output=True, text=True, check=False)

    assert result.returncode in _ROBOCOPY_SUCCESS_CODES, (
        f"robocopy /XF exited {result.returncode}.\nstdout:\n{result.stdout}"
    )
    assert (dest_dir / "keep.txt").exists(), "keep.txt must be copied."
    assert not (dest_dir / "skip.log").exists(), "/XF *.log must exclude skip.log."


@pytest.mark.skipif(sys.platform != "win32", reason="robocopy is only available on Windows")
def test_robocopy_xd_excludes_matching_directory(tmp_path: Path) -> None:
    """The /XD flag prevents directories matching the name from being copied."""
    source_dir: Path = tmp_path / "Source"
    dest_dir: Path = tmp_path / "Destination"
    source_dir.mkdir()
    dest_dir.mkdir()

    included: Path = source_dir / "included"
    included.mkdir()
    (included / "a.txt").write_text("a", encoding="utf-8")
    excluded: Path = source_dir / "excluded"
    excluded.mkdir()
    (excluded / "b.txt").write_text("b", encoding="utf-8")

    cmd: list[str] = build_robocopy_command(
        source=str(source_dir),
        dest=str(dest_dir),
        flags={"/E": True, "/XD": "excluded", "/NP": True, "/NJH": True, "/NJS": True},
    )
    result: subprocess.CompletedProcess[str] = subprocess.run(cmd, capture_output=True, text=True, check=False)

    assert result.returncode in _ROBOCOPY_SUCCESS_CODES, (
        f"robocopy /XD exited {result.returncode}.\nstdout:\n{result.stdout}"
    )
    assert (dest_dir / "included" / "a.txt").exists(), "included dir must be copied."
    assert not (dest_dir / "excluded").exists(), "/XD excluded must prevent that directory from being copied."


@pytest.mark.skipif(sys.platform != "win32", reason="robocopy is only available on Windows")
def test_robocopy_purge_deletes_extra_destination_files(tmp_path: Path) -> None:
    """The /PURGE flag removes files in the destination that are absent from the source."""
    source_dir: Path = tmp_path / "Source"
    dest_dir: Path = tmp_path / "Destination"
    source_dir.mkdir()
    dest_dir.mkdir()

    (source_dir / "kept.txt").write_text("kept", encoding="utf-8")
    stray: Path = dest_dir / "stray.txt"
    stray.write_text("stray", encoding="utf-8")

    cmd: list[str] = build_robocopy_command(
        source=str(source_dir),
        dest=str(dest_dir),
        flags={"/PURGE": True, "/NP": True, "/NJH": True, "/NJS": True},
    )
    result: subprocess.CompletedProcess[str] = subprocess.run(cmd, capture_output=True, text=True, check=False)

    assert result.returncode in _ROBOCOPY_SUCCESS_CODES, (
        f"robocopy /PURGE exited {result.returncode}.\nstdout:\n{result.stdout}"
    )
    assert not stray.exists(), "/PURGE must delete stray.txt from the destination."
    assert (dest_dir / "kept.txt").exists(), "kept.txt must be present in destination."


@pytest.mark.skipif(sys.platform != "win32", reason="robocopy is only available on Windows")
def test_robocopy_e_preserves_nested_directory_structure(tmp_path: Path) -> None:
    """/E copies a deeply-nested (3+ level) directory tree correctly."""
    source_dir: Path = tmp_path / "Source"
    dest_dir: Path = tmp_path / "Destination"
    source_dir.mkdir()
    dest_dir.mkdir()

    # Build a 4-level deep structure.
    leaf: Path = source_dir / "a" / "b" / "c" / "d"
    leaf.mkdir(parents=True)
    (leaf / "deep.txt").write_text("deep", encoding="utf-8")

    cmd: list[str] = build_robocopy_command(
        source=str(source_dir),
        dest=str(dest_dir),
        flags={"/E": True, "/NP": True, "/NJH": True, "/NJS": True},
    )
    result: subprocess.CompletedProcess[str] = subprocess.run(cmd, capture_output=True, text=True, check=False)

    assert result.returncode in _ROBOCOPY_SUCCESS_CODES, (
        f"robocopy /E nested exited {result.returncode}.\nstdout:\n{result.stdout}"
    )
    assert (dest_dir / "a" / "b" / "c" / "d" / "deep.txt").exists(), (
        "Deeply-nested file must be present in destination after /E copy."
    )


@pytest.mark.skipif(sys.platform != "win32", reason="robocopy is only available on Windows")
def test_robocopy_file_filter_copies_only_matching_files(tmp_path: Path) -> None:
    """A positional file filter copies only files matching the pattern."""
    source_dir: Path = tmp_path / "Source"
    dest_dir: Path = tmp_path / "Destination"
    source_dir.mkdir()
    dest_dir.mkdir()

    (source_dir / "image.png").write_text("img", encoding="utf-8")
    (source_dir / "document.txt").write_text("doc", encoding="utf-8")
    (source_dir / "photo.jpg").write_text("jpg", encoding="utf-8")

    # build_robocopy_command uses build_command internally; pass the file
    # filter as a param-style flag with the pattern as its value.
    from rbcopy.builder import build_command

    cmd: list[str] = build_command(
        src=str(source_dir),
        dst=str(dest_dir),
        flag_selections={"/NP": True, "/NJH": True, "/NJS": True},
        param_selections={},
        file_filter="*.txt",
    )
    result: subprocess.CompletedProcess[str] = subprocess.run(cmd, capture_output=True, text=True, check=False)

    assert result.returncode in _ROBOCOPY_SUCCESS_CODES, (
        f"robocopy file-filter exited {result.returncode}.\nstdout:\n{result.stdout}"
    )
    assert (dest_dir / "document.txt").exists(), "document.txt must be copied by *.txt filter."
    assert not (dest_dir / "image.png").exists(), "image.png must NOT be copied by *.txt filter."
    assert not (dest_dir / "photo.jpg").exists(), "photo.jpg must NOT be copied by *.txt filter."
