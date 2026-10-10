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
    compare_spanwise.py --run-dir DIR --compare-with DIR2 [--comparison-out FILE]
    compare_spanwise.py --run-dir DIR --compare-with DIR2 --references
    compare_spanwise.py --profiles-out analysis/spanwise-profiles.csv
    compare_spanwise.py --from-csv analysis/spanwise-profiles.csv

With ``--compare-with`` a second run is read with the same window and the two
are compared band by band (``r/R`` 0.3-0.5, 0.5-0.7, 0.7-0.9 and the pooled
0.3-0.9): stations counted, mean ``alpha_deg`` of each run, the alpha difference
(B minus A) and the ``c_n``/``c_t`` ratios B/A.  The runs are paired **by
element index** and must share one ``r/R`` grid -- a different element count or
a station whose ``r/R`` differs is a hard error, never an interpolation.

``--references`` appends to each band row the committed reference models'
station count, band-mean ``alpha_deg``/``cn``/``ct`` and the ratios
``cn_ratio``/``ct_ratio`` = band mean of the reference divided by band mean of
**run A** (the ``--run-dir`` run).  Run A is the baseline, so ``cn_ratio``
answers "is run A's ``c_ref_n`` higher or lower than the reference here?".
Sources are chosen with ``--reference-source`` (repeatable; default
``ccblade-bem`` and ``olaf-fvw``) and read from ``--reference-store``
(``analysis/spanwise-references.csv``, long format).  The store's
``r_over_R_or_radius_m`` column must hold ``r/R``: a source whose values exceed
1.2 carries a radius in metres and is rejected rather than band-averaged as
if it were ``r/R``.  A requested source missing from the store is an error,
and a band with no reference stations is printed ``n/a`` with a station count
of 0, never a synthesised value.

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

#: Campaign spanwise bands in ``r/R``; :data:`OVERALL_BAND` is the pooled band.
COMPARISON_BANDS = ((0.3, 0.5), (0.5, 0.7), (0.7, 0.9))
OVERALL_BAND = (0.3, 0.9)

#: Largest per-station ``r/R`` difference tolerated between the two runs.
R_OVER_R_TOLERANCE = 1e-6

#: Columns of the printed two-run band table.
COMPARISON_HEADER = (
    "band",
    "stations",
    "alpha_a_deg",
    "alpha_b_deg",
    "delta_alpha_deg",
    "c_n_ratio",
    "c_t_ratio",
)

#: Reference sources appended to the band table when ``--references`` is on.
DEFAULT_REFERENCE_SOURCES = ("ccblade-bem", "olaf-fvw")

#: Committed long-format reference store read by ``--references``.
REFERENCE_STORE = ANALYSIS_DIR / "spanwise-references.csv"

#: Reference quantities band-averaged per source (the store's ``quantity``).
REFERENCE_QUANTITIES = ("alpha_deg", "cn", "ct")

#: The store's ``r_over_R_or_radius_m`` column may only carry ``r/R``; a value
#: above this is a radius in metres and must not be band-averaged as ``r/R``.
R_OVER_R_MAX = 1.2


class StationGridMismatchError(Exception):
    """The two runs are not on the same per-element station grid."""


class ReferenceStoreError(Exception):
    """The committed spanwise reference store cannot answer the request."""


class UnknownReferenceSourceError(ReferenceStoreError):
    """A requested reference source is not in the store."""


class ReferenceUnitError(ReferenceStoreError):
    """A reference source's radius column carries metres, not ``r/R``."""


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


def _read_profile(run_dir, time_name, revs, rpm):
    """Averaged spanwise profile of one run, plus its element indices.

    Read-only: the run's CSVs are opened and nothing is written.  Raises
    ``FileNotFoundError`` when the element directory or the module CSV is
    missing and ``ValueError`` when a window holds no samples.
    """
    element_dir = (
        run_dir / "postProcessing" / "actuatorLineElements" / time_name
    )
    turbine_csv = (
        run_dir / "postProcessing" / "turbines" / time_name / "turbine.csv"
    )
    if not element_dir.is_dir():
        raise FileNotFoundError(f"{element_dir} is not a directory")
    files = sorted(element_dir.glob("*.csv"), key=_element_index)
    if not files:
        raise FileNotFoundError(f"no element CSVs in {element_dir}")
    t_start, t_end, _ = window_bounds(turbine_csv, revs, rpm)
    profile = [average_element(path, t_start, t_end) for path in files]
    return profile, [_element_index(path) for path in files]


