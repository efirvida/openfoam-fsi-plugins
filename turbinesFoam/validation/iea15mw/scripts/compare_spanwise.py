#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Spanwise diagnosis of an IEA 15-240-RWT ALM run.

Reads the per-element actuator-line CSVs of the ALM comparison run
(``runs/iea15mw-asmcmp-alm/`` by default), averages them over the last
``--revs`` rotor revolutions, and writes the spanwise load profile together
with the rotor-level thrust/torque/power coefficients that the module itself
reports.  It exists to answer, from data already on disk and without a new
simulation:

* is the local angle of attack high everywhere (geometry: twist /
  ``curveAngle`` / ``chordMount`` against the WindIO yaml)?
* does alpha match but ``cl`` run high (the polars / the ``Re`` table chosen by
  ``buildPolars.py``)?
* do alpha and ``cl`` match but ``c_t/c_n`` run high (the inflow angle phi,
  i.e. the induced/relative velocity or the force projection)?

Column and unit conventions (verified against
``actuatorLineElement.C`` / ``profileData.C`` / ``axialFlowTurbineALSource.C``):

* ``root_dist`` is the blade-normalised span fraction in ``[0, 1]`` measured
  from the root cutout (``r = HUB_RADIUS + root_dist * BLADE_SPAN``); ``r/R``
  is the projected radius over ``ROTOR_RADIUS``.
* ``alpha_deg`` is the angle actually used for the polar lookup,
  ``alpha_geom_deg`` the geometric one.
* ``c_ref_n``/``c_ref_t`` are the element normal/tangential *coefficients* in
  the flow (plane-of-rotation) reference frame,
  ``c_ref_t = cl*sin(phi) - cd*cos(phi)``,
  ``c_ref_n = cl*cos(phi) + cd*sin(phi)`` with ``phi`` the element inflow
  reference angle (``inflowRefAngle()``).  ``c_t/c_n`` is their ratio.
* ``f_ref_n``/``f_ref_t`` are the element normal/tangential **forces per unit
  span and per unit fluid density** (``0.5 * chord * c_ref * |Vrel|^2``,
  ``normalRefForce()`` / ``tangentialRefForce()``).  The dimensional value in
  N/m is ``f_ref * RHO``; the element *total* force in N is ``f_ref * dr``
  (``dr = BLADE_SPAN / nElements``).  The label "f_ref" in the module CSV
  therefore does **not** denote a total force.

The rotor integration reproduces the module's printed coefficients by using
the module's own normalisation (``axialFlowTurbineALSource.C``):

    C_T (thrust) = N_BLADES * sum_e(f_ref_n * dr) / (0.5 * A * V^2)
    C_Q (torque) = N_BLADES * sum_e(f_ref_t * dr * r) / (0.5 * A * R * V^2)
    C_P (power)  = C_Q * TSR

with ``A = pi * ROTOR_RADIUS^2`` and the run's own tip-speed ratio.  The
module's turbine CSV calls ``C_T`` the ``cd`` column and ``C_Q`` the ``ct``
column; ``C_P`` is its ``cp`` column.

Each element CSV is opened exactly once: the averaging window is taken from
the last time recorded in the module-level ``turbine.csv`` so the (live) run
is never re-read to bound the window.

Usage:
    compare_spanwise.py [--run-dir DIR] [--revs N] [--out FILE]
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent

DEFAULT_RUN_DIR = ROOT / "runs" / "iea15mw-asmcmp-alm"
ELEMENT_DIR = Path("postProcessing") / "actuatorLineElements" / "0"
TURBINE_CSV = Path("postProcessing") / "turbines" / "0" / "turbine.csv"

#: Rated point of the IEA 15-240-RWT case (matches system/fvOptions.ALM).
RHO = 1.225
V_RATED = 10.659
RPM_RATED = 7.518
ROTOR_RADIUS = 120.67532
HUB_RADIUS = 3.97
BLADE_SPAN = 117.0
N_BLADES = 3

#: Default averaging window: the last two rotor revolutions.
DEFAULT_REVS = 2.0

