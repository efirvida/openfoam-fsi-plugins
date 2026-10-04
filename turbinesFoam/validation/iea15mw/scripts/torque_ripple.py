#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Quantify the torque ripple of the three IEA 15-240-RWT comparison runs.

Motivation: ``power-torque-vs-rev.png`` draws the raw per-step torque as a
thin translucent trace behind the bold per-revolution mean, so the raw trace
collapses into a band and the curve *looks* like a mean with no oscillation.
The blade-passage ripple is there and must be visible and quantified.

This script writes ``analysis/torque-ripple.png`` with three panels:

1. Raw torque versus revolution over the last three complete revolutions,
   one line per case (no averaging, no smoothing).  The ASM-mesh run is a
   partial, still-transient run and its trace is an order of magnitude larger
   than ALM/ASM, so it is drawn against a secondary y axis (right, red) to
   keep the ALM/ASM ripple readable.  A secondary top axis gives the rotor
   azimuth.
2. The torque folded modulo 120 deg over the last five complete revolutions,
   1-degree bins, case mean removed.  This isolates the 3/rev blade-passage
   component (the fold sums the three azimuths 120 deg apart that one
   blade-space apart, so 1/rev and 2/rev cancel).  ASM-mesh again on a
   secondary axis.
3. The three per-blade torque coefficients ``ct_blade1..3`` of the ALM run
   over one revolution, mean removed, to show that each blade dips once per
   revolution and that the three dips sit 120 deg apart.

``ct`` is the rotor torque coefficient (see ``turbineALSource::writePerf``);
``cp = ct * tsr`` and ``torque = cp * P_avail / Omega``, so folding ``cp`` or
``ct`` gives the same shape as folding the torque, only a different scale.
The printed table reports the folded ``cp`` peak-to-peak for that reason.

READ-ONLY: this script only reads ``runs/`` and writes under ``analysis/``.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import matplotlib
import numpy as np
from matplotlib.lines import Line2D
from numpy.typing import ArrayLike

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
ANALYSIS = ROOT / "analysis"

TURBINE_CSV = Path("postProcessing") / "turbines" / "0" / "turbine.csv"

#: Nominal kinematics and rotor geometry of the case (matches the constants
#: already verified in ``plot_power_torque.py`` and
#: ``odd/tasks/iea15mw-references.md``).
RHO = 1.225
V_RATED = 10.659
OMEGA = 0.78719  # rad/s
ROTOR_RADIUS = 120.67532
AREA = math.pi * ROTOR_RADIUS**2
P_AVAIL = 0.5 * RHO * AREA * V_RATED**3  # W, = 33.93 MW
#: torque[MN.m] = cp * TORQUE_PER_CP
TORQUE_PER_CP = P_AVAIL / OMEGA / 1e6

REV = 360.0  # deg per revolution
RAW_REVS = 3  # revolutions in panel 1
FOLD_REVS = 5  # revolutions folded in panel 2
FOLD_DEG = 120.0  # fold period: three blades 120 deg apart
FOLD_BINS = 120  # 1-degree bins
N_HARMONICS = 12  # integer harmonics fitted for the non-3/rev check

#: (label, run directory, colour, partial?).  ASM-mesh is the short, still
#: transient run.
RUNS = (
    ("ALM", ROOT / "runs" / "iea15mw-asmcmp-alm", "#1f77b4", False),
    ("ASM", ROOT / "runs" / "iea15mw-asmcmp-asm", "#2ca02c", False),
    ("ASM-mesh", ROOT / "runs" / "iea15mw-asmcmp-asm-mesh", "#d62728", True),
)

COLUMNS = (
    "time",
    "angle_deg",
    "tsr",
    "cp",
    "cd",
    "ct",
    "cd_blade1",
    "ct_blade1",
    "cd_blade2",
    "ct_blade2",
    "cd_blade3",
    "ct_blade3",
)

PNG_NAME = "torque-ripple.png"
CSV_NAME = "torque-ripple.csv"

