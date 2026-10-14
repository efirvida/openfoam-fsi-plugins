#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Nacelle drag area from the UAE aerodynamic tares (NREL/TP-500-29955, Appendix I).

Why this exists
---------------
The report gives no nacelle fairing geometry (Fig. 8 is the drivetrain), so a CFD
nacelle can only be a surrogate. What the report does give is the tunnel-balance
load with the blades removed: run 056 (tower + nacelle, Table I-4) and run 058
(tower only, Table I-5). Their drag difference at yaw 0 is the measured nacelle
drag, interference with the tower included. This script turns it into a drag
area `CdA = D / q` [m^2], the integral target a surrogate body has to match.

Method
------
Rows are read from the report text (PDF pages 296-300) or from the CSV this
script writes. Only yaw-0 points with `q > Q_MIN_PA` are used (the wind-off and
`ATT000000` rows carry the unzeroed balance). The tables are raw balance
channels with no tare applied, and the run 058 balance was re-zeroed during the
run, so two estimates are reported:

* per nominal speed, `CdA = D / q` with the reading as is (offset included);
* a least-squares fit `D = CdA * q + D0` over all speeds of a run, whose slope
  is free of a constant balance offset (Reynolds dependence of the tower drag
  is folded into it).

Usage
-----
    python3 scripts/extractAeroTare.py --rows-out data/experiment/aero-tare/runs_056_058.csv \
        --out analysis/aero-tare-nacelle-cda.csv
    python3 scripts/extractAeroTare.py --from-csv data/experiment/aero-tare/runs_056_058.csv

Exit codes
----------
    0  summary written
    1  input unreadable, or run 056 or 058 has no usable yaw-0 point
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

LB_TO_N = 4.4482216152605
LBFT_TO_NM = 1.3558179483314
PSF_TO_PA = 47.880258888889
FT_TO_M = 0.3048
SLUG_FT3_TO_KG_M3 = 515.378818
Q_MIN_PA = 5.0

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDF = ROOT.parents[1] / "articles" / "29955.pdf"
DEFAULT_PAGES = range(296, 301)  # 1-based PDF pages of Tables I-4 and I-5
RUN_TITLES = {
    "056": "Table I-4. Aerodynamic Tare Run 056",
    "058": "Table I-5. Aerodynamic Tare Run 058",
}
COLUMNS = ("yaw_deg", "rho_slug_ft3", "q_psf", "v_fps", "lift_lb", "drag_lb",
           "side_lb", "pitch_lbft", "roll_lbft", "yaw_lbft")
NUMBER = r"[-+]?\d+\.\d+E[-+]\d+"
ROW = re.compile(rf"^(\d{{3}}:\d{{2}}:\d{{2}}:\d{{2}})\s+(?:(AT\w+)\s+)?((?:{NUMBER}\s*){{10}})$")


def read_pages(pdf: Path, pages) -> list[str]:
    """Text of the given 1-based PDF pages."""
    from pypdf import PdfReader

    reader = PdfReader(str(pdf))
    return [reader.pages[page - 1].extract_text() or "" for page in pages]


def parse_pages(texts: list[str]) -> list[dict]:
    """Data rows of Tables I-4/I-5; a page counts only if it carries a table title."""
    rows: list[dict] = []
    for text in texts:
        run = next((run for run, title in RUN_TITLES.items() if title in text), None)
        if run is None:
            continue
        for line in text.splitlines():
            match = ROW.match(line.strip())
            if not match:
                continue
            values = [float(token) for token in match.group(3).split()]
            row = {"run": run, "stamp": match.group(1), "name": match.group(2) or ""}
            row.update(zip(COLUMNS, values, strict=True))
            rows.append(row)
    return rows


def to_si(row: dict) -> dict:
    return {
        "q_pa": row["q_psf"] * PSF_TO_PA,
        "speed_m_s": row["v_fps"] * FT_TO_M,
        "rho_kg_m3": row["rho_slug_ft3"] * SLUG_FT3_TO_KG_M3,
        "drag_n": row["drag_lb"] * LB_TO_N,
        "pitch_nm": row["pitch_lbft"] * LBFT_TO_NM,
    }


def _yaw0(rows: list[dict], run: str) -> list[dict]:
    points = []
    for row in rows:
        si = to_si(row)
        if row["run"] == run and row["yaw_deg"] == 0.0 and si["q_pa"] > Q_MIN_PA:
            points.append(si)
    return points