#: Per-element columns averaged over the window.
MEAN_COLUMNS = (
    "root_dist",
    "alpha_deg",
    "alpha_geom_deg",
    "Re",
    "cl",
    "cd",
    "c_ref_n",
    "c_ref_t",
    "f_ref_n",
    "f_ref_t",
)


def _element_index(path: Path) -> int:
    """Element number of ``turbine.blade1.element<N>.csv``."""
    stem = path.name
    marker = ".element"
    start = stem.rfind(marker)
    if start < 0:
        raise ValueError(f"{path}: not an element CSV")
    return int(stem[start + len(marker) : stem.rfind(".")])


def _rows(path: Path):
    """Stream a CSV, skipping blank or partially written rows.

    A live run can expose a truncated last line; such a row is dropped
    instead of aborting the whole comparison.
    """
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            if row is None or row.get("time") in (None, ""):
                continue
            yield row


def _float(row: dict, key: str) -> float:
    return float(row[key])


def last_time(path: Path) -> float | None:
    """Last ``time`` value in a CSV, or ``None`` when it has no rows."""
    value = None
    for row in _rows(path):
        try:
            value = float(row["time"])
        except (TypeError, ValueError):
            continue
    return value


def window_bounds(turbine_csv: Path, revs: float, rpm: float):
    """Averaging window ``[t_start, t_end]`` and the revolution period.

    ``t_end`` is the last time written to the module-level turbine CSV, so the
    per-element CSVs are each read once (to average) and never re-read to find
    the window.
    """
    t_end = last_time(turbine_csv) if turbine_csv.is_file() else None
    if t_end is None:
        raise FileNotFoundError(
            f"{turbine_csv}: no time rows; cannot bound the averaging window"
        )
    period = 60.0 / rpm
    return t_end - revs * period, t_end, period


def average_element(path: Path, t_start: float, t_end: float) -> dict:
    """Time-mean of :data:`MEAN_COLUMNS` for one element in the window.

    The file is streamed once; rows outside the window are skipped.
    """
    sums = {key: 0.0 for key in MEAN_COLUMNS}
    count = 0
    for row in _rows(path):
        try:
            time = float(row["time"])
        except (TypeError, ValueError):
            continue
        if time < t_start or time > t_end:
            continue
        try:
            for key in MEAN_COLUMNS:
                sums[key] += _float(row, key)
        except (TypeError, ValueError):
            continue
        count += 1
    if count == 0:
        raise ValueError(f"{path}: no samples in [{t_start:.6g}, {t_end:.6g}]")
    return {key: value / count for key, value in sums.items()} | {"samples": count}


def average_turbine(path: Path, t_start: float, t_end: float) -> dict:
    """Time-mean of the module-reported ``cp``/``cd``/``ct``/``tsr``."""
    keys = ("tsr", "cp", "cd", "ct")
    sums = {key: 0.0 for key in keys}
    count = 0
    for row in _rows(path):
        try:
            time = float(row["time"])
            if time < t_start or time > t_end:
                continue
            for key in keys:
                sums[key] += _float(row, key)
        except (TypeError, ValueError):
            continue
        count += 1
    if count == 0:
        raise ValueError(f"{path}: no turbine samples in the window")
    return {key: value / count for key, value in sums.items()} | {
        "samples": count
    }


def integrate(profile, n_blades: int, dr: float, tsr: float):
    """Rotor thrust/torque/power coefficients from the spanwise profile.

    ``profile`` holds one averaged element dict per CSV and ``tsr`` is the
    run's own tip-speed ratio.  The module's normalisation is used verbatim
    (see the module docstring): the kinematic element forces (per unit
    density) divided by ``0.5 * rhoRef * A * V^2`` collapse to
    ``0.5 * A * V^2`` because the density cancels.
    """
    area = math.pi * ROTOR_RADIUS**2
    dynamic = 0.5 * area * V_RATED**2
    thrust = 0.0
    torque = 0.0
    for element in profile:
        radius = HUB_RADIUS + element["root_dist"] * BLADE_SPAN
        thrust += element["f_ref_n"] * dr
        torque += element["f_ref_t"] * dr * radius
    thrust *= n_blades
    torque *= n_blades
    c_t = thrust / dynamic
    c_q = torque / (dynamic * ROTOR_RADIUS)
    return {"c_t": c_t, "c_q": c_q, "c_p": c_q * tsr, "tsr": tsr}


