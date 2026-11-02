#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Blade geometry table for the IEA 22-280-RWT turbinesFoam case.

Counterpart of ``validation/iea15mw/tools/blade_geometry.py``; the AeroDyn
parsers, the CSV reader and the ALM element-row conversion are *reused* from
that module (loaded by path, parametrised with the 59-station count) and only
the turbine constants and the WindIO-2.0 readers live here.

The AeroDyn15 blade table is the source of truth for chord, twist, span and
prebend; the output columns are those of the IEA-15 table:

    r_over_R, radius_m, span_m, chord_m, twist_deg, pitch_axis, chord_mount,
    pitch_deg, airfoil_id, crv_ac_m, swp_ac_m, crv_ang_deg, axial_distance_m,
    azimuth_deg, curve_angle_deg

Radius decision (see PROVENANCE.md, evidence-based, NOT inherited from IEA-15):

    R = 142.0 m  (D = 284.0 m)  = ElastoDyn ``TipRad`` = ``HubRad + blade span``

Unlike the IEA-15 (where the published diameter is the *projected* radius
``TipRad*cos(precone)``), the published IEA-22 diameter equals twice the
**along-blade** tip radius: the tabular workbook's tip speed
``101.9203 m/s = 6.853997 rpm * R`` gives ``R = 142.0000`` exactly, and
``2 * 142.0 = 284.0`` is windIO ``rotor_diameter``, the workbook Overview and
the ElastoDyn ``TipRad``. The hub radius is 4.2 m (hub diameter 8.4 m,
ElastoDyn ``HubRad``), so the along-blade span is ``142.0 - 4.2 = 137.8 m``.
The rotor-plane projection of the tip is ``142*cos(4 deg) = 141.65 m`` (before
the 7 m prebend), and is *not* what is called R here.

Hence ``r_over_R = radius_m / R`` (tip exactly 1.0), whereas the IEA-15 table
uses ``radius_m*cos(precone)/R``.

