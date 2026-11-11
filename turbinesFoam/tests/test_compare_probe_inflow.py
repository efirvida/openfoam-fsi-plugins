# SPDX-License-Identifier: GPL-3.0-or-later
"""compareProbeInflow: probe local flow angle vs ALM alpha_deg, via the CLI."""

import csv
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "validation" / "phaseVI" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import comparePhaseVI
import compareProbeInflow

STATIONS = (0.34, 0.51, 0.67, 0.84, 0.91)
ROOT_DISTS = [i / 10 for i in range(11)]


def r_of(root_dist):
    return comparePhaseVI.r_over_r_from_root_dist(root_dist, compareProbeInflow.RADIUS)


def alpha_of(rr):
    return 20.0 - 10.0 * rr


def build_run(tmp_path, resumed=False, with_phi=True):
    cfg = comparePhaseVI.load_config(comparePhaseVI.DEFAULT_CONFIG)
    start, end, period = comparePhaseVI.window_bounds(cfg, 7.0, "H")
    tsr = float(comparePhaseVI.select_speed(cfg, 7.0, "H")["tsr"])
    run = tmp_path / "run"
    turbine = run / comparePhaseVI.TURBINE_CSV
    turbine.parent.mkdir(parents=True)
    with turbine.open("w", newline="") as stream:
        w = csv.writer(stream)
        w.writerow(("time", "tsr", "cp", "cd", "ct"))
        for step in range(1201):
            w.writerow((step / 100 * period, tsr, 0.3, 0.8, 0.3 / tsr))
    edir = run / comparePhaseVI.ELEMENT_DIR
    edir.mkdir(parents=True)
    times = [step / 100 * period for step in range(1201)]
    for blade in (1, 2):
        for i, rd in enumerate(ROOT_DISTS):
            cols = ["time", "root_dist", "alpha_deg", "alpha_geom_deg"]
            if with_phi:
                cols.append("inflow_ref_angle_deg")
            with (edir / f"turbine.blade{blade}.element{i}.csv").open("w", newline="") as s:
                w = csv.writer(s)
                w.writerow(cols)
                for t in times:
                    row = [t, rd, alpha_of(r_of(rd)), alpha_of(r_of(rd)) + 2.0]
                    if with_phi:
                        row.append(30.0)
                    w.writerow(row)
    if resumed:
        seg = run / "postProcessing" / "actuatorLineElements" / "5"
        seg.mkdir()
        late = [t for t in times if t >= 8 * period]
        for blade in (1, 2):
            for i, rd in enumerate(ROOT_DISTS):
                with (seg / f"turbine.blade{blade}.element{i}.csv").open("w", newline="") as s:
                    w = csv.writer(s)
                    w.writerow(("time", "root_dist", "alpha_deg", "alpha_geom_deg",
                                "inflow_ref_angle_deg"))
                    for t in late:
                        w.writerow((t, rd, alpha_of(r_of(rd)) + 10.0, 0.0, 30.0))
    return run


def build_experiment(tmp_path, speed=7):
    exp = tmp_path / "exp"
    exp.mkdir()
    with (exp / "sequence_H_probes.csv").open("w", newline="") as s:
        w = csv.writer(s)
        w.writerow(("file_name", "sequence", "wind_speed_m_s", "r_over_R",
                    "local_flow_angle_deg", "spanwise_flow_angle_deg"))
        for st in STATIONS:
            w.writerow(("h0700000", "H", speed, st, alpha_of(st) + 1.5, 9.0))
        w.writerow(("h0800000", "H", 8, 0.34, 99.0, 9.0))
    return exp


def run_cli(tmp_path, run, exp, *extra):
    return compareProbeInflow.main(["--alm-dir", str(run), "--experiment-dir", str(exp),
                                    "--speed", "7", *extra])


def snapshot(path):
    return {p: p.read_bytes() for p in sorted(path.rglob("*")) if p.is_file()}


