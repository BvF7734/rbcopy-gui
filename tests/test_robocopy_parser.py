"""Tests for rbcopy.robocopy_parser."""

from __future__ import annotations

from pathlib import Path


from rbcopy.robocopy_parser import (
    RobocopySummary,
    _TAIL_BYTES,
    _find_last_dash_index,
    _strip_prefix,
    parse_summary_from_log,
)

# ---------------------------------------------------------------------------
# Sample log content helpers
# ---------------------------------------------------------------------------

# The session log prefix format produced by rbcopy.logger:
#   YYYY-MM-DD HH:MM:SS [DEBUG   ] rbcopy.gui: <message>
_PREFIX = "2024-01-01 12:00:00 [DEBUG   ] rbcopy.gui: "

# A complete robocopy summary block as it appears in the session log.
_SUMMARY_BLOCK = """\
{p}
{p}               Total    Copied   Skipped  Mismatch    FAILED    Extras
{p}    Dirs :         2         1         1         0         0         0
{p}   Files :         5         3         2         0         0         0
{p}   Bytes :   1.47 k       768       679         0         0         0
{p}   Times :   0:00:01   0:00:00                       0:00:00   0:00:00
{p}   Speed :             7680000 Bytes/sec.
{p}   Speed :              439.453 MegaBytes/min.
{p}   Ended : Monday, January 1, 2024 12:00:01 AM
{p}""".format(p=_PREFIX)

_DASH_LINE = _PREFIX + "-" * 78


def _make_log(tmp_path: Path, body: str) -> Path:
    """Write *body* to a log file and return its path."""
    p = tmp_path / "robocopy_job_20240101_120000.log"
    p.write_text(body, encoding="utf-8")
    return p


def _full_log(summary_block: str = _SUMMARY_BLOCK) -> str:
    """Return a realistic session log containing one job run."""
    header = (
        f"{_PREFIX}Log file: C:\\some\\path\\log.log\n"
        f"{_PREFIX}Robocopy command: robocopy C:\\src C:\\dst /MIR /NP\n"
        f"{_DASH_LINE}\n"
        f"{_PREFIX}\n"
        f"{_PREFIX}               Source : C:\\src\\\n"
        f"{_PREFIX}                 Dest : C:\\dst\\\n"
        f"{_PREFIX}\n"
        f"{_DASH_LINE}\n"
    )
    return header + summary_block


# ---------------------------------------------------------------------------
# _strip_prefix
# ---------------------------------------------------------------------------


def test_strip_prefix_removes_log_header() -> None:
    line = f"{_PREFIX}   Dirs :         2         1         1         0         0         0"
    assert _strip_prefix(line) == "   Dirs :         2         1         1         0         0         0"


def test_strip_prefix_leaves_plain_lines_unchanged() -> None:
    plain = "no prefix here"
    assert _strip_prefix(plain) == plain


def test_strip_prefix_handles_info_level() -> None:
    line = "2024-01-01 12:00:00 [INFO    ] rbcopy.gui: some info"
    assert _strip_prefix(line) == "some info"


def test_strip_prefix_handles_warning_level() -> None:
    line = "2024-01-01 12:00:00 [WARNING ] rbcopy.cli: some warning"
    assert _strip_prefix(line) == "some warning"


# ---------------------------------------------------------------------------
# _find_last_dash_index
# ---------------------------------------------------------------------------


def test_find_last_dash_index_returns_none_for_empty() -> None:
    assert _find_last_dash_index([]) is None


def test_find_last_dash_index_returns_none_when_no_dashes() -> None:
    assert _find_last_dash_index(["line one", "line two"]) is None


def test_find_last_dash_index_returns_correct_index() -> None:
    lines = ["a", "-" * 78, "b", "-" * 78, "c"]
    assert _find_last_dash_index(lines) == 3


def test_find_last_dash_index_single_dash_line() -> None:
    lines = ["a", "-" * 30, "b"]
    assert _find_last_dash_index(lines) == 1


# ---------------------------------------------------------------------------
# parse_summary_from_log – happy path
# ---------------------------------------------------------------------------


def test_parse_summary_files_counts(tmp_path: Path) -> None:
    log = _make_log(tmp_path, _full_log())
    summary = parse_summary_from_log(log)
    assert summary is not None
    assert summary.files_total == 5
    assert summary.files_copied == 3
    assert summary.files_skipped == 2
    assert summary.files_failed == 0


