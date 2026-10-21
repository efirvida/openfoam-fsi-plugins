#!/usr/bin/env python3
"""Measure the `profileData` Reynolds rescaling a run actually applied.

`profileData::updateRe` rewrites a single-Re lift table as `cl'(a) = K cl(a/K)`
with `K = (Re/ReRef)^n`, `n` = `liftReCorrExp` (source default 0.23). Because the
element CSV records the coefficient that was used and the angle it was looked up
at, K can be recovered element by element from the CSV and the polar on disk,
with no assumption about ReRef:

    cl_csv = K * cl_polar(alpha_csv / K) * end_effect_factor

The tool solves that for K, then also evaluates what a chosen ReRef would
predict, so the declared and the actual factors can be told apart. Read-only.

Usage:
    python3 scripts/quantifyPolarReScaling.py --alm-dir runs/alm-U7-coarse-r1
    python3 scripts/quantifyPolarReScaling.py --alm-dir runs/alm-U7-coarse-r1 --re-ref 1e6
"""
from __future__ import annotations
import argparse, glob, os, re
import bisect
from pathlib import Path

from comparePhaseVI import read_rows_resumed  # noqa: E402


def read_polar(path):
    """(alphas, cls) from a `(alpha cl cd cm)` table; comment lines ignored."""
    alphas, cls = [], []
    for raw in open(path):
        if raw.lstrip().startswith(("//", "#")):
            continue
        parts = raw.replace("(", " ").replace(")", " ").split()
        if len(parts) >= 2:
            try:
                alphas.append(float(parts[0])); cls.append(float(parts[1]))
            except ValueError:
                pass
    return alphas, cls


def interp(x, xs, ys):
    if x <= xs[0]: return ys[0]
    if x >= xs[-1]: return ys[-1]
    i = bisect.bisect_left(xs, x)
    x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0) if x1 != x0 else y0


def solve_K(cl_csv, alpha, end_eff, alphas, cls):
    """K in [0.4, 2.5] reproducing the recorded coefficient, or None."""
    if end_eff <= 0.0 or cl_csv <= 0.0:
        return None
    f = lambda K: K * interp(alpha / K, alphas, cls) * end_eff - cl_csv   # noqa: E731
    lo, hi = 0.4, 2.5
    if f(lo) * f(hi) > 0:
        return None
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if f(lo) * f(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alm-dir", default="runs/alm-U7-coarse-r1")
    ap.add_argument("--polar", default="data/polars/S809_OSU_Re1M_total.dat")
    ap.add_argument("--exponent", type=float, default=0.23)
    ap.add_argument("--re-ref", type=float, default=1.0e6)
    ap.add_argument("--discard-revs", type=float, default=1.0)
    a = ap.parse_args()

    alphas, cls = read_polar(a.polar)
    period = 2.0 * 3.141592653589793 * 5.029 / (5.408 * 7.0)
    d = os.path.join(a.alm_dir, "postProcessing/actuatorLineElements/0")
    files = sorted(glob.glob(f"{d}/*blade1.element*.csv"),
                   key=lambda p: int(re.search(r"element(\d+)", p).group(1)))
    if not files:
        raise SystemExit(f"no element CSVs under {d}")

    print(f"polar {a.polar}   ({len(alphas)} rows)")
    print(f"exponent n = {a.exponent}   assumed ReRef = {a.re_ref:.3e}")
    print(f"\n{'r/R':>6} {'Re':>10} {'endEff':>7} {'K meas':>8} {'K if ReRef':>11} {'cl csv':>8} {'cl polar':>9} {'alpha':>7}")

    ks, kr = [], []
    for p in files:
        rs = [r for r in read_rows_resumed(Path(p)) if float(r["time"]) >= a.discard_revs * period]
        if not rs:
            continue
        m = lambda k: sum(float(r[k]) for r in rs) / len(rs)   # noqa: E731
        rr = 0.5083 / 5.029 + m("root_dist") * (1 - 0.5083 / 5.029)
        Re, ee, alpha = m("Re"), m("end_effect_factor"), m("alpha_deg")
        K = solve_K(m("cl"), alpha, ee, alphas, cls)
        Kr = (Re / a.re_ref) ** a.exponent
        if K:
            ks.append(K); kr.append(Kr)
        if abs(rr - 0.30) < 0.012 or abs(rr - 0.47) < 0.012 or abs(rr - 0.63) < 0.012 \
           or abs(rr - 0.80) < 0.012 or abs(rr - 0.95) < 0.012:
            shell = interp(alpha, alphas, cls)
            print(f"{rr:>6.3f} {Re:>10.3e} {ee:>7.4f} {K:>8.4f} {Kr:>11.4f} "
                  f"{m('cl'):>8.4f} {shell:>9.4f} {alpha:>7.2f}")
    if ks:
        mean_k = sum(ks) / len(ks)
        mean_kr = sum(kr) / len(kr)
        print(f"\nmean K measured from the CSVs        : {mean_k:.4f}   ({(mean_k-1)*100:+.2f} % on lift)")
        print(f"mean K if ReRef = {a.re_ref:.2e}          : {mean_kr:.4f}   ({(mean_kr-1)*100:+.2f} %)")
        print(f"slope multiplier (K^2)               : {(mean_k**2-1)*100:+.2f} %")
        print(f"zero-lift angle displaced (a0 = -2.5): {(mean_k-1)*2.5:+.3f} deg")
        print(f"\n=> the rescaling is {'REDUCING' if mean_k < 1 else 'RAISING'} lift by {abs(mean_k-1)*100:.2f} %")


if __name__ == "__main__":
    main()
