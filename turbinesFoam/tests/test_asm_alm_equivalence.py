#!/usr/bin/env python
"""Equivalence of the ASM and the ALM on the same one-blade rotor.

``actuatorSurfaceElement`` and ``actuatorLineElement`` share the blade-element
chain (inflow, polar, tip correction). On ``tests/asmTipEpsilon`` they must
return the same element state: a difference larger than the tolerance below is
an implementation defect, not model physics.

This is the guard the missing ``projectionEpsilon_`` store (V14 ASM tip
over-load, +57 % c_n at r/R 0.95) slipped past: with that defect the tip
element alpha differs by ~1.8 deg from the ALM, an order of magnitude over the
tolerance, while the fixed build agrees to ~1e-4 deg. Measure the tolerance
first, never widen it to make a run pass.
"""

from __future__ import division, print_function

import csv
import glob
import os
import shutil

import pytest

from test_asm_tip_epsilon import _run

pytestmark = pytest.mark.skipif(
    not (os.environ.get("WM_PROJECT_VERSION") and shutil.which("pimpleFoam")),
    reason="OpenFOAM environment not loaded",
)

# Per-element agreement of the last time step (measured on the fixed build:
# max |d alpha| 1e-4 deg, max |d c_n| < 5e-5; defective build: 1.8 deg, 0.03)
ALPHA_TOL_DEG = 0.05
CN_TOL_REL = 0.005


def _last_rows(case_dir):
    rows = {}
    pattern = os.path.join(
        case_dir, "postProcessing", "actuatorLineElements", "*",
        "turbine.blade1.element*.csv",
    )
    for path in sorted(glob.glob(pattern)):
        name = os.path.basename(path)
        with open(path) as handle:
            rows[name] = list(csv.DictReader(handle))[-1]
    assert rows, "no element CSV written"
    return rows


@pytest.fixture(scope="module")
def element_rows(tmp_path_factory):
    out = {}
    for flag in ("alm", "asm"):
        case_dir = str(tmp_path_factory.mktemp(flag + "-eq") / "case")
        _run(case_dir, "-" + flag)
        out[flag] = _last_rows(case_dir)
    return out


def test_same_elements_written(element_rows):
    assert sorted(element_rows["alm"]) == sorted(element_rows["asm"])


def test_element_alpha_matches_alm(element_rows):
    for name, alm in element_rows["alm"].items():
        asm = element_rows["asm"][name]
        diff = abs(float(asm["alpha_deg"]) - float(alm["alpha_deg"]))
        assert diff < ALPHA_TOL_DEG, "{}: |d alpha| = {} deg".format(name, diff)


def test_element_normal_coefficient_matches_alm(element_rows):
    for name, alm in element_rows["alm"].items():
        asm = element_rows["asm"][name]
        ref = float(alm["c_ref_n"])
        rel = abs(float(asm["c_ref_n"]) - ref) / abs(ref)
        assert rel < CN_TOL_REL, "{}: |d c_n|/c_n = {}".format(name, rel)
