#!/usr/bin/env python3
"""Extract the unique vertex coordinates of a binary STL.

The dummy structural participant must share the interface point cloud with
the fluid side (the turbinesFoam actuator surface reads the same STL). The
preCICE nearest-neighbor mapping only needs the coordinates, not the vertex
order, so this tool deduplicates the triangle vertices by rounding.

Usage:
    stl_vertices.py <input.stl> <output.dat>

The output is one "x y z" line per unique vertex, with a "# vertices" header.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path


def read_binary_stl(path: Path):
    data = path.read_bytes()

    # 80-byte header + uint32 triangle count
    if len(data) < 84:
        raise ValueError(f"{path}: too short to be a binary STL")

    (nTri,) = struct.unpack_from("<I", data, 80)

    expected = 84 + nTri * 50
    if len(data) != expected:
        raise ValueError(
            f"{path}: size {len(data)} != expected {expected} for {nTri} triangles "
            "(not a binary STL? use the ASCII reader)"
        )

    offset = 84
    for _ in range(nTri):
        # skip the normal (3 floats)
        offset += 12
        for _v in range(3):
            x, y, z = struct.unpack_from("<fff", data, offset)
            offset += 12
            yield (x, y, z)
        # skip the attribute byte count (uint16)
        offset += 2


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2

    src = Path(argv[1])
    dst = Path(argv[2])

    seen: set[tuple[float, float, float]] = set()
    unique: list[tuple[float, float, float]] = []

    # 1e-6 m rounding (~1e-4 chord) collapses the shared triangle corners
    for x, y, z in read_binary_stl(src):
        key = (round(x, 6), round(y, 6), round(z, 6))
        if key not in seen:
            seen.add(key)
            unique.append((x, y, z))

    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w") as fh:
        fh.write(f"# unique vertices from {src.name}\n")
        for x, y, z in unique:
            fh.write(f"{x:.8e} {y:.8e} {z:.8e}\n")

    print(f"{src}: {len(unique)} unique vertices -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
