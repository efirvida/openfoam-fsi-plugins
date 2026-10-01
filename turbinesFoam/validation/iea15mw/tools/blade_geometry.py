#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Blade geometry table for the IEA 15-240-RWT turbinesFoam case.

The AeroDyn15 blade table is the source of truth for chord, twist and span.
This module decodes it into one documented table consumed by the case:

    r_over_R, radius_m, span_m, chord_m, twist_deg, pitch_axis, chord_mount,
    pitch_deg, airfoil_id

Radius decision (see odd/tasks/iea15mw-geometry-and-polars.md): the published
rotor radius is R = 120.67532316 m (D = 241.35064632 m, NREL/TP-5000-75698 /
tabular xlsx / repo ontology yaml). It is the *projected* in-plane radius:

    R = (HubRad + blade_span) * cos(precone) = 120.97 * cos(4 deg)

so the physical hub radius is 3.97 m (hub diameter 7.94 m, ElastoDyn HubRad),
the structural tip radius is 120.97 m (ElastoDyn TipRad), and the along-blade
span is 117.0 m.

turbinesFoam ALM conventions (axialFlowTurbineALSource.C:134-143):

- column 4 ``chordMount`` is the chordwise mount fraction; 0.25 is the quarter
  chord and the code shifts the element by ``(chordMount - 0.25)*chord``. The
  aerodynamic centre (where the AeroDyn polar Cm is referenced) is the correct
  mount: 0.25 for the FFA-W3 families, 0.316 for SNL-FFA-W3-500 and 0.5 for the
  circular root. The WindIO ``pitch_axis`` (ElastoDyn ``PitchAxis``, 0.5045 ->
  0.3682) is a different, structural quantity and is NOT used as the mount.
- column 5 ``pitch`` uses the Phase VI convention
  ``pitch = -(twist_deg + collective_pitch_deg)``
  (validation/phaseVI/tools/element_data.py). The AeroDyn ``BlTwist`` is
  positive nose-up towards feather (it equals OpenFAST ElastoDyn ``StrcTwst``),
  the same convention the measurement-validated Phase VI blade uses, so the
  same negation applies.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Committed geometry table.
BLADE_CSV = ROOT / "data" / "iea15mw_blade.csv"

#: Authoritative AeroDyn15 blade table (read-only input; override with
#: ``IEA15MW_BLADE_FILE``).  Do not modify.
DEFAULT_BLADE_FILE = Path(
    os.environ.get(
        "IEA15MW_BLADE_FILE",
        "/scratch/leahk/eduardo.donestevez/IEA-15-240-RWT/OpenFAST/"
        "IEA-15-240-RWT/IEA-15-240-RWT_AeroDyn15_blade.dat",
    )
)

#: WindIO yaml used only for the cross-check (read-only; override with
#: ``IEA15MW_WINDIO``).
DEFAULT_WINDIO = Path(
    os.environ.get(
        "IEA15MW_WINDIO",
        "/scratch/leahk/eduardo.donestevez/IEA-15-240-RWT.yaml",
    )
)

# --- P0 radius decision ------------------------------------------------------
#: WindIO hub diameter [m] (NREL/TP-5000-75698 Table ES-1; ElastoDyn HubRad*2).
HUB_DIAMETER = 7.94
#: Physical hub radius [m] = apex-to-root distance (ElastoDyn ``HubRad``).
HUB_RADIUS = HUB_DIAMETER / 2.0
#: Rotor precone [deg] (negative precone sign convention aside, the tilt
#: magnitude that projects the blade onto the rotor plane).
PRECONE_DEG = 4.0
#: Published rotor diameter [m] (tabular xlsx Overview, repo ontology yaml).
ROTOR_DIAMETER_PUBLISHED = 241.35064632
#: Published projected rotor radius [m].
ROTOR_RADIUS_PUBLISHED = ROTOR_DIAMETER_PUBLISHED / 2.0
#: Nominal blade span [m] (NREL/TP-5000-75698 Table 2-1; yaml reference axis).
BLADE_SPAN = 117.0
#: Structural tip radius [m] = HubRad + blade span (ElastoDyn ``TipRad``).
TIP_RADIUS_STRUCTURAL = HUB_RADIUS + BLADE_SPAN

# Column order of the emitted geometry table.
COLUMNS = (
    "r_over_R",
    "radius_m",
    "span_m",
    "chord_m",
    "twist_deg",
    "pitch_axis",
    "chord_mount",
    "pitch_deg",
    "airfoil_id",
    "crv_ac_m",
    "swp_ac_m",
    "crv_ang_deg",
    "axial_distance_m",
    "azimuth_deg",
    "curve_angle_deg",
)

