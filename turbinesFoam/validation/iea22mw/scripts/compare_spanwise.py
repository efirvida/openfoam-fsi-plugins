#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Spanwise comparison of an IEA-22 ALM run with the OpenFAST reference blocks.

Reads the per-element actuator-line CSVs of blade 1, averages alpha, c_ref_n,
c_ref_t, f_ref_n and f_ref_t over the last ``--revs`` revolutions, maps ``root_dist``
to ``r/R`` with the structural blade geometry (``r = HubRad + root_dist * BladeSpan``,
``R = TipRad``, the same radius the reference store uses) and interpolates the
reference block (``olaf-fvw`` or ``openfast-bem`` of ``analysis/spanwise-references.csv``)
at the ALM radii. Reports per element the angle difference and the coefficient ratios,
and the mean per radial band.

Frames (verified against OpenFAST v5.0.0 ``AeroDyn_IO.f90`` ``BNCn``/``BNCt``/``BNFn``/``BNFt``
and ``actuatorLineElement.C`` ``normalRefCoefficient``/``tangentialRefCoefficient``):

* ALM ``c_ref_n``/``c_ref_t`` are the *rotor-plane* pair, ``Cx = cl cos(phi) + cd sin(phi)``
  (normal to the plane) and ``Cy = cl sin(phi) - cd cos(phi)`` (tangential, along the rotation).
* AeroDyn ``Cn``/``Ct`` (the reference store) are the *chord* pair,
  ``Cn = Cx cos(theta) + Cy sin(theta)`` and ``Ct = -Cx sin(theta) + Cy cos(theta)`` with
  ``theta = BlTwist + collective pitch`` (``phi = alpha + theta``).
* The reference is therefore rotated into the plane frame,
  ``Cx = Cn cos(theta) - Ct sin(theta)``, ``Cy = Cn sin(theta) + Ct cos(theta)``, before the
  ratios ``cx_ratio`` and ``cy_ratio`` (printed ``c_x`` / ``c_y``) are formed. ``cn_ratio``
  keeps the historical definition (ALM plane-normal over AeroDyn chord-normal) and is
  not frame-consistent: it differs from ``cx_ratio`` by about ``cos(theta)``.

Integral check (``--reference-case``, default the run directory of the source under
``runs/``): the reference tangential force per unit span ``Fy = Fn sin(theta) + Ft cos(theta)``
is integrated with ``r`` as lever arm and compared with the OpenFAST ``torque_nm`` of that case
(same for thrust with ``Fx``), and the ALM ``f_ref_t * rho`` integral is compared with the
reference and with the module-reported ``cq``. The per-band torque table shows where the power
difference sits along the span.

Exit codes: 0 comparison written, 1 missing input.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
import blade_geometry as bg  # noqa: E402

RPM_RATED = 6.853997
DEFAULT_BANDS = "0.1-0.3,0.3-0.5,0.5-0.8,0.8-0.95,0.95-1.0"
STORE = HERE.parent / "analysis" / "spanwise-references.csv"
PITCH_DEG = 4.127462
RHO = 1.225
N_BLADES = 3
ROTOR_RADIUS = 142.0
V_RATED = 11.134927
REFERENCE_CASES = {"olaf-fvw": HERE.parent / "runs" / "iea22mw-olaf-dp",
                   "openfast-bem": HERE.parent / "runs" / "scratch-of" / "bem-rated"}


def plane_components(first, second, theta_deg):
    """Rotate a chord-frame pair (n, t) into the rotor-plane pair (x, y); theta = twist + pitch."""
    theta = math.radians(theta_deg)
    return (first * math.cos(theta) - second * math.sin(theta),
            first * math.sin(theta) + second * math.cos(theta))


def theta_deg(r_over_R, pitch):
    table = bg.read_geometry()
    return _interp(r_over_R, [row["r_over_R"] for row in table], [row["twist_deg"] for row in table]) + pitch


def _interp(x, xs, ys):
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for k in range(1, len(xs)):
        if x <= xs[k]:
            weight = (x - xs[k - 1]) / (xs[k] - xs[k - 1])
            return ys[k - 1] + weight * (ys[k] - ys[k - 1])
    return ys[-1]


