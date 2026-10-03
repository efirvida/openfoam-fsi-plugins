#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Three-model spanwise comparison for the IEA 15-240-RWT validation.

PLOT-ONLY, dependency-light script (matplotlib + csv + math + numpy only).  It
reads the per-element actuator outputs of the three live comparison runs that
share one mesh and one operating point and differ only in the force model:

* ALM      ``runs/iea15mw-asmcmp-alm/``
* ASM      ``runs/iea15mw-asmcmp-asm/``
* ASM-mesh ``runs/iea15mw-asmcmp-asm-mesh/``

Each run is averaged over its own last two rotor revolutions (the "same last-2
revolution rule", applied per run because the three runs are at different
transient depths).  The three curves are drawn against the embedded CCBlade
BEM reference at the same operating point, so the figure answers whether the
angle-of-attack offset and the tangential-load excess are a common *method*
effect or model-specific.  Writes ``runs/spanwise-3models.png`` and prints the
numeric table the figure is built from.

Panels (all share the ``r/R`` x axis)
-------------------------------------
1. ``alpha_deg``   local angle of attack            [deg]  + BEM offset per model
2. ``c_n``         normal / thrust coefficient      [-]    + ``model/BEM`` ratio
3. ``c_t``         tangential / torque coefficient  [-]    + ``model/BEM`` ratio
4. ``c_t/c_n``     torque-to-thrust ratio           [-]    (normalisation-free)

Column and unit conventions (verified against the ALM module CSV and reused
verbatim for all three runs, whose element headers are identical)
------------------------------------------------------------------
* ``root_dist`` is the blade-normalised span fraction in ``[0, 1]`` measured
  from the root cutout: ``r = HUB_RADIUS + root_dist * BLADE_SPAN`` and
  ``r/R = r / ROTOR_RADIUS`` (the convention baked into the embedded CCBlade
  ``r/R`` arrays, so the two are directly comparable).
* ``alpha_deg`` is the angle actually used for the polar lookup.
* ``c_ref_n``/``c_ref_t`` are the element normal/tangential *coefficients* in
  the flow (plane-of-rotation) reference frame:
  ``c_ref_n = cl*cos(phi) + cd*sin(phi)``,
  ``c_ref_t = cl*sin(phi) - cd*cos(phi)`` with ``phi`` the element inflow
  reference angle.  ``c_t/c_n`` is their ratio.

Derivation fallback (documented, but NOT needed for these three runs)
---------------------------------------------------------------------
A variant of this reader may meet per-element CSVs that carry the polar values
(``cl``, ``cd``, ``alpha_deg``) but omit ``c_ref_n``/``c_ref_t``.  In that case
the coefficients are reconstructed per row from the polar values and the local
blade geometry (``data/iea15mw_blade.csv``):

    theta = -pitch_deg          (pitch_deg interpolated at r, column of the
                                 blade CSV; collective pitch is 0)
    phi   = alpha_deg + theta   (inflow angle, degrees -> radians)
    c_n   = cl*cos(phi) + cd*sin(phi)
    c_t   = cl*sin(phi) - cd*cos(phi)

The fallback is applied per row and then averaged over the window.  All three
runs currently write ``c_ref_n``/``c_ref_t`` directly, so the fallback is
dormant; it is retained so the script stays correct if a force model stops
writing the coefficients.  (Cross-check at element 43 of the ALM run: the
fallback reproduces the written ``c_ref_n``/``c_ref_t`` to <= 3e-4.)

CCBlade BEM reference (embedded, reproducible)
----------------------------------------------
The BEM arrays below were produced once from the maintainer's Aeroelast, from
``/scratch/leahk/eduardo.donestevez/fem-shell``::

    LD_LIBRARY_PATH=/scratch/app/gcc/14.2.0/lib64:$LD_LIBRARY_PATH PYTHONPATH=src \
      /scratch/leahk/eduardo.donestevez/venv/bin/python - <<'EOF'
    from aeroelast.models.blade.aerodynamics import load_blade_aero
    from aeroelast.solvers.bem.engine import BEMSolver
    ba = load_blade_aero("tests/IEA-15-240-RWT.yaml", hub_radius=3.97, n_blades=3)
    s  = BEMSolver(ba, rho=1.225, precone=4.0, tilt=0.0, yaw=0.0,
                   hub_height=150.0, shear_exp=0.0)
    res = s.compute(10.659, 7.518, 0.0, 0.0)
    EOF

