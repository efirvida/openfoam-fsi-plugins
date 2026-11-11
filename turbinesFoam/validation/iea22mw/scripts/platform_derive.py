#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Derive the IEA-22 ALM D&S platform from the IEA-15 frozen L2 platform.

The IEA-15 reference (``iea15mw-l2-ds``) is the set of values restated in
``iea15mw/scripts/slurm/l2-long.slurm`` / ``l2-ds-surface.slurm``. They are *read from
those files* (nothing is re-typed here) and carried to IEA-22 by a rule that depends
only on the geometry:

- lengths: domain extents are multiples of the rotor diameter D, the base cell is D/32,
  the castellated extents are IEA-15 constants times R22/R15 (``generate_case.py``), so
  every length is identical in units of R;
- dimensionless numbers (snappy level, velocity-sample radius in units of the projection
  epsilon, number of samples, write interval in degrees, revolutions) are carried as is;
- the rotor speed is the generator default (the IEA-22 rated rpm), never passed;
- the decomposition lattice is carried (same domain aspect in D, same cells per axis in
  proportion) and the rank count is the lattice product, checked against
  ``cells22 / (cells15 / ranks15)`` (the IEA-15 cells per rank).

    python -I platform_derive.py            # markdown table
    python -I platform_derive.py --env      # shell exports for the Slurm scripts
    python -I platform_derive.py --json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
IEA15 = PACKAGE.parent / "iea15mw"
SLURM15 = IEA15 / "scripts" / "slurm"
RANK_TOLERANCE = 0.05


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _exports(*files: Path) -> dict[str, str]:
    """``export A=1 B="x y"`` assignments of the IEA-15 Slurm files (plain values only)."""
    found: dict[str, str] = {}
    for path in files:
        for line in path.read_text().splitlines():
            if not line.startswith("export "):
                continue
            for key, quoted, bare in re.findall(r'(TURBINE_[A-Z_]+)=(?:"([^"]*)"|(\S+))', line):
                value = quoted or bare
                if "${" not in value:
                    found[key] = value
    return found


def reference15() -> dict[str, str]:
    """Frozen IEA-15 L2 D&S platform, read from its Slurm files."""
    ref = _exports(SLURM15 / "l2-long.slurm", SLURM15 / "l2-ds-surface.slurm")
    ntasks = re.search(r"^#SBATCH --ntasks=(\d+)", (SLURM15 / "l2-long.slurm").read_text(), re.M)
    ref["ranks"] = ntasks.group(1) if ntasks else ref["TURBINE_RANKS"]
    return ref


def derive() -> dict:
    ref = reference15()
    g15 = _load("_pd_iea15_generate_case", IEA15 / "tools" / "generate_case.py")
    sys.path.insert(0, str(PACKAGE / "tools"))
    try:
        g22 = _load("_pd_iea22_generate_case", PACKAGE / "tools" / "generate_case.py")
    finally:
        sys.path.pop(0)
    level = int(ref["TURBINE_SNAPPY_LEVEL"])
    up, down, lat = (float(ref[k]) for k in ("TURBINE_UPSTREAM", "TURBINE_DOWNSTREAM", "TURBINE_LATERAL"))
    ranks15 = int(ref["ranks"])
    lattice = tuple(int(v) for v in ref["TURBINE_DECOMP_N"].split())

    def case(g):
        domain = g.domain_spec(mesh=ref["TURBINE_MESH"], upstream=up, downstream=down, lateral=lat)
        r = g.ROTOR_RADIUS
        dt = g.delta_t(domain, g.RATED_RPM, level)
        omega = g.omega_from_rpm(g.RATED_RPM)
        return {
            "R_m": r,
            "rpm": g.RATED_RPM,
            "cells": g.cell_count(domain),
            "base_cell_over_R": g.Z_HUB_CELL / r,
            "castellated_cell_over_R": g.Z_HUB_CELL / 2.0**level / r,
            "domain_upstream_R": up * g.ROTOR_DIAMETER / r,
            "domain_downstream_R": down * g.ROTOR_DIAMETER / r,
            "domain_lateral_R": lat * g.ROTOR_DIAMETER / r,
            "dt_s": dt,
            "steps_per_rev": g.revolution_period(g.RATED_RPM) / dt,
            "tip_travel_over_castellated_cell": omega * r * dt / (g.Z_HUB_CELL / 2.0**level),
        }

    c15, c22 = case(g15), case(g22)
    cells_per_rank = c15["cells"] / ranks15
    raw_ranks = c22["cells"] / cells_per_rank
    ranks22 = math.prod(lattice)
    if abs(raw_ranks / ranks22 - 1.0) > RANK_TOLERANCE:
        raise SystemExit(f"carried lattice {lattice} ({ranks22} ranks) is not proportional: cells/rank rule gives {raw_ranks:.1f}")
    return {
        "reference": ref,
        "iea15": c15,
        "iea22": c22,
        "ranks15": ranks15,
        "ranks22": ranks22,
        "ranks_cells_rule": raw_ranks,
        "decomp_method": ref["TURBINE_DECOMP_METHOD"],
        "decomp_n": " ".join(map(str, lattice)),
        "snappy_level": level,
        "velocity_sample_radius": ref["TURBINE_VELOCITY_SAMPLE_RADIUS"],
        "n_velocity_samples": ref["TURBINE_N_VELOCITY_SAMPLES"],
        "write_deg": ref["TURBINE_WRITE_DEG"],
        "total_revs": ref.get("TURBINE_TOTAL_REVS", "23"),
        "mesh": ref["TURBINE_MESH"],
        "domain": (up, down, lat),
    }


