#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tower 3/rev signature on the IEA 15-240-RWT blade loads.

Question: does the tower perturb the blade loads, and by how much?

Method (as specified for the analysis):
  For every blade-1 actuator element, take the last ``--revs`` rotor
  revolutions of its per-element time series, turn the time into the blade
  azimuth (``45.109 deg/s``), then fold the azimuth modulo 120 deg.  The fold
  sums the three azimuths ``psi, psi+120, psi+240`` that sit one blade-space
  apart, so any 1/rev and 2/rev variation cancels and only the harmonics that
  are multiples of 3/rev survive -- the band in which a three-bladed rotor
  feels the tower.  The tower sits at the bottom of the disc, i.e. the blade
  azimuth at which the element's ``z`` is most negative (verified from the
  geometry column, ``z`` smallest -> bottom -> psi = 180 deg -> folded at
  60 deg).

Outputs:
  * ``analysis/tower-azimuthal-signature.csv`` -- the folded (120 deg) and the
    raw (360 deg) azimuthal curves for every outboard element of the three
    comparison runs, long format.
  * ``analysis/tower-azimuthal-signature.png`` -- the raw 1/rev tower dip, the
    folded 3/rev dip and the folded angle of attack, one column per model.
  * the per-element dip table on stdout: the minimum of the folded curve
    against the mean of its two neighbouring 10-degree windows.

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
from matplotlib.colors import Normalize  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
ANALYSIS = ROOT / "analysis"

ELEMENT_DIR = Path("postProcessing") / "actuatorLineElements" / "0"
TURBINE_CSV = Path("postProcessing") / "turbines" / "0" / "turbine.csv"

#: Nominal rotor kinematics of the case (matches system/fvOptions.ALM and the
#: values already verified in odd/tasks/iea15mw-references.md).
OMEGA_DEG_S = 45.109
ROTOR_RADIUS = 120.67532
HUB_RADIUS = 3.97
BLADE_SPAN = 117.0

#: Runs compared.  ``asm-mesh`` is a partial, still-transient run and is
#: flagged wherever it appears.
RUNS = (
    ("alm", ROOT / "runs" / "iea15mw-asmcmp-alm"),
    ("asm", ROOT / "runs" / "iea15mw-asmcmp-asm"),
    ("asm-mesh", ROOT / "runs" / "iea15mw-asmcmp-asm-mesh"),
)

#: Only the outboard elements whose low pass reaches the tower are reported.
RR_MIN = 0.75
RR_MAX = 1.0

#: Fold period and resolution.  60 bins == 2 deg per bin.
FOLD_DEG = 120.0
FOLD_BINS = 60
#: Raw (unfolded) azimuthal profile resolution.
RAW_BINS = 72

#: Half-width (deg) of the two windows flanking the minimum: a 10 deg window on
#: each side of the dip.
WINDOW_HALF_DEG = 10.0

#: The bottom of the disc is at azimuth 180 deg; folded modulo 120 that is 60.
BOTTOM_AZIMUTH_DEG = 180.0
BOTTOM_FOLDED_DEG = BOTTOM_AZIMUTH_DEG % FOLD_DEG

#: Azimuth window (folded) in which the tower passage is expected.
TOWER_WINDOW = (40.0, 70.0)

#: Elements drawn individually in the figure (spanwise spread of the outboard
#: set).  The bold curve is the outboard-element mean.
SHOW_ELEMENTS = (109, 115, 122, 130, 138, 146)

CSV_NAME = "tower-azimuthal-signature.csv"
PNG_NAME = "tower-azimuthal-signature.png"


def last_time(turbine_csv: Path) -> float | None:
    """Last time recorded in the module-level ``turbine.csv``."""
    last = None
    with turbine_csv.open() as fh:
        for row in csv.DictReader(fh):
            try:
                last = float(row["time"])
            except (ValueError, KeyError):
                continue
    return last


def root_dist(element_csv: Path) -> float | None:
    """``root_dist`` (span fraction) of the first usable data row."""
    with element_csv.open() as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                return float(row["root_dist"])
            except (ValueError, KeyError):
                continue
    return None


def element_r(element_csv: Path) -> float | None:
    rd = root_dist(element_csv)
    return None if rd is None else HUB_RADIUS + rd * BLADE_SPAN