def read_references(store: Path, source: str) -> dict:
    series: dict[str, list] = {}
    with store.open() as handle:
        for row in csv.DictReader(handle):
            if row["source"] == source:
                series.setdefault(row["quantity"], []).append(
                    (float(row["r_over_R_or_radius_m"]), float(row["value"])))
    return {name: sorted(points) for name, points in series.items()}


def read_elements(run_dir: Path, revs: float, rpm: float) -> list[dict]:
    files = sorted((run_dir / "postProcessing" / "actuatorLineElements").glob("*/turbine.blade1.element*.csv"))
    elements = []
    for path in files:
        with path.open() as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            continue
        t_end = max(float(r["time"]) for r in rows)
        window = [r for r in rows if float(r["time"]) > t_end - revs * 60.0 / rpm]
        mean = lambda key: sum(float(r[key]) for r in window) / len(window)  # noqa: E731
        radius = bg.HUB_RADIUS + float(rows[0]["root_dist"]) * bg.BLADE_SPAN
        elements.append({"r_over_R": radius / bg.TIP_RADIUS_STRUCTURAL, "alpha_deg": mean("alpha_deg"),
                         "c_n": mean("c_ref_n"), "c_t": mean("c_ref_t"),
                         "radius": radius, "f_n": mean("f_ref_n"), "f_t": mean("f_ref_t")})
    return sorted(elements, key=lambda e: e["r_over_R"])


def read_reference_case(case_dir: Path) -> dict | None:
    """Plane-frame force per unit span of the OpenFAST case plus its reported torque and thrust."""
    spanwise, metrics = case_dir / "spanwise.csv", case_dir / "metrics.json"
    if not (spanwise.exists() and metrics.exists()):
        return None
    info = json.loads(metrics.read_text())
    nodes = []
    with spanwise.open() as handle:
        for row in csv.DictReader(handle):
            fx, fy = plane_components(float(row["Fn"]), float(row["Ft"]), theta_deg(float(row["r_over_R"]), info["pitch"]))
            nodes.append({"radius": float(row["radius_m"]), "fx": fx, "fy": fy})
    return {"nodes": sorted(nodes, key=lambda n: n["radius"]), "torque_nm": info["torque_nm"], "thrust_n": info["thrust_n"]}


def ratio(numerator, denominator):
    return numerator / denominator if denominator else float("nan")


def trapezoid(nodes, key, lever=False):
    total = 0.0
    for lo, hi in zip(nodes, nodes[1:]):
        f_lo, f_hi = lo[key] * (lo["radius"] if lever else 1.0), hi[key] * (hi["radius"] if lever else 1.0)
        total += 0.5 * (f_lo + f_hi) * (hi["radius"] - lo["radius"])
    return N_BLADES * total


def module_torque(run_dir: Path, revs: float, rpm: float) -> float | None:
    """Window-mean torque of the module's own ``cq`` (``ct`` column of turbine.csv), in N m."""
    files = sorted((run_dir / "postProcessing" / "turbines").glob("*/turbine.csv"), key=lambda f: float(f.parent.name))
    if not files:
        return None
    with files[-1].open() as handle:
        rows = list(csv.DictReader(handle))
    t_end = float(rows[-1]["time"])
    window = [float(r["ct"]) for r in rows if float(r["time"]) > t_end - revs * 60.0 / rpm]
    cq = sum(window) / len(window)
    return cq * 0.5 * RHO * math.pi * ROTOR_RADIUS**2 * ROTOR_RADIUS * V_RATED**2


