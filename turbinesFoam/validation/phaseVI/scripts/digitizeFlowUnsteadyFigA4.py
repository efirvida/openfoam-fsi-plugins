#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Extract the FLOWUnsteady curves and UAE min/max bars of Fig. A4 (Mehr et al., 2024).

Mehr, Alvarez, Ning, "Interactional Aerodynamics Analysis of a Multirotor Energy Kite",
Wind Energy 28 (2025) e2957, doi 10.1002/we.2957, page 19: CT, CQ and CP against tip speed
ratio for UAE Phase VI sequence H (72 rpm), FLOWUnsteady line and the experimental
min/max range of each of the 20 cases.

The figure is vector graphics, so the data are read from the PDF drawing operators (no
image digitising): axes are calibrated from the tick marks (short lines of 4.1 pt), the
simulation is the long polyline of each panel and every experimental bar is a pair of caps
(horizontal 4.7 pt lines). The "centre" column is the middle of the min/max range, NOT the
mean of the measurements (the paper does not print the mean).

Usage:
    digitizeFlowUnsteadyFigA4.py PDF [--out CSV] [--panel CT|CQ|CP]
"""
import argparse
import csv
import sys
from pathlib import Path

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar, LTCurve, LTLine, LTRect

PAGE_INDEX = 18
#: panel -> (x0, x1, y0, y1) bounding box in PDF points, tick values (y ascending), (x ticks)
PANELS = {
    "CT": ((135, 300, 225, 312), (0.2, 0.4)),
    "CQ": ((340, 500, 225, 310), (0.025, 0.050)),
    "CP": ((135, 300, 105, 190), (0.00, 0.25, 0.50)),
}
X_TICKS = (2.0, 4.0, 6.0)
TICK_LEN, CAP_LEN, EPS = 4.1, 4.7, 0.3


def _walk(element):
    for child in element:
        if not hasattr(child, "x0"):
            continue
        yield child
        if hasattr(child, "__iter__") and not isinstance(child, LTChar):
            yield from _walk(child)


def _fit(pairs):
    """Least-squares line value = a*coord + b through (coord, value) pairs."""
    n = len(pairs)
    mc = sum(c for c, _ in pairs) / n
    mv = sum(v for _, v in pairs) / n
    a = sum((c - mc) * (v - mv) for c, v in pairs) / sum((c - mc) ** 2 for c, _ in pairs)
    return a, mv - a * mc


def read_panel(objects, name):
    (x0, x1, y0, y1), y_values = PANELS[name]
    inside = [o for o in objects if o.x0 >= x0 and o.x1 <= x1 and o.y0 >= y0 and o.y1 <= y1
              and isinstance(o, (LTCurve, LTLine, LTRect))]
    lines = [o for o in inside if isinstance(o, LTLine)]
    hor = [o for o in lines if abs(o.y0 - o.y1) < 0.01]
    ver = [o for o in lines if abs(o.x0 - o.x1) < 0.01]
    y_ticks = sorted((o.y0 for o in hor if abs((o.x1 - o.x0) - TICK_LEN) < EPS and o.x1 < min(c.x0 for c in hor if abs((c.x1 - c.x0) - CAP_LEN) < EPS)), key=float)
    x_ticks = sorted(o.x0 for o in ver if abs((o.y1 - o.y0) - TICK_LEN) < EPS)
    if len(y_ticks) != len(y_values) or len(x_ticks) != len(X_TICKS):
        raise SystemExit(f"{name}: found {len(y_ticks)} y ticks and {len(x_ticks)} x ticks")
    ay, by = _fit(list(zip(y_ticks, y_values)))
    ax, bx = _fit(list(zip(x_ticks, X_TICKS)))
    line = max((o for o in inside if len(getattr(o, "pts", ())) > 20), key=lambda o: len(o.pts))
    curve = [(ax * px + bx, ay * py + by) for px, py in line.pts]
    caps = [o for o in hor if abs((o.x1 - o.x0) - CAP_LEN) < EPS]
    bars = {}
    for cap in caps:
        bars.setdefault(round((cap.x0 + cap.x1) / 2, 1), []).append(cap.y0)
    exp = []
    for xc, ys in sorted(bars.items()):
        if len(ys) >= 2:
            exp.append((ax * xc + bx, ay * min(ys) + by, ay * max(ys) + by))
    return curve, exp


def interp(curve, tsr):
    for (t0, v0), (t1, v1) in zip(curve, curve[1:]):
        if t0 <= tsr <= t1 or t1 <= tsr <= t0:
            return v0 if t1 == t0 else v0 + (v1 - v0) * (tsr - t0) / (t1 - t0)
    raise ValueError(f"tsr {tsr} outside the curve")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--panel", choices=sorted(PANELS))
    args = parser.parse_args(argv)
    page = next(extract_pages(str(args.pdf), page_numbers=[PAGE_INDEX]))
    objects = list(_walk(page))
    rows = []
    for name in ([args.panel] if args.panel else list(PANELS)):
        curve, exp = read_panel(objects, name)
        for tsr, lo, hi in exp:
            sim = interp(curve, tsr)
            centre = 0.5 * (lo + hi)
            rows.append((name, tsr, lo, hi, centre, sim, sim / centre - 1.0 if centre else float("nan"),
                         "inside" if lo <= sim <= hi else ("above" if sim > hi else "below")))
    print("panel  TSR     exp_min  exp_max  exp_mid   FLOWU   sim/mid-1  vs_range")
    for r in rows:
        print(f"{r[0]:<5} {r[1]:6.3f} {r[2]:8.4f} {r[3]:8.4f} {r[4]:8.4f} {r[5]:8.4f}  {r[6]:+8.1%}  {r[7]}")
    if args.out:
        with args.out.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(("panel", "tsr", "exp_min", "exp_max", "exp_mid", "flowunsteady", "sim_over_mid_minus_1", "vs_range"))
            writer.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
