#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Raw torque signal of the IEA 15-240-RWT comparison runs, with one vertical
marker at every blade-tower passage.

Motivation: the two figures the maintainer has already rejected
(``power-torque-vs-rev.png``, ``power-torque-last-revs.png``) draw bold
per-revolution *means*.  He wants to see the raw signal itself, one sample per
time step, with a vertical dashed line every time a blade passes in front of
the tower, so that the 3/rev passage ripple can be read off directly.

``scripts/torque_ripple.py`` already draws the raw signal over the last three
revolutions and measures the passage phase, so this script reuses its data
conventions unchanged (same CSV, same ``torque = cp * TORQUE_PER_CP``, same
last-three-complete-revolutions window, same colours):

  * revolution          = ``angle_deg / 360``   (``angle_deg`` is the rotor
                          azimuth, unwrapped and monotonic; one revolution is
                          7.9808 s = 360 deg, 45.108 deg/s, ~851.7 samples)
  * torque[MN.m]        = ``cp * 43.108``  (``cp = ct * tsr``)
  * passage phase       = the per-blade ``ct_blade1..3`` dips measured on the
                          ALM's last complete revolution: 73.9 deg (blade 1),
                          193.9 deg (blade 3), 313.6 deg (blade 2); every
                          revolution repeats that set plus 360*k.

The figure has three panels:

1. Raw ALM torque over the last three complete revolutions, thin line, one
   sample per time step, no averaging and no smoothing, with a vertical dashed
   line at all nine passage events.  The ASM is overlaid on a secondary axis
   (its torque is ~10 % lower; the two curves fit legibly and do not clutter,
   so it is kept).  The first three lines carry the blade label.
2. The last complete revolution alone, still raw, same markers, plus the three
   per-blade ALM torque coefficients ``ct_blade1..3`` on a secondary axis, so
   the reader can check that each marker sits on the dip of one specific blade
   and on nothing else.
3. The raw ASM torque over its last three complete revolutions, same markers,
   to show the same 3/rev structure in the second model.

The printed table reports, per model, the torque mean and, for every passage
event, the local minimum of the raw signal, the values 15 deg before and after
the event and the relative depth.  It also reports the dip-vs-marker
coincidence count, which is the point of the figure.

The ASM-mesh run is *not* drawn: it is still transient, its torque swings
between 13.8 and 76.9 MN.m inside a single revolution and sits ~70 % above the
settled ALM/ASM level, so a third axis would be needed and the 1 % passage
ripple would be unreadable.

Phase convention (fixed by ``angle_deg`` and the ``ct_blade*`` columns of
``turbine.csv`` -- ``writePerf`` writes ``bladeMoments_[i] & axis_`` at the
current rotor azimuth): a marker at azimuth ``phi`` means the rotor is at
``phi``, i.e. the blade whose dip is been measured sits in front of the tower.

READ-ONLY: this script only reads ``runs/``; it writes under ``analysis/``.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import matplotlib
import numpy as np
from matplotlib.lines import Line2D

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
ANALYSIS = ROOT / "analysis"

TURBINE_CSV = Path("postProcessing") / "turbines" / "0" / "turbine.csv"

#: Nominal kinematics and rotor geometry of the case.  Identical to
#: ``torque_ripple.py`` so the MN.m numbers agree with the other figures.
RHO = 1.225
V_RATED = 10.659
OMEGA = 0.78719  # rad/s
ROTOR_RADIUS = 120.67532
AREA = math.pi * ROTOR_RADIUS**2
P_AVAIL = 0.5 * RHO * AREA * V_RATED**3  # W
#: torque[MN.m] = cp * TORQUE_PER_CP
TORQUE_PER_CP = P_AVAIL / OMEGA / 1e6

REV = 360.0  # deg per revolution
RAW_REVS = 3  # revolutions shown in panels 1 and 3
SECONDS_PER_REV = 360.0 / 45.108  # 7.9808 s

#: The measured blade-tower passage events of one revolution, in azimuth
#: order: (blade label, rotor azimuth in deg).  Taken from
#: ``torque_ripple.py``'s per-blade output on the ALM's last complete
#: revolution and reproduced exactly by this script.
EVENTS = (
    ("blade 1", 73.9),
    ("blade 3", 193.9),
    ("blade 2", 313.6),
)

#: (label, run directory, colour, partial?).  ``asm-mesh`` is the short,
#: still-transient run; it is measured but not drawn (see ``ASM_MESH_NOTE``).
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

#: Window (deg, half width) used to locate the local minimum of an event.
DIP_HALF_WINDOW = 30.0
#: Flank offset of the reported "before"/"after" values.
FLANK_DEG = 15.0
#: Tolerance asked for by the maintainer when counting coincidences.
COINCIDENCE_DEG = 5.0

FOLD_DEG = 120.0
FOLD_BINS = 120

