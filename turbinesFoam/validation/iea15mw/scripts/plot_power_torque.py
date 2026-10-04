#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Power and torque versus revolution for the three IEA 15-240-RWT runs.

Reads the module-level ``turbine.csv`` of the ALM, ASM and ASM-mesh comparison
runs and writes two figures under ``analysis/``:

* ``power-torque-vs-rev.png`` -- the raw C_P / torque traces (thin) with the
  per-revolution mean (bold), one colour per case, plus the published
  reference levels as labelled horizontal lines.  The ASM-mesh run is a
  partial, still-transient run and is marked as such.
* ``power-torque-last-revs.png`` -- a zoom on the last five revolutions of each
  run, per-revolution means only, with the same reference lines, so the
  settled level of each case is readable.

Torque is not a column of the module CSV.  It is ``C_P * P_avail / omega`` with
``P_avail = 0.5 * rho * A * V^3`` and ``omega`` the rotor speed; the C_P/torque
files use the module's own normalisation (``axialFlowTurbineALSource.C``).

READ-ONLY: this script only reads ``runs/``.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
ANALYSIS = ROOT / "analysis"

TURBINE_CSV = Path("postProcessing") / "turbines" / "0" / "turbine.csv"

#: Rated point of the case (matches system/fvOptions.ALM and the references
#: note odd/tasks/iea15mw-references.md).
RHO = 1.225
V_RATED = 10.659
RPM_RATED = 7.518
OMEGA = 0.78719  # rad/s, as quoted in the task (7.518 rpm -> 0.78728)
ROTOR_RADIUS = 120.67532
AREA = math.pi * ROTOR_RADIUS**2
P_AVAIL = 0.5 * RHO * AREA * V_RATED**3  # W

#: (model, run directory, colour, partial?).  ASM-mesh is the short, still
#: transient run.
RUNS = (
    ("alm", ROOT / "runs" / "iea15mw-asmcmp-alm", "#1f77b4", False),
    ("asm", ROOT / "runs" / "iea15mw-asmcmp-asm", "#2ca02c", False),
    ("asm-mesh", ROOT / "runs" / "iea15mw-asmcmp-asm-mesh", "#d62728", True),
)

#: Published reference levels (odd/tasks/iea15mw-references.md).  ``None``
#: where the source gives no torque value.
REFERENCES = (
    ("WISDEM / published", 0.4618, 19.91),
    ("OpenFAST BEM", 0.4820, 19.51),
    ("CCBlade (ours)", 0.4910, 21.2),
    ("Miroux ALM (turbinesFoam)", 0.527, None),
    ("OLAF free wake", 0.5312, 22.26),
)

REF_STYLES = ("-", "--", "-.", ":", (0, (1, 1)))

REV = 360.0  # deg per revolution
ZOOM_REVS = 5.0

PNG_FULL = "power-torque-vs-rev.png"
PNG_ZOOM = "power-torque-last-revs.png"

TORQUE_NOTE = (
    "torque = $C_P\\cdot\\frac{1}{2}\\rho A V^3/\\Omega$  "
    "($A=\\pi R^2$, $R$=120.675 m, $\\rho$=1.225 kg/m$^3$, "
    "V=10.659 m/s, $\\Omega$=0.78719 rad/s, $P_{avail}$=33.93 MW).\n"
    "Absolute levels use the polars BEFORE the liftReCorrExp 0 "
    "correction -> inflated; the comparison BETWEEN the three cases is "
    "valid because they share the bias."
)


def read_turbine(run_dir: Path):
    """Return ``rev``, ``cp``, ``torque_mnm`` arrays from one turbine.csv."""
    rev, cp = [], []
    path = run_dir / TURBINE_CSV
    with path.open() as fh:
        for row in csv.DictReader(fh):
            try:
                rev.append(float(row["angle_deg"]) / REV)
                cp.append(float(row["cp"]))
            except (KeyError, ValueError):
                continue
    rev = np.asarray(rev)
    cp = np.asarray(cp)
    torque = cp * P_AVAIL / OMEGA / 1e6
    return rev, cp, torque


def per_revolution_means(rev, values):
    """Integer-revolution means: ``means[k]`` covers ``[k, k+1)``.

    Also returns the highest ``k`` whose revolution is fully inside the run.
    """
    means = {}
    if len(rev) == 0:
        return means, -1
    rev_max = float(rev.max())
    last_index = int(math.floor(rev_max))
    last_full = -1
    for k in range(last_index + 1):
        if k + 1 > rev_max + 1e-6:
            continue
        sel = values[(rev >= k) & (rev < k + 1)]
        if len(sel):
            means[k] = float(sel.mean())
            last_full = k
    return means, last_full


