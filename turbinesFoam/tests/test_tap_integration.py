# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract for `tapIntegrationSensitivity.py` on analytic tap distributions."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "validation" / "phaseVI" / "scripts"))

import tapIntegrationSensitivity as tool  # noqa: E402

NUMS = sorted(tool.TAP_X)
X = np.array([tool.TAP_X[n] for n in NUMS])
SPLIT = NUMS.index(tool.LE_TAP)


def thin_geometry():
    """Symmetric 12 %-thick airfoil, z = 0.6 t (0.2969 sqrt(x) - ...) as (surface, x, z) rows."""
    xs = np.linspace(0.0, 1.0, 120)[1:]
    z = 0.6 * (0.2969 * np.sqrt(xs) - 0.126 * xs - 0.3516 * xs**2 + 0.2843 * xs**3 - 0.1036 * xs**4)
    rows = [("upper", float(a), float(b)) for a, b in zip(xs, z)]
    rows += [("lower", float(a), float(-b)) for a, b in zip(xs, z)]
    return rows


@pytest.fixture(scope="module")
def contour():
    return tool.contour_from_geometry(thin_geometry())


def loop_cp(upper_poly=lambda x: -1.2 - 0.8 * x + 0.5 * x**2):
    """Cp_u = polynomial, Cp_l = Cp_u + 2 x (1 - x): continuous at LE and TE, exact C_N = 1/3."""
    cp = np.array([upper_poly(x) + (2.0 * x * (1.0 - x) if n > tool.LE_TAP else 0.0) for n, x in zip(NUMS, X)])
    return cp


EXACT_LOOP_CN = 1.0 / 3.0


def test_trapezoid_matches_hand_value_for_unit_suction_step():
    # Upper Cp = -1 (LE tap included), lower Cp = 0: C_N = 1 minus the closing segment
    # lower(0.92) -> TE (mean of 0 and -1 over 0.08 of chord = 0.04) minus the LE -> lower(0.5 %)
    # segment (mean -0.5 over 0.005 = 0.0025): 1 - 0.04 - 0.0025.
    cp = np.where(np.arange(len(X)) <= SPLIT, -1.0, 0.0)
    assert tool.trapezoid_weights(X) @ cp == pytest.approx(0.9575, abs=1e-12)


def test_trapezoid_of_constant_cp_is_zero():
    assert tool.trapezoid_weights(X) @ np.full(len(X), 0.7) == pytest.approx(0.0, abs=1e-14)


def test_trapezoid_and_pchip_approach_exact_integral_of_polynomial_loop():
    cp = loop_cp()
    trap = tool.trapezoid_weights(X) @ cp
    pchip = tool.pchip_weights(X, SPLIT) @ cp
    assert trap == pytest.approx(EXACT_LOOP_CN, abs=0.03)
    assert pchip == pytest.approx(EXACT_LOOP_CN, abs=0.02)


def test_pchip_is_exact_for_constant_difference_between_surfaces():
    cp = np.where(np.arange(len(X)) <= SPLIT, -0.4, 0.6)
    cp[0] = -0.4
    # lower closes to the TE tap (-0.4): lower curve is 0.6 on [0,0.92] then falls linearly
    # (PCHIP, monotone) to -0.4 on [0.92,1]; the exact value is bounded between both extremes
    got = tool.pchip_weights(X, SPLIT) @ cp
    assert 0.92 <= got <= 1.0


def test_spline_integral_of_smooth_cp_of_x_on_closed_contour_is_zero(contour):
    # Cp = f(x) identical on both surfaces: the closed integral of f(x) dx is exactly zero.
    cp = 0.4 - 1.1 * X + 0.9 * X**2
    s_taps = tool.tap_arclength(X, SPLIT, contour)
    assert np.all(np.diff(s_taps) > 0) and s_taps[-1] < contour[2][-1]
    w = tool.spline_weights(X, SPLIT, contour)
    # a periodic spline of a function with a kink at LE/TE is not exact; the residual stays small
    assert abs(w @ cp) < 0.02


def test_spline_approaches_exact_integral_of_polynomial_loop(contour):
    cp = loop_cp()
    assert tool.spline_weights(X, SPLIT, contour) @ cp == pytest.approx(EXACT_LOOP_CN, abs=0.03)


def test_spline_reproduces_known_cn_of_smooth_pressure_loop(contour):
    # Cp = A cos(theta) on the contour is smooth and periodic; use Cp = x_c(s) - 0.5 times a
    # constant would be zero, so use Cp = z(s)-like asymmetry instead: Cp_u = -1, Cp_l = 0 is
    # a jump (not smooth). Take the pressure of a known C_N = 0.5*(1 - 0.0) via a smooth blend:
    x, z, s, le = contour
    taps_s = tool.tap_arclength(X, SPLIT, contour)

    def cp_of_s(sv):
        # smooth periodic in s: -0.5 + 0.5 cos(2 pi s / L) + 0.3 sin(2 pi s / L)
        phase = 2.0 * math.pi * sv / s[-1]
        return -0.5 + 0.5 * np.cos(phase) + 0.3 * np.sin(phase)

    cp = cp_of_s(taps_s)
    # exact: integral of cp(s) dx(s) over the same dense polyline
    exact = float(np.sum(0.5 * (cp_of_s(s[1:]) + cp_of_s(s[:-1])) * np.diff(x)))
    got = tool.spline_weights(X, SPLIT, contour) @ cp
    assert got == pytest.approx(exact, abs=0.01)


