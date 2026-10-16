#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reference BEM of the NREL Phase VI rotor on the SAME inputs as the CFD runs.

Purpose: separate "the method" from "the implementation". If a classical BEM,
fed the identical chord, twist, S809 polar, rotor speed, density and pitch,
misses the measured power by the same amount as the actuator-line / actuator-
surface runs, the deficit is carried by the shared inputs (polar, tip/root
loss, induction closure), not by the CFD coupling.

Model: steady BEM with Prandtl tip loss, Prandtl hub loss
f_hub = (B/2)(r - rHub)/rHub (the frozen definition), and the Buhl (2005)
high-induction correction for a > 0.4. Tip loss can be switched off to bracket
the Dag & Sorensen tip model used in the CFD, which has no BEM equivalent.

Conventions (match the CFD, ``makeElementData.py``): blade pitch angle
theta = twist_report + tip pitch, phi = alpha + theta, with phi measured from
the plane of rotation. cn/ct below are plane-referenced:
    cn = cl cos(phi) + cd sin(phi),   ct = cl sin(phi) - cd cos(phi)
and the force-direction angle ``phi_force = atan2(ct, cn)`` is the quantity the
experiment publishes as atan2(CTQ, CTH) (see ``compareInflowAngle.py``).

Usage:
    bemPhaseVI.py --speed 7 --rpm 71.8667 --rho 1.2525 --pitch 3
    bemPhaseVI.py ... --tip off          # no tip loss
