#!/usr/bin/env python3
"""Compare the sectional force level station by station, with the correct arithmetic.

Two quantities, each chosen so the comparison cannot be an artefact of the
reference frame:

* `R = hypot(normal, tangential)` -- the resultant sectional force coefficient.
  A frame change is an orthogonal map, so R is the SAME physical quantity on both
  sides: no conversion, no angle, no twist needed. For cl >> cd (the whole
  attached region) R is within a fraction of a percent of cl, so R answers "is
  the lift level right" without an angle at all. This is the comparison of
  record.

* The frame angle, recovered with the ALGEBRAIC INVERSE of the decomposition,
  never `atan2` of the coefficient pair (which ignores cl/cd and carries a
  measured ~2.5 deg bias, see memory obs. 446).

The experiment's `cl`/`cd` are NOT tabulated and are NOT recoverable from its
published coefficients without an external angle, so this tool does not claim
them. What the experiment does expose is the twist: its two published frames are
the same vector seen twice, so the plain rotation between the pairs recovers the
local twist with no auxiliary quantity. That is checked, not assumed -- the
rotation is verified against the pairs and its residual is reported.

Degenerate elements are excluded: the root polar is a sentinel (`cl = 0`,
`cd = 1.1`) and the tip runs through a blend region, so any spanwise mean that
includes them is contaminated.

Read-only; no cluster cost.

Usage:  python3 scripts/compareSectionLoads.py --alm-dir runs/alm-U7-coarse-r2
"""
from __future__ import annotations

import argparse
import csv
import glob
import math
import os
import re
import statistics

R, CUT, TSR, U_REF = 5.029, 0.5083, 5.408, 7.0
STATIONS = (0.30, 0.47, 0.63, 0.80, 0.95)
CD_VALID_MAX = 0.5          # the root sentinel is cd = 1.1


def element_number(path: str) -> int:
    match = re.search(r"element(\d+)", path)
    return int(match.group(1)) if match else 0


def angle_from_pair(n, t, cl, cd):
    """Angle `g` with (n, t) == M(g)(cl, cd); algebraic inverse, not atan2."""
    res = math.hypot(n, t)
    if res < 1e-12 or abs(cl) > res:
        return float("nan")
    psi = math.atan2(t, n)
    offset = math.acos(max(-1.0, min(1.0, cl / res)))
    for g in (psi + offset, psi - offset):
        if abs(cl * math.sin(g) - cd * math.cos(g) - t) < 1e-6:
            return g
    return psi - offset


def rotation_between(x1, y1, x2, y2):
    """Angle b with (x2, y2) == Rot(b)(x1, y1), and how well that actually holds."""
    b = math.atan2(x1 * y2 - y1 * x2, x1 * x2 + y1 * y2)
    ex = x1 * math.cos(b) - y1 * math.sin(b) - x2
    ey = x1 * math.sin(b) + y1 * math.cos(b) - y2
    return b, math.hypot(ex, ey)


def sim_profile(alm_dir, lo, hi):
    """(r/R, cl, cd, R, frame angle, alpha_eff, twist) per valid element."""
    element_dir = os.path.join(
        alm_dir, "postProcessing/actuatorLineElements/0"
    )
    out = []
    dropped = 0
    for path in sorted(
        glob.glob(os.path.join(element_dir, "*blade1.element*.csv")),
        key=element_number,
    ):
        with open(path) as stream:
            rows = [
                row
                for row in csv.DictReader(stream)
                if lo <= float(row["time"]) <= hi
            ]
        if not rows:
            continue
        cl = statistics.mean(float(row["cl"]) for row in rows)
        cd = statistics.mean(float(row["cd"]) for row in rows)
        if cd > CD_VALID_MAX or cl == 0.0:
            dropped += 1
            continue
        cn = statistics.mean(float(row["c_ref_n"]) for row in rows)
        ct = statistics.mean(float(row["c_ref_t"]) for row in rows)
        alpha_eff = statistics.mean(float(row["alpha_deg"]) for row in rows)
        angle = math.degrees(angle_from_pair(cn, ct, cl, cd))
        root_dist = float(rows[0]["root_dist"])
        r_over_r = CUT / R + root_dist * (1.0 - CUT / R)
        out.append(
            (r_over_r, cl, cd, math.hypot(cl, cd), angle, alpha_eff,
             angle - alpha_eff)
        )
    out.sort()
    return out, dropped