def load_window(element_csv: Path, t_start: float):
    """Rows of an element CSV with ``time >= t_start``.

    Returns ``(azimuth_deg, c_ref_n, alpha_deg, z)`` as numpy arrays.  Azimuth
    is ``(45.109 * t) mod 360``; it is not a column of the element CSV.
    """
    az, cn, al, z = [], [], [], []
    with element_csv.open() as fh:
        for row in csv.DictReader(fh):
            try:
                time = float(row["time"])
            except (KeyError, ValueError):
                continue
            if time < t_start:
                continue
            try:
                az.append((OMEGA_DEG_S * time) % 360.0)
                cn.append(float(row["c_ref_n"]))
                al.append(float(row["alpha_deg"]))
                z.append(float(row["z"]))
            except (KeyError, ValueError):
                continue
    return (
        np.asarray(az),
        np.asarray(cn),
        np.asarray(al),
        np.asarray(z),
    )


def fold_profile(az, values, bins=FOLD_BINS, period=FOLD_DEG):
    """Mean of ``values`` in ``bins`` equal bins of the folded azimuth."""
    folded = np.mod(az, period)
    width = period / bins
    idx = np.floor(folded / width).astype(int) % bins
    sums = np.zeros(bins)
    counts = np.zeros(bins)
    np.add.at(sums, idx, values)
    np.add.at(counts, idx, 1.0)
    means = np.divide(sums, counts, out=np.full(bins, np.nan), where=counts > 0)
    centers = width * (np.arange(bins) + 0.5)
    return centers, means, counts


def raw_profile(az, values, bins=RAW_BINS):
    width = 360.0 / bins
    idx = np.floor(az / width).astype(int) % bins
    sums = np.zeros(bins)
    counts = np.zeros(bins)
    np.add.at(sums, idx, values)
    np.add.at(counts, idx, 1.0)
    means = np.divide(sums, counts, out=np.full(bins, np.nan), where=counts > 0)
    centers = width * (np.arange(bins) + 0.5)
    return centers, means


def circular_distance(a, b, period):
    d = abs(a - b) % period
    return min(d, period - d)


def dip_metrics(centers, curve, period=FOLD_DEG, half=WINDOW_HALF_DEG):
    """Depth of the lowest point against its flanking ``half``-degree windows.

    ``depth_pct = (neighbour_mean - min) / neighbour_mean * 100`` where the
    neighbour mean is the mean of the two windows ``(phi-10, phi)`` and
    ``(phi, phi+10)`` around the minimum ``phi``.
    """
    good = np.isfinite(curve)
    if not good.any():
        return None
    imin = int(np.nanargmin(curve))
    phi = centers[imin]
    flank = [
        curve[i]
        for i in range(len(centers))
        if i != imin
        and good[i]
        and 0.0 < circular_distance(centers[i], phi, period) <= half + 1e-9
    ]
    if not flank:
        return None
    neighbour_mean = float(np.mean(flank))
    dip_min = float(curve[imin])
    depth_pct = (neighbour_mean - dip_min) / neighbour_mean * 100.0
    return {
        "azimuth_deg": float(phi),
        "min_c_ref_n": dip_min,
        "neighbour_mean": neighbour_mean,
        "depth_pct": depth_pct,
        "n_flank_bins": len(flank),
    }


def window_min(centers, curve, lo, hi):
    """Lowest point inside an azimuth window, with its own local dip depth."""
    mask = (centers >= lo) & (centers <= hi) & np.isfinite(curve)
    if not mask.any():
        return None
    imin = int(np.nanargmin(np.where(mask, curve, np.inf)))
    phi = centers[imin]
    flank = [
        curve[i]
        for i in range(len(centers))
        if np.isfinite(curve[i])
        and i != imin
        and 0.0 < circular_distance(centers[i], phi, FOLD_DEG) <= WINDOW_HALF_DEG + 1e-9
    ]
    if not flank:
        return None
    neighbour_mean = float(np.mean(flank))
    dip_min = float(curve[imin])
    return {
        "azimuth_deg": float(phi),
        "min_c_ref_n": dip_min,
        "depth_pct": (neighbour_mean - dip_min) / neighbour_mean * 100.0,
    }


