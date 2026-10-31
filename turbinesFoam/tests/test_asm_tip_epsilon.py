#!/usr/bin/env python
"""The Dag & Sorensen tip correction with ``epsilon 0`` on surface elements.

``epsilon 0`` makes the correction read each element's ``projectionEpsilon()``
(core width and circulation smoothing width). ``actuatorSurfaceElement`` used
to compute its mesh-based epsilon without storing it, so the member stayed at
-VGREAT, the stations were all rejected and the correction was identically
zero for ASM. ``tests/asmTipEpsilon`` is a one-blade rotor run once with
``actuatorSurfaceElement`` and once with ``actuatorLineElement``; the
``tipCorrection { debug true; }`` line reports the tip element epsilon and the
largest correction through the solver log.

The ALM run is the regression guard: the unchanged ALM path must keep a
positive epsilon and a non-zero correction.
"""

from __future__ import division, print_function

import glob
import os
import re
import shutil
import subprocess

import pytest

# Solver-driven: needs a loaded OpenFOAM and libturbinesFoam.so on the loader path
pytestmark = pytest.mark.skipif(
    not (os.environ.get("WM_PROJECT_VERSION") and shutil.which("pimpleFoam")),
    reason="OpenFOAM environment not loaded",
)

CASE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "asmTipEpsilon"
)
DEBUG_RE = re.compile(
    r"tipCorrectionDebug t=(\S+) maxCorr=(\S+) .* eps=(\S+) corr=\(([^)]*)\)"
)


def _run(case_dir, flag):
    shutil.copytree(CASE_DIR, case_dir)
    proc = subprocess.run(
        ["./Allrun", flag],
        cwd=case_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    log_path = os.path.join(case_dir, "log.pimpleFoam")
    if proc.returncode != 0:
        tail = open(log_path).readlines()[-100:] if os.path.isfile(log_path) else []
        pytest.fail("Allrun {} failed:\n{}".format(flag, "".join(tail) or proc.stdout))
    return open(log_path).read()


def _debug_lines(log):
    rows = []
    for m in DEBUG_RE.finditer(log):
        t, max_corr, eps, corr = m.groups()
        rows.append(
            (
                float(t),
                float(max_corr),
                float(eps),
                [float(c) for c in corr.split()],
            )
        )
    assert rows, "no tipCorrectionDebug line in the solver log"
    return rows


@pytest.fixture(scope="module")
def asm_log(tmp_path_factory):
    return _run(str(tmp_path_factory.mktemp("asm-eps") / "case"), "-asm")


@pytest.fixture(scope="module")
def alm_case(tmp_path_factory):
    case_dir = str(tmp_path_factory.mktemp("alm-eps") / "case")
    return case_dir, _run(case_dir, "-alm")


def test_asm_projection_epsilon_is_positive(asm_log):
    """The surface element exposes its mesh-based epsilon. The first dump
    precedes the first force projection (epsilon not yet computed), so the
    last dump is the one checked."""
    assert _debug_lines(asm_log)[-1][2] > 0.0


def test_asm_tip_correction_is_nonzero(asm_log):
    """The correction reaches the surface elements (it was exactly 0)."""
    t, max_corr, _, corr = _debug_lines(asm_log)[-1]
    assert max_corr > 0.0
    assert any(abs(c) > 0.0 for c in corr)


def test_alm_path_unchanged(alm_case):
    """ALM keeps a positive epsilon and a non-zero correction, and writes its
    element CSV (the fix did not touch the ALM path; its CSV and debug line
    were checked byte-identical against the pre-fix build)."""
    case_dir, log = alm_case
    t, max_corr, eps, corr = _debug_lines(log)[-1]
    assert eps > 0.0
    assert max_corr > 0.0
    paths = glob.glob(os.path.join(
        case_dir, "postProcessing", "actuatorLineElements", "*",
        "turbine.blade1.element5.csv",
    ))
    assert paths
