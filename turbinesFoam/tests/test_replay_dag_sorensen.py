# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests of the offline Dag & Sorensen replica (`replayDagSorensen.py`).

Analytic layer: one vortex segment with the exp(-(d/eps)^2) kernel, Gamma-jump
bookkeeping, spanwise smoothing on a known Gamma, the sign of the helix sweep.
Solver layer: the replica reproduces the solver's own `tipCorrectionDebug` line and
element CSV of `tests/dagSorensenReplayCase/reference` (produced by ./Allrun there; no
OpenFOAM is needed to run these tests).
"""
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "validation" / "phaseVI" / "scripts"
REF = Path(__file__).resolve().parent / "dagSorensenReplayCase" / "reference"
sys.path.insert(0, str(SCRIPTS))

import replayDagSorensen as R  # noqa: E402


def make_rotor(axis=(-1.0, 0.0, 0.0), omega=111.0, n_blades=1, eps_user=0.0):
    axis = np.array(axis, dtype=float)
    return R.Rotor(
        origin=np.zeros(3), axis=axis / np.linalg.norm(axis), down=np.array([1.0, 0.0, 0.0]), u_inf=10.0,
        omega=omega, radius=0.45, n_blades=n_blades, blade_azimuth_rad=[0.0] * n_blades,
        wake_turns=2, wake_step_deg=2.0, epsilon_user=eps_user, free_stream=np.array([10.0, 0.0, 0.0]),
    )


def straight_blade(n=6, r0=0.05, r1=0.45):
    """Elements on +z of a rotor with axis +/-x (blade in the rotor plane x = 0)."""
    edges = np.linspace(r0, r1, n + 1)
    r = 0.5 * (edges[1:] + edges[:-1])
    pts = np.zeros((1, n, 3))
    pts[0, :, 2] = r
    return pts, r


def line_segments(length, n, d_perp):
    """Straight line along +x from the origin, evaluation point at (0, d_perp, 0)."""
    edges = np.linspace(0.0, length, n + 1)
    cen = np.stack([0.5 * (edges[1:] + edges[:-1]), np.zeros(n), np.zeros(n)], axis=1)
    dl = np.stack([np.diff(edges), np.zeros(n), np.zeros(n)], axis=1)
    return cen, dl, np.array([[0.0, d_perp, 0.0]])


# --------------------------------------------------------------------------- #
# Biot-Savart with the Gaussian kernel
# --------------------------------------------------------------------------- #

def test_single_segment_value_and_direction():
    gamma, eps, length, d = 2.0, 0.3, 0.1, 0.2
    cen = np.array([[0.0, 0.0, 0.0]])
    dl = np.array([[length, 0.0, 0.0]])
    w = R.induced_velocity(np.array([[0.0, d, 0.0]]), cen, dl, np.array([gamma]), np.array([eps]))
    expected = gamma / (4 * math.pi) * length * d / d ** 3 * math.exp(-(d / eps) ** 2)
    assert w[0] == pytest.approx([0.0, 0.0, expected], rel=1e-12, abs=1e-15)


def test_semi_infinite_line_tends_to_gamma_over_four_pi_d_for_large_eps():
    gamma, d = 1.5, 0.25
    cen, dl, pt = line_segments(200.0, 400000, d)
    w = R.induced_velocity(pt, cen, dl, np.full(len(cen), gamma), np.full(len(cen), 1.0e6))
    assert w[0, 2] == pytest.approx(gamma / (4 * math.pi * d), rel=1e-3)


def test_kernel_removes_the_inviscid_induction_inside_the_core():
    # Eq. (16): the correction is Gamma/(4 pi d) exp(-(d/eps)^2); a half-infinite line,
    # fine discretisation (the viscous factor uses the segment distance, not d_perp).
    gamma, eps, d = 1.0, 0.4, 0.1
    cen, dl, pt = line_segments(8.0, 80000, d)
    w = R.induced_velocity(pt, cen, dl, np.full(len(cen), gamma), np.full(len(cen), eps))
    x = cen[:, 0]
    r = np.sqrt(x * x + d * d)
    quad = np.sum(gamma / (4 * math.pi) * d / r ** 3 * np.exp(-(r / eps) ** 2) * dl[:, 0])
    assert w[0, 2] == pytest.approx(quad, rel=1e-9)
    assert 0.0 < w[0, 2] < gamma / (4 * math.pi * d)


# --------------------------------------------------------------------------- #
# Gamma bookkeeping and smoothing
# --------------------------------------------------------------------------- #

def station_inputs(gamma):
    n = len(gamma)
    pts, _ = straight_blade(n)
    eps = np.full(n, 0.05)
    ux = np.full(n, 10.0)
    ut = np.full(n, 40.0)
    return pts[0], np.asarray(gamma, dtype=float), eps, ux, ut


def test_gamma_jump_bookkeeping_closes_at_both_ends():
    pts, g, eps, ux, ut = station_inputs([1.0, 2.0, 4.0])
    *_, st_gam, ok = R.stations(pts, g, eps, ux, ut, make_rotor(), R.Switches())
    assert list(st_gam) == [-1.0, -1.0, -2.0, 4.0]    # Gamma(p-1) - Gamma(p), 0 outside
    assert st_gam.sum() == 0.0
    assert ok.all()


def test_end_station_extrapolation_and_hold():
    pts, g, eps, ux, ut = station_inputs([1.0, 1.0, 1.0, 1.0])
    ux = np.array([10.0, 11.0, 12.0, 13.0])
    rot = make_rotor()
    st = R.stations(pts, g, eps, ux, ut, rot, R.Switches())
    held = R.stations(pts, g, eps, ux, ut, rot, R.Switches(tip_hold=True))
    # position is extrapolated by 1.5/-0.5 in both modes: r = r_last + half spacing
    assert st[0][-1, 2] == pytest.approx(pts[-1, 2] + 0.5 * (pts[-1, 2] - pts[-2, 2]))
    assert held[0][-1, 2] == pytest.approx(st[0][-1, 2])
    # tangent of the flow angle at the tip station: linear extrapolation u_x = 13.5, hold u_x = 13
    r_tip = st[0][-1, 2]
    assert st[2][-1] == pytest.approx(r_tip * 13.5 / 40.0)
    assert held[2][-1] == pytest.approx(r_tip * 13.0 / 40.0)


def test_smoothing_constant_gamma_unchanged_and_impulse_spreads():
    pts, _ = straight_blade(6)
    pts = pts[0]
    eps = np.full(6, 0.1)
    assert R.smooth_gamma(pts, np.full(6, 3.0), eps) == pytest.approx(np.full(6, 3.0))
    imp = np.array([0.0, 0.0, 1.0, 0.0, 0.0, 0.0])
    out = R.smooth_gamma(pts, imp, eps)
    ds = np.linalg.norm(pts - pts[2], axis=1)
    w = np.exp(-0.5 * (ds / 0.1) ** 2)
    # element 3 sees a normalised Gaussian window centred on itself
    ds3 = np.linalg.norm(pts - pts[3], axis=1)
    w3 = np.exp(-0.5 * (ds3 / 0.1) ** 2)
    assert out[3] == pytest.approx(w3[2] / w3.sum())
    assert out[2] == pytest.approx(1.0 / np.exp(-0.5 * (np.linalg.norm(pts - pts[2], axis=1) / 0.1) ** 2).sum())
    assert out.max() < 1.0 and out.min() > 0.0
    assert w[2] == 1.0
    # eps -> 0 leaves the circulation untouched
    assert R.smooth_gamma(pts, imp, np.zeros(6)) == pytest.approx(imp)


def test_smoothing_switch_changes_only_non_constant_gamma():
    pts, _ = straight_blade(6)
    rot = make_rotor()
    eps = np.full((1, 6), 0.1)
    ux, ut = np.full((1, 6), 10.0), np.full((1, 6), 40.0)
    flat = np.full((1, 6), 2.0)
    on = R.trailing_correction(pts, flat, eps, ux, ut, rot, R.Switches())
    off = R.trailing_correction(pts, flat, eps, ux, ut, rot, R.Switches(smooth=False))
    assert on == pytest.approx(off, rel=1e-12)
    bumpy = np.array([[1.0, 1.0, 3.0, 1.0, 1.0, 1.0]])
    on = R.trailing_correction(pts, bumpy, eps, ux, ut, rot, R.Switches())
    off = R.trailing_correction(pts, bumpy, eps, ux, ut, rot, R.Switches(smooth=False))
    assert np.abs(on - off).max() > 1e-3 * np.abs(off).max()


# --------------------------------------------------------------------------- #
# Sign of the helix
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("axis", [(-1.0, 0.0, 0.0), (1.0, 0.0, 0.0)])
def test_implemented_sweep_decelerates_and_reversed_sweep_accelerates(axis):
    # Lifting rotor (Gamma > 0): the trailing helix must reduce the axial inflow (Eq. 26,
    # u_x + w_x with w_x < 0), for either sign of the rotor axis; the reversed sign flips it.
    pts, _ = straight_blade(8)
    rot = make_rotor(axis=axis)
    g = np.full((1, 8), 0.5)
    g[0, -1] = 0.3
    eps = np.full((1, 8), 0.05)
    ux, ut = np.full((1, 8), 10.0), np.full((1, 8), 40.0)
    # blade-motion direction is omega axis x r: z-blade, axis -x -> +y
    w = R.trailing_correction(pts, g, eps, ux, ut, rot, R.Switches(smooth=False))
    wrev = R.trailing_correction(pts, g, eps, ux, ut, rot, R.Switches(smooth=False, sweep_reverse=True))
    assert (w[:, 0] < 0.0)[2:].all()
    assert (wrev[:, 0] > 0.0)[2:].all()
    # mirrored helix: axial component flips sign, magnitude is the same order
    assert wrev[3, 0] == pytest.approx(-w[3, 0], rel=0.2)


def test_alpha_decreases_with_implemented_sweep_sign():
    theta = 0.0                       # normal along the axial direction
    ux, ut = 10.0, -40.0              # rel = (u_x, component along the blade motion)
    base, _ = R.alpha_of(theta, ux, ut)
    lowered, _ = R.alpha_of(theta, ux - 1.0, ut)    # w_x = -1 m/s
    raised, _ = R.alpha_of(theta, ux + 1.0, ut)
    assert lowered < base < raised


def test_rotate_is_right_handed():
    v = R.rotate(np.array([0.0, 1.0, 0.0]), np.zeros(3), np.array([0.0, 0.0, 1.0]), math.pi / 2)
    assert v == pytest.approx([-1.0, 0.0, 0.0], abs=1e-15)


# --------------------------------------------------------------------------- #
# Mesh, polar, parsing
# --------------------------------------------------------------------------- #

def test_blockmesh_uniform_and_graded(tmp_path):
    d = tmp_path / "blockMeshDict"
    d.write_text(
        "scale 1;\nvertices\n(\n(0 0 0) (4 0 0) (4 1 0) (0 1 0) (0 0 1) (4 0 1) (4 1 1) (0 1 1)\n);\n"
        "blocks\n(\n hex (0 1 2 3 4 5 6 7) (8 2 2) simpleGrading (4 1 1)\n);\n")
    m = R.BlockMesh(d)
    assert m.n_cells == 32
    edges = m.blocks[0][2][0]
    w = np.diff(edges)
    assert edges[-1] == pytest.approx(4.0)
    assert w[-1] / w[0] == pytest.approx(4.0)
    assert m.cell_volume(np.array([0.01, 0.2, 0.2])) == pytest.approx(w[0] * 0.5 * 0.5)
    with pytest.raises(ValueError):
        m.cell_volume(np.array([9.0, 0.0, 0.0]))


def test_polar_interpolation_and_reynolds_drag():
    p = R.Polar([(-10, -1.0, 0.1), (0, 0.0, 0.01), (10, 1.0, 0.2)], re_ref=1.0e6)
    assert p.lift(5.0) == pytest.approx(0.5)
    assert p.drag(5.0) == pytest.approx(0.105)
    # profileData::updateRe: cd / K with K = f(ReRef)/f(Re), f = (ln Re - 0.407)^-2.64
    k = (math.log(1e6) - 0.407) ** -2.64 / (math.log(2e6) - 0.407) ** -2.64
    assert p.drag(5.0, 2.0e6) == pytest.approx(0.105 / k)
    assert p.drag(5.0, 1.0e6) == pytest.approx(0.105)


def test_read_case_of_reference_fixture():
    rot, blade, polars, gauss = R.read_case(REF / "meshEps")
    assert rot.n_blades == 1 and rot.omega == pytest.approx(5.0 * 10.0 / 0.45)
    assert rot.wake_turns == 2 and rot.wake_step_deg == 2.0 and rot.epsilon_user == 0.0
    assert blade.n == 6 and blade.chord == pytest.approx(np.full(6, 0.04))
    assert gauss["S809"] == (0.25, 1.0, 2.0)          # profile without GaussianCoeffs: code defaults
    assert polars["S809"].lift(0.0) == pytest.approx(polars["S809"].lift(0.0))
    assert R.BlockMesh(REF / "meshEps" / "system" / "blockMeshDict").n_cells == 15 * 16 * 16
    rot2, *_ = R.read_case(REF / "eps006")
    assert rot2.epsilon_user == 0.06


# --------------------------------------------------------------------------- #
# Replica versus the solver
# --------------------------------------------------------------------------- #

TOL = 1.0e-4        # observed worst relative error is ~2e-5 (six-digit CSV and debug output)


@pytest.mark.parametrize("variant", ["meshEps", "eps006", "twoBlade"])
def test_replica_reproduces_solver_debug_line(variant):
    # twoBlade: blade 2 is blade 1 turned by 180 deg (its state is not written); the CFD blades
    # are not exactly symmetric, so the bound is looser (observed ~2.4e-4)
    tol = 1.0e-3 if variant == "twoBlade" else TOL
    rep = R.validate_case(REF / variant, REF / variant / "debug.txt", REF / "off")
    assert [r["time"] for r in rep] == [0.002, 0.003, 0.004]
    for r in rep:
        assert r["tip_rel_err"] < tol
        assert r["max_corr_rel_err"] < tol
        assert r["max_element_replica"] == r["max_element_solver"]
        if variant != "eps006":
            assert r["eps_replica_tip"] == pytest.approx(r["eps_solver_tip"], rel=1e-9)     # 2 cbrt(V) * 2
        else:
            # the debug line prints projectionEpsilon(); an explicit `epsilon` overrides it
            assert r["eps_solver_tip"] == pytest.approx(0.4) and r["eps_replica_tip"] == 0.06
        assert r["tip_ux_err"] < 1e-4
    # all elements, first corrected step: on-run minus off-run relative velocity
    assert rep[0]["onoff_relative_to_max_w"] < (5.0e-3 if variant == "twoBlade" else 5.0e-4)


def solver_error(variant, switches):
    rot, blade, polars, gauss = R.read_case(REF / variant)
    mesh = R.BlockMesh(REF / variant / "system" / "blockMeshDict")
    series = R.read_element_rows(REF / variant, 1, blade.n, keep=100)
    dbg = R.parse_debug(REF / variant / "debug.txt")
    fr = R.freeze(series, rot, blade, polars, gauss, mesh, 0.003, 0.002)
    w = R.lagged_w(fr, switches)
    c = dbg[0.003]["corr"]
    return np.linalg.norm(w[-1] - c) / np.linalg.norm(c)


def test_two_blade_wake_matters():
    one = R.validate_case(REF / "meshEps", REF / "meshEps" / "debug.txt")
    rot, *_ = R.read_case(REF / "twoBlade")
    assert rot.n_blades == 2 and rot.blade_azimuth_rad[1] == pytest.approx(math.pi)
    # the second blade changes the correction by far more than the replica error
    d1 = R.parse_debug(REF / "meshEps" / "debug.txt")[0.003]["corr"]
    d2 = R.parse_debug(REF / "twoBlade" / "debug.txt")[0.003]["corr"]
    assert np.linalg.norm(d1 - d2) / np.linalg.norm(d1) > 1e-2
    assert one


def test_replica_rejects_the_wrong_switch_sets():
    assert solver_error("meshEps", R.Switches()) < TOL
    # the validation has resolving power: the deviations are far outside the tolerance
    assert solver_error("meshEps", R.Switches(smooth=False)) > 100 * TOL
    assert solver_error("meshEps", R.Switches(sweep_reverse=True)) > 0.1
    assert solver_error("meshEps", R.Switches(tip_hold=True)) > 100 * TOL


def test_inplane_reconstruction_matches_debug_relative_velocity():
    rot, blade, *_ = R.read_case(REF / "meshEps")
    series = R.read_element_rows(REF / "meshEps", 1, blade.n, keep=100)
    dbg = R.parse_debug(REF / "meshEps" / "debug.txt")
    now = R.state_at(series, 0.002)
    pos = np.stack([now["x"], now["y"], now["z"]], axis=1)
    _, e_t, rho = R.blade_frame(pos, rot)
    _, ux, ut = R.inplane_state(rot, e_t, rho, now["rel_vel_mag"], now["alpha_deg"], now["alpha_geom_deg"])
    rel = dbg[0.003]["rel"]            # the solver's tip relative velocity of step 0.002
    assert ux[-1] == pytest.approx(rel[0], abs=2e-4)
    assert ut[-1] == pytest.approx(rel @ e_t[-1], abs=2e-4)
    # blade velocity of step 0.003 = omega axis x r at the step-0.003 position
    nxt = R.state_at(series, 0.003)
    p3 = np.array([nxt["x"][-1], nxt["y"][-1], nxt["z"][-1]])
    assert dbg[0.003]["vel"] == pytest.approx(rot.omega * np.cross(rot.axis, p3), abs=1e-3)


def test_fixed_point_reproduces_a_consistent_state():
    # Frozen reference state: as-implemented one-pass correction is already (nearly) its own
    # fixed point only if the lagged state is converged; here it is the first corrected step,
    # so the fixed point must differ from it and satisfy w = f(rel0 + w).
    rot, blade, polars, gauss = R.read_case(REF / "eps006")
    mesh = R.BlockMesh(REF / "eps006" / "system" / "blockMeshDict")
    series = R.read_element_rows(REF / "eps006", 1, blade.n, keep=100)
    fr = R.freeze(series, rot, blade, polars, gauss, mesh, 0.004, 0.003)
    rel0, w_impl, res = R.evaluate(fr, [R.Switches(), R.Switches(fixed=True)])
    fp = res["b:fixed-point"]
    assert fp["residual"] < 1e-9
    assert np.abs(res["as-implemented"]["alpha"] - fr.alpha_t).max() < 1e-4     # identity by construction
    alpha, mag, ux, ut = R.apply_w(fr, rel0, fp["w"])
    cl, _ = R.coefficients(fr, alpha, mag)
    inactive = fr.rho / rot.radius < 0.5            # frozen at the solver state, as in fixed_point_w
    cl, mag = np.where(inactive, fr.cl_t, cl), np.where(inactive, fr.rel_t, mag)
    ux, ut = np.where(inactive, fr.ux_t, ux), np.where(inactive, fr.ut_t, ut)
    gamma = 0.5 * blade.chord * cl * mag
    pts, g, e, uxs, uts = R.stack_blades(fr, gamma, ux, -ut)
    again = R.trailing_correction(pts, g, e, uxs, uts, rot, R.Switches())
    assert np.abs(again - fp["w"])[~inactive].max() < 1e-8
    assert res["no-correction"]["alpha"].mean() > res["as-implemented"]["alpha"].mean()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("args", [["--help"], ["replay", "--help"], ["validate", "--help"]])
def test_cli_help(args):
    out = subprocess.run([sys.executable, str(SCRIPTS / "replayDagSorensen.py")] + args,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    assert out.returncode == 0
    assert "usage" in out.stdout


def test_cli_validate_pass_and_exit_code(tmp_path):
    base = [sys.executable, str(SCRIPTS / "replayDagSorensen.py"), "validate", "--case", str(REF / "meshEps"),
            "--debug-log", str(REF / "meshEps" / "debug.txt"), "--off-case", str(REF / "off"),
            "--out", str(tmp_path / "v.json")]
    ok = subprocess.run(base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    assert ok.returncode == 0 and "PASS" in ok.stdout
    bad = subprocess.run(base + ["--tol", "1e-9"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         universal_newlines=True)
    assert bad.returncode == 1 and "FAIL" in bad.stdout
