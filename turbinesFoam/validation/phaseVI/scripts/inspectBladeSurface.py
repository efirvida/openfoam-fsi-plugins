#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Spanwise layout and triangle quality of a lofted blade STL.

Why this exists
---------------
The ASM+mesh surface (`geometry/stl/phaseVI_blade.stl`) is a structured loft over
the NREL station table, so its sections sit wherever the table puts them, not at
equal spans. This reader reports, per segment between two consecutive sections,
the span `dz`, the mean chordwise edge, the triangle aspect ratio and the
area, so that the non-uniformity can be quoted as numbers.

Aspect ratio of a triangle is `Lmax**2 / (2*A)` (longest edge over the smallest
altitude); an equilateral triangle gives 1.155. It reads the file only: it
computes no calibrated quantity.

Usage
-----
    python3 validation/phaseVI/scripts/inspectBladeSurface.py geometry/stl/phaseVI_blade.stl
    python3 validation/phaseVI/scripts/inspectBladeSurface.py --json geometry/stl/phaseVI_blade.stl

Exit codes
----------
    0  read
    1  file missing or not a binary STL
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

_STL_DTYPE = np.dtype(
    [("normal", "<f4", 3), ("vertices", "<f4", (3, 3)), ("attr", "<u2")]
)


def read_binary_stl(path: Path) -> np.ndarray:
    """Triangle vertices, shape (n, 3, 3), float64."""
    raw = path.read_bytes()
    if len(raw) < 84:
        raise ValueError(f"{path}: too short for a binary STL")
    count = int(np.frombuffer(raw, dtype="<u4", count=1, offset=80)[0])
    if len(raw) != 84 + count * _STL_DTYPE.itemsize:
        raise ValueError(f"{path}: size does not match the declared {count} triangles")
    return np.frombuffer(raw, dtype=_STL_DTYPE, count=count, offset=84)["vertices"].astype(
        np.float64
    )


def segment_report(tris: np.ndarray, axis: int = 2, decimals: int = 6) -> list[dict]:
    """One row per segment between consecutive section levels along `axis`."""
    levels = np.unique(np.round(tris[:, :, axis].ravel(), decimals))
    rows = []
    centroid = tris[:, :, axis].mean(axis=1)
    for lo, hi in zip(levels[:-1], levels[1:]):
        inside = (centroid > lo) & (centroid < hi)
        if not inside.any():
            continue
        t = tris[inside]
        edges = np.stack(
            [
                np.linalg.norm(t[:, 1] - t[:, 0], axis=1),
                np.linalg.norm(t[:, 2] - t[:, 1], axis=1),
                np.linalg.norm(t[:, 0] - t[:, 2], axis=1),
            ],
            axis=1,
        )
        area = 0.5 * np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1)
        aspect = edges.max(axis=1) ** 2 / (2.0 * area)
        chordwise = np.sort(edges, axis=1)[:, 0]  # shortest edge: the chordwise step
        rows.append(
            {
                "z_lo": float(lo),
                "z_hi": float(hi),
                "dz": float(hi - lo),
                "triangles": int(inside.sum()),
                "chordwise_edge_mean": float(chordwise.mean()),
                "aspect_mean": float(aspect.mean()),
                "aspect_max": float(aspect.max()),
                "area": float(area.sum()),
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("stl", type=Path)
    parser.add_argument("--axis", type=int, default=2, choices=(0, 1, 2), help="span axis (default z)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        tris = read_binary_stl(args.stl)
    except (OSError, ValueError) as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1
    rows = segment_report(tris, axis=args.axis)
    dz = np.array([r["dz"] for r in rows])
    summary = {
        "triangles": int(len(tris)),
        "segments": len(rows),
        "dz_min": float(dz.min()),
        "dz_max": float(dz.max()),
        "dz_ratio": float(dz.max() / dz.min()),
        "aspect_max": float(max(r["aspect_max"] for r in rows)),
    }
    if args.json:
        print(json.dumps({"summary": summary, "segments": rows}, indent=2))
        return 0
    print(f"{summary['triangles']} triangles, {summary['segments']} segments; "
          f"dz {summary['dz_min']:.4f}..{summary['dz_max']:.4f} m (ratio {summary['dz_ratio']:.1f}); "
          f"worst aspect {summary['aspect_max']:.1f}")
    print(f"{'z_lo':>8} {'dz':>8} {'chord edge':>11} {'aspect mean':>12} {'aspect max':>11}")
    for r in rows:
        print(f"{r['z_lo']:8.4f} {r['dz']:8.4f} {r['chordwise_edge_mean']:11.4f} "
              f"{r['aspect_mean']:12.2f} {r['aspect_max']:11.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
