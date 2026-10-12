#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Momentum closure of an actuator rotor: applied thrust vs 2 rho U^2 a (1-a).

Why this exists
---------------
Blade-element-momentum theory rests on ``dT = 2 rho U_inf^2 a (1-a) dA``
(Madsen 1988, IEA 2nd symposium, ch. 4), a relation that was never proved and
degrades with loading and with the radial load gradient. This tool measures how
far an actuator-line run is from it: it samples the axial velocity on rings of
planes parallel to the rotor plane, derives ``a(r) = 1 - u/U_inf`` from the
azimuthal mean, and compares ``2 rho U_inf^2 a (1-a) 2 pi r`` with the thrust the
blade elements actually applied per unit radius. It REPORTS a ratio per radius
and an integrated ratio; it never applies a pass/fail threshold. Rows with
``a >= 0.4`` are flagged because the relation is outside its stated validity
there (the turbulent-wake state; the ratio is then not a closure error).

Usage
-----
    # 1. dictionary for ``postProcess`` (rotor axis, origin, radius, wind):
    induction_closure.py write-dict --origin 0 0 12.192 --axis 1 0 0 \\
        --wind 1 0 0 --radius 5.029 --out system/inductionClosureSample
    postProcess -func inductionClosureSample -latestTime   # or -parallel

    # 2. analysis of that output and the element CSVs of the same run:
    induction_closure.py analyse runs/X/postProcessing/inductionClosureSample \\
        runs/X --rho 1 --u-inf 7 --radius 5.029 --wind 1 0 0 \\
        --origin 0 0 12.192 --axis -1 0 0 --t-from 2.9 --t-to 3.339 --json --csv /tmp/closure.csv

``write-dict`` places ``--n-radii`` circle sets between ``--r-min`` and
``--r-max`` (units of R, default 0.05 and 1.3) on each plane at ``--planes``
signed offsets in units of R measured ALONG THE WIND (negative = upstream;
default 0, -0.25, -1). Each circle has uniform ``dTheta``, so every point has
the same azimuthal weight and the plain mean of ``u`` is the azimuthal mean. The
set names carry the geometry (``ring_x<p|m><offset>_r<r/R>``), which is what
``analyse`` reads back; OpenFOAM v2506 writes ``<set>_U.xy`` (``setFormat raw``),
tab-separated ``x y z Ux Uy Uz`` with one row per point and the closing point
not repeated.