"""
import argparse
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
STATIONS = (0.30, 0.47, 0.63, 0.80, 0.95)


def read_geometry():
    rows = []
    for line in (DATA / "geometry" / "phaseVI_blade.csv").read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        r, c, tw, _ = (float(x) for x in line.split(","))
        rows.append((r, c, tw))
    a = np.array(rows)
    return a[:, 0], a[:, 1], a[:, 2]


def read_polar(name="S809_OSU_Re1M_total.dat"):
    rows = []
    for line in (DATA / "polars" / name).read_text().splitlines():
        s = line.strip()
        if s.startswith("(") and not s.startswith("//"):
            vals = s.strip("()").split()
            if len(vals) == 4:
                rows.append([float(v) for v in vals])
    a = np.array(sorted(rows))
    return a[:, 0], a[:, 1], a[:, 2]


def pressure_drag(polar):
    """Replace cd by the OSU pressure drag cdp inside the measured range.

    The experiment integrates surface pressure taps, so its forces carry the
    pressure drag only; the model polar carries the wake-traverse total.
    """
    alphas, cls, cds = polar
    raw = np.genfromtxt(DATA / "polars" / "raw" / "table_A7.csv", delimiter=",", names=True)
    order = np.argsort(raw["alpha_deg"])
    ra, rp = raw["alpha_deg"][order], raw["cdp"][order]
    inside = (alphas >= ra[0]) & (alphas <= ra[-1])
    new = cds.copy()
    new[inside] = np.interp(alphas[inside], ra, rp)
    return alphas, cls, new


def prandtl(b, f_arg, phi):
    if f_arg <= 0.0:
        return 1.0e-3
    return max(1.0e-3, 2.0 / math.pi * math.acos(min(1.0, math.exp(-f_arg / max(math.sin(phi), 1e-6)))))


def solve_station(r, chord, theta_deg, args, polar, radius, hub):
    alphas, cls, cds = polar
    b, omega = args.blades, args.rpm * 2.0 * math.pi / 60.0
    sigma = b * chord / (2.0 * math.pi * r)
    a, ap = 0.3, 0.0
    for _ in range(500):
        phi = math.atan2((1.0 - a) * args.speed, (1.0 + ap) * omega * r)
        alpha = math.degrees(phi) - theta_deg
        cl = float(np.interp(alpha, alphas, cls))
        cd = args.cd_scale * float(np.interp(alpha, alphas, cds))
        cn = cl * math.cos(phi) + cd * math.sin(phi)
        ct = cl * math.sin(phi) - cd * math.cos(phi)
        f = 1.0
        if args.tip == "on":
            f *= prandtl(b, 0.5 * b * (radius - r) / r, phi)
        f *= prandtl(b, 0.5 * b * (r - hub) / hub, phi)
        sphi, cphi = math.sin(phi), math.cos(phi)
        # Buhl: a from thrust coefficient local CT = sigma (1-a)^2 cn / sin^2(phi)
        ct_loc = sigma * (1.0 - a) ** 2 * cn / (sphi * sphi)
        if ct_loc > 0.96 * f * 1.0 + 0.0 and a > 0.4:
            a_new = (18.0 * f - 20.0 - 3.0 * math.sqrt(ct_loc * (50.0 - 36.0 * f) + 12.0 * f * (3.0 * f - 4.0))) / (36.0 * f - 50.0)
        else:
            a_new = 1.0 / (4.0 * f * sphi * sphi / (sigma * cn) + 1.0)
        ap_new = 1.0 / (4.0 * f * sphi * cphi / (sigma * ct) - 1.0) if abs(ct) > 1e-9 else 0.0
        if not (0.0 <= a_new < 1.0):
            a_new = min(max(a_new, 0.0), 0.99)
        if abs(a_new - a) < 1e-7 and abs(ap_new - ap) < 1e-7:
            a, ap = a_new, ap_new
            break
        a = 0.5 * a + 0.5 * a_new
        ap = 0.5 * ap + 0.5 * ap_new
    wrel2 = ((1.0 - a) * args.speed) ** 2 + ((1.0 + ap) * omega * r) ** 2
    return dict(r=r, a=a, ap=ap, phi=math.degrees(phi), alpha=alpha, cl=cl, cd=cd,
                cn=cn, ct=ct, wrel2=wrel2, chord=chord)


def run(args):
    rr, cc, tw = read_geometry()
    polar = read_polar()
    if args.drag == "pressure":
        polar = pressure_drag(polar)
    radius, hub = float(rr[-1]), float(rr[0])
    rs = np.linspace(hub + 1e-3, radius - 1e-3, args.nstations)
    out = []
    for r in rs:
        chord = float(np.interp(r, rr, cc))
        theta = float(np.interp(r, rr, tw)) + args.pitch
        out.append(solve_station(r, chord, theta, args, polar, radius, hub))
    dr = rs[1] - rs[0]
    thrust = sum(args.blades * 0.5 * args.rho * s["wrel2"] * s["chord"] * s["cn"] * dr for s in out)
    torque = sum(args.blades * 0.5 * args.rho * s["wrel2"] * s["chord"] * s["ct"] * s["r"] * dr for s in out)
    omega = args.rpm * 2.0 * math.pi / 60.0
    return out, thrust, torque, torque * omega, radius


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--speed", type=float, default=7.0)
    p.add_argument("--rpm", type=float, default=71.8667)
    p.add_argument("--rho", type=float, default=1.25249)
    p.add_argument("--pitch", type=float, default=3.0)
    p.add_argument("--blades", type=int, default=2)
    p.add_argument("--tip", choices=("on", "off"), default="on")
    p.add_argument("--cd-scale", type=float, default=1.0, help="diagnostic: scale the polar drag")
    p.add_argument("--drag", choices=("total", "pressure"), default="total")
    p.add_argument("--nstations", type=int, default=200)
    args = p.parse_args()
    out, thrust, torque, power, radius = run(args)
    print(f"BEM U={args.speed} rpm={args.rpm} tip={args.tip} cd_scale={args.cd_scale} drag={args.drag}: P={power/1e3:.3f} kW  Q={torque:.1f} Nm  T_blade={thrust:.1f} N")
    print("r/R   a      phi    alpha  cn     phi_force  R=hypot(cl,cd)")
    for x in STATIONS:
        s = min(out, key=lambda q: abs(q["r"] / radius - x))
        pf = math.degrees(math.atan2(s["ct"], s["cn"]))
        print(f"{x:.2f}  {s['a']:.3f}  {s['phi']:6.2f} {s['alpha']:6.2f} {s['cn']:.3f}  {pf:7.2f}   {math.hypot(s['cl'], s['cd']):.3f}")


if __name__ == "__main__":
    main()
