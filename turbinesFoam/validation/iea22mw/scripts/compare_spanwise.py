#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Spanwise comparison of an IEA-22 ALM run with the OpenFAST reference blocks.

Reads the per-element actuator-line CSVs of blade 1, averages alpha, c_ref_n and
c_ref_t over the last ``--revs`` revolutions, maps ``root_dist`` to ``r/R`` with the
structural blade geometry (``r = HubRad + root_dist * BladeSpan``, ``R = TipRad``,
the same radius the reference store uses) and interpolates the reference block
(``olaf-fvw`` or ``openfast-bem`` of ``analysis/spanwise-references.csv``) at the ALM
radii. Reports per element the angle difference and the c_n / c_t ratios, and the
mean per radial band. The c_t ratio is informational: the AeroDyn tangential frame
is not the ALM ``c_ref_t`` frame (see iea15mw L26), so only alpha and c_n are
comparable.

Exit codes: 0 comparison written, 1 missing input.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
import blade_geometry as bg  # noqa: E402

RPM_RATED = 6.853997
DEFAULT_BANDS = "0.1-0.3,0.3-0.5,0.5-0.8,0.8-0.95,0.95-1.0"
STORE = HERE.parent / "analysis" / "spanwise-references.csv"


def _interp(x, xs, ys):
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for k in range(1, len(xs)):
        if x <= xs[k]:
            weight = (x - xs[k - 1]) / (xs[k] - xs[k - 1])
            return ys[k - 1] + weight * (ys[k] - ys[k - 1])
    return ys[-1]


def read_references(store: Path, source: str) -> dict:
    series: dict[str, list] = {}
    with store.open() as handle:
        for row in csv.DictReader(handle):
            if row["source"] == source:
                series.setdefault(row["quantity"], []).append(
                    (float(row["r_over_R_or_radius_m"]), float(row["value"])))
    return {name: sorted(points) for name, points in series.items()}


def read_elements(run_dir: Path, revs: float, rpm: float) -> list[dict]:
    files = sorted((run_dir / "postProcessing" / "actuatorLineElements").glob("*/turbine.blade1.element*.csv"))
    elements = []
    for path in files:
        with path.open() as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            continue
        t_end = max(float(r["time"]) for r in rows)
        window = [r for r in rows if float(r["time"]) > t_end - revs * 60.0 / rpm]
        mean = lambda key: sum(float(r[key]) for r in window) / len(window)  # noqa: E731
        radius = bg.HUB_RADIUS + float(rows[0]["root_dist"]) * bg.BLADE_SPAN
        elements.append({"r_over_R": radius / bg.TIP_RADIUS_STRUCTURAL, "alpha_deg": mean("alpha_deg"),
                         "c_n": mean("c_ref_n"), "c_t": mean("c_ref_t")})
    return sorted(elements, key=lambda e: e["r_over_R"])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--revs", type=float, default=2.0)
    parser.add_argument("--rpm", type=float, default=RPM_RATED)
    parser.add_argument("--store", type=Path, default=STORE)
    parser.add_argument("--source", choices=("olaf-fvw", "openfast-bem"), default="olaf-fvw")
    parser.add_argument("--bands", default=DEFAULT_BANDS, help="comma list of LO-HI r/R bands")
    parser.add_argument("--out", type=Path, help="per-element CSV")
    args = parser.parse_args(argv)
    elements = read_elements(args.run_dir, args.revs, args.rpm)
    if not elements:
        print(f"error: no element CSV under {args.run_dir}", file=sys.stderr)
        return 1
    reference = read_references(args.store, args.source)
    rows = []
    for element in elements:
        xs = [p[0] for p in reference["alpha_deg"]]
        ref = {q: _interp(element["r_over_R"], xs, [p[1] for p in reference[q]])
               for q in ("alpha_deg", "cn", "ct")}
        rows.append({"r_over_R": element["r_over_R"], "alpha_deg": element["alpha_deg"],
                     "ref_alpha_deg": ref["alpha_deg"], "dalpha_deg": element["alpha_deg"] - ref["alpha_deg"],
                     "cn_ratio": element["c_n"] / ref["cn"] if ref["cn"] else float("nan"),
                     "ct_ratio": element["c_t"] / ref["ct"] if ref["ct"] else float("nan")})
    print(f"run: {args.run_dir}\nreference: {args.source} ({args.store})\n"
          f"window: last {args.revs:g} rev at {args.rpm:g} rpm")
    for band in args.bands.split(","):
        low, high = (float(v) for v in band.split("-"))
        sel = [r for r in rows if low <= r["r_over_R"] <= high]
        if not sel:
            continue
        mean = lambda key: sum(r[key] for r in sel) / len(sel)  # noqa: E731
        print(f"band {band}: n={len(sel)} dalpha {mean('dalpha_deg'):+.2f} deg  "
              f"c_n ratio {mean('cn_ratio'):.3f}  c_t ratio {mean('ct_ratio'):.3f} (c_t informational)")
    if args.out:
        with args.out.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
