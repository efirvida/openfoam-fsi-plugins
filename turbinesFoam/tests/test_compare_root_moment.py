# SPDX-License-Identifier: GPL-3.0-or-later
"""compareRootMoment.py through its CLI, on synthetic element histories."""
import csv
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

PHASE = Path(__file__).resolve().parents[1] / "validation/phaseVI"
SCRIPT = PHASE / "scripts/compareRootMoment.py"
sys.path.insert(0, str(PHASE / "scripts"))
import comparePhaseVI as rotor  # noqa: E402

RHO = 1.2
GAUGE = 0.5083
RADII = (1.0, 3.0)
FORCES = (2.0, 4.0)  # kinematic fx per element
EXPECTED = RHO * sum(f * (r - GAUGE) for r, f in zip(RADII, FORCES))
EXP_AERO, EXP_GAUGE = 1500.0, 1400.0


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def window(speed=7, sequence="S"):
    cfg = rotor.load_config(rotor.DEFAULT_CONFIG)
    start, end, period = rotor.window_bounds(cfg, float(speed), sequence)
    return start, end, period


def make_run(root, speed=7, sequence="S", stale=100.0, resume=False, short=False,
             segments=None):
    """Elements with fx = FORCES inside the window and `stale` before it."""
    start, end, period = window(speed, sequence)
    last = end * (0.5 if short else 1.0)
    dt = period / 50
    rows = {i: [] for i in range(len(RADII))}
    turbine = []
    t = dt
    while t <= last + 1e-12:
        for i, (r, f) in enumerate(zip(RADII, FORCES)):
            rows[i].append(dict(
                time=t, root_dist=(r - GAUGE) / (5.029 - GAUGE),
                fx=(stale if t < start else f), fy=0.0, fz=0.0))
        turbine.append(dict(time=t, tsr=1, cp=0, cd=0, ct=0,
                            cd_blade1=0.1, ct_blade1=0))
        t += dt
    base = root / "postProcessing/actuatorLineElements/0"
    for i, history in rows.items():
        write_csv(base / f"turbine.blade1.element{i}.csv", history)
    write_csv(root / "postProcessing/turbines/0/turbine.csv", turbine)
    return root


def make_experiment(path, rows=None):
    rows = rows if rows is not None else [dict(
        file_name="s0700000", sequence="S", wind_speed_m_s=7, yaw_nominal_deg=0,
        pitch_nominal_deg=3, repetition=0, rho_kg_m3=RHO,
        b1rfb_nm=EXP_GAUGE, b3rfb_nm=1390.0, eaerorfb_nm=EXP_AERO)]
    write_csv(path, rows)
    return path


def run_cli(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                          capture_output=True, text=True)