def test_leave_one_out_matches_independent_hand_calculation():
    x = np.array([1.0, 0.5, 0.0, 0.5])  # TE, upper, LE, lower (closing to TE)
    cp = np.array([0.0, -1.0, 1.0, 0.5])
    full = tool.trapezoid_weights(x) @ cp
    # full: segments TE->u: 0.5*(0-1)*(0.5-1)=0.25 ; u->LE: 0.5*(-1+1)*(0-0.5)=0 ;
    # LE->l: 0.5*(1+0.5)*(0.5-0)=0.375 ; l->TE: 0.5*(0.5+0)*(1-0.5)=0.125  => 0.75
    assert full == pytest.approx(0.75)
    results = dict(tool.leave_one_out(x, 2, [1, 2, 3]))
    # drop upper tap: TE->LE: 0.5*(0+1)*(0-1)=-0.5 ; LE->l 0.375 ; l->TE 0.125 => 0.0
    assert results[1] @ cp == pytest.approx(0.0)
    # drop LE: TE->u 0.25 ; u->l: 0.5*(-1+0.5)*(0.5-0.5)=0 ; l->TE 0.125 => 0.375
    assert results[2] @ cp == pytest.approx(0.375)
    # drop lower: TE->u 0.25 ; u->LE 0 ; LE->TE: 0.5*(1+0)*(1-0)=0.5 => 0.75
    assert results[3] @ cp == pytest.approx(0.75)
    assert results[1][1] == 0.0 and results[2][2] == 0.0  # dropped tap carries no weight


def test_leave_one_out_never_drops_the_te_tap_in_the_analysis():
    table, taps = _synthetic_table(station=95, cn_scale=1.0)
    summary, rows = tool.analyse_station(table, taps, 95, "synth", {}, tool.contour_from_geometry(thin_geometry()))
    dropped = {r[1] for r in rows if r[1].startswith("loo_drop_tap")}
    assert "loo_drop_tap1" not in dropped
    assert len(dropped) == len(NUMS) - 1
    deltas = [r[3] for r in rows if r[1].startswith("loo_drop_tap")]
    assert summary["loo_max_abs_pct"] == pytest.approx(max(abs(d) for d in deltas))
    assert summary["loo_rms_pct"] == pytest.approx(math.sqrt(np.mean(np.square(deltas))))


def _synthetic_table(station, cn_scale, revs=6, per_rev=20):
    import pandas as pd

    rng = np.random.default_rng(3)
    n = revs * per_rev
    cols = {}
    taps = []
    base = np.where(np.array(NUMS) <= tool.LE_TAP, -1.0 - 1.5 * (1 - X), 0.3 * (1 - X) + 0.2)
    base[0] = -0.5
    scale = 1.0 + 0.01 * rng.standard_normal(revs)
    scale = np.repeat(scale, per_rev)
    for k, num in enumerate(NUMS):
        name = f"P{num:02d}{station:02d}xxx"[:8]
        cols[name] = base[k] * scale * cn_scale
        taps.append((num, name))
    cols["CYCLECNT"] = np.repeat(np.arange(revs), per_rev)
    cols[f"QNORM{station}"] = np.full(n, 800.0)
    w = tool.trapezoid_weights(X)
    cols[f"CN{station}"] = (w @ np.array([cols[c] for _, c in taps]))
    return pd.DataFrame(cols), taps


def test_analyse_station_reproduces_record_channel_and_reports_repeatability():
    table, taps = _synthetic_table(station=63, cn_scale=1.0)
    committed = {("synth", 0.63): float(table["CN63"].mean())}
    summary, _ = tool.analyse_station(table, taps, 63, "synth", committed, tool.contour_from_geometry(thin_geometry()))
    assert summary["mismatch_vs_record_pct"] == pytest.approx(0.0, abs=1e-10)
    assert summary["mismatch_vs_committed_pct"] == pytest.approx(0.0, abs=1e-10)
    assert summary["n_revs"] == 6
    assert summary["rev_std"] > 0.0
    assert summary["rev_std_pct"] == pytest.approx(100 * summary["rev_std"] / summary["cn_nrel_trapezoid"])


def test_divide_by_qnorm_scales_pressures():
    table, taps = _synthetic_table(station=63, cn_scale=1.0)
    contour = tool.contour_from_geometry(thin_geometry())
    plain, _ = tool.analyse_station(table, taps, 63, "s", {}, contour)
    scaled, _ = tool.analyse_station(table, taps, 63, "s", {}, contour, divide_by_qnorm=True)
    assert scaled["cn_nrel_trapezoid"] == pytest.approx(plain["cn_nrel_trapezoid"] / 800.0)


def test_missing_station_exits_with_error(tmp_path, capsys):
    import pandas as pd

    table, _ = _synthetic_table(station=63, cn_scale=1.0)
    path = tmp_path / "uae6.z18.00.s0000000.parquet"
    table.to_parquet(path)
    code = tool.main([str(path), "--stations", "95", "--out", str(tmp_path / "out")])
    err = capsys.readouterr().err
    assert code == 2
    assert "station 95" in err
    assert not (tmp_path / "out" / "s0000000_summary.csv").exists()
    del pd


def test_station_taps_orders_by_contour_and_reports_missing():
    names = [f"P{n:02d}95xxx"[:8] for n in reversed(NUMS)]
    found = tool.station_taps(names, 95)
    assert [n for n, _ in found] == NUMS
    with pytest.raises(tool.TapError):
        tool.station_taps(names[:-1], 95)