which returned ``CP = 0.49098`` / ``CT = 0.79341`` (self-check 0.4910 / 0.7934).
The arrays are embedded verbatim so this figure needs no Aeroelast import.

Usage:
    plot_3models_spanwise.py [--revs N] [--rpm R] [--out FILE]
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
RUNS_DIR = ROOT / "runs"
BLADE_CSV = ROOT / "data" / "iea15mw_blade.csv"
DEFAULT_OUT = RUNS_DIR / "spanwise-3models.png"

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

#: Default averaging window: the last two rotor revolutions of each run.
DEFAULT_REVS = 2.0

#: Span window used for the headline offset/excess annotations.
ANNOTATE_LO = 0.30
ANNOTATE_HI = 0.90

#: Common stations printed in the terminal table.
STATIONS = (0.30, 0.45, 0.60, 0.75, 0.90)

#: The three force models under comparison: (label, run directory, colour, marker).
MODELS = (
    ("ALM", RUNS_DIR / "iea15mw-asmcmp-alm", "tab:blue", "o"),
    ("ASM", RUNS_DIR / "iea15mw-asmcmp-asm", "tab:green", "^"),
    ("ASM-mesh", RUNS_DIR / "iea15mw-asmcmp-asm-mesh", "tab:orange", "s"),
)
BEM_COLOR = "0.15"
RATIO_COLOR = "0.45"

# --- CCBlade BEM reference (embedded) ------------------------------------
#: BEM stations as r/R (r in metres / ROTOR_RADIUS).
BEM_RR = (
    0.0328982, 0.0526848, 0.0724714, 0.092258, 0.112045, 0.131831, 0.151618,
    0.171404, 0.191191, 0.210978, 0.230764, 0.250551, 0.270337, 0.290124,
    0.309911, 0.329697, 0.349484, 0.369271, 0.389057, 0.408844, 0.42863,
    0.448417, 0.468204, 0.48799, 0.507777, 0.527563, 0.54735, 0.567137,
    0.586923, 0.60671, 0.626496, 0.646283, 0.66607, 0.685856, 0.705643,
    0.725429, 0.745216, 0.765003, 0.784789, 0.804576, 0.824362, 0.844149,
    0.863936, 0.883722, 0.903509, 0.923295, 0.943082, 0.962869, 0.982655,
    0.987899, 0.992746, 0.997594, 1.00244,
)
BEM_ALPHA_DEG = (
    53.6152, 49.2572, 41.7282, 35.6201, 30.7792, 19.8734, 16.7894, 14.5679,
    12.9387, 11.7059, 9.7053, 8.96115, 8.37663, 7.95477, 7.64776, 7.59426,
    7.41665, 7.25693, 7.10425, 7.16898, 7.02982, 6.91026, 6.80774, 6.71904,
    6.82122, 6.75477, 6.69806, 6.64594, 6.59804, 6.554, 6.5192, 6.49632,
    6.48831, 6.50127, 6.54112, 6.74763, 6.86167, 6.98679, 7.10874, 7.21126,
    7.28075, 7.26879, 7.20829, 7.11455, 6.97915, 6.78887, 6.51595, 6.09108,
    5.29659, 4.98498, 4.69045, 4.46822, 4.92292,
)
BEM_CN = (
    0.327246, 0.316849, 0.294051, 0.270399, 0.24772, 1.5004, 1.57632,
    1.59766, 1.58402, 1.55178, 1.63061, 1.57307, 1.52185, 1.48276, 1.45351,
    1.4059, 1.38735, 1.37028, 1.3535, 1.30207, 1.28617, 1.27245, 1.26066,
    1.25045, 1.21041, 1.20299, 1.1967, 1.19088, 1.18552, 1.18074, 1.17717,
    1.17495, 1.17446, 1.17642, 1.18156, 1.16034, 1.1744, 1.1898, 1.20481,
    1.21744, 1.22605, 1.22477, 1.2176, 1.20643, 1.19027, 1.16758, 1.13517,
    1.08528, 0.994517, 0.959689, 0.927063, 0.902588, 0.952628,
)
BEM_CT = (
    -0.124138, -0.148684, -0.189827, -0.222226, -0.247254, 0.804273,
    0.749865, 0.666203, 0.579763, 0.501322, 0.516641, 0.455167, 0.405259,
    0.365366, 0.333139, 0.307265, 0.284621, 0.264545, 0.246397, 0.231568,
    0.216999, 0.204116, 0.192659, 0.182401, 0.171932, 0.163633, 0.156077,
    0.149147, 0.142788, 0.138133, 0.132829, 0.128002, 0.123634, 0.119702,
    0.116185, 0.114201, 0.111359, 0.108721, 0.106266, 0.103989, 0.101872,
    0.0998347, 0.0977025, 0.0952526, 0.0922342, 0.0882905, 0.0827887,
    0.0742553, 0.057719, 0.0515146, 0.0459012, 0.0420918, 0.0533293,
)
#: CCBlade self-check at the operating point (must be CP 0.4910 / CT 0.7934).
BEM_CP = 0.49098
BEM_CT_ROTOR = 0.79341

