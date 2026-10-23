# SPDX-License-Identifier: GPL-3.0-or-later
"""Frame angle and twist of `validation/phaseVI/scripts/compareSectionLoads.py`.

The element CSV columns are referenced to the plane of rotation with the inflow
angle phi: `c_ref_n = cl cos(phi) + cd sin(phi)`, `c_ref_t = cl sin(phi) - cd cos(phi)`.
The twist `phi - alpha` is geometry, so it must not depend on the polar (cd/cl)
nor on how the rows are averaged.
"""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "validation" / "phaseVI" / "scripts"
sys.path.insert(0, str(SCRIPTS))
compareSectionLoads = pytest.importorskip("compareSectionLoads")


def row(time, phi_deg, alpha_deg, cl, cd):
    phi = math.radians(phi_deg)
    return dict(
        time=time, root_dist=0.5, alpha_deg=alpha_deg, alpha_geom_deg=alpha_deg,
        cl=cl, cd=cd,
        c_ref_n=cl * math.cos(phi) + cd * math.sin(phi),
        c_ref_t=cl * math.sin(phi) - cd * math.cos(phi),
        f_ref_n=1.0, f_ref_t=1.0,
    )


def write_element(root, rows):
    directory = root / "postProcessing/actuatorLineElements/0"
    directory.mkdir(parents=True)
    with open(directory / "turbine.blade1.element0.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.mark.parametrize("ratio", [0.01, 0.3])
@pytest.mark.parametrize("phi_deg, alpha_deg", [(12.0, 8.0), (25.0, -3.0), (40.0, 22.0)])
def test_angle_from_pair_recovers_phi_independent_of_the_polar(ratio, phi_deg, alpha_deg):
    cl = 1.1
    sample = row(0.0, phi_deg, alpha_deg, cl, ratio * cl)
    phi = compareSectionLoads.angle_from_pair(
        sample["c_ref_n"], sample["c_ref_t"], sample["cl"], sample["cd"])
    assert math.degrees(phi) == pytest.approx(phi_deg, abs=1e-9)


def test_angle_from_pair_is_nan_for_a_null_coefficient_pair():
    assert math.isnan(compareSectionLoads.angle_from_pair(0.0, 0.0, 0.0, 0.0))


@pytest.mark.parametrize("ratio", [0.01, 0.3])
def test_sim_profile_twist_is_independent_of_cd_at_fixed_geometry(tmp_path, ratio):
    rows = [row(t, 20.0, 6.0, 1.0, ratio) for t in (1.0, 2.0, 3.0)]
    write_element(tmp_path, rows)
    profile, dropped = compareSectionLoads.sim_profile(tmp_path, 0.0, 10.0)
    assert dropped == 0
    assert profile[0][6] == pytest.approx(14.0, abs=1e-9)


@pytest.mark.parametrize("ratio", [0.01, 0.3])
def test_sim_profile_twist_is_the_mean_of_row_twists_when_phi_varies(tmp_path, ratio):
    cases = [(10.0, 4.0), (30.0, 6.0), (50.0, 5.0)]
    rows = [row(float(i), phi, alpha, 1.2, 1.2 * ratio) for i, (phi, alpha) in enumerate(cases)]
    write_element(tmp_path, rows)
    profile, _ = compareSectionLoads.sim_profile(tmp_path, 0.0, 10.0)
    assert profile[0][6] == pytest.approx(sum(p - a for p, a in cases) / 3, abs=1e-9)
    assert profile[0][4] == pytest.approx(sum(p for p, _ in cases) / 3, abs=1e-9)