def compare_profiles(profile_a, label_a, profile_b, label_b,
                     tolerance=R_OVER_R_TOLERANCE):
    """Per-band comparison of two spanwise profiles paired by station index.

    ``label_a``/``label_b`` name the runs in the output and in the error.  A
    different number of stations or a per-station ``r/R`` difference larger
    than ``tolerance`` raises :class:`StationGridMismatchError`: the runs are
    then not on the same mesh and a station-by-station comparison would be
    meaningless.  A band with no stations is kept in the result with
    ``stations == 0`` and ``None`` metrics, never dropped or synthesised.
    """
    if len(profile_a) != len(profile_b):
        raise StationGridMismatchError(
            f"{label_a} has {len(profile_a)} stations but {label_b} has "
            f"{len(profile_b)}: the two runs are not on the same element grid"
        )
    grid_a = [r_over_r(element) for element in profile_a]
    grid_b = [r_over_r(element) for element in profile_b]
    for index, (rr_a, rr_b) in enumerate(zip(grid_a, grid_b, strict=True)):
        if abs(rr_a - rr_b) > tolerance:
            raise StationGridMismatchError(
                f"station {index}: {label_a} r/R = {rr_a:.8g} but {label_b} "
                f"r/R = {rr_b:.8g} differ by more than {tolerance:g}: the two "
                f"runs are not on the same element grid"
            )
    results = []
    for band in COMPARISON_BANDS + (OVERALL_BAND,):
        low, high = band
        stations = [
            i for i, rr in enumerate(grid_a) if low <= rr < high
        ]
        if not stations:
            results.append({
                "band": band,
                "stations": 0,
                "alpha_a": None,
                "alpha_b": None,
                "delta_alpha": None,
                "c_n_ratio": None,
                "c_t_ratio": None,
                "c_n_a": None,
                "c_t_a": None,
            })
            continue
        count = len(stations)
        alpha_a = sum(profile_a[i]["alpha_deg"] for i in stations) / count
        alpha_b = sum(profile_b[i]["alpha_deg"] for i in stations) / count
        c_n_a = sum(profile_a[i]["c_ref_n"] for i in stations) / count
        c_n_b = sum(profile_b[i]["c_ref_n"] for i in stations) / count
        c_t_a = sum(profile_a[i]["c_ref_t"] for i in stations) / count
        c_t_b = sum(profile_b[i]["c_ref_t"] for i in stations) / count
        results.append({
            "band": band,
            "stations": count,
            "alpha_a": alpha_a,
            "alpha_b": alpha_b,
            "delta_alpha": alpha_b - alpha_a,
            "c_n_ratio": c_n_b / c_n_a if c_n_a else None,
            "c_t_ratio": c_t_b / c_t_a if c_t_a else None,
            "c_n_a": c_n_a,
            "c_t_a": c_t_a,
        })
    return results


def load_reference_profiles(store: Path, sources) -> dict:
    """Per-source reference profiles from the long-format store.

    Returns ``{source: [{"r_over_R": r, "alpha_deg": ..., "cn": ...,
    "ct": ...}, ...]}`` with one entry per station, sorted by ``r/R`` and
    carrying only :data:`REFERENCE_QUANTITIES`.

    Raises :class:`UnknownReferenceSourceError` for a source missing from the
    store (naming the available ones) and :class:`ReferenceUnitError` when a
    requested source's ``r_over_R_or_radius_m`` column holds a radius in metres
    (a value outside ``[0, 1.2]``): band-averaging metres as if they were
    ``r/R`` would produce a plausible, wrong table.
    """
    with store.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    available = sorted({
        (row.get("source") or "").strip() for row in rows
    } - {""})
    missing = [source for source in sources if source not in available]
    if missing:
        raise UnknownReferenceSourceError(
            f"reference source {missing[0]!r} is not in {store}; available "
            f"sources: {', '.join(available)}"
        )
    profiles = {}
    for source in sources:
        stations: dict[float, dict] = {}
        radii = set()
        for row in rows:
            if (row.get("source") or "").strip() != source:
                continue
            raw = (row.get("r_over_R_or_radius_m") or "").strip()
            if not raw:
                continue
            try:
                radius = float(raw)
            except ValueError:
                continue
            radii.add(radius)
            quantity = (row.get("quantity") or "").strip()
            if quantity in REFERENCE_QUANTITIES:
                stations.setdefault(radius, {})[quantity] = float(row["value"])
        if radii and not all(0.0 <= radius <= R_OVER_R_MAX for radius in radii):
            raise ReferenceUnitError(
                f"reference source {source!r} in {store}: its "
                f"r_over_R_or_radius_m column carries a radius in metres "
                f"(values up to {max(radii):g}), not r/R in [0, "
                f"{R_OVER_R_MAX:g}]; it cannot be band-averaged with the r/R "
                f"bands"
            )
        profiles[source] = [
            {"r_over_R": radius} | stations[radius]
            for radius in sorted(stations)
        ]
    return profiles


