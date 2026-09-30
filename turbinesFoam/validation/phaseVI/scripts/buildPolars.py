#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the committed S809 polar files for the NREL Phase VI case.

Reads the committed raw table transcriptions under `data/polars/raw/` (from
NREL/TP-500-29955 Tables A-3..A-8 and NREL/TP-442-7817 Tables B1..B4) and
emits:

- `S809_OSU_Re1M_total.dat`  single-Re baseline (OSU Re 1e6, total drag),
- `S809_multiRe.dat`         multi-Re sensitivity set (OSU clean series).

The baseline uses the total drag coefficient `Cdw` from the wake traverse
where the table reports it and falls back to the pressure drag `Cdp` where the
wake column is blank (the report leaves it blank in the separated region).
Beyond the measured +-20.1/26.1 deg range the file carries a clearly marked
static extension taken from the CSU Table A-3 measurements (mirrored for
negative angles) plus a flat-plate closure at +-120/150/180 deg, so that the
`profileData` lookup never silently returns zero outside the table.

Usage:
    buildPolars.py [--check]

`--check` re-renders in memory and exits 1 when a committed file is missing or
stale, without writing anything.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "polars" / "raw"
POLARS_DIR = ROOT / "data" / "polars"

BASELINE = POLARS_DIR / "S809_OSU_Re1M_total.dat"
MULTI_RE = POLARS_DIR / "S809_multiRe.dat"
# Reynolds-sensitivity variant: the CSU Re = 0.65e6 level (TP-500-29955 Table
# A-5). The simulated Phase VI Re at 7 m/s spans ~0.43e6 (inboard) to ~0.94e6
# (at r/R = 0.7), so the single-Re Re = 1e6 baseline is an upper bound; this
# variant is the ablation that tests that choice. Not blended into the baseline.
CSU_LOW_RE = POLARS_DIR / "S809_CSU_Re0.65M_total.dat"
# Viterna-Corrigan post-stall variants. These are NEW files: the measured rows
# are byte-identical to the `*_total.dat` files above and only the
# beyond-measurement rows are replaced by an empirical post-stall branch. The
# running Phase VI jobs read the committed `*_total.dat` files, never these.
BASELINE_VITERNA = POLARS_DIR / "S809_OSU_Re1M_viterna.dat"
CSU_LOW_RE_VITERNA = POLARS_DIR / "S809_CSU_Re0.65M_viterna.dat"

# Viterna & Corrigan (1982) flat-plate term `B1 = 1.11 + 0.018*AR`. The polar
# is a 2-D airfoil section consumed by `profileData`, so the finite-aspect-ratio
# correction does not apply and the AR term is dropped (B1 = 1.11). See
# odd/tasks/phasevi-polar-viterna-design.md for the justification.
VITERNA_B1_2D = 1.11

# Multi-Re set: nominal Reynolds levels of TP-442-7817 Tables B1..B4.
MULTI_RE_LEVELS = [0.75e6, 1.0e6, 1.25e6, 1.5e6]

# Static extension closure (flat plate); documented as non-measured.
FLAT_PLATE = {
    120.0: (-0.75, 1.5, 0.0),
    150.0: (-0.75, 0.7, 0.0),
    180.0: (0.0, 0.02, 0.0),
}


def read_raw(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"{path}: no data rows")
    rows.sort(key=lambda row: float(row["alpha_deg"]))
    return rows


def drag(row: dict[str, str]) -> float:
    """Total drag where reported, else pressure drag (fallback documented)."""
    cdw = row.get("cdw")
    if cdw:
        return float(cdw)
    cdp = row.get("cdp")
    if cdp:
        return float(cdp)
    raise ValueError("raw table row has neither cdw nor cdp")


def baseline_rows() -> list[tuple[float, float, float, float]]:
    table = read_raw(RAW_DIR / "table_A7.csv")
    rows = [
        (float(row["alpha_deg"]), float(row["cl"]), drag(row), float(row["cm"]))
        for row in table
    ]
    return rows