ALM conventions are identical to the IEA-15 package (chord mount = section
aerodynamic centre, ``pitch = -(twist + collective)``, prebend
``axialDistance = -BlCrvAC``, sweep ``azimuth = asin(BlSwpAC/radius)``,
``curveAngle = BlCrvAng``).
"""

from __future__ import annotations

import argparse
import functools
import importlib.util
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_IEA15_TOOLS = ROOT.parent / "iea15mw" / "tools" / "blade_geometry.py"


def _load_iea15():
    """Load the IEA-15 geometry module under a private name (no sys.path edit)."""
    name = "_iea15mw_blade_geometry_shared"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _IEA15_TOOLS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_base = _load_iea15()

GeometryError = _base.GeometryError
COLUMNS = _base.COLUMNS
_format = _base._format

#: Committed geometry table.
BLADE_CSV = ROOT / "data" / "iea22mw_blade.csv"

_SOURCE_ROOT = "/scratch/leahk/eduardo.donestevez/simulations/tmp/iea22-src/repo"

#: Authoritative AeroDyn15 blade table (read-only input; override with
#: ``IEA22MW_BLADE_FILE``).  Do not modify.
DEFAULT_BLADE_FILE = Path(
    os.environ.get(
        "IEA22MW_BLADE_FILE",
        f"{_SOURCE_ROOT}/OpenFAST/IEA-22-280-RWT/IEA-22-280-RWT_AeroDyn15_blade.dat",
    )
)

#: WindIO-2.0 yaml: airfoil aerodynamic centres, tower, drivetrain and the
#: chord/twist cross-check (read-only; override with ``IEA22MW_WINDIO``).
DEFAULT_WINDIO = Path(
    os.environ.get("IEA22MW_WINDIO", f"{_SOURCE_ROOT}/windIO/IEA-22-280-RWT.yaml")
)

# --- Radius decision ----------------------------------------------------------
#: Number of AeroDyn blade stations / per-station polars.
N_STATIONS = 59
#: Hub diameter [m] (windIO ``hub.diameter``, workbook Overview, ElastoDyn
#: ``HubRad*2``).
HUB_DIAMETER = 8.4
#: Physical hub radius [m] (ElastoDyn ``HubRad``).
HUB_RADIUS = HUB_DIAMETER / 2.0
#: Rotor precone [deg] (windIO ``hub.cone_angle`` = 4; ElastoDyn ``PreCone`` = -4
#: in the OpenFAST sign convention).
PRECONE_DEG = 4.0
#: Shaft tilt [deg] (windIO ``drivetrain.uptilt`` = 6; ElastoDyn ``ShftTilt``
#: = -6).  Not applied to the rotor axis of the case (see README).
SHAFT_TILT_DEG = 6.0
#: Published rotor diameter [m] (windIO ``assembly.rotor_diameter``, workbook).
ROTOR_DIAMETER_PUBLISHED = 284.0
#: Published rotor radius [m]; equals the along-blade tip radius (NOT projected).
ROTOR_RADIUS_PUBLISHED = ROTOR_DIAMETER_PUBLISHED / 2.0
#: Along-blade span [m] (AeroDyn ``BlSpn`` tip; windIO blade length).
BLADE_SPAN = 137.8
#: Structural tip radius [m] = HubRad + blade span (ElastoDyn ``TipRad``).
TIP_RADIUS_STRUCTURAL = HUB_RADIUS + BLADE_SPAN
#: Hub height [m] (windIO ``assembly.hub_height``).
HUB_HEIGHT = 170.0


def read_blade_table(path: Path | str | None = None) -> list[dict[str, float]]:
    """Parse the 59-station AeroDyn15 blade table."""
    source = Path(path) if path is not None else DEFAULT_BLADE_FILE
    return _base.read_blade_table(source, n_stations=N_STATIONS)


def read_geometry(path: Path | str | None = None) -> list[dict[str, float]]:
    """Read the committed geometry CSV."""
    source = Path(path) if path is not None else BLADE_CSV
    return _base.read_geometry(source, n_stations=N_STATIONS)


@functools.lru_cache(maxsize=2)
def _parse_windio(source: str, mtime_ns: int) -> dict:
    """Parse the (large, ~10 s) WindIO yaml once per file version.

    The result is shared read-only; callers must not mutate it.
    """
    try:
        import yaml
    except ImportError as error:  # pragma: no cover - depends on environment
        raise GeometryError("PyYAML is required to read the WindIO yaml") from error
    return yaml.safe_load(Path(source).read_text(encoding="utf-8"))


def _load_windio(path: Path | str | None = None) -> dict:
    source = Path(path) if path is not None else DEFAULT_WINDIO
    if not source.exists():
        raise FileNotFoundError(f"WindIO yaml not found: {source}")
    return _parse_windio(str(source), source.stat().st_mtime_ns)


def _interp(grid: list[float], values: list[float], x: float) -> float:
    if x <= grid[0]:
        return values[0]
    if x >= grid[-1]:
        return values[-1]
    for i in range(len(grid) - 1):
        if grid[i] <= x <= grid[i + 1]:
            ratio = (x - grid[i]) / (grid[i + 1] - grid[i])
            return values[i] + ratio * (values[i + 1] - values[i])
    raise GeometryError(f"x={x} outside {grid[0]}..{grid[-1]}")


def aerodynamic_center_grid(
    windio: Path | str | None = None,
) -> tuple[list[float], list[float]]:
    """``(span_fraction, aerodynamic_center)`` knots from the WindIO yaml.

    Each ``outer_shape.airfoils[]`` entry pairs a span fraction with an airfoil
    name; the section aerodynamic centre is that airfoil's
    ``airfoils[].aerodynamic_center`` (0.25 for every FFA-W3 / FB section, 0.5
    for the circular root).
    """
    data = _load_windio(windio)
    centers = {a["name"]: float(a["aerodynamic_center"]) for a in data["airfoils"]}
    positions = data["components"]["blade"]["outer_shape"]["airfoils"]
    grid = [float(p["spanwise_position"]) for p in positions]
    values = [centers[p["name"]] for p in positions]
    if any(b < a for a, b in zip(grid, grid[1:])):
        raise GeometryError("WindIO airfoil spanwise_position is not increasing")
    return grid, values


def _asin_degrees(ratio: float) -> float:
    return math.degrees(math.asin(max(-1.0, min(1.0, ratio))))


def build_rows(
    blade: list[dict[str, float]] | None = None,
    collective_pitch_deg: float = 0.0,
    center_grid: tuple[list[float], list[float]] | None = None,
) -> list[dict[str, float]]:
    """Build the documented geometry rows for all 59 stations.

    ``pitch_deg = -(twist_deg + collective_pitch_deg)`` (ALM mount sign).
    ``pitch_axis`` is NaN: the WindIO-2.0 yaml of the IEA-22 carries no
    structural pitch axis (``section_offset_y`` instead), and it is audit-only.
    """
    stations = blade if blade is not None else read_blade_table()
    grid, values = center_grid if center_grid is not None else aerodynamic_center_grid()
    rows: list[dict[str, float]] = []
    for station in stations:
        span_m = station["span"]
        radius_m = HUB_RADIUS + span_m
        rows.append(
            {
                "r_over_R": radius_m / ROTOR_RADIUS_PUBLISHED,
                "radius_m": radius_m,
                "span_m": span_m,
                "chord_m": station["chord"],
                "twist_deg": station["twist"],
                "pitch_axis": float("nan"),
                "chord_mount": _interp(grid, values, span_m / BLADE_SPAN),
                "pitch_deg": -(station["twist"] + collective_pitch_deg),
                "airfoil_id": station["af_id"],
                "crv_ac_m": station["crv_ac"],
                "swp_ac_m": station["swp_ac"],
                "crv_ang_deg": station["crv_ang"],
                "axial_distance_m": -station["crv_ac"],
                "azimuth_deg": _asin_degrees(station["swp_ac"] / radius_m),
                "curve_angle_deg": station["crv_ang"],
            }
        )
    return rows


def element_rows(
    path: Path | str | None = None,
    collective_pitch_deg: float = 0.0,
) -> list[list[float]]:
    """turbinesFoam blade rows ``(axialDistance radius azimuth chord chordMount
    pitch curveAngle)`` for the committed geometry (along-blade radius, to be
    used with ``coneAngle 4``)."""
    return [
        [
            row["axial_distance_m"],
            row["radius_m"],
            row["azimuth_deg"],
            row["chord_m"],
            row["chord_mount"],
            -(row["twist_deg"] + collective_pitch_deg),
            row["curve_angle_deg"],
        ]
        for row in read_geometry(path)
    ]


def read_tower_table(path: Path | str | None = None) -> list[dict[str, float]]:
    """WindIO tower stations ``{z, diameter, cd}`` (z above sea level, m).

    ``components.tower.reference_axis.z`` and
    ``components.tower.outer_shape.outer_diameter`` share a 31-point grid; the
    tower starts at the transition piece (z = 15 m) and ends at the tower top
    (164.386 m). Duplicated stations (< 1 cm apart) are collapsed.
    """
    tower = _load_windio(path)["components"]["tower"]
    z_values = [float(v) for v in tower["reference_axis"]["z"]["values"]]
    d_values = [float(v) for v in tower["outer_shape"]["outer_diameter"]["values"]]
    if len(z_values) != len(d_values):
        raise GeometryError("tower z and diameter grids differ in length")
    cd = float(tower["outer_shape"]["cd"]["values"][0])
    stations: list[dict[str, float]] = []
    for z, diameter in zip(z_values, d_values):
        if stations and abs(z - stations[-1]["z"]) < 0.01:
            continue
        stations.append({"z": z, "diameter": diameter, "cd": cd})
    return stations


def read_tower_overhang(path: Path | str | None = None) -> float:
    """Hub-to-yaw-axis distance [m] (``drivetrain.outer_shape.overhang``)."""
    drivetrain = _load_windio(path)["components"]["drivetrain"]
    return float(drivetrain["outer_shape"]["overhang"])


def read_nacelle_drivetrain(path: Path | str | None = None) -> dict[str, float]:
    """Nacelle inputs in the IEA-15 reader's contract [m, rad].

    The IEA-22 WindIO has no ``rad_ag/h_m/h_yr``; the generator outer radius
    ``drivetrain.generator.radius`` (4.89 m) is returned as ``rad_ag`` with
    ``h_m = h_yr = 0``, so ``radius = rad_ag + h_m + h_yr`` is that radius.
    ``uptilt`` is converted from degrees (WindIO-2.0) to radians.
    """
    drivetrain = _load_windio(path)["components"]["drivetrain"]
    shape, generator = drivetrain["outer_shape"], drivetrain["generator"]
    return {
        "overhang": float(shape["overhang"]),
        "uptilt": math.radians(float(shape["uptilt"])),
        "generator_length": float(generator["length"]),
        "rad_ag": float(generator["radius"]),
        "h_m": 0.0,
        "h_yr": 0.0,
    }


HEADER = [
    "# IEA 22-280-RWT blade geometry, 59 stations.",
    "# Source of truth: IEA-22-280-RWT_AeroDyn15_blade.dat (chord/twist/span/prebend/BlAFID).",
    "# Cross-checked against the WindIO-2.0 yaml outer_shape chord/twist (see PROVENANCE.md).",
    "#",
    "# Radius decision: R = 142.0 m (D = 284.0 m) = ElastoDyn TipRad = HubRad + span.",
    "# Evidence: workbook tip speed 101.9203 m/s / (6.853997 rpm) = 142.0000 m; windIO",
    "# rotor_diameter 284.0; ElastoDyn TipRad 142.0. UNLIKE the IEA-15, R is NOT the",
    "# precone-projected radius (142*cos(4 deg) = 141.65 m).",
    "# Hub radius = 4.2 m (hub diameter 8.4 m, ElastoDyn HubRad).",
    "#",
    "# radius_m = HubRad + span_m (along-blade, tip 142.0 m).",
    "# r_over_R = radius_m/R (tip exactly 1.0; no cos(precone) factor).",
    "# twist_deg = BlTwist (positive nose-up towards feather).",
    "# pitch_deg = -(twist_deg + collective_pitch_deg), collective = 0 (ALM mount).",
    "# chord_mount = section aerodynamic centre from the WindIO airfoils (0.25 FFA-W3/FB,",
    "# 0.5 circular), interpolated across outer_shape.airfoils[].spanwise_position.",
    "# pitch_axis is NaN: no structural pitch axis in the IEA-22 WindIO-2.0 yaml (audit only).",
    "# airfoil_id = BlAFID (1..59, per-node AeroDyn15 polar index).",
    "#",
    "# crv_ac_m = BlCrvAC (prebend, tip -7 m), swp_ac_m = BlSwpAC, crv_ang_deg = BlCrvAng.",
    "# axial_distance_m = -BlCrvAC (ALM prebend slot), azimuth_deg = asin(BlSwpAC/radius),",
    "# curve_angle_deg = BlCrvAng (ALM section-frame tilt). Same mapping as iea15mw.",
]


def render_csv(rows: list[dict[str, float]] | None = None) -> str:
    """Render the committed geometry CSV (comments start with '#')."""
    data = rows if rows is not None else build_rows()
    lines = list(HEADER)
    lines.append(",".join(COLUMNS))
    for row in data:
        lines.append(",".join(_format(row[key]) for key in COLUMNS))
    return "\n".join(lines) + "\n"


def windio_cross_check(
    rows: list[dict[str, float]], windio: Path | str | None = None
) -> tuple[float, float]:
    """Return ``(max |d chord| [m], max |d twist| [deg])`` against WindIO.

    The WindIO ``outer_shape`` chord/twist are interpolated at
    ``span_m / BLADE_SPAN``; WindIO twist may be in radians or degrees.
    """
    shape = _load_windio(windio)["components"]["blade"]["outer_shape"]
    chord = shape["chord"]
    twist = shape["twist"]
    scale = 180.0 / math.pi if max(abs(v) for v in twist["values"]) < 1.0 else 1.0
    max_chord = max_twist = 0.0
    for row in rows:
        eta = row["span_m"] / BLADE_SPAN
        max_chord = max(
            max_chord,
            abs(row["chord_m"] - _interp(chord["grid"], chord["values"], eta)),
        )
        max_twist = max(
            max_twist,
            abs(
                row["twist_deg"]
                - _interp(twist["grid"], twist["values"], eta) * scale
            ),
        )
    return max_chord, max_twist


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the committed geometry CSV is missing or stale",
    )
    parser.add_argument("--blade-file", type=Path, default=None)
    parser.add_argument("--windio", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        blade = read_blade_table(args.blade_file)
        rows = build_rows(blade, center_grid=aerodynamic_center_grid(args.windio))
        chord_diff, twist_diff = windio_cross_check(rows, args.windio)
    except (FileNotFoundError, GeometryError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(
        f"WindIO cross-check: max chord difference {chord_diff:.3e} m, "
        f"max twist difference {twist_diff:.3e} deg"
    )
    content = render_csv(rows)

    if args.check:
        if not BLADE_CSV.exists():
            print(f"missing geometry file: {BLADE_CSV}", file=sys.stderr)
            return 1
        if BLADE_CSV.read_text(encoding="utf-8") != content:
            print(f"stale geometry file: {BLADE_CSV}", file=sys.stderr)
            return 1
        print(f"geometry up to date: {BLADE_CSV}")
        return 0

    BLADE_CSV.parent.mkdir(parents=True, exist_ok=True)
    BLADE_CSV.write_text(content, encoding="utf-8")
    print(f"wrote {BLADE_CSV.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
