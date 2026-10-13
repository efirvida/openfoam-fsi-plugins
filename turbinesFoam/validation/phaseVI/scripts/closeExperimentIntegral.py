#!/usr/bin/env python3
"""Close the EXPERIMENT's own spanwise integral against its measured rotor torque.

The UAE6 channel dictionary gives, per instrumented station, the coefficients in
the plane of rotation -- `CTH` (thrust) and `CTQ` (torque) -- beside the
chord-line `CN`/`CT`, the dynamic pressure used to normalize them (`QNORM`, Pa)
and the rotor totals `EAEROTH`/`EAEROTQ`. That is everything needed to check
whether the five stations ARE a sufficient statistic for the rotor torque, which
the simulation comparison alone cannot say.

    T_stations = sum( CTQ * QNORM * chord * dr * r )     over both blades
    Q_stations = sum( CTH * QNORM * chord * dr )         over both blades

and those go against EAEROTQ / EAEROTH. Read-only.

Those channels live only in the raw archive, so `extractUAE6Reference.py` joins
them onto the committed workbook tables; this reads
`data/experiment/sequence_H_{spanwise,performance}.csv` and never touches the
parquet archive.

Usage:
    python3 scripts/closeExperimentIntegral.py --speed 7
"""
from __future__ import annotations

import argparse
import csv
import os
import re

import numpy as np

R, CUT, N_BLADES = 5.029, 0.5083, 2
STATIONS = [0.30, 0.47, 0.63, 0.80, 0.95]


def case_chord(run_dir):
    """(radius, chord) per element from the case's rendered elementData."""
    with open(os.path.join(run_dir, "system/fvOptions")) as stream:
        txt = stream.read()
    m = re.search(r"elementData\s*\((.*?)\)\s*;", txt, re.S)
    if not m:
        m = re.search(r"elementData\s*\n\s*\((.*?)\)\s*;", txt, re.S)
    rows = []
    for tup in re.findall(r"\(([^)]*)\)", m.group(1) if m else ""):
        v = tup.split()
        if len(v) >= 4:
            rows.append((float(v[1]), float(v[3])))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", type=float, default=7.0)
    ap.add_argument("--alm-dir", default="runs/alm-U7-coarse-r2")
    a = ap.parse_args()

    span = list(csv.DictReader(
        open("data/experiment/sequence_H_spanwise.csv")
    ))
    target = [r for r in span if abs(float(r["wind_speed_m_s"]) - a.speed) < 0.6]
    if not target:
        raise SystemExit("no hay estaciones del ensayo para esa velocidad")
    performance = [
        r for r in csv.DictReader(
            open("data/experiment/sequence_H_performance.csv")
        )
        if abs(float(r["wind_speed_m_s"]) - a.speed) < 0.6
    ]
    if not performance:
        raise SystemExit("no hay fila de rotor del ensayo para esa velocidad")
    print(f"ensayo: sequence_H_spanwise.csv {target[0]['file_name']}   "
          f"{len(target)} estaciones")

    def station_row(rr):
        for row in target:
            if abs(float(row["r_over_R"]) - rr) < 1e-9:
                return row
        raise SystemExit(f"falta la estacion {rr:g} del ensayo")

    chords = case_chord(a.alm_dir)
    print(f"cuerdas del caso: {len(chords)} estaciones de (radio, cuerda)")

    def chord_at(rr):
        rs = [c[0] for c in chords]
        cs = [c[1] for c in chords]
        return float(np.interp(rr * R, rs, cs))

    print(f"\n{'est':>4} {'r [m]':>6} {'cuerda':>7} {'QNORM Pa':>9} {'CTH':>7} {'CTQ':>7} {'CN':>7} {'CT':>7} {'dr [m]':>7}")
    rows = []
    for st in STATIONS:
        src = station_row(st)
        q = float(src["qnorm_pa"])
        cth, ctq = float(src["cth"]), float(src["ctq"])
        cn, ct = float(src["cn"]), float(src["ct"])
        c = chord_at(st)
        rows.append({"rr": st, "r": st * R, "chord": c, "q": q,
                     "cth": cth, "ctq": ctq, "cn": cn, "ct": ct})
        print(f"{st*100:>4.0f} {st*R:>6.3f} {c:>7.4f} {q:>9.2f} {cth:>7.4f} {ctq:>7.4f} {cn:>7.4f} {ct:>7.4f} {0:>7}")
    # trapezoidal dr across the five stations, extended to the ends of the span
    for i, e in enumerate(rows):
        lo = (rows[i - 1]["r"] if i > 0 else CUT)
        hi = (rows[i + 1]["r"] if i < len(rows) - 1 else R)
        e["dr"] = (hi - lo) / 2.0
        print(f"     dr[{e['rr']:.2f}] = {e['dr']:.4f} m")

    T_st = sum(e["ctq"] * e["q"] * e["chord"] * e["dr"] * e["r"] for e in rows) * N_BLADES
    Q_st = sum(e["cth"] * e["q"] * e["chord"] * e["dr"] for e in rows) * N_BLADES
    ref = performance[0]
    eaerotq = float(ref["eaerotq_n"])
    eaeroth = float(ref["eaeroth_n"])
    lsstqcor = float(ref["lsstqcor_nm"])
    print(f"\n--- integrado desde las 5 estaciones (x{N_BLADES} palas) ---")
    print(f"  torque   : {T_st:>9.2f} N.m")
    print(f"  empuje   : {Q_st:>9.2f} N")
    print("--- lo que el ensayo mide en el rotor ---")
    print(f"  EAEROTQ  : {eaerotq:>9.2f} N.m")
    print(f"  EAEROTH  : {eaeroth:>9.2f} N")
    print(f"  LSSTQCOR : {lsstqcor:>9.2f} N.m")
    if eaerotq:
        print(f"\n  ratio torque estaciones/EAEROTQ = {T_st/eaerotq:.4f}")
    if eaeroth:
        print(f"  ratio empuje  estaciones/EAEROTH = {Q_st/eaeroth:.4f}")


if __name__ == "__main__":
    main()