def load_all():
    runs = []
    for model, run_dir, color, partial in RUNS:
        if not (run_dir / TURBINE_CSV).is_file():
            print(f"WARNING: no turbine.csv for {model}, skipping")
            continue
        rev, cp, torque = read_turbine(run_dir)
        means_cp, last_cp = per_revolution_means(rev, cp)
        means_t, _ = per_revolution_means(rev, torque)
        runs.append(
            {
                "model": model,
                "color": color,
                "partial": partial,
                "rev": rev,
                "cp": cp,
                "torque": torque,
                "means_cp": means_cp,
                "means_torque": means_t,
                "last_rev": last_cp,
            }
        )
    return runs


def draw_references(ax, key):
    """Draw the reference levels for ``key`` in ('cp', 'torque')."""
    for (_name, cp_ref, torque_ref), ls in zip(
        REFERENCES, REF_STYLES, strict=True
    ):
        y = cp_ref if key == "cp" else torque_ref
        if y is None:
            continue
        ax.axhline(y, color="0.35", linestyle=ls, linewidth=1.0, alpha=0.9)


def reference_handles():
    handles = []
    for (name, cp_ref, torque_ref), ls in zip(REFERENCES, REF_STYLES, strict=True):
        suffix = (
            f"  (Cp {cp_ref:.4f} / T {torque_ref:.2f} MN$\\cdot$m)"
            if torque_ref is not None
            else f"  (Cp {cp_ref:.3f} / no T)"
        )
        handles.append(
            Line2D(
                [],
                [],
                color="0.35",
                linestyle=ls,
                linewidth=1.1,
                label=name + suffix,
            )
        )
    return handles


def case_handles(runs, linewidth, marker=None):
    handles = []
    for run in runs:
        label = run["model"] + (" (partial)" if run["partial"] else "")
        handles.append(
            Line2D(
                [],
                [],
                color=run["color"],
                linewidth=linewidth,
                marker=marker,
                markersize=5 if marker else None,
                label=label,
            )
        )
    return handles


