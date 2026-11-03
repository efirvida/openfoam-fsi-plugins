#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sensitivity of the UAE6 sectional C_N to the pressure-tap integration.

The experimental reference at r/R = 0.95 is an integral of 22 tap pressures
with 20-24 % chord gaps on the suction side (Hand et al. 2001, NREL/TP-500-29955,
p. 51, Eq. 8-9: trapezoid of the average pressure between adjacent taps,
projected on the chord, pressures normalised by the stagnation pressure QNORM).
For each primary station of one raw record this script

  1. time-averages C_N reproduced with the NREL trapezoid and reports the
     per-revolution standard deviation (repeatability);
  2. compares it with the record's own CNxx channel and with the committed
     `sequence_S_spanwise.csv` value;
  3. re-integrates through the same taps with a PCHIP per surface in chord
     coordinate, a periodic cubic spline in contour arc length, and a
     leave-one-tap-out sweep of the trapezoid.

Every method is linear in the tap values, so each is reduced to a weight vector
w (C_N = w . Cp) and applied to all samples at once.

Contour sign convention: TE -> upper surface -> LE -> lower surface -> TE, so
C_N = closed-contour integral of Cp dx (suction on the upper surface gives C_N > 0).

Usage:
    python3 -I tapIntegrationSensitivity.py RECORD.parquet [RECORD2.parquet ...] \\
        [--stations 30 47 63 80 95] [--out DIR]

Raw data is read-only; pass paths as arguments.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import numpy as np
from scipy.interpolate import CubicSpline, PchipInterpolator

HERE = Path(__file__).resolve().parent
PHASE_VI = HERE.parent
DEFAULT_EXPERIMENT = PHASE_VI / "data" / "experiment" / "sequence_S_spanwise.csv"
DEFAULT_GEOMETRY = PHASE_VI / "data" / "s809" / "s809_somers_nlr.csv"
DEFAULT_OUT = PHASE_VI / "analysis" / "tap-integration"
DEFAULT_STATIONS = (30, 47, 63, 80, 95)
STATION_TO_R = {30: 0.30, 47: 0.47, 63: 0.63, 80: 0.80, 95: 0.95}

# Hand et al. 2001, Table 7: tap number -> x/c (surface follows from the number).
TAP_X = {
    1: 1.0, 4: 0.80, 6: 0.68, 8: 0.56, 11: 0.36, 13: 0.20, 15: 0.10, 17: 0.06,
    18: 0.04, 19: 0.02, 20: 0.01, 21: 0.005, 22: 0.0, 23: 0.005, 24: 0.01,
    25: 0.02, 27: 0.06, 30: 0.14, 32: 0.28, 34: 0.44, 36: 0.68, 38: 0.92,
}
LE_TAP = 22
TE_TAP = 1


class TapError(Exception):
    """Missing or unusable tap data."""


# ---------------------------------------------------------------- integrators
def trapezoid_weights(x):
    """Weights w with C_N = w . Cp for the NREL closed-contour trapezoid.

    `x` is the chord position of the taps in contour order starting at the TE;
    the contour closes from the last tap back to the first.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    w = np.zeros(n)
    for i in range(n):
        j = (i + 1) % n
        dx = x[j] - x[i]
        w[i] += 0.5 * dx
        w[j] += 0.5 * dx
    return w


def _basis_weights(integrate, n):
    """Weights of a linear functional given as `integrate(cp_vector) -> scalar`."""
    return np.array([integrate(np.eye(n)[k]) for k in range(n)])


def pchip_weights(x, split):
    """PCHIP per surface in chord coordinate; `split` = index of the LE tap.

    Upper surface: taps 0..split (TE .. LE); lower: taps split..n-1 plus the TE
    tap again (closure). C_N = integral_0^1 (Cp_lower - Cp_upper) dx.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)

    def integrate(cp):
        xu, cu = x[: split + 1][::-1], cp[: split + 1][::-1]
        xl = np.append(x[split:], x[0])
        cl = np.append(cp[split:], cp[0])
        upper = PchipInterpolator(xu, cu).integrate(xu[0], xu[-1])
        lower = PchipInterpolator(xl, cl).integrate(xl[0], xl[-1])
        return lower - upper

    return _basis_weights(integrate, n)


