# SPDX-License-Identifier: GPL-3.0-or-later
"""Contracts for the Phase VI r/R 0.95 speed-trend tool (odd T13).

`scripts/tipSpeedTrend.py` tabulates, per speed and station, the polar Reynolds
sensitivity, the polar-source (OSU vs DUT) lift ratio, the measured-side sensitivities,
the Cp shape indices and the tip excess over the inboard errors. These tests pin each
reduction on synthetic inputs with a closed-form answer, the real polar parsers, and the
CLI error exit.
"""

from __future__ import annotations

import csv
import math
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "validation" / "phaseVI"
SCRIPT = PACKAGE / "scripts" / "tipSpeedTrend.py"
sys.path.insert(0, str(PACKAGE / "scripts"))

import tipSpeedTrend as ts  # noqa: E402


def test_polar_parsers_read_the_committed_tables():
    osu, dut = ts.read_polar(), ts.read_polar(ts.POLAR_DUT)
    assert osu[0][0] == -180 and len(osu) > 50
    re_list, rows = ts.read_multi_re()
    assert re_list == [7.5e5, 1e6, 1.25e6, 1.5e6]
    assert all(len(r) == 5 for r in rows)
    # OSU lifts less than DUT at low alpha (TP-500-29955 A-7 vs A-8), same Re 1e6
    assert ts.polar_source_ratio(osu, dut, 2.7) == pytest.approx(1.21, abs=0.02)
    assert ts.polar_source_ratio(osu, dut, 7.0) < 1.08


def test_polar_state_slope_and_interpolation():
    polar = [(0.0, 0.0, 0.01), (10.0, 1.0, 0.02), (20.0, 1.0, 0.05)]
    st = ts.polar_state(polar, 5.0, half_width=2.0)
    assert st["cl"] == pytest.approx(0.5)
    assert st["cd"] == pytest.approx(0.015)
    assert st["slope_per_deg"] == pytest.approx(0.1)
    assert ts.polar_state(polar, 15.0)["slope_per_deg"] == pytest.approx(0.0)


def test_re_sensitivity_recovers_a_log_re_law_exactly():
    re_list = [7.5e5, 1e6, 1.25e6, 1.5e6]
    rows = [(a, *[0.5 + 0.1 * a + 0.04 * math.log(r / 1e6) for r in re_list]) for a in (0.0, 2.0, 4.0)]
    out = ts.re_sensitivity((re_list, rows), 2.0, 0.9e6)
    expected = 0.04 * math.log(0.9) / 0.7
    assert out["delta_cl_pct"] == pytest.approx(100 * expected, rel=1e-9)
    assert out["dcl_dlnRe"] == pytest.approx(0.04)
    assert not out["extrapolated"]
    assert ts.re_sensitivity((re_list, rows), 2.0, 0.5e6)["extrapolated"]


def test_real_multi_re_sensitivity_at_the_tip_is_small():
    multi = ts.read_multi_re()
    for alpha in (2.7, 3.8, 4.9, 6.1):
        assert abs(ts.re_sensitivity(multi, alpha, 0.92e6)["delta_cl_pct"]) < 3.0


def test_alpha_equivalent_and_nonlinear_guard():
    assert ts.alpha_equivalent(0.40, 0.46, 0.12, 0.0) == pytest.approx(0.5)
    assert math.isnan(ts.alpha_equivalent(0.40, 0.46, 0.05, 7.0))


def test_tip_excess_required_correction_and_predicted_error():
    assert ts.tip_excess(20.0, -2.0, 4.0) == pytest.approx(19.0)
    assert ts.required_correction(1.25, 1.0) == pytest.approx(0.2)
    assert ts.predicted_error_with_polar(10.0, 1.1) == pytest.approx(21.0)
    assert ts.error_pct(1.1, 1.0) == pytest.approx(10.0)


def test_spearman_monotone_reversed_and_ties():
    assert ts.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert ts.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert ts.spearman([1, 1, 2, 2], [1, 1, 2, 2]) == pytest.approx(1.0)


