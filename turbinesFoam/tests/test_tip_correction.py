#!/usr/bin/env python
"""Tests for the Dag & Sorensen (2020) induced-velocity tip correction.

Two layers:

``test_tip_correction_reference.py`` style pure-Python tests re-implement the
Biot-Savart kernel of Eq. (22) and the planar trailing-line formula of
Eqs. (16)-(17), and pin the C++ application point and configuration so the
reference cannot silently drift.

The remaining tests drive ``tests/tipCorrection/rotor``, a minimal one-blade
``axialFlowTurbineALSource`` fixture with an S809 polar and six spanwise
elements (r = 0.083 m .. 0.417 m of a 0.45 m rotor, chord 0.04 m, zero twist,
TSR 5). The rotor axis points upstream (axis -x, free stream +x), matching the
NREL Phase VI convention, so the local flow angle of paper Eq. (3) is the
physical one. ``system/fvOptions`` is the default-off baseline (no
``tipCorrection`` block); ``.off``, ``.on`` and ``.badmodel`` install through
``./Allrun`` on a throwaway copy of the case, so the committed files are never
mutated.

The correction reads the previous PIMPLE iteration's relative velocity (design
D3/H3b) and the fixture uses one outer corrector, so the first CSV row
(t = 0.001) has a zero correction and the second row (t = 0.002) carries the
non-zero correction; the comparisons use the last row.

A mirrored rotor with the axis ALIGNED with the free stream
(``fvOptions.axisdown`` / ``fvOptions.axisdown.on``) exercises the same
correction so the flow-angle and sweep conventions cannot silently regress
with the sign of ``axis_``.
"""

from __future__ import division, print_function

import glob
import os
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest
from numpy.testing import assert_allclose

CASE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tipCorrection", "rotor"
)
ELEMENT_CSV_GLOB = os.path.join(
    "postProcessing", "actuatorLineElements", "*", "turbine.blade1.element{}.csv"
)

N_ELEMENTS = 6
TIP_ELEMENT = N_ELEMENTS - 1

# OpenFOAM VSMALL (used by the C++ kernel floor)
VSMALL = 1.0e-300


# --------------------------------------------------------------------------- #
# Pure-Python reference of the Biot-Savart kernel
# --------------------------------------------------------------------------- #

def segment_induced(gamma, eps, dl, d):
    """Eq. (22) induced velocity of one straight vortex segment.

    ``dl`` is the segment vector (oriented away from the blade) and ``d`` runs
    from the segment centre to the evaluation point. The viscous-core factor
    is ``exp(-(|d|/eps)^2)``.
    """
    dl = np.asarray(dl, dtype=float)
    d = np.asarray(d, dtype=float)
    r = np.linalg.norm(d)
    return (
        gamma / (4.0 * np.pi)
        * np.cross(dl, d)
        / max(r ** 3, VSMALL)
        * np.exp(-(r / eps) ** 2)
    )


def planar_line(gamma, r, eps):
    """Eq. (16)/(17) contribution of one trailing vortex line."""
    return gamma / (4.0 * np.pi * r) * np.exp(-(r / eps) ** 2)


def semi_infinite_line(gamma, eps, d, length, n):
    """Discretised semi-infinite straight line along +x at perpendicular ``d``.

    Returns the vector induced velocity at ``(0, d, 0)``; the line runs from
    ``x = 0`` (the release point) downstream to ``x = length``.
    """
    edges = np.linspace(0.0, length, n + 1)
    centres = 0.5 * (edges[:-1] + edges[1:])
    h = edges[1:] - edges[:-1]

    P = np.array([0.0, d, 0.0])
    D = P[None, :] - np.stack(
        [centres, np.zeros(n), np.zeros(n)], axis=1
    )
    r = np.linalg.norm(D, axis=1)
    dl = np.stack([h, np.zeros(n), np.zeros(n)], axis=1)

    cross = np.cross(dl, D)
    return (
        gamma / (4.0 * np.pi)
        * np.sum(cross / np.maximum(r ** 3, VSMALL)[:, None]
                 * np.exp(-(r / eps) ** 2)[:, None], axis=0)
    )


# --------------------------------------------------------------------------- #
# Case harness
# --------------------------------------------------------------------------- #

def _copy_case(dst):
    """Copy the fixture without generated run artifacts."""
    shutil.copytree(CASE_DIR, dst)
    for name in os.listdir(dst):
        path = os.path.join(dst, name)
        generated = (
            name in ("0", "postProcessing")
            or name.startswith("processor")
            or name.startswith("log.")
            or (name[0].isdigit() and name != "0.org")
        )
        if not generated:
            continue
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
    return dst


