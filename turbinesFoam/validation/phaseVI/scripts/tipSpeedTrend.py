#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Speed trend of the r/R 0.95 c_n error on Phase VI Sequence S (odd T13).

Offline, read-only. The c_n error at r/R 0.95 shared by ALM, OLAF-DP and AeroDyn BEM
grows with wind speed (S5..S8) while the Trigaux virtual-camber factor F_Cl is
load independent. This tool tabulates, per speed and station (0.63, 0.80, 0.95), the
quantities needed to test the candidate explanations:

  (a) local Reynolds number of the ALM elements and the Re sensitivity of the S809 polar
      at the tip angle of attack (OSU multi-Re set, TP-442-7817, Re 0.75..1.5e6; the case
      runs `liftReCorrExp = 0`, so the ALM uses the Re 1e6 polar unscaled);
  (b) tip angle of attack (ALM element mean, AeroDyn station) and where it sits on the
      OSU Re 1e6 total polar (lift slope, drag);
  (c) measurement: committed c_n, QNORM, per-revolution repeatability and tap-integration
      sensitivity (`analysis/tap-integration/summary_all.csv`);
  (d) measured chordwise Cp from the raw taps (optional, `--records`), reduced to shape
      indices (suction peak, plateau, recovery);
  (e) model c_n errors at the three stations, and the correction fraction
      1 - c_n,exp / c_n,model each model would need.

Usage:
    python3 -I tipSpeedTrend.py --runs-dir <runs> --out analysis/tip-speed-trend
    python3 -I tipSpeedTrend.py --runs-dir <runs> --records s0500000.parquet ... --out DIR

Exit status: 0 on success, 2 on an input error.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

POLAR = ROOT / "data" / "polars" / "S809_OSU_Re1M_total.dat"
POLAR_DUT = ROOT / "data" / "polars" / "S809_DUT_Re1M_total.dat"
MULTI_RE = ROOT / "data" / "polars" / "S809_multiRe.dat"
TAP_SUMMARY = ROOT / "analysis" / "tap-integration" / "summary_all.csv"
EXPERIMENT = ROOT / "data" / "experiment" / "uae6-archive"
CONFIG = ROOT / "config" / "case.yaml"
RADIUS_M = 5.029
STATIONS = (0.63, 0.80, 0.95)
SPEEDS = (5, 6, 7, 8)
RE_REF = 1.0e6
NU = 1.46e-5  # m^2/s, informational cross-check only; the ALM Re column is authoritative
LINEAR_ALPHA_MAX = 8.0  # deg: OSU S809 lift is linear up to about here


class InputError(Exception):
    """Unusable input; the CLI maps it to exit status 2."""


# ------------------------------------------------------------------ polars

def read_polar(path: Path = POLAR):
    """[(alpha, cl, cd)] from a `(alpha cl cd cm)` OpenFOAM table; comments ignored."""
    rows = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise InputError(f"{path}: {error}") from error
    for line in text.splitlines():
        if line.lstrip().startswith("//"):
            continue
        m = re.match(r"\s*\(\s*([^()]+)\)\s*$", line)
        if not m:
            continue
        parts = m.group(1).split()
        if len(parts) >= 3:
            rows.append((float(parts[0]), float(parts[1]), float(parts[2])))
    if len(rows) < 3:
        raise InputError(f"{path}: no polar rows")
    rows.sort()
    return rows


def _lerp(rows, x, col):
    """Linear interpolation of column `col` of rows sorted on column 0."""
    if x <= rows[0][0]:
        return rows[0][col]
    if x >= rows[-1][0]:
        return rows[-1][col]
    lo, hi = 0, len(rows) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if rows[mid][0] <= x:
            lo = mid
        else:
            hi = mid
    t = (x - rows[lo][0]) / (rows[hi][0] - rows[lo][0])
    return rows[lo][col] + t * (rows[hi][col] - rows[lo][col])


def polar_state(polar, alpha, half_width=1.0):
    """cl, cd and the local lift slope [1/deg] (central difference) at alpha."""
    cl = _lerp(polar, alpha, 1)
    cd = _lerp(polar, alpha, 2)
    slope = (_lerp(polar, alpha + half_width, 1) - _lerp(polar, alpha - half_width, 1)) / (2 * half_width)
    return {"cl": cl, "cd": cd, "slope_per_deg": slope}


