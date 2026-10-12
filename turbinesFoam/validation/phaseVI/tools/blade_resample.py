#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Equispaced resampling of the Phase VI blade station table.

The committed table (NREL/TP-500-29955 Table A-1) is spaced 0.013 .. 0.305 m. The
ASM+mesh deposit degrades once the cell size drops below that spacing, and the element
layout inherits the same 23:1 spread (odd/tasks/p1-5-equispaced-blade.md). This module
rebuilds the table at constant spanwise distance outboard of the airfoil start
(`AIRFOIL_RADIUS`, where the blade carries one S809 section); the root stations (circle
and circle -> S809 transition) are kept verbatim. Chord, twist and mount are linearly
interpolated, the same rule the loft applies between stations.

The result has the `read_blade()` row shape, so it feeds `blade_element_rows` unchanged.
"""

from __future__ import annotations

import math
from typing import Any

# First airfoil station; keep equal to `geometry/src/blade_phasevi.py:AIRFOIL_RADIUS`.
AIRFOIL_RADIUS = 1.0085

_KEYS = ("chord", "twist", "mount")


def _interp(blade: list[dict[str, float]], radius: float) -> dict[str, float]:
    for a, b in zip(blade, blade[1:]):
        if a["radius"] <= radius <= b["radius"]:
            t = (radius - a["radius"]) / (b["radius"] - a["radius"])
            row = {key: a[key] + t * (b[key] - a[key]) for key in _KEYS}
            row["radius"] = radius
            return row
    raise ValueError(f"radius {radius} outside the blade table")


def resample_blade(blade: list[dict[str, float]], dz: float) -> list[dict[str, float]]:
    """Root stations verbatim, then equispaced stations with step <= `dz` to the tip."""
    if dz <= 0.0:
        raise ValueError("dz must be positive")
    root = [dict(s) for s in blade if s["radius"] < AIRFOIL_RADIUS]
    tip = blade[-1]["radius"]
    n = max(1, math.ceil((tip - AIRFOIL_RADIUS) / dz - 1e-9))
    step = (tip - AIRFOIL_RADIUS) / n
    outboard = [_interp(blade, AIRFOIL_RADIUS + i * step) for i in range(n)]
    outboard.append(dict(blade[-1]))
    return root + outboard


def deviation(
    reference: list[dict[str, float]], resampled: list[dict[str, float]], samples: int = 4000
) -> dict[str, Any]:
    """Max |difference| of chord [m] and twist [deg] on a fine grid, and relative chord area."""
    lo, hi = AIRFOIL_RADIUS, reference[-1]["radius"]
    grid = [lo + (hi - lo) * i / samples for i in range(samples + 1)]
    worst = {"chord": 0.0, "twist": 0.0}
    area = [0.0, 0.0]
    previous = None
    for r in grid:
        a, b = _interp(reference, r), _interp(resampled, r)
        worst["chord"] = max(worst["chord"], abs(a["chord"] - b["chord"]))
        worst["twist"] = max(worst["twist"], abs(a["twist"] - b["twist"]))
        if previous is not None:
            dr = r - previous[0]
            area[0] += 0.5 * (a["chord"] + previous[1]) * dr
            area[1] += 0.5 * (b["chord"] + previous[2]) * dr
        previous = (r, a["chord"], b["chord"])
    worst["chord_area"] = abs(area[1] - area[0]) / area[0]
    return worst
