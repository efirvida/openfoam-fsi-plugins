#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Write a closed capsule-like nacelle surface as a binary STL.

The body is a cylinder of radius `--radius` and length `--length` along
`--axis`, with a flat disc cap at the START end and a hemispherical cap at the
END end (so the total length is `length + radius`). `--start` is the centre of
the flat cap. Triangle normals point outward. The tool is deterministic: the
same arguments give the same bytes.

Used for the Phase VI (UAE sequence H) and IEA 15 MW nacelle on/off studies,
where the real nacelle is approximated by a cylinder with a rounded tail.

Usage:
    python3 validation/tools/make_nacelle_stl.py out.stl --radius 0.455 \
        --length 2.8 --start 0 0 0 --axis 1 0 0
"""
from __future__ import annotations

import argparse
import math
import struct
import sys
from pathlib import Path


def _unit(v):
    n = math.sqrt(sum(c * c for c in v))
    if n == 0.0:
        raise ValueError("axis must be non-zero")
    return tuple(c / n for c in v)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _basis(axis):
    helper = (0.0, 0.0, 1.0) if abs(axis[2]) < 0.9 else (1.0, 0.0, 0.0)
    e1 = _unit(_cross(axis, helper))
    return e1, _cross(axis, e1)


def triangles(radius, length, start, axis, n_theta=48, n_cap=12):
    """Outward-facing triangles `(a, b, c)` of the closed body."""
    axis = _unit(axis)
    e1, e2 = _basis(axis)

    def point(s, rho, theta):
        return tuple(start[i] + axis[i] * s + rho * (math.cos(theta) * e1[i]
                                                   + math.sin(theta) * e2[i])
                     for i in range(3))

    # Profile (s, rho) from the flat cap centre, along the cylinder, over the dome.
    profile = [(0.0, 0.0), (0.0, radius), (length, radius)]
    for k in range(1, n_cap + 1):
        phi = 0.5 * math.pi * k / n_cap
        profile.append((length + radius * math.sin(phi), radius * math.cos(phi)))
    out = []
    for j in range(len(profile) - 1):
        (s0, r0), (s1, r1) = profile[j], profile[j + 1]
        for i in range(n_theta):
            t0 = 2.0 * math.pi * i / n_theta
            t1 = 2.0 * math.pi * (i + 1) / n_theta
            a, b = point(s0, r0, t0), point(s0, r0, t1)
            c, d = point(s1, r1, t1), point(s1, r1, t0)
            if r0 == 0.0:
                out.append((a, d, c))
            elif r1 == 0.0:
                out.append((a, b, d))
            else:
                out.extend([(a, d, c), (a, c, b)])
    return out, axis


def _oriented(tris, start, axis):
    """Flip any triangle whose normal points toward the body axis."""
    fixed = []
    for a, b, c in tris:
        u = tuple(b[i] - a[i] for i in range(3))
        v = tuple(c[i] - a[i] for i in range(3))
        n = _cross(u, v)
        centroid = tuple((a[i] + b[i] + c[i]) / 3.0 for i in range(3))
        rel = tuple(centroid[i] - start[i] for i in range(3))
        along = sum(rel[i] * axis[i] for i in range(3))
        radial = tuple(rel[i] - along * axis[i] for i in range(3))
        outward = sum(n[i] * radial[i] for i in range(3))
        if outward == 0.0:
            # cap triangles have no radial lever: the start cap faces -axis
            outward = -sum(n[i] * axis[i] for i in range(3))
        fixed.append((a, c, b) if outward < 0.0 else (a, b, c))
    return fixed


def write_stl(path: Path, tris) -> None:
    with path.open("wb") as stream:
        stream.write(b"turbinesFoam make_nacelle_stl".ljust(80, b" "))
        stream.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            u = tuple(b[i] - a[i] for i in range(3))
            v = tuple(c[i] - a[i] for i in range(3))
            n = _cross(u, v)
            norm = math.sqrt(sum(x * x for x in n)) or 1.0
            stream.write(struct.pack("<12fH", *(x / norm for x in n), *a, *b, *c, 0))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("out", type=Path)
    p.add_argument("--radius", type=float, required=True)
    p.add_argument("--length", type=float, required=True, help="cylinder length [m]")
    p.add_argument("--start", type=float, nargs=3, default=(0.0, 0.0, 0.0))
    p.add_argument("--axis", type=float, nargs=3, default=(1.0, 0.0, 0.0))
    args = p.parse_args(argv)
    if args.radius <= 0.0 or args.length <= 0.0:
        p.error("radius and length must be positive")
    tris, axis = triangles(args.radius, args.length, tuple(args.start), tuple(args.axis))
    write_stl(args.out, _oriented(tris, tuple(args.start), axis))
    print(f"{args.out}: {len(tris)} triangles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
