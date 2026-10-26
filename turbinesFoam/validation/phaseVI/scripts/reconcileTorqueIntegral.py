#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reconcile Phase VI incompressible ALM element force moments with rotor ct.

Use the written, span-integrated fx/fy/fz, NOT f_ref_t (kinematic force per
span: 0.5*chord*c_ref_t*Urel^2). Compute ((x-origin) cross F) dot axis rowwise,
then average over exactly the rotor samples. No dr, chord interpolation or
mean-product approximation is needed. actuatorLineElement::moment also adds a
section pitching moment along the span: its shaft projection is zero for the
straight radial Phase VI blade. This is not a surface-node torque closure or a
general swept-blade/compressible diagnostic.

Only blade1 is normally written. The mean over blades found is multiplied by
the configured blade count: this is an axisymmetric whole-revolution assumption,
not evidence of equality. Rotor ct can additionally contain hub moments. The
observed ratio is reported, never asserted to agree. Forces and torque are
kinematic (N/rho and N.m/rho); density cancels against the rotor normalization.
Numeric resume segments replace overlap through comparePhaseVI's reader.
Rendered fvOptions supplies origin/axis and nElements for completeness checks;
missing terminal elements, mismatched sample times and surface elements fail.

Defaults: configured sequence/speed TSR and inclusive revolution window.
--discard-revs retains the legacy start override; --end-revs sets the end.
--revolutions DISCARD END uses comparePhaseVI's integer-truncated overrides.
cp/cd drift and short-window refusals follow compareSectionLoads (exit 2;
TSR mismatch exit 3); missing/unusable force data exits 1, without partial output.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import re
import sys

import comparePhaseVI
from compareSectionLoads import converged_window
from checkModelDefinition import parse_dictionary

BANDS = ((0, .30), (.30, .50), (.50, .70), (.70, .90), (.90, .95), (.95, math.inf))