TORQUE_NOTE = (
    "torque = $c_p\\cdot\\frac{1}{2}\\rho A V^3/\\Omega$  "
    "($A=\\pi R^2$, $R$=120.675 m, $\\rho$=1.225 kg/m$^3$, "
    "V=10.659 m/s, $\\Omega$=0.78719 rad/s);  "
    "torque[MN$\\cdot$m] = $c_p\\times$"
    f"{TORQUE_PER_CP:.3f}.  "
    "$c_t$ is the torque coefficient ($c_p=c_t\\cdot$TSR), so folding "
    "$c_p$/$c_t$ gives the torque ripple up to a scale."
)


def read_turbine(run_dir: Path):
    """Return a dict of numpy columns from one ``turbine.csv``."""
    data = {key: [] for key in COLUMNS}
    with (run_dir / TURBINE_CSV).open() as fh:
        for row in csv.DictReader(fh):
            try:
                for key in COLUMNS:
                    data[key].append(float(row[key]))
            except (KeyError, ValueError):
                continue
    return {key: np.asarray(value) for key, value in data.items()}


def last_full_revolution(rev):
    """Index of the last complete revolution and the end revolution.

    ``rev_end = k + 1`` is the highest revolution fully contained in the run.
    """
    rev_max = float(rev.max())
    last_full = int(math.floor(rev_max - 1.0))
    return last_full, float(last_full + 1)


def fold_profile(az_deg, values, bins=FOLD_BINS, period=FOLD_DEG):
    """Mean of ``values`` in ``bins`` equal bins of the folded azimuth."""
    folded = np.mod(az_deg, period)
    width = period / bins
    idx = np.floor(folded / width).astype(int) % bins
    sums = np.zeros(bins)
    counts = np.zeros(bins)
    np.add.at(sums, idx, values)
    np.add.at(counts, idx, 1.0)
    means = np.divide(sums, counts, out=np.full(bins, np.nan), where=counts > 0)
    centers = width * (np.arange(bins) + 0.5)
    return centers, means, counts


def harmonic_amplitudes(az_deg, values, n_max=N_HARMONICS):
    """Amplitude of every integer n/rev harmonic by least squares.

    The window is an integer number of revolutions, so the harmonics are
    orthogonal and a linear transient in the mean level does not leak into
    them the way it does into a raw fold of a still-transient run.
    """
    az = np.radians(az_deg)
    amps = {}
    for n in range(1, n_max + 1):
        basis = np.column_stack([np.cos(n * az), np.sin(n * az)])
        coef, _, _, _ = np.linalg.lstsq(basis, values, rcond=None)
        amps[n] = float(np.hypot(coef[0], coef[1]))
    return amps


def p2p(values):
    """Peak-to-peak, NaN-safe."""
    return float(np.nanmax(values) - np.nanmin(values))


def rev_to_azimuth(rev: ArrayLike) -> np.ndarray:
    """Revolution axis -> rotor azimuth in degrees (for the secondary axis)."""
    return np.asarray(rev) * REV


def azimuth_to_rev(azimuth: ArrayLike) -> np.ndarray:
    """Rotor azimuth in degrees -> revolution axis."""
    return np.asarray(azimuth) / REV