def reference_band_stats(profile, band) -> dict:
    """Station count and band means of one reference profile in ``band``.

    Uses the same ``low <= r/R < high`` convention as the run bands, so the
    columns are directly comparable.  A band with no stations keeps
    ``stations == 0`` and ``None`` means, never a synthesised value.
    """
    low, high = band
    stations = [item for item in profile if low <= item["r_over_R"] < high]
    stats: dict[str, float | None] = {"stations": len(stations)}
    for quantity in REFERENCE_QUANTITIES:
        values = [item[quantity] for item in stations if quantity in item]
        stats[quantity] = sum(values) / len(values) if values else None
    return stats


def attach_references(results, profiles, sources):
    """Add each source's band stats and its ratios to run A to ``results``.

    The ratios are ``band-mean reference / band-mean run A``: run A is the
    ``--run-dir`` baseline.  A ratio is ``None`` when either side is absent.
    """
    enriched = []
    for item in results:
        references = {}
        for source in sources:
            stats = reference_band_stats(profiles[source], item["band"])
            c_n_a = item.get("c_n_a")
            c_t_a = item.get("c_t_a")
            references[source] = stats | {
                "cn_ratio": (
                    stats["cn"] / c_n_a
                    if stats["cn"] is not None and c_n_a else None
                ),
                "ct_ratio": (
                    stats["ct"] / c_t_a
                    if stats["ct"] is not None and c_t_a else None
                ),
            }
        enriched.append(item | {"references": references})
    return enriched


def reference_table_columns(sources) -> tuple:
    """The per-source reference columns appended to the band table header."""
    columns = []
    for source in sources:
        columns += (
            f"{source}_n",
            f"{source}_alpha_deg",
            f"{source}_cn",
            f"{source}_ct",
            f"{source}_cn_ratio",
            f"{source}_ct_ratio",
        )
    return tuple(columns)


def _reference_cell(value, digits=4) -> str:
    """A printed reference value, or ``n/a`` when the band has none."""
    return "n/a" if value is None else f"{value:.{digits}f}"


def _reference_csv_cell(value) -> str:
    """A CSV reference value, or an empty field when the band has none."""
    return "" if value is None else f"{value:.6g}"


def print_comparison(results, label_a, label_b, sources=(), store=None):
    """Print the two-run band table (A is ``label_a``, B is ``label_b``).

    With ``sources`` the committed reference models' band stats and their
    ratios to run A are appended, one group of columns per source; the printed
    header names run A as the baseline the ratios are measured against.
    """
    print(f"\nspanwise comparison: A = {label_a}, B = {label_b}")
    if sources:
        print(
            f"reference band means: ratios are reference / A ({label_a}, the "
            f"--run-dir baseline); store: {store}"
        )
    print("  " + ",".join(COMPARISON_HEADER + reference_table_columns(sources)))
    for item in results:
        low, high = item["band"]
        band = f"{low:g}-{high:g}"
        if not item["stations"]:
            fields = [band, "0", "absent", "absent", "absent", "absent",
                      "absent"]
        else:
            fields = [
                band,
                str(item["stations"]),
                f"{item['alpha_a']:.4f}",
                f"{item['alpha_b']:.4f}",
                f"{item['delta_alpha']:+.4f}",
                f"{item['c_n_ratio']:.4f}",
                f"{item['c_t_ratio']:.4f}",
            ]
        for source in sources:
            reference = item["references"][source]
            fields += [
                str(reference["stations"]),
                _reference_cell(reference["alpha_deg"]),
                _reference_cell(reference["cn"]),
                _reference_cell(reference["ct"]),
                _reference_cell(reference["cn_ratio"]),
                _reference_cell(reference["ct_ratio"]),
            ]
        print("  " + ",".join(fields))