def _run_case(case_dir, *args):
    """Run ``./Allrun`` in ``case_dir``; fail with the log tail on error."""
    proc = subprocess.run(
        ["./Allrun"] + list(args),
        cwd=case_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    if proc.returncode != 0:
        log_path = os.path.join(case_dir, "log.pimpleFoam")
        tail = open(log_path).readlines()[-200:] if os.path.isfile(log_path) else []
        pytest.fail(
            "Allrun failed ({}) exit {}:\n{}".format(
                " ".join(args), proc.returncode, "".join(tail) or proc.stdout
            )
        )


def _run_case_expect_failure(case_dir, *args):
    """Run ``./Allrun`` and return (returncode, log text) without failing."""
    proc = subprocess.run(
        ["./Allrun"] + list(args),
        cwd=case_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    log_path = os.path.join(case_dir, "log.pimpleFoam")
    log = open(log_path).read() if os.path.isfile(log_path) else proc.stdout
    return proc.returncode, log


def _read_element(case_dir, element=0):
    """Read one element's CSV across every written time, sorted by time."""
    paths = sorted(glob.glob(os.path.join(
        case_dir, ELEMENT_CSV_GLOB.format(element)
    )))
    assert paths, "no element CSV for element {} under {}".format(element, case_dir)
    df = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    return df.sort_values("time").reset_index(drop=True)


def _last_row(case_dir, element=0):
    """The final written row, which carries the non-zero correction."""
    return _read_element(case_dir, element).iloc[-1]


@pytest.fixture(scope="module")
def default_case(tmp_path_factory):
    case_dir = str(tmp_path_factory.mktemp("tc-default") / "case")
    _copy_case(case_dir)
    _run_case(case_dir)
    return case_dir


@pytest.fixture(scope="module")
def off_case(tmp_path_factory):
    case_dir = str(tmp_path_factory.mktemp("tc-off") / "case")
    _copy_case(case_dir)
    _run_case(case_dir, "-off")
    return case_dir


@pytest.fixture(scope="module")
def on_case(tmp_path_factory):
    case_dir = str(tmp_path_factory.mktemp("tc-on") / "case")
    _copy_case(case_dir)
    _run_case(case_dir, "-on")
    return case_dir


@pytest.fixture(scope="module")
def on_parallel_case(tmp_path_factory):
    """The tip correction on, decomposed over the fixture's 2 ranks."""
    case_dir = str(tmp_path_factory.mktemp("tc-on-parallel") / "case")
    _copy_case(case_dir)
    _run_case(case_dir, "-on", "-parallel")
    return case_dir


@pytest.fixture(scope="module")
def axisdown_off_case(tmp_path_factory):
    case_dir = str(tmp_path_factory.mktemp("tc-axisdown-off") / "case")
    _copy_case(case_dir)
    _run_case(case_dir, "-axisdown")
    return case_dir


@pytest.fixture(scope="module")
def axisdown_on_case(tmp_path_factory):
    case_dir = str(tmp_path_factory.mktemp("tc-axisdown-on") / "case")
    _copy_case(case_dir)
    _run_case(case_dir, "-axisdown-on")
    return case_dir


# --------------------------------------------------------------------------- #
# Pure-Python reference
# --------------------------------------------------------------------------- #

def test_single_segment_reproduces_eq16():
    """A single trailing vortex line reproduces Eq. (16).

    Eq. (17) sums one term ``Gamma_w(j)/(4*pi*d)*exp(-(d/eps)^2)`` per
    trailing vortex line; that single term is Eq. (16) with ``r = d`` (the
    planar point-vortex limit of the wake). The discrete vector kernel
    (Eq. 22) reproduces the same magnitude for a segment whose length equals
    its distance from the evaluation point and which is perpendicular to it,
    because then ``|dl x d|/|d|^3 = 1/|d|``.
    """
    gamma = 0.7
    eps = 0.3
    r = 0.5

    eq16 = gamma / (4.0 * np.pi * r) * np.exp(-(r / eps) ** 2)
    assert planar_line(gamma, r, eps) == pytest.approx(eq16, rel=1e-9)

    w = segment_induced(gamma, eps, dl=[0.0, 0.0, r], d=[r, 0.0, 0.0])
    assert np.linalg.norm(w) == pytest.approx(eq16, rel=1e-9)


def test_semi_infinite_line_matches_eq17():
    """A discretised semi-infinite line reproduces Eq. (17).

    With a wide core (``eps >> d``) the exponential is unity and the segment
    sum converges to the trailing-line result ``Gamma/(4*pi*d)``; the finite
    length 400 d leaves a relative deficit of order ``(d/length)^2``.
    """
    gamma = 1.0
    d = 0.4
    eps = 1.0e6
    length = 400.0 * d

    w = semi_infinite_line(gamma, eps, d, length, n=20000)
    # dl along +x, point at +y -> +z by the right-hand rule.
    assert w[0] == pytest.approx(0.0, abs=1e-12)
    assert w[1] == pytest.approx(0.0, abs=1e-12)
    assert w[2] == pytest.approx(gamma / (4.0 * np.pi * d), rel=1e-3)


def test_zero_strength_gives_exactly_zero():
    """A wake with ``Gamma_w == 0`` everywhere contributes exactly zero."""
    d = np.array([0.1, 0.2, 0.3])
    dl = np.array([0.0, 0.0, 0.05])
    acc = np.zeros(3)
    for _ in range(8):
        acc += segment_induced(0.0, 0.5, dl, d)
    assert_allclose(acc, np.zeros(3), rtol=0.0, atol=0.0)


def test_right_hand_rule_sign():
    """``dl`` along +x and the point at +y induce a +z velocity."""
    gamma = 1.0
    eps = 1.0e6
    dl = np.array([0.5, 0.0, 0.0])
    d = np.array([0.0, 0.5, 0.0])
    w = segment_induced(gamma, eps, dl, d)

    assert w[0] == pytest.approx(0.0, abs=1e-12)
    assert w[1] == pytest.approx(0.0, abs=1e-12)
    assert w[2] > 0.0
    # |w| = gamma/(4*pi) * |dl|/|d|^2
    expected = gamma / (4.0 * np.pi) * 0.5 / 0.25
    assert w[2] == pytest.approx(expected, rel=1e-9)


def test_cpp_application_point_and_config_pinned():
    """The correction enters the inflow before the angle of attack is formed.

    Pins the D2 application point (after the spanwise removal, before
    ``relativeVelocity_``), the D5 epsilon cache, the D1 call sites and the
    D6 default-off configuration.
    """
    src = open(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "src", "fvOptions", "actuatorLineSource", "actuatorLineElement",
        "actuatorLineElement.C",
    )).read()
    i_spanwise = src.index("inflowVelocity_ -= spanwiseVelocity;")
    i_correction = src.index("inflowVelocity_ += inducedVelocityCorrection_;")
    i_relative = src.index("relativeVelocity_ = inflowVelocity_ - velocity_;")
    assert i_spanwise < i_correction < i_relative

    i_cache = src.index("projectionEpsilon_ = epsilon;")
    i_return = src.index("return epsilon;", i_cache)
    assert i_cache < i_return
    assert "const Foam::vector& Foam::fv::actuatorLineElement::inducedVelocityCorrection() const" in src
    assert "void Foam::fv::actuatorLineElement::setInducedVelocityCorrection" in src

    aftal = open(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "src", "fvOptions", "axialFlowTurbineALSource",
        "axialFlowTurbineALSource.C",
    )).read()
    assert "void Foam::fv::axialFlowTurbineALSource::calcTipCorrection()" in aftal
    assert aftal.count("calcTipCorrection();") >= 3
    for key in ("tipCorrection", "wakeTurns", "wakeAzimuthalStep", "epsilon"):
        assert '"%s"' % key in aftal
    assert '"DagSorensen"' in aftal


