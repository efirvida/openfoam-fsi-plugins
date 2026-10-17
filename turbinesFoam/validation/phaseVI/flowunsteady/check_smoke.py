#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check a Phase VI smoke run: python3 check_smoke.py runs/TAG.

Report last-revolution means, independently integrated mechanical power,
per-revolution wall time, per-revolution CT/CQ means and the convergence gate
(CT and CQ change < 1 % per revolution over the last 2 revolutions).
The 10-revolution estimate assumes cost/revolution grows linearly with wake age;
it excludes Julia import time and is an estimate, not a measured production cost.
"""
import argparse
import csv
import json
from pathlib import Path


GATE_PERCENT = 1.0


def revolution_means(rows, keys):
    """Means over n-1 < rev <= n for every complete revolution n."""
    end = rows[-1]["rev"]
    means = []
    for revolution in range(1, int(end + 1e-6) + 1):
        window = [row for row in rows if revolution - 1 + 1e-9 < row["rev"] <= revolution + 1e-9]
        mean = {key: sum(row[key] for row in window) / len(window) for key in keys}
        means.append(dict(rev=revolution, **mean))
    return means


def convergence_gate(means, keys, last=2, percent=GATE_PERCENT):
    """Largest relative change between successive revolution means, last `last` changes."""
    if len(means) < last + 1:
        return dict(converged=False, max_change_percent=None,
                    reason=f"needs {last + 1} complete revolutions")
    tail = means[-(last + 1):]
    change = {key: max(abs(b[key] - a[key]) / abs(b[key]) * 100.0
                       for a, b in zip(tail, tail[1:]))
              for key in keys}
    return dict(converged=all(value < percent for value in change.values()),
                max_change_percent=change, threshold_percent=percent)


def check(run):
    with (run / "power.csv").open() as stream:
        rows = [{key: float(value) for key, value in row.items()}
                for row in csv.DictReader(stream)]
    if not rows:
        raise ValueError("No monitor rows")
    end = rows[-1]["rev"]
    window = [row for row in rows if row["rev"] > end - 1]
    means = {key: sum(row[key] for row in window) / len(window)
             for key in ("CT", "CQ", "CP", "Q_Nm", "P_monitor_W",
                         "P_force_dot_velocity_W", "Fx_N")}
    # Turbine coefficients must match the native rotor monitor exactly.
    with next(run.glob("*_convergence.csv")).open() as stream:
        native = list(csv.DictReader(stream))
    if len(native) != len(rows):
        raise ValueError("Native and independent monitor lengths differ")
    for row, raw in zip(rows, native):
        if abs(row["CT"] - float(raw["CT_1"])) > 1e-12 or abs(abs(row["CQ"]) - abs(float(raw["CQ_1"]))) > 1e-12:
            raise ValueError("Turbine coefficient normalization mismatch")
    times = []
    previous = 0.0
    for revolution in range(1, int(end + 1e-6) + 1):
        at_end = next(row for row in rows if row["rev"] >= revolution - 1e-6)
        times.append(at_end["wall_s"] - previous)
        previous = at_end["wall_s"]
    estimate = None
    if len(times) >= 2:
        slope = max(0.0, times[-1] - times[-2])
        estimate = sum(times) + sum(times[-1] + slope * i for i in range(1, 11 - len(times)))
    with (run / "geometry.csv").open() as stream:
        geometry = list(csv.DictReader(stream))
    sweep_ok = all(float(row["generated_LE_x_m"]) < 0 < float(row["generated_TE_x_m"])
                   for row in geometry)
    per_revolution = revolution_means(rows, ("CT", "CQ", "CP"))
    result = dict(last_rev_mean=means, completed_revolutions=end,
                  per_revolution=per_revolution,
                  convergence_gate=convergence_gate(per_revolution, ("CT", "CQ")),
                  wall_seconds_by_revolution=times, estimated_10rev_solver_seconds=estimate,
                  sweep_LE_ahead_of_axis=sweep_ok,
                  turbine_extraction=means["P_force_dot_velocity_W"] > 0,
                  in_requested_CT_CQ_band=(0.45 <= means["CT"] <= 0.47 and 0.065 <= means["CQ"] <= 0.070),
                  note="Fountain suppression lasts 3 revs; trust only a passed convergence_gate.")
    print(json.dumps(result, indent=2))
    if not sweep_ok or means["P_force_dot_velocity_W"] <= 0:
        raise SystemExit("FAIL: geometry or physical extraction sign")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    check(parser.parse_args().run)
