# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only ladder comparison through its public CLI."""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "validation/phaseVI/scripts"
sys.path.insert(0, str(SCRIPTS))
import comparePhaseVI
import compareSectionLoads


def comparison(tmp_path, name, factor=1.0, speed=7.0, sequence="H"):
    directory = tmp_path / name
    run = directory / "run"
    cfg = comparePhaseVI.load_config(comparePhaseVI.DEFAULT_CONFIG)
    _, _, period = comparePhaseVI.window_bounds(cfg, 7.0, "H")
    tsr = comparePhaseVI.select_speed(cfg, 7.0, "H")["tsr"]
    turbine = run / comparePhaseVI.TURBINE_CSV
    turbine.parent.mkdir(parents=True)
    with turbine.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["time", "tsr", "cp", "cd", "ct"])
        for step in range(1201):
            writer.writerow([step / 100 * period, tsr, .3, .8, .3 / float(tsr)])
    elements = run / "postProcessing/actuatorLineElements/0"
    elements.mkdir(parents=True)
    # Linear force profile brackets every requested station, testing interpolation.
    for i, station in enumerate((.40, .70, .99)):
        root = (station * compareSectionLoads.R - compareSectionLoads.CUT) / (
            compareSectionLoads.R - compareSectionLoads.CUT)
        with (elements / f"turbine.blade1.element{i}.csv").open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["time", "root_dist", "cl", "cd", "c_ref_n", "c_ref_t",
                             "alpha_deg", "f_ref_n", "f_ref_t"])
            for rev in range(13):
                # Window is deliberately not the default 4..12.
                force = station * 100 * factor if 5 <= rev <= 10 else 99999
                writer.writerow([rev * period, root, 1, 0, 1, 0, 0, force, 1])
    payload = {
        "case": {"speed_m_s": speed, "sequence": sequence, "thrust_scope": "blade"},
        "window": {"discard_revolutions": 5, "end_revolutions": 10},
        "models": {"alm": {"run_dir": str(run), "metrics": {
            "power_kw": 10 * factor, "thrust_n": 100 * factor,
            "thrust_rotor_n": 99999, "thrust_scope": "blade"}}},
    }
    (directory / "metrics.json").write_text(json.dumps(payload))
    return directory


def snapshot(directory):
    return {str(p.relative_to(directory)): p.read_bytes()
            for p in directory.rglob("*") if p.is_file()}


def invoke(reference, *runs, tolerance=2.0):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "compareLadder.py"), "--reference", str(reference),
         "--runs", *map(str, runs), "--tolerance", str(tolerance)],
        cwd=SCRIPTS.parent, text=True, capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


def test_pass_multiple_runs_values_window_and_read_only(tmp_path):
    reference = comparison(tmp_path, "ref")
    runs = [comparison(tmp_path, "fine", 1.01), comparison(tmp_path, "dt", .99)]
    before = snapshot(tmp_path)
    result = invoke(reference, *runs)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "thrust_n; scope blade" in result.stdout
    assert "|change| < 2%" in result.stdout
    rows = [line.split(" | ") for line in result.stdout.splitlines() if " | " in line]
    assert rows[0] == ["quantity", "reference ref/alm", "fine/alm value", "change %", "dt/alm value", "change %"]
    rho = compareSectionLoads.read_density(SCRIPTS.parent / "data/experiment", 7.0, "H")
    expected = [10, 100, *(rho * station * 100 for station in (.47, .63, .80, .95))]
    for row, value in zip(rows[1:7], expected, strict=True):
        assert float(row[1]) == pytest.approx(value, rel=1e-6)
        assert float(row[2]) == pytest.approx(value * 1.01, rel=1e-6)
        assert row[3] == "+1.000000"
        assert float(row[4]) == pytest.approx(value * .99, rel=1e-6)
        assert row[5] == "-1.000000"
    assert rows[7] == ["verdict", "-", "PASS", "-", "PASS", "-"]
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("factor,tolerance", [(1.03, 2), (1.02, 2), (.97, 2), (1.01, .5)])
def test_fail_and_strict_tolerance(tmp_path, factor, tolerance):
    reference = comparison(tmp_path, "ref")
    run = comparison(tmp_path, "fine", factor)
    before = snapshot(tmp_path)
    result = invoke(reference, run, tolerance=tolerance)
    assert result.returncode == 1
    assert result.stderr == ""
    assert "verdict | - | FAIL | -" in result.stdout
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("field,value", [("speed", 8.0), ("sequence", "S")])
def test_mismatched_case_refused(tmp_path, field, value):
    reference = comparison(tmp_path, "ref")
    run = comparison(tmp_path, "fine", **{field: value})
    before = snapshot(tmp_path)
    result = invoke(reference, run)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "mismatched speed/sequence" in result.stderr
    assert snapshot(tmp_path) == before


def test_missing_metrics(tmp_path):
    reference = comparison(tmp_path, "ref")
    before = snapshot(tmp_path)
    result = invoke(reference, tmp_path / "missing")
    assert result.returncode == 2
    assert result.stdout == ""
    assert "missing metrics.json" in result.stderr
    assert snapshot(tmp_path) == before