def r_over_r(element) -> float:
    return (HUB_RADIUS + element["root_dist"] * BLADE_SPAN) / ROTOR_RADIUS


TABLE_HEADER = (
    "r/R",
    "alpha_deg",
    "alpha_geom_deg",
    "Re",
    "cl",
    "cd",
    "c_n",
    "c_t",
    "Fn_per_len",
    "Ft_per_len",
    "c_t/c_n",
)


def table_row(element) -> tuple:
    """One formatted spanwise row (see :data:`TABLE_HEADER`)."""
    c_n = element["c_ref_n"]
    c_t = element["c_ref_t"]
    ratio = c_t / c_n if c_n else float("nan")
    return (
        f"{r_over_r(element):.4f}",
        f"{element['alpha_deg']:.3f}",
        f"{element['alpha_geom_deg']:.3f}",
        f"{element['Re']:.0f}",
        f"{element['cl']:.4f}",
        f"{element['cd']:.4f}",
        f"{c_n:.4f}",
        f"{c_t:.4f}",
        f"{element['f_ref_n'] * RHO:.1f}",
        f"{element['f_ref_t'] * RHO:.1f}",
        f"{ratio:.4f}",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument(
        "--revs",
        type=float,
        default=DEFAULT_REVS,
        help="averaging window length in rotor revolutions (default: 2)",
    )
    parser.add_argument(
        "--rpm", type=float, default=RPM_RATED, help="rotor speed (default 7.518)"
    )
    parser.add_argument(
        "--out", type=Path, default=None, help="write the spanwise table as CSV"
    )
    args = parser.parse_args(argv)

    run_dir = args.run_dir.resolve()
    element_dir = run_dir / ELEMENT_DIR
    turbine_csv = run_dir / TURBINE_CSV
    if not element_dir.is_dir():
        print(f"error: {element_dir} is not a directory", file=sys.stderr)
        return 1

    files = sorted(element_dir.glob("*.csv"), key=_element_index)
    if not files:
        print(f"error: no element CSVs in {element_dir}", file=sys.stderr)
        return 1

    try:
        t_start, t_end, period = window_bounds(turbine_csv, args.revs, args.rpm)
    except FileNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(
        f"run: {run_dir}\n"
        f"window: last {args.revs:g} revolutions = "
        f"[{t_start:.6g}, {t_end:.6g}] s (period {period:.6g} s, "
        f"{args.rpm:g} rpm)\n"
        f"elements: {len(files)} blade-1 CSVs"
    )

    profile = []
    for path in files:
        try:
            element = average_element(path, t_start, t_end)
        except ValueError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        profile.append(element)

    dr = BLADE_SPAN / len(files)
    module = average_turbine(turbine_csv, t_start, t_end)
    integrated = integrate(profile, N_BLADES, dr, module["tsr"])

    print(f"\nspanwise time-mean ({len(files)} elements, dr = {dr:.5f} m)")
    print("  " + ",".join(TABLE_HEADER))
    for element in profile:
        print("  " + ",".join(table_row(element)))

    if args.out is not None:
        with args.out.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(TABLE_HEADER)
            for element in profile:
                writer.writerow(table_row(element))
        print(f"\nwrote {args.out}")

    print("\nrotor integration (module normalisation, A = pi*R^2, R = "
          f"{ROTOR_RADIUS}, V = {V_RATED}, rhoRef = {RHO})")
    print(
        f"  ours   : C_T {integrated['c_t']:.4f}  "
        f"C_Q {integrated['c_q']:.4f}  C_P {integrated['c_p']:.4f}"
    )
    print(
        f"  module : C_T {module['cd']:.4f}  "
        f"C_Q {module['ct']:.4f}  C_P {module['cp']:.4f}  "
        f"(turbine.csv columns cd/ct/cp; TSR {module['tsr']:.6f})"
    )
    if module["cd"]:
        print(
            f"  ratio  : C_T {integrated['c_t'] / module['cd']:.4f}  "
            f"C_Q {integrated['c_q'] / module['ct']:.4f}  "
            f"C_P {integrated['c_p'] / module['cp']:.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
