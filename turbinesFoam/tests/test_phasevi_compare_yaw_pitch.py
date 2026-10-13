"""Tests for compareYawPitch.py (synthetic run + synthetic/committed tables)."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PACKAGE = TESTS_DIR.parent / "validation" / "phaseVI"
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(PACKAGE / "scripts"))

from test_phasevi_compare import SPEED, TSR, write_run  # noqa: E402


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


cyp = _load_module(PACKAGE / "scripts" / "compareYawPitch.py", "compareYawPitch")

COMMITTED = PACKAGE / "data" / "experiment" / "yaw-pitch"
PERF = ("file_name,sequence,wind_speed_m_s,yaw_token,yaw_deg,repetition,rpm,"
        "tsr,rotpow_kw,lsstqcor_nm,eaeroth_n,wtbaro_pa,wtatemp_degc,"
        "rho_kg_m3,eaerotq_n,yaw_nominal_deg,pitch_nominal_deg,b1pitch_deg,"
        "b3pitch_deg,b1rfb_nm,b3rfb_nm,eaerorfb_nm").split(",")
SPAN = ("file_name,sequence,wind_speed_m_s,r_over_R,cn,ct,cm,cth,ctq,qnorm_pa,"
        "yaw_nominal_deg,pitch_nominal_deg,repetition").split(",")


def perf_row(name, seq, yaw, pitch, rep, power):
    return {
        **dict.fromkeys(PERF, "0"),
        "file_name": name, "sequence": seq, "wind_speed_m_s": "7",
        "yaw_deg": str(yaw), "repetition": str(rep), "tsr": str(TSR),
        "rotpow_kw": str(power), "lsstqcor_nm": "100", "eaeroth_n": "1000",
        "wtbaro_pa": "101000", "wtatemp_degc": "15", "rho_kg_m3": "1.2",
        "yaw_nominal_deg": str(yaw), "pitch_nominal_deg": str(pitch),
        "b3pitch_deg": str(pitch),
    }


def write_table(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def make_experiment(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    yaw = [
        perf_row("h07m0000", "H", 0, 3, 1, 5.0),
        perf_row("h070000a", "H", 0, 3, 0, 6.0),
        perf_row("h070000b", "H", 0, 3, 0, 7.0),
        perf_row("h070300", "H", 30, 3, 0, 8.0),
    ]
    pitch = [perf_row("j0700000", "J", 0, 6, 0, 9.0),
             perf_row("h0700000", "H", 0, 3, 0, 6.0)]
    for stem, rows in (("yaw_H", yaw), ("pitch", pitch)):
        write_table(root / f"{stem}_performance.csv", PERF, rows)
        span = []
        for row in rows:
            for station in cyp.STATIONS:
                span.append({
                    "file_name": row["file_name"], "sequence": row["sequence"],
                    "wind_speed_m_s": "7", "r_over_R": str(station),
                    "cn": "0.5", "ct": "0.1", "cm": "0",
                    "yaw_nominal_deg": row["yaw_nominal_deg"],
                    "pitch_nominal_deg": row["pitch_nominal_deg"],
                    "repetition": row["repetition"],
                })
        write_table(root / f"{stem}_spanwise.csv", SPAN, span)
    return root


def write_fv_options(run: Path, axis, wind):
    path = run / "system" / "fvOptions"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"axis ({axis[0]} {axis[1]} {axis[2]});\n"
        f"freeStreamVelocity ({wind[0]} {wind[1]} {wind[2]});\n",
        encoding="utf-8")


def run_main(tmp_path, run, *extra):
    out = tmp_path / "out"
    rc = cyp.main(["--run-dir", str(run), "--speed", "7", "--out", str(out),
                   "--experiment", str(tmp_path / "exp"),
                   "--allow-short-window", "--revolutions", "0", "1", *extra])
    return rc, out


@pytest.fixture
def exp(tmp_path):
    return make_experiment(tmp_path / "exp")


def test_yaw_zero_ok_and_reference_values(tmp_path, exp):
    run = write_run(tmp_path / "run")
    write_fv_options(run, (-1, 0, 0), (7, 0, 0))
    rc, out = run_main(tmp_path, run, "--yaw", "0")
    assert rc == cyp.EXIT_OK
    rows = list(csv.DictReader((out / "turbine_comparison.csv").open()))
    power = next(r for r in rows if r["quantity"] == "power")
    assert float(power["experiment"]) == 6.0  # rep 0, file_name h070000a
    metrics = json.loads((out / "metrics.json").read_text())
    assert metrics["reference"]["file_name"] == "h070000a"
    assert metrics["run_audit"]["run_yaw_magnitude_deg"] == pytest.approx(0.0)
    assert metrics["run_audit"]["run_pitch_audited"] is False
    assert "root_flap_experiment_only" in metrics["reference"]


def test_yaw_mismatch_exit(tmp_path, exp):
    run = write_run(tmp_path / "run")
    write_fv_options(run, (-1, 0, 0), (7, 0, 0))
    rc, _ = run_main(tmp_path, run, "--yaw", "30")
    assert rc == cyp.EXIT_YAW_MISMATCH


@pytest.mark.parametrize("requested", ["30", "-30"])
def test_rotated_wind_matches_yaw_magnitude(tmp_path, exp, requested):
    import math
    run = write_run(tmp_path / "run")
    angle = math.radians(30)
    write_fv_options(run, (-1, 0, 0), (7 * math.cos(angle), 7 * math.sin(angle), 0))
    row = perf_row("h07m0300", "H", -30, 3, 0, 4.0)
    if requested == "-30":
        rows = list(csv.DictReader((tmp_path / "exp/yaw_H_performance.csv").open()))
        write_table(tmp_path / "exp/yaw_H_performance.csv", PERF, rows + [row])
        spans = list(csv.DictReader((tmp_path / "exp/yaw_H_spanwise.csv").open()))
        spans += [{**spans[0], "file_name": "h07m0300", "r_over_R": str(s),
                   "yaw_nominal_deg": "-30"} for s in cyp.STATIONS]
        write_table(tmp_path / "exp/yaw_H_spanwise.csv", SPAN, spans)
    rc, _ = run_main(tmp_path, run, "--yaw", requested)
    assert rc == cyp.EXIT_OK


def test_pitch_six_uses_sequence_j_with_config_h(tmp_path, exp):
    run = write_run(tmp_path / "run")
    rc, out = run_main(tmp_path, run, "--pitch", "6")
    assert rc == cyp.EXIT_OK
    metrics = json.loads((out / "metrics.json").read_text())
    assert metrics["case"]["sequence"] == "J"
    assert metrics["case"]["config_sequence"] == "H"
    assert metrics["reference"]["file_name"] == "j0700000"
    assert metrics["run_audit"]["fvOptions_found"] is False


def test_pitch_unavailable_names_available(tmp_path, exp, capsys):
    run = write_run(tmp_path / "run")
    rc, _ = run_main(tmp_path, run, "--pitch", "5")
    assert rc == cyp.EXIT_MISSING_INPUT
    err = capsys.readouterr().err
    assert "available pitch values" in err and "6 (J)" in err


def test_inconsistent_pitch_sequence_rejected(tmp_path, exp):
    run = write_run(tmp_path / "run")
    rc, _ = run_main(tmp_path, run, "--pitch", "6", "--sequence", "H")
    assert rc == cyp.EXIT_MISSING_INPUT


def test_yaw_tie_break(tmp_path, exp):
    row, stations = cyp.load_reference(tmp_path / "exp", "yaw", "H", SPEED, 0)
    assert row["file_name"] == "h070000a"
    assert sorted(stations) == list(cyp.STATIONS)


def test_committed_tables_yaw_30():
    row, stations = cyp.load_reference(COMMITTED, "yaw", "H", 7.0, 30)
    assert float(row["yaw_nominal_deg"]) == 30
    assert sorted(stations) == pytest.approx([0.30, 0.47, 0.63, 0.80, 0.95])
