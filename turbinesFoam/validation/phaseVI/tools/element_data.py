#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Adapted from mttbrbr/single-actuator-line (main 8284be8c...), GPL-3.0-or-later; see README.md "Attribution and license".
"""Blade and hub element-data generation for the NREL Phase VI case.

turbinesFoam element data rows are
`(axialDistance radius azimuth chord chordMount pitch)` for blades and
`(axialDistance height diameter)` for the hub. The mounting angle uses the
NREL-to-turbinesFoam convention `pitch = -(twist + pitch_deg)`; the NREL
report defines positive twist/pitch towards feather while the axial-flow
element has the opposite sign.

`turbine.pitch_reference` selects where the pitch is measured: `tip` (default,
Model Definition v1.3) follows NREL/TP-500-29955 p.20 (pitch is the angle between
the blade tip chord and the rotor plane) and subtracts the table twist at the
rotor radius first, so the tip mounting equals `-pitch_deg`; `twist-zero` (Model
Definition v1.2, pass it explicitly) adds the pitch to the report twist, which is
zero at the 75 % span station.

Adapted from `mttbrbr/single-actuator-line` (main 8284be8c..., GPL-3.0-or-later).
"""

from __future__ import annotations

from typing import Any

from blade_resample import resample_blade
from case_config import (
    ROOT_CUTOUT_RADIUS,
    ROOT_CYLINDER_END,
    read_blade,
    render_cell_list,
)

# Hub: a lumped cylinder spanning +-root cutout along the rotor axis; the
# diameter is twice the blade root station (TP-500-29955 has no hub table).
HUB_DIAMETER = 2.0 * ROOT_CUTOUT_RADIUS

# Outer radius of the `cylinder` elements of the committed 50-element layout (the first
# 8 elements, i.e. the first 4 table segments, end at the station 1.0675 m). The
# equispaced layout (`turbine.blade_dz`) keeps this boundary.
ELEMENT_CYLINDER_END = 1.0675


PITCH_REFERENCES = ("twist-zero", "tip")
DEFAULT_PITCH_REFERENCE = "tip"


def pitch_reference(cfg: dict[str, Any]) -> str:
    reference = cfg["turbine"].get("pitch_reference", DEFAULT_PITCH_REFERENCE)
    if reference not in PITCH_REFERENCES:
        raise ValueError(f"unknown pitch reference: {reference}; expected one of {', '.join(PITCH_REFERENCES)}")
    return reference


def twist_reference(cfg: dict[str, Any], blade: list[dict[str, float]] | None = None) -> float:
    """Report twist [deg] at which the collective pitch is measured: 0 or the table twist at the rotor radius."""
    if pitch_reference(cfg) == "twist-zero":
        return 0.0
    table = blade if blade is not None else read_blade()
    radius = float(cfg["turbine"]["radius"])
    tip = [row for row in table if abs(row["radius"] - radius) < 1e-9]
    if not tip:
        raise ValueError(f"the blade table has no station at the rotor radius {radius} m")
    return tip[0]["twist"]


def effective_pitch_deg(cfg: dict[str, Any], blade: list[dict[str, float]] | None = None) -> float:
    """Collective pitch relative to the report twist: pitch_deg - twist_tip under `tip`, pitch_deg otherwise."""
    return float(cfg["turbine"]["pitch_deg"]) - twist_reference(cfg, blade)


def blade_stations(cfg: dict[str, Any], blade: list[dict[str, float]] | None = None) -> list[dict[str, float]]:
    """The station table the elements follow: committed, or equispaced when `turbine.blade_dz` is set."""
    stations = blade if blade is not None else read_blade()
    dz = cfg["turbine"].get("blade_dz")
    return resample_blade(stations, float(dz)) if dz else stations


def blade_element_count(cfg: dict[str, Any]) -> int | None:
    """One element per table segment of the equispaced layout; None keeps the configured count."""
    if not cfg["turbine"].get("blade_dz"):
        return None
    return len(blade_stations(cfg)) - 1


def blade_element_rows(cfg: dict[str, Any], blade: list[dict[str, float]] | None = None) -> list[list[float]]:
    """Element data rows for one blade, in turbinesFoam column order."""
    pitch = float(cfg["turbine"]["pitch_deg"])
    # The tip twist comes from the original table, also on the equispaced path.
    twist_zero = twist_reference(cfg, blade)
    stations = blade_stations(cfg, blade)
    rows = []
    for station in stations:
        # NREL twist/pitch is positive towards feather; the axial-flow element
        # convention is the opposite sign.
        turbine_pitch = -((station["twist"] - twist_zero) + pitch)
        rows.append(
            [
                0.0,
                station["radius"],
                0.0,
                station["chord"],
                station["mount"],
                turbine_pitch,
            ]
        )
    return rows


def blade_element_profiles(cfg: dict[str, Any], blade: list[dict[str, float]] | None = None) -> list[str]:
    """`cylinder` inboard of the root cutout, `S809` outboard.

    The count of cylinder elements follows the element interpolation used by
    `axialFlowTurbineALSource`, matching the shared scaffold.
    """
    if cfg["turbine"].get("blade_dz"):
        table = blade_stations(cfg, blade)
        mids = [(a["radius"] + b["radius"]) / 2.0 for a, b in zip(table, table[1:])]
        n_root = sum(1 for mid in mids if mid < ELEMENT_CYLINDER_END)
        return ["cylinder"] * n_root + ["S809"] * (len(mids) - n_root)
    stations = blade if blade is not None else read_blade()
    n_elements = int(cfg["turbine"]["n_elements"])
    radius = float(cfg["turbine"]["radius"])
    span = radius - ROOT_CUTOUT_RADIUS
    n_root = max(1, round(n_elements * (ROOT_CYLINDER_END - ROOT_CUTOUT_RADIUS) / span))
    n_root = min(n_root, n_elements)
    del stations
    return ["cylinder"] * n_root + ["S809"] * (n_elements - n_root)


def hub_element_rows() -> list[list[float]]:
    return [
        [0.0, ROOT_CUTOUT_RADIUS, HUB_DIAMETER],
        [0.0, -ROOT_CUTOUT_RADIUS, HUB_DIAMETER],
    ]


def render_blade_element_data(cfg: dict[str, Any], indent: str = "                    ") -> str:
    return render_cell_list(blade_element_rows(cfg), indent=indent)


def render_hub_element_data(indent: str = "                ") -> str:
    return render_cell_list(hub_element_rows(), indent=indent)


def element_data_summary(cfg: dict[str, Any]) -> dict[str, float | int | str]:
    """Values printed by `scripts/makeElementData.py` and asserted by tests."""
    rows = blade_element_rows(cfg)
    return {
        "stations": len(rows),
        "root_radius": rows[0][1],
        "tip_radius": rows[-1][1],
        "hub_diameter": HUB_DIAMETER,
        "root_mounting_deg": rows[0][5],
        "tip_mounting_deg": rows[-1][5],
    }
