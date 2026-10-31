#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare an AeroDyn-driver Phase VI case (`buildAeroDynCase.py`) with the measured data.

Same definitions as `comparePhaseVI.py`, applied to the AeroDyn output:

    power   RtAeroPwr, blades only, no mechanical loss   (comparePhaseVI `power_kw`, ROTPOW)
    thrust  RtAeroFxh, blades only, no tower or hub      (comparePhaseVI `thrust_n`, blade scope, EAEROTH)
    torque  power / omega                                (comparePhaseVI `torque_nm`, LSSTQCOR)
    Cn, Ct  nodal chord-referenced coefficients (Cl cos a + Cd sin a, Cl sin a - Cd cos a),
            mean of both blades, linearly interpolated in r/R to 0.30/0.47/0.63/0.80/0.95
            like `comparePhaseVI.interpolate`, against the experiment's CN/CT (chord line)
    error % (sim - experiment) / experiment, experiment from `comparePhaseVI.load_experiment`

Averages run over whole revolutions counted back from the end of the run. The last two
whole revolutions give the convergence figure (change of power and of Cn at r/R 0.95
between them, below 1 % = converged; an OLAF run also needs a full wake before them).

Exit codes: 0 comparison written, 1 missing input, 2 fewer whole revolutions than requested.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parent / "tools"))

import comparePhaseVI  # noqa: E402

STATIONS = comparePhaseVI.STATIONS
DEFAULT_EXPERIMENT = comparePhaseVI.DEFAULT_EXPERIMENT / "uae6-archive"
CONVERGENCE_PCT = 1.0
EXIT_OK, EXIT_MISSING_INPUT, EXIT_SHORT_WINDOW = 0, 1, 2


class MissingInput(Exception):
    pass


class ShortWindow(Exception):
    pass


def read_output(path: Path) -> tuple[list[str], np.ndarray]:
    """Channel names and the data matrix of an OpenFAST text output (`Time` row, unit row, data)."""
    path = Path(path)
    if not path.is_file():
        raise MissingInput(f"{path}: AeroDyn output not found")
    names: list[str] | None = None
    rows: list[list[float]] = []
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            parts = line.split()
            if names is None:
                if parts and parts[0].lower() == "time":
                    names = parts
                continue
            try:
                values = [float(token) for token in parts]
            except ValueError:
                continue  # the unit row
            if len(values) == len(names):
                rows.append(values)
    if names is None or not rows:
        raise MissingInput(f"{path}: no Time header or no data rows")
    return names, np.asarray(rows, dtype=float)


def revolution_mask(time: np.ndarray, period: float, first: int, count: int, dt: float) -> np.ndarray:
    """Rows of revolutions `first .. first+count-1` counted back from the last row, half-open (start, end]."""
    t_end = time[-1]
    tol = 0.5 * dt
    start = t_end - (first + count) * period
    end = t_end - first * period
    if start < time[0] - tol:
        raise ShortWindow(f"fewer than {first + count} whole revolutions in the output")
    return (time > start + tol) & (time <= end + tol)


def node_profile(columns: dict[str, np.ndarray], mask: np.ndarray, radii: list[float], rotor_radius: float):
    """Time-mean (r/R, Cn, Ct, alpha) per node, mean of the output blades."""
    profile = []
    for index, radius in enumerate(radii, start=1):
        values = {}
        for channel in ("cn", "ct", "alpha"):
            samples = [
                columns[f"b{blade}n{index:03d}{channel}"][mask].mean()
                for blade in (1, 2)
                if f"b{blade}n{index:03d}{channel}" in columns
            ]
            if not samples:
                raise MissingInput(f"no output channel for node {index} {channel}")
            values[channel] = float(np.mean(samples))
        profile.append((radius / rotor_radius, values["cn"], values["ct"], values["alpha"]))
    profile.sort()
    return profile