#: Element CSV columns that must be present for each reading mode.
DIRECT_POLARS = ("time", "root_dist", "alpha_deg", "c_ref_n", "c_ref_t")
DERIVED_POLARS = ("time", "root_dist", "alpha_deg", "cl", "cd")


# --- geometry helper ------------------------------------------------------
def load_pitch_table(path: Path):
    """Return ``(radii, pitch_deg)`` from ``data/iea15mw_blade.csv``.

    The blade CSV starts with ``#`` comment lines and has a
    ``radius_m,pitch_deg`` pair per station.  Used only by the derivation
    fallback.
    """
    radii: list[float] = []
    pitch: list[float] = []
    if not path.is_file():
        return radii, pitch
    with path.open(encoding="utf-8", newline="") as stream:
        lines = [line for line in stream if not line.startswith("#")]
    reader = csv.DictReader(lines)
    for row in reader:
        try:
            radii.append(float(row["radius_m"]))
            pitch.append(float(row["pitch_deg"]))
        except (TypeError, ValueError, KeyError):
            continue
    return radii, pitch


def pitch_at(radii, pitch, radius: float) -> float:
    """Linear interpolation of ``pitch_deg`` at ``radius`` [m].

    ``numpy.interp`` clamps outside the table to the end values, which is the
    desired behaviour for this fallback.
    """
    if not radii:
        return 0.0
    return float(np.interp(radius, radii, pitch))


# --- live-run reader (same conventions as compare_spanwise.py) -------------
def _element_index(path: Path) -> int:
    """Element number of ``turbine.blade1.element<N>.csv``."""
    stem = path.name
    marker = ".element"
    start = stem.rfind(marker)
    if start < 0:
        raise ValueError(f"{path}: not an element CSV")
    return int(stem[start + len(marker) : stem.rfind(".")])


def _header(path: Path):
    """Column names of the first line of ``path``."""
    with path.open(encoding="utf-8", newline="") as stream:
        return [name.strip() for name in stream.readline().split(",")]


def _last_time(path: Path) -> float | None:
    """Last ``time`` value in a CSV, skipping blank/truncated rows."""
    if not path.is_file():
        return None
    value = None
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            if row is None:
                continue
            try:
                value = float(row["time"])
            except (TypeError, ValueError):
                continue
    return value


def window_bounds(turbine_csv: Path, revs: float, rpm: float):
    """Averaging window ``[t_start, t_end]`` and the rotor period."""
    t_end = _last_time(turbine_csv)
    if t_end is None:
        raise FileNotFoundError(
            f"{turbine_csv}: no time rows; cannot bound the averaging window"
        )
    period = 60.0 / rpm
    return t_end - revs * period, t_end, period


def average_element(path: Path, t_start: float, t_end: float, mode: str,
                    pitch_table) -> tuple[float, float, float, float] | None:
    """Window mean ``(root_dist, alpha_deg, c_n, c_t)`` for one element CSV.

    ``mode`` is ``"direct"`` when the file carries ``c_ref_n``/``c_ref_t``, or
    ``"derived"`` when they must be reconstructed from ``cl``/``cd`` and the
    blade twist (see module docstring).  Returns ``None`` when the window
    holds no sample for this element.
    """
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader, None)
        if header is None:
            return None
        index = {name.strip(): i for i, name in enumerate(header)}
        i_time = index.get("time")
        i_alpha = index.get("alpha_deg")
        i_root = index.get("root_dist")
        if i_time is None or i_alpha is None or i_root is None:
            return None
        if mode == "direct":
            i_cn = index.get("c_ref_n")
            i_ct = index.get("c_ref_t")
            if i_cn is None or i_ct is None:
                return None
            return _average_direct(
                reader, t_start, t_end, i_time, i_alpha, i_root, i_cn, i_ct
            )
        i_cl = index.get("cl")
        i_cd = index.get("cd")
        if i_cl is None or i_cd is None:
            return None
        return _average_derived(
            reader, t_start, t_end, i_time, i_alpha, i_root, i_cl, i_cd,
            pitch_table,
        )