def extension_alphas(core: list[tuple[float, float, float, float]]) -> list[float]:
    """CSU Table A-3 abscissae carried beyond the measured core range.

    Mirrored for negative alpha. Returned unsorted; the caller sorts. This is
    the exact angle grid the committed `*_total.dat` extension uses, so the
    Viterna variant keeps the same row abscissae and only changes the values.
    """
    csu = read_raw(RAW_DIR / "table_A3.csv")
    high = [float(row["alpha_deg"]) for row in csu]
    core_high = max(alpha for alpha, _, _, _ in core)
    core_low = min(alpha for alpha, _, _, _ in core)
    alphas = [alpha for alpha in high if alpha > core_high]
    alphas += [-alpha for alpha in high if alpha > -core_low]
    return alphas


def extension_rows(core: list[tuple[float, float, float, float]]):
    """CSU Table A-3 measured extension, mirrored for negative alpha."""
    csu = read_raw(RAW_DIR / "table_A3.csv")
    high = [
        (float(row["alpha_deg"]), float(row["cl"]), drag(row), 0.0)
        for row in csu
    ]
    wanted = set(extension_alphas(core))
    rows = [(alpha, cl, cd, cm) for alpha, cl, cd, cm in high if alpha in wanted]
    mirrored = [(-alpha, -cl, cd, cm) for alpha, cl, cd, cm in high if -alpha in wanted]
    rows = mirrored + rows
    for alpha, (cl, cd, cm) in FLAT_PLATE.items():
        rows.append((alpha, cl, cd, cm))
        rows.append((-alpha, -cl, cd, cm))
    rows.sort()
    return rows


def viterna_extrapolation(
    alpha_s_deg: float,
    cl_s: float,
    cd_s: float,
    alpha_deg: float,
    aspect_ratio: float = 0.0,
) -> tuple[float, float]:
    """Viterna & Corrigan (1982) post-stall branch at `alpha_deg`.

    Reference relations (angles in degrees, converted internally):

        B1 = 1.11 + 0.018*AR          (flat-plate max-drag term)
        A1 = B1 / 2
        A2 = (CL_s - B1*sin(a_s)*cos(a_s)) * sin(a_s) / cos^2(a_s)
        B2 = (CD_s - B1*sin^2(a_s)) / cos(a_s)

        CL(a) = A1*sin(2a) + A2*cos^2(a)/sin(a)
        CD(a) = B1*sin^2(a) + B2*cos(a)

    The form `A2 = (CL_s - A1*sin(2 a_s))*sin(a_s)/cos^2(a_s)` is identical
    because `A1*sin(2 a_s) = B1*sin(a_s)*cos(a_s)`. The default `aspect_ratio=0`
    drops the finite-aspect-ratio term: this is a 2-D section polar, so the
    finite-wing correction does not apply. Valid for `a_s <= alpha <= 90`.
    """
    a_s = math.radians(alpha_s_deg)
    a = math.radians(alpha_deg)
    b1 = VITERNA_B1_2D + 0.018 * aspect_ratio
    a1 = b1 / 2.0
    a2 = (cl_s - b1 * math.sin(a_s) * math.cos(a_s)) * math.sin(a_s) / (
        math.cos(a_s) ** 2
    )
    b2 = (cd_s - b1 * math.sin(a_s) ** 2) / math.cos(a_s)
    cl = a1 * math.sin(2.0 * a) + a2 * math.cos(a) ** 2 / math.sin(a)
    cd = b1 * math.sin(a) ** 2 + b2 * math.cos(a)
    return cl, cd


