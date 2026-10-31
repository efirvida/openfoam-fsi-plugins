# SPDX-License-Identifier: GPL-3.0-or-later
"""Contracts for the AeroDyn BEM verification against the Phase VI tables on disk.

`scripts/verifyAeroDyn.py` selects measured points from the three table families
(Sequence S 0-yaw curve, blade-pitch sweep, fixed-yaw tables), builds one AeroDyn
driver case per point with the point's own rpm, density, wind speed, tip pitch and
yaw, runs `aerodyn_driver` and compares. These tests pin the selection rules, the
mapping into the driver/AeroDyn inputs (including the sign conventions of yaw and
pitch against the Hand et al. report and the OpenFAST driver documentation) and the
metrics of `odd/tasks/v13-adoption-asm.md` L12 on synthetic data. The real-driver
tests skip when `aerodyn_driver` is absent.
"""

from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PACKAGE = TESTS_DIR.parent / "validation" / "phaseVI"
sys.path.insert(0, str(PACKAGE / "scripts"))
sys.path.insert(0, str(PACKAGE / "tools"))
sys.path.insert(0, str(PACKAGE / "openfast"))

import buildAeroDynCase as build  # noqa: E402
import compareAeroDyn as compare  # noqa: E402
import element_data  # noqa: E402
import rtestAeroDyn as rtest  # noqa: E402
import verifyAeroDyn as verify  # noqa: E402
from case_config import load_config  # noqa: E402

ARCHIVE = PACKAGE / "data" / "experiment" / "uae6-archive"
YAW_PITCH = PACKAGE / "data" / "experiment" / "yaw-pitch"
DP_PREFIX = Path("/scratch/leahk/eduardo.donestevez/openfast-5.0.0-dp")
OPENFAST_ENV = DP_PREFIX
DRIVER = OPENFAST_ENV / "bin" / "aerodyn_driver"
needs_driver = pytest.mark.skipif(not DRIVER.is_file(), reason="aerodyn_driver not installed")


def keyed(text: str, key: str) -> str:
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == key:
            return parts[0].strip('"')
    raise KeyError(key)


# --- table parsing and point selection --------------------------------------

PERF_HEADER = (
    "file_name,sequence,wind_speed_m_s,yaw_token,yaw_deg,repetition,rpm,tsr,rotpow_kw,lsstqcor_nm,eaeroth_n,"
    "wtbaro_pa,wtatemp_degc,rho_kg_m3,eaerotq_n,yaw_nominal_deg,pitch_nominal_deg,b1pitch_deg,b3pitch_deg,"
    "b1rfb_nm,b3rfb_nm,eaerorfb_nm"
)
SPAN_HEADER = "file_name,sequence,wind_speed_m_s,r_over_R,cn,ct,cm,cth,ctq,qnorm_pa,yaw_nominal_deg,pitch_nominal_deg,repetition"


def perf_row(name, seq, speed, yaw, rep, power, rho=1.2, pitch=3, rpm=72.0, thrust=800.0):
    return (f"{name},{seq},{speed},0000,{yaw},{rep},{rpm},7.5,{power},300,{thrust},101000,12,{rho},310,"
            f"{yaw},{pitch},{pitch},{pitch},1,1,1")


def span_rows(name, seq, speed, yaw, rep, pitch=3):
    return [f"{name},{seq},{speed},{x},{0.5 + x},{0.05 + x / 10},-0.03,0.4,0.1,200,{yaw},{pitch},{rep}" for x in (0.3, 0.47, 0.63, 0.8, 0.95)]