def load_run(label, run_dir, color, partial):
    """Read one run and pre-compute every ripple metric."""
    cols = read_turbine(run_dir)
    rev = cols["angle_deg"] / REV
    torque = cols["cp"] * TORQUE_PER_CP
    last_full, rev_end = last_full_revolution(rev)

    # Mean over the last complete revolution: same reference mean as
    # odd/tasks/iea15mw-references.md.
    sel_mean = (rev >= last_full) & (rev < rev_end)
    mean_torque = float(torque[sel_mean].mean())
    mean_cp = float(cols["cp"][sel_mean].mean())
    mean_ct = float(cols["ct"][sel_mean].mean())

    # Panel 1 / raw ripple: last RAW_REVS complete revolutions.
    sel_raw = (rev >= rev_end - RAW_REVS) & (rev < rev_end)
    raw_torque = torque[sel_raw]
    raw_p2p = p2p(raw_torque)

    # Panel 2 / folded ripple: last FOLD_REVS complete revolutions, 120 deg.
    sel_fold = (rev >= rev_end - FOLD_REVS) & (rev < rev_end)
    fold_centers, fold_torque, n_fold = fold_profile(
        cols["angle_deg"][sel_fold], torque[sel_fold]
    )
    fold_torque = fold_torque - np.nanmean(fold_torque)
    _, fold_cp, _ = fold_profile(cols["angle_deg"][sel_fold], cols["cp"][sel_fold])
    fold_cp = fold_cp - np.nanmean(fold_cp)
    _, fold_ct, _ = fold_profile(cols["angle_deg"][sel_fold], cols["ct"][sel_fold])
    fold_ct = fold_ct - np.nanmean(fold_ct)
    fold_p2p = p2p(fold_torque)

    # Drift-robust 3/rev amplitude over the folded window.
    amps = harmonic_amplitudes(cols["angle_deg"][sel_fold], torque[sel_fold])
    amp3 = amps[3]
    non3 = {n: a for n, a in amps.items() if n % 3 != 0}
    max_non3 = max(non3.items(), key=lambda item: item[1])

    # Per-blade azimuthal curves of the ALM run over its last complete
    # revolution (panel 3).
    blades = []
    if label == "ALM":
        sel_rev = (rev >= last_full) & (rev < rev_end)
        az = np.mod(cols["angle_deg"][sel_rev], REV)
        for b in (1, 2, 3):
            ct_b = cols[f"ct_blade{b}"][sel_rev]
            m = float(ct_b.mean())
            imin = int(np.argmin(ct_b))
            blades.append(
                {
                    "blade": b,
                    "azimuth": az,
                    "ct": ct_b,
                    "ct_dev_pct": (ct_b / m - 1.0) * 100.0,
                    "mean": m,
                    "dip_az": float(az[imin]),
                    "dip_pct": float((ct_b[imin] / m - 1.0) * 100.0),
                    "p2p_pct": float(np.ptp(ct_b) / m * 100.0),
                }
            )

    n_per_rev = int(round(len(raw_torque) / RAW_REVS))

    return {
        "label": label,
        "color": color,
        "partial": partial,
        "last_full": last_full,
        "rev_end": rev_end,
        "mean_torque": mean_torque,
        "mean_cp": mean_cp,
        "mean_ct": mean_ct,
        "raw_rev": rev[sel_raw],
        "raw_torque": raw_torque,
        "raw_p2p": raw_p2p,
        "raw_p2p_pct": raw_p2p / mean_torque * 100.0,
        "fold_centers": fold_centers,
        "fold_torque": fold_torque,
        "fold_cp": fold_cp,
        "fold_ct": fold_ct,
        "fold_n": n_fold,
        "fold_p2p": fold_p2p,
        "fold_p2p_pct": fold_p2p / mean_torque * 100.0,
        "fold_cp_p2p": p2p(fold_cp),
        "fold_cp_p2p_pct": p2p(fold_cp) / mean_cp * 100.0,
        "fold_ct_p2p": p2p(fold_ct),
        "fold_ct_p2p_pct": p2p(fold_ct) / mean_ct * 100.0,
        "amp3": amp3,
        "amp3_pct": amp3 / mean_torque * 100.0,
        "max_non3": max_non3,
        "max_non3_pct": max_non3[1] / mean_torque * 100.0,
        "blades": blades,
        "n_per_rev": n_per_rev,
    }


def sorted_runs():
    runs = []
    for label, run_dir, color, partial in RUNS:
        if not (run_dir / TURBINE_CSV).is_file():
            print(f"WARNING: no turbine.csv for {label}, skipping")
            continue
        runs.append(load_run(label, run_dir, color, partial))
    return runs