def test_table_delta_csv_report_and_caveats(tmp_path, capsys):
    run, exp = build_run(tmp_path), build_experiment(tmp_path)
    before = snapshot(run)
    out_csv, out_md = tmp_path / "o.csv", tmp_path / "o.md"
    assert run_cli(tmp_path, run, exp, "--csv", str(out_csv), "--report", str(out_md)) == 0
    text = capsys.readouterr().out
    assert "upwash" in text and "NOT corrected" in text
    assert "alpha_deg" in text and "99.0" not in text  # 8 m/s row ignored
    rows = list(csv.DictReader(out_csv.open()))
    assert [float(r["r_over_R"]) for r in rows] == list(STATIONS)
    for r in rows:
        assert float(r["alm_alpha_deg"]) == pytest.approx(alpha_of(float(r["r_over_R"])), abs=1e-3)
        assert float(r["delta_deg"]) == pytest.approx(-1.5, abs=1e-3)
        assert float(r["exp_local_flow_angle_deg"]) == pytest.approx(
            alpha_of(float(r["r_over_R"])) + 1.5, abs=1e-3)
        assert float(r["alm_alpha_geom_deg"]) == pytest.approx(
            alpha_of(float(r["r_over_R"])) + 2.0, abs=1e-3)
        assert float(r["alm_inflow_ref_angle_deg"]) == pytest.approx(30.0)
    assert "upwash" in out_md.read_text()
    assert snapshot(run) == before  # read-only


def test_absent_phi_column_is_reported_absent(tmp_path, capsys):
    run, exp = build_run(tmp_path, with_phi=False), build_experiment(tmp_path)
    out_csv = tmp_path / "o.csv"
    assert run_cli(tmp_path, run, exp, "--csv", str(out_csv)) == 0
    rows = list(csv.DictReader(out_csv.open()))
    assert all(r["alm_inflow_ref_angle_deg"] == "" for r in rows)
    assert "n/a" in capsys.readouterr().out


def test_resumed_segment_replaces_overlap(tmp_path):
    run, exp = build_run(tmp_path, resumed=True), build_experiment(tmp_path)
    out_csv = tmp_path / "o.csv"
    assert run_cli(tmp_path, run, exp, "--csv", str(out_csv)) == 0
    delta = float(list(csv.DictReader(out_csv.open()))[0]["delta_deg"])
    # window is 4..12 rev; rows from rev 8 on carry +10 deg: mean offset = 10 * 4/8
    assert delta == pytest.approx(-1.5 + 5.0, abs=0.1)


def test_revolutions_override_selects_the_window(tmp_path):
    run, exp = build_run(tmp_path, resumed=True), build_experiment(tmp_path)
    out_csv = tmp_path / "o.csv"
    assert run_cli(tmp_path, run, exp, "--revolutions", "7", "12", "--csv", str(out_csv)) == 0
    delta = float(list(csv.DictReader(out_csv.open()))[0]["delta_deg"])
    assert delta == pytest.approx(-1.5 + 8.0, abs=0.1)  # 10 deg over the last 4 of 5 revolutions


def test_missing_speed_and_missing_inputs_have_distinct_exit_codes(tmp_path, capsys):
    run, exp = build_run(tmp_path), build_experiment(tmp_path)
    (tmp_path / "o").mkdir()
    other = build_experiment(tmp_path / "o", speed=8)
    assert run_cli(tmp_path, run, other) == 2  # no 7 m/s probe rows
    assert "no probe rows" in capsys.readouterr().err
    assert run_cli(tmp_path, run, tmp_path / "nowhere") == 3
    assert run_cli(tmp_path, tmp_path / "norun", exp) == 3


def test_cli_subprocess_prints_table(tmp_path):
    run, exp = build_run(tmp_path), build_experiment(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "compareProbeInflow.py"), "--alm-dir", str(run),
         "--experiment-dir", str(exp), "--speed", "7"],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "0.34" in proc.stdout and "Caveats" in proc.stdout