def force_moments(run, start, end, rotor_rows, origin, axis, radius, n_blades, expected):
    """Return rotor-scaled per-element moments; require identical time sampling."""
    times = [row["time"] for row in rotor_rows if start <= row["time"] <= end]
    blades = {}
    for path, history in comparePhaseVI.read_elements(
            Path(run) / "postProcessing/actuatorLineElements/0"):
        match = re.search(r"\.blade(\d+)\.element(\d+)\.csv$", path.name)
        if not match:
            continue
        blade, element = map(int, match.groups())
        rows = [row for row in history if start <= row["time"] <= end]
        if not rows or [row["time"] for row in rows] != times:
            raise ValueError(f"{path.name}: element and rotor window samples differ or are empty")
        moments, radii = [], []
        for row in rows:
            for key in ("x", "y", "z", "fx", "fy", "fz"):
                if key not in row:
                    raise ValueError(f"{path.name}: missing column {key}")
                if not math.isfinite(float(row[key])):
                    raise ValueError(f"{path.name}: non-finite column {key}")
            r = [float(row[k]) - o for k, o in zip(("x", "y", "z"), origin)]
            f = [float(row[k]) for k in ("fx", "fy", "fz")]
            cross = (r[1]*f[2]-r[2]*f[1], r[2]*f[0]-r[0]*f[2], r[0]*f[1]-r[1]*f[0])
            moments.append(sum(v*a for v, a in zip(cross, axis)))
            axial = sum(v*a for v, a in zip(r, axis))
            radii.append(math.sqrt(sum((v-axial*a)**2 for v, a in zip(r, axis))))
        entries = blades.setdefault(blade, {})
        if element in entries:
            raise ValueError(f"duplicate blade/element {blade}/{element}")
        entries[element] = (sum(radii)/len(radii)/radius, sum(moments)/len(moments))
    if not blades or len(blades) > n_blades:
        raise ValueError("missing blade forces or more blade histories than configured blades")
    for blade, entries in blades.items():
        if blade not in expected or set(entries) != set(range(expected[blade])):
            raise ValueError(f"blade{blade}: CSV element indices do not match rendered nElements")
    indices = set(next(iter(blades.values())))
    if indices != set(range(len(indices))) or any(set(b) != indices for b in blades.values()):
        raise ValueError("incomplete or inconsistent element indices across blades")
    scale = n_blades / len(blades)
    return [(rr, q*scale) for entries in blades.values() for rr, q in entries.values()], len(blades)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--alm-dir", default="runs/alm-U7-coarse-r2")
    ap.add_argument("--speed", type=float, default=7.0)
    ap.add_argument("--sequence", choices=("H", "S"), default="H")
    ap.add_argument("--discard-revs", type=float, help="legacy start revolution override")
    ap.add_argument("--end-revs", type=float, help="inclusive end revolution override")
    ap.add_argument("--revolutions", nargs=2, type=float, metavar=("DISCARD", "END"),
                    help="override configured bounds (integer-truncated)")
    ap.add_argument("--allow-drift", action="store_true", help="warn and continue on cp/cd drift")
    ap.add_argument("--origin", nargs=3, type=float, help="rotor origin [m]; default: rendered fvOptions")
    ap.add_argument("--axis", nargs=3, type=float, help="positive torque axis; default: rendered fvOptions")
    a = ap.parse_args(argv)
    if a.revolutions is not None and (a.discard_revs is not None or a.end_revs is not None):
        ap.error("use --revolutions or --discard-revs/--end-revs, not both")
    cfg = comparePhaseVI.load_config(comparePhaseVI.DEFAULT_CONFIG)
    revs = a.revolutions
    if revs is None and (a.discard_revs is not None or a.end_revs is not None):
        revs = (a.discard_revs if a.discard_revs is not None else cfg["solver"]["discard_revolutions"],
                a.end_revs if a.end_revs is not None else cfg["solver"]["end_revolutions"])
    convert = int if a.revolutions is not None else float
    if revs is not None and (convert(revs[0]) < 0 or convert(revs[1]) <= convert(revs[0])):
        ap.error("require 0 <= discard < end (integer truncation for --revolutions)")
    try:
        start, end, info = converged_window(
            a.alm_dir, a.speed, a.sequence, revs, a.allow_drift,
            truncate_revolutions=a.revolutions is not None)
        turbine = cfg["turbine"]
        radius, n_blades = float(turbine["radius"]), int(turbine["n_blades"])
        rendered = parse_dictionary((Path(a.alm_dir) / "system/fvOptions").read_text())
        owners = [value for value in rendered.values() if isinstance(value, dict)
                  and value.get("type") == "axialFlowTurbineALSource"]
        if len(owners) != 1:
            raise ValueError("require one rendered axialFlowTurbineALSource")
        coeffs = owners[0]["axialFlowTurbineALSourceCoeffs"]
        rendered_blades = coeffs["blades"]
        if len(rendered_blades) != n_blades:
            raise ValueError("rendered blade count differs from configured rotor")
        expected = {}
        for name, blade in rendered_blades.items():
            if blade.get("elementType") != "actuatorLineElement":
                raise ValueError("force-moment reconciliation requires ALM, not surface elements")
            expected[int(name.removeprefix("blade"))] = int(blade["nElements"])
        origin = a.origin or [float(v) for v in coeffs["origin"][1:-1]]
        axis = a.axis or [float(v) for v in coeffs["axis"][1:-1]]
        if len(origin) != 3 or len(axis) != 3:
            raise ValueError("rendered origin and axis must have three components")
        norm = math.sqrt(sum(float(v)**2 for v in axis))
        if not norm or not all(math.isfinite(v) for v in (*origin, *axis)):
            raise ValueError("origin and axis must be finite; axis must be nonzero")
        axis = [float(v)/norm for v in axis]
        rows = comparePhaseVI.read_rows_resumed(Path(a.alm_dir) / comparePhaseVI.TURBINE_CSV)
        tsr = float(comparePhaseVI.select_speed(cfg, a.speed, a.sequence)["tsr"])
        period = 2*math.pi*radius/(tsr*a.speed)
        stats = comparePhaseVI.analyse_turbine(rows, start, end, period, False, tsr)
        elements, found = force_moments(a.alm_dir, start, end, rows, origin, axis, radius, n_blades, expected)
        denom = 0.5*math.pi*radius**3*a.speed**2
        declared = stats["ct"]*denom
        total = sum(q for _, q in elements)
        if not math.isfinite(declared) or declared == 0:
            raise ValueError("rotor torque is zero or non-finite; ratio undefined")
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"run {a.alm_dir}   revolutions {info['discard_revolutions']:g}..{info['end_revolutions']:g}"
          f"   t in [{start:.6f}, {end:.6f}] s")
    print(f"blades found: {found}; rotor blades: {n_blades}; scale = {n_blades/found:g}")
    print("kinematic forces: N/rho; torque: N.m/rho; no density multiplier or dr")
    print("Missing blades: axisymmetric mean assumption, not measured rotor closure.")
    print("Straight radial ALM only: shaft pitching-moment projection is zero; rotor may include hub moments.")
    print(f"cp (mean): {stats['cp']:.6f}; ct (mean): {stats['ct']:.9f}; TSR: {stats['tsr']:.6f}")
    print(f"Q rotor / rho: {declared:.6f}")
    print(f"Q elements / rho: {total:.6f}")
    print(f"C_T elements: {total/denom:.9f}; ratio = {total/declared:.6f}")
    print("Radial contributions to scaled element torque [N.m/rho] (sum = Q elements / rho):")
    for lo, hi in BANDS:
        part = sum(q for rr, q in elements if lo <= rr < hi)
        print(f"band {lo:.2f}-{hi:.2f}: {part:.6f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