def report_integrals(args, elements, bands) -> None:
    case = args.reference_case or REFERENCE_CASES[args.source]
    reference = read_reference_case(case)
    if reference is None:
        print(f"integral check skipped: no spanwise.csv/metrics.json in {case}")
        return
    dr = bg.BLADE_SPAN / len(elements)
    alm_torque = RHO * N_BLADES * sum(e["f_t"] * e["radius"] * dr for e in elements)
    alm_thrust = RHO * N_BLADES * sum(e["f_n"] * dr for e in elements)
    ref_torque, ref_thrust = trapezoid(reference["nodes"], "fy", True), trapezoid(reference["nodes"], "fx")
    for name, alm, ref, reported in (("torque", alm_torque, ref_torque, reference["torque_nm"]),
                                     ("thrust", alm_thrust, ref_thrust, reference["thrust_n"])):
        print(f"integral {name}: reference {ref:.5g} vs reported {reported:.5g} (reference/metrics {ratio(ref, reported):.3f}); "
              f"ALM {alm:.5g} (ALM/reference {ratio(alm, ref):.3f})")
    module = module_torque(args.run_dir, args.revs, args.rpm)
    if module:
        print(f"integral torque: ALM {alm_torque:.5g} vs module cq {module:.5g} (ALM/module {ratio(alm_torque, module):.3f})")
    radii = [n["radius"] for n in reference["nodes"]]
    ref_fy = [n["fy"] for n in reference["nodes"]]
    for low, high in bands:
        sel = [e for e in elements if low <= e["r_over_R"] <= high]
        if not sel:
            continue
        alm_band = RHO * N_BLADES * sum(e["f_t"] * e["radius"] * dr for e in sel)
        ref_band = N_BLADES * sum(_interp(e["radius"], radii, ref_fy) * e["radius"] * dr for e in sel)
        print(f"band {low:g}-{high:g} torque: ALM {ratio(alm_band, alm_torque):.1%} of ALM total, reference {ratio(ref_band, ref_torque):.1%} "
              f"of reference total, ALM-reference {ratio(alm_band - ref_band, ref_torque):+.2%} of reference total")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--revs", type=float, default=2.0)
    parser.add_argument("--rpm", type=float, default=RPM_RATED)
    parser.add_argument("--store", type=Path, default=STORE)
    parser.add_argument("--source", choices=("olaf-fvw", "openfast-bem"), default="olaf-fvw")
    parser.add_argument("--pitch", type=float, default=PITCH_DEG, help="collective pitch of the reference (deg)")
    parser.add_argument("--reference-case", type=Path, help="OpenFAST case dir with spanwise.csv and metrics.json")
    parser.add_argument("--bands", default=DEFAULT_BANDS, help="comma list of LO-HI r/R bands")
    parser.add_argument("--out", type=Path, help="per-element CSV")
    args = parser.parse_args(argv)
    elements = read_elements(args.run_dir, args.revs, args.rpm)
    if not elements:
        print(f"error: no element CSV under {args.run_dir}", file=sys.stderr)
        return 1
    reference = read_references(args.store, args.source)
    rows = []
    for element in elements:
        xs = [p[0] for p in reference["alpha_deg"]]
        ref = {q: _interp(element["r_over_R"], xs, [p[1] for p in reference[q]])
               for q in ("alpha_deg", "cn", "ct")}
        theta = theta_deg(element["r_over_R"], args.pitch)
        ref["cx"], ref["cy"] = plane_components(ref["cn"], ref["ct"], theta)
        rows.append({"r_over_R": element["r_over_R"], "alpha_deg": element["alpha_deg"],
                     "ref_alpha_deg": ref["alpha_deg"], "dalpha_deg": element["alpha_deg"] - ref["alpha_deg"],
                     "cn_ratio": element["c_n"] / ref["cn"] if ref["cn"] else float("nan"),
                     "ref_cx": ref["cx"], "ref_cy": ref["cy"],
                     "cx_ratio": element["c_n"] / ref["cx"] if ref["cx"] else float("nan"),
                     "cy_ratio": element["c_t"] / ref["cy"] if ref["cy"] else float("nan")})
    print(f"run: {args.run_dir}\nreference: {args.source} ({args.store})\n"
          f"window: last {args.revs:g} rev at {args.rpm:g} rpm")
    for band in args.bands.split(","):
        low, high = (float(v) for v in band.split("-"))
        sel = [r for r in rows if low <= r["r_over_R"] <= high]
        if not sel:
            continue
        mean = lambda key: sum(r[key] for r in sel) / len(sel)  # noqa: E731
        print(f"band {band}: n={len(sel)} dalpha {mean('dalpha_deg'):+.2f} deg  "
              f"c_n ratio {mean('cn_ratio'):.3f}  c_x ratio {mean('cx_ratio'):.3f}  c_y ratio {mean('cy_ratio'):.3f}")
    report_integrals(args, elements, [tuple(float(v) for v in b.split("-")) for b in args.bands.split(",")])
    if args.out:
        with args.out.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
