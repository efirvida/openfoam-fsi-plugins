#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Station-by-station ratio of two spanwise profiles, pooled in r/R bands.

``compare_spanwise.py --out`` writes one profile CSV per run (columns ``r/R``,
``alpha_deg``, ``c_n``, ``c_t``, ``Fn_per_len``, ``Ft_per_len``). Its own
``--compare-with`` pools only r/R 0.3-0.9; this reader adds the root and tip
bands where a tip or root model acts. Per band it reports the station count,
the mean angle-of-attack difference and the ratio of the integrated normal and
tangential force per length (the bands are narrow, so the unweighted sum of
``F_per_len`` over equally spaced stations is the ratio of the band forces).

Usage
-----
    python3 scripts/station_ratio.py A.csv B.csv
    python3 scripts/station_ratio.py --bands 0,0.1,0.9,0.97,1.0 A.csv B.csv

A and B must hold the same stations (same blade discretisation); ratio = A / B.

Exit codes
----------
    0  ratios printed
    1  the two profiles do not share the same stations
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

DEFAULT_BANDS = (0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 0.95, 1.0)


def read_profile(path: Path) -> list[dict[str, float]]:
    """Rows of a profile CSV; the leading ``Σ`` summary row is skipped."""
    rows: list[dict[str, float]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                rows.append({key: float(value) for key, value in row.items()})
            except (TypeError, ValueError):
                continue
    return rows


def band_ratios(
    a: list[dict[str, float]], b: list[dict[str, float]], bands: tuple[float, ...]
) -> list[dict[str, float]]:
    """Per band: stations, mean alpha difference and Fn / Ft ratios (A over B)."""
    if len(a) != len(b) or any(
        abs(x["r/R"] - y["r/R"]) > 1e-4 for x, y in zip(a, b, strict=True)
    ):
        raise ValueError("the profiles do not share the same stations")
    out = []
    for low, high in zip(bands[:-1], bands[1:], strict=True):
        idx = [i for i, row in enumerate(a) if low <= row["r/R"] < high]
        if not idx:
            continue
        sums = {
            key: (sum(a[i][key] for i in idx), sum(b[i][key] for i in idx))
            for key in ("Fn_per_len", "Ft_per_len")
        }
        out.append(
            {
                "low": low,
                "high": high,
                "stations": len(idx),
                "d_alpha": sum(a[i]["alpha_deg"] - b[i]["alpha_deg"] for i in idx)
                / len(idx),
                "fn_ratio": sums["Fn_per_len"][0] / sums["Fn_per_len"][1],
                "ft_ratio": sums["Ft_per_len"][0] / sums["Ft_per_len"][1],
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("a", type=Path)
    parser.add_argument("b", type=Path)
    parser.add_argument(
        "--bands", default=",".join(str(x) for x in DEFAULT_BANDS),
        help="comma-separated r/R band edges",
    )
    args = parser.parse_args(argv)
    bands = tuple(float(x) for x in args.bands.split(","))
    try:
        rows = band_ratios(read_profile(args.a), read_profile(args.b), bands)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"A = {args.a}\nB = {args.b}   (ratio = A / B)")
    print("band,stations,d_alpha_deg,fn_ratio,ft_ratio")
    for r in rows:
        print(
            f"{r['low']:.2f}-{r['high']:.2f},{int(r['stations'])},"
            f"{r['d_alpha']:+.3f},{r['fn_ratio']:.4f},{r['ft_ratio']:.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