def write_tables(directory: Path, prefix: str, perf: list[str], span: list[str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{prefix}_performance.csv").write_text(PERF_HEADER + "\n" + "\n".join(perf) + "\n")
    (directory / f"{prefix}_spanwise.csv").write_text(SPAN_HEADER + "\n" + "\n".join(span) + "\n")


def test_s_curve_points_cover_every_speed_of_the_committed_table():
    points = verify.s_curve_points(ARCHIVE)
    speeds = [p["wind_speed_m_s"] for p in points]
    assert speeds == [float(v) for v in range(5, 26)]
    assert all(p["family"] == "s-curve" and p["sequence"] == "S" for p in points)
    assert all(p["pitch_deg"] == 3.0 and p["yaw_deg"] == 0.0 for p in points)
    first = points[0]
    assert first["id"] == "s0500000"
    assert first["rpm"] == pytest.approx(71.68505195)
    assert first["rho_kg_m3"] == pytest.approx(1.250032664)
    assert first["performance"]["rotpow_kw"] == pytest.approx(2.200219865)
    assert sorted(first["spanwise"]) == [0.3, 0.47, 0.63, 0.8, 0.95]
    assert first["spanwise"][0.3]["cn"] == pytest.approx(0.3637853822)


def test_pitch_points_cover_the_whole_pitch_table_with_nominal_tip_pitch():
    points = verify.pitch_points(YAW_PITCH)
    assert len(points) == 125
    assert {(p["sequence"], p["pitch_deg"]) for p in points} == {("I", 0.0), ("T", 2.0), ("H", 3.0), ("S", 3.0), ("U", 4.0), ("J", 6.0)}
    assert all(p["yaw_deg"] == 0.0 and p["family"] == "pitch" for p in points)
    point = next(p for p in points if p["id"] == "i0500000")
    assert point["pitch_deg"] == 0.0 and point["rpm"] == pytest.approx(71.69895997)
    assert point["spanwise"][0.95]["cn"] > 0.0


def test_yaw_points_keep_first_repetition_per_speed_and_yaw_up_to_the_speed_cap(tmp_path):
    perf = [
        perf_row("s0500000", "S", 5, 0, 1, 2.0),
        perf_row("s0500001", "S", 5, 0, 0, 2.1),  # lower repetition listed later wins
        perf_row("s05m0000", "S", 5, 0, 0, 2.2),  # same repetition as s0500001: sorted file name decides
        perf_row("s0501000", "S", 5, 10, 0, 1.9),
        perf_row("s0501001", "S", 5, 10, 1, 1.8),
        perf_row("s1000000", "S", 10, 0, 0, 9.0),
        perf_row("s1100000", "S", 11, 0, 0, 9.5),  # above the cap
    ]
    span = []
    for row in perf:
        f = row.split(",")
        span += span_rows(f[0], "S", f[2], f[15], f[5])
    write_tables(tmp_path, "yaw_S", perf, span)
    points = verify.yaw_points(tmp_path, "S", max_speed=10.0)
    assert [p["id"] for p in points] == ["s0500001", "s0501000", "s1000000"]
    assert [(p["wind_speed_m_s"], p["yaw_deg"]) for p in points] == [(5.0, 0.0), (5.0, 10.0), (10.0, 0.0)]
    assert all(p["family"] == "yaw-S" for p in points)
    assert points[0]["performance"]["rotpow_kw"] == pytest.approx(2.1)


def test_yaw_points_of_the_committed_tables_follow_the_rule():
    s_points = verify.yaw_points(YAW_PITCH, "S", max_speed=10.0)
    h_points = verify.yaw_points(YAW_PITCH, "H", max_speed=10.0)
    assert len(s_points) == 42 and len(h_points) == 65
    assert max(p["wind_speed_m_s"] for p in s_points + h_points) == 10.0
    assert {p["yaw_deg"] for p in h_points} >= {-30.0, 0.0, 30.0}
    assert len({(p["wind_speed_m_s"], p["yaw_deg"]) for p in h_points}) == len(h_points)


def test_missing_or_unknown_rows_fail_loud(tmp_path):
    with pytest.raises(FileNotFoundError):
        verify.s_curve_points(tmp_path)
    with pytest.raises(ValueError):
        verify.yaw_points(YAW_PITCH, "X")


# --- mapping into the driver and AeroDyn inputs ------------------------------


def make_point(**override):
    point = {
        "family": "pitch", "id": "t0700000", "sequence": "T", "wind_speed_m_s": 7.0, "rpm": 71.9, "rho_kg_m3": 1.2345,
        "pitch_deg": 2.0, "yaw_deg": 0.0, "repetition": 0,
        "performance": {"file_name": "t0700000", "rotpow_kw": 5.0, "eaeroth_n": 900.0, "lsstqcor_nm": 660.0},
        "spanwise": {x: {"cn": 0.5 + x, "ct": 0.05} for x in (0.3, 0.47, 0.63, 0.8, 0.95)},
    }
    point.update(override)
    return point


def test_point_case_uses_the_points_own_rpm_density_wind_pitch_and_yaw(tmp_path):
    point = make_point(pitch_deg=6.0, yaw_deg=-10.0, rpm=72.1234, rho_kg_m3=1.2111, wind_speed_m_s=9.0)
    out = build.build_point_case(point, "bem", tmp_path / "case")
    case = json.loads((out / "case.json").read_text())
    inputs = case["inputs"]
    assert inputs["rotor_speed_rpm"]["value"] == 72.1234  # measured table rpm, not tsr * U / R
    assert "table" in inputs["rotor_speed_rpm"]["source"]
    assert inputs["rho_kg_m3"]["value"] == 1.2111 and inputs["wind_speed_m_s"]["value"] == 9.0
    assert inputs["pitch_deg"]["value"] == 6.0 and inputs["yaw_deg"]["value"] == -10.0
    driver = (out / "ad_driver.dvr").read_text()
    assert float(keyed(driver, "RotSpeed(1)")) == pytest.approx(72.1234)
    assert float(keyed(driver, "FldDens")) == pytest.approx(1.2111)
    assert float(keyed(driver, "HWindSpeed")) == 9.0
    assert float(keyed(driver, "BldPitch(1)")) == 6.0
    assert float(keyed(driver, "NacYaw(1)")) == -10.0
    assert case["experiment"]["performance"]["rotpow_kw"] == 5.0
    assert case["point"]["id"] == "t0700000" and case["wake"] == "bem"


@pytest.mark.parametrize("pitch", [0.0, 2.0, 3.0, 4.0, 6.0])
def test_table_pitch_is_the_tip_pitch_toward_feather_and_twist_plus_pitch_is_minus_mounting(tmp_path, pitch):
    """Hand et al. p.20: pitch = tip chord to the plane of the disk, positive toward feather = AeroDyn BldPitch.

    The tip reference keeps `BlTwist + BldPitch = -mounting` for any pitch: the tip node has BlTwist 0
    and the tip mounting angle is -pitch.
    """
    out = build.build_point_case(make_point(pitch_deg=pitch), "bem", tmp_path / "case")
    case = json.loads((out / "case.json").read_text())
    cfg = load_config(PACKAGE / "config" / "case.yaml")
    cfg["turbine"]["blade_dz"] = build.BLADE_DZ
    cfg["turbine"]["pitch_deg"] = pitch
    cfg["turbine"]["pitch_reference"] = "tip"
    rows = element_data.blade_element_rows(cfg)
    assert len(rows) == len(case["nodes"])
    for row, node in zip(rows, case["nodes"]):
        assert node["twist"] + pitch == pytest.approx(-row[5], abs=1e-9)
    assert case["nodes"][-1]["twist"] == pytest.approx(0.0, abs=1e-9)
    assert -rows[-1][5] == pytest.approx(pitch, abs=1e-9)
    # more pitch -> less incidence: the whole mounting angle moves by exactly the pitch change
    base = build.build_point_case(make_point(pitch_deg=3.0), "bem", tmp_path / "base")
    base_nodes = json.loads((base / "case.json").read_text())["nodes"]
    for node, ref in zip(case["nodes"], base_nodes):
        assert (node["twist"] + pitch) - (ref["twist"] + 3.0) == pytest.approx(pitch - 3.0, abs=1e-9)


def test_nac_yaw_sign_reproduces_positive_yaw_blade_advancing_at_180_deg_azimuth():
    """Hand et al. Fig. B-25: in positive yaw the blade advances into the wind at 180 deg azimuth.

    UAE: counterclockwise as seen from upwind (report p.62), positive yaw clockwise seen from above
    (report App. G). AeroDyn driver docs: RotSpeed positive clockwise looking downwind, NacYaw positive
    counterclockwise looking downward. The two are mirror images about the wind-vertical plane, so
    `NacYaw = +yaw` keeps the property for the clockwise AeroDyn rotor.
    """
    assert build.NAC_YAW_SIGN == 1
    assert verify.bottom_blade_axial_velocity(clockwise_from_upwind=False, yaw_clockwise_from_top_deg=20.0) < 0.0
    assert verify.bottom_blade_axial_velocity(clockwise_from_upwind=True, yaw_counterclockwise_from_top_deg=20.0 * build.NAC_YAW_SIGN) < 0.0
    # and the opposite sign would not
    assert verify.bottom_blade_axial_velocity(clockwise_from_upwind=True, yaw_counterclockwise_from_top_deg=-20.0) > 0.0
    assert verify.bottom_blade_axial_velocity(clockwise_from_upwind=False, yaw_clockwise_from_top_deg=0.0) == pytest.approx(0.0, abs=1e-12)


def test_skew_model_is_on_only_for_yawed_points(tmp_path):
    yawed = build.build_point_case(make_point(yaw_deg=20.0), "bem", tmp_path / "yawed")
    ad = (yawed / "aerodyn.dat").read_text()
    assert keyed(ad, "Skew_Mod") == "1" and keyed(ad, "SkewMomCorr") == "True" and keyed(ad, "SkewRedistr_Mod") == "1"
    assert "skew" in json.loads((yawed / "case.json").read_text())
    straight = build.build_point_case(make_point(yaw_deg=0.0), "bem", tmp_path / "straight")
    ad0 = (straight / "aerodyn.dat").read_text()
    assert keyed(ad0, "Skew_Mod") == "0" and keyed(ad0, "SkewMomCorr") == "False"
    sens = build.build_point_case(make_point(yaw_deg=20.0), "bem", tmp_path / "sens", skew_mom_corr=False)
    assert keyed((sens / "aerodyn.dat").read_text(), "SkewMomCorr") == "False"
    assert keyed((sens / "aerodyn.dat").read_text(), "Skew_Mod") == "1"


def test_existing_gate_case_is_unchanged_by_the_point_support(tmp_path):
    out = build.build_case("S", 7, "bem", tmp_path / "gate")
    ad = (out / "aerodyn.dat").read_text()
    assert keyed(ad, "Skew_Mod") == "0" and keyed(ad, "SkewMomCorr") == "False" and keyed(ad, "SkewRedistr_Mod") == "0"
    assert "experiment" not in json.loads((out / "case.json").read_text())


def test_compare_reads_the_experiment_embedded_in_a_point_case(tmp_path):
    from test_aerodyn_case import write_synthetic_output  # noqa: PLC0415

    point = make_point(wind_speed_m_s=7.0, sequence="T", pitch_deg=2.0)
    out = build.build_point_case(point, "bem", tmp_path / "case")
    write_synthetic_output(out, power_w=5500.0, thrust_n=950.0, cn_of_r=lambda x: 0.5 + x, alpha_of_r=lambda x: 10.0)
    metrics = compare.compare_case(out, revolutions=1)["metrics"]
    assert metrics["power_exp_kw"] == 5.0 and metrics["power_kw"] == pytest.approx(5.5)
    assert metrics["power_error_pct"] == pytest.approx(10.0)
    assert metrics["thrust_error_pct"] == pytest.approx(100.0 * (950.0 - 900.0) / 900.0)
    assert metrics["stations"]["0.95"]["cn_exp"] == pytest.approx(1.45)
    assert metrics["stations"]["0.95"]["cn_error_pct"] == pytest.approx(0.0, abs=1e-3)


# --- L12 metrics on synthetic data ---------------------------------------------


def test_finite_differences_of_a_value_ladder_are_per_degree_between_consecutive_levels():
    steps = verify.pitch_slopes({3.0: 6.0, 0.0: 9.0, 2.0: 7.0, 6.0: 4.5})
    assert [(s["pitch_lo"], s["pitch_hi"]) for s in steps] == [(0.0, 2.0), (2.0, 3.0), (3.0, 6.0)]
    assert [s["slope"] for s in steps] == pytest.approx([-1.0, -1.0, -0.5])


def test_sign_agreement_counts_matching_slopes_and_ignores_flat_experiment_steps():
    model = [{"pitch_lo": 0.0, "pitch_hi": 2.0, "slope": -1.0}, {"pitch_lo": 2.0, "pitch_hi": 3.0, "slope": 0.4}, {"pitch_lo": 3.0, "pitch_hi": 6.0, "slope": -0.2}]
    experiment = [{"pitch_lo": 0.0, "pitch_hi": 2.0, "slope": -0.8}, {"pitch_lo": 2.0, "pitch_hi": 3.0, "slope": -0.3}, {"pitch_lo": 3.0, "pitch_hi": 6.0, "slope": 0.0}]
    result = verify.sign_agreement(model, experiment)
    assert result["agree"] == 1 and result["total"] == 3
    assert result["pairs"][1]["agree"] is False
    assert result["pairs"][2]["agree"] is False  # a zero experiment slope has no sign to agree with


def test_power_ratio_difference_is_in_percentage_points_of_the_yaw_zero_power():
    points = [
        {"sequence": "S", "wind_speed_m_s": 7.0, "yaw_deg": 0.0, "model_power_kw": 6.0, "exp_power_kw": 5.0},
        {"sequence": "S", "wind_speed_m_s": 7.0, "yaw_deg": 20.0, "model_power_kw": 5.1, "exp_power_kw": 4.0},
        {"sequence": "S", "wind_speed_m_s": 8.0, "yaw_deg": 20.0, "model_power_kw": 5.0, "exp_power_kw": 4.0},  # no yaw-0 partner
    ]
    rows = verify.power_ratios(points)
    assert len(rows) == 1
    row = rows[0]
    assert row["ratio_model"] == pytest.approx(0.85) and row["ratio_exp"] == pytest.approx(0.8)
    assert row["diff_pp"] == pytest.approx(5.0)


def test_attached_flow_power_errors_cover_5_to_7_ms_per_pitch():
    rows = [
        {"sequence": "T", "pitch_deg": 2.0, "wind_speed_m_s": 5.0, "power_error_pct": -4.0},
        {"sequence": "T", "pitch_deg": 2.0, "wind_speed_m_s": 8.0, "power_error_pct": -30.0},
        {"sequence": "J", "pitch_deg": 6.0, "wind_speed_m_s": 7.0, "power_error_pct": 12.0},
    ]
    table = verify.attached_power_errors(rows, speeds=(5.0, 6.0, 7.0))
    assert [(r["pitch_deg"], r["wind_speed_m_s"]) for r in table] == [(2.0, 5.0), (6.0, 7.0)]


def test_probe_configuration_rows_pair_h_and_s_at_the_same_speed():
    def row(seq, speed, model, exp):
        return {"family": "pitch", "status": "ok", "sequence": seq, "wind_speed_m_s": speed, "power_kw": model, "power_exp_kw": exp,
                "thrust_n": 2 * model, "thrust_exp_n": 2 * exp, "power_error_pct": 100.0 * (model - exp) / exp}
    rows = [row("H", 5.0, 2.0, 2.2), row("S", 5.0, 2.05, 2.3), row("H", 6.0, 3.0, 3.1), row("T", 5.0, 2.0, 2.0)]
    table = verify.probe_configuration_rows(rows)
    assert len(table) == 1  # 6 m/s has no S partner
    assert table[0]["power_exp_H_over_S"] == pytest.approx(2.2 / 2.3)
    assert table[0]["power_model_H_over_S"] == pytest.approx(2.0 / 2.05)


def test_l12_summary_counts_the_band_the_attached_errors_and_the_yaw_ratio_differences():
    s_rows = [{"status": "ok", "wind_speed_m_s": 5.0, "power_error_pct": -7.0}, {"status": "ok", "wind_speed_m_s": 9.0, "power_error_pct": -12.0},
              {"status": "ok", "wind_speed_m_s": 18.0, "power_error_pct": -70.0}]
    attached = [{"pitch_deg": 0.0, "power_error_pct": -8.0}, {"pitch_deg": 0.0, "power_error_pct": 11.0}, {"pitch_deg": 6.0, "power_error_pct": -21.0}]
    ratios = [{"sequence": "S", "wind_speed_m_s": 5.0, "yaw_deg": 10.0, "diff_pp": -2.0}, {"sequence": "H", "wind_speed_m_s": 7.0, "yaw_deg": -10.0, "diff_pp": 6.5},
              {"sequence": "S", "wind_speed_m_s": 7.0, "yaw_deg": 30.0, "diff_pp": 1.0}, {"sequence": "S", "wind_speed_m_s": 7.0, "yaw_deg": 135.0, "diff_pp": -40.0},
              {"sequence": "S", "wind_speed_m_s": 9.0, "yaw_deg": 10.0, "diff_pp": 30.0}]
    summary = verify.l12_summary(s_rows, attached, ratios)
    assert summary["s_curve_power_within_band"] == [5.0]
    assert summary["s_curve_worst_power"] == {"wind_speed_m_s": 18.0, "error_pct": -70.0}
    assert summary["attached_power_max_abs_error_pct_by_pitch"] == {"0": 11.0, "6": 21.0}
    assert (summary["attached_power_within_band"], summary["attached_power_total"]) == (1, 3)
    small = summary["yaw_ratio_small_yaw"]
    assert (small["within_band"], small["total"], small["max_abs_diff_pp"]) == (1, 2, 6.5) and small["at"] == "H 7 m/s yaw -10"
    large = summary["yaw_ratio_20_to_90_deg"]  # 135 deg is outside BEM validity and 9 m/s is outside 5-7 m/s
    assert (large["within_band"], large["total"]) == (1, 1)


# --- CLI --------------------------------------------------------------------


def test_cli_list_prints_the_selection_without_running_openfast(capsys):
    assert verify.main(["--list"]) == 0
    text = capsys.readouterr().out
    lines = {line.split()[0]: int(line.split()[1]) for line in text.splitlines() if line.strip()}
    assert lines == {"s-curve": 21, "pitch": 125, "yaw-S": 42, "yaw-H": 65, "total": 253}


def test_cli_refuses_a_missing_driver_with_a_clear_message(tmp_path, capsys):
    code = verify.main(["--openfast-env", str(tmp_path / "nope"), "--out", str(tmp_path / "out"), "--work", str(tmp_path / "work")])
    assert code == 1
    assert "aerodyn_driver" in capsys.readouterr().err


# --- r-test tolerance rule (openfast/rtestAeroDyn.py) -------------------------


def test_rtest_rule_atol_is_a_fraction_of_the_channel_scale_with_a_floor():
    base = [0.0, 1.0, 100.0, 1000.0]
    assert rtest.channel_atol(__import__("numpy").array(base)) == pytest.approx(10.0 ** (3 - 1.9))
    assert rtest.channel_atol(__import__("numpy").zeros(5)) == pytest.approx(1e-6)


def test_rtest_rule_one_percent_relative_plus_atol():
    import numpy as np

    base = np.array([[100.0, 200.0, 300.0, 400.0]])
    assert rtest.passing_channels(base * 1.009, base)[0]
    assert not rtest.passing_channels(base * 1.02, base)[0]
    nan = base.copy()
    nan[0, 1] = float("nan")
    assert not rtest.passing_channels(nan, base)[0]
    assert not rtest.passing_channels(base[:, :3], base)[0]


def test_rtest_outb_round_trip_of_the_compressed_format(tmp_path):
    import struct

    import numpy as np

    path = tmp_path / "x.outb"
    n_chan, n_time = 2, 3
    scale, offset = np.array([100.0, 10.0], dtype=np.float32), np.array([5.0, -2.0], dtype=np.float32)
    data = np.array([[1.0, 2.0], [1.5, 2.5], [2.0, 3.0]])
    packed = np.round(data * scale + offset).astype("<i2")
    with path.open("wb") as f:
        f.write(struct.pack("<hii", 2, n_chan, n_time))
        f.write(struct.pack("<dd", 0.0, 0.25))
        f.write(scale.astype("<f4").tobytes() + offset.astype("<f4").tobytes())
        desc = b"unit test"
        f.write(struct.pack("<i", len(desc)) + desc)
        for name in ("Time", "A", "B"):
            f.write(name.ljust(10).encode())
        for unit in ("(s)", "(-)", "(-)"):
            f.write(unit.ljust(10).encode())
        f.write(packed.tobytes())
    names, matrix = rtest.read_outb(path)
    assert names == ["Time", "A", "B"]
    assert matrix[:, 0] == pytest.approx([0.0, 0.25, 0.5])
    assert matrix[:, 1:] == pytest.approx(data, abs=0.011)


# --- real driver (skipped without OpenFAST) ------------------------------------


@needs_driver
def test_real_driver_runs_a_table_point_and_matches_the_gate_pipeline(tmp_path):
    point = next(p for p in verify.s_curve_points(ARCHIVE) if p["wind_speed_m_s"] == 7.0)
    row = verify.run_point(point, "bem", tmp_path / "s7", OPENFAST_ENV)
    assert row["status"] == "ok"
    assert row["power_error_pct"] == pytest.approx(-2.8, abs=1.0)  # odd/tasks/v13-adoption-asm.md L11 (tsr*U/R rpm; here the measured rpm)
    assert math.isfinite(row["thrust_error_pct"])
    assert set(row["stations"]) == {"0.30", "0.47", "0.63", "0.80", "0.95"}


@needs_driver
def test_real_driver_positive_yaw_loads_the_blade_at_180_deg_azimuth_more_than_at_0(tmp_path):
    """The mapped sign is the physical one: the advancing blade (180 deg for positive yaw) sees more Vrel."""
    import numpy as np

    point = make_point(sequence="S", wind_speed_m_s=7.0, rpm=71.8667, rho_kg_m3=1.25, pitch_deg=3.0, yaw_deg=30.0)
    out = build.build_point_case(point, "bem", tmp_path / "case")
    log = subprocess.run([str(DRIVER), "ad_driver.dvr"], cwd=out, capture_output=True, text=True)
    assert log.returncode == 0, log.stdout[-500:]
    names, data = compare.read_output(out / "ad_driver.out")
    cols = {n.lower(): data[:, i] for i, n in enumerate(names)}
    period = 60.0 / point["rpm"]
    time = cols["time"]
    mid = [k for k in cols if k.endswith("vrel") and k.startswith("ab1n")][40]
    last = time >= time[-1] - period - 1e-9
    t = time[last] - (time[-1] - period)
    vrel = cols[mid][last]
    at = lambda target: float(np.interp(target, t, vrel))  # noqa: E731
    assert at(0.5 * period) > at(0.0)  # azimuth 180 vs 0 (blade 1 starts up, TMax = whole periods)


# --- precision comparison tool (openfast/comparePrecision.py) -------------------


def test_compare_precision_reports_the_largest_difference_per_family(tmp_path):
    import comparePrecision  # noqa: PLC0415

    def write(directory, power, cn):
        directory.mkdir()
        fields = "family,id,status,wind_speed_m_s,power_kw,thrust_n,torque_nm"
        (directory / "points.csv").write_text(fields + "\n" + "\n".join(f"s-curve,p{i},ok,5,{p},100,10" for i, p in enumerate(power)) + "\n")
        (directory / "stations.csv").write_text("family,id,r_over_R,cn,ct\n" + "\n".join(f"s-curve,p{i},0.30,{c},0.1" for i, c in enumerate(cn)) + "\n")

    write(tmp_path / "a", [2.0, 4.0], [1.0, 1.0])
    write(tmp_path / "b", [2.0, 4.04], [1.0, 1.1])
    rows = {r["quantity"].split()[1]: r for r in comparePrecision.compare(tmp_path / "a", tmp_path / "b")}
    assert rows["power_kw"]["max_difference"] == pytest.approx(0.04 / 4.04) and rows["power_kw"]["where"] == "p1"
    assert rows["cn"]["max_difference"] == pytest.approx(0.1 / 1.1)
    assert comparePrecision.compare(tmp_path / "a", tmp_path / "b", max_speed=4.0) == []


# --- double-precision default binary (task T13) ---------------------------------


def test_default_openfast_is_the_double_precision_prefix_in_every_consumer():
    import quantifyUncertainty as qu

    assert verify.OPENFAST_ENV_DEFAULT == DP_PREFIX
    assert qu.OPENFAST_ENV_DEFAULT == DP_PREFIX
    slurm = (PACKAGE / "scripts" / "slurm" / "aerodyn.slurm").read_text()
    assert f'OPENFAST_ENV="${{OPENFAST_ENV:-{DP_PREFIX}}}"' in slurm


def test_build_script_is_posix_double_precision_v5_with_rpath():
    path = PACKAGE / "openfast" / "build_openfast_dp.sh"
    text = path.read_text()
    assert text.startswith("#!/bin/sh")
    assert subprocess.run(["sh", "-n", str(path)], capture_output=True).returncode == 0
    assert "-DDOUBLE_PRECISION=ON" in text and "OPENFAST_TAG=${OPENFAST_TAG:-v5.0.0}" in text
    assert "-DCMAKE_INSTALL_RPATH=" in text and "BUILD-INFO.txt" in text
    assert str(DP_PREFIX) in text


def _fake_rtest_module(root: Path) -> Path:
    for name, mod, ref in [("ad_bem", 1, True), ("ad_olaf", 3, True), ("ad_olaf_noref", 3, False)]:
        case = root / name
        case.mkdir(parents=True)
        (case / "ad_driver.dvr").write_text('"aero.dat"   AeroFile\n')
        (case / "aero.dat").write_text(f"{mod}   Wake_Mod\n")
        if ref:
            (case / "ad_driver.outb").write_bytes(b"")
    return root


def test_rtest_case_selection_is_bem_only_by_default_and_takes_olaf_on_request(tmp_path):
    module = _fake_rtest_module(tmp_path / "aerodyn")
    run, skipped = rtest.select_cases(module)
    assert [e["case"] for e in run] == ["ad_bem"]
    assert {e["case"]: e["reason"] for e in skipped}["ad_olaf"] == "Wake_Mod 3 (not selected)"
    run, skipped = rtest.select_cases(module, wake_mods=(3,))
    assert [e["case"] for e in run] == ["ad_olaf"]
    assert {e["case"]: e["reason"] for e in skipped}["ad_olaf_noref"] == "no reference .outb"
    run, _ = rtest.select_cases(module, wake_mods=(1, 3))
    assert [e["case"] for e in run] == ["ad_bem", "ad_olaf"]
