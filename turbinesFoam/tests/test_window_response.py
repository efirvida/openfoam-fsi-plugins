# SPDX-License-Identifier: GPL-3.0-or-later
"""window_response.py averages cp/cd/ct in azimuth windows of the run's own columns."""

import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "validation" / "tools" / "window_response.py"
_spec = importlib.util.spec_from_file_location("window_response", _PATH)
window_response = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(window_response)


def _row(angle, cp, cd=0.0, ct=0.0):
    return {"angle_deg": angle, "cp": cp, "cd": cd, "ct": ct}


def test_rows_are_averaged_per_window():
    rows = [_row(0.5, 1.0), _row(1.5, 3.0), _row(10.5, 5.0)]
    got = window_response.window_means(rows, 10.0, 0.0, 20.0)
    assert got[0]["cp"] == pytest.approx(2.0)
    assert got[1]["cp"] == pytest.approx(5.0)


def test_rows_outside_the_range_are_ignored():
    rows = [_row(-1.0, 9.0), _row(5.0, 1.0), _row(20.0, 9.0)]
    got = window_response.window_means(rows, 10.0, 0.0, 20.0)
    assert list(got) == [0]
    assert got[0]["cp"] == pytest.approx(1.0)


def test_main_reads_a_run_dir(tmp_path, capsys):
    run = tmp_path / "run" / "postProcessing" / "turbines" / "0"
    run.mkdir(parents=True)
    columns = "time,angle_deg,tsr,cp,cd,ct,cd_blade1,ct_blade1,cd_blade2,ct_blade2,cd_blade3,ct_blade3"
    values = "1,5,8,0.5,0.8,0.06,0,0,0,0,0,0"
    (run / "turbine.csv").write_text(columns + "\n" + values + "\n")
    assert window_response.main(
        [str(tmp_path / "run"), "--from-deg", "0", "--to-deg", "10", "--window-deg", "10"]
    ) == 0
    assert "0.500000" in capsys.readouterr().out


def test_missing_history_returns_one(tmp_path):
    assert window_response.main([str(tmp_path), "--from-deg", "0", "--to-deg", "1"]) == 1
