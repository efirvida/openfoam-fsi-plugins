#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read where a turbine run got to, without re-deriving any physics.

Why this exists
---------------
During a campaign the same question is asked over and over: "how far did this
run get, and what does the last window look like?". It used to be answered with
a fresh inline ``python3 - <<PY`` snippet each time. That was expensive in two
ways: the snippet text stayed in the agent context for the rest of the session,
and it tended to re-type experimental constants that already live in
``data/experiment/``.

This tool is a pure reader. It reports the run's own columns and nothing else:

* which ``postProcessing`` source was used, and how many rows it has;
* the first and last ``time`` value (and revolutions, if you supply the rpm);
* the mean of the last ``--mean-last`` rows for each numeric column present.

It deliberately does **not** compute ``P``, ``Q``, ``cp``, ``T`` or any
calibrated quantity, and it holds no experimental reference data. Those are
defined once, against the NREL report, in ``scripts/comparePhaseVI.py``; use
that for anything you intend to report.

Usage
-----
    python3 validation/tools/case_state.py runs/alm-U7-coarse-s0
    python3 validation/tools/case_state.py --mean-last 400 --rpm 71.878 runs/*
    python3 validation/tools/case_state.py --json runs/alm-U7-coarse-s0

Exit codes
----------
    0  every requested run was read
    1  a run directory does not exist
    2  a run directory has no ``postProcessing`` output yet
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

#: Preferred turbine-level source, relative to ``postProcessing``.
PREFERRED_GLOB = "turbines/*/turbine.csv"

#: Upper bound on listed fallback sources, and the size above which row counting
#: is skipped: a campaign can leave thousands of element CSVs behind.
MAX_LISTED_SOURCES = 20
MAX_COUNTED_BYTES = 64 * 1024 * 1024

#: Column treated as the time axis, and therefore never summarised.
TIME_COLUMN = "time"

#: Columns present in a run's output but meaningless to average: ``angle_deg``
#: is a cumulative azimuth that wraps, so a mean over a window has no meaning.
UNSUMMARISED_COLUMNS = (TIME_COLUMN, "angle_deg")


