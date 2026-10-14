# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract for `compareElementStates.py` on synthetic element CSVs."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR.parent / "validation" / "phaseVI" / "scripts"))

import compareElementStates as states  # noqa: E402


def write_run(root: Path, cl: float) -> Path:
    directory = root / states.ELEMENT_DIR
    directory.mkdir(parents=True)
    for index in (0, 1):
        with (directory / f"turbine.blade1.element{index}.csv").open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["time", "root_dist", "cl"])
            for time, value in ((0.5, 99.0), (2.0, cl), (3.0, cl + 0.2)):
                writer.writerow([time, 0.1 * index, value])
    return root


def test_average_uses_only_rows_after_the_window_start(tmp_path):
    run = write_run(tmp_path / "a", cl=0.6)
    result = states.average_elements(run, 1.0, ("cl",))
    assert sorted(result) == [0, 1]
    assert result[1]["cl"] == pytest.approx(0.7)
    assert result[1]["root_dist"] == pytest.approx(0.1)


def test_main_reports_the_ratio_to_the_first_run(tmp_path, capsys):
    first = write_run(tmp_path / "a", cl=0.6)
    second = write_run(tmp_path / "b", cl=0.9)
    rc = states.main([str(first), str(second), "--speed", "7",
                      "--discard-revolutions", "1.0", "--columns", "cl"])
    assert rc == 0
    assert "1.429" in capsys.readouterr().out  # (0.9 + 0.1) / (0.6 + 0.1)


def test_main_fails_when_a_run_has_no_element_rows(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert states.main(["--speed", "7", str(empty)]) == 1
