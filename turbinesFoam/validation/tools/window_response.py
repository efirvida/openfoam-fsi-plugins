#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mean cp / cd / ct of one or more runs in fixed azimuth windows.

Why this exists
---------------
A model switched on at a restart (a tip correction, an end-effect toggle) is
judged over a fraction of a revolution, not over whole revolutions, so
``rev_history.py`` (per-revolution means) cannot show it. This reader averages
the run's own ``cp``/``cd``/``ct`` columns in windows of ``--window-deg`` of the
cumulative ``angle_deg``, so runs that share an azimuth origin -- the same
restart state -- line up window by window. With ``--window-deg 120`` on a
three-bladed rotor each window is one full blade-passing period, which removes
the once-per-pass ripple.

It computes no calibrated quantity: the columns are the module's own.

Usage
-----
    python3 validation/tools/window_response.py --from-deg 7200 --to-deg 7330 \
        --window-deg 60 runs/iea15mw-screen-m3-l2 runs/iea15mw-l2-ds

Exit codes
----------
    0  every run was read
    1  a run has no ``postProcessing/turbines`` history
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("rev_history", _HERE / "rev_history.py")
assert _spec is not None and _spec.loader is not None
rev_history = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("rev_history", rev_history)
_spec.loader.exec_module(rev_history)

QUANTITIES = ("cp", "cd", "ct")  # power, thrust and torque coefficients

#: Columns a window needs; ``rev_history.read_history`` keeps only cp and ct.
COLUMNS = ("angle_deg", *QUANTITIES)


def read_rows(run_dir: Path) -> list[dict[str, float]]:
    """Every split history of a run, in chronological order, with cd included."""
    rows: list[dict[str, float]] = []
    for path in rev_history.history_files(run_dir):
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                try:
                    rows.append({name: float(row[name]) for name in COLUMNS})
                except (KeyError, TypeError, ValueError):
                    continue
    return rows


def window_means(
    rows: list[dict[str, float]],
    window_deg: float,
    from_deg: float,
    to_deg: float,
) -> dict[int, dict[str, float]]:
    """Mean of each quantity per window index ``floor((angle - from) / window)``.

    Rows outside ``[from_deg, to_deg)`` are ignored; a later duplicate of an
    angle (a resumed history overlaps its predecessor's last row) replaces the
    earlier one by being averaged with it, which for a duplicate row is a no-op.
    """
    sums: dict[int, dict[str, float]] = {}
    counts: dict[int, int] = {}
    for row in rows:
        angle = row["angle_deg"]
        if not from_deg <= angle < to_deg:
            continue
        index = int((angle - from_deg) // window_deg)
        bucket = sums.setdefault(index, dict.fromkeys(QUANTITIES, 0.0))
        for name in QUANTITIES:
            bucket[name] += row[name]
        counts[index] = counts.get(index, 0) + 1
    return {
        index: {name: bucket[name] / counts[index] for name in QUANTITIES}
        for index, bucket in sums.items()
    }


def render(
    results: dict[str, dict[int, dict[str, float]]],
    window_deg: float,
    from_deg: float,
) -> str:
    names = list(results)
    indices = sorted({i for table in results.values() for i in table})
    lines = ["window [deg from %.1f]   " % from_deg + "   ".join(
        f"{Path(n).name[:22]:>22}" for n in names
    )]
    for quantity in QUANTITIES:
        lines.append(f"-- {quantity}")
        for index in indices:
            low = from_deg + index * window_deg
            cells = []
            for name in names:
                value = results[name].get(index, {}).get(quantity)
                cells.append(f"{value:22.6f}" if value is not None else " " * 21 + "-")
            lines.append(f"{low:8.1f}-{low + window_deg:<8.1f}      " + "   ".join(cells))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("run_dirs", nargs="+", type=Path)
    parser.add_argument("--window-deg", type=float, default=60.0)
    parser.add_argument("--from-deg", type=float, required=True)
    parser.add_argument("--to-deg", type=float, required=True)
    args = parser.parse_args(argv)

    results: dict[str, dict[int, dict[str, float]]] = {}
    for run_dir in args.run_dirs:
        try:
            rows = read_rows(run_dir)
        except FileNotFoundError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        results[str(run_dir)] = window_means(
            rows, args.window_deg, args.from_deg, args.to_deg
        )
    print(render(results, args.window_deg, args.from_deg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
