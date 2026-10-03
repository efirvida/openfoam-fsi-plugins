#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Spanwise diagnosis figure for the IEA 15-240-RWT ALM validation.

PLOT-ONLY, dependency-light script (matplotlib + csv + math + numpy only). It
reads the converged per-element actuator-line CSVs of the live
``runs/iea15mw-asmcmp-alm`` run, averages them over the last two rotor
revolutions, and draws them against the CCBlade BEM reference at the same
operating point.  It writes ``runs/spanwise-diagnosis.png`` and prints the
numeric table the figure is built from.

Panels (all share the ``r/R`` x axis)
-------------------------------------
1. ``alpha_deg``        local angle of attack       [deg]
2. ``c_n``              normal/thrust coefficient   [-]
3. ``c_t``              tangential/torque coeff.    [-]
4. ``c_t/c_n``          torque-to-thrust ratio      [-]
5. ``a`` (thin, below)  axial induction            [-]

Axial induction of our run
--------------------------
The solver does not post-process the axial induction ``a`` per element, so it
is deduced from the force coefficients as documented in the task:

    tan(phi) = c_t / c_n            (phi = local inflow angle)
    Va       = omega * r * tan(phi) (axial velocity seen by the element)
    a        = 1 - Va / V           (axial induction factor)

with ``omega = 2*pi*RPM/60`` and ``r = ROTOR_RADIUS * (r/R)``.  This is the
classic blade-element relation ``tan(phi) = V*(1-a) / (omega*r*(1+a'))`` with
the tangential induction ``a'`` neglected and ``c_t/c_n`` used as the proxy for
``tan(phi)``.  The BEM value is the solver's own ``a``.  The panel exposes the
~25 % deficit of the ALM induction at mid span.

CCBlade BEM reference (from the committed snapshot)
---------------------------------------------------
The BEM arrays below are no longer embedded in this file: they live in
``analysis/spanwise-references.csv``, generated once with the maintainer's
Aeroelast from ``/scratch/leahk/eduardo.donestevez/fem-shell``::

    LD_LIBRARY_PATH=/scratch/app/gcc/14.2.0/lib64:$LD_LIBRARY_PATH PYTHONPATH=src \
      /scratch/leahk/eduardo.donestevez/venv/bin/python - <<'EOF'
    from aeroelast.models.blade.aerodynamics import load_blade_aero
    from aeroelast.solvers.bem.engine import BEMSolver
    ba = load_blade_aero("tests/IEA-15-240-RWT.yaml", hub_radius=3.97, n_blades=3)
    s  = BEMSolver(ba, rho=1.225, precone=4.0, tilt=0.0, yaw=0.0,
                   hub_height=150.0, shear_exp=0.0)
    res = s.compute(10.659, 7.518, 0.0, 0.0)
    EOF

which returned ``CP = 0.49098`` / ``CT = 0.79341`` (the self-check:
0.4910 / 0.7934).  This script reads the reference snapshot at import time so
it needs no Aeroelast import, and the snapshot generator lives in
``plot_3models_spanwise.py`` (``--write-references``).

Usage:
    plot_spanwise_diagnosis.py [--run-dir DIR] [--revs N] [--out FILE]
    plot_spanwise_diagnosis.py --from-csv [--profiles-csv FILE]

Regenerate the committed figure from the committed snapshot alone (no live
run, no Aeroelast)::

    /scratch/leahk/eduardo.donestevez/venv/bin/python \
      turbinesFoam/validation/iea15mw/scripts/plot_spanwise_diagnosis.py \
      --from-csv \
      --out turbinesFoam/validation/iea15mw/analysis/spanwise-diagnosis.png
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import plot_3models_spanwise as _references  # noqa: E402

DEFAULT_RUN_DIR = ROOT / "runs" / "iea15mw-asmcmp-alm"
DEFAULT_OUT = ROOT / "runs" / "spanwise-diagnosis.png"
PROFILES_CSV = ROOT / "analysis" / "spanwise-profiles.csv"

ELEMENT_DIR = Path("postProcessing") / "actuatorLineElements" / "0"
TURBINE_CSV = Path("postProcessing") / "turbines" / "0" / "turbine.csv"

#: Rated point of the IEA 15-240-RWT case (matches system/fvOptions.ALM).
RHO = 1.225
V_RATED = 10.659
RPM_RATED = 7.518
ROTOR_RADIUS = 120.67532
HUB_RADIUS = 3.97
BLADE_SPAN = 117.0
N_BLADES = 3
PRECONE_DEG = 4.0
TSR_RATED = 8.913

#: Default averaging window: the last two rotor revolutions.
DEFAULT_REVS = 2.0

#: Per-element columns averaged over the window.
MEAN_COLUMNS = ("root_dist", "alpha_deg", "c_ref_n", "c_ref_t")

#: Span window used for the headline offset/excess annotations.
ANNOTATE_LO = 0.30
ANNOTATE_HI = 0.90

# --- CCBlade BEM reference (loaded from the committed snapshot) -----------
# ``plot_3models_spanwise.py --write-references`` generates
# ``analysis/spanwise-references.csv`` from its module arrays; the loader is
# imported here so both plot scripts share one reference source (no second
# copy of the arrays).
_BEM, _SCALARS, _DIGITIZED = _references.load_references_csv(
    _references.REFERENCES_CSV)
#: BEM stations as r/R (r in metres / ROTOR_RADIUS).
BEM_RR = _BEM["rr"]
BEM_ALPHA_DEG = _BEM["alpha_deg"]
BEM_CN = _BEM["cn"]
BEM_CT = _BEM["ct"]
BEM_A = _BEM["a"]
#: CCBlade self-check at the operating point (must be CP 0.4910 / CT 0.7934).
BEM_CP = _SCALARS["cp"]
BEM_CT_ROTOR = _SCALARS["ct"]


# --- live-run reader (same conventions as compare_spanwise.py) -------------
def _element_index(path: Path) -> int:
    """Element number of ``turbine.blade1.element<N>.csv``."""
    stem = path.name
    marker = ".element"
    start = stem.rfind(marker)
    if start < 0:
        raise ValueError(f"{path}: not an element CSV")
    return int(stem[start + len(marker) : stem.rfind(".")])


def _rows(path: Path):
    """Stream a CSV, skipping blank or partially written rows.

    A live run can expose a truncated last line; such a row is dropped instead
    of aborting the whole comparison.
    """
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            if row is None or row.get("time") in (None, ""):
                continue
            yield row


def _last_time(path: Path) -> float | None:
    """Last ``time`` value in a CSV, or ``None`` when it has no rows."""
    value = None
    for row in _rows(path):
        try:
            value = float(row["time"])
        except (TypeError, ValueError):
            continue
    return value


def window_bounds(turbine_csv: Path, revs: float, rpm: float):
    """Averaging window ``[t_start, t_end]`` and the rotor period."""
    t_end = _last_time(turbine_csv) if turbine_csv.is_file() else None
    if t_end is None:
        raise FileNotFoundError(
            f"{turbine_csv}: no time rows; cannot bound the averaging window"
        )
    period = 60.0 / rpm
    return t_end - revs * period, t_end, period


def average_element(path: Path, t_start: float, t_end: float) -> dict:
    """Time-mean of :data:`MEAN_COLUMNS` for one element in the window."""
    sums = dict.fromkeys(MEAN_COLUMNS, 0.0)
    count = 0
    for row in _rows(path):
        try:
            time = float(row["time"])
        except (TypeError, ValueError):
            continue
        if time < t_start or time > t_end:
            continue
        try:
            for key in MEAN_COLUMNS:
                sums[key] += float(row[key])
        except (TypeError, ValueError):
            continue
        count += 1
    if count == 0:
        raise ValueError(f"{path}: no samples in [{t_start:.6g}, {t_end:.6g}]")
    return {key: value / count for key, value in sums.items()} | {"samples": count}


def average_turbine(path: Path, t_start: float, t_end: float) -> dict:
    """Time-mean of the module-reported ``cp``/``cd``/``ct``/``tsr``."""
    keys = ("tsr", "cp", "cd", "ct")
    sums = dict.fromkeys(keys, 0.0)
    count = 0
    for row in _rows(path):
        try:
            time = float(row["time"])
            if time < t_start or time > t_end:
                continue
            for key in keys:
                sums[key] += float(row[key])
        except (TypeError, ValueError):
            continue
        count += 1
    if count == 0:
        raise ValueError(f"{path}: no turbine samples in the window")
    return {key: value / count for key, value in sums.items()} | {"samples": count}


def r_over_r(root_dist: float) -> float:
    """Blade-normalised span fraction [-] -> projected ``r/R`` [-]."""
    return (HUB_RADIUS + root_dist * BLADE_SPAN) / ROTOR_RADIUS


def axial_induction(ct_over_cn: float, rr: float) -> float:
    """Deduce the axial induction ``a`` from ``c_t/c_n`` (see module docstring).

    ``omega = 2*pi*RPM/60``; ``r = ROTOR_RADIUS * rr``; ``Va`` is the axial
    velocity the element sees, taken from ``tan(phi) = c_t/c_n``.
    """
    omega = 2.0 * math.pi * RPM_RATED / 60.0
    radius = ROTOR_RADIUS * rr
    phi = math.atan(ct_over_cn)
    va = omega * radius * math.tan(phi)
    return 1.0 - va / V_RATED


def load_profile(run_dir: Path, revs: float, rpm: float):
    """Averaged spanwise profile of our run, as a dict of ``numpy`` arrays."""
    element_dir = run_dir / ELEMENT_DIR
    turbine_csv = run_dir / TURBINE_CSV
    if not element_dir.is_dir():
        raise FileNotFoundError(f"{element_dir}: not a directory")
    files = sorted(element_dir.glob("*.csv"), key=_element_index)
    if not files:
        raise FileNotFoundError(f"{element_dir}: no element CSVs")
    t_start, t_end, period = window_bounds(turbine_csv, revs, rpm)
    elements = [average_element(path, t_start, t_end) for path in files]
    n = len(elements)
    rr = np.array([r_over_r(e["root_dist"]) for e in elements])
    alpha = np.array([e["alpha_deg"] for e in elements])
    cn = np.array([e["c_ref_n"] for e in elements])
    ct = np.array([e["c_ref_t"] for e in elements])
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(cn != 0.0, ct / cn, np.nan)
    # The induction formula is only meaningful in the windmill state
    # (c_t/c_n > 0).  The reversed-flow root stations have c_t < 0 and would
    # otherwise yield a > 1, so they are left undefined (NaN).
    a_ours = np.full(n, np.nan)
    for i in range(n):
        if np.isfinite(ratio[i]) and ratio[i] > 0.0:
            a_ours[i] = axial_induction(ratio[i], rr[i])
    module = average_turbine(turbine_csv, t_start, t_end)
    return {
        "rr": rr,
        "alpha": alpha,
        "cn": cn,
        "ct": ct,
        "ratio": ratio,
        "a": a_ours,
        "n_elements": n,
        "dr": BLADE_SPAN / n,
        "window": (t_start, t_end, period),
        "module": module,
    }


def load_profile_from_csv(csv_path: Path, model: str = "alm") -> dict:
    """The same profile dict, read from ``analysis/spanwise-profiles.csv``.

    The snapshot averages the same last-two-revolutions window; the induction
    ``a`` is rebuilt exactly as :func:`load_profile` does, so the figure is the
    same as a live redraw from the snapshot's data.
    """
    rr, alpha, cn, ct = [], [], [], []
    window = (0.0, 0.0, 1.0)
    module = {"tsr": 0.0, "cp": 0.0, "cd": 0.0, "ct": 0.0}
    with csv_path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row.get("model") != model:
                continue
            rr.append(float(row["r_over_R"]))
            alpha.append(float(row["alpha_deg"]))
            cn.append(float(row["c_ref_n"]))
            ct.append(float(row["c_ref_t"]))
            t_start = float(row["window_start_s"])
            t_end = float(row["window_end_s"])
            revs = float(row["revs"])
            window = (t_start, t_end, (t_end - t_start) / revs)
            tsr = float(row["tsr"])
            cp = float(row["cp_module"])
            module = {
                "tsr": tsr,
                "cp": cp,
                # The snapshot stores C_T (``ct_module``); C_Q follows from
                # C_P = C_Q * TSR.
                "cd": float(row["ct_module"]),
                "ct": cp / tsr if tsr else float("nan"),
            }
    if not rr:
        raise FileNotFoundError(f"{csv_path}: no rows for model {model!r}")
    rr = np.array(rr)
    alpha = np.array(alpha)
    cn = np.array(cn)
    ct = np.array(ct)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(cn != 0.0, ct / cn, np.nan)
    a_ours = np.full(len(rr), np.nan)
    for i in range(len(rr)):
        if np.isfinite(ratio[i]) and ratio[i] > 0.0:
            a_ours[i] = axial_induction(ratio[i], rr[i])
    return {
        "rr": rr,
        "alpha": alpha,
        "cn": cn,
        "ct": ct,
        "ratio": ratio,
        "a": a_ours,
        "n_elements": len(rr),
        "dr": BLADE_SPAN / len(rr),
        "window": window,
        "module": module,
    }


def print_table(profile: dict) -> None:
    """Print the merged our-vs-BEM table (our stations, BEM interpolated)."""
    rr = profile["rr"]
    bem_alpha = np.interp(rr, BEM_RR, BEM_ALPHA_DEG)
    bem_cn = np.interp(rr, BEM_RR, BEM_CN)
    bem_ct = np.interp(rr, BEM_RR, BEM_CT)
    bem_a = np.interp(rr, BEM_RR, BEM_A)
    header = (
        "r/R",
        "alpha_ours",
        "alpha_bem",
        "d_alpha",
        "cn_ours",
        "cn_bem",
        "ct_ours",
        "ct_bem",
        "ct_excess_%",
        "ctcn_ours",
        "ctcn_bem",
        "a_ours",
        "a_bem",
    )
    print("spanwise our-run vs CCBlade BEM (our element stations, BEM interp.)")
    print("  " + ",".join(header))
    for i in range(len(rr)):
        excess = (profile["ct"][i] / bem_ct[i] - 1.0) * 100.0 if bem_ct[i] else float("nan")
        print(
            "  "
            + ",".join(
                (
                    f"{rr[i]:.4f}",
                    f"{profile['alpha'][i]:.3f}",
                    f"{bem_alpha[i]:.3f}",
                    f"{profile['alpha'][i] - bem_alpha[i]:+.3f}",
                    f"{profile['cn'][i]:.4f}",
                    f"{bem_cn[i]:.4f}",
                    f"{profile['ct'][i]:+.4f}",
                    f"{bem_ct[i]:+.4f}",
                    f"{excess:+.1f}",
                    f"{profile['ratio'][i]:.4f}",
                    f"{bem_ct[i] / bem_cn[i]:.4f}",
                    f"{profile['a'][i]:.4f}",
                    f"{bem_a[i]:.4f}",
                )
            )
        )


def print_summary(profile: dict) -> None:
    """Print the headline span-window statistics and the CCBlade self-check."""
    rr = profile["rr"]
    bem_alpha = np.interp(rr, BEM_RR, BEM_ALPHA_DEG)
    bem_ct = np.interp(rr, BEM_RR, BEM_CT)
    bem_a = np.interp(rr, BEM_RR, BEM_A)
    mask = (rr >= ANNOTATE_LO) & (rr <= ANNOTATE_HI)
    d_alpha = profile["alpha"][mask] - bem_alpha[mask]
    excess = (profile["ct"][mask] / bem_ct[mask] - 1.0) * 100.0
    deficit = (profile["a"][mask] - bem_a[mask]) / bem_a[mask] * 100.0
    print(
        f"\nsummary over r/R in [{ANNOTATE_LO:g}, {ANNOTATE_HI:g}] "
        f"({int(mask.sum())} elements)"
    )
    print(
        f"  d_alpha [deg]      : mean {d_alpha.mean():+.3f}  "
        f"min {d_alpha.min():+.3f}  max {d_alpha.max():+.3f}"
    )
    print(
        f"  c_t excess [%]     : mean {excess.mean():+.1f}  "
        f"min {excess.min():+.1f}  max {excess.max():+.1f}"
    )
    print(
        f"  a deficit  [%]     : mean {deficit.mean():+.1f}  "
        f"min {deficit.min():+.1f}  max {deficit.max():+.1f}"
    )
    mid = (rr >= 0.35) & (rr <= 0.65)
    a_mid_ours = np.nanmean(profile["a"][mid])
    a_mid_bem = bem_a[mid].mean()
    print(
        f"  mid-span a [0.35,0.65]: ours {a_mid_ours:.4f}  "
        f"BEM {a_mid_bem:.4f}  ({(a_mid_ours - a_mid_bem) / a_mid_bem * 100:+.1f} %)"
    )
    module = profile["module"]
    print(
        f"\nCCBlade self-check : CP {BEM_CP:.4f}  CT {BEM_CT_ROTOR:.4f}  "
        "(expected CP 0.4910 / CT 0.7934)"
    )
    print(
        f"our run (module)   : CP {module['cp']:.4f}  "
        f"CT {module['cd']:.4f}  C_Q {module['ct']:.4f}  "
        f"TSR {module['tsr']:.4f}"
    )
    print(
        f"window             : last {DEFAULT_REVS:g} revs = "
        f"[{profile['window'][0]:.6g}, {profile['window'][1]:.6g}] s "
        f"(period {profile['window'][2]:.6g} s)"
    )


def make_figure(profile: dict, out_png: Path) -> None:
    """Draw the five-panel spanwise diagnosis figure and save it."""
    rr = profile["rr"]
    bem_rr = np.array(BEM_RR)
    bem_alpha = np.array(BEM_ALPHA_DEG)
    bem_cn = np.array(BEM_CN)
    bem_ct = np.array(BEM_CT)
    bem_a = np.array(BEM_A)
    with np.errstate(divide="ignore", invalid="ignore"):
        bem_ratio = np.where(bem_cn != 0.0, bem_ct / bem_cn, np.nan)

    # Drop the single station that sits just outside r/R = 1.
    keep = bem_rr <= 1.0
    bem_rr, bem_alpha, bem_cn, bem_ct, bem_a, bem_ratio = (
        bem_rr[keep],
        bem_alpha[keep],
        bem_cn[keep],
        bem_ct[keep],
        bem_a[keep],
        bem_ratio[keep],
    )

    ours_kw = {"color": "tab:blue", "linewidth": 1.6, "marker": "o",
               "markersize": 3.5, "markevery": 4,
               "label": "ours (ALM, last 2 revs)"}
    bem_kw = {"color": "tab:red", "linewidth": 1.6, "marker": "s",
              "markersize": 3.5, "markevery": 3, "label": "CCBlade BEM"}

    fig = plt.figure(figsize=(13.5, 13.0))
    gs = fig.add_gridspec(3, 2, height_ratios=(1.0, 1.0, 0.55),
                          hspace=0.16, wspace=0.20)
    ax_alpha = fig.add_subplot(gs[0, 0])
    ax_cn = fig.add_subplot(gs[0, 1], sharex=ax_alpha)
    ax_ct = fig.add_subplot(gs[1, 0], sharex=ax_alpha)
    ax_ratio = fig.add_subplot(gs[1, 1], sharex=ax_alpha)
    ax_a = fig.add_subplot(gs[2, :], sharex=ax_alpha)

    panels = (
        (ax_alpha, profile["alpha"], bem_alpha),
        (ax_cn, profile["cn"], bem_cn),
        (ax_ct, profile["ct"], bem_ct),
        (ax_ratio, profile["ratio"], bem_ratio),
        (ax_a, profile["a"], bem_a),
    )
    for ax, ours, bem in panels:
        ax.plot(rr, ours, **ours_kw)
        ax.plot(bem_rr, bem, **bem_kw)
        ax.grid(True, alpha=0.3, linewidth=0.6)
        ax.legend(loc="best", fontsize=8, framealpha=0.9)

    ax_alpha.set_ylabel(r"$\alpha$  [deg]")
    ax_cn.set_ylabel(r"$c_n$  [-]")
    ax_ct.set_ylabel(r"$c_t$  [-]")
    ax_ratio.set_ylabel(r"$c_t/c_n$  [-]")
    ax_a.set_ylabel(r"$a$  [-]")
    ax_a.set_xlabel(r"$r/R$  [-]")

    ax_alpha.set_title(r"(a) local angle of attack $\alpha$", fontsize=10)
    ax_cn.set_title(r"(b) normal / thrust coefficient $c_n$", fontsize=10)
    ax_ct.set_title(r"(c) tangential / torque coefficient $c_t$", fontsize=10)
    ax_ratio.set_title(r"(d) torque-to-thrust ratio $c_t/c_n$", fontsize=10)
    ax_a.set_title(
        r"(e) axial induction $a = 1 - V_a/V$,  "
        r"$V_a = \omega\,r\,\tan\phi$,  $\tan\phi = c_t/c_n$  "
        "(reversed-flow root: undefined)",
        fontsize=10,
    )

    # Headline annotations.
    mask = (rr >= ANNOTATE_LO) & (rr <= ANNOTATE_HI)
    d_alpha = profile["alpha"][mask] - np.interp(rr, BEM_RR, BEM_ALPHA_DEG)[mask]
    ax_alpha.annotate(
        f"mean $\\Delta\\alpha$ = {d_alpha.mean():+.2f} deg\n"
        f"(range {d_alpha.min():+.2f} .. {d_alpha.max():+.2f})",
        xy=(0.55, 0.35), xycoords="axes fraction",
        fontsize=9, color="tab:blue",
        bbox={"boxstyle": "round", "fc": "white", "ec": "tab:blue",
              "alpha": 0.9},
    )
    excess = (profile["ct"][mask]
              / np.interp(rr, BEM_RR, BEM_CT)[mask] - 1.0) * 100.0
    ax_ct.annotate(
        f"$c_t$ excess {excess.min():+.0f} .. {excess.max():+.0f} %\n"
        f"(mean {excess.mean():+.0f} %)",
        xy=(0.40, 0.72), xycoords="axes fraction",
        fontsize=9, color="tab:blue",
        bbox={"boxstyle": "round", "fc": "white", "ec": "tab:blue",
              "alpha": 0.9},
    )
    mid = (rr >= 0.35) & (rr <= 0.65)
    bem_a_i = np.interp(rr, BEM_RR, BEM_A)
    a_ours_mid = np.nanmean(profile["a"][mid])
    a_bem_mid = bem_a_i[mid].mean()
    a_deficit = (a_ours_mid - a_bem_mid) / a_bem_mid * 100.0
    ax_a.annotate(
        f"mid-span $a$: ours {a_ours_mid:.3f} vs BEM {a_bem_mid:.3f} "
        f"({a_deficit:+.0f} %)",
        xy=(0.02, 0.06), xycoords="axes fraction",
        fontsize=9, color="tab:blue",
        bbox={"boxstyle": "round", "fc": "white", "ec": "tab:blue",
              "alpha": 0.9},
    )

    for ax in (ax_alpha, ax_cn, ax_ct, ax_ratio):
        ax.tick_params(labelbottom=False)
    ax_a.tick_params(labelbottom=True)
    ax_a.set_ylim(-0.05, 0.65)

    ax_alpha.set_xlim(0.0, 1.0)
    ax_alpha.set_ylim(bottom=0.0)
    fig.suptitle(
        "IEA 15-240-RWT spanwise diagnosis: ALM run vs CCBlade BEM\n"
        "V = 10.659 m/s   7.518 rpm   pitch 0$^\\circ$   "
        "uniform inflow   precone 4$^\\circ$   TSR 8.913",
        fontsize=13, y=0.985,
    )

    module = profile["module"]
    fig.text(
        0.995, 0.005,
        f"CCBlade self-check: CP {BEM_CP:.4f} / CT {BEM_CT_ROTOR:.4f}    "
        f"our module: CP {module['cp']:.4f} / CT {module['cd']:.4f}",
        ha="right", va="bottom", fontsize=8, color="0.35",
    )

    fig.subplots_adjust(left=0.075, right=0.985, top=0.925, bottom=0.065)
    _save_figure(fig, out_png)
    plt.close(fig)


def _save_figure(fig, out) -> None:
    """Save ``fig`` to a ``Path`` or a writable binary file-like object."""
    parent = getattr(out, "parent", None)
    if parent is not None:
        parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--revs", type=float, default=DEFAULT_REVS)
    parser.add_argument("--rpm", type=float, default=RPM_RATED)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--from-csv", action="store_true",
        help="read the ALM profile from the committed profiles CSV instead "
             "of the live run directory",
    )
    parser.add_argument("--profiles-csv", type=Path, default=PROFILES_CSV)
    args = parser.parse_args(argv)

    if args.from_csv:
        profile = load_profile_from_csv(args.profiles_csv, "alm")
    else:
        profile = load_profile(args.run_dir.resolve(), args.revs, args.rpm)
    print_table(profile)
    print_summary(profile)
    make_figure(profile, args.out)
    print(f"\nwrote {args.out.resolve()} "
          f"({args.out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