def collect(run_dir: Path, revs: float):
    """Return the per-element curves for the outboard set of one run."""
    t_end = last_time(run_dir / TURBINE_CSV)
    if t_end is None:
        return None
    t_start = t_end - revs * 360.0 / OMEGA_DEG_S
    elements = []
    for element_csv in sorted(
        (run_dir / ELEMENT_DIR).glob("turbine.blade1.element*.csv"),
        key=lambda p: int(p.stem.split("element")[-1]),
    ):
        r = element_r(element_csv)
        if r is None:
            continue
        rr = r / ROTOR_RADIUS
        if not (RR_MIN - 1e-9 <= rr <= RR_MAX + 1e-9):
            continue
        az, cn, al, z = load_window(element_csv, t_start)
        if len(az) < 10:
            continue
        f_centers, f_cn, _ = fold_profile(az, cn)
        _, f_al, _ = fold_profile(az, al)
        r_centers, r_cn = raw_profile(az, cn)
        # bottom of the disc: the azimuth at which z is most negative
        bottom_az = float(az[int(np.argmin(z))])
        elements.append(
            {
                "element": int(element_csv.stem.split("element")[-1]),
                "root_dist": root_dist(element_csv),
                "r": r,
                "r_over_R": rr,
                "fold_centers": f_centers,
                "fold_cn": f_cn,
                "fold_alpha": f_al,
                "raw_centers": r_centers,
                "raw_cn": r_cn,
                "bottom_az": bottom_az,
                "t_start": t_start,
                "t_end": t_end,
                "n_samples": int(len(az)),
            }
        )
    return {"t_start": t_start, "t_end": t_end, "revs": revs, "elements": elements}


def write_csv(data, out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "model",
                "element",
                "root_dist",
                "r_m",
                "r_over_R",
                "kind",
                "azimuth_deg",
                "c_ref_n_mean",
                "alpha_deg_mean",
            ]
        )
        for model, run in data.items():
            for el in run["elements"]:
                for center, cn, al in zip(
                    el["fold_centers"],
                    el["fold_cn"],
                    el["fold_alpha"],
                    strict=True,
                ):
                    writer.writerow(
                        [
                            model,
                            el["element"],
                            f"{el['root_dist']:.6f}",
                            f"{el['r']:.4f}",
                            f"{el['r_over_R']:.5f}",
                            "folded120",
                            f"{center:.2f}",
                            f"{cn:.8f}",
                            f"{al:.8f}",
                        ]
                    )
                for center, cn in zip(el["raw_centers"], el["raw_cn"], strict=True):
                    writer.writerow(
                        [
                            model,
                            el["element"],
                            f"{el['root_dist']:.6f}",
                            f"{el['r']:.4f}",
                            f"{el['r_over_R']:.5f}",
                            "raw360",
                            f"{center:.2f}",
                            f"{cn:.8f}",
                            "",
                        ]
                    )


