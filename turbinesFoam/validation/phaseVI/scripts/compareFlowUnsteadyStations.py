#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""FLOWUnsteady Phase VI sectional loads next to the experiment (and our ALM).

Reads FLOWVLM's legacy ASCII `<tag>_Rotor_Blade{1,2}_vlm.<step>.vtk` of one
saved step and averages the two blades. Only the lattice (quad) cells are used;
FLOWVLM repeats the same cell data on its control-point vertex cells.
`Ftot`/`L` are forces per unit length INCLUDING density (FLOWVLM
`solvefromCCBlade`: "These Ftot, L, D, and S are forces per unit length").

Plane-of-rotation decomposition, rotor axis +x and wind along -x
(`flowunsteady/phaseVI.jl`): `F'n = -Ftot_x` (thrust), `F't = s Ftot . (x_hat x
e_r)` with the sign `s` chosen so the blade torque is positive (the run extracts
power; `check_smoke.py` fails otherwise). Two inflow angles from the plane of
rotation are printed: `phi_L` from the lift direction (exact: lift is normal to
the relative wind) and `phi_F = atan2(F't, F'n)`, the resultant-force angle that
`compareInflowAngle.py` compares against the experiment's `atan2(CTQ, CTH)`.

Units check before anything is read into a table: the blade integrals
`B sum F'n dr` and `B sum F't r dr` are printed next to the run's own monitor
(`power.csv` `Fx_N`, `Q_Nm`) at the same step.

The force x arm table uses `arm_contributions`/`station_widths` of
`compareSectionLoads.py` (five-point trapezoid, extended to the cutout and the
tip); the experiment's `F'n`/`F't` are `CTH`/`CTQ x QNORM x chord` with the
chord taken from the run's `geometry.csv`. `--alm-dir` adds our ALM with the
window and density of `compareSectionLoads.py` (configured sequence H window;
f_ref x rho_exp). The ALM window must pass the turbine cp/cd drift check.

Read-only; no cluster cost.

Usage:  python3 scripts/compareFlowUnsteadyStations.py flowunsteady/runs/fu-total-dson \
            [--step 720] [--alm-dir runs/alm-U7-coarse-p21]