def read_multi_re(path: Path = MULTI_RE):
    """(re_list, [(alpha, cl_1, ..., cl_n)]) from the OpenFOAM multiRe table."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise InputError(f"{path}: {error}") from error
    text = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("//"))
    m = re.search(r"ReList\s*\(([^)]*)\)", text)
    if not m:
        raise InputError(f"{path}: no ReList")
    re_list = [float(v) for v in m.group(1).split()]
    block = re.search(r"clData\s*\((.*?)\n\)\s*;", text, re.S)
    if not block:
        raise InputError(f"{path}: no clData")
    rows = []
    for line in block.group(1).splitlines():
        m = re.match(r"\s*\(\s*([^()]+)\)\s*$", line)
        if m:
            vals = [float(v) for v in m.group(1).split()]
            if len(vals) == len(re_list) + 1:
                rows.append(tuple(vals))
    if not rows:
        raise InputError(f"{path}: empty clData")
    rows.sort()
    return re_list, rows


def cl_vs_re(multi, alpha):
    """([Re], [cl]) at alpha from the multi-Re table (linear in alpha)."""
    re_list, rows = multi
    return re_list, [_lerp(rows, alpha, 1 + i) for i in range(len(re_list))]


def re_sensitivity(multi, alpha, re_tip, re_ref=RE_REF):
    """Lift change from Re = re_ref to re_tip at alpha, from the OSU multi-Re set.

    Fits cl = a + b ln(Re) by least squares over the tabulated levels and evaluates the
    ratio at re_tip against re_ref. `extrapolated` is True when re_tip lies outside the
    tabulated Re range. Returns dcl_dlnRe, cl_ref (fit), cl_tip (fit), ratio-1 in percent,
    and the raw cl at the tabulated levels.
    """
    re_list, cls = cl_vs_re(multi, alpha)
    xs = [math.log(r) for r in re_list]
    n = len(xs)
    mx, my = sum(xs) / n, sum(cls) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, cls)) / sxx
    a = my - b * mx
    cl_ref = a + b * math.log(re_ref)
    cl_tip = a + b * math.log(re_tip)
    return {
        "dcl_dlnRe": b,
        "cl_ref_fit": cl_ref,
        "cl_tip_fit": cl_tip,
        "delta_cl_pct": 100.0 * (cl_tip - cl_ref) / cl_ref if cl_ref else float("nan"),
        "extrapolated": not (min(re_list) <= re_tip <= max(re_list)),
        "levels": dict(zip(re_list, cls)),
    }


# ------------------------------------------------------------ model inputs

def station_means(element_rows, window, keys):
    """Window means of `keys` and of derived cn from one element's rows."""
    start, end = window
    sel = [r for r in element_rows if start <= float(r["time"]) <= end]
    if not sel:
        return None
    out = {k: sum(float(r[k]) for r in sel) / len(sel) for k in keys}
    cn = []
    for r in sel:
        a = math.radians(float(r["alpha_deg"]))
        cn.append(float(r["cl"]) * math.cos(a) + float(r["cd"]) * math.sin(a))
    out["cn"] = sum(cn) / len(cn)
    return out


def interpolate_profile(profile, x):
    """Linear interpolation in r/R of [(r_over_R, {key: value})]; clamps are errors."""
    profile = sorted(profile, key=lambda p: p[0])
    if not profile[0][0] <= x <= profile[-1][0]:
        raise InputError(f"station {x} outside the element range")
    for (x0, v0), (x1, v1) in zip(profile, profile[1:]):
        if x0 <= x <= x1:
            t = 0.0 if x1 == x0 else (x - x0) / (x1 - x0)
            return {k: v0[k] + t * (v1[k] - v0[k]) for k in v0}
    raise InputError(f"station {x} not bracketed")


def alm_states(run_dir: Path, cfg, speed, sequence, stations):
    """{station: {Re, alpha_deg, cl, cd, rel_vel_mag, cn}} window means of an ALM run."""
    import comparePhaseVI as cp

    element_dir = run_dir / cp.ELEMENT_DIR
    if not element_dir.is_dir():
        raise InputError(f"{element_dir}: not a directory")
    start, end, _ = cp.window_bounds(cfg, float(speed), sequence)
    keys = ("root_dist", "Re", "alpha_deg", "cl", "cd", "rel_vel_mag")
    profile = []
    for path, rows in cp.read_elements(element_dir):
        state = station_means(rows, (start, end), keys)
        if state is None:
            raise InputError(f"{path}: no samples in the averaging window")
        r = cp.r_over_r_from_root_dist(state.pop("root_dist"), RADIUS_M)
        profile.append((r, state))
    return {s: interpolate_profile(profile, s) for s in stations}


