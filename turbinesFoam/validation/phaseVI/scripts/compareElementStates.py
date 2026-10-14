#!/usr/bin/env python3
"""Compare the per-element aerodynamic state of several runs side by side.

A pure reader of `postProcessing/actuatorLineElements/0/<owner>.blade1.element*.csv`:
for every element it averages the columns below over the same revolution window
in each run and prints one block per column (elements as rows, runs as columns,
then the ratio to the first run). It defines no calibrated quantity; use it to
locate WHERE two runs first differ (relative speed, angle of attack, lift, drag,
chord-frame coefficients) before asking why.

Usage:
    python3 scripts/compareElementStates.py --speed 7 --rpm 72 \
        runs/asm-U7-coarse-p21 runs/asm-mesh-U7-coarse-p21 \
        --columns rel_vel_mag alpha_deg cl cd c_ref_t c_ref_n
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ELEMENT_DIR = Path("postProcessing") / "actuatorLineElements" / "0"
DEFAULT_COLUMNS = ("rel_vel_mag", "alpha_deg", "alpha_geom_deg", "cl", "cd",
                   "end_effect_factor", "c_ref_t", "c_ref_n")
BLADE = "blade1"


def element_files(run_dir: Path) -> list[tuple[int, Path]]:
    pattern = re.compile(rf"\.{BLADE}\.element(\d+)\.csv$")
    found = []
    for path in (run_dir / ELEMENT_DIR).glob(f"*.{BLADE}.element*.csv"):
        match = pattern.search(path.name)
        if match:
            found.append((int(match.group(1)), path))
    return sorted(found)


def average_elements(run_dir: Path, start: float, columns: tuple[str, ...]) -> dict[int, dict]:
    """Mean of `columns` per element over rows with time >= start (plus root_dist)."""
    result = {}
    for index, path in element_files(run_dir):
        with path.open(newline="", encoding="utf-8") as stream:
            rows = [r for r in csv.DictReader(stream) if float(r["time"]) >= start]
        if not rows:
            continue
        entry = {"root_dist": float(rows[0]["root_dist"])}
        for column in ("root_dist", *columns):
            entry[column] = sum(float(r[column]) for r in rows) / len(rows)
        result[index] = entry
    return result


def window_start(speed: float, tsr: float, radius: float, discard_revolutions: float) -> float:
    import math
    return discard_revolutions * 2.0 * math.pi * radius / (tsr * speed)


def render(runs: list[Path], states: list[dict], columns: tuple[str, ...]) -> str:
    lines = []
    indices = sorted(set.intersection(*(set(s) for s in states)))
    labels = [run.name for run in runs]
    for column in columns:
        lines.append(f"\n## {column}")
        lines.append("elem  root_dist  " + "  ".join(f"{label[-22:]:>22}" for label in labels)
                     + "".join(f"  ratio{n}" for n in range(1, len(runs))))
        for index in indices:
            values = [state[index][column] for state in states]
            ratios = ["      n/a" if values[0] == 0.0 else f"{v / values[0]:9.3f}"
                      for v in values[1:]]
            lines.append(f"{index:4d}  {states[0][index]['root_dist']:9.4f}  "
                         + "  ".join(f"{v:22.5g}" for v in values) + "".join(ratios))
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("run_dirs", nargs="+", type=Path)
    parser.add_argument("--speed", type=float, required=True, help="inflow speed [m/s]")
    parser.add_argument("--tsr", type=float, default=5.408)
    parser.add_argument("--radius", type=float, default=5.029)
    parser.add_argument("--discard-revolutions", type=float, default=4.0)
    parser.add_argument("--columns", nargs="+", default=list(DEFAULT_COLUMNS))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    start = window_start(args.speed, args.tsr, args.radius, args.discard_revolutions)
    columns = tuple(args.columns)
    states = [average_elements(run, start, columns) for run in args.run_dirs]
    if not all(states):
        print("no element rows found in at least one run", file=sys.stderr)
        return 1
    print(f"window: time >= {start:.4f} s ({args.discard_revolutions:g} revolutions discarded)")
    print(render(args.run_dirs, states, columns))
    return 0


if __name__ == "__main__":
    sys.exit(main())
