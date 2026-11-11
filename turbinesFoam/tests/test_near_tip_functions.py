# SPDX-License-Identifier: GPL-3.0-or-later
"""Contracts for the Trigaux near-tip correction functions applied offline to Phase VI.

`validation/phaseVI/data/near-tip-functions/trigaux2024_tableC.csv` is the transcription of
Tables C.2/C.3 of F. Trigaux's thesis (UCLouvain 2024); `scripts/applyNearTipFunctions.py`
computes the effective tip distance of the blade (thesis eq. 3.29-3.31), interpolates the
functions and applies them to station c_n values. These tests pin the table integrity, the
effective distance against the closed form, the interpolation, the lift-only application and
the error exit for d/c outside the table.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "validation" / "phaseVI"
SCRIPT = PACKAGE / "scripts" / "applyNearTipFunctions.py"
sys.path.insert(0, str(PACKAGE / "scripts"))

import applyNearTipFunctions as nt  # noqa: E402

TABLE = nt.read_table()
KEYS = [(k, s) for k in nt.KERNELS for s in nt.SIGMAS]


@pytest.mark.parametrize("key", KEYS)
def test_table_block_layout(key):
    rows = TABLE[key]
    assert len(rows) == 30
    assert rows[0] == (0.0, 1.0, 0.0, 1.0)
    ds = [r[0] for r in rows]
    assert ds == sorted(ds) and len(set(ds)) == 30
    step = (1.0 / 128.0) * 15.0
    for i, d in zip(range(1, 30), ds[1:]):
        assert d == pytest.approx((0.5 + i) * step, abs=6e-5)


@pytest.mark.parametrize("key", KEYS)
def test_table_identity_to_printed_precision(key):
    """(1 - F_Cl)(1 - F_alpha_e) = 1 - F_l within the rounding of three 4-decimal numbers."""
    for d, fl, fcl, fae in TABLE[key]:
        bound = 5e-5 * (1.0 + (1.0 - fcl) + (1.0 - fae)) + 1e-12
        assert abs((1 - fcl) * (1 - fae) - (1 - fl)) <= bound, (key, d)


@pytest.mark.parametrize("key", KEYS)
def test_table_total_lift_function_decreases_from_the_tip(key):
    fl = [r[1] for r in TABLE[key]]
    assert all(b < a for a, b in zip(fl, fl[1:]))
    assert all(0.0 <= v <= 1.0 for v in fl)


def test_f_cl_is_kernel_independent_at_the_phase_vi_distance():
    """Parent check of tip-model-analysis L9: F_Cl(0.6445) is 0.183-0.187 in all six blocks."""
    values = [nt.interp_functions(TABLE[k], 0.6445)[1] for k in KEYS]
    assert max(values) - min(values) < 0.005


def _linear_blade(c_root, c_tip, radius, n):
    return [(radius * i / n, c_root + (c_tip - c_root) * i / n) for i in range(1, n + 1)]


def test_effective_distance_matches_eq_3_31_on_a_linear_taper():
    radius, c_tip, c_root = 5.0, 0.2, 0.6
    blade = _linear_blade(c_root, c_tip, radius, 7)
    slope = (c_root - c_tip) / radius  # |dc/dy|
    for r in (1.0, 2.5, 4.0, 4.9):
        closed = math.log(1.0 + slope * (radius - r) / c_tip) / slope
        assert nt.effective_distance(blade, r, radius) == pytest.approx(closed, rel=1e-12)


def test_effective_distance_rectangular_blade_is_distance_over_chord():
    blade = [(1.0, 0.4), (3.0, 0.4), (5.0, 0.4)]
    assert nt.effective_distance(blade, 4.0, 5.0) == pytest.approx(2.5, rel=1e-12)


def test_effective_distance_of_the_committed_blade_at_the_stations():
    blade = nt.read_blade()
    assert nt.effective_distance(blade, 0.95 * nt.RADIUS_M) == pytest.approx(0.683, abs=5e-3)
    assert nt.effective_distance(blade, nt.RADIUS_M) == 0.0


def test_interpolation_returns_tabulated_values_and_linear_midpoints():
    rows = TABLE[("3D", 0.5)]
    for d, *values in rows[3:6]:
        assert nt.interp_functions(rows, d) == pytest.approx(tuple(values), abs=1e-12)
    (d1, *a), (d2, *b) = rows[4], rows[5]
    mid = nt.interp_functions(rows, 0.5 * (d1 + d2))
    assert mid == pytest.approx(tuple(0.5 * (x + y) for x, y in zip(a, b)), abs=1e-12)
    low = nt.functions_at(TABLE, d1, "3D", 0.25)
    high = nt.functions_at(TABLE, d1, "3D", 0.5)
    assert nt.functions_at(TABLE, d1, "3D", 0.375) == pytest.approx(
        tuple(0.5 * (x + y) for x, y in zip(low, high)), abs=1e-12)


def test_cl_application_scales_only_the_lift_part():
    alpha, cl, cd = 12.0, 0.9, 0.05
    a = math.radians(alpha)
    cn = cl * math.cos(a) + cd * math.sin(a)
    ct = cl * math.sin(a) - cd * math.cos(a)
    cl_back, cd_back = nt.split_lift(cn, ct, alpha)
    assert (cl_back, cd_back) == pytest.approx((cl, cd), abs=1e-12)
    f = 0.18
    expected = (1 - f) * cl * math.cos(a) + cd * math.sin(a)
    assert nt.apply_lift_factor(cn, cl * math.cos(a), 1 - f) == pytest.approx(expected, abs=1e-12)
    # F = 0 is the identity; the scale approximation differs by (F * drag part)
    assert nt.apply_lift_factor(cn, cl * math.cos(a), 1.0) == cn
    assert nt.apply_scale(cn, 1 - f) - expected == pytest.approx(-f * cd * math.sin(a), abs=1e-12)


def test_distance_outside_the_table_is_rejected():
    with pytest.raises(nt.InputError, match="outside the table range"):
        nt.interp_functions(TABLE[("2D", 0.25)], 3.5)
    with pytest.raises(nt.InputError, match="sigma/c"):
        nt.functions_at(TABLE, 1.0, "3D", 2.0)


def _synthetic_runs(tmp_path, blade_chord=None):
    run = tmp_path / "runs" / "aerodyn-bem-SU7"
    run.mkdir(parents=True)
    stations = {f"{r:.2f}": {"cn": 0.8, "ct": 0.08, "alpha_deg": 6.0, "cn_exp": 0.77}
                for r in (0.80, 0.95)}
    (run / "metrics.json").write_text(json.dumps({"stations": stations}))
    blade = tmp_path / "blade.csv"
    if blade_chord is not None:
        blade.write_text("# header\n0.5,%g\n5.029,%g\n" % (blade_chord, blade_chord))
    return tmp_path / "runs", blade


def _run(*args):
    return subprocess.run([sys.executable, "-I", str(SCRIPT), *args],
                          capture_output=True, text=True, check=False)


def test_cli_cl_mode_end_to_end(tmp_path):
    runs, _ = _synthetic_runs(tmp_path)
    out = tmp_path / "out.csv"
    done = _run("--apply", "cl", "--runs-dir", str(runs), "--cells", "S7", "--models", "bem",
                "--out", str(out))
    assert done.returncode == 0, done.stderr
    lines = out.read_text().splitlines()
    assert len(lines) == 3
    header = lines[0].split(",")
    row = dict(zip(header, lines[2].split(",")))  # r/R 0.95
    cl, cd = nt.split_lift(0.8, 0.08, 6.0)
    fcl = float(row["F_Cl"])
    assert 0.17 < fcl < 0.19
    expected = 0.8 - fcl * cl * math.cos(math.radians(6.0))
    assert float(row["cn_corr"]) == pytest.approx(expected, abs=2e-4)
    assert row["err_uncorr_pct"] == f"{100 * (0.8 - 0.5064) / 0.5064:.1f}"


def test_cli_exits_2_when_d_over_c_is_outside_the_table(tmp_path):
    runs, blade = _synthetic_runs(tmp_path, blade_chord=0.05)  # d/c ~ 20 at r/R 0.95? >> table
    done = _run("--apply", "cl", "--runs-dir", str(runs), "--cells", "S7", "--models", "bem",
                "--blade", str(blade))
    assert done.returncode == 2
    assert "outside the table range" in done.stderr
    assert done.stdout == ""


def test_cli_summarize_counts_bands(tmp_path):
    runs, _ = _synthetic_runs(tmp_path)
    out = tmp_path / "out.csv"
    assert _run("--apply", "cl", "--runs-dir", str(runs), "--cells", "S7", "--models", "bem",
                "--out", str(out)).returncode == 0
    done = _run("--summarize", str(out))
    assert done.returncode == 0, done.stderr
    assert "bem: inside 10 % 1/2 -> 1/2" in done.stdout


def _synthetic_cell(tmp_path, cell, models=("bem",)):
    runs = tmp_path / "runs"
    for model in models:
        run = runs / f"aerodyn-{model}-{cell[0]}U{cell[1:]}"
        run.mkdir(parents=True)
        stations = {f"{r:.2f}": {"cn": 1.2, "ct": 0.05, "alpha_deg": 20.0, "cn_exp": 1.1}
                    for r in (0.80, 0.95)}
        (run / "metrics.json").write_text(json.dumps({"stations": stations}))
    return runs


@pytest.mark.parametrize("cell", ["S10", "S13", "S15", "S20", "S25"])
def test_stall_cells_are_selectable_but_not_default(cell):
    labels = [f"{c[0]}{c[1]}" for c in nt.CELLS]
    assert cell in labels
    assert [f"{c[0]}{c[1]}" for c in nt.DEFAULT_CELLS] == ["S5", "S6", "S7", "S8", "H7"]


@pytest.mark.parametrize("cell", ["S10", "S13", "S15", "S20", "S25"])
def test_cli_accepts_stall_cells_with_bem(tmp_path, cell):
    runs = _synthetic_cell(tmp_path, cell)
    done = _run("--apply", "cl", "--runs-dir", str(runs), "--cells", cell, "--models", "bem")
    assert done.returncode == 0, done.stderr
    rows = done.stdout.splitlines()
    assert len(rows) == 3 and all(r.split(",")[1] == cell for r in rows[1:])


def test_cli_skips_models_without_a_run_for_the_cell(tmp_path):
    runs = _synthetic_cell(tmp_path, "S20")
    done = _run("--apply", "cl", "--runs-dir", str(runs), "--cells", "S20")
    assert done.returncode == 0, done.stderr
    assert "skipping alm S20" in done.stderr and "skipping olaf-dp S20" in done.stderr
    assert {r.split(",")[0] for r in done.stdout.splitlines()[1:]} == {"bem"}