class CaseStateError(Exception):
    """A run could not be read, with a process exit code attached."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def _count_data_rows(path: Path) -> int:
    """Count data rows of a CSV cheaply, returning -1 when not counted."""
    if path.stat().st_size > MAX_COUNTED_BYTES:
        return -1
    with path.open(errors="replace") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", errors="replace") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _segment_key(source: Path) -> tuple[int, float, str]:
    """Order ``turbines/<time>/turbine.csv`` by numeric start time, then by name."""
    value = _as_float(source.parent.name)
    return (0, value, "") if value is not None else (1, 0.0, source.parent.name)


def _read_joined(sources: list[Path]) -> tuple[list[str], list[dict[str, str]]]:
    """Join segment 0 with its resume segments, as ``comparePhaseVI`` does.

    resume-run.slurm restarts from the last written time, so each later segment
    repeats rows the previous one already holds; the later segment replaces them.
    """
    fields, rows = _read_rows(sources[0])
    for source in sources[1:]:
        later_fields, later = _read_rows(source)
        start = _as_float(later[0].get(TIME_COLUMN)) if later else None
        if start is None:
            continue
        rows = [row for row in rows if _before(row, start)] + later
        fields = fields + [name for name in later_fields if name not in fields]
    return fields, rows


def _before(row: dict[str, str], start: float) -> bool:
    time = _as_float(row.get(TIME_COLUMN))
    return time is not None and time < start


def _numeric_columns(fields: list[str], rows: list[dict[str, str]]) -> list[str]:
    """Return the columns that hold a float in every row, in header order."""
    return [
        name
        for name in fields
        if name not in UNSUMMARISED_COLUMNS
        and rows
        and all(_as_float(row.get(name)) is not None for row in rows)
    ]


def _as_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _fallback_sources(post: Path) -> dict[str, int]:
    """List CSV sources other than the preferred one, with bounded work."""
    sources: dict[str, int] = {}
    for candidate in sorted(post.rglob("*.csv")):
        if len(sources) >= MAX_LISTED_SOURCES:
            break
        relative = candidate.relative_to(post).as_posix()
        if relative.endswith("turbine.csv") and relative.startswith("turbines/"):
            continue
        try:
            sources[relative] = _count_data_rows(candidate)
        except OSError:
            continue
    return sources


def inspect_run(
    run_dir: Path | str,
    *,
    mean_last: int = 1,
    rpm: float | None = None,
) -> dict:
    """Return the observable state of one run directory.

    Raises ``CaseStateError`` when the directory is absent or has produced no
    ``postProcessing`` output yet.
    """
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise CaseStateError(f"run directory not found: {run_dir}", 1)

    post = run_dir / "postProcessing"
    if not post.is_dir():
        raise CaseStateError(
            f"{run_dir} has no postProcessing output yet (nothing has been written)",
            2,
        )

    candidates = sorted(post.glob(PREFERRED_GLOB), key=_segment_key)
    if not candidates:
        return {
            "run": run_dir.name,
            "source": None,
            "segments": [],
            "rows": 0,
            "t_first": None,
            "t_last": None,
            "revolutions": None,
            "means": {},
            "otherSources": _fallback_sources(post),
        }

    source = candidates[0]
    fields, rows = _read_joined(candidates)
    if not rows:
        raise CaseStateError(f"{source} has a header but no data rows", 2)

    times = [_as_float(row.get(TIME_COLUMN)) for row in rows]
    first = next((value for value in times if value is not None), None)
    last = next((value for value in reversed(times) if value is not None), None)

    window = rows[-max(mean_last, 1) :]
    means: dict[str, float] = {}
    for name in _numeric_columns(fields, rows):
        values = [_as_float(row.get(name)) for row in window]
        present = [value for value in values if value is not None]
        if present:
            means[name] = sum(present) / len(present)

    revolutions = None
    if rpm is not None and first is not None and last is not None:
        revolutions = (last - first) * rpm / 60.0

    return {
        "run": run_dir.name,
        "source": source.relative_to(post).as_posix(),
        "segments": [candidate.relative_to(post).as_posix() for candidate in candidates],
        "rows": len(rows),
        "t_first": first,
        "t_last": last,
        "revolutions": revolutions,
        "means": means,
        "otherSources": {},
    }


def _format_number(value: float | None, digits: int = 6) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}g}"


def render_text(states: list[dict], mean_last: int) -> str:
    """Render a compact, one-line-per-run report."""
    out = [
        f"run state (mean of the last {mean_last} row(s); "
        "calibrated metrics come from scripts/comparePhaseVI.py)"
    ]
    for state in states:
        if state["source"] is None:
            out.append(f"\n{state['run']}: no turbine.csv yet")
            for name, count in state["otherSources"].items():
                counted = "unknown" if count < 0 else str(count)
                out.append(f"  {name}: {counted} rows")
            continue

        resumes = [Path(name).parent.name for name in state["segments"][1:]]
        resumed = f" + resume {', '.join(resumes)}" if resumes else ""
        head = (
            f"\n{state['run']}  {state['source']}{resumed}\n"
            f"  rows={state['rows']}  t=[{_format_number(state['t_first'])}, "
            f"{_format_number(state['t_last'])}]"
        )
        if state["revolutions"] is not None:
            head += f"  revs={state['revolutions']:.3f}"
        out.append(head)
        if state["means"]:
            rendered = "  ".join(
                f"{name}={_format_number(value)}" for name, value in state["means"].items()
            )
            out.append(f"  {rendered}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read the observable state of one or more turbine runs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("run_dirs", nargs="+", help="run directories to read")
    parser.add_argument(
        "--mean-last",
        type=int,
        default=1,
        help="average the last N rows instead of reporting the last row (default: 1)",
    )
    parser.add_argument(
        "--rpm",
        type=float,
        default=None,
        help="rotor speed, so revolutions are reported alongside the time span",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if args.mean_last < 1:
        parser.error("--mean-last must be at least 1")

    states: list[dict] = []
    failures: list[tuple[Path, CaseStateError]] = []
    for run_dir in args.run_dirs:
        try:
            states.append(
                inspect_run(run_dir, mean_last=args.mean_last, rpm=args.rpm)
            )
        except CaseStateError as error:
            failures.append((Path(run_dir), error))

    if args.json:
        print(json.dumps({"runs": states}, indent=2, sort_keys=True))
    elif states:
        print(render_text(states, args.mean_last))

    for _run_dir, error in failures:
        print(f"error: {error}", file=sys.stderr)

    if failures:
        return max(error.code for _, error in failures)
    return 0


if __name__ == "__main__":
    sys.exit(main())