def build_figure(data, out: Path):
    models = list(data.keys())
    fig, axes = plt.subplots(
        3,
        len(models),
        figsize=(16.5, 13.0),
        sharex="col",
    )
    cmap = plt.get_cmap("viridis")
    norm = Normalize(RR_MIN, RR_MAX)

    for col, model in enumerate(models):
        run = data[model]
        ax_raw = axes[0][col]
        ax_fold = axes[1][col]
        ax_alpha = axes[2][col]

        partial = model == "asm-mesh"
        title = model + (" (partial, transient)" if partial else "")
        ax_raw.set_title(title, fontsize=12, fontweight="bold")

        # -- raw (unfolded) azimuthal profile, tip elements ------------------
        for el in run["elements"]:
            if el["element"] in SHOW_ELEMENTS:
                ax_raw.plot(
                    el["raw_centers"],
                    el["raw_cn"],
                    color=cmap(norm(el["r_over_R"])),
                    linewidth=1.2,
                    alpha=0.9,
                )
        tip = max(run["elements"], key=lambda e: e["r_over_R"])
        ax_raw.plot(
            tip["raw_centers"],
            tip["raw_cn"],
            color="black",
            linewidth=2.0,
            label=f"tip e{tip['element']} (r/R={tip['r_over_R']:.3f})",
        )
        ax_raw.axvline(
            BOTTOM_AZIMUTH_DEG,
            color="crimson",
            linestyle="--",
            linewidth=1.2,
        )
        ax_raw.annotate(
            "bottom 180$^\\circ$",
            xy=(BOTTOM_AZIMUTH_DEG, 0.02),
            xycoords=("data", "axes fraction"),
            xytext=(4, 4),
            textcoords="offset points",
            color="crimson",
            fontsize=8,
        )
        raw_dip = dip_metrics(tip["raw_centers"], tip["raw_cn"], period=360.0)
        if raw_dip is not None:
            ax_raw.plot(
                raw_dip["azimuth_deg"],
                raw_dip["min_c_ref_n"],
                marker="v",
                color="crimson",
                markersize=6,
            )
            ax_raw.annotate(
                f"tip dip {raw_dip['depth_pct']:.2f}% @ "
                f"{raw_dip['azimuth_deg']:.0f}$^\\circ$",
                xy=(raw_dip["azimuth_deg"], raw_dip["min_c_ref_n"]),
                xytext=(6, -22),
                textcoords="offset points",
                fontsize=8,
                color="crimson",
            )
        ax_raw.set_ylabel("$c_{ref,n}$  (raw, mod 360$^\\circ$)")
        ax_raw.set_xlim(0, 360)
        ax_raw.grid(alpha=0.25)
        if col == 0:
            ax_raw.legend(fontsize=8, loc="lower right")

        # -- folded 3/rev profile --------------------------------------------
        for el in run["elements"]:
            ax_fold.plot(
                el["fold_centers"],
                el["fold_cn"],
                color=cmap(norm(el["r_over_R"])),
                linewidth=0.7,
                alpha=0.35,
            )
        stack = np.vstack([el["fold_cn"] for el in run["elements"]])
        mean_cn = np.nanmean(stack, axis=0)
        centers = run["elements"][0]["fold_centers"]
        ax_fold.plot(
            centers,
            mean_cn,
            color="black",
            linewidth=2.2,
            label="outboard mean",
        )
        ax_fold.axvline(
            BOTTOM_FOLDED_DEG,
            color="crimson",
            linestyle="--",
            linewidth=1.2,
            label=f"bottom folded {BOTTOM_FOLDED_DEG:.0f}$^\\circ$",
        )
        mean_dip = dip_metrics(centers, mean_cn)
        if mean_dip is not None:
            ax_fold.plot(
                mean_dip["azimuth_deg"],
                mean_dip["min_c_ref_n"],
                marker="v",
                color="crimson",
                markersize=6,
            )
            ax_fold.annotate(
                f"mean dip {mean_dip['depth_pct']:.2f}% @ "
                f"{mean_dip['azimuth_deg']:.0f}$^\\circ$",
                xy=(mean_dip["azimuth_deg"], mean_dip["min_c_ref_n"]),
                xytext=(6, -26),
                textcoords="offset points",
                fontsize=8,
                color="crimson",
            )
        ax_fold.set_ylabel("$c_{ref,n}$  (folded mod 120$^\\circ$)")
        ax_fold.grid(alpha=0.25)
        if col == 0:
            ax_fold.legend(fontsize=8, loc="lower right")

        # -- folded angle of attack ------------------------------------------
        stack_a = np.vstack([el["fold_alpha"] for el in run["elements"]])
        mean_a = np.nanmean(stack_a, axis=0)
        for el in run["elements"]:
            ax_alpha.plot(
                el["fold_centers"],
                el["fold_alpha"],
                color=cmap(norm(el["r_over_R"])),
                linewidth=0.7,
                alpha=0.35,
            )
        ax_alpha.plot(centers, mean_a, color="black", linewidth=2.2)
        ax_alpha.axvline(
            BOTTOM_FOLDED_DEG, color="crimson", linestyle="--", linewidth=1.2
        )
        alpha_dip = dip_metrics(centers, mean_a)
        if alpha_dip is not None:
            ax_alpha.plot(
                alpha_dip["azimuth_deg"],
                alpha_dip["min_c_ref_n"],
                marker="v",
                color="crimson",
                markersize=6,
            )
            ax_alpha.annotate(
                f"mean dip {alpha_dip['min_c_ref_n'] - alpha_dip['neighbour_mean']:.3f}"
                f"$^\\circ$ @ {alpha_dip['azimuth_deg']:.0f}$^\\circ$",
                xy=(alpha_dip["azimuth_deg"], alpha_dip["min_c_ref_n"]),
                xytext=(6, -26),
                textcoords="offset points",
                fontsize=8,
                color="crimson",
            )
        ax_alpha.set_ylabel("$\\alpha$  [deg]  (folded)")
        ax_alpha.set_xlabel("folded azimuth  [deg]  (mod 120$^\\circ$)")
        ax_alpha.set_xlim(0, 120)
        ax_alpha.grid(alpha=0.25)

        # span colourbar per column (on the middle row)
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        cbar = fig.colorbar(sm, ax=ax_fold, fraction=0.05, pad=0.03)
        cbar.set_label("r/R")

    # window annotation
    win = next(iter(data.values()))
    fig.suptitle(
        "IEA 15-240-RWT tower signature on the blade loads\n"
        f"last {win['revs']:.0f} rev ({win['t_start']:.1f}-{win['t_end']:.1f} s); "
        "azimuth folded mod 120$^\\circ$; "
        "bottom = 180$^\\circ$ = folded 60$^\\circ$",
        fontsize=13,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def print_tables(data):
    for model, run in data.items():
        partial = " (partial/transient)" if model == "asm-mesh" else ""
        print()
        print("=" * 100)
        print(
            f"MODEL {model}{partial}   window {run['t_start']:.2f}-"
            f"{run['t_end']:.2f} s ({run['revs']:.1f} rev), "
            f"{len(run['elements'])} outboard elements"
        )
        print("=" * 100)
        header = (
            f"{'elem':<6} {'r/R':<9} {'dip@deg':<8} {'min cn':<10} "
            f"{'neighbour':<12} {'depth %':<9} {'twr@deg':<9} {'twr depth %':<12}"
        )
        print(header)
        depths = []
        for el in run["elements"]:
            dip = dip_metrics(el["fold_centers"], el["fold_cn"])
            twr = window_min(el["fold_centers"], el["fold_cn"], *TOWER_WINDOW)
            if dip is None:
                continue
            depths.append(dip["depth_pct"])
            twr_az = f"{twr['azimuth_deg']:.1f}" if twr else "-"
            twr_dp = f"{twr['depth_pct']:.2f}" if twr else "-"
            print(
                f"{el['element']:<6d} {el['r_over_R']:<9.4f} "
                f"{dip['azimuth_deg']:<8.1f} {dip['min_c_ref_n']:<10.4f} "
                f"{dip['neighbour_mean']:<12.4f} {dip['depth_pct']:<9.2f} "
                f"{twr_az:<9} {twr_dp:<12}"
            )
        if depths:
            print(
                f"  global folded dip: mean {np.mean(depths):.2f}%  "
                f"min {np.min(depths):.2f}%  max {np.max(depths):.2f}% "
                f"(n={len(depths)} elements)"
            )
        # bottom-azimuth verification for a tip element: at the bottom the
        # element's z is most negative
        tip = max(run["elements"], key=lambda e: e["r_over_R"])
        raw_dip = dip_metrics(tip["raw_centers"], tip["raw_cn"], period=360.0)
        raw_az = f"{raw_dip['azimuth_deg']:.0f} deg" if raw_dip else "n/a"
        raw_dp = f"{raw_dip['depth_pct']:.2f}%" if raw_dip else "n/a"
        print(
            f"  bottom check (min z): tip element {tip['element']} "
            f"(r/R={tip['r_over_R']:.4f}) reaches z_min at azimuth "
            f"{tip['bottom_az']:.1f} deg (geometry bottom = 180 deg)"
        )
        print(
            f"  raw 1/rev tower dip of that tip: {raw_dp} at {raw_az}"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revs", type=float, default=5.0,
                        help="number of rotor revolutions to fold (default 5)")
    parser.add_argument("--csv", type=Path, default=ANALYSIS / CSV_NAME)
    parser.add_argument("--png", type=Path, default=ANALYSIS / PNG_NAME)
    args = parser.parse_args()

    data = {}
    for model, run_dir in RUNS:
        if not (run_dir / TURBINE_CSV).is_file():
            print(f"WARNING: no turbine.csv for {model}, skipping")
            continue
        res = collect(run_dir, args.revs)
        if res is None or not res["elements"]:
            print(f"WARNING: no element data for {model}, skipping")
            continue
        data[model] = res

    if not data:
        raise SystemExit("no run data found")

    write_csv(data, args.csv)
    print(f"wrote {args.csv}")
    build_figure(data, args.png)
    print(f"wrote {args.png}")
    print_tables(data)


if __name__ == "__main__":
    main()
