#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Write the Phase VI blade surface (CSV, STL, metadata) for a pitch reference into a directory.

With `--dz` the committed station table is resampled with `blade_resample.resample_blade`;
without it the committed table is lofted as is. Either way the committed pipeline
(`geometry/src/blade_phasevi.py`, same S809, same section rule) lofts it with the section
angle of the elements: the surface sampler applies no element pitch, so the STL has to
bake the element chord angle for the chosen `--pitch-reference` (`tip`, the v1.3 default:
collective pitch measured at the tip chord; `twist-zero`: the v1.2 orientation, whose
committed-table loft is byte-identical to `geometry/stl/phaseVI_blade.stl`). The committed
STL under `geometry/` is never touched. Prints the STL sha256.

Usage:
    make_equispaced_blade.py [--dz DZ] [--pitch-reference twist-zero|tip] --out-dir DIR

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
from case_config import DEFAULT_CONFIG, load_config, read_blade  # noqa: E402
from element_data import DEFAULT_PITCH_REFERENCE, PITCH_REFERENCES, twist_reference  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dz", type=float, default=None, help="equispaced station spacing [m]; omit for the committed table")
    parser.add_argument("--pitch-reference", choices=PITCH_REFERENCES, default=DEFAULT_PITCH_REFERENCE)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.dz is not None and not args.dz > 0.0:
        print("error: --dz must be positive", file=sys.stderr)
        return 2
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.dz is None:
        csv_path = blade_phasevi.BLADE_CSV
        expected = blade_phasevi.N_STATIONS
    else:
        csv_path = args.out_dir / "phaseVI_blade_equispaced.csv"
        csv_path.write_text(render_csv(resample_blade(read_blade(), args.dz), args.dz), encoding="utf-8")
        expected = None
    cfg = load_config(DEFAULT_CONFIG)
    cfg["turbine"]["pitch_reference"] = args.pitch_reference
    stl = args.out_dir / "phaseVI_blade.stl"
    meta = args.out_dir / "phaseVI_blade.json"
    _, summary = blade_phasevi.build(stl, meta, blade_csv=csv_path, expected_stations=expected, twist_reference_deg=twist_reference(cfg))
    print(summary, file=sys.stderr)
    import json

    print(json.loads(meta.read_text(encoding="utf-8"))["stl_sha256"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
