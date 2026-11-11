#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sanity check of an IEA-22 OpenFAST ``metrics.json`` against the published tables.

Two independent references, both from the read-only IEA-22-280-RWT repository:

* ``OpenFAST/IEA-22-280-RWT/IEA-22-280-RWT_Cp_Ct_Cq.txt`` (ROSCO tables, 20 pitch x
  20 TSR at 11.14 m/s): interpolated at the case TSR and pitch (cubic spline when SciPy
  is available, bilinear otherwise; the bilinear value is always reported too).
* the WISDEM quasi-static rated row of ``Documentation/IEA-22-280-RWT_tabular.xlsx``
  ("Rotor Performance - WISDEM": ``Aero Power Coefficient``, ``Thrust Coefficient``)
  when ``--xlsx`` is given.

The tables come from other aerodynamic models (CCBlade/WISDEM), so agreement is a
plausibility check of the setup (units, radius, pitch sign, hub loss), not a
validation, and nothing is tuned towards it.

    rated_table_check.py CASEDIR|metrics.json [--table FILE] [--xlsx FILE] [--tolerance 5]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_TABLE = Path(
    "/scratch/leahk/eduardo.donestevez/simulations/tmp/iea22-src/repo/OpenFAST/IEA-22-280-RWT/IEA-22-280-RWT_Cp_Ct_Cq.txt"
)
SECTIONS = {"cp": "Power coefficient", "ct": "Thrust coefficient", "cq": "Torque coefficient"}


def read_table(path: Path) -> dict:
    """``{pitch: [...], tsr: [...], cp/ct/cq: [[row per TSR]]}`` of a ROSCO performance file."""
    lines = path.read_text().splitlines()
    vectors, key, blocks, current = {}, None, {}, None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            low = stripped.lower()
            key = "pitch" if "pitch angle vector" in low else "tsr" if "tsr vector" in low else key
            current = next((n for n, title in SECTIONS.items() if title.lower() in low), current if key is None else None)
            if current:
                blocks.setdefault(current, [])
                key = None
            continue
        if not stripped:
            continue
        values = [float(v) for v in stripped.split()]
        if key in ("pitch", "tsr") and key not in vectors:
            vectors[key] = values
        elif current:
            blocks[current].append(values)
    return {**vectors, **blocks}


def bilinear(xs, ys, grid, x, y):
    """``grid[row=y index][col=x index]`` bilinear interpolation (clamped to the table)."""
    def bracket(axis, v):
        v = min(max(v, axis[0]), axis[-1])
        i = max(j for j in range(len(axis) - 1) if axis[j] <= v)
        return i, (v - axis[i]) / (axis[i + 1] - axis[i])
    i, fx = bracket(xs, x)
    j, fy = bracket(ys, y)
    return ((1 - fx) * (1 - fy) * grid[j][i] + fx * (1 - fy) * grid[j][i + 1]
            + (1 - fx) * fy * grid[j + 1][i] + fx * fy * grid[j + 1][i + 1])


def spline(xs, ys, grid, x, y):
    from scipy.interpolate import RectBivariateSpline
    # RectBivariateSpline(x=rows axis, y=cols axis, z[rows][cols])
    return float(RectBivariateSpline(ys, xs, grid, kx=min(3, len(ys) - 1), ky=min(3, len(xs) - 1))(y, x)[0, 0])


def table_values(table: dict, tsr: float, pitch: float) -> dict:
    out = {}
    for name in SECTIONS:
        entry = {"bilinear": bilinear(table["pitch"], table["tsr"], table[name], pitch, tsr)}
        try:
            entry["spline"] = spline(table["pitch"], table["tsr"], table[name], pitch, tsr)
        except ImportError:
            pass
        out[name] = entry
    return out


def workbook_row(xlsx: Path, speed: float) -> dict:
    import openpyxl
    sheet = openpyxl.load_workbook(xlsx, data_only=True)["Rotor Performance - WISDEM"]
    rows = sheet.iter_rows(values_only=True)
    header = [str(h) for h in next(rows)]
    data = [r for r in rows if isinstance(r[0], (int, float))]
    row = min(data, key=lambda r: abs(r[0] - speed))
    pick = lambda name: row[header.index(name)]  # noqa: E731
    return {"U": pick("Wind [m/s]"), "pitch": pick("Pitch [deg]"), "cp": pick("Aero Power Coefficient [-]"),
            "ct": pick("Thrust Coefficient [-]"), "thrust_mn": pick("Thrust [MN]")}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("metrics", type=Path)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--xlsx", type=Path, default=None)
    parser.add_argument("--tolerance", type=float, default=5.0, help="plausibility band, percent")
    args = parser.parse_args(argv)
    path = args.metrics / "metrics.json" if args.metrics.is_dir() else args.metrics
    metrics = json.loads(path.read_text())
    values = table_values(read_table(args.table), metrics["tip_speed_ratio"], metrics["pitch"])
    method = "spline" if "spline" in values["cp"] else "bilinear"
    refs = {f"Cp_Ct_Cq.txt ({method})": {n: values[n].get("spline", values[n]["bilinear"]) for n in ("cp", "ct")}}
    if args.xlsx:
        row = workbook_row(args.xlsx, metrics["U"])
        refs[f"WISDEM row U={row['U']:.4f} pitch={row['pitch']:.3f}"] = {"cp": row["cp"], "ct": row["ct"]}
    ok = True
    print(f"case: U {metrics['U']} m/s, {metrics['rpm']} rpm, pitch {metrics['pitch']} deg, TSR {metrics['tip_speed_ratio']:.4f}, "
          f"wake {metrics['wake']}: Cp {metrics['cp']:.5f}  Ct {metrics['ct']:.5f}")
    for label, ref in refs.items():
        for name in ("cp", "ct"):
            diff = 100.0 * (metrics[name] - ref[name]) / ref[name]
            flag = "ok" if abs(diff) <= args.tolerance else "OUT"
            ok &= flag == "ok"
            print(f"  vs {label:<44} {name}: {ref[name]:.5f}  diff {diff:+6.2f} %  {flag}")
    print("  bilinear table values:", {n: round(v["bilinear"], 5) for n, v in values.items() if n != "cq"})
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
