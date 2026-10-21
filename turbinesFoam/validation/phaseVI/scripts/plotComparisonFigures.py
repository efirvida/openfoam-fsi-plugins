#!/usr/bin/env python3
"""Figures for the Phase VI comparison outputs (P1.4 epsilon sweep, P2.1 calibration).

A pure reader: it plots what `comparePhaseVI.py --out DIR` wrote
(`turbine_comparison.csv`, `spanwise_comparison.csv`, `metrics.json`) and the
`turbine.csv` time history of the runs. It never recomputes a calibrated
quantity.

Usage:
    # P2.1: one comparePhaseVI output directory per speed
    python3 scripts/plotComparisonFigures.py p21 --out-dir analysis/figures \
        --case 7=analysis/p21/U7 --case 10=analysis/p21/U10

    # P1.4: one output directory per ASM arm; ALM and the experiment come
    # from the reference directory
    python3 scripts/plotComparisonFigures.py eps --out-dir analysis/figures \
        --reference analysis/p14/alm-hubfix \
        --arm 1=analysis/p14/asm-mf0p5 --arm 2=analysis/p14/asm-mf1 \
        --arm 4=analysis/p14/asm-mf2 --arm 8=analysis/p14/asm-mf4
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from comparePhaseVI import read_rows_resumed  # noqa: E402

ROTOR_RADIUS = 5.029
TURBINE_CSV = Path("postProcessing") / "turbines" / "0" / "turbine.csv"
MODELS = ("alm", "asm", "asm-mesh")
COLORS = {"alm": "tab:blue", "asm": "tab:orange", "asm-mesh": "tab:green"}
QUANTITIES = (("power", "P [kW]"), ("torque", "Q [Nm]"), ("thrust", "T [N]"))
TURBINE_BAND = 0.15


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def read_metrics(directory: Path) -> dict:
    return json.loads((directory / "metrics.json").read_text(encoding="utf-8"))


def parse_pairs(items: list[str]) -> list[tuple[float, Path]]:
    pairs = []
    for item in items:
        key, _, path = item.partition("=")
        pairs.append((float(key), Path(path)))
    return pairs


def save(figure, out_dir: Path, name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    figure.tight_layout()
    figure.savefig(path, dpi=140)
    plt.close(figure)
    return path


def turbine_rows(directory: Path) -> dict[tuple[str, str], dict]:
    return {(row["model"], row["quantity"]): row
            for row in read_csv(directory / "turbine_comparison.csv")}


def plot_turbine_loads(cases: list[tuple[float, Path]], out_dir: Path) -> Path:
    """Absolute value and relative error of P, Q and T for every model and speed."""
    figure, axes = plt.subplots(2, 3, figsize=(13, 7))
    width = 0.25
    for column, (quantity, label) in enumerate(QUANTITIES):
        top, bottom = axes[0][column], axes[1][column]
        for index, (speed, directory) in enumerate(cases):
            rows = turbine_rows(directory)
            for offset, model in enumerate(MODELS):
                row = rows.get((model, quantity))
                if row is None:
                    continue
                x = index + (offset - 1) * width
                top.bar(x, float(row["sim"]), width, color=COLORS[model],
                        label=model if index == 0 else None)
                bottom.bar(x, 100.0 * float(row["delta_frac"]), width,
                           color=COLORS[model])
            experiment = next((float(r["experiment"]) for (m, q), r in rows.items()
                               if q == quantity), None)
            if experiment is not None:
                top.hlines(experiment, index - 0.45, index + 0.45, color="black",
                           linestyle="--", label="experiment" if index == 0 else None)
        for axis in (top, bottom):
            axis.set_xticks(range(len(cases)))
            axis.set_xticklabels([f"{speed:g} m/s" for speed, _ in cases])
            axis.grid(axis="y", alpha=0.3)
        top.set_ylabel(label)
        top.set_title(label)
        bottom.axhline(0.0, color="black", linewidth=0.8)
        bottom.axhspan(-100 * TURBINE_BAND, 100 * TURBINE_BAND, color="gray", alpha=0.15)
        bottom.set_ylabel("error vs experiment [%]")
    axes[0][0].legend(fontsize=8)
    figure.suptitle("Turbine loads: simulation against experiment (grey: +-15 % band)")
    return save(figure, out_dir, "p21-turbine-loads.png")


def plot_spanwise(cases: list[tuple[float, Path]], out_dir: Path, plane: bool) -> Path:
    """Spanwise coefficients against the five instrumented stations."""
    if plane:
        columns = (("c_ref_n_plane", "cth_exp", "C_Thrust (plane of rotation)"),
                   ("c_ref_t_plane", "ctq_exp", "C_Torque (plane of rotation)"))
        name = "p21-spanwise-plane.png"
    else:
        columns = (("c_ref_n", "cn_exp", "CN (chord-referenced)"),
                   ("c_ref_t", "ct_exp", "CT (chord-referenced)"))
        name = "p21-spanwise-chord.png"
    figure, axes = plt.subplots(len(cases), 2, figsize=(11, 4 * len(cases)),
                                squeeze=False)
    for row_index, (speed, directory) in enumerate(cases):
        rows = read_csv(directory / "spanwise_comparison.csv")
        for col_index, (sim_key, exp_key, title) in enumerate(columns):
            axis = axes[row_index][col_index]
            for model in MODELS:
                subset = [r for r in rows if r["model"] == model]
                if subset:
                    axis.plot([float(r["r_over_R"]) for r in subset],
                              [float(r[sim_key]) for r in subset], "o-",
                              color=COLORS[model], label=model)
            reference = [r for r in rows if r["model"] == MODELS[0]] or rows
            axis.plot([float(r["r_over_R"]) for r in reference],
                      [float(r[exp_key]) for r in reference], "ks", markersize=8,
                      label="experiment")
            axis.set_title(f"{title}, {speed:g} m/s")
            axis.set_xlabel("r/R")
            axis.grid(alpha=0.3)
    axes[0][0].legend(fontsize=8)
    return save(figure, out_dir, name)


def plot_spanwise_error(cases: list[tuple[float, Path]], out_dir: Path) -> Path:
    """Relative spanwise error per station; a red edge marks a point outside the band."""
    figure, axes = plt.subplots(len(cases), 2, figsize=(11, 4 * len(cases)),
                                squeeze=False)
    width = 0.25
    for row_index, (speed, directory) in enumerate(cases):
        rows = read_csv(directory / "spanwise_comparison.csv")
        for col_index, (key, title) in enumerate((("dcn_frac", "CN"), ("dct_frac", "CT"))):
            axis = axes[row_index][col_index]
            stations = sorted({r["r_over_R"] for r in rows}, key=float)
            for offset, model in enumerate(MODELS):
                for position, station in enumerate(stations):
                    match = [r for r in rows
                             if r["model"] == model and r["r_over_R"] == station]
                    if not match:
                        continue
                    outside = match[0]["within_band"] != "yes"
                    axis.bar(position + (offset - 1) * width,
                             100.0 * float(match[0][key]), width,
                             color=COLORS[model],
                             edgecolor="red" if outside else "none", linewidth=1.5,
                             label=model if position == 0 else None)
            axis.axhline(0.0, color="black", linewidth=0.8)
            axis.set_xticks(range(len(stations)))
            axis.set_xticklabels(stations)
            axis.set_xlabel("r/R")
            axis.set_ylabel("error vs experiment [%]")
            axis.set_title(f"{title} error, {speed:g} m/s (red edge: outside band)")
            axis.grid(axis="y", alpha=0.3)
    axes[0][0].legend(fontsize=8)
    return save(figure, out_dir, "p21-spanwise-error.png")


def read_cp_history(run_dir: Path) -> tuple[list[float], list[float], float]:
    rows = read_rows_resumed(run_dir / TURBINE_CSV)
    return ([float(r["time"]) for r in rows], [float(r["cp"]) for r in rows],
            float(rows[-1]["tsr"]))


def plot_cp_history(cases: list[tuple[float, Path]], out_dir: Path) -> Path:
    """cp against revolutions with the averaging window shaded."""
    figure, axes = plt.subplots(len(cases), 1, figsize=(10, 4 * len(cases)),
                                squeeze=False)
    for index, (speed, directory) in enumerate(cases):
        metrics = read_metrics(directory)
        axis = axes[index][0]
        for model in MODELS:
            entry = metrics["models"].get(model)
            if entry is None:
                continue
            time, cp, tsr = read_cp_history(Path(entry["metrics"]["run_dir"]))
            per_rev = 2.0 * math.pi * ROTOR_RADIUS / (tsr * speed)
            axis.plot([t / per_rev for t in time], cp, color=COLORS[model],
                      label=model, linewidth=1.0)
        window = metrics.get("window", {})
        start, end = window.get("discard_revolutions"), window.get("end_revolutions")
        if start is not None and end is not None:
            axis.axvspan(start, end, color="gray", alpha=0.15, label="averaging window")
        axis.set_title(f"cp history, {speed:g} m/s")
        axis.set_xlabel("revolutions")
        axis.set_ylabel("cp")
        axis.grid(alpha=0.3)
    axes[0][0].legend(fontsize=8)
    return save(figure, out_dir, "p21-cp-history.png")


def plot_drift(cases: list[tuple[float, Path]], out_dir: Path) -> Path:
    """Per-revolution cp inside the averaging window, relative to its mean."""
    figure, axes = plt.subplots(1, len(cases), figsize=(6 * len(cases), 4),
                                squeeze=False)
    for index, (speed, directory) in enumerate(cases):
        metrics = read_metrics(directory)
        axis = axes[0][index]
        for model in MODELS:
            entry = metrics["models"].get(model)
            if entry is None:
                continue
            values = entry["drift"]["cp"]["per_revolution"]
            mean = sum(values) / len(values)
            axis.plot(range(1, len(values) + 1), [100.0 * (v / mean - 1.0) for v in values],
                      "o-", color=COLORS[model], label=model)
        axis.set_title(f"cp per revolution vs window mean, {speed:g} m/s")
        axis.set_xlabel("revolution in window")
        axis.set_ylabel("deviation [%]")
        axis.grid(alpha=0.3)
    axes[0][0].legend(fontsize=8)
    return save(figure, out_dir, "p21-cp-drift.png")


def plot_epsilon(reference: Path, arms: list[tuple[float, Path]], out_dir: Path) -> list[Path]:
    """P1.4: P, Q, T and the spanwise CN/CT against the ASM epsilon/h."""
    arms = sorted(arms)
    paths = []
    ref_rows = turbine_rows(reference)
    figure, axes = plt.subplots(1, 3, figsize=(13, 4))
    for axis, (quantity, label) in zip(axes, QUANTITIES):
        sims = []
        for ratio, directory in arms:
            rows = turbine_rows(directory)
            row = next(r for (m, q), r in rows.items() if q == quantity)
            sims.append((ratio, float(row["sim"])))
        axis.plot([r for r, _ in sims], [v for _, v in sims], "o-",
                  color=COLORS["asm"], label="ASM")
        alm = next((r for (m, q), r in ref_rows.items() if q == quantity), None)
        if alm is not None:
            axis.axhline(float(alm["sim"]), color=COLORS["alm"], linestyle="-.",
                         label=f"{alm['model']} reference")
            experiment = float(alm["experiment"])
            axis.axhline(experiment, color="black", linestyle="--", label="experiment")
            axis.axhspan(experiment * (1 - TURBINE_BAND), experiment * (1 + TURBINE_BAND),
                         color="gray", alpha=0.15)
        axis.set_xscale("log", base=2)
        axis.set_xlabel("epsilon / h")
        axis.set_ylabel(label)
        axis.grid(alpha=0.3)
    axes[0].legend(fontsize=8)
    figure.suptitle("ASM kernel width sensitivity (grey: +-15 % band)")
    paths.append(save(figure, out_dir, "p14-epsilon-turbine.png"))

    figure, axes = plt.subplots(1, 2, figsize=(11, 4))
    for axis, (key, title) in zip(axes, (("c_ref_n", "CN"), ("c_ref_t", "CT"))):
        for ratio, directory in arms:
            rows = [r for r in read_csv(directory / "spanwise_comparison.csv")]
            axis.plot([float(r["r_over_R"]) for r in rows],
                      [float(r[key]) for r in rows], "o-", label=f"eps/h = {ratio:g}")
        exp_key = "cn_exp" if key == "c_ref_n" else "ct_exp"
        rows = read_csv(arms[0][1] / "spanwise_comparison.csv")
        axis.plot([float(r["r_over_R"]) for r in rows], [float(r[exp_key]) for r in rows],
                  "ks", markersize=8, label="experiment")
        axis.set_title(f"{title} (chord-referenced)")
        axis.set_xlabel("r/R")
        axis.grid(alpha=0.3)
    axes[0].legend(fontsize=8)
    paths.append(save(figure, out_dir, "p14-epsilon-spanwise.png"))
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p21 = sub.add_parser("p21", help="calibration figures, one directory per speed")
    p21.add_argument("--case", action="append", required=True, metavar="SPEED=DIR")
    p21.add_argument("--out-dir", type=Path, required=True)
    eps = sub.add_parser("eps", help="epsilon/h sensitivity figures")
    eps.add_argument("--reference", type=Path, required=True)
    eps.add_argument("--arm", action="append", required=True, metavar="RATIO=DIR")
    eps.add_argument("--out-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "p21":
        cases = sorted(parse_pairs(args.case))
        paths = [plot_turbine_loads(cases, args.out_dir),
                 plot_spanwise(cases, args.out_dir, plane=False),
                 plot_spanwise(cases, args.out_dir, plane=True),
                 plot_spanwise_error(cases, args.out_dir),
                 plot_cp_history(cases, args.out_dir),
                 plot_drift(cases, args.out_dir)]
    else:
        paths = plot_epsilon(args.reference, parse_pairs(args.arm), args.out_dir)
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
