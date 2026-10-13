#!/usr/bin/env python3
"""Per-revolution trend of the inboard angle, speed and tangential load.

Zero cluster cost: reads an existing run. If the inboard induction is still
developing when the run stops, the inboard angle is still falling and the
tangential load is still rising, which separates a time-convergence deficit from
a model deficit.

The check the run cannot escape: the *geometric* angle is fixed by the blade
geometry and the kinematics, so `alpha_geom_deg` must be time-independent. Any
movement in `alpha_deg` is induction.

Usage:  python3 scripts/inspectInboardAngle.py --alm-dir runs/alm-U7-coarse-r2
"""
from __future__ import annotations
import argparse, csv, glob, math, os, re, statistics

R, CUT = 5.029, 0.5083
TSR, U_REF = 5.408, 7.0
BANDS = [(0.20, 0.30), (0.30, 0.45), (0.45, 0.70), (0.70, 1.01)]


def idx(p):
    m = re.search(r"element(\d+)", p)
    return int(m.group(1)) if m else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alm-dir", default="runs/alm-U7-coarse-r2")
    ap.add_argument("--revs", type=float, default=4.0)
    a = ap.parse_args()
    period = 1.0 / (TSR * U_REF / (2 * math.pi * R))   # one revolution [s]

    d = os.path.join(a.alm_dir, "postProcessing/actuatorLineElements/0")
    files = sorted(glob.glob(f"{d}/*blade1.element*.csv"), key=idx)
    data = []
    for p in files:
        rs = list(csv.DictReader(open(p)))
        if not rs:
            continue
        rr = CUT / R + float(rs[0]["root_dist"]) * (1 - CUT / R)
        data.append((rr, rs))

    print(f"run {a.alm_dir}   one revolution = {period:.4f} s")
    for lo, hi in BANDS:
        sel = [(rr, rs) for rr, rs in data if lo <= rr < hi]
        if not sel:
            continue
        print(f"\n=== r/R in [{lo:.2f}, {hi:.2f})  ->  {len(sel)} elements")
        print(f"{'rev':>4} {'alpha_eff':>10} {'alpha_geom':>11} {'U_rel':>8} {'cl':>7} {'ct(plane)':>10} {'ft*r':>9}")
        prev = None
        for rev in range(int(a.revs)):
            t0, t1 = rev * period, (rev + 1) * period
            acc = {k: [] for k in ("alpha_deg", "alpha_geom_deg", "rel_vel_mag", "cl", "c_ref_t", "f_ref_t")}
            for rr, rs in sel:
                w = [r for r in rs if t0 <= float(r["time"]) < t1]
                if not w:
                    continue
                for k in acc:
                    acc[k].append(statistics.mean(float(r[k]) for r in w))
            vals = {k: statistics.mean(v) for k, v in acc.items() if v}
            ftr = statistics.mean(
                float(r["f_ref_t"]) * 0.0 for r in [{}]   # placeholder, replaced below
            ) if False else None
            ftr = statistics.mean(
                float(r["f_ref_t"]) * (CUT + float(r["root_dist"]) * (R - CUT))
                for rr, rs in sel for r in rs if t0 <= float(r["time"]) < t1
            ) if any(t0 <= float(r["time"]) < t1 for rr, rs in sel for r in rs) else float("nan")
            print(f"{rev:>4} {vals['alpha_deg']:>10.3f} {vals['alpha_geom_deg']:>11.3f} "
                  f"{vals['rel_vel_mag']:>8.3f} {vals['cl']:>7.4f} {vals['c_ref_t']:>10.4f} {ftr:>9.4f}")

    # what the kinematics alone predict for the geometric angle, for reference
    print("\n=== referencia: phi geometrico = atan(V/(Omega r)) y el twist de la geometria")
    for rr in (0.25, 0.30, 0.35, 0.45):
        omr = TSR * U_REF / R * rr * R
        print(f"   r/R={rr:.2f}: phi_geom = {math.degrees(math.atan(U_REF/omr)):.2f} deg")


if __name__ == "__main__":
    main()
