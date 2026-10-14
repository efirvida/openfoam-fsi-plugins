#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Chord-frame cn and ct of the IEA 15 MW models against a reference, by r/R band.

The reference CSV (`analysis/spanwise-references.csv`, `olaf-fvw` or
`ccblade-bem`) carries AeroDyn normal/tangential-to-chord coefficients, so the
model pair is rebuilt from the profile's own `cl`, `cd` and `alpha_deg`
(`cn = cl cos(alpha) + cd sin(alpha)`, `ct = cl sin(alpha) - cd cos(alpha)`),
exactly as `phaseVI/scripts/comparePhaseVI.py` does against the experiment.
Neither side carries a nacelle or hub, so the band pattern is a rotor-only
benchmark. Read-only; no calibrated quantity is defined here.

Usage:
    python3 scripts/band_ratio_vs_reference.py --source olaf-fvw
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

ANALYSIS = Path(__file__).resolve().parent.parent / "analysis"
BANDS = (0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0)


def read_models(path: Path) -> dict[str, list[tuple[float, float, float]]]:
    """Per model: time-window mean `(r/R, cn, ct)` per station, sorted by r/R."""
    grouped: dict[str, dict[float, list[tuple[float, float]]]] = defaultdict(
        lambda: defaultdict(list))
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            alpha = math.radians(float(row["alpha_deg"]))
            cl, cd = float(row["cl"]), float(row["cd"])
            grouped[row["model"]][round(float(row["r_over_R"]), 6)].append(
                (cl * math.cos(alpha) + cd * math.sin(alpha),
                 cl * math.sin(alpha) - cd * math.cos(alpha)))
    result = {}
    for model, stations in grouped.items():
        result[model] = sorted(
            (r, sum(v[0] for v in values) / len(values),
             sum(v[1] for v in values) / len(values))
            for r, values in stations.items())
    return result


def read_reference(path: Path, source: str, quantity: str) -> list[tuple[float, float]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return sorted((float(r["r_over_R_or_radius_m"]), float(r["value"]))
                      for r in csv.DictReader(stream)
                      if r["source"] == source and r["quantity"] == quantity)


def interpolate(points: list[tuple[float, float]], x: float) -> float:
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    raise ValueError(x)


def band_ratios(profile, reference, index: int) -> list[tuple[float, float, float, int]]:
    """Mean model/reference ratio per band: `(lo, hi, ratio, stations)`."""
    out = []
    for lo, hi in zip(BANDS, BANDS[1:]):
        ratios = [row[index] / interpolate(reference, row[0])
                  for row in profile
                  if lo <= row[0] < hi or (hi == BANDS[-1] and row[0] == hi)]
        ratios = [r for r in ratios if math.isfinite(r)]
        out.append((lo, hi, sum(ratios) / len(ratios) if ratios else float("nan"),
                    len(ratios)))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", default="olaf-fvw",
                        choices=("olaf-fvw", "ccblade-bem"))
    parser.add_argument("--profiles", type=Path, default=ANALYSIS / "spanwise-profiles.csv")
    parser.add_argument("--references", type=Path,
                        default=ANALYSIS / "spanwise-references.csv")
    args = parser.parse_args(argv)
    models = read_models(args.profiles)
    print(f"model / {args.source} (chord frame), mean ratio per r/R band")
    for name, index in (("cn", 1), ("ct", 2)):
        reference = read_reference(args.references, args.source, name)
        print(f"\n{name}\nband       " + "  ".join(f"{m:>9}" for m in sorted(models)))
        for position, (lo, hi) in enumerate(zip(BANDS, BANDS[1:])):
            cells = []
            for model in sorted(models):
                ratio = band_ratios(models[model], reference, index)[position][2]
                cells.append(f"{ratio:9.3f}")
            print(f"{lo:.1f}-{hi:.1f}   " + "  ".join(cells))
    return 0


if __name__ == "__main__":
    sys.exit(main())