def _average_direct(reader, t_start, t_end, i_time, i_alpha, i_root, i_cn,
                    i_ct):
    """Window mean of the coefficients written directly by the run."""
    root_sum = alpha_sum = cn_sum = ct_sum = 0.0
    count = 0
    for row in reader:
        if not row:
            continue
        try:
            time = float(row[i_time])
            if time < t_start or time > t_end:
                continue
            root_sum += float(row[i_root])
            alpha_sum += float(row[i_alpha])
            cn_sum += float(row[i_cn])
            ct_sum += float(row[i_ct])
        except (ValueError, IndexError):
            continue
        count += 1
    if count == 0:
        return None
    return (root_sum / count, alpha_sum / count, cn_sum / count,
            ct_sum / count)


def _average_derived(reader, t_start, t_end, i_time, i_alpha, i_root, i_cl,
                     i_cd, pitch_table):
    """Window mean with ``c_n``/``c_t`` reconstructed from ``cl``/``cd``."""
    root_sum = alpha_sum = cn_sum = ct_sum = 0.0
    count = 0
    for row in reader:
        if not row:
            continue
        try:
            time = float(row[i_time])
            if time < t_start or time > t_end:
                continue
            root = float(row[i_root])
            alpha = float(row[i_alpha])
            radius = HUB_RADIUS + root * BLADE_SPAN
            pitch = pitch_at(pitch_table[0], pitch_table[1], radius)
            phi = math.radians(alpha - pitch)
            cl = float(row[i_cl])
            cd = float(row[i_cd])
            cn = cl * math.cos(phi) + cd * math.sin(phi)
            ct = cl * math.sin(phi) - cd * math.cos(phi)
        except (ValueError, IndexError):
            continue
        root_sum += root
        alpha_sum += alpha
        cn_sum += cn
        ct_sum += ct
        count += 1
    if count == 0:
        return None
    return (root_sum / count, alpha_sum / count, cn_sum / count,
            ct_sum / count)


def load_profile(label: str, run_dir: Path, revs: float, rpm: float) -> dict:
    """Averaged spanwise profile of one run, as a dict of ``numpy`` arrays."""
    element_dir = run_dir / ELEMENT_DIR
    turbine_csv = run_dir / TURBINE_CSV
    if not element_dir.is_dir():
        raise FileNotFoundError(f"{element_dir}: not a directory")
    files = sorted(element_dir.glob("*.csv"), key=_element_index)
    if not files:
        raise FileNotFoundError(f"{element_dir}: no element CSVs")
    header = _header(files[0])
    mode = "direct" if {"c_ref_n", "c_ref_t"} <= set(header) else "derived"
    pitch_table = load_pitch_table(BLADE_CSV) if mode == "derived" else ([], [])

    t_start, t_end, period = window_bounds(turbine_csv, revs, rpm)

    rr, alpha, cn, ct = [], [], [], []
    missing = []
    for path in files:
        element = average_element(path, t_start, t_end, mode, pitch_table)
        if element is None:
            missing.append(_element_index(path))
            continue
        rr.append((HUB_RADIUS + element[0] * BLADE_SPAN) / ROTOR_RADIUS)
        alpha.append(element[1])
        cn.append(element[2])
        ct.append(element[3])
    rr = np.array(rr)
    alpha = np.array(alpha)
    cn = np.array(cn)
    ct = np.array(ct)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(cn != 0.0, ct / cn, np.nan)
    return {
        "label": label,
        "run_dir": run_dir,
        "element_dir": element_dir,
        "turbine_csv": turbine_csv,
        "header": header,
        "mode": mode,
        "n_files": len(files),
        "n_used": len(alpha),
        "missing": missing,
        "rr": rr,
        "alpha": alpha,
        "cn": cn,
        "ct": ct,
        "ratio": ratio,
        "window": (t_start, t_end, period),
        "revs_to_end": t_end / period,
    }