def _by_speed(points: list[dict]) -> dict[int, dict]:
    """Mean q and drag per nominal speed (repeated yaw-0 points are averaged)."""
    groups: dict[int, list[dict]] = {}
    for point in points:
        groups.setdefault(round(point["speed_m_s"]), []).append(point)
    return {
        speed: {key: sum(p[key] for p in group) / len(group) for key in ("q_pa", "speed_m_s", "drag_n")}
        for speed, group in groups.items()
    }


def drag_area_by_speed(rows: list[dict]) -> list[dict]:
    """Per nominal speed present in both runs: CdA of each run and their difference."""
    run_056, run_058 = _by_speed(_yaw0(rows, "056")), _by_speed(_yaw0(rows, "058"))
    table = []
    for speed in sorted(set(run_056) & set(run_058)):
        a, b = run_056[speed], run_058[speed]
        table.append({
            "speed_m_s": a["speed_m_s"],
            "q_pa": a["q_pa"],
            "drag_056_n": a["drag_n"],
            "drag_058_n": b["drag_n"],
            "cda_056_m2": a["drag_n"] / a["q_pa"],
            "cda_058_m2": b["drag_n"] / b["q_pa"],
            "cda_nacelle_m2": a["drag_n"] / a["q_pa"] - b["drag_n"] / b["q_pa"],
        })
    return table


def drag_area_fit(rows: list[dict], run: str) -> dict:
    """Least-squares `D = CdA * q + D0` over the yaw-0 points of one run."""
    points = _yaw0(rows, run)
    n = len(points)
    if n < 2:
        raise ValueError(f"run {run}: {n} usable yaw-0 point(s), need 2")
    mean_q = sum(p["q_pa"] for p in points) / n
    mean_d = sum(p["drag_n"] for p in points) / n
    sxx = sum((p["q_pa"] - mean_q) ** 2 for p in points)
    sxy = sum((p["q_pa"] - mean_q) * (p["drag_n"] - mean_d) for p in points)
    slope = sxy / sxx
    return {"cda_m2": slope, "offset_n": mean_d - slope * mean_q, "points": n}


def write_rows(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("run", "stamp", "name", *COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


def read_rows(path: Path) -> list[dict]:
    with path.open() as handle:
        return [
            {"run": row["run"], "stamp": row["stamp"], "name": row["name"],
             **{key: float(row[key]) for key in COLUMNS}}
            for row in csv.DictReader(handle)
        ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--from-csv", type=Path, help="read rows written by --rows-out instead of the PDF")
    parser.add_argument("--rows-out", type=Path, help="write the parsed table rows (report units)")
    parser.add_argument("--out", type=Path, help="write the CdA summary CSV")
    args = parser.parse_args(argv)

    try:
        rows = read_rows(args.from_csv) if args.from_csv else parse_pages(read_pages(args.pdf, DEFAULT_PAGES))
    except (OSError, KeyError, ValueError) as exc:
        print(f"ERROR: cannot read the tare rows: {exc}", file=sys.stderr)
        return 1
    if args.rows_out:
        write_rows(rows, args.rows_out)
    try:
        fits = {run: drag_area_fit(rows, run) for run in ("056", "058")}
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    summary = [dict(entry, basis="per-speed") for entry in drag_area_by_speed(rows)]
    summary.append({
        "basis": "fit", "speed_m_s": "", "q_pa": "", "drag_056_n": fits["056"]["offset_n"],
        "drag_058_n": fits["058"]["offset_n"], "cda_056_m2": fits["056"]["cda_m2"],
        "cda_058_m2": fits["058"]["cda_m2"],
        "cda_nacelle_m2": fits["056"]["cda_m2"] - fits["058"]["cda_m2"],
    })
    print(f"{'basis':>9} {'U[m/s]':>7} {'q[Pa]':>7} {'D056[N]':>9} {'D058[N]':>9} "
          f"{'CdA056':>8} {'CdA058':>8} {'CdA_nac[m2]':>11}")
    for entry in summary:
        cells = [f"{entry[key]:.4g}" if isinstance(entry[key], float) else str(entry[key])
                 for key in ("speed_m_s", "q_pa", "drag_056_n", "drag_058_n",
                             "cda_056_m2", "cda_058_m2", "cda_nacelle_m2")]
        print(f"{entry['basis']:>9} {cells[0]:>7} {cells[1]:>7} {cells[2]:>9} {cells[3]:>9} "
              f"{cells[4]:>8} {cells[5]:>8} {cells[6]:>11}")
    print("(fit rows: D056/D058 columns hold the fitted offset D0 [N]; "
          f"points {fits['056']['points']} / {fits['058']['points']})")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
            writer.writeheader()
            writer.writerows(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