def viterna_extension_rows(core: list[tuple[float, float, float, float]]):
    """Viterna post-stall branch beyond the measured core, plus the closure.

    One anchor per side, re-anchored at the outermost measured sample (the
    blend point) so the emitted table is continuous there: anchoring at the
    interior max-CL stall point would leave the near-edge abscissae undefined
    (CSU negative) or introduce a discontinuity (OSU positive). Negative alpha
    mirrors the branch (CL odd, CD even). The same flat-plate closure as the
    committed `*_total.dat` files is retained beyond the +-90 deg Viterna range.
    """
    pos_edge = max(core, key=lambda row: row[0])
    neg_edge = min(core, key=lambda row: row[0])
    pos_anchor = (pos_edge[0], pos_edge[1], pos_edge[2])
    neg_anchor = (-neg_edge[0], -neg_edge[1], neg_edge[2])
    rows: list[tuple[float, float, float, float]] = []
    for alpha in extension_alphas(core):
        if alpha > pos_anchor[0]:
            cl, cd = viterna_extrapolation(*pos_anchor, alpha)
            rows.append((alpha, cl, cd, 0.0))
        elif alpha < neg_edge[0]:
            cl, cd = viterna_extrapolation(*neg_anchor, -alpha)
            rows.append((alpha, -cl, cd, 0.0))
    for alpha, (cl, cd, cm) in FLAT_PLATE.items():
        rows.append((alpha, cl, cd, cm))
        rows.append((-alpha, -cl, cd, cm))
    rows.sort()
    return rows


def csu_low_re_rows() -> list[tuple[float, float, float, float]]:
    """CSU Re = 0.65e6 level (Table A-5); same Cdw->Cdp fallback as the baseline."""
    table = read_raw(RAW_DIR / "table_A5.csv")
    return [
        (float(row["alpha_deg"]), float(row["cl"]), drag(row), 0.0)
        for row in table
    ]


BASELINE_HEADER = [
    "// S809 polar, OSU Re = 1e6, TOTAL drag (NREL/TP-500-29955 Table A-7;",
    "// cross-checked against NREL/TP-442-7817 Table B2, which is the same",
    "// OSU clean series). `Cdw` (wake traverse) is used where reported; rows",
    "// where the report leaves the wake column blank fall back to `Cdp`",
    "// (pressure drag) -- verified by scripts/buildPolars.py from the raw",
    "// table transcription in data/polars/raw/table_A7.csv.",
    "// Rows with |alpha| beyond the measured OSU range are a STATIC EXTENSION",
    "// from CSU Table A-3 (Re = 0.3e6, mirrored for negative alpha) plus a",
    "// flat-plate closure, added so profileData never reads outside the table.",
    "// (alpha_deg Cl Cd Cm)",
]

CSU_HEADER = [
    "// S809 polar, CSU Re = 0.65e6 (NREL/TP-500-29955 Table A-5); pressure drag",
    "// `Cdp` (the CSU series reports no wake traverse), transcribed in",
    "// data/polars/raw/table_A5.csv and emitted by scripts/buildPolars.py.",
    "// REYNOLDS-SENSITIVITY VARIANT, not the committed baseline: the baseline is",
    "// S809_OSU_Re1M_total.dat. The simulated Phase VI Re at 7 m/s is ~0.43e6",
    "// inboard to ~0.94e6 at r/R = 0.7, so this lower-Re level brackets it from",
    "// below. Rows with |alpha| beyond the measured CSU range are a STATIC",
    "// EXTENSION from the same table (mirrored for negative alpha) plus a",
    "// flat-plate closure, so profileData never reads outside the table.",
    "// (alpha_deg Cl Cd Cm)",
]

VITERNA_LIMITATION = [
    "// Viterna & Corrigan (1982) is an EMPIRICAL post-stall engineering model,",
    "// NOT measured data. B1 = 1.11 (2-D flat-plate baseline); the finite",
    "// aspect-ratio term 0.018*AR is dropped because this is a 2-D section polar.",
    "// Beyond +-90 deg the Viterna range ends and the flat-plate closure is kept.",
]