def env_lines(d: dict) -> list[str]:
    up, down, lat = d["domain"]
    pairs = [
        ("TURBINE_RANKS", d["ranks22"]),
        ("TURBINE_REQUEUE", 0),
        ("TURBINE_VELOCITY_SAMPLE_RADIUS", d["velocity_sample_radius"]),
        ("TURBINE_N_VELOCITY_SAMPLES", d["n_velocity_samples"]),
        ("TURBINE_UPSTREAM", f"{up:g}"),
        ("TURBINE_DOWNSTREAM", f"{down:g}"),
        ("TURBINE_LATERAL", f"{lat:g}"),
        ("TURBINE_DECOMP_METHOD", d["decomp_method"]),
        ("TURBINE_MESH", d["mesh"]),
        ("TURBINE_SNAPPY", "on"),
        ("TURBINE_SNAPPY_LEVEL", d["snappy_level"]),
        ("TURBINE_WRITE_DEG", d["write_deg"]),
    ]
    lines = [f"export {k}={v}" for k, v in pairs]
    lines.append(f'export TURBINE_DECOMP_N="{d["decomp_n"]}"')
    return lines


def table(d: dict) -> str:
    a, b = d["iea15"], d["iea22"]
    rows = [
        ("R [m]", f"{a['R_m']:.3f}", f"{b['R_m']:.3f}", "turbine"),
        ("rated rpm (generator default, not passed)", f"{a['rpm']}", f"{b['rpm']}", "turbine"),
        ("domain up/down/lateral [D]", "/".join(f"{v:g}" for v in d["domain"]), "/".join(f"{v:g}" for v in d["domain"]), "carried (D multiples)"),
        ("domain up/down/lateral [R]", *("/".join(f"{x[k]:g}" for k in ("domain_upstream_R", "domain_downstream_R", "domain_lateral_R")) for x in (a, b)), "equal"),
        ("base cell / R", f"{a['base_cell_over_R']:.5f}", f"{b['base_cell_over_R']:.5f}", "D/32"),
        ("snappy level", d["snappy_level"], d["snappy_level"], "carried (dimensionless)"),
        ("castellated cell / R", f"{a['castellated_cell_over_R']:.5f}", f"{b['castellated_cell_over_R']:.5f}", "base / 2^level"),
        ("velocity-sample radius [x epsilon]", d["velocity_sample_radius"], d["velocity_sample_radius"], "carried (epsilon is geometry-derived)"),
        ("n velocity samples", d["n_velocity_samples"], d["n_velocity_samples"], "carried"),
        ("background cells", f"{a['cells']:,}", f"{b['cells']:,}", "geometry"),
        ("cells / rank (IEA-15 reference)", f"{a['cells'] / d['ranks15']:,.0f}", f"{b['cells'] / d['ranks22']:,.0f}", "ranks = cells22 / (cells15/ranks15) = " + f"{d['ranks_cells_rule']:.1f}"),
        ("decomposition", f"{d['decomp_method']} {d['decomp_n']}", f"{d['decomp_method']} {d['decomp_n']}", "lattice carried"),
        ("ranks", d["ranks15"], d["ranks22"], "lattice product"),
        ("deltaT [s]", a["dt_s"], b["dt_s"], "delta_t(): finest cell / tip speed"),
        ("steps / revolution", f"{a['steps_per_rev']:.0f}", f"{b['steps_per_rev']:.0f}", "derived"),
        ("tip travel / castellated cell", f"{a['tip_travel_over_castellated_cell']:.4f}", f"{b['tip_travel_over_castellated_cell']:.4f}", "0.95 x ; IEA-22 +2 %"),
        ("write interval [deg]", d["write_deg"], d["write_deg"], "carried"),
        ("revolutions (from scratch)", d["total_revs"], d["total_revs"], "carried"),
    ]
    out = ["| quantity | IEA-15 | IEA-22 | rule |", "|---|---|---|---|"]
    out += [f"| {q} | {x} | {y} | {r} |" for q, x, y, r in rows]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--env", action="store_true", help="print shell exports")
    mode.add_argument("--json", action="store_true")
    mode.add_argument("--get", metavar="KEY", help="print one value (ranks, decomp_n, ...)")
    args = p.parse_args(argv)
    d = derive()
    if args.env:
        print("\n".join(env_lines(d)))
    elif args.json:
        print(json.dumps(d, indent=2, default=str))
    elif args.get:
        print(d[{"ranks": "ranks22"}.get(args.get, args.get)])
    else:
        print(table(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
