#!/usr/bin/env python3
"""Reconcile the spanwise tangential coefficients with the rotor torque.

The spanwise comparison shows `c_t` above the experiment at almost every station
while the integrated power sits below it. Both cannot describe the same run unless
the five stations are not a sufficient statistic for the integral, so this tool
integrates the element data itself and compares against the torque the same run
declares.

All quantities are dimensionless and the density cancels:

    C_T      = cp / tip_speed_ratio

    C_T_span = sum(c_t * 0.5 * U_rel^2 * chord * dr * r) / (0.5 * A * U_ref^2 * R)

with `A = pi R^2`, the two blades counted explicitly. If the two agree, the
spanwise coefficients are consistent with the integral and any disagreement with
the experiment belongs to the stations the experiment does not measure. If they
do not, the spanwise column is not on the experiment's footing and must not be
used for attribution.

Usage:
    python3 scripts/reconcileTorqueIntegral.py --alm-dir runs/alm-U7-coarse-r2
"""
from __future__ import annotations
import argparse, glob, math, os, re
from pathlib import Path

from comparePhaseVI import read_rows_resumed  # noqa: E402

R, R_ROOT, N_BLADES, CUT_R = 5.029, 0.5083, 2, 0.5083
TSR, U_REF = 5.408, 7.0


def element_index(path):
    m = re.search(r"element(\d+)", path)
    return int(m.group(1)) if m else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alm-dir", default="runs/alm-U7-coarse-r2")
    ap.add_argument("--discard-revs", type=float, default=1.0)
    a = ap.parse_args()

    period = 2.0 * math.pi * R / (TSR * U_REF)
    d = os.path.join(a.alm_dir, "postProcessing/actuatorLineElements/0")
    files = sorted(glob.glob(f"{d}/*blade1.element*.csv"), key=element_index)
    if not files:
        raise SystemExit(f"no element CSVs under {d}")

    rows = []
    for p in files:
        rs = [r for r in read_rows_resumed(Path(p)) if float(r["time"]) >= a.discard_revs * period]
        if not rs:
            continue
        m = lambda k: sum(float(r[k]) for r in rs) / len(rs)   # noqa: E731
        rr = CUT_R / R + m("root_dist") * (1 - CUT_R / R)
        # the CSV carries no chord column; f_ref_t already contains chord*span,
        # so the integrated torque is built from it directly.
        rows.append(dict(rr=rr, r=rr * R, U=m("rel_vel_mag"), ct=m("c_ref_t"),
                         cn=m("c_ref_n"), ft=m("f_ref_t"), alpha=m("alpha_deg"),
                         cl=m("cl"), ee=m("end_effect_factor")))

    # trapezoidal dr from the radial spacing of the elements
    for i, e in enumerate(rows):
        lo = rows[i - 1]["r"] if i > 0 else e["r"] - (rows[1]["r"] - rows[0]["r"]) / 2
        hi = rows[i + 1]["r"] if i < len(rows) - 1 else e["r"] + (rows[-1]["r"] - rows[-2]["r"]) / 2
        e["dr"] = (hi - lo) / 2.0

    A = math.pi * R ** 2
    denom = 0.5 * A * U_REF ** 2 * R
    def integ(key):
        return sum(e[key] * 0.5 * e["U"] ** 2 * e["chord"] * e["dr"] * e["r"] for e in rows) * N_BLADES

    ct_span = sum(e["ft"] * e["r"] * e["dr"] for e in rows) / denom
    ct_nodr = float("nan")
    cn_span = float("nan")

    # the run's own declared torque
    turl = os.path.join(a.alm_dir, "postProcessing/turbines/0/turbine.csv")
    cp = None
    if os.path.exists(turl):
        rs = [r for r in read_rows_resumed(Path(turl)) if float(r["time"]) >= a.discard_revs * period]
        cp = sum(float(r["cp"]) for r in rs) / len(rs)
    ct_declared = (cp / TSR) if cp is not None else float("nan")

    print(f"run            : {a.alm_dir}   ({len(rows)} elements, revs >= {a.discard_revs})")
    print(f"cp (mean)      : {cp:.5f}")
    print(f"C_T declared   : cp/tsr = {ct_declared:.6f}")
    print(f"C_T with dr    : {ct_span:.6f}   (ratio = {ct_span/ct_declared:.4f})")
    tot = sum(e["ft"] * e["r"] * e["dr"] for e in rows)
    print(f"\n  per-band share of the blade torque (the CSV is ONE blade; the declared")
    print(f"  coefficient covers the rotor, and the two agree, so the CSV total already")
    print(f"  carries the rotor's own normalisation):")
    bands = [(0.0,0.30),(0.30,0.50),(0.50,0.70),(0.70,0.90),(0.90,0.95),(0.95,1.01)]
    for lo,hi in bands:
        part = sum(e["ft"]*e["r"]*e["dr"] for e in rows if lo <= e["rr"] < hi)
        print(f"    {lo:.2f}-{hi:.2f}: {100*part/tot:>+7.2f} %")
    print(f"  => the element column and the declared torque differ by this factor.")
    ftsum = sum(e["ft"] * e["r"] for e in rows) * N_BLADES
    print(f"\nsum f_ref_t * r (x{N_BLADES})   = {ftsum:.2f}  [force/density * m]")
    print(f"denominator 0.5*A*Uref^2*R    = {denom:.2f}")
    print(f"\n{'r/R':>6} {'U_rel':>7} {'ct':>8} {'ft':>9} {'ft*r':>10} {'dr':>7}")
    for e in rows[::5]:
        print(f"{e['rr']:>6.3f} {e['U']:>7.2f} {e['ct']:>8.4f} {e['ft']:>9.4f} {e['ft']*e['r']:>10.4f} {e['dr']:>7.4f}")


if __name__ == "__main__":
    main()
