#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
"""Opt-in near-tip virtual-camber correction of the actuator line (F_Cl only).

Trigaux, Villeneuve, Dumas & Winckelmans (2024, JFM 989 A1; thesis App. C):
``cl *= (1 - F_Cl((d_tip/c)_eff))`` per element, with the effective tip
distance ``(d_tip/c)_eff = int_r^R dr/c(r)`` and the committed table
``validation/phaseVI/data/near-tip-functions/trigaux2024_tableC.csv``.

``tests/nearTipCorrectionCase`` is a one-blade rotor (chord 0.06 -> 0.03 m,
six elements) run for two steps on a frozen uniform inflow:

* no dictionary, ``active off`` and the pre-fix library give the same cl;
* ``active on``: the tip element cl is ``(1 - F_Cl)`` times the baseline cl,
  the root element (d/c beyond the table) is unchanged, and the C++ d/c_eff
  and F_Cl equal ``scripts/applyNearTipFunctions.py`` for the same geometry;
* drag is untouched (F_alpha_e is not applied).

The solver tests need a loaded OpenFOAM and ``libturbinesFoam.so`` on the
loader path; the Python-only checks below always run.
"""

from __future__ import division, print_function

import csv
import glob
import math
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
CASE_DIR = os.path.join(HERE, "nearTipCorrectionCase")
PHASEVI = os.path.join(os.path.dirname(HERE), "validation", "phaseVI")
TABLE = os.path.join(PHASEVI, "data", "near-tip-functions", "trigaux2024_tableC.csv")
BLADE = os.path.join(PHASEVI, "data", "geometry", "phaseVI_blade.csv")
sys.path.insert(0, os.path.join(PHASEVI, "scripts"))
sys.path.insert(0, os.path.join(PHASEVI, "tools"))

import applyNearTipFunctions as nt  # noqa: E402

needs_solver = pytest.mark.skipif(
    not (os.environ.get("WM_PROJECT_VERSION") and shutil.which("pimpleFoam")),
    reason="OpenFOAM environment not loaded",
)

# Test geometry: elementData rows (r, chord), six elements between 0.05 and 0.45 m
R_ROOT, C_ROOT, R_TIP, C_TIP, N_ELEM = 0.05, 0.06, 0.45, 0.03, 6
ELEM_LINE = re.compile(
    r"element (\d+) \(d/c\)_eff = (\S+) F_Cl = (\S+)"
)
TOL_REL = 1e-5  # the log and CSV print six significant digits


def element_radii():
    dr = (R_TIP - R_ROOT) / N_ELEM
    return [R_ROOT + (i + 0.5) * dr for i in range(N_ELEM)]


def python_reference():
    """[(d/c_eff, F_Cl)] per element from applyNearTipFunctions.py."""
    blade = [(R_ROOT, C_ROOT), (R_TIP, C_TIP)]
    rows = nt.read_table(nt.Path(TABLE))[("3D", 0.25)]
    out = []
    for r in element_radii():
        d = nt.effective_distance(blade, r, radius=R_TIP)
        out.append((d, nt.interp_functions(rows, d)[1] if d <= rows[-1][0] else 0.0))
    return out


