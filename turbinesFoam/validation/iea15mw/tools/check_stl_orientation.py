#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare the staged IEA blade STL section chord angle with the element pitch rows.

The ASM+mesh sampler places the STL as exported and applies no element pitch, so the
section chord angle baked into the STL has to equal the element chord angle the case
uses (`blade_geometry.element_rows` column 6, `pitch = -twist`) at every airfoil
station. This is the IEA counterpart of `tests/test_blade_pitch_reference.py`
(Phase VI B1, 1.815 deg defect).

The span runs along +z and the chord lies near +x in the exported frame, so the
section chord angle is `atan2(dy, dx)` of the LE -> TE-midpoint chord and the
expected value is `-pitch`. The LE -> TE-midpoint chord replaces the farthest-pair
chord, which is biased by up to 0.7 deg on the thick blunt-trailing-edge sections.

Usage:
    check_stl_orientation.py [--stl PATH] [--min-radius M] [--tolerance DEG]

Exit code 0 when max |difference| over the airfoil stations is below the tolerance.
"""

from __future__ import annotations

import argparse
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import blade_geometry  # noqa: E402

DEFAULT_STL = ROOT.parents[1] / "geometry" / "stl" / "iea15mw_blade.stl"
#: Radius [m] below which the section is the circular root, where a chord angle is undefined.
AIRFOIL_RADIUS = 20.0
#: Measurement bias of the LE -> TE-midpoint chord on the thickest airfoil section [deg].
TOLERANCE_DEG = 0.35


def sections(stl: Path) -> dict[float, list[tuple[float, float]]]:
    """Binary STL -> {z: unique (x, y) points}."""
    data = stl.read_bytes()
    count = struct.unpack("<I", data[80:84])[0]
    out: dict[float, set[tuple[float, float]]] = {}
    for i in range(count):
        record = struct.unpack("<12fH", data[84 + 50 * i: 134 + 50 * i])
        for k in range(3):
            x, y, z = record[3 + 3 * k: 6 + 3 * k]
            out.setdefault(round(z, 3), set()).add((x, y))
    return {z: sorted(points) for z, points in out.items()}


def chord_angle_deg(points: list[tuple[float, float]]) -> float:
    """Angle from +x of the LE -> TE-midpoint chord (aft 3 % of the chord averaged).

    The trailing edge is the farthest-pair end with the thinner aft slice (a blunt TE is
    thinner than the nose at 3 % chord).
    """
    pair = max(((a, b) for a in points for b in points), key=lambda p: math.dist(*p))
    length = math.dist(*pair)
    best = None
    for te, le in (pair, pair[::-1]):
        for _ in range(3):
            ux, uy = te[0] - le[0], te[1] - le[1]
            norm = math.hypot(ux, uy)
            ux, uy = ux / norm, uy / norm
            s = [(p[0] - le[0]) * ux + (p[1] - le[1]) * uy for p in points]
            aft = [p for p, v in zip(points, s) if v >= max(s) - 0.03 * length]
            te = (sum(p[0] for p in aft) / len(aft), sum(p[1] for p in aft) / len(aft))
            le = max(points, key=lambda p: math.dist(p, te))
        spread = max(math.dist(a, b) for a in aft for b in aft)
        if best is None or spread < best[0]:
            best = (spread, te, le)
    _, te, le = best
    dx, dy = te[0] - le[0], te[1] - le[1]
    if dx < 0.0:
        dx, dy = -dx, -dy
    return math.degrees(math.atan2(dy, dx))


def differences(stl: Path = DEFAULT_STL, min_radius: float = AIRFOIL_RADIUS) -> list[tuple[float, float, float]]:
    """(radius, STL chord angle, element chord angle) at the airfoil stations."""
    measured = sections(stl)
    zs = sorted(measured)
    rows = []
    for row in blade_geometry.element_rows(blade_geometry.BLADE_CSV):
        radius = row[1]
        if radius < min_radius:
            continue
        z = min(zs, key=lambda value: abs(value - radius))
        rows.append((radius, chord_angle_deg(measured[z]), -row[5]))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stl", type=Path, default=DEFAULT_STL)
    parser.add_argument("--min-radius", type=float, default=AIRFOIL_RADIUS)
    parser.add_argument("--tolerance", type=float, default=TOLERANCE_DEG)
    args = parser.parse_args(argv)
    rows = differences(args.stl, args.min_radius)
    worst = max(rows, key=lambda r: abs(r[1] - r[2]))
    print(f"stations {len(rows)} (r >= {args.min_radius} m)")
    print(f"max |STL chord angle - element chord angle| = {abs(worst[1] - worst[2]):.3f} deg at r = {worst[0]:.2f} m")
    outer = [r for r in rows if r[0] >= 60.0]
    print(f"  r >= 60 m: {max(abs(r[1] - r[2]) for r in outer):.3f} deg")
    return 0 if abs(worst[1] - worst[2]) < args.tolerance else 1


if __name__ == "__main__":
    raise SystemExit(main())