# Distinct airfoil labels and their grid positions (WindIO ``airfoil_position``).
AIRFOIL_POSITION_GRID = (
    0.0,
    0.02,
    0.15,
    0.24517031675566095,
    0.3288439506472435,
    0.4391793464459161,
    0.5376714071084352,
    0.6382076569163737,
    0.7717438522715817,
    1.0,
)
AIRFOIL_POSITION_LABELS = (
    "circular",
    "circular",
    "SNL-FFA-W3-500",
    "FFA-W3-360",
    "FFA-W3-330blend",
    "FFA-W3-301",
    "FFA-W3-270blend",
    "FFA-W3-241",
    "FFA-W3-211",
    "FFA-W3-211",
)
#: Section aerodynamic centre (fraction of chord), from the WindIO airfoils.
AERODYNAMIC_CENTER = {
    "circular": 0.5,
    "SNL-FFA-W3-500": 0.316,
    "FFA-W3-211": 0.25,
    "FFA-W3-241": 0.25,
    "FFA-W3-270blend": 0.25,
    "FFA-W3-301": 0.25,
    "FFA-W3-330blend": 0.25,
    "FFA-W3-360": 0.25,
}


class GeometryError(ValueError):
    """Raised when the blade geometry source is not the expected format."""


def read_blade_table(path: Path | str | None = None) -> list[dict[str, float]]:
    """Parse the AeroDyn15 blade table into per-station dictionaries.

    50 numeric rows are expected; the header block and the unit line have fewer
    than seven numeric tokens and are skipped.
    """
    source = Path(path) if path is not None else DEFAULT_BLADE_FILE
    if not source.exists():
        raise FileNotFoundError(f"AeroDyn15 blade table not found: {source}")
    rows: list[dict[str, float]] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        tokens = line.split()
        try:
            values = [float(token) for token in tokens[:10]]
        except ValueError:
            continue
        if len(values) < 7:
            continue
        rows.append(
            {
                "span": values[0],
                "crv_ac": values[1],
                "swp_ac": values[2],
                "crv_ang": values[3],
                "twist": values[4],
                "chord": values[5],
                "af_id": values[6],
            }
        )
    if len(rows) != 50:
        raise GeometryError(
            f"{source}: expected 50 blade stations, found {len(rows)}"
        )
    if any(b["span"] <= a["span"] for a, b in zip(rows, rows[1:])):
        raise GeometryError(f"{source}: blade span must be strictly increasing")
    return rows


def interpolated_aerodynamic_center(span_fraction: float) -> float:
    """Aerodynamic centre fraction interpolated across the label grid.

    The WindIO ``airfoil_position`` pairs a span fraction with an airfoil label.
    The section aerodynamic centre is linearly interpolated between the labelled
    stations (clamped at the ends), so the transition sections blend the
    cylindrical root (0.5), the SNL-FFA-W3-500 (0.316) and the FFA-W3 families
    (0.25).
    """
    grid = AIRFOIL_POSITION_GRID
    values = [AERODYNAMIC_CENTER[label] for label in AIRFOIL_POSITION_LABELS]
    if span_fraction <= grid[0]:
        return values[0]
    if span_fraction >= grid[-1]:
        return values[-1]
    for i in range(len(grid) - 1):
        if grid[i] <= span_fraction <= grid[i + 1]:
            ratio = (span_fraction - grid[i]) / (grid[i + 1] - grid[i])
            return values[i] + ratio * (values[i + 1] - values[i])
    raise GeometryError(f"span fraction {span_fraction} outside the airfoil grid")


def _asin_degrees(ratio: float) -> float:
    """``asin`` in degrees, clamped so rounding cannot raise a domain error."""
    return math.degrees(math.asin(max(-1.0, min(1.0, ratio))))


def build_rows(
    blade: list[dict[str, float]] | None = None,
    collective_pitch_deg: float = 0.0,
) -> list[dict[str, float]]:
    """Build the documented geometry rows for all 50 stations.

    ``collective_pitch_deg`` is added to the twist before the ALM sign
    negation: ``pitch_deg = -(twist_deg + collective_pitch_deg)``.
    """
    stations = blade if blade is not None else read_blade_table()
    cos_precone = math.cos(math.radians(PRECONE_DEG))
    rows: list[dict[str, float]] = []
    for station in stations:
        span_m = station["span"]
        radius_m = HUB_RADIUS + span_m
        span_fraction = span_m / BLADE_SPAN
        rows.append(
            {
                "r_over_R": radius_m * cos_precone / ROTOR_RADIUS_PUBLISHED,
                "radius_m": radius_m,
                "span_m": span_m,
                "chord_m": station["chord"],
                "twist_deg": station["twist"],
                "pitch_axis": float("nan"),
                "chord_mount": interpolated_aerodynamic_center(span_fraction),
                "pitch_deg": -(station["twist"] + collective_pitch_deg),
                "airfoil_id": station["af_id"],
                # AeroDyn blade shape (out-of-plane / in-plane / curve angle).
                "crv_ac_m": station["crv_ac"],
                "swp_ac_m": station["swp_ac"],
                "crv_ang_deg": station["crv_ang"],
                # turbinesFoam ALM ← AeroDyn mapping (verified against the
                # AeroDyn node locus; see odd/tasks/iea15mw-blade-geometry-mapping.md):
                #   axialDistance = -BlCrvAC   (prebend; +axis_ is upwind)
                #   azimuth       = asin(BlSwpAC / radius)
                #   curveAngle    = BlCrvAng   (tilts the section frame)
                "axial_distance_m": -station["crv_ac"],
                "azimuth_deg": _asin_degrees(station["swp_ac"] / radius_m),
                "curve_angle_deg": station["crv_ang"],
            }
        )
    return rows


