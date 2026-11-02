#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Wall-clock trace of an OpenFAST/OLAF run and its extrapolation (Slurm sizing).

    olaf_trace.py sample LOG OUT PID [--period S]  # append "wall_s,sim_s" while PID lives
    olaf_trace.py truncate CASEDIR STEPS           # TMax = STEPS * DT in the case .fst
    olaf_trace.py fit OUT [--steps N] [--dt S]     # extrapolate the wall time to N steps

OpenFAST prints ``Time: <t> of <tmax> seconds.`` every few steps. The OLAF cost per step
grows with the number of wake panels until ``nNWPanels`` is reached, so ``fit`` fits the
cumulative wall time ``W(n) = a n + b n^2`` (n = steps done) and reports the extrapolation.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

PROGRESS = re.compile(rb"Time:\s+([0-9.]+)\s+of\s+([0-9.]+)\s+seconds")


def last_progress(log: Path) -> tuple[float, float] | None:
    """(simulated time, tmax) of the last progress line of ``log`` (``\\r``-separated)."""
    try:
        with log.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - 4096))
            tail = handle.read()
    except OSError:
        return None
    found = PROGRESS.findall(tail)
    return (float(found[-1][0]), float(found[-1][1])) if found else None


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def sample(log: Path, out: Path, pid: int, period: float = 15.0) -> int:
    start = time.time()
    with out.open("w") as handle:
        handle.write("wall_s,sim_s\n")
        while alive(pid):
            got = last_progress(log)
            if got:
                handle.write(f"{time.time() - start:.1f},{got[0]:.4f}\n")
                handle.flush()
            time.sleep(period)
    return 0


def truncate(case: Path, steps: int) -> float:
    fst = next(case.glob("*.fst"))
    lines = fst.read_text().splitlines()
    dt = next(float(l.split()[0]) for l in lines if re.search(r"\sDT\s", l))
    tmax = steps * dt
    for i, line in enumerate(lines):
        if re.search(r"\sTMax\s", line):
            lines[i] = re.sub(r"^\s*\S+", f"{tmax:.4f}", line, count=1)
    fst.write_text("\n".join(lines) + "\n")
    return tmax


def read_trace(path: Path, dt: float) -> list[tuple[float, float]]:
    rows = path.read_text().splitlines()[1:]
    return [(float(a), float(b) / dt) for a, b in (r.split(",") for r in rows if r)]


def fit(trace: list[tuple[float, float]], steps: float) -> dict:
    """Least squares ``wall = a n + b n^2`` through the origin; extrapolate to ``steps``."""
    sxx = sum(n * n for _, n in trace)
    sx3 = sum(n**3 for _, n in trace)
    sx4 = sum(n**4 for _, n in trace)
    sy1 = sum(w * n for w, n in trace)
    sy2 = sum(w * n * n for w, n in trace)
    det = sxx * sx4 - sx3 * sx3
    a = (sy1 * sx4 - sy2 * sx3) / det
    b = (sxx * sy2 - sx3 * sy1) / det
    return {"a": a, "b": b, "steps_measured": trace[-1][1], "wall_measured_s": trace[-1][0],
            "wall_extrapolated_s": a * steps + b * steps**2}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("log", type=Path), s.add_argument("out", type=Path), s.add_argument("pid", type=int)
    s.add_argument("--period", type=float, default=15.0)
    t = sub.add_parser("truncate")
    t.add_argument("case", type=Path), t.add_argument("steps", type=int)
    f = sub.add_parser("fit")
    f.add_argument("out", type=Path)
    f.add_argument("--steps", type=float, default=1640)
    f.add_argument("--dt", type=float, default=0.14590026812092274)
    args = p.parse_args(argv)
    if args.cmd == "sample":
        return sample(args.log, args.out, args.pid, args.period)
    if args.cmd == "truncate":
        print(f"TMax = {truncate(args.case, args.steps):.4f} s")
        return 0
    result = fit(read_trace(args.out, args.dt), args.steps)
    print({k: round(v, 6) for k, v in result.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