def read_experiment(experiment_dir, speed):
    """Per station: (cn, ct, cth, ctq) from the enriched committed table."""
    stations = {}
    path = os.path.join(experiment_dir, "sequence_H_spanwise.csv")
    with open(path) as stream:
        for row in csv.DictReader(stream):
            if abs(float(row["wind_speed_m_s"]) - speed) > 1e-9:
                continue
            stations[round(float(row["r_over_R"]), 4)] = (
                float(row["cn"]), float(row["ct"]),
                float(row["cth"]), float(row["ctq"]),
            )
    return stations


def interpolate(profile, x, column):
    if x <= profile[0][0]:
        return profile[0][column]
    if x >= profile[-1][0]:
        return profile[-1][column]
    for lower, upper in zip(profile, profile[1:], strict=False):
        if lower[0] <= x <= upper[0]:
            ratio = 0.0 if upper[0] == lower[0] else (
                (x - lower[0]) / (upper[0] - lower[0])
            )
            return lower[column] + ratio * (upper[column] - lower[column])
    return float("nan")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--alm-dir", default="runs/alm-U7-coarse-r2")
    parser.add_argument("--experiment-dir", default="data/experiment")
    parser.add_argument("--speed", type=float, default=7.0)
    args = parser.parse_args()

    period = 2.0 * math.pi / (TSR * U_REF / R)
    start, end = 3.0 * period, 4.0 * period      # last revolution: least transient
    profile, dropped = sim_profile(args.alm_dir, start, end)
    if not profile:
        raise SystemExit("no valid elements in the window")
    experiment = read_experiment(args.experiment_dir, args.speed)
    if not experiment:
        raise SystemExit("no experiment stations for that speed")

    print(
        f"run {args.alm_dir}   last revolution t in "
        f"[{start:.3f}, {end:.3f}] s   degenerate elements excluded: {dropped}"
    )
    print(
        "\n  R is the frame-free resultant (no frame, no angle, no twist).\n"
        "  twist comes from the plain rotation between the experiment's two\n"
        "  published frames; the residual proves they are one vector seen twice.\n"
    )
    print(
        f"{'r/R':>5} | {'cl_sim':>7} {'R_sim':>7} {'phi_sim':>8} {'tw_sim':>7} | "
        f"{'R_exp':>7} {'tw_exp':>7} {'resid':>7} | {'dR':>8} {'dTw':>7}"
    )
    for station in STATIONS:
        key = round(station, 4)
        if key not in experiment:
            continue
        cn, ct, cth, ctq = experiment[key]
        r_sim = interpolate(profile, station, 3)
        cl_sim = interpolate(profile, station, 1)
        phi_sim = interpolate(profile, station, 4)
        twist_sim = interpolate(profile, station, 6)
        twist_exp, residual = rotation_between(cn, ct, cth, ctq)
        r_exp = math.hypot(cn, ct)
        r_exp_plane = math.hypot(cth, ctq)
        d_r = (r_sim - r_exp) / r_exp * 100.0
        twist_exp_deg = math.degrees(twist_exp)
        d_twist = abs(twist_sim) - abs(twist_exp_deg)
        print(
            f"{station:>5.2f} | {cl_sim:>7.3f} {r_sim:>7.3f} {phi_sim:>8.2f} "
            f"{twist_sim:>7.2f} | {r_exp:>7.3f} "
            f"{twist_exp_deg:>7.2f} {residual:>7.1e} | "
            f"{d_r:>+7.1f}% {d_twist:>+7.2f}"
        )
        if abs(r_exp - r_exp_plane) > 1e-4:
            print(f"      WARNING: the two experiment frames disagree in "
                  f"magnitude at r/R={station:.2f}: {r_exp:.5f} vs "
                  f"{r_exp_plane:.5f}")

    print(
        "\n  R_exp is the experiment's own resultant, so the two frames agreeing\n"
        "  in magnitude is a property of its data, not of this tool. dR is the\n"
        "  comparison of record. The simulation's twist (phi_sim - alpha_eff)\n"
        "  and the experiment's differ by a sign convention only; compare size."
    )


if __name__ == "__main__":
    main()