# --- table and summarise ---------------------------------------------------
def bem_at(value, rr):
    """Interpolate an embedded BEM array at ``rr``."""
    return np.interp(rr, BEM_RR, value)


def print_model_report(profiles) -> None:
    """Per-model window, input paths, file counts and header line."""
    print("=" * 78)
    print("INPUTS (read-only; all runs are live and were not modified)")
    print("=" * 78)
    for profile in profiles:
        t_start, t_end, period = profile["window"]
        print(f"\n[{profile['label']}]")
        print(f"  element dir : {profile['element_dir']}")
        print(f"  turbine csv : {profile['turbine_csv']}")
        print(f"  element files found : {profile['n_files']} "
              f"(used {profile['n_used']}"
              + (f", no in-window samples for {profile['missing']}"
                 if profile["missing"] else "") + ")")
        print(f"  mode        : {profile['mode']} "
              + ("(c_ref_n/c_ref_t written by the run)"
                 if profile["mode"] == "direct"
                 else "(reconstructed from cl/cd + blade pitch)"))
        print(f"  header      : {','.join(profile['header'])}")
        print(f"  window      : t_start {t_start:.6f} s   "
              f"t_end {t_end:.6f} s   "
              f"({(t_end - t_start) / period:.3f} revs averaged, "
              f"period {period:.6f} s)")
        print(f"  run to date : {profile['revs_to_end']:.3f} revs "
              f"(t_end/period at {RPM_RATED} rpm)")


def print_station_table(profiles) -> None:
    """Compact model-vs-BEM table at :data:`STATIONS`."""
    print("\n" + "=" * 78)
    print("COMMON-STATION TABLE  (model vs CCBlade BEM, BEM interpolated)")
    print("=" * 78)
    header = ("r/R", "model", "alpha_deg", "c_n", "c_t",
              "c_n/BEM", "c_t/BEM")
    print("  " + "  ".join(f"{name:>8}" for name in header))
    model_lookup = {p["label"]: p for p in profiles}
    for station in STATIONS:
        bem_alpha = float(bem_at(BEM_ALPHA_DEG, station))
        bem_cn = float(bem_at(BEM_CN, station))
        bem_ct = float(bem_at(BEM_CT, station))
        rows = [("BEM", bem_alpha, bem_cn, bem_ct, 1.0, 1.0)]
        for label, _, _, _ in MODELS:
            profile = model_lookup.get(label)
            if profile is None:
                rows.append((label, *_nan_fields()))
                continue
            a = float(np.interp(station, profile["rr"], profile["alpha"]))
            n = float(np.interp(station, profile["rr"], profile["cn"]))
            t = float(np.interp(station, profile["rr"], profile["ct"]))
            rows.append((label, a, n, t, n / bem_cn, t / bem_ct))
        for label, a, n, t, rn, rt in rows:
            print(
                "  "
                + "  ".join(
                    (
                        f"{station:>8.3f}", f"{label:>8}", f"{a:>8.3f}",
                        f"{n:>8.4f}", f"{t:>8.4f}", f"{rn:>8.3f}",
                        f"{rt:>8.3f}",
                    )
                )
            )
        print()


def _nan_fields():
    nan = float("nan")
    return nan, nan, nan, nan, nan


def print_offsets(profiles) -> None:
    """Mean BEM offset per model over the annotation span."""
    print("=" * 78)
    print(f"SPAN-WINDOW MEANS over r/R in [{ANNOTATE_LO:g}, {ANNOTATE_HI:g}]")
    print("=" * 78)
    for profile in profiles:
        rr = profile["rr"]
        mask = (rr >= ANNOTATE_LO) & (rr <= ANNOTATE_HI)
        d_alpha = profile["alpha"][mask] - bem_at(BEM_ALPHA_DEG, rr)[mask]
        excess_n = (profile["cn"][mask] / bem_at(BEM_CN, rr)[mask] - 1.0) * 100.0
        excess_t = (profile["ct"][mask] / bem_at(BEM_CT, rr)[mask] - 1.0) * 100.0
        print(
            f"  {profile['label']:>8}: "
            f"mean d_alpha {d_alpha.mean():+.3f} deg "
            f"(min {d_alpha.min():+.3f}, max {d_alpha.max():+.3f})   "
            f"c_n excess {excess_n.mean():+.1f} %   "
            f"c_t excess {excess_t.mean():+.1f} %"
        )


