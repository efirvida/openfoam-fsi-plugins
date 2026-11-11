#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Blade root flap bending moment: ALM vs the UAE Phase VI measurement.

Experiment (`data/experiment/yaw-pitch/pitch_performance.csv`, one row per test
point, picked by sequence + wind speed + nominal yaw 0 [+ nominal pitch]):

    eaerorfb_nm   EAERORFB, the acquisition system's ESTIMATED AERODYNAMIC root
                  flap bending (derived channel). Aerodynamic only: no gravity,
                  centrifugal or teeter contribution (those are separate
                  channels, e.g. ETEEMRFB). THE FAIR COMPARISON: the ALM carries
                  aerodynamic load only.
    b1rfb_nm      B1RFB, blade-1 strain-gauge root flap bending. Measured
                  structural response (gravity, centrifugal and gauge
                  calibration included); reported as context, not as the
                  fair comparison.

(The S/H tables under `data/experiment/uae6-archive/` do not carry these
channels; only `yaw-pitch/*_performance.csv` does.)

ALM: blade 1 only, from the written element CSVs
`postProcessing/actuatorLineElements/0/<turbine>.blade1.element*.csv`
(resumed segments joined by `comparePhaseVI.read_rows_resumed`):

    M = rho * sum_i  mean_window(fx_i) * (r_i - r_gauge)       r_i >= r_gauge

`fx` is the written element force along the rotor axis (the thrust direction,
the same component `comparePhaseVI` sums for thrust) in KINEMATIC units (N/rho,
as `reconcileTorqueIntegral.py` and `compareSectionLoads.py` already treat it),
so it is multiplied by rho (experiment row, `--rho`). `r_i` is the element
radius mapped from `root_dist` as `comparePhaseVI.r_over_r_from_root_dist`.
The blade is straight and unconed, so the out-of-plane force acts along the
blade axis and the arm is the radial distance to the gauge.

Gauge radius: the repository does not record where the B1RFB bridge sits; the
default `--gauge-radius 0.5083` m is the blade-root attachment radius (NREL/TP-
500-29955 p73, `ROOT_CUTOUT_RADIUS`). It is an assumption, settable.

Blade 1 only; the experiment row is blade 1 as well, so no blade scaling is
applied. Whole-rotor loading is assumed axisymmetric (uniform inflow, 0 yaw).
The 10 % band is informational and never changes the exit code.

Exit codes: 0 ok, 1 missing input (run, elements, experiment row), 2 the run
does not cover the averaging window.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import comparePhaseVI as base
from comparePhaseVI import (
    EXIT_MISSING_INPUT,
    EXIT_OK,
    EXIT_SHORT_WINDOW,
    ROOT,
    ROOT_CUTOUT_RADIUS,
    MissingInput,
    ShortWindow,
    _exit,
    mean,
    read_rows_resumed,
)

DEFAULT_EXPERIMENT = ROOT / "data" / "experiment" / "yaw-pitch" / "pitch_performance.csv"
DEFAULT_GAUGE_RADIUS = ROOT_CUTOUT_RADIUS
BAND_PERCENT = 10.0
NOMINAL_TOLERANCE = 1.0e-6
# channel -> is it the fair (aerodynamic-only) comparison
CHANNELS = (("eaerorfb_nm", True), ("b1rfb_nm", False))
CSV_FIELDS = (
    "run", "sequence", "speed_m_s", "yaw_deg", "pitch_deg", "channel",
    "fair_comparison", "experiment_nm", "alm_nm", "delta_nm", "delta_pct",
    "band_pct", "within_10pct", "rho_kg_m3", "gauge_radius_m",
    "window_start_s", "window_end_s", "n_elements", "n_experiment_rows",
)


