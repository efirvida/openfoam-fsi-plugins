#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Spanwise ripple of the ASM+mesh deposit for a given node layout and cell size.

Why this exists
---------------
Each surface node deposits its force with the separable kernel of Yang & Sotiropoulos
(Eq. 8, support 2.5*h, `surfaceSamplerBase::kernel`), so along the span the deposited
density is `D(z) = sum_i A_i * k((z - z_i)/h) / h` for a uniform load per unit area
(`A_i` the node area). The continuous answer is the same kernel applied to the
piecewise-constant area density `dA/dz` of the loft. Their difference is the
quadrature error of representing a segment by point nodes: harmless while the node
spacing is well below the kernel width, a comb once the mesh is refined below it.

The nodes are the triangle centroids of a lofted blade STL (as
`inspectBladeSurface.py` reads it). `--uniform-dz S` replaces them by nodes every `S`
metres carrying the local `dA/dz`, i.e. the proposal of an equispaced loft with the same
surface. It models the z direction only; it says nothing about the chordwise
direction (60 points per section, 0.01-0.025 m, always far below `h`).

Usage
-----
    python3 validation/phaseVI/scripts/spanwiseDepositRipple.py geometry/stl/phaseVI_blade.stl \
        --h 0.31 0.155 0.078 0.039 --uniform-dz 0.05

Exit codes
----------
    0  computed
    1  file missing or not a binary STL
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("inspectBladeSurface", _HERE / "inspectBladeSurface.py")
assert _spec is not None and _spec.loader is not None
inspect_surface = importlib.util.module_from_spec(_spec)
sys.modules["inspectBladeSurface"] = inspect_surface
_spec.loader.exec_module(inspect_surface)


def kernel(r: np.ndarray) -> np.ndarray:
    """Eq. 8 smoothed four-point cosine kernel, support |r| <= 2.5."""
    ar = np.abs(r)
    inner = 0.25 + (np.sin(np.pi * (2 * ar + 1) / 4) - np.sin(np.pi * (2 * ar - 1) / 4)) / (2 * np.pi)
    outer = 0.625 - 0.25 * ar - np.sin(np.pi * (2 * ar - 1) / 4) / (2 * np.pi)
    return np.where(ar <= 1.5, inner, np.where(ar <= 2.5, outer, 0.0))


def area_density(tris: np.ndarray, axis: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """Segment edges and the piecewise-constant dA/dz of each segment."""
    rows = inspect_surface.segment_report(tris, axis=axis)
    edges = np.array([rows[0]["z_lo"]] + [r["z_hi"] for r in rows])
    rho = np.array([r["area"] / r["dz"] for r in rows])
    return edges, rho


def nodes_from_triangles(tris: np.ndarray, axis: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """Triangle centroid z and area, the nodes the sampler uses."""
    area = 0.5 * np.linalg.norm(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1)
    return tris[:, :, axis].mean(axis=1), area


def nodes_uniform(edges: np.ndarray, rho: np.ndarray, dz: float) -> tuple[np.ndarray, np.ndarray]:
    """Nodes every `dz` carrying the local dA/dz."""
    n = max(int(round((edges[-1] - edges[0]) / dz)), 1)
    step = (edges[-1] - edges[0]) / n
    z = edges[0] + (np.arange(n) + 0.5) * step
    idx = np.clip(np.searchsorted(edges, z, side="right") - 1, 0, len(rho) - 1)
    return z, rho[idx] * step


def deposited(z_eval: np.ndarray, z_nodes: np.ndarray, weight: np.ndarray, h: float) -> np.ndarray:
    return (weight[None, :] * kernel((z_eval[:, None] - z_nodes[None, :]) / h) / h).sum(axis=1)


def reference(z_eval: np.ndarray, edges: np.ndarray, rho: np.ndarray, h: float, sub: int = 400) -> np.ndarray:
    """Kernel applied to the piecewise-constant density, by fine midpoint quadrature."""
    zs, ws = [], []
    for lo, hi, r in zip(edges[:-1], edges[1:], rho):
        m = max(int(np.ceil((hi - lo) / (h / sub))), 1)
        step = (hi - lo) / m
        zs.append(lo + (np.arange(m) + 0.5) * step)
        ws.append(np.full(m, r * step))
    return deposited(z_eval, np.concatenate(zs), np.concatenate(ws), h)


def ripple(tris: np.ndarray, h: float, uniform_dz: float | None = None, axis: int = 2) -> dict:
    edges, rho = area_density(tris, axis)
    z_n, w_n = nodes_from_triangles(tris, axis) if uniform_dz is None else nodes_uniform(edges, rho, uniform_dz)
    margin = 2.5 * h
    lo, hi = edges[0] + margin, edges[-1] - margin
    if hi <= lo:
        return {"h": h, "nodes": len(z_n), "max": float("nan"), "rms": float("nan")}
    z_eval = np.linspace(lo, hi, 2000)
    ref = reference(z_eval, edges, rho, h)
    err = (deposited(z_eval, z_n, w_n, h) - ref) / ref.mean()
    return {"h": h, "nodes": int(len(z_n)), "max": float(np.abs(err).max()), "rms": float(np.sqrt((err**2).mean()))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("stl", type=Path)
    parser.add_argument("--h", type=float, nargs="+", default=[0.31, 0.155, 0.078, 0.039],
                        help="cell sizes in metres (default: the coarse mesh and three refinements)")
    parser.add_argument("--uniform-dz", type=float, nargs="*", default=[],
                        help="also report an equispaced layout with these spacings")
    parser.add_argument("--axis", type=int, default=2, choices=(0, 1, 2))
    args = parser.parse_args(argv)
    try:
        tris = inspect_surface.read_binary_stl(args.stl)
    except (OSError, ValueError) as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1
    print("ripple = max |D - D_ref| / mean(D_ref) over the span interior (2.5 h from both ends)")
    print(f"{'layout':>22} {'h [m]':>8} {'nodes':>7} {'max':>9} {'rms':>9}")
    for h in args.h:
        r = ripple(tris, h, None, args.axis)
        print(f"{'committed loft':>22} {h:8.3f} {r['nodes']:7d} {r['max']:9.4f} {r['rms']:9.4f}")
        for dz in args.uniform_dz:
            r = ripple(tris, h, dz, args.axis)
            print(f"{'uniform dz=%g' % dz:>22} {h:8.3f} {r['nodes']:7d} {r['max']:9.4f} {r['rms']:9.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