# --- figure ---------------------------------------------------------------
def make_figure(profiles, out_png: Path) -> None:
    """Draw the four-panel three-model comparison and save it."""
    bem_rr = np.array(BEM_RR)
    bem_alpha = np.array(BEM_ALPHA_DEG)
    bem_cn = np.array(BEM_CN)
    bem_ct = np.array(BEM_CT)
    with np.errstate(divide="ignore", invalid="ignore"):
        bem_ratio = np.where(bem_cn != 0.0, bem_ct / bem_cn, np.nan)
    keep = bem_rr <= 1.0
    bem_rr, bem_alpha, bem_cn, bem_ct, bem_ratio = (
        bem_rr[keep], bem_alpha[keep], bem_cn[keep], bem_ct[keep],
        bem_ratio[keep],
    )

    fig = plt.figure(figsize=(14.0, 10.5))
    gs = fig.add_gridspec(2, 2, hspace=0.30, wspace=0.22)
    ax_alpha = fig.add_subplot(gs[0, 0])
    ax_cn = fig.add_subplot(gs[0, 1])
    ax_ct = fig.add_subplot(gs[1, 0])
    ax_ratio = fig.add_subplot(gs[1, 1])
    ax_cn_r = ax_cn.twinx()
    ax_ct_r = ax_ct.twinx()

    model_handles = []
    for label, _, color, marker in MODELS:
        profile = next((p for p in profiles if p["label"] == label), None)
        if profile is None:
            continue
        rr = profile["rr"]
        for ax, values in (
            (ax_alpha, profile["alpha"]),
            (ax_cn, profile["cn"]),
            (ax_ct, profile["ct"]),
            (ax_ratio, profile["ratio"]),
        ):
            ax.plot(rr, values, color=color, linewidth=1.6, marker=marker,
                    markersize=3.2, markevery=6, label=label)
        ax_cn_r.plot(rr, profile["cn"] / bem_at(BEM_CN, rr), color=color,
                     linewidth=1.0, linestyle="--", alpha=0.85)
        ax_ct_r.plot(rr, profile["ct"] / bem_at(BEM_CT, rr), color=color,
                     linewidth=1.0, linestyle="--", alpha=0.85)
        model_handles.append(
            Line2D([], [], color=color, linewidth=1.6, marker=marker,
                   markersize=3.2, label=label)
        )

    bem_handle = Line2D([], [], color=BEM_COLOR, linewidth=1.6,
                        linestyle="--", label="CCBlade BEM")
    ax_alpha.plot(bem_rr, bem_alpha, color=BEM_COLOR, linewidth=1.6,
                  linestyle="--")
    ax_cn.plot(bem_rr, bem_cn, color=BEM_COLOR, linewidth=1.6, linestyle="--")
    ax_ct.plot(bem_rr, bem_ct, color=BEM_COLOR, linewidth=1.6, linestyle="--")
    ax_ratio.plot(bem_rr, bem_ratio, color=BEM_COLOR, linewidth=1.6,
                  linestyle="--")

    ratio_handle = Line2D([], [], color=RATIO_COLOR, linewidth=1.0,
                          linestyle="--", label="model/BEM (right axis)")
    ax_cn_r.axhline(1.0, color=RATIO_COLOR, linewidth=0.9, linestyle=":")
    ax_ct_r.axhline(1.0, color=RATIO_COLOR, linewidth=0.9, linestyle=":")

    for ax in (ax_alpha, ax_cn, ax_ct, ax_ratio):
        ax.grid(True, alpha=0.3, linewidth=0.6)
        ax.set_xlim(0.0, 1.0)
    ax_cn_r.set_ylim(0.0, 2.2)
    ax_ct_r.set_ylim(0.0, 2.4)
    for ax, lab in ((ax_cn_r, r"$c_n$ model/BEM  [-]"),
                    (ax_ct_r, r"$c_t$ model/BEM  [-]")):
        ax.set_ylabel(lab, color=RATIO_COLOR)
        ax.tick_params(axis="y", colors=RATIO_COLOR)

    ax_alpha.set_ylabel(r"$\alpha$  [deg]")
    ax_cn.set_ylabel(r"$c_n$  [-]")
    ax_ct.set_ylabel(r"$c_t$  [-]")
    ax_ratio.set_ylabel(r"$c_t/c_n$  [-]")
    for ax in (ax_alpha, ax_cn, ax_ct, ax_ratio):
        ax.set_xlabel(r"$r/R$  [-]")

    ax_alpha.set_title(r"(a) local angle of attack $\alpha$", fontsize=11)
    ax_cn.set_title(r"(b) normal/thrust coefficient $c_n$ and $c_n/c_n^{BEM}$",
                    fontsize=11)
    ax_ct.set_title(r"(c) tangential/torque coefficient $c_t$ and "
                    r"$c_t/c_t^{BEM}$", fontsize=11)
    ax_ratio.set_title(r"(d) torque-to-thrust ratio $c_t/c_n$ "
                       "(normalisation-free)", fontsize=11)
    ax_alpha.set_ylim(bottom=0.0)

    # Panel (a): per-model mean BEM offset over the annotation span.
    lines = []
    for label, _, color, _ in MODELS:
        profile = next((p for p in profiles if p["label"] == label), None)
        if profile is None:
            continue
        rr = profile["rr"]
        mask = (rr >= ANNOTATE_LO) & (rr <= ANNOTATE_HI)
        d_alpha = profile["alpha"][mask] - bem_at(BEM_ALPHA_DEG, rr)[mask]
        lines.append((label, color, d_alpha.mean(), d_alpha.min(),
                      d_alpha.max()))
    text = "\n".join(
        f"{label}: mean {mean:+.2f} deg  "
        f"({lo:+.2f} .. {hi:+.2f})"
        for label, _, mean, lo, hi in lines
    )
    ax_alpha.annotate(
        f"$\\Delta\\alpha$ vs BEM, r/R in [{ANNOTATE_LO:g}, {ANNOTATE_HI:g}]\n"
        + text,
        xy=(0.03, 0.72), xycoords="axes fraction", fontsize=8.5,
        bbox={"boxstyle": "round", "fc": "white", "ec": "0.6", "alpha": 0.9},
    )

    handles = model_handles + [bem_handle, ratio_handle]
    fig.legend(handles=handles, loc="upper center", ncol=len(handles),
               fontsize=9.5, framealpha=0.9, bbox_to_anchor=(0.5, 0.955))

    fig.suptitle(
        "IEA 15-240-RWT spanwise comparison: ALM vs ASM vs ASM-mesh vs "
        "CCBlade BEM\n"
        f"V = {V_RATED:g} m/s   {RPM_RATED:g} rpm   pitch 0$^\\circ$   "
        f"uniform inflow   precone {PRECONE_DEG:g}$^\\circ$   "
        f"TSR {TSR_RATED:g}",
        fontsize=13, y=0.995,
    )

    caption = []
    for profile in profiles:
        t_start, t_end, period = profile["window"]
        caption.append(
            f"{profile['label']} [{t_start:.1f}, {t_end:.1f}] s "
            f"({(t_end - t_start) / period:.1f} rev, "
            f"{profile['revs_to_end']:.1f} rev to date)"
        )
    fig.text(
        0.5, 0.013,
        "Windows: last 2 revs per run (same rule, run-specific times).  "
        + "   ".join(caption) + ".\n"
        "No extrapolation: each model is plotted only where its live "
        "transient data exists (the ASM-mesh run is the shortest, ~4 rev).",
        ha="center", va="bottom", fontsize=8, color="0.3",
    )

    fig.subplots_adjust(left=0.070, right=0.925, top=0.895, bottom=0.085)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revs", type=float, default=DEFAULT_REVS)
    parser.add_argument("--rpm", type=float, default=RPM_RATED)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    profiles = []
    for label, run_dir, _, _ in MODELS:
        try:
            profiles.append(load_profile(label, run_dir, args.revs, args.rpm))
        except FileNotFoundError as error:
            print(f"warning: {label}: {error}")

    if not profiles:
        print("error: none of the three runs provided data", flush=True)
        return 1

    print_model_report(profiles)
    print_station_table(profiles)
    print_offsets(profiles)
    make_figure(profiles, args.out)
    print(f"\nwrote {args.out.resolve()} ({args.out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