def write_csv(runs, out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["model", "partial", "kind", "series", "x", "y", "x_unit", "y_unit"]
        )
        for run in runs:
            partial = "yes" if run["partial"] else "no"
            for x, y in zip(run["raw_rev"], run["raw_torque"], strict=True):
                writer.writerow(
                    [
                        run["label"],
                        partial,
                        "raw_last3",
                        "torque",
                        f"{x:.6f}",
                        f"{y:.6f}",
                        "rev",
                        "MN.m",
                    ]
                )
            for x, y in zip(
                run["fold_centers"], run["fold_torque"], strict=True
            ):
                writer.writerow(
                    [
                        run["label"],
                        partial,
                        "fold120_last5",
                        "torque_dev",
                        f"{x:.2f}",
                        f"{y:.6f}",
                        "deg",
                        "MN.m",
                    ]
                )
            for x, y in zip(run["fold_centers"], run["fold_cp"], strict=True):
                writer.writerow(
                    [
                        run["label"],
                        partial,
                        "fold120_last5",
                        "cp_dev",
                        f"{x:.2f}",
                        f"{y:.8f}",
                        "deg",
                        "-",
                    ]
                )
            for x, y in zip(run["fold_centers"], run["fold_ct"], strict=True):
                writer.writerow(
                    [
                        run["label"],
                        partial,
                        "fold120_last5",
                        "ct_dev",
                        f"{x:.2f}",
                        f"{y:.8f}",
                        "deg",
                        "-",
                    ]
                )
            for blade in run["blades"]:
                for x, y in zip(
                    blade["azimuth"], blade["ct"], strict=True
                ):
                    writer.writerow(
                        [
                            run["label"],
                            partial,
                            "blade_last1",
                            f"ct_blade{blade['blade']}",
                            f"{x:.4f}",
                            f"{y:.8f}",
                            "deg",
                            "-",
                        ]
                    )