def contour_from_geometry(rows, points=1500):
    """Dense TE -> upper -> LE -> lower -> TE contour (x, z, s, split index).

    `rows` = list of (surface, x/c, z/c). Each surface is interpolated by PCHIP
    in sqrt(x) so the leading-edge radius is resolved.
    """
    surfaces = {}
    for surface, xc, zc in rows:
        surfaces.setdefault(surface, []).append((xc, zc))
    out = {}
    for name in ("upper", "lower"):
        pts = sorted(set(surfaces[name]))
        xs = np.array([0.0] + [p[0] for p in pts if p[0] > 0.0])
        zs = np.array([0.0] + [p[1] for p in pts if p[0] > 0.0])
        if xs[-1] < 1.0:
            xs, zs = np.append(xs, 1.0), np.append(zs, 0.0)
        out[name] = PchipInterpolator(np.sqrt(xs), zs)
    u = np.linspace(0.0, 1.0, points)
    xd = 0.5 * (1.0 - np.cos(np.pi * u))  # clustered at LE and TE
    zu, zl = out["upper"](np.sqrt(xd)), out["lower"](np.sqrt(xd))
    x = np.concatenate([xd[::-1], xd[1:]])
    z = np.concatenate([zu[::-1], zl[1:]])
    s = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(z)))])
    return x, z, s, points - 1


def tap_arclength(x_taps, split, contour):
    """Arc-length of each tap on the dense contour (monotone interpolation)."""
    x, _, s, le = contour
    su, xu = s[: le + 1][::-1], x[: le + 1][::-1]  # LE -> TE on the upper surface
    sl, xl = s[le:], x[le:]
    s_taps = np.empty(len(x_taps))
    for i, xt in enumerate(x_taps):
        if i <= split:
            s_taps[i] = np.interp(xt, xu, su)
        else:
            s_taps[i] = np.interp(xt, xl, sl)
    s_taps[0] = 0.0  # TE tap, start of the contour
    return s_taps


def spline_weights(x_taps, split, contour):
    """Periodic cubic spline of Cp in contour arc length; C_N = closed integral Cp dx."""
    x, _, s, _ = contour
    s_taps = np.append(tap_arclength(x_taps, split, contour), s[-1])

    def integrate(cp):
        spl = CubicSpline(s_taps, np.append(cp, cp[0]), bc_type="periodic")
        c = spl(s)
        return float(np.sum(0.5 * (c[1:] + c[:-1]) * np.diff(x)))

    return _basis_weights(integrate, len(x_taps))


def leave_one_out(x, split, drop_indices):
    """Trapezoid weights (padded to full length) with each tap in `drop_indices` removed."""
    x = np.asarray(x, dtype=float)
    results = []
    for k in drop_indices:
        keep = [i for i in range(len(x)) if i != k]
        w = np.zeros(len(x))
        w[keep] = trapezoid_weights(x[keep])
        results.append((k, w))
    return results


# ------------------------------------------------------------------- I/O
def read_geometry(path):
    rows = []
    with Path(path).open(newline="") as stream:
        lines = [ln for ln in stream if not ln.startswith("#")]
    for rec in csv.DictReader(lines):
        rows.append((rec["surface"], float(rec["x_over_c"]), float(rec["z_over_c"])))
    return rows


def read_committed(path):
    """{(file_name, r_over_R): cn}."""
    out = {}
    with Path(path).open(newline="") as stream:
        for rec in csv.DictReader(stream):
            out[(rec["file_name"], round(float(rec["r_over_R"]), 2))] = float(rec["cn"])
    return out


def station_taps(columns, station):
    """[(tap_number, column)] sorted in contour order; raises TapError when absent."""
    found = {}
    for name in columns:
        if len(name) == 8 and name[0] == "P" and name[1:3].isdigit() and name[3:5].isdigit():
            if int(name[3:5]) == station and int(name[1:3]) in TAP_X:
                found[int(name[1:3])] = name
    missing = sorted(set(TAP_X) - set(found))
    if not found or missing:
        raise TapError(f"station {station}: missing taps {missing or sorted(TAP_X)}")
    return sorted(found.items())


