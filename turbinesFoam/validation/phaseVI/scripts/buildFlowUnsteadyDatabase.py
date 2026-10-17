#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Write a FLOWUnsteady rotor database for the NREL Phase VI blade from repository data.

FLOWUnsteady reads a rotor from a small tree of CSV files (`read_rotor`/`read_blade`):

    rotors/phaseVI.csv            Rtip, Rhub, B, blade file, precone
    rotors/phaseVI_blade.csv      names of the distribution files + spline settings
    rotors/phaseVI_{chord,pitch,sweep,height}dist.csv   r/R -> c/R, deg, x/R, z/R
    rotors/phaseVI_airfoils.csv   r/R -> contour file, polar file
    airfoils/s809_rfl.csv         S809 contour, x/c,y/c from the trailing edge over the upper surface
    airfoils/s809-<drag>.csv      S809 polar (Alpha,Cl,Cd,Cm), OSU Re = 1e6, total or pressure drag

Inputs are only the committed Phase VI data: `data/geometry/phaseVI_blade.csv`
(NREL/TP-500-29955 Table A-1), `data/s809/s809_somers_nlr.csv`,
`data/polars/S809_OSU_Re1M_{total,pressure}.dat`. Nothing is read from the
turbinesFoam model, so the file is an independent reference input.

Conventions (checked by the sign run, not assumed):
  * pitch distribution = twist + tip pitch [deg], the angle between the chord and
    the plane of rotation as FLOWUnsteady defines it (`turbine_flag=true` flips the
    sign internally);
  * the leading edge is placed `-chord_mount * chord` behind the pitch axis so the
    section rotates about the Phase VI pitch axis (30 % chord outboard);
  * polars are limited to the OSU measured range (|alpha| <= 20.1 deg); the
    +-180 deg closure of the repository .dat files is NOT written, because
    FLOWUnsteady applies its own Viterna extension (`apply_extrapolate`).

Usage:
    buildFlowUnsteadyDatabase.py OUTDIR [--drag total|pressure] [--pitch-deg 3.0]
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

PHASE_VI = Path(__file__).resolve().parents[1]
R_TIP = 5.029
R_HUB = 0.5083
N_BLADES = 2
ALPHA_MAX = 20.1
POLARS = {
    "total": "S809_OSU_Re1M_total.dat",
    "pressure": "S809_OSU_Re1M_pressure.dat",
}


def read_blade(path: Path) -> list[tuple[float, float, float, float]]:
    """(radius [m], chord [m], twist [deg], chord_mount) per row of Table A-1."""
    rows = []
    with path.open() as stream:
        for line in stream:
            if line.startswith("#") or not line.strip() or line.startswith("radius"):
                continue
            radius, chord, twist, mount = (float(v) for v in line.split(","))
            rows.append((radius, chord, twist, mount))
    return rows


def read_contour(path: Path) -> list[tuple[float, float]]:
    """Closed contour, trailing edge -> upper surface -> leading edge -> lower surface."""
    upper: list[tuple[float, float]] = []
    lower: list[tuple[float, float]] = []
    with path.open() as stream:
        for row in csv.DictReader(line for line in stream if not line.startswith("#")):
            point = (float(row["x_over_c"]), float(row["z_over_c"]))
            target = upper if row["surface"] == "upper" else lower
            if not target or target[-1] != point:
                target.append(point)
    return upper[::-1] + lower


def read_polar(path: Path, alpha_max: float = ALPHA_MAX) -> list[tuple[float, float, float, float]]:
    """(alpha, cl, cd, cm) rows of a repository `.dat` polar within `|alpha| <= alpha_max`."""
    rows = []
    for line in path.read_text().splitlines():
        match = re.fullmatch(r"\(\s*(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*\)", line.strip())
        if not match:
            continue
        alpha, cl, cd, cm = (float(v) for v in match.groups())
        if abs(alpha) <= alpha_max:
            rows.append((alpha, cl, cd, cm))
    return sorted(rows)


def write_csv(path: Path, header: list[str], rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def build(out_dir: Path, drag: str, pitch_deg: float) -> None:
    blade = [row for row in read_blade(PHASE_VI / "data/geometry/phaseVI_blade.csv") if row[0] >= R_HUB]
    rotors = out_dir / "rotors"
    name = "phaseVI"
    write_csv(rotors / f"{name}_chorddist.csv", ["r/R", "c/R"],
              [(r / R_TIP, c / R_TIP) for r, c, _, _ in blade])
    write_csv(rotors / f"{name}_pitchdist.csv", ["r/R", "pitch (deg)"],
              [(r / R_TIP, tw + pitch_deg) for r, _, tw, _ in blade])
    write_csv(rotors / f"{name}_sweepdist.csv", ["r/R", "LE x/R"],
              [(r / R_TIP, -m * c / R_TIP) for r, c, _, m in blade])
    write_csv(rotors / f"{name}_heightdist.csv", ["r/R", "LE z/R"],
              [(r / R_TIP, 0.0) for r, _, _, _ in blade])
    polar_name = f"s809-{drag}.csv"
    write_csv(rotors / f"{name}_airfoils.csv", ["r/R", "Contour file", "Aero file"],
              [(0.0, "s809_rfl.csv", polar_name), (1.0, "s809_rfl.csv", polar_name)])
    write_csv(rotors / f"{name}_blade.csv", ["property", "file", "description"], [
        ("chorddist", f"{name}_chorddist.csv", " Chord distribution"),
        ("pitchdist", f"{name}_pitchdist.csv", " Pitch distribution"),
        ("sweepdist", f"{name}_sweepdist.csv", " LE sweep distribution"),
        ("heightdist", f"{name}_heightdist.csv", " LE height distribution"),
        ("airfoil_files", f"{name}_airfoils.csv", " Airfoil distribution"),
        ("spl_k", 3, " Spline order"),
        ("spl_s", "1.0e-8", " Spline smoothing"),
    ])
    write_csv(rotors / f"{name}.csv", ["property", "file", "description"], [
        ("Rtip", R_TIP, " (m) Radius of blade tip"),
        ("Rhub", R_HUB, " (m) Radius of hub"),
        ("B", N_BLADES, " Number of blades"),
        ("blade", f"{name}_blade.csv", " Blade file"),
        ("precone", 0.0, " (deg) Precone"),
    ])
    airfoils = out_dir / "airfoils"
    write_csv(airfoils / "s809_rfl.csv", ["x/c", "y/c"], read_contour(PHASE_VI / "data/s809/s809_somers_nlr.csv"))
    write_csv(airfoils / polar_name, ["Alpha", "Cl", "Cd", "Cm"],
              read_polar(PHASE_VI / "data/polars" / POLARS[drag]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--drag", choices=sorted(POLARS), default="total")
    parser.add_argument("--pitch-deg", type=float, default=3.0)
    args = parser.parse_args()
    build(args.out_dir, args.drag, args.pitch_deg)
    print(f"FLOWUnsteady database written to {args.out_dir} (drag={args.drag}, tip pitch {args.pitch_deg} deg)")


if __name__ == "__main__":
    main()