def write_comparison_csv(path, results, label_a, label_b, sources=()):
    """Write the band table as CSV, naming both runs and the band bounds.

    With ``sources`` each row gains that source's reference columns; a band
    with no reference stations writes a count of 0 and empty value fields.
    """
    header = (("run_a", "run_b", "band_lo", "band_hi")
              + COMPARISON_HEADER[1:] + reference_table_columns(sources))
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        for item in results:
            low, high = item["band"]
            if not item["stations"]:
                fields = [label_a, label_b, f"{low:g}", f"{high:g}", 0,
                          "", "", "", "", ""]
            else:
                fields = [
                    label_a, label_b, f"{low:g}", f"{high:g}",
                    item["stations"],
                    f"{item['alpha_a']:.6g}", f"{item['alpha_b']:.6g}",
                    f"{item['delta_alpha']:.6g}",
                    f"{item['c_n_ratio']:.6g}", f"{item['c_t_ratio']:.6g}",
                ]
            for source in sources:
                reference = item["references"][source]
                fields += [
                    reference["stations"],
                    _reference_csv_cell(reference["alpha_deg"]),
                    _reference_csv_cell(reference["cn"]),
                    _reference_csv_cell(reference["ct"]),
                    _reference_csv_cell(reference["cn_ratio"]),
                    _reference_csv_cell(reference["ct_ratio"]),
                ]
            writer.writerow(fields)


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
        "--time",
        default="0",
        help=(
            "time directory of the postProcessing output (default 0). A "
            "RESUMED run writes its own, named after the run's start time: a "
            "case resumed at 31.9209 s keeps its new revolutions in "
            "postProcessing/*/31.9209/, so reading .../0/ would analyse the "
            "history before the resume (the ALM convergence series hit exactly "
            "this)"
        ),
    )
    parser.add_argument(
        "--out", type=Path, default=None, help="write the spanwise table as CSV"
    )
    parser.add_argument(
        "--compare-with", type=Path, default=None,
        help=(
            "second run directory to compare against; prints the per-band "
            "table after the single-run output"
        ),
    )
    parser.add_argument(
        "--compare-time", default=None,
        help=(
            "time directory of the second run's postProcessing output "
            "(default: the same as --time)"
        ),
    )
    parser.add_argument(
        "--comparison-out", type=Path, default=None,
        help="write the two-run band table as CSV",
    )
    parser.add_argument(
        "--references",
        action="store_true",
        help=(
            "append the committed reference models' band means and their "
            "ratios to run A to the --compare-with band table"
        ),
    )
    parser.add_argument(
        "--reference-store",
        type=Path,
        default=REFERENCE_STORE,
        help=(
            "long-format reference store (default: "
            "analysis/spanwise-references.csv)"
        ),
    )
    parser.add_argument(
        "--reference-source",
        action="append",
        default=None,
        help=(
            "reference source in the store to report (repeatable; default: "
            + " and ".join(DEFAULT_REFERENCE_SOURCES) + ")"
        ),
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

    if args.references and args.compare_with is None:
        print(
            "error: --references needs --compare-with, which builds the band "
            "table it annotates",
            file=sys.stderr,
        )
        return 1

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
    element_dir = run_dir / "postProcessing" / "actuatorLineElements" / args.time
    turbine_csv = run_dir / "postProcessing" / "turbines" / args.time / "turbine.csv"
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

    if args.compare_with is not None:
        label_a = str(args.run_dir)
        label_b = str(args.compare_with)
        compare_time = (
            args.compare_time if args.compare_time is not None else args.time
        )
        try:
            profile_b, indices_b = _read_profile(
                args.compare_with.resolve(), compare_time, args.revs, args.rpm
            )
        except (FileNotFoundError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        indices_a = [_element_index(path) for path in files]
        try:
            if indices_a != indices_b:
                raise StationGridMismatchError(
                    f"{label_a} has element indices {indices_a} but {label_b} "
                    f"has {indices_b}: the two runs are not on the same "
                    f"element grid"
                )
            results = compare_profiles(profile, label_a, profile_b, label_b)
        except StationGridMismatchError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        sources = ()
        store = None
        if args.references:
            sources = tuple(dict.fromkeys(
                args.reference_source or DEFAULT_REFERENCE_SOURCES))
            store = args.reference_store
            try:
                references = load_reference_profiles(store, sources)
            except (ReferenceStoreError, OSError) as error:
                print(f"error: {error}", file=sys.stderr)
                return 1
            results = attach_references(results, references, sources)
        print_comparison(results, label_a, label_b, sources, store)
        if args.comparison_out is not None:
            write_comparison_csv(
                args.comparison_out, results, label_a, label_b, sources)
            print(f"\nwrote {args.comparison_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