def load_record(path, stations):
    import pyarrow.parquet as pq

    schema = pq.read_schema(path).names
    need = {"CYCLECNT"}
    tap_cols = {}
    for st in stations:
        tap_cols[st] = station_taps(schema, st)
        need.update(col for _, col in tap_cols[st])
        for chan in (f"QNORM{st}", f"CN{st}"):
            if chan not in schema:
                raise TapError(f"station {st}: channel {chan} not in {Path(path).name}")
            need.add(chan)
    table = pq.read_table(path, columns=sorted(need)).to_pandas()
    return table, tap_cols


def revolution_blocks(cycle, min_fraction=0.8):
    """Index arrays of complete revolutions (partial first/last cycles dropped)."""
    cycle = np.asarray(cycle)
    ids, counts = np.unique(cycle, return_counts=True)
    keep = ids[counts >= min_fraction * np.median(counts)]
    return [np.flatnonzero(cycle == i) for i in keep]


# --------------------------------------------------------------- analysis
def analyse_station(table, taps, station, stem, committed, contour, divide_by_qnorm=False):
    nums = [t for t, _ in taps]
    x = np.array([TAP_X[t] for t in nums])
    split = nums.index(LE_TAP)
    q = table[f"QNORM{station}"].to_numpy(float)
    p = np.column_stack([table[c].to_numpy(float) for _, c in taps])
    good = np.isfinite(p).all(axis=1) & np.isfinite(q) & (q > 0.0)
    # The archive's P channels already hold Cp = (p - p_static)/QNORM (Hand et al.
    # 2001, p. 31: "normalized pressure coefficients ... were stored in these
    # channels"); channels.csv labels them "Pascal" in error.
    cp = p[good] / q[good, None] if divide_by_qnorm else p[good]

    weights = {
        "nrel_trapezoid": trapezoid_weights(x),
        "pchip_chord": pchip_weights(x, split),
        "spline_arclength": spline_weights(x, split, contour),
    }
    cn_t = {name: cp @ w for name, w in weights.items()}
    mean = {name: float(v.mean()) for name, v in cn_t.items()}
    base = mean["nrel_trapezoid"]

    drops = [k for k, n in enumerate(nums) if n != TE_TAP]
    loo = []
    for k, w in leave_one_out(x, split, drops):
        loo.append((nums[k], float((cp @ w).mean())))
    dloo = np.array([100.0 * (v - base) / base for _, v in loo])
    worst = int(np.argmax(np.abs(dloo)))

    blocks = revolution_blocks(table["CYCLECNT"].to_numpy()[good])
    per_rev = np.array([cn_t["nrel_trapezoid"][b].mean() for b in blocks])

    record_cn = float(table[f"CN{station}"].to_numpy(float)[good].mean())
    committed_cn = committed.get((stem, STATION_TO_R.get(station, station / 100.0)), math.nan)

    summary = {
        "record": stem, "station": station, "n_samples": int(good.sum()), "n_revs": len(blocks),
        "cn_nrel_trapezoid": base, "cn_record_channel": record_cn, "cn_committed": committed_cn,
        "mismatch_vs_record_pct": 100.0 * (base - record_cn) / record_cn,
        "mismatch_vs_committed_pct": 100.0 * (base - committed_cn) / committed_cn if committed_cn == committed_cn else math.nan,
        "cn_pchip": mean["pchip_chord"], "cn_spline": mean["spline_arclength"],
        "pchip_delta_pct": 100.0 * (mean["pchip_chord"] - base) / base,
        "spline_delta_pct": 100.0 * (mean["spline_arclength"] - base) / base,
        "loo_max_abs_pct": float(abs(dloo[worst])), "loo_max_tap": loo[worst][0],
        "loo_rms_pct": float(np.sqrt(np.mean(dloo ** 2))),
        "rev_std": float(per_rev.std(ddof=1)) if len(per_rev) > 1 else math.nan,
    }
    summary["rev_std_pct"] = 100.0 * summary["rev_std"] / base if len(per_rev) > 1 else math.nan

    rows = [(station, "nrel_trapezoid", base, 0.0)]
    rows.append((station, "pchip_chord", mean["pchip_chord"], summary["pchip_delta_pct"]))
    rows.append((station, "spline_arclength", mean["spline_arclength"], summary["spline_delta_pct"]))
    rows.append((station, "loo_max", base * (1.0 + math.copysign(summary["loo_max_abs_pct"], dloo[worst]) / 100.0), float(dloo[worst])))
    rows.append((station, "loo_rms", math.nan, summary["loo_rms_pct"]))
    for (tap, v), d in zip(loo, dloo):
        rows.append((station, f"loo_drop_tap{tap}", v, float(d)))
    return summary, rows


