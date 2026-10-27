# SPDX-License-Identifier: GPL-3.0-or-later
"""T4/B1: the ASM+mesh blade surface follows the pitch reference of its elements.

The surface sampler places the STL on the reference chord *before* pitch and applies no
element pitch, so the section chord angle baked into the STL has to equal the element
chord angle `SIGMA * turbine_pitch` (elementData column 6) at every airfoil station, under
both `--pitch-reference` values and on both the committed-table and `--blade-dz` paths.
The measured chord is the LE-TE chord (farthest point pair of each section).
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
import subprocess
import sys
from pathlib import Path

import pytest

TURBINESFOAM = Path(__file__).resolve().parents[1]
PACKAGE = TURBINESFOAM / "validation" / "phaseVI"
TOOLS = PACKAGE / "tools"
GEOMETRY = TURBINESFOAM / "geometry"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(GEOMETRY / "src"))

from blade_phasevi import AIRFOIL_RADIUS, SIGMA  # noqa: E402
from case_config import DEFAULT_CONFIG, load_config  # noqa: E402
from element_data import blade_element_rows  # noqa: E402

#: Section chord angle tolerance [deg]. The farthest-pair chord of the thick root-most
#: airfoil section is biased by up to 0.158 deg against the nominal LE-TE chord (a profile
#: property, identical under both references); the defect being pinned is 1.815 deg.
TOLERANCE_DEG = 0.25
#: Tolerance of the reference-to-reference difference, where that bias cancels.
DIFFERENCE_TOLERANCE_DEG = 0.01


def loft(out_dir: Path, *args: str) -> Path:
    subprocess.run(
        [sys.executable, str(TOOLS / "make_equispaced_blade.py"), "--out-dir", str(out_dir), *args],
        check=True, capture_output=True, text=True,
    )
    return out_dir / "phaseVI_blade.stl"


def sections(stl: Path) -> dict[float, list[tuple[float, float]]]:
    data = stl.read_bytes()
    count = struct.unpack("<I", data[80:84])[0]
    out: dict[float, set[tuple[float, float]]] = {}
    for i in range(count):
        record = struct.unpack("<12fH", data[84 + 50 * i: 134 + 50 * i])
        for k in range(3):
            x, y, z = record[3 + 3 * k: 6 + 3 * k]
            out.setdefault(round(z, 6), set()).add((x, y))
    return {z: sorted(points) for z, points in out.items()}


def chord_angle_deg(points: list[tuple[float, float]]) -> float:
    """Generation-frame rotation about +z of the TE -> LE chord (0 deg = +y)."""
    best = max(((a, b) for a in points for b in points), key=lambda p: math.dist(*p))
    (x0, y0), (x1, y1) = best
    dx, dy = x1 - x0, y1 - y0
    if dy < 0.0:
        dx, dy = -dx, -dy
    return math.degrees(math.atan2(-dx, dy))


def element_angles(reference: str, dz: float | None) -> dict[float, float]:
    cfg = load_config(DEFAULT_CONFIG)
    cfg["turbine"]["pitch_reference"] = reference
    if dz:
        cfg["turbine"]["blade_dz"] = dz
    return {round(row[1], 6): SIGMA * row[5] for row in blade_element_rows(cfg) if row[1] >= AIRFOIL_RADIUS}


def wrap(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


@pytest.mark.parametrize("reference", ["twist-zero", "tip"])
@pytest.mark.parametrize("dz", [None, 0.05])
def test_surface_sections_match_element_chord_angle(tmp_path, reference, dz):
    args = ["--pitch-reference", reference] + (["--dz", str(dz)] if dz else [])
    measured = sections(loft(tmp_path, *args))
    expected = element_angles(reference, dz)
    assert expected
    for radius, angle in expected.items():
        assert abs(wrap(chord_angle_deg(measured[radius]) - angle)) < TOLERANCE_DEG, (reference, dz, radius)


def test_twist_zero_committed_loft_is_the_committed_stl(tmp_path):
    stl = loft(tmp_path, "--pitch-reference", "twist-zero")
    committed = GEOMETRY / "stl" / "phaseVI_blade.stl"
    assert stl.read_bytes() == committed.read_bytes()
    meta = json.loads((GEOMETRY / "metadata" / "phaseVI_blade.json").read_text(encoding="utf-8"))
    assert meta["stl_sha256"] == hashlib.sha256(committed.read_bytes()).hexdigest()
    assert (tmp_path / "phaseVI_blade.json").read_text(encoding="utf-8") == (
        GEOMETRY / "metadata" / "phaseVI_blade.json"
    ).read_text(encoding="utf-8")


def test_tip_loft_differs_from_twist_zero_by_the_tip_twist(tmp_path):
    zero = sections(loft(tmp_path / "z", "--pitch-reference", "twist-zero"))
    tip = sections(loft(tmp_path / "t", "--pitch-reference", "tip"))
    radius = max(zero)
    delta = wrap(chord_angle_deg(tip[radius]) - chord_angle_deg(zero[radius]))
    assert delta == pytest.approx(1.815, abs=DIFFERENCE_TOLERANCE_DEG)
