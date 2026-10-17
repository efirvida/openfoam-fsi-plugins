# SPDX-License-Identifier: GPL-3.0-or-later
"""FLOWUnsteady station loads (`validation/phaseVI/scripts/compareFlowUnsteadyStations.py`).

Pins the reading of FLOWVLM's legacy ASCII `*_vlm.<step>.vtk`: lattice cells
only (the control-point vertex cells repeat the data), the plane-of-rotation
decomposition (axis +x, wind along -x so thrust is -Ftot_x; tangential sign
such that extraction gives positive torque), the inflow angle from the lift
direction, and the blade integrals used as the units check.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "validation" / "phaseVI" / "scripts"
sys.path.insert(0, str(SCRIPTS))
tool = pytest.importorskip("compareFlowUnsteadyStations")

PHI = math.radians(20.0)


def _vtk(path: Path, radii, ftot, lift, axis="z", sense=1.0) -> Path:
    """Blade along +`axis`; LE at x=-0.1, TE at x=+0.1; one lattice per span."""
    n = len(radii) - 1

    def point(r, x):
        return (x, 0.0, r) if axis == "z" else (x, r, 0.0)

    le = [point(r, -0.1) for r in radii]
    te = [point(r, 0.1) for r in radii]
    cp = [point(0.5 * (a + b), 0.05) for a, b in zip(radii, radii[1:])]
    points = le + te + cp
    lines = ["# vtk DataFile Version 4.0", "[MyVLM domain - lattices] ", "ASCII",
             "DATASET UNSTRUCTURED_GRID", f"POINTS {len(points)} float"]
    lines += [" ".join(str(c) for c in p) for p in points]
    lines.append(f"CELLS {2 * n} {5 * n + 2 * n}")
    lines += [f"4 {i} {n + 1 + i} {n + 2 + i} {i + 1}" for i in range(n)]
    lines += [f"1 {2 * (n + 1) + i}" for i in range(n)]
    lines.append(f"CELL_TYPES {2 * n}")
    lines += ["9"] * n + ["1"] * n
    lines += ["", f"CELL_DATA {2 * n}", "", "SCALARS Gamma float", "LOOKUP_TABLE default"]
    lines += ["1.0"] * (2 * n)

    def tangential(t):
        # e_theta = s * (x_hat x e_r); for e_r = +z, x_hat x z_hat = -y_hat.
        return (0.0, -sense * t, 0.0) if axis == "z" else (0.0, 0.0, sense * t)

    for name, values in (("Ftot", ftot), ("L", lift)):
        lines += ["", f"VECTORS {name} float"]
        for _ in range(2):
            for fn, ft in values:
                tx, ty, tz = tangential(ft)
                lines.append(f"{-fn + tx} {ty} {tz}")
    path.write_text("\n".join(lines) + "\n")
    return path


@pytest.fixture
def blade(tmp_path):
    radii = [1.0, 2.0, 3.0, 4.0]
    ftot = [(100.0, 10.0), (200.0, 20.0), (300.0, 30.0)]
    lift = [(math.cos(PHI), math.sin(PHI))] * 3
    return _vtk(tmp_path / "x_Rotor_Blade1_vlm.72.vtk", radii, ftot, lift)


def test_sections_are_lattice_cells_in_plane_of_rotation(blade):
    sections = tool.read_sections(blade)
    assert [round(s["r"], 12) for s in sections] == [1.5, 2.5, 3.5]
    assert [s["dr"] for s in sections] == pytest.approx([1.0, 1.0, 1.0])
    assert [s["fn"] for s in sections] == pytest.approx([100.0, 200.0, 300.0])
    assert [s["ft"] for s in sections] == pytest.approx([10.0, 20.0, 30.0])


def test_inflow_angle_is_the_lift_direction(blade):
    for section in tool.read_sections(blade):
        assert section["phi_lift_deg"] == pytest.approx(20.0)


def test_tangential_sign_follows_extraction_for_either_rotation(tmp_path):
    radii = [1.0, 2.0, 3.0]
    ftot = [(50.0, 5.0), (60.0, 6.0)]
    lift = [(1.0, 0.2)] * 2
    path = _vtk(tmp_path / "y_vlm.0.vtk", radii, ftot, lift, axis="y", sense=-1.0)
    sections = tool.read_sections(path)
    assert [s["ft"] for s in sections] == pytest.approx([5.0, 6.0])
    assert sections[0]["phi_lift_deg"] == pytest.approx(math.degrees(math.atan2(0.2, 1.0)))


def test_blade_integrals_are_thrust_and_torque(blade):
    thrust, torque = tool.blade_integrals(tool.read_sections(blade))
    assert thrust == pytest.approx(600.0)
    assert torque == pytest.approx(10.0 * 1.5 + 20.0 * 2.5 + 30.0 * 3.5)


def test_station_values_interpolate_in_r_over_r(blade):
    sections = tool.read_sections(blade)
    value = tool.at_station(sections, 2.0 / 5.029 * 1.0 + 0.0, "fn", radius=5.029)
    assert value == pytest.approx(150.0)
