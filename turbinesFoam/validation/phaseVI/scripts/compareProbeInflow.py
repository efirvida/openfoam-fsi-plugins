#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare the H-sequence five-hole-probe local flow angle with the ALM angle.

Experiment: `sequence_H_probes.csv` column `local_flow_angle_deg` (channel
`5HPxxA`, "5 hole probe xx% local flow angle", degrees) at r/R 0.34/0.51/
0.67/0.84/0.91. The channel is speed dependent (about 5 deg at 5 m/s to 26 deg
at 10 m/s at 34 %), i.e. it behaves like an angle of attack relative to the
blade, NOT like the rotor-plane inflow angle phi (which falls with speed). The
sibling column `spanwise_flow_angle_deg` (`5HPxxF`) is the nearly
speed-independent one and is not compared here.

Simulation: the element CSV `alpha_deg` column, time-averaged over the
revolution window and interpolated linearly in r/R to the probe station
(`actuatorLineElement::calculateForce`: asin(planformNormal . Urel / |Urel|),
Urel from the sampled, spanwise-stripped inflow plus the Dag-Sorensen
induced-velocity correction minus the blade velocity, then the optional flow
curvature correction). Also reported, never compared: `alpha_geom_deg`
(uninduced kinematics) and `inflow_ref_angle_deg` (phi, plane-referenced).

The probe angle definition (reference line, sign) is not documented in the
repository, so "alpha_deg == probe angle" is an inference from the trend. No
upwash/probe correction is applied: none is documented. The probe sits ahead
of the leading edge, where upwash makes it read a larger angle than the angle
at the blade. Treat the delta as an indicator, not a validation metric.

Read-only. Resume segments are joined by comparePhaseVI.read_elements. The
window follows comparePhaseVI (--revolutions DISCARD END overrides it).

Exit codes: 2 window/drift refusal or missing station/column, 3 missing input.
Usage: python3 scripts/compareProbeInflow.py --alm-dir runs/<run> --speed 7
           [--csv out.csv] [--report out.md]
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import statistics
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import comparePhaseVI  # noqa: E402
from compareSectionLoads import converged_window  # noqa: E402

RADIUS = 5.029
PROBE_FILE = "sequence_H_probes.csv"
DEFAULT_EXPERIMENT_DIR = comparePhaseVI.ROOT / "data" / "experiment" / "uae6-archive"
CSV_COLUMNS = (
    "r_over_R", "exp_local_flow_angle_deg", "alm_alpha_deg", "delta_deg",
    "alm_alpha_geom_deg", "alm_inflow_ref_angle_deg",
)
CAVEATS = (
    "alm = element-CSV alpha_deg (angle of relative velocity to the chord line, "
    "incl. induced-velocity correction); inferred match to the probe 'local flow angle'.",
    "Probe angle definition (reference, sign) is not documented in the repository.",
    "Probe upwash/interference is NOT corrected (no documented correction): the probe "
    "is ahead of the leading edge and reads a larger angle than the blade sees.",
    "Station 0.51 reads anomalously high in the experiment (non-monotonic in r/R); "
    "the extraction itself matches channels.csv, so it is a measurement feature.",
    "alm_alpha_geom_deg and alm_inflow_ref_angle_deg are context only, not compared.",
    "Time-averaged data only; blades averaged; linear interpolation in r/R.",
)