def read_geometry(path: Path | str | None = None) -> list[dict[str, float]]:
    """Read the committed geometry CSV into per-station dictionaries."""
    source = Path(path) if path is not None else BLADE_CSV
    rows: list[dict[str, float]] = []
    with source.open(encoding="utf-8") as stream:
        reader = csv.DictReader(
            line for line in stream if not line.startswith("#")
        )
        for record in reader:
            rows.append({key: float(record[key]) for key in COLUMNS})
    if len(rows) != 50:
        raise GeometryError(f"{source}: expected 50 rows, found {len(rows)}")
    return rows


def element_rows(
    path: Path | str | None = None,
    collective_pitch_deg: float = 0.0,
) -> list[list[float]]:
    """turbinesFoam blade element rows ``(axialDistance radius azimuth chord
    chordMount pitch curveAngle)`` for the committed geometry.

    The radius is the along-blade radius (``HubRad + span``); the case should
    apply ``coneAngle`` 4 deg so the ALM projects it onto the rotor plane.
    ``axialDistance`` is the prebend (``-BlCrvAC``), ``azimuth`` the sweep and
    ``curveAngle`` the AeroDyn ``BlCrvAng`` section tilt (the 7th column is
    additive: a 6-column table keeps the legacy zero curve angle).
    """
    rows = read_geometry(path)
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
        for row in rows
    ]


def read_tower_table(
    path: Path | str | None = None,
) -> list[dict[str, float]]:
    """WindIO tower stations ``{z, diameter, cd}`` (z from the ground, m).

    The WindIO grid repeats each station with a sub-millimetre offset to model
    the abrupt diameter steps; the duplicates are collapsed to one station, so
    the returned list has no zero-length segments.
    """
    try:
        import yaml
    except ImportError as error:  # pragma: no cover - depends on environment
        raise GeometryError("PyYAML is required to read the tower") from error

    source = Path(path) if path is not None else DEFAULT_WINDIO
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    tower = data["components"]["tower"]["outer_shape_bem"]
    z_values = [float(v) for v in tower["reference_axis"]["z"]["values"]]
    d_values = [float(v) for v in tower["outer_diameter"]["values"]]
    cd_entry = tower.get("drag_coefficient")
    cd = float(cd_entry["values"][0]) if cd_entry else 1.1
    stations: list[dict[str, float]] = []
    for z, diameter in zip(z_values, d_values):
        if stations and abs(z - stations[-1]["z"]) < 0.01:
            continue
        stations.append({"z": z, "diameter": diameter, "cd": cd})
    return stations


def _format(value: float) -> str:
    text = f"{value:.10g}"
    return "0" if text in ("-0", "") else text


HEADER = [
    "# IEA 15-240-RWT blade geometry, 50 stations.",
    "# Source of truth: IEA-15-240-RWT_AeroDyn15_blade.dat (chord/twist/span/BlAFID).",
    "# Cross-checked against the WindIO yaml outer_shape_bem and the Aeroelast",
    "# loader (max chord difference 1.2e-4 m, max twist difference 1e-5 deg).",
    "#",
    "# Radius decision (P0): published rotor radius R = 120.67532316 m",
    "# (D = 241.35064632 m; NREL/TP-5000-75698 + tabular xlsx + repo ontology",
    "# yaml). R = (HubRad + blade_span)*cos(precone) = 120.97*cos(4 deg).",
    "# Hub radius = 3.97 m (hub diameter 7.94 m, ElastoDyn HubRad).",
    "#",
    "# radius_m = HubRad + span_m (along-blade, tip 120.9699 m, ElastoDyn TipRad).",
    "# r_over_R = radius_m*cos(precone)/R (projected radius; tip exactly 1.0).",
    "# twist_deg = BlTwist (positive nose-up towards feather).",
    "# pitch_deg = -(twist_deg + collective_pitch_deg), collective = 0 (ALM mount).",
    "# chord_mount = section aerodynamic centre (0.25 FFA-W3, 0.316 SNL-FFA-W3-500,",
    "# 0.5 circular), interpolated across the WindIO airfoil_position grid.",
    "# pitch_axis is the structural pitch axis (OpenFAST ElastoDyn PitchAxis); it is",
    "# NOT the ALM chord mount and is recorded here for the audit only.",
    "# airfoil_id = BlAFID (1..50, per-node AeroDyn15 polar index).",
    "#",
    "# Blade shape (AeroDyn v15, see odd/tasks/iea15mw-blade-geometry-mapping.md):",
    "# crv_ac_m = BlCrvAC (prebend, + downwind), swp_ac_m = BlSwpAC (sweep,",
    "# + opposite rotation), crv_ang_deg = BlCrvAng (curve angle = prebend slope).",
    "# axial_distance_m = -BlCrvAC (ALM prebend slot), azimuth_deg = asin(BlSwpAC/",
    "# radius) (ALM sweep), curve_angle_deg = BlCrvAng (ALM section-frame tilt).",
]