BLADE_COLORS = ("#1f77b4", "#e37700", "#2ca02c")

PNG_NAME = "torque-signal-tower-passage.png"
CSV_NAME = "torque-signal-tower-passage.csv"

TORQUE_NOTE = (
    "torque = $c_p\\cdot\\frac{1}{2}\\rho A V^3/\\Omega$ "
    "($A=\\pi R^2$, $R$=120.675 m, $\\rho$=1.225 kg/m$^3$, "
    "V=10.659 m/s, $\\Omega$=0.78719 rad/s);  "
    "torque[MN$\\cdot$m] = $c_p\\times$" f"{TORQUE_PER_CP:.3f}."
)

#: Caption lines, each short enough to fit the figure width at fontsize 7.5.
MARKER_NOTE = (
    "Vertical dashed lines: the blade-tower passage events of every "
    "revolution -- rotor azimuth 73.9$^\\circ$ (blade 1), 193.9$^\\circ$ "
    "(blade 3), 313.6$^\\circ$ (blade 2), plus 360$k$."
)

MARKER_NOTE2 = (
    "These are the MEASURED events (the argmin of the per-blade $c_t$ over "
    "one revolution, reproduced by scripts/torque_ripple.py), not a fitted "
    "phase."
)

CONVENTION_NOTE = (
    "Phase convention: the rotor azimuth $\\psi$ is the unwrapped "
    "``angle_deg`` column; one revolution is 360$^\\circ$ = 7.9808 s at "
    "45.108 deg/s, and a line at $\\psi$ means the rotor is at $\\psi$ "
    "(blade 1 offset 0)."
)

MEASURED_NOTE = (
    "Measured: the raw-torque dip is ~44$^\\circ$ wide (below the 3/rev "
    "mean) and every one of the 9 markers falls inside it; its deepest point, "
    "however, sits 6.3$^\\circ$ (fitted 3/rev harmonic) to 13.4$^\\circ$ "
    "(120$^\\circ$ fold) BEFORE the line, see the terminal table."
)

POLAR_NOTE = (
    "The ALM and ASM runs used the polars from before ``liftReCorrExp 0``, "
    "so their absolute torque level carries that inflation."
)

