#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stall margin of an IEA 15-240-RWT spanwise profile against its 2-D polars.

Answers one question from data already on disk: how far is the angle of attack
that the actuator line uses (``alpha_deg`` of the snapshot written by
``compare_spanwise.py --profiles-out``) from the stall of the airfoil polar at
that station?

Per polar (AirfoilInfo tables in ``data/polars``, Re = 3e6 nominal):

* ``alpha0``      zero-lift angle (cl zero crossing nearest 0 deg);
* ``alpha_dev``   first angle above ``alpha0`` where cl falls ``--dev`` below the
                  linear extrapolation fitted on ``alpha0 + 1 .. alpha0 + 5``;
* ``alpha_clmax`` angle of the cl maximum in 0-35 deg, reported only when cl
                  then drops by at least 3 % within 10 deg (a true stall peak).

Per station: ``margin_dev = alpha_dev - alpha`` and
``margin_max = alpha_clmax - alpha``; a station is flagged ``NEAR`` when a margin
is below ``--margin`` deg and ``NONLIN`` when alpha is past ``alpha_dev`` (lift no longer linear, trailing-edge
separation growing) and ``STALL`` when alpha is past ``alpha_clmax``.
Cylinder-like sections (|cl| < 0.3 everywhere) are marked ``n/a``.

Usage:
    stall_margin.py [--model alm] [--csv PATH] [--margin 3] [--dev 0.1]