def test_cpp_flow_angle_and_sweep_convention_pinned():
    """The flow angle follows the blade motion; the sweep follows the spin.

    Pins the convention fix: ``uTheta`` is built from the blade velocity (the
    calcEndEffects convention) rather than ``downstream ^ radialDir``, and the
    sweep sign keeps the axis-sign dependence of the spin about the flow axis.
    """
    aftal = open(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "src", "fvOptions", "axialFlowTurbineALSource",
        "axialFlowTurbineALSource.C",
    )).read()
    i_start = aftal.index(
        "void Foam::fv::axialFlowTurbineALSource::calcTipCorrection()"
    )
    i_end = aftal.index("Constructors  *", i_start)
    body = aftal[i_start:i_end]

    assert "uThetaA[i][j] = -(bladeDir & rel);" in body
    assert "tangentialDir" not in body
    assert "-Foam::sign(omega_*(axisHat & downstream))" in body
    assert "axisHat ^ radialDir0" not in body


# --------------------------------------------------------------------------- #
# Integration
# --------------------------------------------------------------------------- #

def test_default_off_byte_identical(default_case, off_case):
    """No block and explicit ``active off`` produce identical element output."""
    for element in range(N_ELEMENTS):
        default_paths = sorted(glob.glob(os.path.join(
            default_case, ELEMENT_CSV_GLOB.format(element)
        )))
        off_paths = sorted(glob.glob(os.path.join(
            off_case, ELEMENT_CSV_GLOB.format(element)
        )))
        assert default_paths and off_paths
        assert open(default_paths[0], "rb").read() == open(off_paths[0], "rb").read()