"""
from __future__ import annotations

import argparse
import csv
import glob
import math
import os
import re

from compareSectionLoads import (CUT, R, STATIONS, U_REF, arm_contributions, chord_at,
                                 converged_window,
                                 interpolate, read_density, read_experiment, sim_profile,
                                 station_widths, QNORM)

BLADES = 2
STEPS_PER_REV = 72


def _blocks(path):
    """Points, lattice cells and cell data (name -> list) of a FLOWVLM vtk."""
    with open(path) as stream:
        lines = [line.split() for line in stream]
    points, cells, types, data = [], [], [], {}
    i = 0
    while i < len(lines):
        words = lines[i]
        if not words:
            i += 1
            continue
        key = words[0]
        if key == "POINTS":
            count = int(words[1])
            points = [tuple(float(v) for v in lines[i + 1 + k]) for k in range(count)]
            i += 1 + count
        elif key == "CELLS":
            count = int(words[1])
            cells = [[int(v) for v in lines[i + 1 + k][1:]] for k in range(count)]
            i += 1 + count
        elif key == "CELL_TYPES":
            count = int(words[1])
            types = [int(lines[i + 1 + k][0]) for k in range(count)]
            i += 1 + count
        elif key in ("VECTORS", "SCALARS"):
            name = words[1]
            i += 1
            if lines[i] and lines[i][0] == "LOOKUP_TABLE":
                i += 1
            values = [tuple(float(v) for v in lines[i + k]) for k in range(len(cells))]
            data[name] = values
            i += len(cells)
        else:
            i += 1
    lattice = [k for k, kind in enumerate(types) if kind == 9]
    return points, cells, lattice, data


def read_sections(path):
    """Per lattice: r [m], dr [m], F'n, F't [N/m], phi_lift_deg, phi_force_deg."""
    points, cells, lattice, data = _blocks(path)
    raw = []
    for k in lattice:
        le_in, le_out = points[cells[k][0]], points[cells[k][3]]
        r_in, r_out = math.hypot(*le_in[1:]), math.hypot(*le_out[1:])
        mid_y, mid_z = 0.5 * (le_in[1] + le_out[1]), 0.5 * (le_in[2] + le_out[2])
        r = math.hypot(mid_y, mid_z)
        e_t = (-mid_z / r, mid_y / r)       # x_hat x e_r, (y, z) components
        ftot, lift = data["Ftot"][k], data["L"][k]
        raw.append(dict(r=r, dr=abs(r_out - r_in),
                        fn=-ftot[0], ft=ftot[1] * e_t[0] + ftot[2] * e_t[1],
                        ln=-lift[0], lt=lift[1] * e_t[0] + lift[2] * e_t[1]))
    sign = 1.0 if sum(s["ft"] * s["r"] * s["dr"] for s in raw) >= 0.0 else -1.0
    sections = []
    for s in raw:
        ft, lt = sign * s["ft"], sign * s["lt"]
        sections.append(dict(r=s["r"], dr=s["dr"], fn=s["fn"], ft=ft,
                             phi_lift_deg=math.degrees(math.atan2(lt, s["ln"])),
                             phi_force_deg=math.degrees(math.atan2(ft, s["fn"]))))
    return sections


def blade_integrals(sections):
    """(thrust [N], torque [N.m]) of one blade, midpoint rule."""
    return (sum(s["fn"] * s["dr"] for s in sections),
            sum(s["ft"] * s["r"] * s["dr"] for s in sections))


def at_station(sections, r_over_r, key, radius=R):
    """Linear interpolation of `key` at r/R."""
    x = r_over_r * radius
    for a, b in zip(sections, sections[1:]):
        if a["r"] <= x <= b["r"]:
            w = (x - a["r"]) / (b["r"] - a["r"])
            return a[key] + w * (b[key] - a[key])
    raise ValueError(f"r/R {r_over_r} outside the lattice span")


def _mean_blades(paths):
    blades = [read_sections(p) for p in paths]
    out = []
    for parts in zip(*blades, strict=True):
        out.append({k: sum(p[k] for p in parts) / len(parts) for k in parts[0]})
    return out


def _monitor(run, step):
    with open(os.path.join(run, "power.csv")) as stream:
        rows = list(csv.DictReader(stream))
    rev = step / STEPS_PER_REV
    return min(rows, key=lambda row: abs(float(row["rev"]) - rev))


def _geometry_chords(run):
    with open(os.path.join(run, "geometry.csv")) as stream:
        return [(float(row["r_m"]), float(row["chord_m"])) for row in csv.DictReader(stream)]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("run")
    parser.add_argument("--step", type=int, default=None, help="saved step (default: last)")
    parser.add_argument("--alm-dir", default=None)
    parser.add_argument("--experiment-dir", default="data/experiment")
    parser.add_argument("--speed", type=float, default=U_REF)
    args = parser.parse_args()

    blade1 = glob.glob(os.path.join(args.run, "*_Rotor_Blade1_vlm.*.vtk"))
    steps = sorted(int(re.search(r"_vlm\.(\d+)\.vtk$", p).group(1)) for p in blade1)
    step = steps[-1] if args.step is None else args.step
    paths = [glob.glob(os.path.join(args.run, f"*_Rotor_Blade{b}_vlm.{step}.vtk"))[0]
             for b in range(1, BLADES + 1)]
    sections = _mean_blades(paths)

    thrust, torque = blade_integrals(sections)
    row = _monitor(args.run, step)
    print(f"run {args.run}  step {step} (rev {step / STEPS_PER_REV:g})")
    print(f"  units check: B*sum F'n dr = {BLADES * thrust:.1f} N vs monitor |Fx| "
          f"{abs(float(row['Fx_N'])):.1f} N; B*sum F't r dr = {BLADES * torque:.1f} N.m "
          f"vs monitor Q {float(row['Q_Nm']):.1f} N.m")

    experiment = read_experiment(args.experiment_dir, args.speed)
    chords = _geometry_chords(args.run)
    alm = None
    if args.alm_dir:
        start, end, _ = converged_window(args.alm_dir, args.speed, "H")
        alm, _ = sim_profile(args.alm_dir, start, end)
        rho = read_density(args.experiment_dir, args.speed)

    keys = [s for s in STATIONS if round(s, 4) in experiment]
    print("\n  per station (N/m, per blade; phi from the plane of rotation, deg)")
    head = (f"{'r/R':>5} | {'Fn_fu':>7} {'Fn_exp':>7} {'dFn%':>6} | {'Ft_fu':>7} {'Ft_exp':>7} "
            f"{'dFt%':>6} | {'phiL_fu':>7} {'phiF_fu':>7} {'phi_exp':>7}")
    if alm:
        head += f" | {'Fn_alm':>7} {'Ft_alm':>7}"
    print(head)
    widths = station_widths(keys, CUT, R)
    totals = {"fu": [0.0] * 3, "exp": [0.0] * 3, "alm": [0.0] * 3}
    arm_rows = []
    for station, d_r in zip(keys, widths, strict=True):
        cn, ct, cth, ctq = experiment[round(station, 4)]
        chord = chord_at(station * R, chords)
        fn_exp = cth * QNORM[round(station, 4)] * chord
        ft_exp = ctq * QNORM[round(station, 4)] * chord
        fn_fu, ft_fu = at_station(sections, station, "fn"), at_station(sections, station, "ft")
        line = (f"{station:>5.2f} | {fn_fu:>7.1f} {fn_exp:>7.1f} {100 * (fn_fu / fn_exp - 1):>+6.1f} | "
                f"{ft_fu:>7.1f} {ft_exp:>7.1f} {100 * (ft_fu / ft_exp - 1):>+6.1f} | "
                f"{at_station(sections, station, 'phi_lift_deg'):>7.2f} "
                f"{at_station(sections, station, 'phi_force_deg'):>7.2f} "
                f"{math.degrees(math.atan2(ctq, cth)):>7.2f}")
        contributions = {"fu": arm_contributions(station * R, d_r, fn_fu, ft_fu, CUT),
                         "exp": arm_contributions(station * R, d_r, fn_exp, ft_exp, CUT)}
        if alm:
            fn_alm = rho * interpolate(alm, station, 7)
            ft_alm = rho * interpolate(alm, station, 8)
            line += f" | {fn_alm:>7.1f} {ft_alm:>7.1f}"
            contributions["alm"] = arm_contributions(station * R, d_r, fn_alm, ft_alm, CUT)
        print(line)
        for side, values in contributions.items():
            for i in range(3):
                totals[side][i] += values[i]
        arm_rows.append((station, contributions))

    print("\n  force x arm, fu - exp per station (N.m): flapwise, edgewise, torque")
    for station, c in arm_rows:
        d = [c["fu"][i] - c["exp"][i] for i in range(3)]
        print(f"{station:>5.2f} | {d[0]:>+7.1f} {d[1]:>+7.1f} {d[2]:>+7.1f} "
              f"| {100 * d[2] / totals['exp'][2]:>+6.1f}% of station-sum torque")
    names = ("flapwise", "edgewise", "torque")
    sides = ["fu"] + (["alm"] if alm else [])
    for side in sides:
        print(f"  {side} station sums vs exp: " + "; ".join(
            f"{names[i]} {totals[side][i]:.0f} vs {totals['exp'][i]:.0f} N.m "
            f"({100 * (totals[side][i] / totals['exp'][i] - 1):+.1f} %)" for i in range(3)))


if __name__ == "__main__":
    main()