def render_csv(rows: list[dict[str, float]] | None = None) -> str:
    """Render the committed geometry CSV (comments start with '#')."""
    data = rows if rows is not None else build_rows()
    lines = list(HEADER)
    lines.append(",".join(COLUMNS))
    for row in data:
        lines.append(",".join(_format(row[key]) for key in COLUMNS))
    return "\n".join(lines) + "\n"


def apply_windio_pitch_axis(
    rows: list[dict[str, float]],
    windio: Path | str | None = None,
) -> float:
    """Fill ``pitch_axis`` from the WindIO yaml; return the max chord difference.

    Read-only cross-check. The yaml chord/twist are interpolated onto each
    station's blade-span fraction and compared to the AeroDyn values; the maximum
    absolute chord difference is returned.
    """
    try:
        import yaml
    except ImportError as error:  # pragma: no cover - depends on environment
        raise GeometryError("PyYAML is required for the WindIO cross-check") from error

    source = Path(windio) if windio is not None else DEFAULT_WINDIO
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    blade = data["components"]["blade"]
    bem = blade.get("outer_shape_bem", blade.get("outer_shape"))

    def values(key: str) -> tuple[list[float], list[float]]:
        entry = bem[key]
        return [float(v) for v in entry["grid"]], [float(v) for v in entry["values"]]

    chord_grid, chord_values = values("chord")
    twist_grid, twist_values = values("twist")
    pa_grid, pa_values = values("pitch_axis")
    # WindIO twist may be radians (windIO 2.x) or degrees (older ontology).
    twist_scale = 180.0 / math.pi if max(abs(v) for v in twist_values) < 1.0 else 1.0

    def interp(grid: list[float], vals: list[float], x: float) -> float:
        if x <= grid[0]:
            return vals[0]
        if x >= grid[-1]:
            return vals[-1]
        for i in range(len(grid) - 1):
            if grid[i] <= x <= grid[i + 1]:
                r = (x - grid[i]) / (grid[i + 1] - grid[i])
                return vals[i] + r * (vals[i + 1] - vals[i])
        raise GeometryError(f"x={x} outside {grid[0]}..{grid[-1]}")

    max_chord_diff = 0.0
    for row in rows:
        eta = row["span_m"] / BLADE_SPAN
        row["pitch_axis"] = interp(pa_grid, pa_values, eta)
        diff = abs(row["chord_m"] - interp(chord_grid, chord_values, eta))
        max_chord_diff = max(max_chord_diff, diff)
        twist_diff = abs(
            row["twist_deg"] - interp(twist_grid, twist_values, eta) * twist_scale
        )
        if twist_diff > 1e-4:
            raise GeometryError(
                f"station {eta:.4f}: twist differs from WindIO by {twist_diff:.3g} deg"
            )
    return max_chord_diff


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the committed geometry CSV is missing or stale",
    )
    parser.add_argument(
        "--blade-file",
        type=Path,
        default=None,
        help="AeroDyn15 blade table (default: IEA15MW_BLADE_FILE)",
    )
    parser.add_argument(
        "--windio",
        type=Path,
        default=None,
        help="WindIO yaml for the read-only cross-check (default: IEA15MW_WINDIO)",
    )
    args = parser.parse_args(argv)

    rows = build_rows(read_blade_table(args.blade_file))
    if args.windio is not None or DEFAULT_WINDIO.exists():
        try:
            diff = apply_windio_pitch_axis(rows, args.windio)
            print(f"WindIO cross-check: max chord difference {diff:.3e} m")
        except (FileNotFoundError, KeyError) as error:
            print(f"WindIO cross-check skipped: {error}", file=sys.stderr)
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
    try:
        display = BLADE_CSV.relative_to(ROOT.parent.parent)
    except ValueError:
        display = BLADE_CSV
    print(f"wrote {display}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