def test_parse_summary_dirs_counts(tmp_path: Path) -> None:
    log = _make_log(tmp_path, _full_log())
    summary = parse_summary_from_log(log)
    assert summary is not None
    assert summary.dirs_total == 2
    assert summary.dirs_copied == 1
    assert summary.dirs_skipped == 1
    assert summary.dirs_failed == 0


def test_parse_summary_bytes(tmp_path: Path) -> None:
    log = _make_log(tmp_path, _full_log())
    summary = parse_summary_from_log(log)
    assert summary is not None
    assert summary.bytes_total == "1.47 k"
    assert summary.bytes_copied == "768"


def test_parse_summary_duration(tmp_path: Path) -> None:
    log = _make_log(tmp_path, _full_log())
    summary = parse_summary_from_log(log)
    assert summary is not None
    assert summary.duration == "0:00:01"


def test_parse_summary_speed_bytes(tmp_path: Path) -> None:
    log = _make_log(tmp_path, _full_log())
    summary = parse_summary_from_log(log)
    assert summary is not None
    assert summary.speed_bytes_sec == "7680000"


def test_parse_summary_speed_mb(tmp_path: Path) -> None:
    log = _make_log(tmp_path, _full_log())
    summary = parse_summary_from_log(log)
    assert summary is not None
    assert summary.speed_mb_min == "439.453"


def test_parse_summary_ended(tmp_path: Path) -> None:
    log = _make_log(tmp_path, _full_log())
    summary = parse_summary_from_log(log)
    assert summary is not None
    assert summary.ended == "Monday, January 1, 2024 12:00:01 AM"


# ---------------------------------------------------------------------------
# parse_summary_from_log – edge cases
# ---------------------------------------------------------------------------


def test_parse_summary_returns_none_when_no_dashes(tmp_path: Path) -> None:
    """No dash separator means no summary section — returns None."""
    log = _make_log(tmp_path, f"{_PREFIX}just some output\n")
    assert parse_summary_from_log(log) is None


def test_parse_summary_returns_none_for_empty_file(tmp_path: Path) -> None:
    log = _make_log(tmp_path, "")
    assert parse_summary_from_log(log) is None


def test_parse_summary_returns_none_when_file_missing(tmp_path: Path) -> None:
    result = parse_summary_from_log(tmp_path / "nonexistent.log")
    assert result is None


def test_parse_summary_returns_none_when_dash_but_no_data(tmp_path: Path) -> None:
    """Dash separator present but no summary rows — returns None."""
    content = f"{_DASH_LINE}\n{_PREFIX}some other content\n"
    log = _make_log(tmp_path, content)
    assert parse_summary_from_log(log) is None


def test_parse_summary_returns_last_when_multiple_jobs(tmp_path: Path) -> None:
    """When a log contains two job runs, the last summary is returned."""
    first_summary = (
        f"{_DASH_LINE}\n"
        f"{_PREFIX}   Dirs :         1         1         0         0         0         0\n"
        f"{_PREFIX}  Files :        10        10         0         0         0         0\n"
        f"{_PREFIX}  Times :   0:00:05   0:00:04                       0:00:00   0:00:00\n"
    )
    second_summary = (
        f"{_DASH_LINE}\n"
        f"{_PREFIX}   Dirs :         3         2         1         0         0         0\n"
        f"{_PREFIX}  Files :        20        15         5         0         0         0\n"
        f"{_PREFIX}  Times :   0:00:10   0:00:08                       0:00:00   0:00:00\n"
    )
    log = _make_log(tmp_path, first_summary + second_summary)
    summary = parse_summary_from_log(log)
    assert summary is not None
    assert summary.files_total == 20
    assert summary.files_copied == 15
    assert summary.dirs_copied == 2


def test_parse_summary_handles_failed_files(tmp_path: Path) -> None:
    """Non-zero FAILED count is correctly parsed into files_failed."""
    block = (
        f"{_DASH_LINE}\n"
        f"{_PREFIX}  Files :        10         7         2         0         1         0\n"
        f"{_PREFIX}  Times :   0:00:02   0:00:01                       0:00:00   0:00:00\n"
    )
    log = _make_log(tmp_path, block)
    summary = parse_summary_from_log(log)
    assert summary is not None
    assert summary.files_failed == 1


