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

A force-times-arm table follows (owner priority: the tangential force matters
structurally, so deficits are ranked by force x arm, not by percent). Per
station it prints the sectional force per length in the plane of rotation
(`F'n` thrust direction, `F't` tangential, N/m), and its share of the blade-root
flapwise moment `F'n (r - r_cut) dr`, edgewise moment `F't (r - r_cut) dr` and
shaft torque `F't r dr`, with `dr` the trapezoidal width over the five stations
(extended to the cutout and the tip). The simulation's `f_ref_n`/`f_ref_t` are
KINEMATIC (`0.5 c C |U|^2`, no density) and are multiplied by the experiment's
`rho_kg_m3`; the experiment's are `CTH`/`CTQ x QNORM x chord`, the chord taken
from the case's rendered `elementData`. The station sum is five-point
trapezoidal, so it ranks deficits; it does not replace the rotor torque of
record.

Degenerate elements are excluded: the root polar is a sentinel (`cl = 0`,
`cd = 1.1`) and the tip runs through a blend region, so any spanwise mean that
includes them is contaminated.

Read-only; no cluster cost.

Usage:  python3 scripts/compareSectionLoads.py --alm-dir runs/alm-U7-coarse-r2 [--sequence S]
(`--sequence` picks `data/experiment/sequence_<H|S>_*.csv`; default H.)
"""
from __future__ import annotations

import argparse
import csv
import glob
import math
import os
import re
import statistics

from closeExperimentIntegral import case_chord

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
        f_n = statistics.mean(float(row["f_ref_n"]) for row in rows)
        f_t = statistics.mean(float(row["f_ref_t"]) for row in rows)
        out.append(
            (r_over_r, cl, cd, math.hypot(cl, cd), angle, alpha_eff,
             angle - alpha_eff, f_n, f_t)
        )
    out.sort()
    return out, dropped


def read_experiment(experiment_dir, speed, sequence="H"):
    """Per station: (cn, ct, cth, ctq) from the enriched committed table."""
    stations = {}
    path = os.path.join(experiment_dir, f"sequence_{sequence}_spanwise.csv")
    with open(path) as stream:
        for row in csv.DictReader(stream):
            if abs(float(row["wind_speed_m_s"]) - speed) > 1e-9:
                continue
            stations[round(float(row["r_over_R"]), 4)] = (
                float(row["cn"]), float(row["ct"]),
                float(row["cth"]), float(row["ctq"]),
            )
            QNORM[round(float(row["r_over_R"]), 4)] = float(row["qnorm_pa"])
    return stations


QNORM = {}


def read_density(experiment_dir, speed, sequence="H"):
    """Air density [kg/m^3] of the experiment row at `speed`."""
    path = os.path.join(experiment_dir, f"sequence_{sequence}_performance.csv")
    with open(path) as stream:
        for row in csv.DictReader(stream):
            if abs(float(row["wind_speed_m_s"]) - speed) < 0.6:
                return float(row["rho_kg_m3"])
    raise SystemExit("no experiment density for that speed")


def station_widths(stations, r_min, r_max):
    """Trapezoidal dr [m] per station, extended to the cutout and the tip."""
    radii = [station * R for station in stations]
    widths = []
    for i, radius in enumerate(radii):
        lower = radii[i - 1] if i > 0 else r_min
        upper = radii[i + 1] if i < len(radii) - 1 else r_max
        widths.append((upper - lower) / 2.0)
    return widths


def arm_contributions(r, d_r, f_n, f_t, r_cut):
    """Moment shares of one station: (flapwise, edgewise, torque) in N.m."""
    return (
        f_n * (r - r_cut) * d_r,
        f_t * (r - r_cut) * d_r,
        f_t * r * d_r,
    )


def print_force_arm_table(profile, experiment, chords, rho):
    """Rank the station deficits by force x arm (sim - experiment, N.m)."""
    keys = [s for s in STATIONS if round(s, 4) in experiment]
    widths = station_widths(keys, CUT, R)
    print(
        "\n  force x arm per station (plane of rotation, per blade); dr is the"
        "\n  trapezoidal width over the stations. d* = sim - exp, N.m; the last"
        "\n  column is the share of the total experimental torque."
    )
    print(
        f"{'r/R':>5} {'dr':>6} | {'Fn_sim':>7} {'Fn_exp':>7} {'Ft_sim':>7} "
        f"{'Ft_exp':>7} | {'dFlap':>7} {'dEdge':>7} {'dTorq':>7} | {'dTorq%Qexp':>10}"
    )
    totals_exp = [0.0, 0.0, 0.0]
    totals_sim = [0.0, 0.0, 0.0]
    rows = []
    for station, d_r in zip(keys, widths, strict=True):
        cn, ct, cth, ctq = experiment[round(station, 4)]
        chord = float(chord_at(station * R, chords))
        q_norm = QNORM[round(station, 4)]
        fn_exp, ft_exp = cth * q_norm * chord, ctq * q_norm * chord
        fn_sim = rho * interpolate(profile, station, 7)
        ft_sim = rho * interpolate(profile, station, 8)
        r = station * R
        exp_c = arm_contributions(r, d_r, fn_exp, ft_exp, CUT)
        sim_c = arm_contributions(r, d_r, fn_sim, ft_sim, CUT)
        for i in range(3):
            totals_exp[i] += exp_c[i]
            totals_sim[i] += sim_c[i]
        rows.append((station, d_r, fn_sim, fn_exp, ft_sim, ft_exp, sim_c, exp_c))
    q_exp = totals_exp[2]
    for station, d_r, fn_sim, fn_exp, ft_sim, ft_exp, sim_c, exp_c in rows:
        d = [sim_c[i] - exp_c[i] for i in range(3)]
        print(
            f"{station:>5.2f} {d_r:>6.3f} | {fn_sim:>7.1f} {fn_exp:>7.1f} "
            f"{ft_sim:>7.1f} {ft_exp:>7.1f} | {d[0]:>+7.1f} {d[1]:>+7.1f} "
            f"{d[2]:>+7.1f} | {100.0 * d[2] / q_exp:>+9.1f}%"
        )
    print(
        f"{'sum':>5} {'':>6} | {'':>7} {'':>7} {'':>7} {'':>7} | "
        f"{totals_sim[0] - totals_exp[0]:>+7.1f} "
        f"{totals_sim[1] - totals_exp[1]:>+7.1f} "
        f"{totals_sim[2] - totals_exp[2]:>+7.1f} | "
        f"{100.0 * (totals_sim[2] - totals_exp[2]) / q_exp:>+9.1f}%"
    )
    print(
        f"  station-sum flapwise root moment: sim {totals_sim[0]:.0f} vs exp "
        f"{totals_exp[0]:.0f} N.m ({100.0 * (totals_sim[0] / totals_exp[0] - 1.0):+.1f} %)"
        f"; edgewise: sim {totals_sim[1]:.0f} vs exp {totals_exp[1]:.0f} N.m "
        f"({100.0 * (totals_sim[1] / totals_exp[1] - 1.0):+.1f} %)"
    )


def chord_at(radius, chords):
    """Linear chord at `radius` from the rendered (radius, chord) pairs."""
    pairs = sorted(chords)
    if radius <= pairs[0][0]:
        return pairs[0][1]
    for (r0, c0), (r1, c1) in zip(pairs, pairs[1:], strict=False):
        if radius <= r1:
            return c0 + (c1 - c0) * (radius - r0) / (r1 - r0)
    return pairs[-1][1]


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
    parser.add_argument("--sequence", choices=("H", "S"), default="H")
    args = parser.parse_args()

    period = 2.0 * math.pi / (TSR * U_REF / R)
    start, end = 3.0 * period, 4.0 * period      # last revolution: least transient
    profile, dropped = sim_profile(args.alm_dir, start, end)
    if not profile:
        raise SystemExit("no valid elements in the window")
    experiment = read_experiment(args.experiment_dir, args.speed, args.sequence)
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

    print_force_arm_table(
        profile, experiment, case_chord(args.alm_dir),
        read_density(args.experiment_dir, args.speed, args.sequence),
    )

    print(
        "\n  R_exp is the experiment's own resultant, so the two frames agreeing\n"
        "  in magnitude is a property of its data, not of this tool. dR is the\n"
        "  comparison of record. The simulation's twist (phi_sim - alpha_eff)\n"
        "  and the experiment's differ by a sign convention only; compare size."
    )


if __name__ == "__main__":
    main()