def build_full_figure(runs, out: Path):
    fig, (ax_cp, ax_tq) = plt.subplots(2, 1, figsize=(13.5, 8.6), sharex=True)

    for run in runs:
        color = run["color"]
        ax_cp.plot(run["rev"], run["cp"], color=color, linewidth=0.5, alpha=0.20)
        ax_tq.plot(
            run["rev"], run["torque"], color=color, linewidth=0.5, alpha=0.20
        )
        ks = sorted(run["means_cp"])
        ax_cp.plot(
            np.asarray(ks) + 0.5,
            [run["means_cp"][k] for k in ks],
            color=color,
            linewidth=2.2,
        )
        kt = sorted(run["means_torque"])
        ax_tq.plot(
            np.asarray(kt) + 0.5,
            [run["means_torque"][k] for k in kt],
            color=color,
            linewidth=2.2,
        )

    # partial-run end marker
    shortest = min(runs, key=lambda r: r["rev"].max())
    end_rev = shortest["rev"].max()
    ax_cp.axvline(
        end_rev, color=shortest["color"], linestyle=":", linewidth=1.3
    )
    ax_tq.axvline(
        end_rev, color=shortest["color"], linestyle=":", linewidth=1.3
    )
    draw_references(ax_cp, "cp")
    draw_references(ax_tq, "torque")
    ax_cp.annotate(
        f"ASM-mesh ends at {end_rev:.1f} rev\n(partial, still transient)",
        xy=(end_rev, 0.96),
        xycoords=("data", "axes fraction"),
        xytext=(-6, 0),
        textcoords="offset points",
        fontsize=8.5,
        color=shortest["color"],
        va="top",
        ha="right",
    )

    ax_cp.set_ylabel("$C_P$  [-]")
    ax_tq.set_ylabel("Torque  [MN$\\cdot$m]")
    ax_tq.set_xlabel("revolution  [-]")
    ax_cp.grid(alpha=0.25)
    ax_tq.grid(alpha=0.25)
    ax_cp.set_xlim(0, max(r["rev"].max() for r in runs))

    handles = case_handles(runs, 2.2) + reference_handles()
    ax_cp.legend(handles=handles, fontsize=8.5, loc="upper right",
                 framealpha=0.9)

    fig.suptitle(
        "IEA 15-240-RWT: power and torque vs revolution", fontsize=14
    )
    fig.text(0.5, 0.005, TORQUE_NOTE, ha="center", va="bottom", fontsize=8.5)
    fig.tight_layout(rect=(0, 0.085, 1, 0.96))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def build_zoom_figure(runs, out: Path):
    fig, (ax_cp, ax_tq) = plt.subplots(2, 1, figsize=(13.5, 8.6), sharex=True)

    for run in runs:
        color = run["color"]
        last = run["last_rev"]
        ks = [k for k in sorted(run["means_cp"]) if k > last - ZOOM_REVS]
        ax_cp.plot(
            np.asarray(ks) + 0.5,
            [run["means_cp"][k] for k in ks],
            color=color,
            linewidth=2.0,
            marker="o",
            markersize=5,
        )
        kt = [k for k in sorted(run["means_torque"]) if k > last - ZOOM_REVS]
        ax_tq.plot(
            np.asarray(kt) + 0.5,
            [run["means_torque"][k] for k in kt],
            color=color,
            linewidth=2.0,
            marker="o",
            markersize=5,
        )
        last_cp = run["means_cp"].get(last)
        last_t = run["means_torque"].get(last)
        if last_cp is not None:
            ax_cp.annotate(
                f"{run['model']}: {last_cp:.4f}",
                xy=(last + 0.5, last_cp),
                xytext=(8, 0),
                textcoords="offset points",
                fontsize=9,
                color=color,
                va="center",
            )
        if last_t is not None:
            ax_tq.annotate(
                f"{run['model']}: {last_t:.2f}",
                xy=(last + 0.5, last_t),
                xytext=(8, 0),
                textcoords="offset points",
                fontsize=9,
                color=color,
                va="center",
            )

    draw_references(ax_cp, "cp")
    draw_references(ax_tq, "torque")
    ax_cp.grid(alpha=0.25)
    ax_tq.grid(alpha=0.25)

    ax_cp.set_ylabel("$C_P$  [-]")
    ax_tq.set_ylabel("Torque  [MN$\\cdot$m]")
    ax_tq.set_xlabel("revolution  [-]")

    handles = [
        Line2D(
            [],
            [],
            color=r["color"],
            linewidth=2.0,
            marker="o",
            markersize=5,
            label=f"{r['model']} (last rev {r['last_rev']}"
            + (", partial)" if r["partial"] else ")"),
        )
        for r in runs
    ]
    handles += reference_handles()
    ax_cp.legend(handles=handles, fontsize=8.5, loc="center left",
                 framealpha=0.9)

    fig.suptitle(
        f"IEA 15-240-RWT: power and torque, last {int(ZOOM_REVS)} revolutions "
        "of each run",
        fontsize=14,
    )
    fig.text(0.5, 0.005, TORQUE_NOTE, ha="center", va="bottom", fontsize=8.5)
    fig.tight_layout(rect=(0, 0.085, 1, 0.96))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def print_table(runs):
    print()
    print("=" * 86)
    print(
        f"LAST-REVOLUTION MEANS  (torque = cp * {P_AVAIL:.6e} W / "
        f"{OMEGA:.5f} rad/s / 1e6)"
    )
    print(f"P_avail = 0.5*rho*A*V^3 = {P_AVAIL / 1e6:.4f} MW;  A = {AREA:.1f} m^2")
    print("=" * 86)
    print(
        f"{'model':<10} {'last rev':<8} {'cp mean':<16} {'torque [MN.m]':<12} "
        f"{'window [rev]':<16} {'partial':<10}"
    )
    for run in runs:
        k = run["last_rev"]
        cp_m = run["means_cp"].get(k)
        t_m = run["means_torque"].get(k)
        print(
            f"{run['model']:<10} {k:<8d} {cp_m:<16.5f} {t_m:<12.3f} "
            f"{f'{k}-{k + 1}':<16} {'yes' if run['partial'] else 'no':<10}"
        )
    print()
    print(
        "Reference levels: "
        + " | ".join(
            f"{name} Cp={cp_ref:.4f}"
            + ("" if torque_ref is None else f" T={torque_ref:.2f} MN.m")
            for name, cp_ref, torque_ref in REFERENCES
        )
    )
    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", type=Path, default=ANALYSIS / PNG_FULL)
    parser.add_argument("--zoom", type=Path, default=ANALYSIS / PNG_ZOOM)
    args = parser.parse_args()

    runs = load_all()
    if not runs:
        raise SystemExit("no run data found")

    build_full_figure(runs, args.full)
    print(f"wrote {args.full}")
    build_zoom_figure(runs, args.zoom)
    print(f"wrote {args.zoom}")
    print_table(runs)


if __name__ == "__main__":
    main()
