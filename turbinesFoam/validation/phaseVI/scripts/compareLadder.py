#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare mesh/time-step ladder metrics without modifying any input.

Usage (from validation/phaseVI):
    python3 scripts/compareLadder.py --reference /tmp/cmpH_d1 \
        --runs /tmp/cmpH_dt05 /tmp/cmpH_l1 [--tolerance 2.0]

Each directory contains comparePhaseVI metrics.json. The reference must contain
one model; every model in --runs becomes a column pair. P and banded T are read
from power_kw and thrust_n (not thrust_rotor_n). Effective thrust scopes must
match. F'n uses compareSectionLoads' converged window, profile interpolation and
experimental density, with each comparison's recorded discard/end revolutions.
No drift override is applied. Percent change is 100 * (value - ref) / abs(ref);
a zero reference has zero change only if the compared value is also zero,
otherwise infinite change. PASS requires every absolute change < tolerance.
Exit codes: 0 all pass, 1 any fail, 2 invalid or unavailable input.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

# Suppress import caches as well: this analysis is strictly read-only.
sys.dont_write_bytecode = True
import compareSectionLoads as sections

EXPERIMENT = Path(__file__).resolve().parents[1] / "data/experiment"
STATIONS = tuple(station for station in sections.STATIONS if station >= 0.47)
QUANTITIES = ("P [kW]", "T [N]", *(f"F'n {s:.2f} [N/m]" for s in STATIONS))


def load_comparison(directory):
    path = directory / "metrics.json"
    if not path.is_file():
        raise ValueError(f"missing metrics.json: {path}")
    payload = json.loads(path.read_text())
    if not payload["models"]:
        raise ValueError(f"no models in {path}")
    return payload


def values(payload, model):
    case = payload["case"]
    window = payload["window"]
    metrics = model["metrics"]
    scope = metrics.get("thrust_scope", case["thrust_scope"])
    requested = case["thrust_scope"]
    if scope != requested and not (requested == "blade" and scope == "blade (r/R >= 0.25)"):
        raise ValueError(f"thrust scope {scope!r} does not match case scope {requested!r}")
    run = Path(model["run_dir"])
    lo, hi, _ = sections.converged_window(
        run, case["speed_m_s"], case["sequence"],
        (window["discard_revolutions"], window["end_revolutions"]),
        allow_short_window=window.get("allow_short_window", False),
    )
    profile, _ = sections.sim_profile(run, lo, hi)
    if not profile:
        raise ValueError(f"no valid elements in recorded window: {run}")
    rho = sections.read_density(EXPERIMENT, case["speed_m_s"], case["sequence"])
    result = [float(metrics["power_kw"]), float(metrics["thrust_n"])]
    result.extend(rho * sections.interpolate(profile, station, 7) for station in STATIONS)
    if not all(math.isfinite(value) for value in result):
        raise ValueError(f"non-finite quantity: {run}")
    return result, scope


def percent_change(value, reference):
    if reference == 0:
        return 0.0 if value == 0 else math.copysign(math.inf, value)
    return 100 * (value - reference) / abs(reference)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, type=Path,
                        help="comparePhaseVI output directory containing one reference model")
    parser.add_argument("--runs", required=True, nargs="+", type=Path,
                        help="comparePhaseVI output directories to compare with the reference")
    parser.add_argument("--tolerance", type=float, default=2.0,
                        help="strict absolute percent-change limit (default: 2.0)")
    args = parser.parse_args(argv)
    try:
        if not math.isfinite(args.tolerance) or args.tolerance <= 0:
            raise ValueError("tolerance must be finite and positive")
        directories = [args.reference, *args.runs]
        payloads = [load_comparison(directory) for directory in directories]
        if len(payloads[0]["models"]) != 1:
            raise ValueError("reference metrics.json must contain exactly one model")
        reference_case = payloads[0]["case"]
        for directory, payload in zip(directories[1:], payloads[1:]):
            case = payload["case"]
            if (case["speed_m_s"], case["sequence"]) != (
                    reference_case["speed_m_s"], reference_case["sequence"]):
                raise ValueError(f"mismatched speed/sequence: {directory}; expected "
                                 f"{reference_case['speed_m_s']} m/s, {reference_case['sequence']}")
        labels, columns, scopes = [], [], []
        for directory, payload in zip(directories, payloads):
            for name, model in payload["models"].items():
                column, scope = values(payload, model)
                labels.append(f"{directory.name}/{name}")
                columns.append(column)
                scopes.append(scope)
        if any(scope != scopes[0] for scope in scopes):
            raise ValueError(f"mismatched effective thrust scopes: {scopes}")
    except SystemExit as exc:
        # Existing section readers report gate errors themselves, sometimes with
        # a nonnumeric SystemExit for a missing density. Normalise to input error.
        if not isinstance(exc.code, int):
            print(f"error: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    changes = [[percent_change(value, ref) for value, ref in zip(column, columns[0])]
               for column in columns[1:]]
    passed = [all(abs(change) < args.tolerance for change in column) for column in changes]
    print(f"T = thrust_n; scope {scopes[0]}. PASS: |change| < {args.tolerance:g}%")
    header = ["quantity", f"reference {labels[0]}"]
    for label in labels[1:]:
        header.extend([f"{label} value", "change %"])
    print(" | ".join(header))
    for i, quantity in enumerate(QUANTITIES):
        row = [quantity, f"{columns[0][i]:.6f}"]
        for column, delta in zip(columns[1:], changes):
            row.extend([f"{column[i]:.6f}", f"{delta[i]:+.6f}"])
        print(" | ".join(row))
    verdict = ["verdict", "-"]
    for ok in passed:
        verdict.extend(["PASS" if ok else "FAIL", "-"])
    print(" | ".join(verdict))
    return 0 if all(passed) else 1


if __name__ == "__main__":
    sys.exit(main())