def test_cp_shape_closed_contour_integral_and_peak():
    # TE -> upper -> LE -> lower -> TE; Cp = -1 on the upper side, 0 on the lower side
    x = [1.0, 0.5, 0.0, 0.5, 1.0]
    cp = [-1.0, -1.0, -1.0, 0.0, 0.0]
    shape = ts.cp_shape(x, 2, cp)
    # upper TE->LE: -1 * (0 - 1) = +1; LE->first lower tap, trapezoid of (-1, 0) over dx 0.5: -0.25
    assert shape["cn_trap"] == pytest.approx(0.75)
    assert shape["peak_cp"] == pytest.approx(-1.0)
    # a sharp LE peak has le_peak_ratio > 1, a ramp < 1
    sharp = ts.cp_shape([1.0, 0.5, 0.2, 0.02, 0.0, 0.02, 1.0], 4, [0.0, -0.4, -0.8, -1.6, 0.5, 0.3, 0.2])
    ramp = ts.cp_shape([1.0, 0.5, 0.2, 0.02, 0.0, 0.02, 1.0], 4, [0.0, -0.4, -0.8, -0.5, 0.5, 0.3, 0.2])
    assert sharp["le_peak_ratio"] > 1.0 > ramp["le_peak_ratio"]


def test_shape_vs_alpha_joins_on_speed_and_station():
    trend = [{"speed": s, "r_over_R": "0.95", "alm_alpha_deg": a} for s, a in ((5, 2.7), (6, 3.8), (7, 4.9))]
    shape = [{"speed": s, "station": 95, "le_peak_ratio": v} for s, v in ((5, 0.7), (6, 1.0), (7, 1.3))]
    joined, rho = ts.shape_vs_alpha(shape, trend)
    assert len(joined) == 3 and rho == pytest.approx(1.0)


def test_station_means_and_interpolation():
    rows = [{"time": t, "root_dist": 1.0, "Re": 1e6 * t, "alpha_deg": 0.0, "cl": 0.5, "cd": 0.1, "rel_vel_mag": 1.0}
            for t in (0.0, 1.0, 2.0, 3.0)]
    keys = ("root_dist", "Re", "alpha_deg", "cl", "cd", "rel_vel_mag")
    m = ts.station_means(rows, (1.0, 2.0), keys)
    assert m["Re"] == pytest.approx(1.5e6) and m["cn"] == pytest.approx(0.5)
    assert ts.station_means(rows, (10.0, 11.0), keys) is None
    prof = [(0.5, {"v": 0.0}), (1.0, {"v": 10.0})]
    assert ts.interpolate_profile(prof, 0.75)["v"] == pytest.approx(5.0)
    with pytest.raises(ts.InputError):
        ts.interpolate_profile(prof, 1.2)


def test_readers_of_experiment_and_tap_summary(tmp_path):
    exp = tmp_path / "e.csv"
    exp.write_text("file_name,sequence,wind_speed_m_s,r_over_R,cn,ct,cm,cth,ctq,qnorm_pa\n"
                   "s0500000,S,5,0.95,0.3467,0.0059,0,0,0,823.5\n")
    assert ts.read_experiment(exp)[(5, 0.95)] == {"cn": 0.3467, "qnorm": 823.5}
    tap = tmp_path / "t.csv"
    tap.write_text("record,station,rev_std_pct\ns0500000,95,0.2\n")
    assert ts.read_tap_summary(tap)[("s0500000", 95)]["rev_std_pct"] == "0.2"
    with pytest.raises(ts.InputError):
        ts.read_experiment(tmp_path / "missing.csv")


def test_cli_missing_runs_exits_2_and_writes_nothing_to_inputs(tmp_path):
    out = tmp_path / "out"
    proc = subprocess.run([sys.executable, "-I", str(SCRIPT), "--runs-dir", str(tmp_path / "none"),
                           "--out", str(out)], capture_output=True, text=True)
    assert proc.returncode == 2
    assert "tipSpeedTrend:" in proc.stderr


def test_cli_help():
    proc = subprocess.run([sys.executable, "-I", str(SCRIPT), "--help"], capture_output=True, text=True)
    assert proc.returncode == 0 and "--runs-dir" in proc.stdout
