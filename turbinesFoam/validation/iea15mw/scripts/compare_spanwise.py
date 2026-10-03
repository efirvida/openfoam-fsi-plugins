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
    compare_spanwise.py --profiles-out analysis/spanwise-profiles.csv
    compare_spanwise.py --from-csv analysis/spanwise-profiles.csv

The multi-model snapshot ``analysis/spanwise-profiles.csv`` is written by
``--profiles-out`` (one row per model per element, window mean over the last
``--revs`` revolutions).  It carries the averaging-window bounds as extra
columns (``window_start_s``/``window_end_s``/``revs`` plus the module
``tsr``/``cp_module``/``ct_module``) so the CSV stays machine-readable -- a
single header line and no comment lines -- while still recording the window.
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

ANALYSIS_DIR = ROOT / "analysis"
#: Committed multi-model spanwise snapshot written by :func:`write_profiles_csv`.
PROFILES_CSV = ANALYSIS_DIR / "spanwise-profiles.csv"

#: Header of the snapshot: the required spanwise columns first, then the
#: per-model averaging-window bounds and module coefficients.
PROFILE_HEADER = (
    "model",
    "r_over_R",
    "alpha_deg",
    "cl",
    "cd",
    "c_ref_n",
    "c_ref_t",
    "Fn_per_len_N_m",
    "Ft_per_len_N_m",
    "Re",
    "window_start_s",
    "window_end_s",
    "revs",
    "tsr",
    "cp_module",
    "ct_module",
)

#: Runs snapshotted together.  ``alm-corrpolars`` is written only when its run
#: directory already holds per-element data (it is queued, not started here).
MODEL_RUNS = (
    ("alm", ROOT / "runs" / "iea15mw-asmcmp-alm"),
    ("asm", ROOT / "runs" / "iea15mw-asmcmp-asm"),
    ("asm-mesh", ROOT / "runs" / "iea15mw-asmcmp-asm-mesh"),
    ("alm-corrpolars", ROOT / "runs" / "iea15mw-alm-corrpolars"),
)

