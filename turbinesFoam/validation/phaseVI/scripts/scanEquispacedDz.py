#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Scan the equispaced step dz against the cell size h (P1.5, E1).

Prints (1) the max spanwise deposit ripple of `spanwiseDepositRipple` for dz = f*h and
(2) the chord/twist/area deviation of the resampled station table from the committed
one (`tools/blade_resample.py`). The rule it supports is dz = min(0.05 m, h/2).

Usage: scanEquispacedDz.py [STL]      Exit codes: 0 computed, 1 STL missing.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))

from blade_resample import deviation, resample_blade  # noqa: E402
from case_config import read_blade  # noqa: E402

DEFAULT_STL = HERE.parents[2] / "geometry" / "stl" / "phaseVI_blade.stl"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    stl = Path(argv[0]) if argv else DEFAULT_STL
    if not stl.is_file():
        print(f"error: {stl} not found", file=sys.stderr)
        return 1
    tris = _load("inspectBladeSurface").read_binary_stl(stl)
    ripple = _load("spanwiseDepositRipple").ripple
    fractions = (0.25, 0.5, 0.75, 1.0, 1.5)
    print("max deposit ripple, dz = f*h")
    print("h [m]  " + "  ".join(f"f={f:<5}" for f in fractions))
    for h in (0.31, 0.155, 0.078, 0.039):
        cells = "  ".join(f"{100 * ripple(tris, h, uniform_dz=f * h)['max']:6.1f}%" for f in fractions)
        print(f"{h:<6} {cells}")
    blade = read_blade()
    print("\ngeometry kept by the resampled table")
    print("dz [m]  stations  chord dev [m]  twist dev [deg]  chord area dev")
    for dz in (0.0195, 0.025, 0.05, 0.1, 0.15):
        out = resample_blade(blade, dz)
        d = deviation(blade, out)
        print(f"{dz:<7} {len(out):<9} {d['chord']:<14.4f} {d['twist']:<16.3f} {100 * d['chord_area']:.3f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