SUMMARY_FIELDS = [
    "record", "station", "n_samples", "n_revs", "cn_nrel_trapezoid", "cn_record_channel", "cn_committed",
    "mismatch_vs_record_pct", "mismatch_vs_committed_pct", "cn_pchip", "pchip_delta_pct", "cn_spline",
    "spline_delta_pct", "loo_max_abs_pct", "loo_max_tap", "loo_rms_pct", "rev_std", "rev_std_pct",
]


def record_stem(path):
    name = Path(path).name
    stem = name[: -len(".parquet")] if name.endswith(".parquet") else name
    return stem.split(".")[-1] if stem.startswith("uae6.") else stem


def write_csv(path, header, rows):
    with Path(path).open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        for row in rows:
            writer.writerow([f"{v:.6g}" if isinstance(v, float) else v for v in row])


def print_table(stem, summaries):
    print(f"\n== {stem} ==")
    head = ("st", "NREL", "chan", "commit", "mm_chan%", "mm_comm%", "PCHIP%", "spline%", "LOOmax%", "tap", "LOOrms%", "rev_std%")
    print(" ".join(f"{h:>9}" for h in head))
    for s in summaries:
        vals = (s["station"], s["cn_nrel_trapezoid"], s["cn_record_channel"], s["cn_committed"],
                s["mismatch_vs_record_pct"], s["mismatch_vs_committed_pct"], s["pchip_delta_pct"],
                s["spline_delta_pct"], s["loo_max_abs_pct"], s["loo_max_tap"], s["loo_rms_pct"], s["rev_std_pct"])
        print(" ".join(f"{v:>9.4f}" if isinstance(v, float) else f"{v:>9}" for v in vals))


def run(records, stations, out_dir, experiment, geometry, divide_by_qnorm=False):
    committed = read_committed(experiment)
    contour = contour_from_geometry(read_geometry(geometry))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    all_summary = []
    for record in records:
        stem = record_stem(record)
        table, tap_cols = load_record(record, stations)
        summaries, long_rows = [], []
        for st in stations:
            summary, rows = analyse_station(table, tap_cols[st], st, stem, committed, contour, divide_by_qnorm)
            summaries.append(summary)
            long_rows += [(stem, *r) for r in rows]
        write_csv(out_dir / f"{stem}_methods.csv", ["record", "station", "method", "cn", "delta_vs_nrel_pct"], long_rows)
        write_csv(out_dir / f"{stem}_summary.csv", SUMMARY_FIELDS, [[s[k] for k in SUMMARY_FIELDS] for s in summaries])
        print_table(stem, summaries)
        all_summary += summaries
    write_csv(out_dir / "summary_all.csv", SUMMARY_FIELDS, [[s[k] for k in SUMMARY_FIELDS] for s in all_summary])
    return all_summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("records", nargs="+", help="UAE6 parquet record(s)")
    ap.add_argument("--stations", nargs="+", type=int, default=list(DEFAULT_STATIONS))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--experiment", default=str(DEFAULT_EXPERIMENT))
    ap.add_argument("--geometry", default=str(DEFAULT_GEOMETRY))
    ap.add_argument("--divide-by-qnorm", action="store_true", help="treat P channels as Pa (default: already Cp)")
    args = ap.parse_args(argv)
    try:
        run(args.records, args.stations, args.out, args.experiment, args.geometry, args.divide_by_qnorm)
    except (TapError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