def compare_case(case_dir: Path, revolutions: int | None = None, experiment_dir: Path | None = None) -> dict:
    case_dir = Path(case_dir)
    case_file = case_dir / "case.json"
    if not case_file.is_file():
        raise MissingInput(f"{case_file}: not found")
    case = json.loads(case_file.read_text())
    inputs = case["inputs"]
    rpm = inputs["rotor_speed_rpm"]["value"]
    rotor_radius = inputs["rotor_radius_m"]["value"]
    period = case["time"]["period_s"]
    revolutions = int(revolutions if revolutions is not None else case["time"]["averaging_revolutions"])
    names, data = read_output(case_dir / case["output"])
    # The driver prefixes AeroDyn's nodal channels with the module letter (`AB1N001Cn`).
    columns = {re.sub(r"^a(?=b\dn\d{3})", "", name.lower()): data[:, i] for i, name in enumerate(names)}
    for needed in ("time", "rtaeropwr", "rtaerofxh"):
        if needed not in columns:
            raise MissingInput(f"{case['output']}: channel {needed} missing")
    time = columns["time"]
    dt = float(np.median(np.diff(time)))
    radii = [node["radius"] for node in case["nodes"]]

    def window_stats(first: int, count: int) -> dict:
        mask = revolution_mask(time, period, first, count, dt)
        profile = node_profile(columns, mask, radii, rotor_radius)
        return {
            "power_w": float(columns["rtaeropwr"][mask].mean()),
            "thrust_n": float(columns["rtaerofxh"][mask].mean()),
            "profile": profile,
            "samples": int(mask.sum()),
        }

    mean = window_stats(0, revolutions)
    omega = rpm * math.pi / 30.0
    sequence, speed = case["sequence"], case["speed_m_s"]
    if "experiment" in case:
        # A table-point case (`buildAeroDynCase.build_point_case`) carries its own experiment row.
        experiment = case["experiment"]["performance"]
        spanwise = {float(station): values for station, values in case["experiment"]["spanwise"].items()}
        experiment = {**experiment, "file_name": experiment.get("file_name", case["point"]["id"])}
    else:
        experiment, spanwise = comparePhaseVI.load_experiment(
            experiment_dir or DEFAULT_EXPERIMENT, sequence, speed
        )

    def error_pct(value: float, measured: float) -> float:
        return 100.0 * (value - measured) / measured

    power_kw = mean["power_w"] / 1.0e3
    metrics = {
        "case": str(case_dir),
        "wake": case["wake"],
        "sequence": sequence,
        "speed_m_s": speed,
        "experiment_row": experiment["file_name"],
        "rotor_speed_rpm": rpm,
        "rho_kg_m3": inputs["rho_kg_m3"]["value"],
        "pitch_deg": inputs["pitch_deg"]["value"],
        "yaw_deg": inputs["yaw_deg"]["value"],
        "power_kw": power_kw,
        "power_exp_kw": float(experiment["rotpow_kw"]),
        "power_error_pct": error_pct(power_kw, float(experiment["rotpow_kw"])),
        "thrust_n": mean["thrust_n"],
        "thrust_exp_n": float(experiment["eaeroth_n"]),
        "thrust_error_pct": error_pct(mean["thrust_n"], float(experiment["eaeroth_n"])),
        "torque_nm": mean["power_w"] / omega,
        "torque_exp_nm": float(experiment["lsstqcor_nm"]),
        "window": {
            "revolutions": revolutions,
            "t_start_s": float(time[-1] - revolutions * period),
            "t_end_s": float(time[-1]),
            "samples": mean["samples"],
        },
        "definitions": {
            "power": "RtAeroPwr, blades only (comparePhaseVI power_kw)",
            "thrust": "RtAeroFxh, blades only, no tower (comparePhaseVI thrust_n, blade scope)",
            "torque": "RtAeroPwr / omega (comparePhaseVI torque_nm)",
            "spanwise": "nodal Cn, Ct (chord line), mean of blades 1 and 2, linear in r/R",
        },
    }
    metrics["torque_error_pct"] = error_pct(metrics["torque_nm"], metrics["torque_exp_nm"])
    metrics["within_band"] = {
        "power": abs(metrics["power_error_pct"]) <= 100 * comparePhaseVI.TURBINE_BANDS["power"],
        "thrust": abs(metrics["thrust_error_pct"]) <= 100 * comparePhaseVI.TURBINE_BANDS["thrust"],
        "torque": abs(metrics["torque_error_pct"]) <= 100 * comparePhaseVI.TURBINE_BANDS["torque"],
    }

    stations = {}
    for station in STATIONS:
        cn, ct, alpha = comparePhaseVI.interpolate(mean["profile"], station)
        measured = spanwise[station]
        band_n = max(comparePhaseVI.SPANWISE_BAND_MIN, comparePhaseVI.SPANWISE_BAND_FRACTION * abs(measured["cn"]))
        band_t = max(comparePhaseVI.SPANWISE_BAND_MIN, comparePhaseVI.SPANWISE_BAND_FRACTION * abs(measured["ct"]))
        stations[f"{station:.2f}"] = {
            "cn": cn,
            "ct": ct,
            "alpha_deg": alpha,
            "cn_exp": measured["cn"],
            "ct_exp": measured["ct"],
            "cn_error_pct": error_pct(cn, measured["cn"]),
            "ct_error_pct": error_pct(ct, measured["ct"]),
            "within_band": abs(cn - measured["cn"]) <= band_n and abs(ct - measured["ct"]) <= band_t,
        }
    metrics["stations"] = stations

    # Convergence: last two whole revolutions, individually.
    try:
        last, previous = window_stats(0, 1), window_stats(1, 1)
    except ShortWindow:
        metrics["convergence"] = None
    else:
        cn_last = comparePhaseVI.interpolate(last["profile"], 0.95)[0]
        cn_previous = comparePhaseVI.interpolate(previous["profile"], 0.95)[0]
        power_change = 100.0 * abs(last["power_w"] - previous["power_w"]) / abs(last["power_w"])
        cn_change = 100.0 * abs(cn_last - cn_previous) / abs(cn_last)
        # An OLAF run is only converged once the last two revolutions lie after the wake is full.
        olaf = case.get("olaf")
        filled = olaf is None or (time[-1] - 2 * period) >= olaf["n_nw_panels"] * case["time"]["dt_s"] - dt
        metrics["convergence"] = {
            "power_change_pct": power_change,
            "cn_095_change_pct": cn_change,
            "threshold_pct": CONVERGENCE_PCT,
            "wake_filled": bool(filled),
            "converged": bool(filled and power_change < CONVERGENCE_PCT and cn_change < CONVERGENCE_PCT),
        }
    return {"metrics": metrics, "profile": mean["profile"]}