def load_reference(experiment: Path, sequence: str, speed: float, yaw: float,
                   pitch: float | None):
    """(mean row, number of rows) for the requested test point."""
    if not experiment.is_file():
        raise MissingInput(f"{experiment}: experiment table not found")
    with experiment.open(encoding="utf-8") as stream:
        rows = [
            row for row in csv.DictReader(stream)
            if row["sequence"] == sequence
            and abs(float(row["wind_speed_m_s"]) - speed) < NOMINAL_TOLERANCE
            and abs(float(row["yaw_nominal_deg"]) - yaw) < NOMINAL_TOLERANCE
            and (pitch is None
                 or abs(float(row["pitch_nominal_deg"]) - pitch) < NOMINAL_TOLERANCE)
        ]
    if not rows:
        raise MissingInput(
            f"no experiment row for sequence {sequence} speed {speed:g} "
            f"yaw {yaw:g}" + ("" if pitch is None else f" pitch {pitch:g}")
            + f" in {experiment}"
        )
    pitches = sorted({float(row["pitch_nominal_deg"]) for row in rows})
    if len(pitches) > 1:
        raise MissingInput(
            f"experiment rows span pitches {pitches}: select one with --pitch"
        )
    result = dict(rows[0])
    for key in ("rho_kg_m3", "b1rfb_nm", "eaerorfb_nm"):
        result[key] = mean([float(row[key]) for row in rows])
    return result, len(rows)


def window_for(cfg, speed, config_sequence, revolutions):
    start, end, period = base.window_bounds(cfg, speed, config_sequence)
    if revolutions is not None:
        start, end = int(revolutions[0]) * period, int(revolutions[1]) * period
    return start, end, period


def element_histories(run_dir: Path):
    directory = run_dir / base.ELEMENT_DIR
    if not directory.is_dir():
        raise MissingInput(f"{directory}: not found")
    files = sorted(directory.glob("*.blade1.element*.csv"))
    if not files:
        raise MissingInput(f"{directory}: no blade1 element CSVs")
    histories = []
    for path in files:
        rows = read_rows_resumed(path)
        if not rows:
            raise MissingInput(f"{path}: no data rows")
        histories.append((path, rows))
    return histories


def blade_moment(histories, start, end, period, radius, gauge, allow_short):
    """(kinematic moment [N.m/rho], kinematic thrust [N/rho], elements used)."""
    last = min(rows[-1]["time"] for _, rows in histories)
    if last < end - 0.01 * period and not allow_short:
        raise ShortWindow(
            f"run reaches t={last:.4f} s, averaging window ends at {end:.4f} s "
            "(use --allow-short-window to average what exists)"
        )
    moment = thrust = 0.0
    used = 0
    for path, rows in histories:
        window = [row for row in rows if start <= row["time"] <= end]
        if not window:
            if not allow_short:
                raise ShortWindow(f"{path}: no samples in the averaging window")
            window = rows
        r = base.r_over_r_from_root_dist(mean([row["root_dist"] for row in window]), radius) * radius
        fx = mean([row["fx"] for row in window])
        thrust += fx
        if r >= gauge:
            moment += fx * (r - gauge)
            used += 1
    return moment, thrust, used


def thrust_closure(run_dir, start, end, rho, speed, radius, thrust_kin):
    """blade-1 element thrust * rho over cd_blade1 * q_dyn, or None."""
    path = run_dir / base.TURBINE_CSV
    if not path.is_file():
        return None
    rows = [r for r in read_rows_resumed(path) if start <= r["time"] <= end]
    if not rows or "cd_blade1" not in rows[0]:
        return None
    q_dyn = 0.5 * rho * math.pi * radius**2 * speed**2
    declared = mean([r["cd_blade1"] for r in rows]) * q_dyn
    return None if declared == 0 else rho * thrust_kin / declared


def build_rows(args, reference, count, moment_nm, rho, window, used):
    rows = []
    for channel, fair in CHANNELS:
        measured = float(reference[channel])
        delta = moment_nm - measured
        pct = 100.0 * delta / measured if measured else math.nan
        rows.append({
            "run": args.run_dir.name,
            "sequence": args.sequence,
            "speed_m_s": f"{args.speed:g}",
            "yaw_deg": f"{args.yaw:g}",
            "pitch_deg": reference["pitch_nominal_deg"],
            "channel": channel,
            "fair_comparison": "yes" if fair else "no",
            "experiment_nm": f"{measured:.6f}",
            "alm_nm": f"{moment_nm:.6f}",
            "delta_nm": f"{delta:.6f}",
            "delta_pct": f"{pct:.4f}",
            "band_pct": f"{BAND_PERCENT:g}",
            "within_10pct": "yes" if abs(pct) <= BAND_PERCENT else "no",
            "rho_kg_m3": f"{rho:.6f}",
            "gauge_radius_m": f"{args.gauge_radius:g}",
            "window_start_s": f"{window[0]:.6f}",
            "window_end_s": f"{window[1]:.6f}",
            "n_elements": used,
            "n_experiment_rows": count,
        })
    return rows