BASELINE_VITERNA_HEADER = [
    "// S809 polar, OSU Re = 1e6, TOTAL drag (NREL/TP-500-29955 Table A-7) with a",
    "// Viterna-Corrigan post-stall branch. Rows inside the measured range",
    "// (alpha in [-20.1, +26.1] deg) are byte-identical to",
    "// S809_OSU_Re1M_total.dat; rows beyond it are re-anchored at the outermost",
    "// measured sample (the blend point) so the branch is continuous there, and",
    "// mirrored for negative alpha:",
    "//   CL(a) = A1*sin(2a) + A2*cos^2(a)/sin(a)",
    "//   CD(a) = B1*sin^2(a) + B2*cos(a)",
    "//   A1 = B1/2, B1 = 1.11",
    "//   A2 = (CL_s - B1*sin(a_s)*cos(a_s))*sin(a_s)/cos^2(a_s)",
    "//   B2 = (CD_s - B1*sin^2(a_s))/cos(a_s)",
] + VITERNA_LIMITATION + [
    "// (alpha_deg Cl Cd Cm)",
]

CSU_VITERNA_HEADER = [
    "// S809 polar, CSU Re = 0.65e6 (NREL/TP-500-29955 Table A-5) with a",
    "// Viterna-Corrigan post-stall branch. Rows inside the measured range",
    "// (alpha in [-0.25, +90.2] deg) are byte-identical to",
    "// S809_CSU_Re0.65M_total.dat; rows beyond it (the negative alpha branch,",
    "// which this table does not measure) are the mirrored Viterna branch",
    "// re-anchored at the outermost measured sample.",
    "//   CL(a) = A1*sin(2a) + A2*cos^2(a)/sin(a)",
    "//   CD(a) = B1*sin^2(a) + B2*cos(a)",
    "//   A1 = B1/2, B1 = 1.11",
    "//   A2 = (CL_s - B1*sin(a_s)*cos(a_s))*sin(a_s)/cos^2(a_s)",
    "//   B2 = (CD_s - B1*sin^2(a_s))/cos(a_s)",
] + VITERNA_LIMITATION + [
    "// (alpha_deg Cl Cd Cm)",
]


def render_single_re(rows, header: list[str] | None = None) -> str:
    lines = list(header) if header is not None else list(BASELINE_HEADER)
    for alpha, cl, cd, cm in rows:
        lines.append(f"({alpha:.4g} {cl:.6g} {cd:.6g} {cm:.6g})")
    return "\n".join(lines) + "\n"


def multi_re_tables():
    """Pivot the TP-442-7817 clean series onto a shared angle grid.

    The shared grid is the Re = 1e6 angle list restricted to the range every
    level measures, so no value is extrapolated. Off-grid values are linearly
    interpolated within each level's own measured samples.
    """
    raw = read_raw(RAW_DIR / "table_TP442-7817.csv")
    levels: dict[float, dict[float, tuple[float, float, float, float]]] = {
        level: {} for level in MULTI_RE_LEVELS
    }
    for row in raw:
        level = float(row["re_millions"]) * 1e6
        if level not in levels:
            continue
        alpha = float(row["alpha_deg"])
        levels[level][alpha] = (
            float(row["cl"]),
            drag(row),
            float(row["cm"]),
        )
    reference = sorted(levels[1.0e6])
    low = max(min(samples) for samples in levels.values())
    high = min(max(samples) for samples in levels.values())
    grid = [alpha for alpha in reference if low <= alpha <= high]
    if len(grid) < 10:
        raise ValueError("multi-Re angle grid is too small")
    tables = {level: [] for level in MULTI_RE_LEVELS}
    for alpha in grid:
        for level in MULTI_RE_LEVELS:
            cl, cd, cm = interpolate(levels[level], alpha)
            tables[level].append((cl, cd, cm))
    return grid, tables