``analyse`` reads the element histories
``postProcessing/actuatorLineElements/*/<turbine>.blade<B>.element<N>.csv``
(``x y z`` and ``fx``; ``fx`` is the BLADE force, positive along the wind in
the Phase VI case, so ``--wind`` is the direction ``fx`` is measured along and
the sampled velocity is projected on). A resumed run splits those histories over
several time folders named after the start time; they are united in NUMERIC
folder order ("2" before "10"), a duplicated time keeping the later folder. The
radius of an element is its distance from the rotor axis line (``--origin``,
``--axis``), computed from the ``x y z`` columns row by row and then averaged
over the window (a blade rotates, so its time-averaged position would collapse
onto the axis). ``root_dist`` is NOT a length: in the real CSVs it is the
normalised span fraction 0..1 and is never read. ``--radius`` is R in metres and
scales r/R, which is also the coordinate of the ring sets. ``dr`` is the
central spacing of neighbouring element radii (one-sided at the ends). Each element is time-averaged
over ``--t-from``/``--t-to``; without them the LAST HALF of the available span is
used and the output says so (``default window``).

Which ``--rho`` for the CSV forces
----------------------------------
The CSV ``fx`` is whatever ``actuatorLineElement::writePerf`` writes after
``multiplyForceRho``. The incompressible ``addSup(eqn, fieldI)`` overload (what
``pimpleFoam`` calls, "Force (per unit density)" in the log) never multiplies by
a density, so the Phase VI case (``system/fvOptions.ALM`` carries no ``rho``;
the solver is incompressible with kinematic ``nu``) writes KINEMATIC forces,
N/rho. Pass ``--rho 1`` there: the theory is then kinematic too and the ratio is
independent of the physical density. Pass the physical density (e.g. 1.225) only
for a compressible solver, whose CSV forces are in newtons.

Exit codes: 1 a path or the data it must hold is missing (no ring files, no
element CSVs); 2 usage error (argparse, e.g. ``--rho`` omitted); 3 the data is
unusable (empty time window, malformed file).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np

#: Induction above which the momentum relation is outside its stated validity.
HIGH_INDUCTION = 0.4

#: Fraction of the available span used when no window is given (the last part).
DEFAULT_SPAN_FRACTION = 0.5

RING_NAME = re.compile(r"^ring_x(?P<sign>[pm])(?P<offset>\d+(?:\.\d+)?)_r(?P<rel>\d+(?:\.\d+)?)_U\.xy$")
ELEMENT_NAME = re.compile(r"^(?P<turbine>.+)\.blade(?P<blade>\d+)\.element(?P<element>\d+)\.csv$")


class DataError(ValueError):
    """The data exists but cannot be used (exit code 3)."""


# --------------------------------------------------------------------- write-dict


def _perpendicular(axis: np.ndarray) -> np.ndarray:
    """Unit vector perpendicular to ``axis``, from the coordinate axis it is least aligned with."""
    helper = np.zeros(3)
    helper[int(np.argmin(np.abs(axis)))] = 1.0
    vector = np.cross(axis, helper)
    return vector / np.linalg.norm(vector)


def _vec(values: np.ndarray) -> str:
    return "(" + " ".join(f"{float(v):.10g}" for v in values) + ")"


def _plane_tag(offset: float) -> str:
    return ("m" if offset < 0 else "p") + f"{abs(offset):.4f}"


def render_dict(
    origin: np.ndarray,
    axis: np.ndarray,
    wind: np.ndarray,
    radius: float,
    n_radii: int,
    r_min: float,
    r_max: float,
    planes: list[float],
    d_theta: float,
    name: str,
) -> str:
    axis = axis / np.linalg.norm(axis)
    wind = wind / np.linalg.norm(wind)
    perpendicular = _perpendicular(axis)
    rels = np.linspace(r_min, r_max, n_radii)
    sets = []
    for offset in planes:
        centre = origin + offset * radius * wind
        for rel in rels:
            start = centre + rel * radius * perpendicular
            sets.append(
                f"""    ring_x{_plane_tag(offset)}_r{rel:.4f}
    {{
        type            circle;
        axis            xyz;
        origin          {_vec(centre)};
        circleAxis      {_vec(axis)};
        startPoint      {_vec(start)};
        dTheta          {d_theta:g};
    }}
"""
            )
    body = "\n".join(sets)
    return f"""/*--------------------------------*- C++ -*----------------------------------*\\
  Generated by validation/tools/induction_closure.py write-dict. Do not edit by hand.
  Run: postProcess -func {name} -latestTime
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      {name};
}}

type            sets;
libs            ("libsampling.so");
interpolationScheme cellPoint;
setFormat       raw;
writeControl    writeTime;
fields          (U);

sets
(
{body});
"""


# ---------------------------------------------------------------------- analyse


def _numeric_folder_key(folder: Path) -> tuple[float, str]:
    """Chronological order of a timeName folder: "2" < "10", which text order reverses."""
    try:
        return (float(folder.name), "")
    except ValueError:
        return (float("inf"), folder.name)


def latest_time_folder(samples: Path, sample_time: str | None) -> Path:
    if sample_time is not None:
        folder = samples / sample_time
        if not folder.is_dir():
            raise FileNotFoundError(f"no sample time {sample_time} under {samples}")
        return folder
    folders = [d for d in samples.iterdir() if d.is_dir()]
    if not folders:
        raise FileNotFoundError(f"no time folder under {samples}")
    return max(folders, key=_numeric_folder_key)


def read_rings(
    folder: Path, wind: np.ndarray, u_inf: float
) -> dict[float, list[tuple[float, float]]]:
    """``{plane offset: [(r/R, a), ...]}`` from the ``ring_*_U.xy`` files of one time."""
    planes: dict[float, list[tuple[float, float]]] = {}
    for path in sorted(folder.glob("ring_*_U.xy")):
        match = RING_NAME.match(path.name)
        if match is None:
            continue
        offset = float(match["offset"]) * (-1.0 if match["sign"] == "m" else 1.0)
        try:
            data = np.loadtxt(path, ndmin=2)
        except ValueError as error:
            raise DataError(f"{path}: {error}") from error
        if data.shape[1] != 6:
            raise DataError(f"{path}: expected 6 columns (x y z Ux Uy Uz), got {data.shape[1]}")
        axial = data[:, 3:6] @ wind
        planes.setdefault(offset, []).append((float(match["rel"]), 1.0 - float(axial.mean()) / u_inf))
    if not planes:
        raise FileNotFoundError(f"no ring_*_U.xy files under {folder}")
    return {offset: sorted(rings) for offset, rings in sorted(planes.items())}


def element_files(run_dir: Path) -> dict[tuple[int, int], list[Path]]:
    """``{(blade, element): [csv, ...]}``, each list in chronological folder order."""
    root = run_dir / "postProcessing" / "actuatorLineElements"
    if not root.is_dir():
        raise FileNotFoundError(f"no postProcessing/actuatorLineElements under {run_dir}")
    found: dict[tuple[int, int], list[Path]] = {}
    for folder in sorted((d for d in root.iterdir() if d.is_dir()), key=_numeric_folder_key):
        for path in sorted(folder.glob("*.csv")):
            match = ELEMENT_NAME.match(path.name)
            if match is not None:
                found.setdefault((int(match["blade"]), int(match["element"])), []).append(path)
    if not found:
        raise FileNotFoundError(f"no element CSV under {root}")
    return found


def read_element(
    paths: list[Path], origin: np.ndarray, axis: np.ndarray
) -> dict[float, tuple[float, float]]:
    """Union of one element's split histories: ``{time: (radius, fx)}``, later folder wins.

    The radius is the distance of ``x y z`` from the rotor axis line.
    """
    rows: dict[float, tuple[float, float]] = {}
    for path in paths:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            missing = [c for c in ("time", "x", "y", "z", "fx") if c not in (reader.fieldnames or [])]
            if missing:
                raise DataError(f"{path}: missing column(s) {', '.join(missing)}")
            for row in reader:
                try:
                    position = np.array([float(row["x"]), float(row["y"]), float(row["z"])]) - origin
                    radial = position - np.dot(position, axis) * axis
                    rows[float(row["time"])] = (float(np.linalg.norm(radial)), float(row["fx"]))
                except (TypeError, ValueError):
                    continue
    return rows


def window_means(
    run_dir: Path, origin: np.ndarray, axis: np.ndarray, t_from: float | None, t_to: float | None
) -> tuple[dict[int, dict[str, float]], dict[str, Any]]:
    """Per element index: mean radius and the SUM over blades of the time-mean fx."""
    histories = {
        key: read_element(paths, origin, axis) for key, paths in element_files(run_dir).items()
    }
    times = [t for rows in histories.values() for t in rows]
    if not times:
        raise DataError("element CSVs hold no numeric rows")
    first, last = min(times), max(times)
    defaulted = t_from is None and t_to is None
    if t_to is None:
        t_to = last
    if t_from is None:
        t_from = last - DEFAULT_SPAN_FRACTION * (last - first) if defaulted else first

    elements: dict[int, dict[str, float]] = {}
    used_rows = 0
    for (_, element), rows in sorted(histories.items()):
        inside = [(t, v) for t, v in rows.items() if t_from <= t <= t_to]
        if not inside:
            continue
        used_rows = max(used_rows, len(inside))
        entry = elements.setdefault(element, {"radius": 0.0, "fx": 0.0, "blades": 0.0})
        entry["radius"] += float(np.mean([v[0] for _, v in inside]))
        entry["fx"] += float(np.mean([v[1] for _, v in inside]))
        entry["blades"] += 1.0
    if not elements:
        raise DataError(f"no element row inside the window t = {t_from:g} .. {t_to:g}")
    for entry in elements.values():
        entry["radius"] /= entry["blades"]
    window = {
        "t_from": t_from,
        "t_to": t_to,
        "available": [first, last],
        "defaulted": defaulted,
        "rows": used_rows,
    }
    return elements, window


def _spacings(radii: np.ndarray) -> np.ndarray:
    if radii.size < 2:
        raise DataError("at least two elements are needed to form dr")
    return np.gradient(radii)


def analyse(
    samples: Path,
    run_dir: Path,
    *,
    wind: np.ndarray,
    u_inf: float,
    rho: float,
    radius: float,
    origin: np.ndarray,
    axis: np.ndarray,
    t_from: float | None = None,
    t_to: float | None = None,
    sample_time: str | None = None,
) -> dict[str, Any]:
    wind = wind / np.linalg.norm(wind)
    axis = axis / np.linalg.norm(axis)
    if not samples.is_dir():
        raise FileNotFoundError(f"sample directory not found: {samples}")
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run directory not found: {run_dir}")
    folder = latest_time_folder(samples, sample_time)
    rings_by_plane = read_rings(folder, wind, u_inf)
    elements, window = window_means(run_dir, origin, axis, t_from, t_to)

    order = sorted(elements)
    radii = np.array([elements[n]["radius"] for n in order])
    sorter = np.argsort(radii)
    order = [order[i] for i in sorter]
    radii = radii[sorter]
    dr = _spacings(radii)
    force_sum = np.array([elements[n]["fx"] for n in order])
    actual = force_sum / dr  # sum over blades, per unit radius

    planes = []
    for offset, rings in rings_by_plane.items():
        rel = np.array([r for r, _ in rings])
        a_ring = np.array([a for _, a in rings])
        a = np.interp(radii / radius, rel, a_ring)
        theory = 2.0 * rho * u_inf**2 * a * (1.0 - a) * 2.0 * np.pi * radii
        rows = []
        for i, r in enumerate(radii):
            ratio = actual[i] / theory[i] if abs(theory[i]) > 1e-12 else None
            rows.append(
                {
                    "r_over_R": float(r / radius),
                    "a": float(a[i]),
                    "actual": float(actual[i]),
                    "theory": float(theory[i]),
                    "ratio": None if ratio is None else float(ratio),
                    "flag": bool(a[i] >= HIGH_INDUCTION),
                }
            )
        total_actual = float(np.sum(actual * dr))
        total_theory = float(np.sum(theory * dr))
        planes.append(
            {
                "offset": offset,
                "rows": rows,
                "integrated_actual": total_actual,
                "integrated_theory": total_theory,
                "integrated_ratio": total_actual / total_theory if abs(total_theory) > 1e-12 else None,
            }
        )
    return {
        "samples": str(folder),
        "run": str(run_dir),
        "u_inf": u_inf,
        "rho": rho,
        "radius": radius,
        "window": window,
        "planes": planes,
    }


def _fmt(value: float | None, spec: str) -> str:
    return "n/a" if value is None else format(value, spec)


def render_text(result: dict[str, Any]) -> str:
    window = result["window"]
    lines = [
        f"samples: {result['samples']}",
        f"U_inf = {result['u_inf']:g}  rho = {result['rho']:g}  R = {result['radius']:g}",
    ]
    note = " (default window: last half of the available span)" if window["defaulted"] else ""
    lines.append(
        f"element window: t = {window['t_from']:g} .. {window['t_to']:g}{note}; "
        f"available {window['available'][0]:g} .. {window['available'][1]:g}"
    )
    for plane in result["planes"]:
        lines += [
            "",
            f"plane x/R = {plane['offset']:+g} (along the wind)",
            f"{'r/R':>8} {'a':>9} {'actual':>13} {'theory':>13} {'ratio':>8}  flag",
        ]
        for row in plane["rows"]:
            flag = "a>=0.4" if row["flag"] else ""
            lines.append(
                f"{row['r_over_R']:8.4f} {row['a']:9.5f} {row['actual']:13.6g} "
                f"{row['theory']:13.6g} {_fmt(row['ratio'], '8.4f'):>8}  {flag}"
            )
        lines.append(
            f"integrated: actual {plane['integrated_actual']:.6g}  theory {plane['integrated_theory']:.6g}  "
            f"ratio {_fmt(plane['integrated_ratio'], '.4f')}"
        )
    return "\n".join(lines) + "\n"


def write_csv(result: dict[str, Any], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["plane", "r_over_R", "a", "actual", "theory", "ratio", "flag"])
        for plane in result["planes"]:
            for row in plane["rows"]:
                writer.writerow(
                    [plane["offset"], row["r_over_R"], row["a"], row["actual"], row["theory"],
                     "" if row["ratio"] is None else row["ratio"], int(row["flag"])]
                )  # fmt: skip


# --------------------------------------------------------------------------- CLI


def _vector_arg(parser: argparse.ArgumentParser, name: str, **kwargs: Any) -> None:
    parser.add_argument(name, type=float, nargs=3, metavar=("X", "Y", "Z"), **kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Momentum closure dT = 2 rho U^2 a (1-a) of an actuator rotor.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    write = sub.add_parser("write-dict", help="write the postProcess sample dictionary")
    _vector_arg(write, "--origin", required=True, help="rotor centre")
    _vector_arg(write, "--axis", required=True, help="rotor axis (normal of the rings; sign irrelevant)")
    _vector_arg(write, "--wind", help="wind direction the plane offsets are measured along (default: --axis)")
    write.add_argument("--radius", type=float, required=True, help="rotor radius R")
    write.add_argument("--n-radii", type=int, default=26, help="circle sets per plane (default 26)")
    write.add_argument("--r-min", type=float, default=0.05, help="smallest ring, in R (default 0.05)")
    write.add_argument("--r-max", type=float, default=1.3, help="largest ring, in R (default 1.3)")
    write.add_argument("--planes", type=float, nargs="+", default=[0.0, -0.25, -1.0],
                       help="signed axial offsets in R, negative = upstream (default 0 -0.25 -1)")  # fmt: skip
    write.add_argument("--dtheta", type=float, default=5.0, help="azimuthal step in degrees (default 5)")
    write.add_argument("--name", default="inductionClosureSample", help="function-object name")
    write.add_argument("--out", type=Path, help="output file (default: stdout)")

    ana = sub.add_parser("analyse", help="compare applied thrust with the momentum relation")
    ana.add_argument("samples", type=Path, help="postProcessing/<sample function object> directory")
    ana.add_argument("run_dir", type=Path, help="run directory holding postProcessing/actuatorLineElements")
    ana.add_argument("--rho", type=float, required=True,
                     help="density of the CSV forces: 1 for kinematic (incompressible, Phase VI), else physical")  # fmt: skip
    ana.add_argument("--u-inf", type=float, required=True, help="freestream speed")
    ana.add_argument("--radius", type=float, required=True, help="rotor radius R")
    _vector_arg(ana, "--wind", required=True, help="wind direction (fx positive along it)")
    _vector_arg(ana, "--origin", required=True, help="rotor centre (a point on the axis)")
    _vector_arg(ana, "--axis", required=True, help="rotor axis (sign irrelevant)")
    ana.add_argument("--t-from", type=float, help="start of the element averaging window")
    ana.add_argument("--t-to", type=float, help="end of the element averaging window")
    ana.add_argument("--sample-time", help="time folder of the ring files (default: latest)")
    ana.add_argument("--json", action="store_true", help="machine-readable output")
    ana.add_argument("--csv", type=Path, help="write the per-element table here")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "write-dict":
        axis = np.array(args.axis)
        wind = np.array(args.wind) if args.wind else axis
        if np.linalg.norm(axis) == 0 or np.linalg.norm(wind) == 0:
            print("error: --axis and --wind must be non-zero", file=sys.stderr)
            return 3
        text = render_dict(
            np.array(args.origin), axis, wind, args.radius, args.n_radii,
            args.r_min, args.r_max, args.planes, args.dtheta, args.name,
        )  # fmt: skip
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        return 0

    try:
        result = analyse(
            args.samples,
            args.run_dir,
            wind=np.array(args.wind),
            u_inf=args.u_inf,
            rho=args.rho,
            radius=args.radius,
            origin=np.array(args.origin),
            axis=np.array(args.axis),
            t_from=args.t_from,
            t_to=args.t_to,
            sample_time=args.sample_time,
        )
    except FileNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except DataError as error:
        print(f"error: {error}", file=sys.stderr)
        return 3

    if args.csv:
        write_csv(result, args.csv)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_text(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