def report_text(args, rows, closure, window):
    lines = [
        f"Root flap bending, blade 1: {args.run_dir.name}",
        f"sequence {args.sequence}  speed {args.speed:g} m/s  yaw {args.yaw:g}  "
        f"pitch {rows[0]['pitch_deg']} deg  window t in [{window[0]:.4f}, {window[1]:.4f}] s",
        f"gauge radius {args.gauge_radius:g} m (assumed: blade root attachment); "
        f"rho {rows[0]['rho_kg_m3']} kg/m^3; elements {rows[0]['n_elements']}",
        "Blade 1 only; axisymmetric rotor assumed. ALM = aerodynamic load only.",
        "",
        f"{'channel':<14}{'fair':<6}{'experiment [N.m]':>18}{'ALM [N.m]':>14}"
        f"{'delta [%]':>12}  within 10 % (informational)",
    ]
    for row in rows:
        lines.append(
            f"{row['channel']:<14}{row['fair_comparison']:<6}{float(row['experiment_nm']):>18.1f}"
            f"{float(row['alm_nm']):>14.1f}{float(row['delta_pct']):>+12.2f}  {row['within_10pct']}"
        )
    lines.append("")
    lines.append(
        "thrust closure (blade-1 element thrust * rho / (cd_blade1 * q_dyn)): "
        + ("n/a" if closure is None else f"{closure:.4f}")
    )
    return "\n".join(lines) + "\n"


def parse_args(argv):
    p = argparse.ArgumentParser(
        description="ALM vs measured blade-1 root flap bending (Phase VI).")
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--speed", type=float, required=True)
    p.add_argument("--sequence", choices=("I", "T", "H", "U", "J", "S"), default="H")
    p.add_argument("--config-sequence", choices=("H", "S"), default=None,
                   help="case.yaml speed table (default: S for S, else H)")
    p.add_argument("--yaw", type=float, default=0.0, help="nominal yaw [deg]")
    p.add_argument("--pitch", type=float, default=None, help="nominal pitch [deg]")
    p.add_argument("--experiment", type=Path, default=DEFAULT_EXPERIMENT)
    p.add_argument("--config", type=Path, default=base.DEFAULT_CONFIG)
    p.add_argument("--revolutions", nargs=2, type=float, metavar=("DISCARD", "END"),
                   help="averaging window override (integer-truncated)")
    p.add_argument("--gauge-radius", type=float, default=DEFAULT_GAUGE_RADIUS,
                   help="B1RFB gauge radius [m] (default: blade root attachment)")
    p.add_argument("--rho", default="auto", help="'auto' (experiment row) or kg/m^3")
    p.add_argument("--allow-short-window", action="store_true")
    p.add_argument("--out", type=Path, default=None,
                   help="write root_moment_comparison.csv and report.txt here")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        cfg = base.load_config(args.config)
        config_sequence = args.config_sequence or ("S" if args.sequence == "S" else "H")
        radius = float(cfg["turbine"]["radius"])
        reference, count = load_reference(
            args.experiment, args.sequence, args.speed, args.yaw, args.pitch)
        rho = float(reference["rho_kg_m3"]) if args.rho == "auto" else float(args.rho)
        if not args.run_dir.is_dir():
            raise MissingInput(f"{args.run_dir}: run directory not found")
        window = window_for(cfg, args.speed, config_sequence, args.revolutions)[:2]
        period = window_for(cfg, args.speed, config_sequence, None)[2]
        histories = element_histories(args.run_dir)
        kinematic, thrust_kin, used = blade_moment(
            histories, window[0], window[1], period, radius,
            args.gauge_radius, args.allow_short_window)
    except ShortWindow as exc:
        return _exit(str(exc), EXIT_SHORT_WINDOW)
    except (MissingInput, FileNotFoundError, KeyError, ValueError) as exc:
        return _exit(str(exc), EXIT_MISSING_INPUT)
    moment = rho * kinematic
    closure = thrust_closure(args.run_dir, window[0], window[1], rho,
                             args.speed, radius, thrust_kin)
    rows = build_rows(args, reference, count, moment, rho, window, used)
    text = report_text(args, rows, closure, window)
    if args.out is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        with (args.out / "root_moment_comparison.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        (args.out / "report.txt").write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
