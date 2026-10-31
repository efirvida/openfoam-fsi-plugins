#!/usr/bin/env python3
"""Side-by-side AeroDyn cases (e.g. BEM vs OLAF) per Phase VI point.

Reads the `metrics.json` that `scripts/compareAeroDyn.py` writes in each case
directory and prints, per point (sequence + wind speed), the percent error vs
the experiment of power, thrust and c_n at r/R 0.30/0.47/0.63/0.80/0.95 for
every configuration, plus `diff_pp` = second configuration minus first, in
percentage points. No quantity is recomputed: every cell is copied from
`metrics.json`.

A configuration is the case directory name without the `aerodyn-` prefix and
the `-<sequence>U<speed>` suffix (`aerodyn-olaf-dp-SU8` -> `olaf-dp`); columns
follow the order in which configurations first appear on the command line.

Usage:
    compareWakes.py runs/aerodyn-bem-SU5 runs/aerodyn-olaf-dp-SU5 ... [--out table.csv]

Exit codes: 0 table written, 1 a case has no readable metrics.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

STATIONS = ("0.30", "0.47", "0.63", "0.80", "0.95")
QUANTITIES = ("P", "T") + tuple("cn" + s for s in STATIONS)
SUFFIX_RE = re.compile(r"-[A-Z]U\d+$")


def configuration(case_dir: Path) -> str:
    name = case_dir.name
    if name.startswith("aerodyn-"):
        name = name[len("aerodyn-"):]
    return SUFFIX_RE.sub("", name)


def point_label(metrics: dict) -> str:
    speed = float(metrics["speed_m_s"])
    speed_txt = str(int(speed)) if speed.is_integer() else "{:g}".format(speed)
    return "{}{}".format(metrics["sequence"], speed_txt)


def errors(metrics: dict) -> dict:
    out = {"P": metrics["power_error_pct"], "T": metrics["thrust_error_pct"]}
    for s in STATIONS:
        out["cn" + s] = metrics["stations"][s]["cn_error_pct"]
    return out


class LoadError(Exception):
    """A case directory without a readable metrics.json."""


def load(case_dirs):
    """{point: {configuration: errors}}, configurations in order, unconverged."""
    table, configs, unconverged, order = {}, [], [], []
    for d in case_dirs:
        path = Path(d) / "metrics.json"
        try:
            metrics = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            raise LoadError("cannot read {}: {}".format(path, exc))
        config = configuration(Path(d))
        point = point_label(metrics)
        if config not in configs:
            configs.append(config)
        if point not in table:
            table[point] = {}
            order.append(point)
        table[point][config] = errors(metrics)
        if not metrics.get("convergence", {}).get("converged", False):
            unconverged.append("{} {}".format(config, point))
    return table, configs, unconverged, order


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("cases", nargs="+", help="AeroDyn case directories")
    parser.add_argument("--out", help="also write the table as CSV")
    args = parser.parse_args(argv)

    try:
        table, configs, unconverged, order = load(args.cases)
    except LoadError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 1

    header = ["point", "quantity"] + configs + (["diff_pp"] if len(configs) > 1 else [])
    rows = []
    for point in order:
        for q in QUANTITIES:
            cells = [table[point].get(c, {}).get(q) for c in configs]
            diff = None
            if len(configs) > 1 and cells[0] is not None and cells[1] is not None:
                diff = cells[1] - cells[0]
            rows.append((point, q, cells, diff))

    def fmt(v, signed=True):
        if v is None:
            return "n/a"
        return ("{:+.1f}" if signed else "{:.1f}").format(v)

    widths = [6, 9] + [max(9, len(c) + 1) for c in header[2:]]
    print("".join(h.ljust(w) for h, w in zip(header, widths)).rstrip())
    for point, q, cells, diff in rows:
        vals = [point, q] + [fmt(c) for c in cells]
        if len(configs) > 1:
            vals.append(fmt(diff))
        print("".join(v.ljust(w) for v, w in zip(vals, widths)).rstrip())
    print()
    print("cells: % error vs experiment; diff_pp = {} - {}".format(
        configs[1], configs[0]) if len(configs) > 1 else "cells: % error vs experiment")
    if unconverged:
        print("not converged: " + ", ".join(unconverged))

    if args.out:
        lines = [",".join(header)]
        for point, q, cells, diff in rows:
            vals = [point, q] + [fmt(c, signed=False) for c in cells]
            if len(configs) > 1:
                vals.append(fmt(diff, signed=False))
            lines.append(",".join(vals))
        Path(args.out).write_text("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