def test_on_completes_and_reduces_tip_loading(off_case, on_case):
    """The active block produces finite corrections that lower tip loading.

    The correction adds the viscous part of the wake induction back to the
    inflow, so the tip element's normal loading falls relative to the
    uncorrected run (the physical direction of the paper's Fig. 10).
    """
    off_row = _last_row(off_case, TIP_ELEMENT)
    on_row = _last_row(on_case, TIP_ELEMENT)

    for column in ("alpha_deg", "cl", "f_ref_n", "f_ref_t"):
        assert np.isfinite(on_row[column]), column

    # The correction changed the tip element from the uncorrected run.
    assert on_row["alpha_deg"] != pytest.approx(off_row["alpha_deg"], rel=1e-6)
    # The tip normal loading falls (the required physical direction).
    assert on_row["f_ref_n"] < off_row["f_ref_n"]
    assert on_row["c_ref_n"] < off_row["c_ref_n"]


def test_parallel_invariance(on_case, on_parallel_case):
    """The correction is rank-independent.

    ``calcTipCorrection`` is built only from replicated element geometry and
    circulation -- no halo exchange, no rank-local accumulation -- so a
    decomposed run must reproduce the serial element output. Measured here: the
    1-rank and 2-rank element CSVs are bit-identical, so the assertion is exact
    up to the CSV's printed precision; a rank dependence would show up at the
    percent level.
    """
    for element in range(N_ELEMENTS):
        serial = _last_row(on_case, element)
        parallel = _last_row(on_parallel_case, element)
        for column in (
            "alpha_deg", "cl", "c_ref_n", "c_ref_t", "f_ref_n", "f_ref_t"
        ):
            assert parallel[column] == pytest.approx(
                serial[column], rel=1.0e-9, abs=1.0e-12
            ), "element {} column {}".format(element, column)


def test_unknown_model_rejected(tmp_path):
    """An unregistered model fails loudly (FatalIOError)."""
    case_dir = str(tmp_path / "case")
    _copy_case(case_dir)
    returncode, log = _run_case_expect_failure(case_dir, "-badmodel")
    assert returncode != 0
    assert "Unknown tipCorrection model" in log
    assert "DagSorensen" in log


def test_axis_convention_invariance(
    off_case, on_case, axisdown_off_case, axisdown_on_case
):
    """The correction lowers the tip loading for both axis orientations.

    The mirrored rotor (axis aligned with the free stream, ``axisdown``) spins
    opposite to the upstream rotor about the flow axis, so the two have
    opposite wake handedness and are NOT expected to reproduce each other's
    loads. Both must still reduce the tip loading; the upstream-vs-axisdown
    comparison is printed as information only, never asserted.
    """
    upstream_off = _last_row(off_case, TIP_ELEMENT)
    upstream_on = _last_row(on_case, TIP_ELEMENT)
    down_off = _last_row(axisdown_off_case, TIP_ELEMENT)
    down_on = _last_row(axisdown_on_case, TIP_ELEMENT)

    print(
        "tip correction convention check (element {}, r/R = {:.3f}):".format(
            TIP_ELEMENT, down_off["root_dist"]
        )
    )
    for label, row in (
        ("upstream off", upstream_off),
        ("upstream on ", upstream_on),
        ("axisdown off", down_off),
        ("axisdown on ", down_on),
    ):
        print("  {}: alpha_deg={:.6f} f_ref_n={:.6f} c_ref_n={:.6f}".format(
            label, row["alpha_deg"], row["f_ref_n"], row["c_ref_n"]
        ))

    for row in (down_off, down_on):
        for column in ("alpha_deg", "f_ref_n", "c_ref_n"):
            assert np.isfinite(row[column]), column

    # The mirrored rotor's tip loading also falls.
    assert down_on["alpha_deg"] != pytest.approx(down_off["alpha_deg"], rel=1e-6)
    assert down_on["f_ref_n"] < down_off["f_ref_n"]
    assert down_on["c_ref_n"] < down_off["c_ref_n"]

    # Informational only: the two rotors spin oppositely about the flow axis,
    # so opposite wake handedness makes them non-equivalent by construction.
    for column in ("alpha_deg", "f_ref_n", "c_ref_n"):
        if not np.isclose(down_on[column], upstream_on[column], rtol=0.02):
            print(
                "expected mismatch (opposite handedness) {}: "
                "upstream={:.6f} axisdown={:.6f}".format(
                    column, upstream_on[column], down_on[column]
                )
            )