def aerodyn_states(metrics_path: Path, stations):
    import json

    try:
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise InputError(f"{metrics_path}: {error}") from error
    out = {}
    for s in stations:
        e = data["stations"].get(f"{s:.2f}")
        if e is None:
            raise InputError(f"{metrics_path}: no station {s:.2f}")
        out[s] = {"cn": e["cn"], "alpha_deg": e["alpha_deg"], "cn_exp_file": e["cn_exp"]}
    return out


def error_pct(value, reference):
    return 100.0 * (value - reference) / reference


def required_correction(cn_model, cn_exp):
    """Fraction F such that cn_model (1 - F) = cn_exp."""
    return 1.0 - cn_exp / cn_model


# ------------------------------------------------------------- measurement

def read_experiment(path: Path, sequence="S"):
    """{(speed, r/R): {cn, qnorm}} from sequence_<S>_spanwise.csv."""
    out = {}
    try:
        with path.open(encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                out[(int(float(row["wind_speed_m_s"])), round(float(row["r_over_R"]), 2))] = {
                    "cn": float(row["cn"]), "qnorm": float(row["qnorm_pa"])}
    except (OSError, KeyError, ValueError) as error:
        raise InputError(f"{path}: {error}") from error
    return out


def read_tap_summary(path: Path = TAP_SUMMARY):
    """{(record, station_percent): row} of the T6 tap-integration summary."""
    out = {}
    try:
        with path.open(encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                out[(row["record"], int(row["station"]))] = row
    except (OSError, KeyError, ValueError) as error:
        raise InputError(f"{path}: {error}") from error
    return out


# -------------------------------------------------------------- Cp shape

def cp_shape(x_taps, split, cp):
    """Shape indices of one chordwise Cp distribution.

    Taps run TE -> upper -> LE (index `split`) -> lower -> TE. Returns the suction peak
    (min Cp on the upper surface) and its x/c, the Cp plateau extent (consecutive
    upper-surface taps downstream of the peak with |dCp/d(x/c)| < 1 per unit chord), the
    pressure-recovery gradient between 0.2c and 0.8c of the upper surface, the
    c_n-normalised suction peak, and the trapezoid closed-contour integral.
    """
    n = len(cp)
    upper = [(x_taps[i], cp[i]) for i in range(0, split + 1)]  # TE -> LE
    upper.sort()  # by x ascending (LE -> TE)
    peak_x, peak_cp = min(upper, key=lambda t: t[1])
    # recovery: slope of Cp between x = 0.2 and 0.8 by linear interpolation
    def at(xq):
        for (x0, c0), (x1, c1) in zip(upper, upper[1:]):
            if x0 <= xq <= x1:
                return c0 if x1 == x0 else c0 + (xq - x0) / (x1 - x0) * (c1 - c0)
        return upper[-1][1]
    recovery = (at(0.8) - at(0.2)) / 0.6
    plateau = 0.0
    prev = None
    for x, c in upper:
        if x < peak_x:
            prev = (x, c)
            continue
        if prev is not None and x > prev[0]:
            if abs((c - prev[1]) / (x - prev[0])) < 1.0:
                plateau += x - prev[0]
        prev = (x, c)
    cn = 0.0
    contour = [(x_taps[i], cp[i]) for i in range(n)]
    for (x0, c0), (x1, c1) in zip(contour, contour[1:]):
        cn += 0.5 * (c0 + c1) * (x1 - x0)
    cn += 0.5 * (contour[-1][1] + contour[0][1]) * (contour[0][0] - contour[-1][0])
    return {
        "peak_cp": peak_cp, "peak_x": peak_x, "plateau_x": plateau,
        "recovery_slope": recovery,
        "cp_at_0.20": at(0.2), "cp_at_0.50": at(0.5), "cp_at_0.80": at(0.8),
        "cn_trap": cn,
        "peak_over_cn": peak_cp / cn if cn else float("nan"),
        "cp_at_0.02": at(0.02),
        "le_peak_ratio": at(0.02) / at(0.2) if at(0.2) else float("nan"),
    }


def mean_cp_shape(record: Path, station_percent: int):
    """Time-mean Cp per tap (raw, read-only parquet) and its shape indices."""
    import tapIntegrationSensitivity as tap
    import numpy as np

    stations = (station_percent,)
    table, tap_cols = tap.load_record(record, stations)
    taps = tap_cols[station_percent]
    nums = [t for t, _ in taps]
    x = [tap.TAP_X[t] for t in nums]
    split = nums.index(tap.LE_TAP)
    cp = [float(np.mean(table[col].to_numpy(float))) for _, col in taps]
    shape = cp_shape(x, split, cp)
    shape["cn_record"] = float(np.mean(table[f"CN{station_percent}"].to_numpy(float)))
    return nums, x, cp, shape


def polar_source_ratio(polar_a, polar_b, alpha):
    """cl(polar_b) / cl(polar_a) at alpha (e.g. DUT over OSU, both Re 1e6)."""
    return _lerp(polar_b, alpha, 1) / _lerp(polar_a, alpha, 1)


def alpha_equivalent(cn_model, cn_exp, slope_per_deg, alpha_deg, min_slope=0.08):
    """Angle-of-attack offset [deg] that would close the c_n gap on a linear polar.

    NaN where the local lift slope is below `min_slope` per degree (non-linear range).
    """
    if slope_per_deg < min_slope:
        return float("nan")
    return (cn_exp - cn_model) / (slope_per_deg * math.cos(math.radians(alpha_deg)))


def tip_excess(err_tip, err_in_a, err_in_b):
    """Tip error minus the mean of the two inboard errors (same model and speed), in pp."""
    return err_tip - 0.5 * (err_in_a + err_in_b)


def spearman(xs, ys):
    """Spearman rank correlation (average ranks for ties)."""
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = 0.5 * (i + j) + 1.0
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def shape_vs_alpha(shape_rows, trend_rows, key="le_peak_ratio"):
    """Join Cp-shape rows with the ALM alpha of the same speed/station; add the rank correlation.

    A shape index that is a single monotone function of the local angle of attack over all
    speeds and stations carries no speed-specific (transition/separation) signature.
    """
    alpha = {(r["speed"], int(round(float(r["r_over_R"]) * 100))): float(r["alm_alpha_deg"]) for r in trend_rows}
    joined = [{"speed": r["speed"], "station": r["station"], "alm_alpha_deg": alpha[(r["speed"], r["station"])],
               key: r[key]} for r in shape_rows if (r["speed"], r["station"]) in alpha]
    rho = spearman([j["alm_alpha_deg"] for j in joined], [j[key] for j in joined]) if len(joined) > 2 else float("nan")
    return joined, rho


def predicted_error_with_polar(err_pct, cl_ratio):
    """c_n error [%] if the whole c_n scaled by the polar-source lift ratio (cd neglected)."""
    return 100.0 * ((1.0 + err_pct / 100.0) * cl_ratio - 1.0)


# ------------------------------------------------------------------ main

def cells(runs: Path):
    for speed in SPEEDS:
        yield speed


def run_dirs(runs: Path, speed):
    return {
        "alm": runs / f"alm-U{speed}-coarse-seqS-var-tip-pitch-dag-sorensen-total",
        "olaf-dp": runs / f"aerodyn-olaf-dp-SU{speed}" / "metrics.json",
        "bem": runs / f"aerodyn-bem-SU{speed}" / "metrics.json",
    }


WINDOWS = {5: (16, 24), 6: (16, 24), 7: (4, 12), 8: (4, 12)}  # v13-adoption-asm L26

TABLE_COLUMNS = [
    "speed", "r_over_R", "cn_exp", "qnorm_pa", "rev_std_pct", "pchip_delta_pct", "loo_rms_pct",
    "alm_Re", "re_ratio_to_1M", "alm_alpha_deg", "bem_alpha_deg", "olaf_alpha_deg",
    "alm_cl", "alm_cd", "polar_slope_per_deg", "polar_cl_1M_at_alm_alpha",
    "re_dcl_pct_tip_vs_1M", "re_extrapolated",
    "alm_cn", "olaf_cn", "bem_cn",
    "alm_err_pct", "olaf_err_pct", "bem_err_pct",
    "alm_F_req", "olaf_F_req", "bem_F_req",
    "dut_over_osu_cl", "alm_err_if_dut_pct", "alm_alpha_equiv_deg", "bem_alpha_equiv_deg",
    "alm_tip_excess_pp", "olaf_tip_excess_pp", "bem_tip_excess_pp",
]

VARIANT_COLUMNS = ["speed", "r_over_R", "cn_exp", "osu_cn", "osu_err_pct", "dut_cn", "dut_err_pct",
                   "dut_alpha_deg", "dut_over_osu_cn", "predicted_dut_err_pct", "F_Cl", "osu_err_FCl_pct", "dut_err_FCl_pct"]


def build_rows(runs: Path, polar, multi, experiment, taps, cfg, polar_dut=None):
    import comparePhaseVI as cp

    polar_dut = polar_dut or read_polar(POLAR_DUT)
    rows = []
    for speed in SPEEDS:
        paths = run_dirs(runs, speed)
        cfg["solver"]["discard_revolutions"], cfg["solver"]["end_revolutions"] = WINDOWS[speed]
        alm = alm_states(paths["alm"], cfg, speed, "S", STATIONS)
        olaf = aerodyn_states(paths["olaf-dp"], STATIONS)
        bem = aerodyn_states(paths["bem"], STATIONS)
        record = f"s{speed:02d}00000"
        for s in STATIONS:
            exp = experiment[(speed, round(s, 2))]
            tap_row = taps.get((record, int(round(s * 100))), {})
            a = alm[s]
            sens = re_sensitivity(multi, a["alpha_deg"], a["Re"])
            ps = polar_state(polar, a["alpha_deg"])
            rows.append({
                "speed": speed, "r_over_R": f"{s:.2f}", "cn_exp": exp["cn"], "qnorm_pa": exp["qnorm"],
                "rev_std_pct": tap_row.get("rev_std_pct", ""),
                "pchip_delta_pct": tap_row.get("pchip_delta_pct", ""),
                "loo_rms_pct": tap_row.get("loo_rms_pct", ""),
                "alm_Re": a["Re"], "re_ratio_to_1M": a["Re"] / RE_REF,
                "alm_alpha_deg": a["alpha_deg"], "bem_alpha_deg": bem[s]["alpha_deg"],
                "olaf_alpha_deg": olaf[s]["alpha_deg"],
                "alm_cl": a["cl"], "alm_cd": a["cd"],
                "polar_slope_per_deg": ps["slope_per_deg"], "polar_cl_1M_at_alm_alpha": ps["cl"],
                "re_dcl_pct_tip_vs_1M": sens["delta_cl_pct"], "re_extrapolated": sens["extrapolated"],
                "alm_cn": a["cn"], "olaf_cn": olaf[s]["cn"], "bem_cn": bem[s]["cn"],
                "alm_err_pct": error_pct(a["cn"], exp["cn"]),
                "olaf_err_pct": error_pct(olaf[s]["cn"], exp["cn"]),
                "bem_err_pct": error_pct(bem[s]["cn"], exp["cn"]),
                "alm_F_req": required_correction(a["cn"], exp["cn"]),
                "olaf_F_req": required_correction(olaf[s]["cn"], exp["cn"]),
                "bem_F_req": required_correction(bem[s]["cn"], exp["cn"]),
                "dut_over_osu_cl": polar_source_ratio(polar, polar_dut, a["alpha_deg"]),
                "alm_err_if_dut_pct": predicted_error_with_polar(
                    error_pct(a["cn"], exp["cn"]), polar_source_ratio(polar, polar_dut, a["alpha_deg"])),
                "alm_alpha_equiv_deg": alpha_equivalent(a["cn"], exp["cn"], ps["slope_per_deg"], a["alpha_deg"]),
                "bem_alpha_equiv_deg": alpha_equivalent(bem[s]["cn"], exp["cn"], ps["slope_per_deg"], bem[s]["alpha_deg"]),
            })
    by = {(r["speed"], r["r_over_R"]): r for r in rows}
    for r in rows:
        for m in ("alm", "olaf", "bem"):
            r[f"{m}_tip_excess_pp"] = (
                tip_excess(r[f"{m}_err_pct"], by[(r["speed"], "0.63")][f"{m}_err_pct"],
                           by[(r["speed"], "0.80")][f"{m}_err_pct"]) if r["r_over_R"] == "0.95" else "")
    return rows


def variant_rows(runs: Path, cfg, experiment, base_rows, label="var-tip-pitch-dag-sorensen-dut"):
    """ALM runs of the DUT-polar variant versus the OSU run, where the variant exists."""
    import applyNearTipFunctions as nt

    table, blade = nt.read_table(), nt.read_blade()
    by = {(r["speed"], r["r_over_R"]): r for r in base_rows}
    out = []
    for speed in SPEEDS:
        d = runs / f"alm-U{speed}-coarse-seqS-{label}"
        if not d.is_dir():
            continue
        cfg["solver"]["discard_revolutions"], cfg["solver"]["end_revolutions"] = WINDOWS[speed]
        states = alm_states(d, cfg, speed, "S", STATIONS)
        for s in STATIONS:
            b = by[(speed, f"{s:.2f}")]
            exp = experiment[(speed, round(s, 2))]["cn"]
            try:  # c_n scaled by (1 - F_Cl): within 0.05 pp of scaling the lift part (T10 REPORT)
                fcl = nt.functions_at(table, nt.effective_distance(blade, s * RADIUS_M, RADIUS_M), "3D", 0.25)[1]
            except nt.InputError:
                fcl = 0.0  # d_tip/c beyond the tabulated range: no near-tip correction
            out.append({
                "speed": speed, "r_over_R": f"{s:.2f}", "cn_exp": exp, "osu_cn": b["alm_cn"],
                "osu_err_pct": b["alm_err_pct"], "dut_cn": states[s]["cn"],
                "dut_err_pct": error_pct(states[s]["cn"], exp), "dut_alpha_deg": states[s]["alpha_deg"],
                "dut_over_osu_cn": states[s]["cn"] / b["alm_cn"],
                "predicted_dut_err_pct": b["alm_err_if_dut_pct"],
                "F_Cl": fcl,
                "osu_err_FCl_pct": error_pct(b["alm_cn"] * (1.0 - fcl), exp),
                "dut_err_FCl_pct": error_pct(states[s]["cn"] * (1.0 - fcl), exp),
            })
    return out


def tip_ratio(rows, key):
    """{speed: value(0.95) / value(0.80)} for a numeric column."""
    by = {(r["speed"], r["r_over_R"]): float(r[key]) for r in rows}
    return {s: by[(s, "0.95")] / by[(s, "0.80")] for s in SPEEDS if (s, "0.95") in by and (s, "0.80") in by}


def write_csv(path: Path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        w = csv.DictWriter(stream, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.5g}" if isinstance(v, float) else v) for k, v in r.items()})


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runs-dir", required=True, help="directory holding alm-U*-... and aerodyn-*-SU* runs")
    p.add_argument("--out", required=True, help="output directory")
    p.add_argument("--records", nargs="*", default=[], help="raw UAE6 z18 parquet records for Cp shape (read-only)")
    p.add_argument("--stations-cp", nargs="*", type=int, default=[63, 80, 95])
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        import comparePhaseVI as cp

        cfg = cp.load_config(CONFIG)
        polar, multi = read_polar(), read_multi_re()
        experiment = read_experiment(EXPERIMENT / "sequence_S_spanwise.csv")
        taps = read_tap_summary()
        rows = build_rows(Path(args.runs_dir), polar, multi, experiment, taps, cfg)
        out = Path(args.out)
        write_csv(out / "speed_trend.csv", TABLE_COLUMNS, rows)
        variants = variant_rows(Path(args.runs_dir), cfg, experiment, rows)
        if variants:
            write_csv(out / "alm_dut_variant.csv", VARIANT_COLUMNS, variants)
        shape_rows = []
        for rec in args.records:
            m = re.search(r"s(\d\d)00000", Path(rec).name)
            if not m:
                raise InputError(f"{rec}: not an s<NN>00000 record")
            for st in args.stations_cp:
                nums, x, cpv, shape = mean_cp_shape(Path(rec), st)
                shape_rows.append({"speed": int(m.group(1)), "station": st, **shape})
                write_csv(out / f"cp_s{int(m.group(1)):02d}_{st}.csv", ["tap", "x_over_c", "cp"],
                          [{"tap": t, "x_over_c": xx, "cp": c} for t, xx, c in zip(nums, x, cpv)])
        if shape_rows:
            write_csv(out / "cp_shape.csv", list(shape_rows[0]), shape_rows)
            joined, rho = shape_vs_alpha(shape_rows, rows)
            write_csv(out / "cp_vs_alpha.csv", list(joined[0]), joined)
            print(f"Spearman rho(le_peak_ratio, ALM alpha) over {len(joined)} cells: {rho:.3f}")
    except (InputError, FileNotFoundError) as error:
        print(f"tipSpeedTrend: {error}", file=sys.stderr)
        return 2
    print(f"wrote {out}/speed_trend.csv ({len(rows)} rows)" + (f", cp_shape.csv ({len(shape_rows)} rows)" if shape_rows else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