def _run(flag, tmp_path):
    case = str(tmp_path / "case")
    shutil.copytree(CASE_DIR, case)
    env = dict(os.environ, NEAR_TIP_TABLE=TABLE)
    proc = subprocess.run(
        ["./Allrun", flag],
        cwd=case,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    log_path = os.path.join(case, "log.pimpleFoam")
    log = open(log_path).read() if os.path.isfile(log_path) else ""
    if proc.returncode != 0:
        pytest.fail("Allrun {} failed:\n{}".format(flag, (log or proc.stdout)[-4000:]))
    return case, log


def _element_rows(case, element):
    paths = glob.glob(os.path.join(
        case, "postProcessing", "actuatorLineElements", "*",
        "turbine.blade1.element{}.csv".format(element),
    ))
    assert paths, "no element CSV for element {}".format(element)
    with open(paths[0]) as stream:
        return list(csv.DictReader(stream))


def _first_step(case, element):
    """CSV row of the first step (frozen uniform inflow)."""
    rows = _element_rows(case, element)
    return rows[0]


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    out = {}
    for flag in ("-off", "-offblock", "-on", "-twocol"):
        out[flag] = _run(flag, tmp_path_factory.mktemp("neartip" + flag.strip("-")))
    return out


# --------------------------------------------------------------- python-only

def test_python_reference_tip_and_root_regions():
    """The test geometry has one tip element inside the table and a root far outside."""
    ref = python_reference()
    assert ref[-1][0] < 1.5 and ref[-1][1] > 0.1
    assert ref[0][0] > 3.5 and ref[0][1] == 0.0


def test_phasevi_effective_distance_values():
    """The Python tool the C++ reproduces gives 2.4885 / 0.6834 at r/R 0.80 / 0.95."""
    blade = nt.read_blade(nt.Path(BLADE))
    assert nt.effective_distance(blade, 0.80 * nt.RADIUS_M) == pytest.approx(2.4885, abs=5e-4)
    assert nt.effective_distance(blade, 0.95 * nt.RADIUS_M) == pytest.approx(0.6834, abs=5e-4)


def _generate(tmp_path, name, *flags):
    case = tmp_path / name
    result = subprocess.run(
        [sys.executable, os.path.join(PHASEVI, "tools", "generate_case.py"),
         "--case-dir", str(case), *flags],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return case


def _tree(case):
    return {str(p.relative_to(case)): p.read_bytes()
            for p in sorted(case.rglob("*")) if p.is_file()}


def test_renderer_default_is_on_and_flag_off_removes_exactly_the_block(tmp_path):
    """No flag and ``--near-tip-correction on`` render the same files (v1.4 default); ``off``
    drops the table and the ``nearTipCorrection`` block and nothing else."""
    base = _tree(_generate(tmp_path, "base"))
    on = _tree(_generate(tmp_path, "on", "--near-tip-correction", "on"))
    off = _tree(_generate(tmp_path, "off", "--near-tip-correction", "off"))
    assert on == base
    assert b"nearTipCorrection" not in off["system/fvOptions.ALM"]
    assert set(base) - set(off) == {"system/trigaux2024_tableC.csv"}
    assert set(off) <= set(base)
    changed = {k for k in off if off[k] != base[k]}
    assert changed == {"system/fvOptions.ALM", "system/fvOptions.ASM", "system/fvOptions.ASM-MESH"}
    for name in changed:
        text = base[name].decode()
        assert (
            "        nearTipCorrection\n        {\n            active on;\n"
            "            model TrigauxVirtualCamber;\n"
            "            table \"system/trigaux2024_tableC.csv\";\n"
            "            kernel \"3D\";\n            sigmaOverC 0.25;\n        }"
        ) in text
        # nothing else moved: removing the block restores the off render
        assert text.replace(
            text[text.index("\n\n        nearTipCorrection"):
                 text.index("}", text.index("sigmaOverC")) + 1], ""
        ) == off[name].decode()


# --------------------------------------------------------------- solver tests

@needs_solver
def test_off_variants_have_identical_element_output(runs):
    """No dictionary and ``active off`` give byte-identical element CSVs."""
    for i in range(N_ELEM):
        a = open(os.path.join(runs["-off"][0], "postProcessing", "actuatorLineElements",
                              "0", "turbine.blade1.element{}.csv".format(i))).read()
        b = open(os.path.join(runs["-offblock"][0], "postProcessing", "actuatorLineElements",
                              "0", "turbine.blade1.element{}.csv".format(i))).read()
        assert a == b
    assert "near_tip" not in a  # default output columns are unchanged


@needs_solver
def test_on_cpp_matches_python_effective_distance(runs):
    """The solver's (d/c)_eff and F_Cl per element equal the Python tool."""
    found = {int(i): (float(d), float(f)) for i, d, f in ELEM_LINE.findall(runs["-on"][1])}
    assert sorted(found) == list(range(N_ELEM)), "no per-element startup print"
    for i, (d_ref, f_ref) in enumerate(python_reference()):
        assert found[i][0] == pytest.approx(d_ref, rel=TOL_REL)
        assert found[i][1] == pytest.approx(f_ref, abs=1e-6)
        row = _first_step(runs["-on"][0], i)
        assert float(row["near_tip_d_over_c"]) == pytest.approx(d_ref, rel=TOL_REL)
        assert float(row["near_tip_f_cl"]) == pytest.approx(f_ref, abs=1e-6)


@needs_solver
def test_on_tip_element_cl_ratio_is_one_minus_fcl(runs):
    """First step, frozen inflow: cl_on / cl_off = 1 - F_Cl at the tip element."""
    d_ref, f_ref = python_reference()[-1]
    assert f_ref > 0.1
    off = _first_step(runs["-off"][0], N_ELEM - 1)
    on = _first_step(runs["-on"][0], N_ELEM - 1)
    assert float(on["cl"]) / float(off["cl"]) == pytest.approx(1.0 - f_ref, rel=1e-5)
    # Drag is not corrected; the angle of attack is unchanged
    assert float(on["cd"]) == pytest.approx(float(off["cd"]), rel=1e-9)
    assert float(on["alpha_deg"]) == pytest.approx(float(off["alpha_deg"]), rel=1e-9)


@needs_solver
def test_on_interior_element_is_unchanged(runs):
    """An element with (d/c)_eff beyond the table keeps its cl (< 1e-6 relative)."""
    off = _first_step(runs["-off"][0], 0)
    on = _first_step(runs["-on"][0], 0)
    assert float(on["near_tip_f_cl"]) == 0.0
    assert float(on["cl"]) == pytest.approx(float(off["cl"]), rel=1e-6)


@needs_solver
def test_two_column_table_is_interpolated_linearly(runs):
    """A two-column d/c, F_Cl file is read; F_Cl is 0 beyond its last row."""
    found = {int(i): (float(d), float(f)) for i, d, f in ELEM_LINE.findall(runs["-twocol"][1])}
    pts = [(0.0, 0.0), (1.0, 0.2), (2.0, 0.1), (3.0, 0.0)]

    def expect(d):
        if d >= pts[-1][0]:
            return 0.0
        for (d1, f1), (d2, f2) in zip(pts, pts[1:]):
            if d1 <= d <= d2:
                return f1 + (d - d1) / (d2 - d1) * (f2 - f1)

    for i, (d_ref, _) in enumerate(python_reference()):
        assert found[i][1] == pytest.approx(expect(d_ref), abs=1e-6)
