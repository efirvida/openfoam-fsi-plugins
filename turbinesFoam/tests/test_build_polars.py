# SPDX-License-Identifier: GPL-3.0-or-later
"""The DUT Re 1e6 polar (TP-500-29955 Table A-8) for the P4 diagnostic arm.

The DUT table is built by the same code path as the OSU total table, so inside
the measured DUT range the only difference between the two files is the source
data; outside it both carry the documented CSU Table A-3 static extension.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

PHASEVI = Path(__file__).resolve().parents[1] / "validation" / "phaseVI"
POLARS = PHASEVI / "data" / "polars"
DUT = POLARS / "S809_DUT_Re1M_total.dat"
OSU = POLARS / "S809_OSU_Re1M_total.dat"
ROW = re.compile(r"^\(\s*(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*\)$")


def read_polar(path: Path) -> list[tuple[float, float, float, float]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("//"):
            continue
        match = ROW.match(line)
        assert match, f"{path.name}: unparsable row {line!r}"
        rows.append(tuple(float(value) for value in match.groups()))
    return rows


def a8_rows() -> list[tuple[float, float, float, float]]:
    with (POLARS / "raw" / "table_A8.csv").open(encoding="utf-8") as stream:
        return [
            (float(r["alpha_deg"]), float(r["cl"]), float(r["cdw"]), float(r["cm"]))
            for r in csv.DictReader(stream)
        ]


def test_polar_dut_table_exists() -> None:
    assert DUT.is_file()


def test_polar_dut_carries_every_a8_row_verbatim() -> None:
    rows = read_polar(DUT)
    for expected in a8_rows():
        assert expected in rows


def test_polar_dut_grid_covers_full_circle_like_osu() -> None:
    alphas = [row[0] for row in read_polar(DUT)]
    assert alphas == sorted(alphas)
    assert alphas[0] == -180.0 and alphas[-1] == 180.0
    assert {a for a in (-180.0, -150.0, -120.0, 120.0, 150.0, 180.0)} <= set(alphas)


def test_polar_dut_outside_range_equals_osu_extension() -> None:
    low = min(row[0] for row in a8_rows())
    high = max(row[0] for row in a8_rows())
    dut = read_polar(DUT)
    osu = read_polar(OSU)
    # OSU measured range is -20.1..26.1; beyond it both files carry the identical
    # CSU A-3 extension (mirrored for negative alpha) and the flat-plate closure
    assert [r for r in dut if r[0] > 26.1] == [r for r in osu if r[0] > 26.1]
    assert [r for r in dut if r[0] < -20.1] == [r for r in osu if r[0] < -20.1]
    # DUT fills alpha < -1.04 with mirrored CSU A-3 rows (no DUT row there)
    below = [r for r in dut if r[0] < low]
    assert below and all(r not in a8_rows() for r in below)
    assert [r for r in dut if low <= r[0] <= high] == a8_rows()


def test_polar_dut_is_current_with_builder() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(PHASEVI / "scripts" / "buildPolars.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
