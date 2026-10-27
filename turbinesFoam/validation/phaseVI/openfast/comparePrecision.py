#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare two `verifyAeroDyn.py` result directories point by point (single vs double precision builds).

The conda-forge OpenFAST is built with `-DDOUBLE_PRECISION=OFF`; the r-test baselines are double
precision. This tool measures what that costs on the Phase VI points: for every point that is `ok` in
both directories, the relative difference of power, thrust and torque, of c_n at the five stations, and
the absolute difference of c_t (c_t passes through zero, so a relative figure is not meaningful there).

Usage:
    comparePrecision.py --a RESULT_DIR_SINGLE --b RESULT_DIR_DOUBLE --out TABLE.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def read(path: Path) -> list[dict]:
    with Path(path).open(newline="") as stream:
        return list(csv.DictReader(stream))


def key(row: dict) -> tuple[str, str]:
    return (row["family"], row["id"])


def compare(a: Path, b: Path, max_speed: float = float("inf")) -> list[dict]:
    """One row per (family, quantity): largest difference over the common ok points of the family and where it occurs."""
    points_a = {key(r): r for r in read(Path(a) / "points.csv") if r["status"] == "ok"}
    points_b = {key(r): r for r in read(Path(b) / "points.csv") if r["status"] == "ok"}
    common = sorted(k for k in set(points_a) & set(points_b) if float(points_a[k]["wind_speed_m_s"]) <= max_speed)
    worst: dict[str, tuple[float, str]] = {}

    def note(name: str, value: float, where: str) -> None:
        if name not in worst or value > worst[name][0]:
            worst[name] = (value, where)

    for k in common:
        for name in ("power_kw", "thrust_n", "torque_nm"):
            va, vb = float(points_a[k][name]), float(points_b[k][name])
            note(f"{k[0]:<8} {name} (relative)", abs(va - vb) / abs(vb), k[1])
    stations_a = {(key(r), r["r_over_R"]): r for r in read(Path(a) / "stations.csv")}
    stations_b = {(key(r), r["r_over_R"]): r for r in read(Path(b) / "stations.csv")}
    for (k, station), ra in stations_a.items():
        rb = stations_b.get((k, station))
        if rb is None or k not in set(common):
            continue
        note(f"{k[0]:<8} cn (relative)", abs(float(ra["cn"]) - float(rb["cn"])) / max(abs(float(rb["cn"])), 1e-3), f"{k[1]} r/R {station}")
        note(f"{k[0]:<8} ct (absolute)", abs(float(ra["ct"]) - float(rb["ct"])), f"{k[1]} r/R {station}")
    rows = [{"quantity": name, "max_difference": value, "where": where, "points_compared": len(common)} for name, (value, where) in worst.items()]
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--a", type=Path, required=True, help="result directory A (e.g. the conda single-precision build)")
    parser.add_argument("--b", type=Path, required=True, help="result directory B (reference, e.g. double precision)")
    parser.add_argument("--max-speed", type=float, default=float("inf"), help="only points up to this wind speed (m/s), e.g. 8 for the attached-flow regime")
    parser.add_argument("--out", type=Path, required=True, help="result CSV")
    args = parser.parse_args(argv)
    try:
        rows = compare(args.a, args.b, args.max_speed)
    except FileNotFoundError as exc:
        print(f"missing input: {exc}", file=sys.stderr)
        return 1
    with args.out.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["quantity", "max_difference", "where", "points_compared"])
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "max_difference": f"{row['max_difference']:.4e}"})
    for row in rows:
        print(f"{row['quantity']:<34}{row['max_difference']:.3e}  at {row['where']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