def test_parse_summary_bytes_with_megabyte_suffix(tmp_path: Path) -> None:
    """Bytes values with 'm' suffix are preserved as strings."""
    block = (
        f"{_DASH_LINE}\n"
        f"{_PREFIX}  Files :         1         1         0         0         0         0\n"
        f"{_PREFIX}  Bytes :   3.20 m    3.20 m         0         0         0         0\n"
        f"{_PREFIX}  Times :   0:00:03   0:00:02                       0:00:00   0:00:00\n"
    )
    log = _make_log(tmp_path, block)
    summary = parse_summary_from_log(log)
    assert summary is not None
    assert "m" in (summary.bytes_total or "").lower()


def test_parse_summary_without_speed_lines(tmp_path: Path) -> None:
    """Speed lines are optional — summary still parses when absent."""
    block = (
        f"{_DASH_LINE}\n"
        f"{_PREFIX}  Files :         5         3         2         0         0         0\n"
        f"{_PREFIX}  Bytes :       768       512       256         0         0         0\n"
        f"{_PREFIX}  Times :   0:00:01   0:00:00                       0:00:00   0:00:00\n"
    )
    log = _make_log(tmp_path, block)
    summary = parse_summary_from_log(log)
    assert summary is not None
    assert summary.speed_bytes_sec is None
    assert summary.speed_mb_min is None
    assert summary.files_copied == 3


