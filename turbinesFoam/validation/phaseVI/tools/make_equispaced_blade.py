#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Write the equispaced Phase VI blade surface (CSV, STL, metadata) into a directory.

Resamples the committed station table with `blade_resample.resample_blade` and lofts it
with the committed pipeline (`geometry/src/blade_phasevi.py`, same S809, same section
rule). The committed STL under `geometry/` is never touched. Prints the STL sha256.

Usage:
    make_equispaced_blade.py --dz DZ --out-dir DIR

Exit codes:
    0  files written
    2  invalid --dz
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEOMETRY_SRC = ROOT.parents[1] / "geometry" / "src"
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(GEOMETRY_SRC))

import blade_phasevi  # noqa: E402
from blade_resample import render_csv, resample_blade  # noqa: E402
from case_config import read_blade  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dz", type=float, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.dz > 0.0:
        print("error: --dz must be positive", file=sys.stderr)
        return 2
    args.out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.out_dir / "phaseVI_blade_equispaced.csv"
    csv_path.write_text(render_csv(resample_blade(read_blade(), args.dz), args.dz), encoding="utf-8")
    stl = args.out_dir / "phaseVI_blade.stl"
    meta = args.out_dir / "phaseVI_blade.json"
    _, summary = blade_phasevi.build(stl, meta, blade_csv=csv_path, expected_stations=None)
    print(summary, file=sys.stderr)
    import json

    print(json.loads(meta.read_text(encoding="utf-8"))["stl_sha256"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