class Refusal(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def load_probes(experiment_dir, speed):
    path = Path(experiment_dir) / PROBE_FILE
    if not path.is_file():
        raise Refusal(f"missing probe table: {path}", 3)
    out = {}
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if abs(float(row["wind_speed_m_s"]) - speed) < 1e-9:
                out[round(float(row["r_over_R"]), 4)] = float(row["local_flow_angle_deg"])
    if not out:
        raise Refusal(f"no probe rows at {speed:g} m/s in {path}", 2)
    return out


def element_profiles(alm_dir, lo, hi):
    """{blade: [(r/R, alpha, alpha_geom, phi|None)]} time-averaged per element."""
    try:
        elements = comparePhaseVI.read_elements(Path(alm_dir) / comparePhaseVI.ELEMENT_DIR)
    except FileNotFoundError as exc:
        raise Refusal(f"missing element CSVs: {exc}", 3) from exc
    blades = {}
    for path, rows in elements:
        match = re.search(r"blade(\d+)\.element\d+\.csv$", path.name)
        if not match:
            continue
        window = [r for r in rows if lo <= float(r["time"]) <= hi]
        if not window:
            continue
        for col in ("root_dist", "alpha_deg", "alpha_geom_deg"):
            if col not in window[0]:
                raise Refusal(f"{path}: column {col} absent", 2)
        mean = lambda col: statistics.mean(float(r[col]) for r in window)
        phi = mean("inflow_ref_angle_deg") if "inflow_ref_angle_deg" in window[0] else None
        rr = comparePhaseVI.r_over_r_from_root_dist(mean("root_dist"), RADIUS)
        blades.setdefault(int(match.group(1)), []).append(
            (rr, mean("alpha_deg"), mean("alpha_geom_deg"), phi))
    if not blades:
        raise Refusal("no element rows in the averaging window", 2)
    return {b: sorted(p, key=lambda t: t[0]) for b, p in blades.items()}


def interpolate(profile, x, col):
    if not profile[0][0] <= x <= profile[-1][0]:
        raise Refusal(f"station r/R {x:g} outside the element range "
                      f"[{profile[0][0]:.3f}, {profile[-1][0]:.3f}]", 2)
    for a, b in zip(profile, profile[1:]):
        if a[0] <= x <= b[0]:
            if a[col] is None or b[col] is None:
                return None
            f = 0.0 if b[0] == a[0] else (x - a[0]) / (b[0] - a[0])
            return a[col] + f * (b[col] - a[col])
    return profile[-1][col]


def compare(alm_dir, experiment_dir, speed, revolutions=None, allow_drift=False):
    lo, hi, info = converged_window(alm_dir, speed, "H", revolutions, allow_drift)
    exp = load_probes(experiment_dir, speed)
    blades = element_profiles(alm_dir, lo, hi)
    rows = []
    for station in sorted(exp):
        vals = []
        for col in (1, 2, 3):
            per = [interpolate(p, station, col) for p in blades.values()]
            vals.append(None if None in per else statistics.mean(per))
        alpha, geom, phi = vals
        rows.append({"r_over_R": station, "exp_local_flow_angle_deg": exp[station],
                     "alm_alpha_deg": alpha, "delta_deg": alpha - exp[station],
                     "alm_alpha_geom_deg": geom, "alm_inflow_ref_angle_deg": phi})
    return rows, (lo, hi, info)


def fmt(value):
    return "" if value is None else f"{value:.4f}"


def table_text(rows):
    lines = [f"{'r/R':>5} {'exp':>8} {'ALM':>8} {'delta':>8} {'alpha_geom':>11} {'phi':>8}"]
    for r in rows:
        f = lambda v: "     n/a" if v is None else f"{v:8.2f}"
        lines.append(f"{r['r_over_R']:>5.2f} {f(r['exp_local_flow_angle_deg'])} "
                     f"{f(r['alm_alpha_deg'])} {r['delta_deg']:>+8.2f} "
                     f"{f(r['alm_alpha_geom_deg']):>11} {f(r['alm_inflow_ref_angle_deg'])}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--alm-dir", required=True)
    ap.add_argument("--experiment-dir", default=str(DEFAULT_EXPERIMENT_DIR))
    ap.add_argument("--speed", type=float, default=7.0)
    ap.add_argument("--revolutions", nargs=2, type=float, metavar=("DISCARD", "END"))
    ap.add_argument("--allow-drift", action="store_true")
    ap.add_argument("--csv", help="write the station table here")
    ap.add_argument("--report", help="write a markdown report here")
    args = ap.parse_args(argv)
    try:
        rows, (lo, hi, info) = compare(args.alm_dir, args.experiment_dir, args.speed,
                                       args.revolutions, args.allow_drift)
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    except FileNotFoundError as exc:
        print(f"error: missing input: {exc}", file=sys.stderr)
        return 3
    header = (f"run {args.alm_dir}   H {args.speed:g} m/s   revolutions "
              f"{info['discard_revolutions']:g}..{info['end_revolutions']:g}   "
              f"t in [{lo:.3f}, {hi:.3f}] s")
    text = table_text(rows)
    print(header)
    print("compared: 5HPxxA local flow angle (exp) vs element alpha_deg (ALM); angles in deg\n")
    print(text)
    print("\nCaveats:")
    for item in CAVEATS:
        print(f"- {item}")
    if args.csv:
        with open(args.csv, "w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(CSV_COLUMNS)
            for r in rows:
                writer.writerow([fmt(r[c]) for c in CSV_COLUMNS])
    if args.report:
        with open(args.report, "w") as stream:
            stream.write(f"# Probe vs ALM flow angle\n\n{header}\n\n```\n{text}\n```\n\n"
                         "## Caveats\n\n" + "\n".join(f"- {c}" for c in CAVEATS) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