def test_parse_summary_large_file_reads_tail(tmp_path: Path) -> None:
    """For files larger than _TAIL_BYTES, only the tail is read."""
    # Pad with enough filler to push the summary past the tail window
    filler = (_PREFIX + "x" * 100 + "\n") * (_TAIL_BYTES // 102 + 10)
    content = filler + _full_log()
    log = _make_log(tmp_path, content)
    summary = parse_summary_from_log(log)
    assert summary is not None
    assert summary.files_total == 5


# ---------------------------------------------------------------------------
# Localization: non-English summary blocks
# ---------------------------------------------------------------------------

# French (fr-FR) summary block — robocopy on a French Windows installation.
_SUMMARY_BLOCK_FR = """\
{p}
{p}               Total    Copié    Ignoré   NonCorr.    ÉCHEC   Extras
{p}    Répertoires :         2         1         1         0         0         0
{p}       Fichiers :         5         3         2         0         0         0
{p}         Octets :   1.47 k       768       679         0         0         0
{p}         Durées :   0:00:01   0:00:00                       0:00:00   0:00:00
{p}        Vitesse :             7680000 Octets/s.
{p}        Vitesse :              439.453 Mégaoctets/min.
{p}        Terminé : lundi 1 janvier 2024 00:00:01
{p}""".format(p=_PREFIX)

# German (de-DE) summary block — robocopy on a German Windows installation.
_SUMMARY_BLOCK_DE = """\
{p}
{p}               Gesamt   Kopiert  Übersp.  Ungleich    FEHLER  Extras
{p}    Verzeichnisse :         2         1         1         0         0         0
{p}          Dateien :         5         3         2         0         0         0
{p}            Bytes :   1.47 k       768       679         0         0         0
{p}           Zeiten :   0:00:01   0:00:00                       0:00:00   0:00:00
{p}          Geschw. :             7680000 Bytes/Sek.
{p}          Geschw. :              439.453 MB/Min.
{p}             Ende : Montag, 1. Januar 2024 00:00:01
{p}""".format(p=_PREFIX)


def test_parse_summary_french_locale(tmp_path: Path) -> None:
    """Summary block with French Windows UI labels is correctly parsed."""
    log = _make_log(tmp_path, _full_log(_SUMMARY_BLOCK_FR))
    summary = parse_summary_from_log(log)
    assert summary is not None
    assert summary.dirs_total == 2
    assert summary.dirs_copied == 1
    assert summary.dirs_skipped == 1
    assert summary.dirs_failed == 0
    assert summary.files_total == 5
    assert summary.files_copied == 3
    assert summary.files_skipped == 2
    assert summary.files_failed == 0
    assert summary.bytes_total == "1.47 k"
    assert summary.bytes_copied == "768"
    assert summary.duration == "0:00:01"
    assert summary.speed_bytes_sec == "7680000"
    assert summary.speed_mb_min == "439.453"
    assert summary.ended is not None


def test_parse_summary_german_locale(tmp_path: Path) -> None:
    """Summary block with German Windows UI labels is correctly parsed."""
    log = _make_log(tmp_path, _full_log(_SUMMARY_BLOCK_DE))
    summary = parse_summary_from_log(log)
    assert summary is not None
    assert summary.dirs_total == 2
    assert summary.dirs_copied == 1
    assert summary.dirs_skipped == 1
    assert summary.dirs_failed == 0
    assert summary.files_total == 5
    assert summary.files_copied == 3
    assert summary.files_skipped == 2
    assert summary.files_failed == 0
    assert summary.bytes_total == "1.47 k"
    assert summary.bytes_copied == "768"
    assert summary.duration == "0:00:01"
    assert summary.speed_bytes_sec == "7680000"
    assert summary.speed_mb_min == "439.453"
    assert summary.ended is not None


# ---------------------------------------------------------------------------
# RobocopySummary.format_card
# ---------------------------------------------------------------------------


def _make_summary(**kwargs: object) -> RobocopySummary:
    defaults: dict[str, object] = {
        "files_total": 5,
        "files_copied": 3,
        "files_skipped": 2,
        "files_failed": 0,
        "dirs_total": 2,
        "dirs_copied": 1,
        "dirs_skipped": 1,
        "dirs_failed": 0,
        "bytes_total": "1.47 k",
        "bytes_copied": "768",
        "duration": "0:00:01",
        "speed_bytes_sec": "7,680,000",
        "speed_mb_min": "439.453",
    }
    defaults.update(kwargs)
    return RobocopySummary(**defaults)  # type: ignore[arg-type]


def test_format_card_contains_file_counts() -> None:
    card = _make_summary().format_card()
    assert "3 copied" in card
    assert "2 skipped" in card


def test_format_card_contains_dir_counts() -> None:
    card = _make_summary().format_card()
    assert "1 copied" in card


def test_format_card_contains_bytes() -> None:
    card = _make_summary().format_card()
    assert "768" in card
    assert "1.47 k" in card


def test_format_card_contains_speed() -> None:
    card = _make_summary().format_card()
    assert "7,680,000" in card
    assert "439.453" in card


def test_format_card_contains_duration() -> None:
    card = _make_summary().format_card()
    assert "0:00:01" in card


def test_format_card_failed_lowercase_when_zero() -> None:
    """When no files failed, label is lowercase 'failed'."""
    card = _make_summary(files_failed=0).format_card()
    assert "0 failed" in card
    assert "FAILED" not in card


def test_format_card_failed_uppercase_when_nonzero() -> None:
    """When files failed, label is uppercase 'FAILED' for visibility."""
    card = _make_summary(files_failed=2).format_card()
    assert "2 FAILED" in card


def test_format_card_dirs_failed_uppercase_when_nonzero() -> None:
    card = _make_summary(dirs_failed=1).format_card()
    assert "1 FAILED" in card


def test_format_card_omits_bytes_when_none() -> None:
    """Bytes row is absent when bytes_total and bytes_copied are None."""
    card = _make_summary(bytes_total=None, bytes_copied=None).format_card()
    # Check the row label specifically — "Bytes" also appears in "Bytes/sec"
    # on the Speed line, so we look for the padded column label instead.
    assert "  Bytes     " not in card


def test_format_card_omits_speed_when_none() -> None:
    """Speed row is absent when speed_bytes_sec is None."""
    card = _make_summary(speed_bytes_sec=None, speed_mb_min=None).format_card()
    assert "Bytes/sec" not in card


def test_format_card_shows_bytes_only_when_total_missing() -> None:
    """When only bytes_copied is known, show partial bytes info."""
    card = _make_summary(bytes_total=None, bytes_copied="512").format_card()
    assert "512 copied" in card
    assert "of" not in card


def test_format_card_returns_string() -> None:
    assert isinstance(_make_summary().format_card(), str)


def test_format_card_starts_and_ends_with_newline() -> None:
    card = _make_summary().format_card()
    assert card.startswith("\n")
    assert card.endswith("\n")


def test_format_card_omits_files_row_when_files_copied_is_none() -> None:
    """Files row is absent when files_copied is None (branch L160->170)."""
    card = _make_summary(files_copied=None, files_total=None, files_skipped=None, files_failed=None).format_card()
    assert "  Files     " not in card


def test_format_card_speed_without_mb_per_min() -> None:
    """Speed row shows only Bytes/sec when speed_mb_min is None (branch L188->190)."""
    card = _make_summary(speed_mb_min=None).format_card()
    assert "Bytes/sec" in card
    assert "MB/min" not in card