def build_figure(runs, out: Path):
    fig = plt.figure(figsize=(13.5, 14.0))
    grid = fig.add_gridspec(3, 1, hspace=0.45, left=0.07, right=0.93,
                            top=0.895, bottom=0.075)
    ax_raw = fig.add_subplot(grid[0])
    ax_fold = fig.add_subplot(grid[1])
    ax_blade = fig.add_subplot(grid[2])

    # ---- panel 1: raw torque, last RAW_REVS revolutions -------------------
    ax_raw_r = ax_raw.twinx()
    for run in runs:
        target = ax_raw_r if run["partial"] else ax_raw
        rel = run["raw_rev"] - (run["rev_end"] - RAW_REVS)
        target.plot(
            rel,
            run["raw_torque"],
            color=run["color"],
            linewidth=0.9,
            label=run["label"]
            + (" (partial, right axis)" if run["partial"] else ""),
        )
    ax_raw.set_xlabel("revolution  (relative to the last complete revolution)")
    ax_raw.set_ylabel("torque  [MN$\\cdot$m]")
    ax_raw_r.set_ylabel(
        "ASM-mesh torque  [MN$\\cdot$m]\n(partial, right axis)",
        color=runs[-1]["color"],
    )
    ax_raw_r.tick_params(axis="y", colors=runs[-1]["color"])
    seg = ax_raw.secondary_xaxis(
        "top", functions=(rev_to_azimuth, azimuth_to_rev)
    )
    seg.set_xlabel("azimuth  [deg]")
    ax_raw.set_xlim(0, RAW_REVS)
    ax_raw.grid(alpha=0.25)
    ax_raw.set_title(
        f"Raw torque, last {RAW_REVS} complete revolutions "
        "(no averaging, no smoothing)",
        fontsize=12,
    )
    handles = [
        Line2D(
            [],
            [],
            color=run["color"],
            linewidth=1.4,
            label=run["label"] + (" (partial)" if run["partial"] else ""),
        )
        for run in runs
    ]
    ax_raw.legend(handles=handles, loc="upper right", fontsize=9)

    # ---- panel 2: azimuthal fold modulo 120 deg ---------------------------
    ax_fold_r = ax_fold.twinx()
    for run in runs:
        target = ax_fold_r if run["partial"] else ax_fold
        target.plot(
            run["fold_centers"],
            run["fold_torque"],
            color=run["color"],
            linewidth=1.6,
        )
    ax_fold.axhline(0.0, color="0.6", linewidth=0.8)
    for deg in (0.0, 60.0, 120.0):
        ax_fold.axvline(deg, color="0.85", linewidth=0.8, zorder=0)
    ax_fold.set_xlim(0, FOLD_DEG)
    ax_fold.set_xlabel("folded azimuth  [deg]  (mod 120$^\\circ$)")
    ax_fold.set_ylabel("torque $-$ mean  [MN$\\cdot$m]")
    ax_fold_r.set_ylabel(
        "ASM-mesh torque $-$ mean  [MN$\\cdot$m]\n(partial, right axis)",
        color=runs[-1]["color"],
    )
    ax_fold_r.tick_params(axis="y", colors=runs[-1]["color"])
    ax_fold.grid(alpha=0.25)
    ax_fold.set_title(
        f"Azimuthal fold mod 120$^\\circ$, last {FOLD_REVS} revolutions, "
        "1$^\\circ$ bins, mean removed (isolates the 3/rev blade passage)",
        fontsize=12,
    )
    ax_fold.legend(handles=handles, loc="upper right", fontsize=9)

    # ---- panel 3: per-blade torque coefficient, ALM, one revolution -------
    alm = next((r for r in runs if r["label"] == "ALM"), None)
    if alm is not None and alm["blades"]:
        blade_colors = ("#1f77b4", "#e37700", "#2ca02c")
        for blade in alm["blades"]:
            ax_blade.plot(
                blade["azimuth"],
                blade["ct_dev_pct"],
                color=blade_colors[blade["blade"] - 1],
                linewidth=1.1,
                label=(
                    f"blade {blade['blade']}  (dip "
                    f"{blade['dip_pct']:.2f}% @ {blade['dip_az']:.0f}$^\\circ$)"
                ),
            )
            ax_blade.axvline(
                blade["dip_az"],
                color="0.8",
                linewidth=0.8,
                linestyle=":",
                zorder=0,
            )
        tottorque = alm["mean_ct"]
        ax_blade.axhline(0.0, color="0.6", linewidth=0.8)
        ax_blade.set_xlim(0, 360)
        ax_blade.set_xticks(np.arange(0, 361, 60))
        ax_blade.set_xlabel("rotor azimuth  [deg]")
        ax_blade.set_ylabel("$c_{t,blade}$ relative to mean  [%]")
        ax_blade.grid(alpha=0.25)
        ax_blade.legend(fontsize=9, loc="lower right")
        ax_blade.set_title(
            "ALM per-blade torque coefficient, last complete revolution "
            "(each blade dips once, dips 120$^\\circ$ apart);  "
            f"rotor mean $c_t$ = {tottorque:.4f}",
            fontsize=12,
        )

    fig.suptitle(
        "IEA 15-240-RWT: torque ripple (ALM / ASM settled, ASM-mesh partial)",
        fontsize=15,
        y=0.972,
    )
    fig.text(0.5, 0.012, TORQUE_NOTE, ha="center", va="bottom", fontsize=8.5)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def print_metrics(runs):
    print()
    print("=" * 108)
    print(
        "TORQUE RIPPLE  (mean = last complete revolution;  "
        f"torque = cp * {TORQUE_PER_CP:.3f} MN.m)"
    )
    print("=" * 108)
    header = (
        f"{'model':<10} {'part':<6} {'mean T':<9} {'raw p2p':<9} {'raw %':<8} "
        f"{'fold p2p':<9} {'fold %':<8} {'3/rev amp':<10} {'3/rev %':<8} "
        f"{'samp/rev':<9}"
    )
    print(header)
    print("-" * len(header))
    for run in runs:
        print(
            f"{run['label']:<10} "
            f"{'yes' if run['partial'] else 'no':<6} "
            f"{run['mean_torque']:<9.3f} "
            f"{run['raw_p2p']:<9.3f} "
            f"{run['raw_p2p_pct']:<8.2f} "
            f"{run['fold_p2p']:<9.3f} "
            f"{run['fold_p2p_pct']:<8.2f} "
            f"{run['amp3']:<10.3f} "
            f"{run['amp3_pct']:<8.2f} "
            f"{run['n_per_rev']:<9d}"
        )
    print()
    print(
        "raw p2p and fold p2p are peak-to-peak in MN.m; the % columns are "
        "relative to the mean T of that row."
    )
    print(
        "fold p2p = peak-to-peak of the 120-deg fold over the last "
        f"{FOLD_REVS} revolutions, 1-deg bins, mean removed."
    )
    print(
        "3/rev amp = amplitude of the 3rd integer harmonic of the raw torque "
        f"over the same {FOLD_REVS} revolutions (drift-robust)."
    )
    print()
    print("=" * 108)
    print("NON-3/rev CONTENT AT THE 1 % LEVEL (raw torque, last 5 revolutions)")
    print("=" * 108)
    for run in runs:
        n, a = run["max_non3"]
        verdict = (
            "VISIBLE (a real non-3/rev component exists)"
            if run["max_non3_pct"] >= 1.0
            else "not visible at the 1 % level"
        )
        print(
            f"{run['label']:<10} strongest non-3/rev harmonic is {n}/rev at "
            f"{run['max_non3_pct']:.3f} % of the mean -> {verdict}"
        )
    print(
        "  (1/rev would mean blade-to-blade asymmetry; 2/rev would mean a "
        "two-per-revolution asymmetry.)"
    )
    print()
    print("=" * 108)
    print("cp / ct FOLD (check that the torque trace is not an artefact)")
    print("=" * 108)
    print(
        f"{'model':<10} {'fold cp p2p':<13} {'cp %':<8} "
        f"{'fold ct p2p':<13} {'ct %':<8}"
    )
    for run in runs:
        print(
            f"{run['label']:<10} "
            f"{run['fold_cp_p2p']:<13.6f} {run['fold_cp_p2p_pct']:<8.2f} "
            f"{run['fold_ct_p2p']:<13.6f} {run['fold_ct_p2p_pct']:<8.2f}"
        )
    print(
        "  cp and ct fold to the SAME shape as the torque (torque = cp * "
        f"{TORQUE_PER_CP:.3f}, cp = ct * TSR); the % columns match because the "
        "scale factor cancels."
    )
    print()
    for run in runs:
        if not run["blades"]:
            continue
        print("=" * 108)
        print(
            f"PER-BLADE TORQUE COEFFICIENT, {run['label']}, last complete "
            f"revolution {run['last_full']}-{run['last_full'] + 1}"
        )
        print("=" * 108)
        for blade in run["blades"]:
            print(
                f"  blade {blade['blade']}: mean {blade['mean']:.5f}, "
                f"dip {blade['dip_pct']:.2f} % of mean at azimuth "
                f"{blade['dip_az']:.1f} deg, p2p {blade['p2p_pct']:.2f} %"
            )
        dips = sorted(b["dip_az"] for b in run["blades"])
        gaps = [
            (dips[1] - dips[0]) % 360.0,
            (dips[2] - dips[1]) % 360.0,
            (dips[0] - dips[2]) % 360.0,
        ]
        print(
            "  dip azimuths: "
            + ", ".join(f"{d:.1f}" for d in dips)
            + " deg;  spacings: "
            + ", ".join(f"{g:.1f}" for g in gaps)
            + " deg (120 deg expected for 3 blades)"
        )
        print()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--png", type=Path, default=ANALYSIS / PNG_NAME)
    parser.add_argument("--csv", type=Path, default=ANALYSIS / CSV_NAME)
    args = parser.parse_args()

    runs = sorted_runs()
    if not runs:
        raise SystemExit("no run data found")

    build_figure(runs, args.png)
    print(f"wrote {args.png}")
    write_csv(runs, args.csv)
    print(f"wrote {args.csv}")
    print_metrics(runs)


if __name__ == "__main__":
    main()