def render_table(metrics: dict) -> str:
    lines = [
        f"AeroDyn {metrics['wake'].upper()}  Sequence {metrics['sequence']}  U = {metrics['speed_m_s']:g} m/s  "
        f"({metrics['experiment_row']}, {metrics['rotor_speed_rpm']:.3f} rpm, rho {metrics['rho_kg_m3']:.4f})",
        f"window: last {metrics['window']['revolutions']} whole revolution(s), t = "
        f"{metrics['window']['t_start_s']:.3f} .. {metrics['window']['t_end_s']:.3f} s",
        "",
        f"{'quantity':<10}{'sim':>14}{'experiment':>14}{'error %':>10}",
        f"{'power kW':<10}{metrics['power_kw']:>14.4f}{metrics['power_exp_kw']:>14.4f}{metrics['power_error_pct']:>10.2f}",
        f"{'thrust N':<10}{metrics['thrust_n']:>14.2f}{metrics['thrust_exp_n']:>14.2f}{metrics['thrust_error_pct']:>10.2f}",
        f"{'torque Nm':<10}{metrics['torque_nm']:>14.2f}{metrics['torque_exp_nm']:>14.2f}{metrics['torque_error_pct']:>10.2f}",
        "",
        f"{'r/R':>6}{'Cn':>9}{'Cn exp':>9}{'dCn %':>8}{'Ct':>9}{'Ct exp':>9}{'dCt %':>8}{'alpha deg':>11}  band",
    ]
    for key, row in metrics["stations"].items():
        lines.append(
            f"{key:>6}{row['cn']:>9.4f}{row['cn_exp']:>9.4f}{row['cn_error_pct']:>8.1f}"
            f"{row['ct']:>9.4f}{row['ct_exp']:>9.4f}{row['ct_error_pct']:>8.1f}{row['alpha_deg']:>11.2f}  "
            f"{'yes' if row['within_band'] else 'no'}"
        )
    conv = metrics["convergence"]
    lines.append("")
    if conv is None:
        lines.append("convergence: fewer than two whole revolutions in the output")
    else:
        lines.append(
            f"convergence (last two revolutions): power {conv['power_change_pct']:.3f} %, "
            f"Cn(0.95) {conv['cn_095_change_pct']:.3f} %  -> {'converged' if conv['converged'] else 'NOT converged'} (< {conv['threshold_pct']:g} %)"
        )
        if not conv["wake_filled"]:
            lines.append("wake not yet full over the last two revolutions: not a result")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", type=Path, required=True, help="case directory written by buildAeroDynCase.py")
    parser.add_argument("--revolutions", type=int, default=None, help="whole revolutions to average (default: case.json averaging_revolutions)")
    parser.add_argument("--experiment", type=Path, default=DEFAULT_EXPERIMENT, help="experiment table directory (default: data/experiment/uae6-archive, the gate comparison's)")
    parser.add_argument("--out", type=Path, default=None, help="metrics.json path (default: <case>/metrics.json)")
    args = parser.parse_args(argv)
    try:
        result = compare_case(args.case, args.revolutions, args.experiment)
    except MissingInput as exc:
        print(f"missing input: {exc}", file=sys.stderr)
        return EXIT_MISSING_INPUT
    except (FileNotFoundError, KeyError) as exc:
        print(f"missing input: {exc}", file=sys.stderr)
        return EXIT_MISSING_INPUT
    except ShortWindow as exc:
        print(f"short window: {exc}", file=sys.stderr)
        return EXIT_SHORT_WINDOW
    metrics = result["metrics"]
    out = args.out or (args.case / "metrics.json")
    out.write_text(json.dumps(metrics, indent=2) + "\n")
    print(render_table(metrics))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
