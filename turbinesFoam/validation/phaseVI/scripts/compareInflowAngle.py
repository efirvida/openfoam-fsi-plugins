#!/usr/bin/env python3
"""Compare the force-direction proxy atan2(tangential, axial) at each station.

The experiment supplies CTQ/CTH and the simulation c_ref_t/c_ref_n. Drag
rotates the resultant away from the lift direction, so this is not independent
flow/induction evidence and is NOT the five-hole-probe local flow angle.
No measured experimental alpha or velocity components are inferred.
The separately extracted sequence_H_probes.csv retains the measured probe
channels at their own stations; no conversion to rotor-plane phi is assumed.
--experiment-dir selects the reference CSV directory (default data/experiment).

Read-only; no cluster cost.

Usage:  python3 scripts/compareInflowAngle.py --alm-dir runs/alm-U7-coarse-r2 [--sequence S]
Numeric resume segments replace overlap. The inclusive averaging window and
uninduced kinematics follow comparePhaseVI's sequence/speed configuration.
--revolutions DISCARD END overrides it (integer-truncated, like comparePhaseVI).
Turbine cp/cd drift above 1% exits 2; --allow-drift warns and continues.
"""
from __future__ import annotations
import argparse, csv, math, os, re, statistics
from pathlib import Path

import comparePhaseVI
from compareSectionLoads import converged_window

R, CUT, TSR, U_REF = 5.029, 0.5083, 5.408, 7.0
STATIONS = (0.30, 0.47, 0.63, 0.80, 0.95)


def el_index(path):
    m = re.search(r"element(\d+)", path)
    return int(m.group(1)) if m else 0


def read_table(path):
    return list(csv.DictReader(open(path)))


def sim_profile(alm_dir, lo, hi):
    """(r/R, phi_deg, alpha_eff, alpha_geom) per element, from the plane pair."""
    d = Path(alm_dir) / "postProcessing/actuatorLineElements/0"
    out = []
    for path, history in comparePhaseVI.read_elements(d):
        if not re.search(r"\.blade1\.element\d+\.csv$", path.name):
            continue
        rows = [r for r in history if lo <= float(r["time"]) <= hi]
        if not rows:
            continue
        rr = CUT / R + float(rows[0]["root_dist"]) * (1 - CUT / R)
        q_n = statistics.mean(float(r["c_ref_n"]) for r in rows)
        q_t = statistics.mean(float(r["c_ref_t"]) for r in rows)
        a_e = statistics.mean(float(r["alpha_deg"]) for r in rows)
        a_g = statistics.mean(float(r["alpha_geom_deg"]) for r in rows)
        out.append((rr, math.degrees(math.atan2(q_t, q_n)), a_e, a_g))
    out.sort()
    return out


def interpolate(profile, x, col):
    if x <= profile[0][0]:
        return profile[0][col]
    if x >= profile[-1][0]:
        return profile[-1][col]
    for lo, hi in zip(profile, profile[1:]):
        if lo[0] <= x <= hi[0]:
            f = 0.0 if hi[0] == lo[0] else (x - lo[0]) / (hi[0] - lo[0])
            return lo[col] + f * (hi[col] - lo[col])
    return float("nan")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--alm-dir", default="runs/alm-U7-coarse-r2")
    ap.add_argument("--experiment-dir", default="data/experiment",
                    help="reference CSV directory (default: data/experiment)")
    ap.add_argument("--speed", type=float, default=7.0)
    ap.add_argument("--sequence", choices=("H", "S"), default="H")
    ap.add_argument("--revolutions", nargs=2, type=float, metavar=("DISCARD", "END"),
                    help="override configured revolution bounds (integer-truncated)")
    ap.add_argument("--allow-drift", action="store_true",
                    help="warn and continue if turbine cp/cd drift exceeds 1%%")
    a = ap.parse_args()

    lo, hi, info = converged_window(
        a.alm_dir, a.speed, a.sequence, a.revolutions, a.allow_drift
    )

    exp = {}
    for row in read_table(os.path.join(a.experiment_dir, f"sequence_{a.sequence}_spanwise.csv")):
        if abs(float(row["wind_speed_m_s"]) - a.speed) < 1e-9:
            cth, ctq = float(row["cth"]), float(row["ctq"])
            exp[round(float(row["r_over_R"]), 4)] = math.degrees(math.atan2(ctq, cth))

    cfg = comparePhaseVI.load_config(comparePhaseVI.DEFAULT_CONFIG)
    tsr = float(comparePhaseVI.select_speed(cfg, a.speed, a.sequence)["tsr"])
    prof = sim_profile(a.alm_dir, lo, hi)
    if not prof:
        raise SystemExit("no element rows in the window")
    if any(round(st, 4) not in exp for st in STATIONS):
        raise SystemExit("missing experiment stations for that speed")
    print(f"run {a.alm_dir}   revolutions {info['discard_revolutions']:g}.."
          f"{info['end_revolutions']:g}   t in [{lo:.3f}, {hi:.3f}] s")
    print("force-direction proxy: not independent flow/induction evidence")
    print("phi del ensayo = atan2(CTQ, CTH); phi de la sim = atan2(c_ref_t, c_ref_n)\n")
    print(f"{'r/R':>5} {'phi_exp':>8} {'phi_sim':>8} {'delta':>8} {'phi geom':>9} {'alpha_eff':>10} {'alpha_geom':>11}")
    for st in STATIONS:
        e = exp.get(round(st, 4))
        s = interpolate(prof, st, 1)
        a_e = interpolate(prof, st, 2)
        a_g = interpolate(prof, st, 3)
        omega_r = tsr * a.speed * st
        phi_geom = math.degrees(math.atan(a.speed / omega_r))
        d = s - e if e is not None else float("nan")
        print(f"{st:>5.2f} {e:>8.2f} {s:>8.2f} {d:>+8.2f} {phi_geom:>9.2f} {a_e:>10.2f} {a_g:>11.2f}")
    print("\nphi_geom is uninduced kinematics; its difference from the force proxy does not isolate induction.")
    print("alpha_eff and alpha_geom are simulation columns, not measured experimental alpha.")


if __name__ == "__main__":
    main()
