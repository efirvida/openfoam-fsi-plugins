#!/usr/bin/env python3
"""Compare the root-loss factor this fork computes with the Prandtl hub-loss
factor AeroDyn computes, on a run's own elements.

Both factors have the Prandtl shape `F = 2/pi acos(min(1, exp(-f/sin phi)))`, and
both are multiplied by the tip factor, `F = F_tip * F_root`. They differ in the
constant:

    this fork   f_root = (B/2) * (r - r_root) / (R - r)   [src/.../axialFlowTurbineALSource.C]
    AeroDyn     f_root = (B/2) * (r - r_hub) / r_hub      [modules/aerodyn/src/BEMT.f90:246]

`rootDistance` is the blade-arc fraction from the root station, `(i + 0.5)/n`, and
`rootLocation` is the first geometry point, not the axis, so the fork's constant
carries `r - r_root` where AeroDyn carries `r`.

Since a run records only the product, `phi` is recovered first by solving the
fork's own two-factor product against the recorded factor, then AeroDyn's
constant is evaluated at that same `phi`. Read-only.

Usage:
    python3 scripts/compareHubLossFormula.py --alm-dir runs/alm-U7-coarse-r1
"""
from __future__ import annotations
import argparse, glob, math, os, re
from pathlib import Path

from comparePhaseVI import read_rows_resumed  # noqa: E402

R, R_ROOT, R_HUB, N_BLADES = 5.029, 0.5083, 0.5083, 2


def F_of(const, sin_phi):
    if sin_phi <= 0.0:
        return 1.0
    return 2.0 / math.pi * math.acos(min(1.0, math.exp(-const / sin_phi)))


def element_index(path):
    """Sort key: the element number in `...elementN.csv`, 0 when absent."""
    m = re.search(r"element(\d+)", path)
    return int(m.group(1)) if m else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alm-dir", default="runs/alm-U7-coarse-r1")
    ap.add_argument("--discard-revs", type=float, default=1.0)
    a = ap.parse_args()

    period = 2.0 * math.pi * R / (5.408 * 7.0)
    d = os.path.join(a.alm_dir, "postProcessing/actuatorLineElements/0")
    files = sorted(glob.glob(f"{d}/*blade1.element*.csv"), key=element_index)
    if not files:
        raise SystemExit(f"no element CSVs under {d}")

    print(f"{'r/R':>6} {'r [m]':>7} {'F measured':>11} {'F tip':>7} {'F root pkg':>11} "
          f"{'f pkg':>7} {'f AeroDyn':>10} {'F root AD':>10} {'F new':>7} {'lift':>8}")
    for p in files:
        rs = [r for r in read_rows_resumed(Path(p)) if float(r["time"]) >= a.discard_revs * period]
        if not rs:
            continue
        m = lambda k: sum(float(r[k]) for r in rs) / len(rs)   # noqa: E731
        rr = R_HUB / R + m("root_dist") * (1 - R_HUB / R)
        r = rr * R
        F_meas = m("end_effect_factor")
        # the fork's two constants, and the sin(phi) that reproduces F_meas
        a_tip = (N_BLADES / 2.0) * (R - r) / (r - R_ROOT)
        a_root = (N_BLADES / 2.0) * (r - R_ROOT) / (R - r)
        # F is decreasing in sin(phi) from 1 at 0+ to 0 at large sin(phi)
        lo, hi = 1e-8, 1.0
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if F_of(a_tip, mid) * F_of(a_root, mid) > F_meas:
                lo = mid
            else:
                hi = mid
        sin_phi = 0.5 * (lo + hi)
        F_tip = F_of(a_tip, sin_phi)
        F_root_pkg = F_of(a_root, sin_phi)
        f_ad = (N_BLADES / 2.0) * (r - R_HUB) / R_HUB
        F_root_ad = F_of(f_ad, sin_phi)
        F_new = F_tip * F_root_ad
        if rr < 0.55 or abs(rr - 0.63) < 0.02 or abs(rr - 0.80) < 0.02 or abs(rr - 0.95) < 0.02:
            print(f"{rr:>6.3f} {r:>7.3f} {F_meas:>11.4f} {F_tip:>7.4f} {F_root_pkg:>11.4f} "
                  f"{a_root/sin_phi:>7.3f} {f_ad/sin_phi:>10.3f} {F_root_ad:>10.4f} {F_new:>7.4f} "
                  f"{(F_new/F_meas - 1)*100:>+7.1f}%")


if __name__ == "__main__":
    main()
