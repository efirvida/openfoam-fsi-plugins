#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Markdown table of the IEA-15 and IEA-22 mesh quantities in units of the rotor radius R.

    python -I mesh_proportions.py

Both cases are rendered with their own generators (default flags) and every length is
divided by its own R. Exit code 1 if a proportional quantity differs by more than 1e-4
(the hub height and the realised vertical cell are listed as documented exceptions).
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

VALIDATION = Path(__file__).resolve().parents[2]
NUMBER = r"(-?[\d.]+(?:e[-+]?\d+)?)"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def quantities(gc) -> dict[str, tuple[float, bool]]:
    """``{name: (length [m], proportional)}`` of one rendered case."""
    rendered = {p.name: t for p, t in gc.outputs(case_dir=Path("case")).items()}
    snappy = rendered["snappyHexMeshDict"]
    out: dict[str, tuple[float, bool]] = {}
    for name in ("rotorDisk", "rotorWake"):
        block = snappy[snappy.index(f"{name}\n") :]
        p1 = re.search(rf"point1 \({NUMBER} {NUMBER} {NUMBER}\)", block).groups()
        p2 = re.search(rf"point2 \({NUMBER} {NUMBER} {NUMBER}\)", block).groups()
        out[f"{name} radius"] = (float(re.search(rf"radius {NUMBER};", block).group(1)), True)
        out[f"{name} point1 y (flow axis)"] = (float(p1[1]), True)
        out[f"{name} point2 y (flow axis)"] = (float(p2[1]), True)
    box = snappy[snappy.index("min (") :]
    lo = re.search(rf"min \({NUMBER} {NUMBER} {NUMBER}\)", box).groups()
    hi = re.search(rf"max \({NUMBER} {NUMBER} {NUMBER}\)", box).groups()
    out["tower box lateral half-width"] = (float(hi[0]), True)
    out["tower box upwind face"] = (float(lo[1]), True)
    out["tower box downwind end"] = (float(hi[1]), True)
    out["tower box floor"] = (float(lo[2]), True)
    out["tower box top"] = (float(hi[2]), True)
    domain = gc.domain_spec()
    out["domain upwind"] = (gc.flow_breaks(domain)[0], True)
    out["domain downwind"] = (gc.flow_breaks(domain)[-1], True)
    out["domain lateral"] = (gc.lateral_breaks(domain)[-1], True)
    out["domain top"] = (gc.DEFAULT_DOMAIN_TOP, True)
    out["base (hub) cell, D/32"] = (gc.Z_HUB_CELL, True)
    out["near-ground cell"] = (gc.Z_GROUND_CELL, True)
    out["disk castellated cell, level 3"] = (gc.Z_HUB_CELL / 2.0**gc.DEFAULT_SNAPPY_LEVEL, True)
    out["hub height (real geometry)"] = (gc.HUB_HEIGHT, False)
    out["realised hub-adjacent cell"] = (gc.hub_cell_size(), False)
    return out


def main() -> int:
    gc22 = _load("_mp_iea22", VALIDATION / "iea22mw" / "tools" / "generate_case.py")
    previous = sys.modules.get("blade_geometry")
    sys.modules["blade_geometry"] = _load("blade_geometry", VALIDATION / "iea15mw" / "tools" / "blade_geometry.py")
    gc15 = _load("_mp_iea15", VALIDATION / "iea15mw" / "tools" / "generate_case.py")
    if previous is not None:
        sys.modules["blade_geometry"] = previous
    q15, q22 = quantities(gc15), quantities(gc22)
    print("| Quantity | IEA-15 [m] | IEA-15 [R] | IEA-22 [m] | IEA-22 [R] |")
    print("|---|---|---|---|---|")
    print(f"| R | {gc15.ROTOR_RADIUS:.4f} | 1 | {gc22.ROTOR_RADIUS:.4f} | 1 |")
    worst = 0.0
    for name, (v15, proportional) in q15.items():
        v22 = q22[name][0]
        r15, r22 = v15 / gc15.ROTOR_RADIUS, v22 / gc22.ROTOR_RADIUS
        mark = "" if proportional else " (exception)"
        print(f"| {name}{mark} | {v15:.4g} | {r15:.5f} | {v22:.4g} | {r22:.5f} |")
        if proportional:
            worst = max(worst, abs(r22 - r15) / max(abs(r15), 1e-12))
    print(f"| cells (blockMesh base) | {gc15.cell_count():,} | | {gc22.cell_count():,} | |")
    print(f"\nmax relative difference of the proportional rows: {worst:.2e}")
    return 0 if worst < 1e-4 else 1


if __name__ == "__main__":
    raise SystemExit(main())
