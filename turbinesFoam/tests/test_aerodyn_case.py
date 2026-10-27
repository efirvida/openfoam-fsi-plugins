# SPDX-License-Identifier: GPL-3.0-or-later
"""Contracts for the Phase VI AeroDyn-driver case builder and comparator.

The pipeline is the OpenFAST (AeroDyn BEMT and OLAF) code-to-code arbiter of the
v1.3 ALM: `scripts/buildAeroDynCase.py` writes a self-contained driver case from
repository data and `scripts/compareAeroDyn.py` reads its output with the same
definitions `comparePhaseVI.py` uses. The AeroDyn outputs below are synthetic
placeholders generated under pytest's `tmp_path`; no result is a validation
result and OpenFAST is never required.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PACKAGE = TESTS_DIR.parent / "validation" / "phaseVI"
sys.path.insert(0, str(PACKAGE / "scripts"))
sys.path.insert(0, str(PACKAGE / "tools"))

import buildAeroDynCase as build  # noqa: E402
import compareAeroDyn as compare  # noqa: E402
import comparePhaseVI  # noqa: E402
import element_data  # noqa: E402
from case_config import load_config, read_blade  # noqa: E402

POINTS = [("S", 5), ("S", 6), ("S", 7), ("S", 8), ("H", 7)]
RADIUS = 5.029
HUB_RADIUS = 0.5083
EXPERIMENT = PACKAGE / "data" / "experiment" / "uae6-archive"


def keyed(text: str, key: str) -> str:
    """Value token(s) of the AeroDyn input line that carries `key`."""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == key:
            return parts[0].strip('"')
    raise KeyError(key)


def tip_config(reference: str) -> dict:
    cfg = load_config(PACKAGE / "config" / "case.yaml")
    cfg["turbine"]["blade_dz"] = build.BLADE_DZ
    cfg["turbine"]["pitch_reference"] = reference
    return cfg


# --- geometry ---------------------------------------------------------------


@pytest.mark.parametrize("reference", element_data.PITCH_REFERENCES)
def test_twist_plus_pitch_is_minus_the_alm_mounting_angle(reference):
    cfg = tip_config(reference)
    rows = element_data.blade_element_rows(cfg)
    nodes = build.blade_nodes(cfg)
    assert len(nodes) == len(rows)
    pitch = float(cfg["turbine"]["pitch_deg"])
    for node, row in zip(nodes, rows):
        assert node["radius"] == pytest.approx(row[1])
        assert node["chord"] == pytest.approx(row[3])
        # AeroDyn positive-to-feather twist+pitch is the opposite sign of the
        # NREL-to-turbinesFoam mounting angle (row[5]).
        assert node["twist"] + pitch == pytest.approx(-row[5], abs=1e-9)


def test_tip_reference_has_zero_tip_twist_and_three_degree_pitch():
    cfg = tip_config("tip")
    rows = element_data.blade_element_rows(cfg)
    assert rows[-1][5] == pytest.approx(-3.0)
    nodes = build.blade_nodes(cfg)
    assert nodes[-1]["twist"] == pytest.approx(0.0, abs=1e-9)
    assert nodes[-1]["radius"] == pytest.approx(RADIUS)
    assert nodes[0]["radius"] == pytest.approx(HUB_RADIUS)  # AeroDyn needs BlSpn = 0 at the root


def test_twist_reference_choices_differ_by_the_tip_twist():
    tip = build.blade_nodes(tip_config("tip"))
    zero = build.blade_nodes(tip_config("twist-zero"))
    tip_twist = read_blade()[-1]["twist"]
    for a, b in zip(tip, zero):
        assert b["twist"] - a["twist"] == pytest.approx(tip_twist, abs=1e-9)


def test_root_nodes_use_the_cylinder_profile_like_the_alm():
    cfg = tip_config("tip")
    nodes = build.blade_nodes(cfg)
    for node in nodes:
        assert (node["airfoil"] == "cylinder") == (node["radius"] < element_data.ELEMENT_CYLINDER_END - 1e-9)
    assert nodes[0]["airfoil"] == "cylinder" and nodes[-1]["airfoil"] == "S809"


def test_blade_file_round_trip(tmp_path):
    cfg = tip_config("tip")
    nodes = build.blade_nodes(cfg)
    path = tmp_path / "blade.dat"
    path.write_text(build.render_blade_file(nodes, HUB_RADIUS, {"cylinder": 1, "S809": 2}))
    text = path.read_text()
    assert int(keyed(text, "NumBlNds")) == len(nodes)
    body = [line.split() for line in text.splitlines() if len(line.split()) == 12 and re.fullmatch(r"[-+0-9.eE\s]+", line)]
    assert len(body) == len(nodes)
    for node, row in zip(nodes, body):
        assert float(row[0]) == pytest.approx(node["radius"] - HUB_RADIUS, abs=1e-6)
        assert float(row[1]) == 0.0 and float(row[2]) == 0.0 and float(row[3]) == 0.0
        assert float(row[4]) == pytest.approx(node["twist"], abs=1e-6)
        assert float(row[5]) == pytest.approx(node["chord"], abs=1e-6)
        assert int(row[6]) == {"cylinder": 1, "S809": 2}[node["airfoil"]]


# --- polar ------------------------------------------------------------------


def test_polar_conversion_round_trip(tmp_path):
    source = PACKAGE / "data" / "polars" / "S809_OSU_Re1M_total.dat"
    original = build.read_foam_polar(source)
    out = tmp_path / "S809.dat"
    out.write_text(build.render_airfoil_file(original, "S809 OSU total"))
    text = out.read_text()
    assert keyed(text, "NumTabs") == "1"
    assert keyed(text, "InclUAdata").lower() == "false"
    assert int(keyed(text, "NumAlf")) == len(original)
    back = build.read_aerodyn_polar(out)
    assert len(back) == len(original)
    for a, b in zip(original, back):
        assert b == pytest.approx(a, abs=1e-6)
    alphas = [row[0] for row in back]
    assert alphas == sorted(alphas) and alphas[0] == -180.0 and alphas[-1] == 180.0


def test_cylinder_polar_matches_the_alm_cylinder_profile():
    rows = build.cylinder_polar()
    assert rows[0][0] == -180.0 and rows[-1][0] == 180.0
    assert all(row[1] == 0.0 and row[2] == 1.1 and row[3] == 0.0 for row in rows)


# --- case.json --------------------------------------------------------------


@pytest.mark.parametrize("sequence,speed", POINTS)
def test_case_json_inputs_per_point(tmp_path, sequence, speed):
    out = tmp_path / "case"
    build.build_case(sequence, speed, "bem", out)
    case = json.loads((out / "case.json").read_text())
    cfg = load_config(PACKAGE / "config" / "case.yaml")
    entry = comparePhaseVI_select(cfg, speed, sequence)
    omega = entry["tsr"] * speed / RADIUS
    experiment, _ = comparePhaseVI.load_experiment(EXPERIMENT, sequence, speed)
    inputs = case["inputs"]
    assert inputs["rotor_speed_rpm"]["value"] == pytest.approx(omega * 30.0 / math.pi, rel=1e-9)
    assert inputs["rho_kg_m3"]["value"] == pytest.approx(float(experiment["rho_kg_m3"]))
    assert inputs["rotor_radius_m"]["value"] == pytest.approx(RADIUS)
    assert inputs["hub_radius_m"]["value"] == pytest.approx(HUB_RADIUS)
    assert inputs["pitch_deg"]["value"] == pytest.approx(3.0)
    assert inputs["wind_speed_m_s"]["value"] == pytest.approx(speed)
    assert inputs["n_blades"]["value"] == 2
    for key in ("cone_deg", "tilt_deg", "yaw_deg"):
        assert inputs[key]["value"] == 0.0
    assert all(item["source"] for item in inputs.values())
    assert case["sequence"] == sequence and case["speed_m_s"] == speed and case["wake"] == "bem"
    assert case["pitch_reference"] == "tip"
    # driver file carries the same numbers
    driver = (out / "ad_driver.dvr").read_text()
    assert float(keyed(driver, "RotSpeed(1)")) == pytest.approx(inputs["rotor_speed_rpm"]["value"], rel=1e-9)
    assert float(keyed(driver, "FldDens")) == pytest.approx(inputs["rho_kg_m3"]["value"], rel=1e-9)
    assert float(keyed(driver, "HWindSpeed")) == speed
    assert float(keyed(driver, "HubRad(1)")) == pytest.approx(HUB_RADIUS)
    assert float(keyed(driver, "BldPitch(1)")) == pytest.approx(3.0)


def comparePhaseVI_select(cfg, speed, sequence):
    from case_config import select_speed

    return select_speed(cfg, speed, sequence)


def test_bem_options_are_the_documented_like_for_like_set(tmp_path):
    out = tmp_path / "case"
    build.build_case("S", 7, "bem", out)
    ad = (out / "aerodyn.dat").read_text()
    driver = (out / "ad_driver.dvr").read_text()
    assert keyed(ad, "Wake_Mod") == "1"
    for flag in ("TipLoss", "HubLoss", "TanInd", "AIDrag", "TIDrag"):
        assert keyed(ad, flag) == "True", flag
    assert keyed(ad, "DBEMT_Mod") == "0"
    assert keyed(ad, "UA_Mod") == "0"
    assert keyed(ad, "TwrPotent") == "0" and keyed(ad, "TwrShadow") == "0"
    assert keyed(ad, "TwrAero") == "False"
    assert keyed(ad, "AFTabMod") == "1"
    assert keyed(ad, "NumAFfiles") == "2"
    for key in ("Overhang(1)", "ShftTilt(1)", "Precone(1)"):
        assert float(keyed(driver, key)) == 0.0, key
    assert float(keyed(driver, "NacYaw(1)")) == 0.0
    assert int(keyed(driver, "NumBlades(1)")) == 2
    assert not (out / "OLAF.dat").exists()
    for name in ("blade.dat", "S809.dat", "cylinder.dat", "ad_driver.dvr", "aerodyn.dat", "case.json"):
        assert (out / name).is_file(), name


def test_olaf_case_writes_olaf_input_with_guideline_wake(tmp_path):
    out = tmp_path / "case"
    build.build_case("S", 7, "olaf", out)
    ad = (out / "aerodyn.dat").read_text()
    olaf = (out / "OLAF.dat").read_text()
    case = json.loads((out / "case.json").read_text())
    assert keyed(ad, "Wake_Mod") == "3"
    assert keyed(ad, "OLAFInputFileName") == "OLAF.dat"
    rpm = case["inputs"]["rotor_speed_rpm"]["value"]
    dt = float(keyed(olaf, "DTfvw"))
    assert dt == pytest.approx(build.OLAF_DPSI_DEG / (6.0 * rpm))
    period = 60.0 / rpm
    n_nw = int(keyed(olaf, "nNWPanels"))
    # OpenFAST guideline: at least 4 D of wake and at least 10 revolutions
    assert n_nw * dt >= 10 * period - dt
    assert n_nw * dt * 0.5 * 7 >= 4 * 10.058 - 0.5 * 7 * dt
    assert int(keyed(olaf, "nFWPanels")) == 0
    assert int(keyed(olaf, "nNWPanelsFree")) <= n_nw
    assert keyed(olaf, "RegDeterMethod") == "3"
    assert float(keyed(olaf, "WakeRegFactor")) == pytest.approx(0.6)
    assert float(keyed(olaf, "WingRegFactor")) == pytest.approx(0.6)
    driver = (out / "ad_driver.dvr").read_text()
    t_max = float(keyed(driver, "TMax"))
    assert float(keyed(driver, "DT")) == pytest.approx(dt)
    assert t_max >= n_nw * dt + build.OLAF_AVERAGING_REVOLUTIONS * period - dt
    assert case["olaf"]["n_nw_panels"] == n_nw


def test_bem_driver_runs_whole_revolutions(tmp_path):
    out = tmp_path / "case"
    build.build_case("H", 7, "bem", out)
    case = json.loads((out / "case.json").read_text())
    period = 60.0 / case["inputs"]["rotor_speed_rpm"]["value"]
    driver = (out / "ad_driver.dvr").read_text()
    dt = float(keyed(driver, "DT"))
    assert period / dt == pytest.approx(round(period / dt))
    assert float(keyed(driver, "TMax")) >= 2 * period - dt


def test_rejects_unknown_point(tmp_path):
    with pytest.raises(SystemExit):
        build.main(["--sequence", "S", "--speed", "7.5", "--wake", "bem", "--out", str(tmp_path / "x")])


def test_refuses_to_overwrite_existing_case(tmp_path):
    out = tmp_path / "case"
    build.build_case("S", 7, "bem", out)
    with pytest.raises(SystemExit):
        build.main(["--sequence", "S", "--speed", "7", "--wake", "bem", "--out", str(out)])


# --- comparison -------------------------------------------------------------

N_REV = 4
STEPS = 36


def write_synthetic_output(case_dir: Path, power_w, thrust_n, cn_of_r, alpha_of_r, ct_of_r=None, drift=None):
    """A minimal AeroDyn text output: rotor channels + nodal Cn/Ct/Alpha of blades 1 and 2."""
    case = json.loads((case_dir / "case.json").read_text())
    nodes = case["nodes"]
    period = 60.0 / case["inputs"]["rotor_speed_rpm"]["value"]
    dt = period / STEPS
    names = ["Time", "RtAeroPwr", "RtAeroFxh"]
    for blade in (1, 2):
        for i in range(1, len(nodes) + 1):
            names += [f"B{blade}N{i:03d}Alpha", f"B{blade}N{i:03d}Cn", f"B{blade}N{i:03d}Ct"]
    lines = [
        "Predictions were generated on 27-Oct-2026 using AeroDyn_driver (synthetic)",
        "Description from the AeroDyn input file: synthetic",
        " ".join(f"{n:>14s}" for n in names),
        " ".join(f"{'(-)':>14s}" for _ in names),
    ]
    for step in range(N_REV * STEPS + 1):
        t = step * dt
        revolution = int(t / period - 1e-9) if step else 0
        scale = 1.0 + (drift(revolution) if drift else 0.0)
        row = [t, power_w * scale, thrust_n * scale]
        for _ in (1, 2):
            for node in nodes:
                x = node["radius"] / RADIUS
                row += [alpha_of_r(x), cn_of_r(x) * scale, (ct_of_r or (lambda x: 0.1))(x)]
        lines.append(" ".join(f"{v:14.7e}" for v in row))
    (case_dir / "ad_driver.out").write_text("\n".join(lines) + "\n")


@pytest.fixture()
def synthetic_case(tmp_path):
    out = tmp_path / "case"
    build.build_case("S", 7, "bem", out)
    write_synthetic_output(
        out, power_w=6000.0, thrust_n=1200.0, cn_of_r=lambda x: 0.5 + x, alpha_of_r=lambda x: 20.0 - 10.0 * x
    )
    return out


def test_compare_power_thrust_and_station_interpolation(synthetic_case, tmp_path):
    result = compare.compare_case(synthetic_case, revolutions=1)
    metrics = result["metrics"]
    assert metrics["power_kw"] == pytest.approx(6.0)
    assert metrics["thrust_n"] == pytest.approx(1200.0)
    experiment, spanwise = comparePhaseVI.load_experiment(EXPERIMENT, "S", 7.0)
    assert metrics["power_error_pct"] == pytest.approx(100 * (6.0 - float(experiment["rotpow_kw"])) / float(experiment["rotpow_kw"]))
    assert metrics["thrust_error_pct"] == pytest.approx(100 * (1200.0 - float(experiment["eaeroth_n"])) / float(experiment["eaeroth_n"]))
    assert metrics["torque_nm"] == pytest.approx(6000.0 / (metrics["rotor_speed_rpm"] * math.pi / 30.0))
    for station in comparePhaseVI.STATIONS:
        entry = metrics["stations"][f"{station:.2f}"]
        assert entry["cn"] == pytest.approx(0.5 + station, abs=2e-3)  # linear field, linear interpolation
        assert entry["alpha_deg"] == pytest.approx(20.0 - 10.0 * station, abs=2e-2)
        assert entry["cn_exp"] == pytest.approx(spanwise[station]["cn"])
        assert entry["cn_error_pct"] == pytest.approx(100 * (entry["cn"] - spanwise[station]["cn"]) / spanwise[station]["cn"])


def test_compare_uses_only_whole_revolutions(synthetic_case):
    # the last revolution differs from the first three: averaging 1 rev must see only it
    write_synthetic_output(
        synthetic_case, 6000.0, 1200.0, lambda x: 0.5 + x, lambda x: 10.0, drift=lambda rev: 0.5 if rev == N_REV - 1 else 0.0
    )
    last = compare.compare_case(synthetic_case, revolutions=1)["metrics"]
    two = compare.compare_case(synthetic_case, revolutions=2)["metrics"]
    assert last["power_kw"] == pytest.approx(9.0, rel=2e-2)
    assert two["power_kw"] == pytest.approx(7.5, rel=2e-2)
    assert last["window"]["revolutions"] == 1


def test_compare_reports_revolution_convergence(synthetic_case):
    write_synthetic_output(
        synthetic_case, 6000.0, 1200.0, lambda x: 0.5 + x, lambda x: 10.0, drift=lambda rev: 0.004 * rev
    )
    conv = compare.compare_case(synthetic_case, revolutions=1)["metrics"]["convergence"]
    # last two revolutions differ by about 0.4 % in power and in Cn(0.95): converged under 1 %
    assert 0.0 < conv["power_change_pct"] < 1.0
    assert 0.0 < conv["cn_095_change_pct"] < 1.0
    assert conv["converged"] is True
    write_synthetic_output(
        synthetic_case, 6000.0, 1200.0, lambda x: 0.5 + x, lambda x: 10.0, drift=lambda rev: 0.05 * rev
    )
    conv = compare.compare_case(synthetic_case, revolutions=1)["metrics"]["convergence"]
    assert conv["power_change_pct"] > 1.0 and conv["converged"] is False


def test_compare_main_writes_table_and_metrics(synthetic_case, capsys):
    assert compare.main(["--case", str(synthetic_case), "--revolutions", "1"]) == 0
    text = capsys.readouterr().out
    assert "power" in text and "0.95" in text and "alpha" in text.lower()
    metrics = json.loads((synthetic_case / "metrics.json").read_text())
    assert metrics["wake"] == "bem" and metrics["power_kw"] == pytest.approx(6.0)


def test_compare_fails_loud_without_output(tmp_path):
    out = tmp_path / "case"
    build.build_case("S", 7, "bem", out)
    assert compare.main(["--case", str(out)]) == 1


def test_compare_fails_loud_on_short_window(synthetic_case):
    assert compare.main(["--case", str(synthetic_case), "--revolutions", "9"]) == 2


def test_olaf_convergence_requires_a_full_wake(tmp_path):
    out = tmp_path / "case"
    build.build_case("S", 7, "olaf", out)
    # four steady revolutions are far shorter than the 10+ revolution wake of the case
    write_synthetic_output(out, 6000.0, 1200.0, lambda x: 0.5 + x, lambda x: 10.0)
    conv = compare.compare_case(out, revolutions=1)["metrics"]["convergence"]
    assert conv["power_change_pct"] == pytest.approx(0.0, abs=1e-9)
    assert conv["wake_filled"] is False and conv["converged"] is False


# --- batch scripts ----------------------------------------------------------


def test_slurm_script_is_posix_ntasks_only_and_defaults_to_the_dev_queue():
    import subprocess

    path = PACKAGE / "scripts" / "slurm" / "aerodyn.slurm"
    text = path.read_text()
    assert text.startswith("#!/bin/sh")
    assert subprocess.run(["sh", "-n", str(path)], capture_output=True).returncode == 0
    assert "#SBATCH --ntasks=1" in text and "#SBATCH --partition=sequana_cpu_dev" in text
    assert "--nodes" not in text and "--mem" not in text


def test_submit_matrix_dry_run_lists_the_ten_cases_balanced_over_partitions():
    import subprocess

    result = subprocess.run(
        ["sh", str(PACKAGE / "openfast" / "submit_matrix.sh")], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) == 10
    points = {(l.split("SEQUENCE=")[1].split()[0], l.split("SPEED=")[1].split()[0], l.split("WAKE=")[1].split()[0]) for l in lines}
    assert points == {(s, str(v), w) for s, v in [("S", 5), ("S", 6), ("S", 7), ("S", 8), ("H", 7)] for w in ("bem", "olaf")}
    olaf = [l for l in lines if "WAKE=olaf" in l]
    assert sum("-p sequana_cpu " in l for l in olaf) == 3 and sum("-p sequana_cpu_bigmem " in l for l in olaf) == 2
    assert all("-p sequana_cpu_dev " in l for l in lines if "WAKE=bem" in l)
