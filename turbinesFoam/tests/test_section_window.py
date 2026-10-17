# SPDX-License-Identifier: GPL-3.0-or-later
"""Station comparisons share the rotor window and reject turbine drift."""

import csv
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "validation" / "phaseVI" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import comparePhaseVI
import compareSectionLoads


def turbine_file(tmp_path, sequence="H", drift=None):
    cfg = comparePhaseVI.load_config(comparePhaseVI.DEFAULT_CONFIG)
    start, end, period = comparePhaseVI.window_bounds(cfg, 7.0, sequence)
    tsr = float(comparePhaseVI.select_speed(cfg, 7.0, sequence)["tsr"])
    path = tmp_path / comparePhaseVI.TURBINE_CSV
    path.parent.mkdir(parents=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("time", "tsr", "cp", "cd", "ct"))
        writer.writeheader()
        for step in range(1201):
            rev = step / 100
            cp = 0.3 + (0.01 * rev if drift == "cp" else 0.0)
            cd = 0.8 + (0.02 * rev if drift == "cd" else 0.0)
            writer.writerow(dict(time=rev * period, tsr=tsr, cp=cp, cd=cd, ct=cp / tsr))
    return start, end, period, path


@pytest.mark.parametrize("sequence", ["H", "S"])
def test_window_matches_rotor_and_steady_file_passes(tmp_path, capsys, sequence):
    start, end, period, path = turbine_file(tmp_path, sequence)
    before = path.read_bytes()
    lo, hi, info = compareSectionLoads.converged_window(tmp_path, 7.0, sequence)
    assert (lo, hi) == (start, end)
    assert info["discard_revolutions"] == start / period
    assert info["end_revolutions"] == end / period
    assert info["drift"]["flag"] is False
    assert path.read_bytes() == before
    assert capsys.readouterr() == ("", "")


def test_revolutions_override_matches_rotor_integer_semantics(tmp_path):
    _, _, period, _ = turbine_file(tmp_path)
    lo, hi, info = compareSectionLoads.converged_window(tmp_path, 7.0, "H", (5.9, 10.9))
    assert (lo, hi) == (5 * period, 10 * period)
    assert (info["discard_revolutions"], info["end_revolutions"]) == (5, 10)


@pytest.mark.parametrize("quantity", ["cp", "cd"])
def test_drift_refused_or_explicitly_warned(tmp_path, capsys, quantity):
    start, end, _, path = turbine_file(tmp_path, drift=quantity)
    before = path.read_bytes()
    with pytest.raises(SystemExit) as exc:
        compareSectionLoads.converged_window(tmp_path, 7.0, "H")
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "drift flag: True" in captured.err
    assert f"{quantity} variation" in captured.err
    assert "--allow-drift" in captured.err
    assert path.read_bytes() == before
    lo, hi, info = compareSectionLoads.converged_window(tmp_path, 7.0, "H", allow_drift=True)
    assert (lo, hi) == (start, end)
    assert info["drift"][quantity]["flag"] is True
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("WARNING:")
    assert "drift flag: True" in captured.err
    assert path.read_bytes() == before


def test_drift_outside_override_window_is_not_counted(tmp_path):
    _, _, period, path = turbine_file(tmp_path)
    with path.open("a") as stream:
        stream.write(f"{13 * period},5.408,4,0.8,0.1\n")
    _, _, info = compareSectionLoads.converged_window(tmp_path, 7.0, "H", (4, 10))
    assert info["drift"]["flag"] is False