def snapshot(root):
    return {p.relative_to(root): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture
def case(tmp_path):
    run = make_run(tmp_path / "run")
    exp = make_experiment(tmp_path / "exp.csv")
    return tmp_path, run, exp


def table(out):
    with (out / "root_moment_comparison.csv").open() as stream:
        return {row["channel"]: row for row in csv.DictReader(stream)}


def test_moment_arithmetic_and_delta(case):
    tmp, run, exp = case
    out = tmp / "out"
    done = run_cli("--run-dir", run, "--sequence", "S", "--speed", 7,
                   "--experiment", exp, "--out", out)
    assert done.returncode == 0, done.stderr
    rows = table(out)
    aero = rows["eaerorfb_nm"]
    assert float(aero["alm_nm"]) == pytest.approx(EXPECTED, rel=1e-9)
    assert float(aero["experiment_nm"]) == EXP_AERO
    assert float(aero["delta_pct"]) == pytest.approx(100 * (EXPECTED - EXP_AERO) / EXP_AERO)
    assert aero["fair_comparison"] == "yes"
    assert rows["b1rfb_nm"]["fair_comparison"] == "no"
    assert float(rows["b1rfb_nm"]["experiment_nm"]) == EXP_GAUGE
    assert "eaerorfb_nm" in done.stdout and "b1rfb_nm" in done.stdout
    assert "axisymmetric" in done.stdout
    assert (out / "report.txt").is_file()


def test_band_flag_is_informational(tmp_path):
    run = make_run(tmp_path / "run")
    close = make_experiment(tmp_path / "close.csv", [dict(
        file_name="s", sequence="S", wind_speed_m_s=7, yaw_nominal_deg=0,
        pitch_nominal_deg=3, repetition=0, rho_kg_m3=RHO,
        b1rfb_nm=EXPECTED * 1.05, b3rfb_nm=0, eaerorfb_nm=EXPECTED * 1.05)])
    out = tmp_path / "out"
    done = run_cli("--run-dir", run, "--sequence", "S", "--speed", 7,
                   "--experiment", close, "--out", out)
    assert done.returncode == 0
    assert table(out)["eaerorfb_nm"]["within_10pct"] == "yes"
    far = make_experiment(tmp_path / "far.csv", [dict(
        file_name="s", sequence="S", wind_speed_m_s=7, yaw_nominal_deg=0,
        pitch_nominal_deg=3, repetition=0, rho_kg_m3=RHO,
        b1rfb_nm=EXPECTED * 2, b3rfb_nm=0, eaerorfb_nm=EXPECTED * 2)])
    out2 = tmp_path / "out2"
    done = run_cli("--run-dir", run, "--sequence", "S", "--speed", 7,
                   "--experiment", far, "--out", out2)
    assert done.returncode == 0  # a failed band never fails the run
    assert table(out2)["eaerorfb_nm"]["within_10pct"] == "no"


def test_gauge_radius_option_changes_arm(case):
    tmp, run, exp = case
    out = tmp / "out"
    done = run_cli("--run-dir", run, "--sequence", "S", "--speed", 7,
                   "--experiment", exp, "--gauge-radius", 1.0, "--out", out)
    assert done.returncode == 0, done.stderr
    expected = RHO * FORCES[1] * (RADII[1] - 1.0)  # element at r = gauge adds 0
    assert float(table(out)["eaerorfb_nm"]["alm_nm"]) == pytest.approx(expected, rel=1e-9)


def test_rho_override(case):
    tmp, run, exp = case
    out = tmp / "out"
    done = run_cli("--run-dir", run, "--sequence", "S", "--speed", 7,
                   "--experiment", exp, "--rho", 2.4, "--out", out)
    assert done.returncode == 0
    assert float(table(out)["eaerorfb_nm"]["alm_nm"]) == pytest.approx(2 * EXPECTED, rel=1e-9)


def test_revolutions_override_moves_window(case):
    tmp, run, exp = case
    out = tmp / "out"
    # window starting before the stale/real boundary picks up the stale rows
    done = run_cli("--run-dir", run, "--sequence", "S", "--speed", 7,
                   "--experiment", exp, "--revolutions", 0, 3, "--out", out)
    assert done.returncode == 0, done.stderr
    assert float(table(out)["eaerorfb_nm"]["alm_nm"]) > 1.5 * EXPECTED


def test_missing_experiment_row_exits_1(case):
    tmp, run, exp = case
    done = run_cli("--run-dir", run, "--sequence", "S", "--speed", 9,
                   "--experiment", exp)
    assert done.returncode == 1
    assert "no experiment row" in done.stderr
    assert done.stdout == ""


def test_pitch_selects_row_and_ambiguity_fails(tmp_path):
    run = make_run(tmp_path / "run")
    base = dict(file_name="s", sequence="S", wind_speed_m_s=7, yaw_nominal_deg=0,
                repetition=0, rho_kg_m3=RHO, b1rfb_nm=1.0, b3rfb_nm=1.0)
    exp = make_experiment(tmp_path / "e.csv", [
        dict(base, pitch_nominal_deg=3, eaerorfb_nm=1000.0),
        dict(base, pitch_nominal_deg=6, eaerorfb_nm=2000.0)])
    out = tmp_path / "out"
    done = run_cli("--run-dir", run, "--sequence", "S", "--speed", 7,
                   "--experiment", exp, "--pitch", 6, "--out", out)
    assert done.returncode == 0, done.stderr
    assert float(table(out)["eaerorfb_nm"]["experiment_nm"]) == 2000.0
    done = run_cli("--run-dir", run, "--sequence", "S", "--speed", 7, "--experiment", exp)
    assert done.returncode == 1
    assert "--pitch" in done.stderr


def test_repetitions_are_averaged(tmp_path):
    run = make_run(tmp_path / "run")
    base = dict(sequence="S", wind_speed_m_s=7, yaw_nominal_deg=0, pitch_nominal_deg=3,
                rho_kg_m3=RHO, b1rfb_nm=1.0, b3rfb_nm=1.0)
    exp = make_experiment(tmp_path / "e.csv", [
        dict(base, file_name="a", repetition=0, eaerorfb_nm=1000.0),
        dict(base, file_name="b", repetition=1, eaerorfb_nm=1200.0)])
    out = tmp_path / "out"
    done = run_cli("--run-dir", run, "--sequence", "S", "--speed", 7,
                   "--experiment", exp, "--out", out)
    assert done.returncode == 0, done.stderr
    assert float(table(out)["eaerorfb_nm"]["experiment_nm"]) == 1100.0
    assert table(out)["eaerorfb_nm"]["n_experiment_rows"] == "2"


def test_missing_run_and_elements_exit_1(case, tmp_path):
    _, run, exp = case
    done = run_cli("--run-dir", tmp_path / "nope", "--sequence", "S", "--speed", 7,
                   "--experiment", exp)
    assert done.returncode == 1 and "error:" in done.stderr
    empty = tmp_path / "empty"
    empty.mkdir()
    done = run_cli("--run-dir", empty, "--sequence", "S", "--speed", 7, "--experiment", exp)
    assert done.returncode == 1 and "error:" in done.stderr


def test_short_run_exits_2_unless_allowed(tmp_path):
    run = make_run(tmp_path / "short", short=True)
    exp = make_experiment(tmp_path / "e.csv")
    done = run_cli("--run-dir", run, "--sequence", "S", "--speed", 7, "--experiment", exp)
    assert done.returncode == 2
    assert "window" in done.stderr
    done = run_cli("--run-dir", run, "--sequence", "S", "--speed", 7,
                   "--experiment", exp, "--allow-short-window")
    assert done.returncode == 0, done.stderr


def test_resumed_segment_replaces_overlap(tmp_path):
    run = make_run(tmp_path / "run")
    start, end, period = window()
    base = run / "postProcessing/actuatorLineElements"
    seg = end * 0.9
    for i, (r, f) in enumerate(zip(RADII, FORCES)):
        history = []
        t = seg
        while t <= end + 1e-12:
            history.append(dict(time=t, root_dist=(r - GAUGE) / (5.029 - GAUGE),
                                fx=2 * f, fy=0, fz=0))
            t += period / 50
        write_csv(base / str(seg) / f"turbine.blade1.element{i}.csv", history)
    exp = make_experiment(tmp_path / "e.csv")
    out = tmp_path / "out"
    done = run_cli("--run-dir", run, "--sequence", "S", "--speed", 7,
                   "--experiment", exp, "--out", out)
    assert done.returncode == 0, done.stderr
    got = float(table(out)["eaerorfb_nm"]["alm_nm"])
    assert EXPECTED < got < 2 * EXPECTED  # last 10 % of the window doubled


def test_run_dir_is_not_mutated(case):
    tmp, run, exp = case
    before = snapshot(run)
    done = run_cli("--run-dir", run, "--sequence", "S", "--speed", 7,
                   "--experiment", exp, "--out", tmp / "out")
    assert done.returncode == 0
    assert snapshot(run) == before


def test_thrust_closure_reported_when_turbine_csv_has_blade_cd(case):
    tmp, run, exp = case
    done = run_cli("--run-dir", run, "--sequence", "S", "--speed", 7, "--experiment", exp)
    assert done.returncode == 0
    assert "thrust closure" in done.stdout


def test_committed_table_resolves_real_rows():
    cmp = __import__("compareRootMoment")
    for seq, speed in (("S", 5), ("S", 6), ("S", 7), ("S", 8), ("H", 7)):
        row, count = cmp.load_reference(cmp.DEFAULT_EXPERIMENT, seq, speed, 0.0, None)
        assert count >= 1
        assert float(row["eaerorfb_nm"]) > 0 and float(row["b1rfb_nm"]) > 0