"""
import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "analysis" / "spanwise-profiles.csv"
BLADE_CSV = ROOT / "data" / "iea15mw_blade.csv"
POLARS_DIR = ROOT / "data" / "polars"

_ROW = re.compile(r"\(\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\)")


def read_polar(path):
    """Return the (alpha, cl) table of one polar file, in degrees."""
    rows = [(float(a), float(cl)) for a, cl, _, _ in _ROW.findall(path.read_text())]
    return sorted(rows)


def interp(table, alpha):
    for (a0, c0), (a1, c1) in zip(table, table[1:]):
        if a0 <= alpha <= a1:
            return c0 + (c1 - c0) * (alpha - a0) / (a1 - a0)
    raise ValueError(f"alpha {alpha} outside the polar table")


def polar_metrics(table, dev=0.1):
    """Stall descriptors of one polar, or None for a cylinder-like section."""
    if max(abs(cl) for _, cl in table) < 0.3:
        return None
    window = [(a, cl) for a, cl in table if -10.0 <= a <= 10.0]
    alpha0 = None
    for (a0, c0), (a1, c1) in zip(window, window[1:]):
        if c0 <= 0.0 <= c1 and c1 > c0:
            candidate = a0 + (0.0 - c0) * (a1 - a0) / (c1 - c0)
            if alpha0 is None or abs(candidate) < abs(alpha0):
                alpha0 = candidate
    if alpha0 is None:
        return None
    grid = [alpha0 + 1.0 + 0.25 * i for i in range(17)]
    cls = [interp(table, a) for a in grid]
    n = len(grid)
    mean_a, mean_c = sum(grid) / n, sum(cls) / n
    slope = sum((a - mean_a) * (c - mean_c) for a, c in zip(grid, cls)) / sum((a - mean_a) ** 2 for a in grid)
    intercept = mean_c - slope * mean_a
    alpha_dev = None
    alpha = alpha0 + 5.0
    while alpha <= 35.0:
        if intercept + slope * alpha - interp(table, alpha) > dev:
            alpha_dev = alpha
            break
        alpha += 0.25
    peak_alpha, peak_cl = max(((a, cl) for a, cl in table if 0.0 <= a <= 35.0), key=lambda p: p[1])
    after = [cl for a, cl in table if peak_alpha < a <= peak_alpha + 10.0]
    alpha_clmax = peak_alpha if after and min(after) < 0.97 * peak_cl else None
    return {"alpha0": alpha0, "slope": slope, "alpha_dev": alpha_dev,
            "alpha_clmax": alpha_clmax, "cl_max": peak_cl}


def read_blade(path=BLADE_CSV):
    """Return [(r_over_R, polar index)] from the blade table."""
    lines = [l for l in path.read_text().splitlines() if l and not l.startswith("#")]
    out = []
    for row in csv.DictReader(lines):
        out.append((float(row["r_over_R"]), int(row["airfoil_id"]) - 1))
    return out


def station_polar(blade, r_over_r):
    return min(blade, key=lambda b: abs(b[0] - r_over_r))[1]


def read_profile(path, model):
    with path.open() as handle:
        rows = [r for r in csv.DictReader(handle) if r["model"] == model]
    return sorted((float(r["r_over_R"]), float(r["alpha_deg"]), float(r["cl"])) for r in rows)


def classify(alpha, metrics, margin):
    """STALL past the cl peak, NONLIN past the departure from linear lift."""
    if metrics is None:
        return "n/a"
    peak, dev = metrics["alpha_clmax"], metrics["alpha_dev"]
    if peak is not None and alpha >= peak:
        return "STALL"
    if dev is not None and alpha >= dev:
        return "NONLIN"
    near = [m - alpha for m in (dev, peak) if m is not None]
    return "NEAR" if near and min(near) < margin else "ok"


def analyse(profile, blade, margin=3.0, dev=0.1, polars_dir=POLARS_DIR):
    cache, rows = {}, []
    for r_r, alpha, cl in profile:
        index = station_polar(blade, r_r)
        if index not in cache:
            cache[index] = polar_metrics(read_polar(polars_dir / f"polar_{index:02d}.dat"), dev)
        m = cache[index]
        rows.append({"r_R": r_r, "polar": index, "alpha": alpha, "cl": cl, "m": m,
                     "flag": classify(alpha, m, margin)})
    return rows


def _fmt(value):
    return "  -  " if value is None else f"{value:5.1f}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--model", default="alm")
    parser.add_argument("--margin", type=float, default=3.0)
    parser.add_argument("--dev", type=float, default=0.1)
    parser.add_argument("--step", type=int, default=6, help="print every Nth station")
    args = parser.parse_args(argv)
    rows = analyse(read_profile(args.csv, args.model), read_blade(), args.margin, args.dev)
    if not rows:
        print(f"no rows for model {args.model!r} in {args.csv}", file=sys.stderr)
        return 1
    print(f"model={args.model}  margin={args.margin} deg  dev={args.dev}  ({len(rows)} stations)")
    print(" r/R   polar  alpha  alpha0 a_dev  a_clmx  m_dev  m_max  cl    clmax  flag")
    for i, r in enumerate(rows):
        if i % args.step and r["flag"] in ("ok", "n/a", "NEAR", "NONLIN"):
            continue
        m = r["m"]
        if m is None:
            print(f"{r['r_R']:.3f}  {r['polar']:3d}  {r['alpha']:6.1f}   (cylinder-like)            {r['cl']:5.2f}        n/a")
            continue
        md = None if m["alpha_dev"] is None else m["alpha_dev"] - r["alpha"]
        mm = None if m["alpha_clmax"] is None else m["alpha_clmax"] - r["alpha"]
        print(f"{r['r_R']:.3f}  {r['polar']:3d}  {r['alpha']:6.1f} {m['alpha0']:6.1f} {_fmt(m['alpha_dev'])} {_fmt(m['alpha_clmax'])}  "
              f"{_fmt(md)} {_fmt(mm)}  {r['cl']:5.2f} {m['cl_max']:5.2f}  {r['flag']}")
    flags = [r["flag"] for r in rows]
    print(f"summary: STALL={flags.count('STALL')} NONLIN={flags.count('NONLIN')} NEAR={flags.count('NEAR')} ok={flags.count('ok')} n/a={flags.count('n/a')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
