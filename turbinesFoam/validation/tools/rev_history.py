#!/usr/bin/env python3
"""Per-revolution history of a turbine run, read from every split history.

Usage:
    rev_history.py runs/iea15mw-screen-m3-l2
    rev_history.py --window 2 --csv /tmp/dt2.csv runs/iea15mw-screen-m3-l2
    rev_history.py runs/iea15mw-screen-m3-l2 runs/iea15mw-l2-ra

Why it exists: a resumed run writes a *new*
``postProcessing/turbines/<timeName>/turbine.csv``, named after the run's start
time, so the revolutions of one continuous run end up split across folders whose
names sort wrongly as text -- ``"31.9209"`` sorts after ``"159.6232"`` -- and
whose row counts differ when the time step changes (the CSV is written every
solver step). Reading one folder alone silently reports a fraction of the
history, and reading them in lexical order reports it shuffled. The module's
``angle_deg`` stays cumulative across a restart, so the revolution is
reconstructed from it over the union of the folders taken in *numeric* timeName
order; that is the mistake this tool removes.

The same trap applies to the per-element histories (``actuatorLineElements/``,
``bladeSurface/``), which carry the same folder split; ``compare_spanwise.py``
takes --time for that reason.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Any

#: Columns read from turbine.csv. The module's own names, so a renamed column
#: fails loudly here instead of silently producing a wrong revolution count.
COLUMNS = ("time", "angle_deg", "cp", "ct")

#: A revolution whose row count falls below this fraction of the median is a stub
#: (the run stopped mid-revolution and wrote a single row at endTime), not a
#: revolution; it is reported and kept out of the plateau and the drift.
PARTIAL_FRACTION = 0.5


def history_files(run_dir: Path) -> list[Path]:
    """Every turbine.csv of a run, ordered numerically by its timeName folder.

    ``float`` on the folder name makes ``0 < 31.9209 < 159.6232``, which is the
    chronological order the runs were written in; lexical order is not.
    """
    root = run_dir / "postProcessing" / "turbines"
    if not root.is_dir():
        raise FileNotFoundError(f"no postProcessing/turbines under {run_dir}")
    files = [d / "turbine.csv" for d in root.iterdir() if (d / "turbine.csv").is_file()]
    if not files:
        raise FileNotFoundError(f"no turbine.csv under {root}")

    def sort_key(path: Path) -> tuple[float, str]:
        try:
            return (float(path.parent.name), "")
        except ValueError:
            return (float("inf"), path.parent.name)

    return sorted(files, key=sort_key)


def read_history(files: list[Path]) -> list[dict[str, float]]:
    """Concatenate every split history, in chronological order."""
    rows: list[dict[str, float]] = []
    for path in files:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            missing = [name for name in COLUMNS if name not in (reader.fieldnames or [])]
            if missing:
                raise ValueError(f"{path}: missing column(s) {', '.join(missing)}")
            for row in reader:
                try:
                    rows.append({name: float(row[name]) for name in COLUMNS})
                except (TypeError, ValueError):
                    continue
    return rows


def per_revolution(rows: list[dict[str, float]]) -> list[dict[str, Any]]:
    """Mean cp and ct per revolution, the revolution taken from cumulative angle.

    ``angle_deg`` is the azimuth accumulated since the case started, so it keeps
    growing across a restart and floor(angle/360)+1 is the revolution number in
    the union. A missing revolution (a gap in the history) is reported rather
    than hidden, because it changes what a drift means.
    """
    grouped: dict[int, list[dict[str, float]]] = {}
    for row in rows:
        revolution = int(row["angle_deg"] // 360.0) + 1
        grouped.setdefault(revolution, []).append(row)

    series: list[dict[str, Any]] = []
    for revolution in sorted(grouped):
        block = grouped[revolution]
        series.append(
            {
                "rev": revolution,
                "time": block[-1]["time"],
                "rows": len(block),
                "cp": statistics.fmean(row["cp"] for row in block),
                "ct": statistics.fmean(row["ct"] for row in block),
            }
        )
    # A run that stops mid-revolution leaves a stub -- one row at endTime in the
    # real case. That is not a revolution: averaging it into a plateau or a drift
    # reports a level and a change the run never held (it is what put a phantom
    # +0.135 % drift at the end of the rotational-augmentation run). Anything far
    # below the median row count is flagged and kept out of both.
    mid = statistics.median([entry["rows"] for entry in series]) if series else 0.0
    for entry in series:
        entry["partial"] = entry["rows"] < PARTIAL_FRACTION * mid
        entry["drift_cp_pct"] = None
    complete = [entry for entry in series if not entry["partial"]]
    # Consecutive-pair walk over the complete revolutions only; unequal by
    # construction (complete[1:] is one shorter), hence strict=False.
    for previous, current in zip(complete, complete[1:], strict=False):
        current["drift_cp_pct"] = 100.0 * (current["cp"] - previous["cp"]) / previous["cp"]
    return series


def analyse(
    run_dir: Path,
    window: int = 2,
    drift_window: int = 4,
) -> dict[str, Any]:
    """Per-revolution series plus the plateau and drift of its tail."""
    files = history_files(run_dir)
    series = per_revolution(read_history(files))
    if not series:
        raise ValueError(f"{run_dir}: the histories hold no rows")
    revisions = [entry["rev"] for entry in series]
    gaps = [
        missing
        for previous, current in zip(revisions, revisions[1:], strict=False)
        for missing in range(previous + 1, current)
    ]
    tail = [entry for entry in series if not entry["partial"]][-window:]
    drift_values = [
        entry["drift_cp_pct"]
        for entry in [item for item in series if not item["partial"]][-drift_window:]
        if entry["drift_cp_pct"] is not None
    ]
    return {
        "run": str(run_dir),
        "histories": [str(path) for path in files],
        "series": series,
        "revolutions": len(series),
        "first_rev": revisions[0],
        "last_rev": revisions[-1],
        "gaps": gaps,
        "partial_revs": [entry["rev"] for entry in series if entry["partial"]],
        "plateau_window": window,
        "plateau_cp": statistics.fmean(entry["cp"] for entry in tail),
        "plateau_ct": statistics.fmean(entry["ct"] for entry in tail),
        "mean_drift_cp_pct": (
            statistics.fmean(drift_values) if drift_values else None
        ),
    }


def render_text(results: list[dict[str, Any]], window: int) -> str:
    """Text table: one per-revolution block per run, then the comparison."""
    lines: list[str] = []
    for result in results:
        lines.append(f"=== {result['run']}")
        lines.append(f"    {len(result['histories'])} historia(s) en el union")
        if result["gaps"]:
            lines.append(f"    OJO: faltan las revoluciones {result['gaps']}")
        lines.append(f"    {'rev':>4} {'time':>9} {'rows':>6} {'cp':>9} {'ct':>9} {'d(cp)':>8}")
        for entry in result["series"]:
            drift = entry["drift_cp_pct"]
            drift_text = "       -" if drift is None else f"{drift:+7.3f}%"
            marker = "  parcial (fuera del plateau)" if entry["partial"] else ""
            lines.append(
                f"    {entry['rev']:>4} {entry['time']:>9.2f} {entry['rows']:>6} "
                f"{entry['cp']:>9.5f} {entry['ct']:>9.5f} {drift_text:>8}{marker}"
            )
        lines.append(
            f"    plateau (ultimas {window} rev): cp {result['plateau_cp']:.5f}  "
            f"ct {result['plateau_ct']:.5f}  "
            f"deriva media {result['mean_drift_cp_pct']:+.3f}%/rev"
            if result["mean_drift_cp_pct"] is not None
            else f"    plateau: cp {result['plateau_cp']:.5f}"
        )
    if len(results) > 1:
        lines.append("")
        lines.append("=== comparacion de plateaus")
        reference = results[0]
        for result in results:
            delta = 100.0 * (result["plateau_cp"] - reference["plateau_cp"]) / reference["plateau_cp"]
            lines.append(
                f"    {Path(result['run']).name:<34} cp {result['plateau_cp']:.5f} "
                f"({delta:+.2f}% vs {Path(reference['run']).name})  "
                f"ct {result['plateau_ct']:.5f}"
            )
    return "\n".join(lines) + "\n"


def write_csv(results: list[dict[str, Any]], path: Path) -> None:
    """The per-revolution series of every run, long format."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["run", "rev", "time", "rows", "cp", "ct", "drift_cp_pct"])
        for result in results:
            for entry in result["series"]:
                drift = entry["drift_cp_pct"]
                writer.writerow(
                    [
                        result["run"],
                        entry["rev"],
                        f"{entry['time']:.6f}",
                        entry["rows"],
                        f"{entry['cp']:.8g}",
                        f"{entry['ct']:.8g}",
                        "" if drift is None else f"{drift:.6g}",
                    ]
                )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Per-revolution cp/ct history of a turbine run, over every split history.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("run_dirs", nargs="+", help="run directories to read")
    parser.add_argument(
        "--window",
        type=int,
        default=2,
        help="revolutions averaged into the plateau (default 2)",
    )
    parser.add_argument(
        "--drift-window",
        type=int,
        default=4,
        help="revolutions averaged into the mean drift (default 4)",
    )
    parser.add_argument("--csv", type=Path, help="write the per-revolution series here")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    results = []
    for run_dir in args.run_dirs:
        try:
            results.append(analyse(Path(run_dir), args.window, args.drift_window))
        except (FileNotFoundError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 1

    if args.csv:
        write_csv(results, args.csv)
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(render_text(results, args.window), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
