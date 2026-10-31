# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the ``--bands`` option of ``compare_spanwise.py``.

The two-run band table used three hard-coded bands plus the pooled 0.3-0.9, so
the IEA 15 MW tip region (r/R > 0.9) could not be compared.  ``--bands`` lets
the caller choose the bands; these tests pin that the given bands are the rows
in the given order, that the pooled row spans them, that malformed input is a
clean argparse error, that empty bands stay ``absent``/``n/a``, and that the CSV
carries the printed rows.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

import pytest

from test_compare_spanwise import (  # noqa: F401  (fixtures and helpers)
    REFERENCE_ROWS_A,
    REFERENCE_ROWS_B,
    TOOL,
    _make_run,
    _profile,
    _two_source_store,
    compare_spanwise,
)

TIP_ROWS_A = [
    (0.75, 5.0, 1.0, 0.5), (0.85, 6.0, 2.0, 0.6),
    (0.92, 7.0, 3.0, 0.7), (0.97, 8.0, 4.0, 0.8),
]
TIP_ROWS_B = [
    (0.75, 6.0, 1.1, 0.6), (0.85, 8.0, 2.1, 0.7),
    (0.92, 9.0, 3.3, 0.9), (0.97, 10.0, 4.4, 1.0),
]


def test_parse_bands_keeps_the_given_order() -> None:
    assert compare_spanwise.parse_bands("0.9-0.95,0.7-0.8, 0.95-1.0") == (
        (0.9, 0.95), (0.7, 0.8), (0.95, 1.0),
    )


@pytest.mark.parametrize("text", [
    "", "0.7", "0.7-", "-0.8", "a-b", "0.8-0.7", "0.8-0.8", "0.7-1.1",
    "-0.1-0.5", "0.7-0.8,,0.9-1.0", "0.7-0.8,", "0.1-0.2-0.3",
])
def test_parse_bands_rejects_malformed_input(text: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        compare_spanwise.parse_bands(text)


def test_compare_profiles_rows_are_the_given_bands_then_the_pooled_span() -> None:
    bands = ((0.9, 0.95), (0.7, 0.8), (0.95, 1.0))
    results = compare_spanwise.compare_profiles(
        _profile(TIP_ROWS_A), "runA", _profile(TIP_ROWS_B), "runB", bands=bands
    )

    assert [item["band"] for item in results] == [
        (0.9, 0.95), (0.7, 0.8), (0.95, 1.0), (0.7, 1.0)
    ]
    assert [item["stations"] for item in results] == [1, 1, 1, 4]
    tip = results[0]
    assert tip["alpha_a"] == pytest.approx(7.0)
    assert tip["c_n_ratio"] == pytest.approx(1.1)
    pooled = results[3]
    assert pooled["alpha_a"] == pytest.approx((5.0 + 6.0 + 7.0 + 8.0) / 4)


def test_default_bands_are_unchanged() -> None:
    results = compare_spanwise.compare_profiles(
        _profile(REFERENCE_ROWS_A), "runA", _profile(REFERENCE_ROWS_B), "runB"
    )

    assert [item["band"] for item in results] == [
        (0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.3, 0.9)
    ]


def _run(tmp_path: Path, *extra: str):
    store = _two_source_store(tmp_path / "refs.csv")
    run_a = _make_run(tmp_path / "run-a", TIP_ROWS_A)
    run_b = _make_run(tmp_path / "run-b", TIP_ROWS_B)
    return subprocess.run(
        [
            sys.executable, str(TOOL),
            "--run-dir", str(run_a), "--time", "0", "--revs", "0",
            "--compare-with", str(run_b), "--compare-time", "0",
            "--references", "--reference-store", str(store),
            "--reference-source", "srcA", "--reference-source", "srcB",
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_bands_set_the_printed_rows_and_the_csv(tmp_path: Path) -> None:
    out = tmp_path / "comparison.csv"
    result = _run(
        tmp_path, "--bands", "0.9-0.95,0.95-1.0,0.7-0.8",
        "--comparison-out", str(out),
    )

    assert result.returncode == 0, result.stderr
    lines = [line.strip() for line in result.stdout.splitlines()]
    start = next(i for i, line in enumerate(lines) if line.startswith("band,"))
    rows = [line.split(",")[0] for line in lines[start + 1:start + 5]]
    assert rows == ["0.9-0.95", "0.95-1", "0.7-0.8", "0.7-1"]
    # No station of the (0.3-0.9 fixture) store reaches r/R > 0.9 -> n/a, no crash.
    tip = lines[start + 1].split(",")
    assert tip[1] == "1"
    assert tip[7] == "0" and tip[8:12] == ["n/a"] * 4

    with out.open(encoding="utf-8", newline="") as stream:
        table = list(csv.DictReader(stream))
    assert [(r["band_lo"], r["band_hi"]) for r in table] == [
        ("0.9", "0.95"), ("0.95", "1"), ("0.7", "0.8"), ("0.7", "1"),
    ]
    assert [r["srcA_n"] for r in table] == ["0", "0", "0", "1"]
    assert [r["stations"] for r in table] == ["1", "1", "1", "4"]


def test_cli_band_without_stations_prints_absent(tmp_path: Path) -> None:
    result = _run(tmp_path, "--bands", "0.0-0.1,0.9-0.95")

    assert result.returncode == 0, result.stderr
    assert "  0-0.1,0,absent,absent,absent,absent,absent," in result.stdout


@pytest.mark.parametrize("value", ["0.8-0.7", "abc", "0.5-1.5", "0.7"])
def test_cli_malformed_bands_is_an_argparse_error(
    tmp_path: Path, value: str
) -> None:
    result = _run(tmp_path, "--bands", value)

    assert result.returncode == 2
    assert "--bands" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_explicit_default_bands_print_the_default_table(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    default = _run(first)
    explicit = _run(second, "--bands", "0.3-0.5,0.5-0.7,0.7-0.9")

    assert default.returncode == 0, default.stderr
    assert explicit.returncode == 0, explicit.stderr
    assert default.stdout.replace(str(first), "X") == explicit.stdout.replace(
        str(second), "X"
    )