FROM_CSV_HEADER = (
    "r/R",
    "alpha_deg",
    "Re",
    "cl",
    "cd",
    "c_n",
    "c_t",
    "Fn_per_len",
    "Ft_per_len",
    "c_t/c_n",
)

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

    The file is streamed once with ``csv.reader`` and header-resolved column
    indices (keeps the three-model snapshot quick); rows outside the window
    and partially written rows are skipped.
    """
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader, None)
        if header is None:
            raise ValueError(f"{path}: empty CSV")
        index = {name.strip(): i for i, name in enumerate(header)}
        try:
            i_time = index["time"]
            columns = [index[key] for key in MEAN_COLUMNS]
        except KeyError as error:
            raise ValueError(f"{path}: missing column {error}") from error
        sums = [0.0] * len(MEAN_COLUMNS)
        count = 0
        for row in reader:
            try:
                time = float(row[i_time])
            except (ValueError, IndexError):
                continue
            if time < t_start or time > t_end:
                continue
            try:
                values = [float(row[i]) for i in columns]
            except (ValueError, IndexError):
                continue
            for j, value in enumerate(values):
                sums[j] += value
            count += 1
    if count == 0:
        raise ValueError(f"{path}: no samples in [{t_start:.6g}, {t_end:.6g}]")
    means = {key: value / count for key, value in zip(MEAN_COLUMNS, sums,
                                                      strict=True)}
    means["samples"] = count
    return means


def average_turbine(path: Path, t_start: float, t_end: float) -> dict:
    """Time-mean of the module-reported ``cp``/``cd``/``ct``/``tsr``."""
    keys = ("tsr", "cp", "cd", "ct")
    sums = dict.fromkeys(keys, 0.0)
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


def _profile_row(model, element, module, t_start, t_end, revs):
    """One snapshot row (see :data:`PROFILE_HEADER`)."""
    return (
        model,
        f"{r_over_r(element):.10g}",
        f"{element['alpha_deg']:.10g}",
        f"{element['cl']:.10g}",
        f"{element['cd']:.10g}",
        f"{element['c_ref_n']:.10g}",
        f"{element['c_ref_t']:.10g}",
        f"{element['f_ref_n'] * RHO:.10g}",
        f"{element['f_ref_t'] * RHO:.10g}",
        f"{element['Re']:.10g}",
        f"{t_start:.10g}",
        f"{t_end:.10g}",
        f"{revs:.10g}",
        f"{module['tsr']:.10g}",
        f"{module['cp']:.10g}",
        f"{module['cd']:.10g}",
    )


def write_profiles_csv(out_path, revs=DEFAULT_REVS, rpm=RPM_RATED,
                       models=MODEL_RUNS):
    """Write the committed multi-model spanwise snapshot.

    Returns ``(rows_written, skipped_models)``.  A model whose run directory
    or per-element data is not present yet is skipped (e.g. the queued
    ``alm-corrpolars`` run), so the snapshot is complete for the runs that
    exist.
    """
    rows_written = 0
    skipped = []
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(PROFILE_HEADER)
        for model, run_dir in models:
            element_dir = run_dir / ELEMENT_DIR
            files = (sorted(element_dir.glob("*.csv"), key=_element_index)
                     if element_dir.is_dir() else [])
            if not files:
                skipped.append(model)
                continue
            try:
                t_start, t_end, _ = window_bounds(
                    run_dir / TURBINE_CSV, revs, rpm)
                module = average_turbine(
                    run_dir / TURBINE_CSV, t_start, t_end)
            except (FileNotFoundError, ValueError):
                skipped.append(model)
                continue
            for path in files:
                element = average_element(path, t_start, t_end)
                writer.writerow(_profile_row(
                    model, element, module, t_start, t_end, revs))
                rows_written += 1
    return rows_written, skipped


def load_profile_rows(csv_path: Path, model: str) -> list[dict]:
    """The snapshot rows of one model, in file order."""
    rows = []
    with csv_path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row.get("model") == model:
                rows.append(row)
    return rows


def print_rows_table(rows, model, source) -> None:
    """Print a snapshot model's spanwise table (the live table minus
    ``alpha_geom_deg``, which the snapshot does not carry)."""
    print(f"\nspanwise snapshot ({model}, {len(rows)} elements) from {source}")
    print("  " + ",".join(FROM_CSV_HEADER))
    for row in rows:
        c_n = float(row["c_ref_n"])
        c_t = float(row["c_ref_t"])
        ratio = c_t / c_n if c_n else float("nan")
        print("  " + ",".join((
            f"{float(row['r_over_R']):.4f}",
            f"{float(row['alpha_deg']):.3f}",
            f"{float(row['Re']):.0f}",
            f"{float(row['cl']):.4f}",
            f"{float(row['cd']):.4f}",
            f"{c_n:.4f}",
            f"{c_t:.4f}",
            f"{float(row['Fn_per_len_N_m']):.1f}",
            f"{float(row['Ft_per_len_N_m']):.1f}",
            f"{ratio:.4f}",
        )))


def integrate_rows(rows):
    """Rotor integration of a snapshot model (returns ``(result, tsr)``)."""
    tsr = float(rows[0]["tsr"])
    profile = []
    for row in rows:
        rr = float(row["r_over_R"])
        profile.append({
            "root_dist": (rr * ROTOR_RADIUS - HUB_RADIUS) / BLADE_SPAN,
            "f_ref_n": float(row["Fn_per_len_N_m"]) / RHO,
            "f_ref_t": float(row["Ft_per_len_N_m"]) / RHO,
        })
    dr = BLADE_SPAN / len(profile)
    return integrate(profile, N_BLADES, dr, tsr), tsr


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
    parser.add_argument(
        "--profiles-out", type=Path, default=None,
        help="write the committed multi-model snapshot and exit",
    )
    parser.add_argument(
        "--from-csv", type=Path, default=None,
        help="print the spanwise table from a committed profiles CSV",
    )
    parser.add_argument(
        "--model", default="alm",
        help="model to print with --from-csv (default: alm)",
    )
    args = parser.parse_args(argv)

    if args.profiles_out is not None:
        written, skipped = write_profiles_csv(
            args.profiles_out, args.revs, args.rpm)
        print(f"wrote {args.profiles_out} ({written} rows)")
        if skipped:
            print("skipped (no per-element data yet): " + ", ".join(skipped))
        return 0

    if args.from_csv is not None:
        rows = load_profile_rows(args.from_csv, args.model)
        if not rows:
            print(f"error: no rows for model {args.model!r} in "
                  f"{args.from_csv}", file=sys.stderr)
            return 1
        t_start = float(rows[0]["window_start_s"])
        t_end = float(rows[0]["window_end_s"])
        revs = float(rows[0]["revs"])
        print(f"model: {args.model}\nsource: {args.from_csv}\n"
              f"window: last {revs:g} revolutions = [{t_start:.6g}, "
              f"{t_end:.6g}] s")
        print_rows_table(rows, args.model, args.from_csv)
        integrated, tsr = integrate_rows(rows)
        module_ct = float(rows[0]["ct_module"])
        module_cp = float(rows[0]["cp_module"])
        module_cq = module_cp / tsr if tsr else float("nan")
        print("\nrotor integration from the snapshot (module normalisation, "
              f"A = pi*R^2, R = {ROTOR_RADIUS}, V = {V_RATED}, "
              f"rhoRef = {RHO})")
        print(f"  ours   : C_T {integrated['c_t']:.4f}  "
              f"C_Q {integrated['c_q']:.4f}  C_P {integrated['c_p']:.4f}")
        print(f"  module : C_T {module_ct:.4f}  C_Q {module_cq:.4f}  "
              f"C_P {module_cp:.4f}  (snapshot columns; TSR {tsr:.6f})")
        if module_ct and module_cq:
            print(f"  ratio  : C_T {integrated['c_t'] / module_ct:.4f}  "
                  f"C_Q {integrated['c_q'] / module_cq:.4f}  "
                  f"C_P {integrated['c_p'] / module_cp:.4f}")
        return 0

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