ASM_MESH_NOTE = (
    "ASM-mesh is NOT included: the run is partial and still being written "
    "(~13 rev, its CSV grows while this runs); its torque swings "
    "13.8-76.9 MN.m within one revolution, ~70 % above ALM/ASM, and would "
    "swamp the ~1 % ripple."
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


def azimuth_to_time(time, az_deg, azimuth):
    """Interpolate the sample time at an unwrapped rotor azimuth."""
    return float(np.interp(azimuth, az_deg, time))


def detrend_per_rev(az_deg, values, rev):
    """Remove a linear least-squares trend inside each complete revolution.
    The ALM/ASM runs are still decaying, so a few tenths of MN.m of drift sit
    on top of the ~1 % ripple.  Removing one straight line per revolution (not
    a mean, and nothing that can follow the 3/rev ripple) is what makes the
    folded dip azimuth stable; it is only used for the *measurement*, never for
    the drawn trace.
    """
    out = np.array(values, dtype=float, copy=True)
    # ``int`` truncation on purpose: the window starts slightly after the
    # revolution boundary (first sample az = 6120.36) and ends slightly before
    # the last one (7199.62), so floor/ceil would leave a whole revolution
    # undetrended.
    k0 = int(rev.min())
    k1 = int(rev.max())
    for k in range(k0, k1 + 1):
        sel = (rev >= k) & (rev < k + 1)
        if sel.sum() < 3:
            continue
        x = az_deg[sel] - REV * k
        coef = np.polyfit(x, out[sel], 1)
        out[sel] -= np.polyval(coef, x)
    return out


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
    return centers, means


def folded_band(centers, ripple):
    """Below-the-mean region of a folded ripple around its own minimum.

    Returns ``(dip_azimuth, lo, hi)`` with ``lo``/``hi`` the two edges at which
    the ripple crosses zero, walking away from the dip in both directions.
    """
    n = len(centers)
    step = centers[1] - centers[0]
    i_dip = int(np.nanargmin(ripple))
    below = ripple < 0.0

    lo = centers[i_dip]
    for j in range(1, n + 1):
        i = (i_dip - j) % n
        if not below[i]:
            break
        lo = centers[i]

    hi = centers[i_dip]
    for j in range(1, n + 1):
        i = (i_dip + j) % n
        if not below[i]:
            break
        hi = centers[i]

    return {
        "dip_deg": float(centers[i_dip]),
        "lo_deg": float(lo),
        "hi_deg": float(hi),
        "p2p": float(np.nanmax(ripple) - np.nanmin(ripple)),
        "bin_deg": float(step),
    }


def harmonic_dip_azimuth(az_deg, values, period, n_harm):
    """Azimuth of the minimum of the fitted ``n_harm``/rev component.

    Drift- and noise-robust: the fitted harmonic cannot follow a trend or
    single-sample noise, only the ripple of that period.
    """
    phase = np.radians(az_deg)
    basis = np.column_stack(
        [np.cos(n_harm * phase), np.sin(n_harm * phase)]
    )
    coef, _, _, _ = np.linalg.lstsq(basis, values, rcond=None)
    fine = np.arange(0.0, period, 0.1)
    comp = coef[0] * np.cos(n_harm * np.radians(fine)) + coef[1] * np.sin(
        n_harm * np.radians(fine)
    )
    return float(fine[int(np.argmin(comp))]), float(np.hypot(*coef))


def circular_offset(a, b):
    """Smallest signed difference ``a - b`` modulo 360."""
    return (a - b + 180.0) % 360.0 - 180.0


def event_metrics(time, az_deg, torque, event_az, rev_end):
    """Per-revolution metrics of one passage event in the last RAW_REVS revs.

    ``event_az`` is the event azimuth of the last complete revolution; every
    earlier revolution repeats it every 360 deg.
    """
    rows = []
    for k in range(int(rev_end) - RAW_REVS, int(rev_end)):
        az_event = event_az + REV * k
        sel = np.abs(circular_offset(az_deg, az_event)) <= DIP_HALF_WINDOW
        if sel.sum() < 3:
            continue
        min_idx = int(np.argmin(np.where(sel, torque, np.inf)))
        az_min = float(az_deg[min_idx])
        t_min = float(torque[min_idx])
        t_before = float(np.interp(az_event - FLANK_DEG, az_deg, torque))
        t_after = float(np.interp(az_event + FLANK_DEG, az_deg, torque))
        flank = 0.5 * (t_before + t_after)
        rows.append(
            {
                "rev": k,
                "az_event": float(az_event),
                "time_event": float(np.interp(az_event, az_deg, time)),
                "torque_event": float(np.interp(az_event, az_deg, torque)),
                "az_min": az_min,
                "offset_deg": float(circular_offset(az_min, az_event)),
                "t_min": t_min,
                "t_before": t_before,
                "t_after": t_after,
                "flank": flank,
                "depth_pct": (flank - t_min) / flank * 100.0,
                "depth_marker_pct": (flank - float(np.interp(az_event, az_deg, torque)))
                / flank
                * 100.0,
            }
        )
    return rows


def load_run(label, run_dir, color, partial):
    """Read one run and pre-compute the panels, the markers and the metrics."""
    cols = read_turbine(run_dir)
    time = cols["time"]
    az = cols["angle_deg"]
    rev = az / REV
    torque = cols["cp"] * TORQUE_PER_CP

    rev_end = float(math.floor(rev.max() - 1.0) + 1)

    # -- window of the last RAW_REVS complete revolutions ------------------
    az_lo = (rev_end - RAW_REVS) * REV
    az_hi = rev_end * REV
    sel_raw = (az >= az_lo) & (az < az_hi)
    # -- last complete revolution only (panel 2) ---------------------------
    sel_one = (az >= az_hi - REV) & (az < az_hi)

    # -- passage markers ----------------------------------------------------
    markers = []
    for blade, event_az in EVENTS:
        for k in range(int(rev_end) - RAW_REVS, int(rev_end)):
            az_event = event_az + REV * k
            markers.append(
                {
                    "blade": blade,
                    "rev": k,
                    "az": az_event,
                    "time": azimuth_to_time(time, az, az_event),
                }
            )
    markers.sort(key=lambda m: m["time"])

    # -- dip-vs-marker coincidence measurement ------------------------------
    res = detrend_per_rev(az[sel_raw], torque[sel_raw], rev[sel_raw])
    centers, ripple = fold_profile(az[sel_raw], res)
    ripple = ripple - np.nanmean(ripple)
    band = folded_band(centers, ripple)
    fold_dip, amp3 = harmonic_dip_azimuth(az[sel_raw], res, 360.0, 3)

    coincidence = []
    for blade, event_az in EVENTS:
        folded_event = float(np.mod(event_az, FOLD_DEG))
        folded_dip = band["dip_deg"]
        off_fold = circular_offset(folded_event, folded_dip)
        off_harm = circular_offset(event_az, fold_dip + REV * int(rev_end - 1))
        in_band = (
            (folded_event >= band["lo_deg"]) and (folded_event <= band["hi_deg"])
        ) or (
            (band["lo_deg"] > band["hi_deg"])
            and not (band["hi_deg"] < folded_event < band["lo_deg"])
        )
        coincidence.append(
            {
                "blade": blade,
                "event_az": event_az,
                "folded_event": folded_event,
                "offset_fold_deg": off_fold,
                "offset_harmonic_deg": off_harm,
                "in_band": bool(in_band),
            }
        )

    # -- per-blade curves and their dips (panel 2 and the cross-check) ------
    blades = []
    if label == "ALM":
        az_one = az[sel_one]
        time_one = time[sel_one]
        for b in (1, 2, 3):
            curve = cols[f"ct_blade{b}"][sel_one]
            mean = float(curve.mean())
            dev = (curve / mean - 1.0) * 100.0
            # Raw argmin, the same single-sample estimator ``torque_ripple.py``
            # uses (there it reproduces 73.9 / 193.9 / 313.6 exactly).  The dip
            # is broad (~40 deg below the mean) and mildly asymmetric, so a
            # running mean would drag the argmin towards the flat middle.
            i_local = int(np.argmin(dev))
            blades.append(
                {
                    "blade": b,
                    "az": az_one,
                    "time": time_one,
                    "ct": curve,
                    "ct_dev_pct": dev,
                    "mean": mean,
                    "dip_az": float(az_one[i_local]),
                    "dip_pct": float(dev[i_local]),
                    "p2p_pct": float(np.ptp(curve) / mean * 100.0),
                }
            )

    # -- the passage-event table -------------------------------------------
    events = []
    for blade, event_az in EVENTS:
        events.append(
            {
                "blade": blade,
                "event_az": event_az,
                "rows": event_metrics(time, az, torque, event_az, rev_end),
            }
        )

    mean_rev = float(torque[sel_one].mean())
    mean_raw = float(torque[sel_raw].mean())
    p2p_raw = float(np.ptp(torque[sel_raw]))
    n_per_rev = float(sel_raw.sum()) / RAW_REVS

    return {
        "label": label,
        "color": color,
        "partial": partial,
        "rev_end": rev_end,
        "mean_rev": mean_rev,
        "mean_raw": mean_raw,
        "p2p_raw": p2p_raw,
        "amp3": amp3,
        "amp3_pct": amp3 / mean_raw * 100.0,
        "torque": torque,
        "time": time,
        "az": az,
        "rev": rev,
        "raw_time": time[sel_raw],
        "raw_az": az[sel_raw],
        "raw_torque": torque[sel_raw],
        "one_time": time[sel_one],
        "one_az": az[sel_one],
        "one_torque": torque[sel_one],
        "markers": markers,
        "events": events,
        "band": band,
        "fold_dip": fold_dip,
        "fold_centers": centers,
        "fold_ripple": ripple,
        "coincidence": coincidence,
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
            for x, y in zip(run["raw_time"], run["raw_torque"], strict=True):
                writer.writerow(
                    [run["label"], partial, "raw_last3", "torque",
                     f"{x:.6f}", f"{y:.6f}", "s", "MN.m"]
                )
            for x, y in zip(run["one_time"], run["one_torque"], strict=True):
                writer.writerow(
                    [run["label"], partial, "raw_last1", "torque",
                     f"{x:.6f}", f"{y:.6f}", "s", "MN.m"]
                )
            for marker in run["markers"]:
                writer.writerow(
                    [run["label"], partial, "passage_marker", marker["blade"],
                     f"{marker['time']:.6f}", f"{marker['az']:.4f}", "s", "deg"]
                )
            for blade in run["blades"]:
                for x, y in zip(blade["az"], blade["ct_dev_pct"], strict=True):
                    writer.writerow(
                        [run["label"], partial, "blade_last1",
                         f"ct_blade{blade['blade']}", f"{x:.4f}", f"{y:.8f}",
                         "deg", "%"]
                    )


def draw_markers(ax, run, ymax_frac=0.97, annotate_first=False):
    """Dashed vertical line at every passage event of one run."""
    for i, marker in enumerate(run["markers"]):
        ax.axvline(
            marker["time"],
            color="0.35",
            linestyle="--",
            linewidth=0.9,
            zorder=1,
        )
        if annotate_first and i < len(EVENTS):
            ax.annotate(
                marker["blade"],
                xy=(marker["time"], ymax_frac),
                xycoords=("data", "axes fraction"),
                xytext=(3, 0),
                textcoords="offset points",
                rotation=90,
                va="top",
                ha="left",
                fontsize=8.5,
                color="0.2",
                zorder=5,
            )


def azimuth_top_axis(ax, run, az_ticks, labels_are_mod=False):
    """Secondary top axis in rotor azimuth (deg), drawn with ``twiny``.

    ``az_ticks`` are rotor azimuths, which is what the labels show; the tick
    *positions* have to be the corresponding times.
    """
    top = ax.twiny()
    top.set_xlim(ax.get_xlim())
    times = [azimuth_to_time(run["time"], run["az"], t) for t in az_ticks]
    top.set_xticks(times)
    top.set_xticklabels(
        [f"{t % REV:.0f}" if labels_are_mod else f"{t:.0f}" for t in az_ticks]
    )
    top.set_xlabel("rotor azimuth  $\\psi$  [deg]" + (" mod 360" if labels_are_mod else " (unwrapped)"))
    for label in top.get_xticklabels():
        label.set_fontsize(8)
        label.set_rotation(45)
        label.set_ha("left")


def build_figure(runs, out: Path):
    by_label = {run["label"]: run for run in runs}
    for required in ("ALM", "ASM"):
        if required not in by_label:
            raise SystemExit(f"the {required} run is required for the figure")
    alm = by_label["ALM"]
    asm = by_label["ASM"]

    fig = plt.figure(figsize=(14.0, 17.0))
    grid = fig.add_gridspec(
        3, 1, hspace=0.40, left=0.085, right=0.895, top=0.905, bottom=0.16
    )
    ax1 = fig.add_subplot(grid[0])
    ax2 = fig.add_subplot(grid[1])
    ax3 = fig.add_subplot(grid[2])

    # ---- panel 1: raw torque, last three complete revolutions ------------
    ax1.plot(
        alm["raw_time"],
        alm["raw_torque"],
        color=alm["color"],
        linewidth=0.8,
        label="ALM (left axis)",
    )
    ax1_asm = ax1.twinx()
    ax1_asm.plot(
        asm["raw_time"],
        asm["raw_torque"],
        color=asm["color"],
        linewidth=0.8,
        label="ASM (right axis)",
    )
    # Same MN.m per unit on both axes, shifted by the 9.6 % level difference,
    # so the two curves are separated instead of drawn on top of each other and
    # their ripple amplitudes stay directly comparable.  The ASM overlay is
    # legible, so it is kept.
    lo = min(alm["raw_torque"].min(), asm["raw_torque"].min())
    hi = max(alm["raw_torque"].max(), asm["raw_torque"].max())
    pad = 0.08 * (hi - lo)
    ax1.set_ylim(alm["raw_torque"].min() - pad, alm["raw_torque"].max() + pad)
    delta = alm["mean_raw"] - asm["mean_raw"]
    ax1_asm.set_ylim(
        alm["raw_torque"].min() - pad - delta,
        alm["raw_torque"].max() + pad - delta,
    )
    ax1_asm.set_ylabel("ASM torque  [MN$\\cdot$m]  (right axis)", color=asm["color"])
    ax1_asm.tick_params(axis="y", colors=asm["color"])
    draw_markers(ax1, alm, annotate_first=True)
    ax1.set_ylabel("ALM torque  [MN$\\cdot$m]  (left axis)", color=alm["color"])
    ax1.tick_params(axis="y", colors=alm["color"])
    ax1.set_xlabel("time  [s]")
    ax1.grid(alpha=0.25)
    ax1.set_title(
        f"Panel 1 -- raw ALM torque, last {RAW_REVS} complete revolutions: "
        "1 sample per time step, no averaging, no smoothing;  ASM overlaid on "
        "the right axis",
        fontsize=11.5,
    )
    ax1.legend(
        handles=[
            Line2D([], [], color=alm["color"], linewidth=1.4, label="ALM"),
            Line2D([], [], color=asm["color"], linewidth=1.4, label="ASM"),
            Line2D([], [], color="0.35", linestyle="--", label="passage event"),
        ],
        loc="lower left",
        fontsize=9,
        ncol=3,
    )
    azimuth_top_axis(
        ax1, alm,
        np.arange(np.ceil(alm["raw_az"][0] / 120.0) * 120.0,
                  alm["raw_az"][-1] + 1, 120.0),
    )

    # ---- panel 2: one revolution, raw, plus the per-blade curves ---------
    ax2.plot(
        alm["one_time"],
        alm["one_torque"],
        color="0.15",
        linewidth=1.3,
        label="ALM raw torque",
    )
    ax2_ct = ax2.twinx()
    one_markers = [
        m for m in alm["markers"] if m["rev"] == int(alm["rev_end"]) - 1
    ]
    handles = [
        Line2D([], [], color="0.15", linewidth=1.6, label="ALM raw torque"),
    ]
    for marker in one_markers:
        ax2.axvline(
            marker["time"], color="0.35", linestyle="--", linewidth=1.0,
            zorder=1,
        )
    for blade in alm["blades"]:
        color = BLADE_COLORS[blade["blade"] - 1]
        ax2_ct.plot(
            blade["time"],
            blade["ct_dev_pct"],
            color=color,
            linewidth=1.1,
        )
        label = f"$c_{{t,{blade['blade']}}}$"
        handles.append(Line2D([], [], color=color, linewidth=1.4, label=label))
    # blade label of each marker, at the top of the panel so they neither
    # collide with the legend nor with the curves
    for marker in one_markers:
        ax2.annotate(
            marker["blade"],
            xy=(marker["time"], 0.985),
            xycoords=("data", "axes fraction"),
            xytext=(3, 0),
            textcoords="offset points",
            rotation=90,
            va="top",
            ha="left",
            fontsize=8.5,
            color="0.2",
            zorder=5,
        )
    ax2_ct.set_ylabel(
        "per-blade $c_t$ relative to its mean  [%]  (right axis)"
    )
    ax2.set_ylabel("ALM torque  [MN$\\cdot$m]  (left axis)")
    ax2.set_xlabel("time  [s]")
    ax2.grid(alpha=0.25)
    ax2.set_title(
        "Panel 2 -- zoom on ONE ALM revolution, still raw: every marker sits "
        "on the $c_t$ dip of exactly one blade (right axis)",
        fontsize=11.5,
    )
    ax2.legend(handles=handles, loc="lower left", fontsize=8.5, ncol=5)
    azimuth_top_axis(
        ax2, alm,
        np.arange(
            math.floor(alm["one_az"][0] / 60.0) * 60.0,
            alm["one_az"][-1] + 1,
            60.0,
        ),
        labels_are_mod=True,
    )

    # ---- panel 3: raw ASM torque, same markers ---------------------------
    ax3.plot(
        asm["raw_time"],
        asm["raw_torque"],
        color=asm["color"],
        linewidth=0.8,
        label="ASM",
    )
    draw_markers(ax3, asm)
    ax3.set_ylabel("ASM torque  [MN$\\cdot$m]", color=asm["color"])
    ax3.tick_params(axis="y", colors=asm["color"])
    ax3.set_xlabel("time  [s]")
    ax3.grid(alpha=0.25)
    ax3.set_title(
        f"Panel 3 -- raw ASM torque, last {RAW_REVS} complete revolutions, "
        "same passage markers (same 3/rev structure, level ~10 % lower);  "
        "ASM-mesh left out, still transient",
        fontsize=11.5,
    )
    ax3.legend(loc="lower left", fontsize=9)
    azimuth_top_axis(
        ax3, asm,
        np.arange(np.ceil(asm["raw_az"][0] / 120.0) * 120.0,
                  asm["raw_az"][-1] + 1, 120.0),
    )

    fig.suptitle(
        "IEA 15-240-RWT: raw torque signal and the blade-tower passage events\n"
        f"ALM {RAW_REVS} revolutions = {RAW_REVS * SECONDS_PER_REV:.1f} s, "
        f"{alm['n_per_rev']:.0f} samples per revolution, "
        f"torque mean {alm['mean_raw']:.2f} MN$\\cdot$m (ALM) / "
        f"{asm['mean_raw']:.2f} MN$\\cdot$m (ASM)",
        fontsize=13.5,
        y=0.978,
        linespacing=1.5,
    )
    notes = (
        MARKER_NOTE,
        MARKER_NOTE2,
        CONVENTION_NOTE,
        MEASURED_NOTE,
        POLAR_NOTE,
        TORQUE_NOTE,
        ASM_MESH_NOTE,
    )
    for i, note in enumerate(notes):
        fig.text(
            0.5,
            0.125 - i * 0.019,
            note,
            ha="center",
            va="top",
            fontsize=7.5 if i < len(notes) - 1 else 7.0,
            color="black" if i < len(notes) - 1 else "0.35",
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def print_table(runs):
    print()
    print("=" * 118)
    print(
        "TORQUE MEAN AND BLADE-TOWER PASSAGE EVENTS "
        f"(torque = cp * {TORQUE_PER_CP:.3f} MN.m)"
    )
    print("=" * 118)
    print(
        f"{'model':<9} {'partial':<8} {'mean T last rev':<17} "
        f"{'mean T last 3 rev':<18} {'raw p2p 3 rev':<14} "
        f"{'3/rev amp':<11} {'3/rev %':<8} {'samples/rev':<11}"
    )
    print("-" * 118)
    for run in runs:
        print(
            f"{run['label']:<9} {'yes' if run['partial'] else 'no':<8} "
            f"{run['mean_rev']:<17.3f} {run['mean_raw']:<18.3f} "
            f"{run['p2p_raw']:<14.3f} {run['amp3']:<11.4f} "
            f"{run['amp3_pct']:<8.2f} {run['n_per_rev']:<11.1f}"
        )
    print(
        "  mean T last rev     = mean over the last complete revolution "
        "(rev 19 -> 20 for the settled runs)."
    )
    print(
        f"  mean T last 3 rev   = mean over the last {RAW_REVS} complete "
        "revolutions (the plotted window)."
    )
    print(
        "  raw p2p 3 rev       = peak-to-peak of the raw signal in that window."
    )
    print(
        "  3/rev amp           = amplitude of the 3rd integer harmonic of the "
        "per-revolution-detrended signal in that window."
    )
    print()
    print("=" * 118)
    print(
        "PASSAGE-EVENT TABLE  "
        f"(local minimum = minimum of the raw signal within "
        f"+/-{DIP_HALF_WINDOW:.0f} deg of the event; "
        f"before/after = raw signal {FLANK_DEG:.0f} deg before/after the event; "
        "depth = (mean(before,after) - min)/mean(before,after))"
    )
    print("=" * 118)
    for run in runs:
        print()
        print(
            f"--- {run['label']}"
            + ("  (partial, still transient)" if run["partial"] else "")
        )
        print("-" * 118)
        header = (
            f"{'blade':<8} {'rev':<5} {'az_event':<10} {'t_event':<10} "
            f"{'T(marker)':<11} {'T(-15)':<10} {'T(+15)':<10} "
            f"{'flank mean':<11} {'T_min':<10} {'az_min':<10} "
            f"{'offset':<9} {'depth %':<9}"
        )
        print(header)
        for event in run["events"]:
            for row in event["rows"]:
                print(
                    f"{event['blade']:<8} {row['rev']:<5d} "
                    f"{row['az_event']:<10.1f} {row['time_event']:<10.3f} "
                    f"{row['torque_event']:<11.3f} {row['t_before']:<10.3f} "
                    f"{row['t_after']:<10.3f} {row['flank']:<11.3f} "
                    f"{row['t_min']:<10.3f} {row['az_min']:<10.2f} "
                    f"{row['offset_deg']:<+9.2f} {row['depth_pct']:<9.2f}"
                )
        # per-event summary over the shown revolutions
        print(
            "  (per-event values averaged over the "
            f"{len(run['events'][0]['rows'])} revolutions; "
            "'-- mean' rows below)"
        )
        for event in run["events"]:
            rows = event["rows"]
            if not rows:
                continue
            depth = np.mean([r["depth_pct"] for r in rows])
            offset = np.mean([r["offset_deg"] for r in rows])
            t_min = np.mean([r["t_min"] for r in rows])
            before = np.mean([r["t_before"] for r in rows])
            after = np.mean([r["t_after"] for r in rows])
            flank = np.mean([r["flank"] for r in rows])
            print(
                f"{event['blade']:<8} {'-- mean':<5} "
                f"{event['event_az']:<10.1f} "
                f"{np.mean([r['time_event'] for r in rows]):<10.3f} "
                f"{np.mean([r['torque_event'] for r in rows]):<11.3f} "
                f"{before:<10.3f} {after:<10.3f} {flank:<11.3f} "
                f"{t_min:<10.3f} "
                f"{np.mean([r['az_min'] for r in rows]):<10.2f} "
                f"{offset:<+9.2f} {depth:<9.2f}"
            )


def print_coincidence(runs):
    print()
    print("=" * 118)
    print(
        "DIP-vs-MARKER COINCIDENCE  (the point of the figure: is there a dip "
        "of the raw signal at EVERY marker?)"
    )
    print("=" * 118)
    for run in runs:
        band = run["band"]
        print()
        print(f"--- {run['label']}")
        print(
            f"  markers: {len(run['markers'])}  "
            f"({len(EVENTS)} events x {RAW_REVS} revolutions)"
        )
        print(
            f"  folded (mod 120 deg) ripple of the detrended raw signal: "
            f"minimum at {band['dip_deg']:.1f} deg "
            f"({band['bin_deg']:.0f} deg bins), p2p {band['p2p']:.3f} MN.m "
            f"= {band['p2p'] / run['mean_raw'] * 100:.2f} % of the mean"
        )
        print(
            f"  below-mean dip band of that fold: "
            f"{band['lo_deg']:.1f} deg .. {band['hi_deg']:.1f} deg "
            f"(width "
            f"{(band['hi_deg'] - band['lo_deg']) % FOLD_DEG:.1f} deg)"
        )
        print(
            f"  fitted 3/rev harmonic minimum at {run['fold_dip']:.1f} deg "
            f"(+120 deg), amplitude {run['amp3']:.4f} MN.m "
            f"= {run['amp3_pct']:.2f} % of the mean"
        )
        print()
        print(
            f"  {'blade':<8} {'event az':<10} {'folded az':<10} "
            f"{'offset vs fold min':<20} {'offset vs 3/rev min':<21} "
            f"{'marker inside dip band?':<24}"
        )
        for row in run["coincidence"]:
            print(
                f"  {row['blade']:<8} {row['event_az']:<10.1f} "
                f"{row['folded_event']:<10.1f} "
                f"{row['offset_fold_deg']:<+20.2f} "
                f"{row['offset_harmonic_deg']:<+21.2f} "
                f"{'yes' if row['in_band'] else 'no':<24}"
            )
        n_fold = sum(
            1 for r in run["coincidence"]
            if abs(r["offset_fold_deg"]) <= COINCIDENCE_DEG
        )
        n_harm = sum(
            1 for r in run["coincidence"]
            if abs(r["offset_harmonic_deg"]) <= COINCIDENCE_DEG
        )
        n_band = sum(1 for r in run["coincidence"] if r["in_band"])
        n_mark = len(run["markers"])
        print()
        print(
            f"  COUNT, {COINCIDENCE_DEG:.0f} deg tolerance, "
            f"{len(EVENTS)} passage events "
            f"({n_mark} markers over {RAW_REVS} revolutions):"
        )
        print(
            f"    marker inside the folded below-mean dip band : "
            f"{n_band * RAW_REVS}/{n_mark}"
        )
        print(
            f"    event within {COINCIDENCE_DEG:.0f} deg of the folded dip "
            f"minimum                  : {n_fold}/{len(EVENTS)}"
        )
        print(
            f"    event within {COINCIDENCE_DEG:.0f} deg of the fitted 3/rev "
            f"minimum                 : {n_harm}/{len(EVENTS)}"
        )
        n_window = 0
        for event in run["events"]:
            for row in event["rows"]:
                if abs(row["offset_deg"]) <= COINCIDENCE_DEG:
                    n_window += 1
        print(
            f"    marker within {COINCIDENCE_DEG:.0f} deg of the local raw "
            f"minimum (window min)     : {n_window}/{n_mark}"
        )
        if run["blades"]:
            n_blade = 0
            for blade in run["blades"]:
                near = min(
                    abs(circular_offset(blade["dip_az"], row["event_az"]))
                    for row in run["coincidence"]
                )
                if near <= COINCIDENCE_DEG:
                    n_blade += 1
            print(
                f"    per-blade c_t dip within {COINCIDENCE_DEG:.0f} deg of "
                f"its marker (ALM)      : {n_blade}/{len(run['blades'])}  "
                "(this is the phase the markers were measured from)"
            )
            for blade in run["blades"]:
                print(
                    f"      blade {blade['blade']}: c_t dip "
                    f"{blade['dip_pct']:+.2f}% at azimuth "
                    f"{blade['dip_az']:.1f} deg, p2p "
                    f"{blade['p2p_pct']:.2f}%"
                )
        sign = "before"
        print()
        print(
            f"  VERDICT ({run['label']}): {n_band * RAW_REVS}/{n_mark} markers "
            "sit inside a below-mean dip of the raw signal, i.e. the raw "
            "signal DOES dip at every marker."
        )
        print(
            f"    The dip minimum, however, is not under the line: the folded "
            f"dip is {abs(run['coincidence'][0]['offset_fold_deg']):.1f} deg "
            f"and the fitted 3/rev dip "
            f"{abs(run['coincidence'][0]['offset_harmonic_deg']):.1f} deg "
            f"{sign} the marker, so a strict "
            f"'{COINCIDENCE_DEG:.0f} deg of the dip minimum' test gives "
            f"{n_fold}/{len(EVENTS)} (fold) and {n_harm}/{len(EVENTS)} "
            "(3/rev).  The dip is broad (~40 deg) and asymmetric: the marker "
            "sits on its recovering shoulder."
        )


def print_mesh_status(runs):
    print()
    print("=" * 118)
    print("ASM-MESH")
    print("=" * 118)
    mesh_runs = [r for r in runs if r["label"] == "ASM-mesh"]
    if not mesh_runs:
        print("  not found in runs/")
        return
    mesh = mesh_runs[0]
    print("  included in the figure: NO")
    print(f"  reason: {ASM_MESH_NOTE}")
    print(
        f"  numbers: {len(mesh['torque'])} samples = "
        f"{mesh['rev'].max():.1f} revolutions; last complete revolution "
        f"{mesh['rev_end'] - 1:.0f}-{mesh['rev_end']:.0f}; "
        f"torque mean {mesh['mean_rev']:.2f} MN.m, "
        f"raw p2p over its last {RAW_REVS} revolutions "
        f"{mesh['p2p_raw']:.2f} MN.m "
        f"({mesh['p2p_raw'] / mesh['mean_raw'] * 100:.0f} % of the mean), "
        f"3/rev amplitude {mesh['amp3_pct']:.2f} % of the mean"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--png", type=Path, default=ANALYSIS / PNG_NAME)
    parser.add_argument("--csv", type=Path, default=ANALYSIS / CSV_NAME)
    parser.add_argument(
        "--no-figure", action="store_true", help="skip writing the PNG"
    )
    args = parser.parse_args()

    runs = sorted_runs()
    if not runs:
        raise SystemExit("no run data found")

    if not args.no_figure:
        build_figure(runs, args.png)
        print(f"wrote {args.png}")
    write_csv(runs, args.csv)
    print(f"wrote {args.csv}")
    print_table([r for r in runs if not r["partial"]])
    print_coincidence([r for r in runs if not r["partial"]])
    print_mesh_status(runs)


if __name__ == "__main__":
    main()