def interpolate(samples, x):
    keys = sorted(samples)
    if x <= keys[0]:
        return samples[keys[0]]
    if x >= keys[-1]:
        return samples[keys[-1]]
    for lower, upper in zip(keys, keys[1:]):
        if lower <= x <= upper:
            ratio = (x - lower) / (upper - lower)
            a = samples[lower]
            b = samples[upper]
            return tuple(a[i] + ratio * (b[i] - a[i]) for i in range(3))
    raise AssertionError("unreachable")


def render_multi_re() -> str:
    grid, tables = multi_re_tables()
    lines = [
        "// S809 multi-Re sensitivity set, OSU clean series from NREL/TP-442-7817",
        "// Tables B1..B4 (Re = 0.75/1/1.25/1.5e6). `Cdw` where reported, else",
        "// `Cdp`; values linearly interpolated onto the shared Re = 1e6 grid",
        "// restricted to the range every level measures (no extrapolation).",
        "// Not blended with CSU (Tables A-3..A-5) or DUT (Table A-8).",
        "tableType multiRe;",
        "ReList",
        "(",
        "    " + " ".join(f"{level:.4g}" for level in MULTI_RE_LEVELS),
        ");",
        "clData",
        "(",
    ]
    for index, alpha in enumerate(grid):
        values = " ".join(
            f"{tables[level][index][0]:.6g}" for level in MULTI_RE_LEVELS
        )
        lines.append(f"    ({alpha:.4g} {values})")
    lines.append(");")
    lines.append("cdData")
    lines.append("(")
    for index, alpha in enumerate(grid):
        values = " ".join(
            f"{tables[level][index][1]:.6g}" for level in MULTI_RE_LEVELS
        )
        lines.append(f"    ({alpha:.4g} {values})")
    lines.append(");")
    lines.append("cmData")
    lines.append("(")
    for index, alpha in enumerate(grid):
        values = " ".join(
            f"{tables[level][index][2]:.6g}" for level in MULTI_RE_LEVELS
        )
        lines.append(f"    ({alpha:.4g} {values})")
    lines.append(");")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail (exit 1) if the committed polar files are missing or stale",
    )
    parser.add_argument(
        "--viterna-only",
        action="store_true",
        help="write/check only the two Viterna post-stall variants; never touch "
        "the committed `*_total.dat` files (running Phase VI jobs read them)",
    )
    args = parser.parse_args(argv)

    core = baseline_rows()
    rows = core + extension_rows(core)
    rows.sort(key=lambda row: row[0])
    csu_core = csu_low_re_rows()
    csu_rows = csu_core + extension_rows(csu_core)
    csu_rows.sort(key=lambda row: row[0])
    osu_viterna_rows = core + viterna_extension_rows(core)
    osu_viterna_rows.sort(key=lambda row: row[0])
    csu_viterna_rows = csu_core + viterna_extension_rows(csu_core)
    csu_viterna_rows.sort(key=lambda row: row[0])
    rendered = {
        BASELINE: render_single_re(rows),
        MULTI_RE: render_multi_re(),
        CSU_LOW_RE: render_single_re(csu_rows, CSU_HEADER),
        BASELINE_VITERNA: render_single_re(osu_viterna_rows, BASELINE_VITERNA_HEADER),
        CSU_LOW_RE_VITERNA: render_single_re(
            csu_viterna_rows, CSU_VITERNA_HEADER
        ),
    }
    if args.viterna_only:
        rendered = {
            BASELINE_VITERNA: rendered[BASELINE_VITERNA],
            CSU_LOW_RE_VITERNA: rendered[CSU_LOW_RE_VITERNA],
        }

    stale = False
    for path, content in rendered.items():
        if args.check:
            if not path.exists():
                print(f"missing polar file: {path}", file=sys.stderr)
                stale = True
            elif path.read_text(encoding="utf-8") != content:
                print(f"stale polar file: {path}", file=sys.stderr)
                stale = True
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")
    if args.check:
        return 1 if stale else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
