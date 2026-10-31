#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Diff two runs' own ``postProcessing`` CSVs, without re-deriving any physics.

Why this exists
---------------
After a library rebuild or a renderer change the regression question is always
the same: "does the candidate run reproduce the reference run?". It used to be
answered with an ad-hoc script per campaign that re-typed file lists and
tolerances. This tool answers it once.

It is a pure reader. For every ``postProcessing/<family>/<segment>/<name>.csv``
it joins the resume segments of one file the way ``case_state.py`` does (a later
segment replaces the rows from its first time on), aligns the two runs on the
``time`` column and reports, per shared column, ``max|a-b|`` and that value
relative to ``max|reference|`` over the common rows. Files and columns present in
only one run are listed and never compared; non-numeric columns are skipped.

It computes no ``cp``/``P``/``Q`` and holds no reference constants. Calibrated
quantities are defined once in ``phaseVI/scripts/comparePhaseVI.py``. Neither run
directory is ever written to.

Usage
-----
    python3 validation/tools/run_diff.py runs/reference runs/candidate
    python3 validation/tools/run_diff.py --until 2.5 --tolerance 1e-6 REF CAND
    python3 validation/tools/run_diff.py --json --top 20 REF CAND

Exit codes
----------
    0  both runs were read (and the worst relative difference is within
       ``--tolerance`` when given)
    1  a run directory does not exist
    2  a run directory has no ``postProcessing`` output yet
    3  ``--tolerance`` given and the worst max_rel exceeds it
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import case_state  # noqa: E402

#: Time keys are rounded to this many decimals to absorb text formatting.
TIME_DECIMALS = 9


class RunDiffError(Exception):
    """A run could not be read, with a process exit code attached."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def _collect(run: Path) -> dict[str, list[Path]]:
    """Map ``<family>/<name>.csv`` to its segment files in numeric segment order."""
    if not run.is_dir():
        raise RunDiffError(f"run directory {run} does not exist", 1)
    post = run / "postProcessing"
    if not post.is_dir():
        raise RunDiffError(f"{run} has no postProcessing output yet", 2)
    grouped: dict[str, list[Path]] = {}
    for path in post.glob("*/*/*.csv"):
        grouped.setdefault(f"{path.parent.parent.name}/{path.name}", []).append(path)
    for sources in grouped.values():
        sources.sort(key=case_state._segment_key)
    return grouped


def _load(sources: list[Path], until: float | None) -> tuple[list[str], dict[float, dict[str, str]]]:
    fields, rows = case_state._read_joined(sources)
    keyed: dict[float, dict[str, str]] = {}
    for row in rows:
        time = case_state._as_float(row.get(case_state.TIME_COLUMN))
        if time is None or (until is not None and time > until):
            continue
        keyed[round(time, TIME_DECIMALS)] = row
    return fields, keyed


def _diff_file(ref_sources: list[Path], cand_sources: list[Path], until: float | None) -> dict:
    ref_fields, ref_rows = _load(ref_sources, until)
    cand_fields, cand_rows = _load(cand_sources, until)
    common = sorted(set(ref_rows) & set(cand_rows))
    time = case_state.TIME_COLUMN
    columns: dict[str, dict[str, float]] = {}
    for name in ref_fields:
        if name == time or name not in cand_fields:
            continue
        pairs = []
        for key in common:
            a = case_state._as_float(ref_rows[key].get(name))
            b = case_state._as_float(cand_rows[key].get(name))
            if a is None or b is None:
                pairs = None
                break
            pairs.append((a, b))
        if not pairs:
            continue
        max_abs = max(abs(a - b) for a, b in pairs)
        scale = max(abs(a) for a, _ in pairs)
        max_rel = max_abs / scale if scale > 0.0 else (0.0 if max_abs == 0.0 else float("inf"))
        columns[name] = {"max_abs": max_abs, "max_rel": max_rel}
    return {
        "common_rows": len(common),
        "reference_only_rows": len(set(ref_rows) - set(cand_rows)),
        "candidate_only_rows": len(set(cand_rows) - set(ref_rows)),
        "columns": columns,
        "reference_only_columns": [n for n in ref_fields if n not in cand_fields],
        "candidate_only_columns": [n for n in cand_fields if n not in ref_fields],
    }


def diff_runs(reference: Path, candidate: Path, until: float | None = None) -> dict:
    """Return the per-file, per-column difference of two runs."""
    ref_files = _collect(Path(reference))
    cand_files = _collect(Path(candidate))
    files = {
        key: _diff_file(ref_files[key], cand_files[key], until)
        for key in sorted(set(ref_files) & set(cand_files))
    }
    worst = {"file": None, "column": None, "max_abs": 0.0, "max_rel": 0.0}
    for key, entry in files.items():
        for name, stats in entry["columns"].items():
            if stats["max_rel"] > worst["max_rel"] or (
                worst["file"] is None and stats["max_rel"] == worst["max_rel"]
            ):
                worst = {"file": key, "column": name, **stats}
    return {
        "files": files,
        "reference_only_files": sorted(set(ref_files) - set(cand_files)),
        "candidate_only_files": sorted(set(cand_files) - set(ref_files)),
        "worst": worst,
    }


def _file_worst(entry: dict) -> float:
    return max((s["max_rel"] for s in entry["columns"].values()), default=0.0)


def render_text(report: dict, top: int) -> str:
    files = report["files"]
    lines = [
        f"files compared: {len(files)}; "
        f"reference only: {len(report['reference_only_files'])}; "
        f"candidate only: {len(report['candidate_only_files'])}"
    ]
    ranked = sorted(files.items(), key=lambda item: -_file_worst(item[1]))[: max(top, 0)]
    for key, entry in ranked:
        name, stats = max(
            entry["columns"].items(), key=lambda item: item[1]["max_rel"], default=(None, None)
        )
        detail = f"worst {name} max_abs={stats['max_abs']:.6g} max_rel={stats['max_rel']:.6g}" if name else "no shared numeric columns"
        lines.append(
            f"  {key}: rows common={entry['common_rows']} "
            f"ref_only={entry['reference_only_rows']} cand_only={entry['candidate_only_rows']}; {detail}"
        )
    if len(files) > len(ranked):
        lines.append(f"  ... {len(files) - len(ranked)} more files (use --json for all)")
    worst = report["worst"]
    lines.append(
        f"worst: file={worst['file']} column={worst['column']} "
        f"max_abs={worst['max_abs']:.6g} max_rel={worst['max_rel']:.6g}"
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("reference", type=Path, help="reference run directory")
    parser.add_argument("candidate", type=Path, help="candidate run directory")
    parser.add_argument("--until", type=float, default=None, help="ignore rows with time above this value")
    parser.add_argument("--tolerance", type=float, default=None,
                        help="exit 3 when the worst max_rel exceeds this relative difference")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    parser.add_argument("--top", type=int, default=10, help="files listed in the text report (default: 10)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = diff_runs(args.reference, args.candidate, args.until)
    except RunDiffError as error:
        print(f"run_diff: {error}", file=sys.stderr)
        return error.code
    print(json.dumps(report, indent=2) if args.json else render_text(report, args.top))
    if args.tolerance is not None and report["worst"]["max_rel"] > args.tolerance:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
