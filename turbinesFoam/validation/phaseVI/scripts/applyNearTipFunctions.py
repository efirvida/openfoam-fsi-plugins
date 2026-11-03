#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply the Trigaux near-tip correction functions to existing Phase VI station results.

Offline, no solver: reads the per-station normal-force coefficient c_n of the ALM
element CSVs, of the AeroDyn OLAF-DP / BEM runs and the experiment, computes the
effective tip distance of the Phase VI blade and applies the near-tip functions of
F. Trigaux (UCLouvain PhD thesis 2024, Appendix C, Tables C.2/C.3; J. Fluid Mech. 989,
A1, DOI 10.1017/jfm.2024.461).

Definitions (thesis eq. 3.17-3.31):

    (1 - F_l) = (1 - F_Cl) (1 - F_alpha_e)
    C_l^corr  = (1 - F_Cl) dCl/dalpha (1 - F_alpha_e) alpha_e
    (d_tip/c)_eff(r) = integral from r to R of dr'/c(r')

The blade chord is linear between the stations of `phaseVI_blade.csv`; on a linear
taper the integral reduces to the closed form of eq. 3.31.

Modes
  --apply cl    multiply the lift part of c_n by (1 - F_Cl): the virtual-camber
                part, kernel-independent (the F_Cl of the six tables differ by a few
                1e-3 at the Phase VI stations; the spread is reported). Valid for any
                lifting-line-class model (ALM + Dag-Sorensen, OLAF, BEM).
  --apply full  multiply the lift part by (1 - F_l) = (1 - F_Cl)(1 - F_alpha_e) for
                `--kernel` and `--sigma-over-c` (linear in sigma/c between the tabulated
                0.25, 0.5, 1.0). F_alpha_e removes the mollification-induced error of a
                model WITHOUT a smearing correction: on top of Dag-Sorensen it double
                counts; the result is flagged.

c_n = c_l cos(alpha) + c_d sin(alpha). The lift part is c_l cos(alpha). Where c_t is
known (ALM element CSV, AeroDyn nodal Ct) c_l = c_n cos(alpha) + c_t sin(alpha) is
exact and the corrected value is c_n - F c_l cos(alpha) (drag and alpha unchanged:
alpha_e of the line model is kept, only the lift is rescaled). `cn_scale` columns give the
approximation c_n (1 - F), which treats the drag term as part of the lift.

Exit status: 0 on success, 2 on an input error (missing file, d/c outside the table,
sigma/c outside [0.25, 1]).

Example
  python3 -I scripts/applyNearTipFunctions.py --apply cl \\
      --runs-dir <runs> --out analysis/near-tip-functions/cl.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tools"))

DEFAULT_TABLE = ROOT / "data" / "near-tip-functions" / "trigaux2024_tableC.csv"
DEFAULT_BLADE = ROOT / "data" / "geometry" / "phaseVI_blade.csv"
DEFAULT_EXPERIMENT = ROOT / "data" / "experiment" / "uae6-archive"
DEFAULT_CONFIG = ROOT / "config" / "case.yaml"
RADIUS_M = 5.029
SIGMAS = (0.25, 0.5, 1.0)
KERNELS = ("2D", "3D")
LABEL_ALM = "var-tip-pitch-dag-sorensen-total"
# (sequence, speed, discard revolutions, end revolutions): v13-adoption-asm L26.
CELLS = (
    ("S", 5, 16, 24),
    ("S", 6, 16, 24),
    ("S", 7, 4, 12),
    ("S", 8, 4, 12),
    ("H", 7, 4, 12),
)
MODELS = ("alm", "olaf-dp", "bem")
BAND = 0.10


class InputError(Exception):
    """Unusable input; the CLI maps it to exit status 2."""


# --------------------------------------------------------------------------- data

def _csv_rows(path: Path):
    try:
        with path.open(encoding="utf-8") as stream:
            lines = [line for line in stream if line.strip() and not line.startswith("#")]
    except OSError as error:
        raise InputError(f"{path}: {error}") from error
    return list(csv.DictReader(lines))


def read_table(path: Path = DEFAULT_TABLE):
    """{(kernel, sigma_over_c): [(d, F_l, F_Cl, F_alpha_e), ...]} sorted by d."""
    table: dict = {}
    for row in _csv_rows(path):
        key = (row["kernel"], float(row["sigma_over_c"]))
        table.setdefault(key, []).append(
            (float(row["d_over_c"]), float(row["F_l"]), float(row["F_Cl"]),
             float(row["F_alpha_e"]))
        )
    for rows in table.values():
        rows.sort()
    return table


def read_blade(path: Path = DEFAULT_BLADE):
    """[(radius_m, chord_m), ...] sorted by radius."""
    # The header of phaseVI_blade.csv is a '#' comment line: columns by position.
    try:
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.startswith("#")]
        blade = sorted(
            (float(ln.split(",")[0]), float(ln.split(",")[1])) for ln in lines
            if not ln.startswith("radius_m")
        )
    except (OSError, ValueError, IndexError) as error:
        raise InputError(f"{path}: {error}") from error
    if len(blade) < 2:
        raise InputError(f"{path}: fewer than two blade stations")
    return blade


# ---------------------------------------------------------------------- geometry

def effective_distance(blade, r, radius=RADIUS_M):
    """(d_tip/c)_eff(r) = integral from r to `radius` of dr'/c(r') (thesis eq. 3.29).

    The chord is linear between stations (and constant outside the table); on one
    linear piece the integral is dr/(c2 - c1) ln(c2/c1), the closed form of eq. 3.31.
    """
    if r > radius:
        raise InputError(f"radius {r} m is beyond the tip ({radius} m)")
    points = [(x, c) for x, c in blade if x < radius] + [(radius, _chord_at(blade, radius))]
    total = 0.0
    for (x1, c1), (x2, c2) in zip(points, points[1:]):
        lo, hi = max(x1, r), x2
        if hi <= lo:
            continue
        ca = c1 + (c2 - c1) * (lo - x1) / (x2 - x1)
        cb = c1 + (c2 - c1) * (hi - x1) / (x2 - x1)
        if abs(cb - ca) < 1e-12 * max(ca, cb):
            total += (hi - lo) / ca
        else:
            total += (hi - lo) / (cb - ca) * math.log(cb / ca)
    return total


def _chord_at(blade, x):
    if x <= blade[0][0]:
        return blade[0][1]
    if x >= blade[-1][0]:
        return blade[-1][1]
    for (x1, c1), (x2, c2) in zip(blade, blade[1:]):
        if x1 <= x <= x2:
            return c1 + (c2 - c1) * (x - x1) / (x2 - x1)
    raise InputError("chord lookup failed")


# ------------------------------------------------------------------- interpolation

def interp_functions(rows, d):
    """(F_l, F_Cl, F_alpha_e) at d/c by linear interpolation in the table `rows`.

    Raises InputError if d is outside [0, last tabulated d/c].
    """
    if d < rows[0][0] or d > rows[-1][0]:
        raise InputError(
            f"d/c = {d:.4f} outside the table range [{rows[0][0]:.4f}, {rows[-1][0]:.4f}]"
        )
    for (d1, *v1), (d2, *v2) in zip(rows, rows[1:]):
        if d1 <= d <= d2:
            t = (d - d1) / (d2 - d1)
            return tuple(a + t * (b - a) for a, b in zip(v1, v2))
    return tuple(rows[-1][1:])


def functions_at(table, d, kernel, sigma):
    """(F_l, F_Cl, F_alpha_e) for `kernel` at `sigma`/c, linear in sigma/c between tables."""
    if kernel not in KERNELS:
        raise InputError(f"kernel {kernel!r} not in {KERNELS}")
    if sigma < SIGMAS[0] - 1e-12 or sigma > SIGMAS[-1] + 1e-12:
        raise InputError(f"sigma/c = {sigma} outside [{SIGMAS[0]}, {SIGMAS[-1]}]")
    for s1, s2 in zip(SIGMAS, SIGMAS[1:]):
        if s1 - 1e-12 <= sigma <= s2 + 1e-12:
            a = interp_functions(table[(kernel, s1)], d)
            b = interp_functions(table[(kernel, s2)], d)
            t = (sigma - s1) / (s2 - s1)
            return tuple(x + t * (y - x) for x, y in zip(a, b))
    raise InputError("sigma interpolation failed")


# ---------------------------------------------------------------------- application

def split_lift(cn, ct, alpha_deg):
    """(c_l, c_d) of a chord-line (c_n, c_t) pair: c_n = c_l cos a + c_d sin a,
    c_t = c_l sin a - c_d cos a."""
    a = math.radians(alpha_deg)
    return cn * math.cos(a) + ct * math.sin(a), cn * math.sin(a) - ct * math.cos(a)


def apply_lift_factor(cn, lift_part, factor):
    """c_n with the lift part c_l cos(alpha) multiplied by `factor` = 1 - F."""
    return cn - (1.0 - factor) * lift_part


def apply_scale(cn, factor):
    """Approximation: scale the whole c_n by `factor` = 1 - F."""
    return cn * factor


def error_pct(value, reference):
    return 100.0 * (value - reference) / reference


# ------------------------------------------------------------------------- inputs

def alm_station(run_dir: Path, cfg, speed, sequence, radius, stations):
    """{r/R: (c_n, c_t, alpha_deg_equivalent, lift_part)} of an ALM run, window from cfg.

    c_n and c_t are the time means of c_l cos a + c_d sin a and c_l sin a - c_d cos a
    per element row (as comparePhaseVI.spanwise_profile), interpolated linearly in r/R;
    the lift part c_l cos a is averaged the same way.
    """
    import comparePhaseVI as cp

    element_dir = run_dir / cp.ELEMENT_DIR
    if not element_dir.is_dir():
        raise InputError(f"{element_dir}: not a directory")
    start, end, _ = cp.window_bounds(cfg, speed, sequence)
    profile = []
    for path, rows in cp.read_elements(element_dir):
        window = [row for row in rows if start <= float(row["time"]) <= end]
        if not window:
            raise InputError(f"{path}: no samples in the averaging window")
        mean = cp.mean
        root = mean([float(row["root_dist"]) for row in window])
        cn, ct, lift, drag = [], [], [], []
        for row in window:
            a = math.radians(float(row["alpha_deg"]))
            cl, cd = float(row["cl"]), float(row["cd"])
            cn.append(cl * math.cos(a) + cd * math.sin(a))
            ct.append(cl * math.sin(a) - cd * math.cos(a))
            lift.append(cl * math.cos(a))
            drag.append(cd * math.sin(a))
        profile.append((cp.r_over_r_from_root_dist(root, radius),
                        mean(cn), mean(ct), mean(lift), mean(drag)))
    profile.sort()
    out = {}
    for station in stations:
        cn, ct, lift, drag = cp.interpolate(profile, station)
        out[station] = {"cn": cn, "lift_part": lift, "drag_part": drag, "ct": ct}
    return out


def aerodyn_station(metrics_path: Path, stations):
    """{r/R: dict} from an AeroDyn driver metrics.json (nodal Cn, Ct, alpha)."""
    try:
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise InputError(f"{metrics_path}: {error}") from error
    out = {}
    for station in stations:
        entry = data["stations"].get(f"{station:.2f}")
        if entry is None:
            raise InputError(f"{metrics_path}: no station {station:.2f}")
        cl, cd = split_lift(entry["cn"], entry["ct"], entry["alpha_deg"])
        a = math.radians(entry["alpha_deg"])
        out[station] = {"cn": entry["cn"], "ct": entry["ct"],
                        "lift_part": cl * math.cos(a), "drag_part": cd * math.sin(a),
                        "cn_exp_file": entry["cn_exp"]}
    return out


def run_dirs(runs: Path, model, sequence, speed):
    if model == "alm":
        suffix = (f"U{speed}-coarse-seq{sequence}-{LABEL_ALM}" if sequence == "S"
                  else f"U{speed}-coarse-{LABEL_ALM}")
        return runs / f"alm-{suffix}"
    wake = "bem" if model == "bem" else "olaf-dp"
    return runs / f"aerodyn-{wake}-{sequence}U{speed}" / "metrics.json"


# ---------------------------------------------------------------------------- main

COLUMNS = [
    "model", "cell", "r_over_R", "d_eff_over_c", "apply", "kernel", "sigma_over_c",
    "F_Cl", "F_alpha_e", "F_applied", "F_Cl_min", "F_Cl_max",
    "cn_exp", "cn_uncorr", "err_uncorr_pct", "in_band_uncorr",
    "lift_part", "cn_corr", "err_corr_pct", "in_band_corr",
    "cn_corr_scale", "err_corr_scale_pct", "scale_vs_lift_pp",
    "err_corr_FClmin_pct", "err_corr_FClmax_pct", "double_counts_DS",
]


def process(args) -> list[dict]:
    import comparePhaseVI as cp

    table = read_table(Path(args.table))
    blade = read_blade(Path(args.blade))
    cfg = cp.load_config(Path(args.config))
    cells = [c for c in CELLS if not args.cells or f"{c[0]}{c[1]}" in args.cells]
    models = args.models or list(MODELS)
    stations = args.stations
    rows = []
    for sequence, speed, discard, end in cells:
        cell = f"{sequence}{speed}"
        cfg["solver"]["discard_revolutions"] = discard
        cfg["solver"]["end_revolutions"] = end
        _, experiment = cp.load_experiment(Path(args.experiment_dir), sequence, float(speed))
        for model in models:
            path = run_dirs(Path(args.runs_dir), model, sequence, speed)
            if model == "alm":
                data = alm_station(path, cfg, float(speed), sequence, args.radius, stations)
            else:
                data = aerodyn_station(path, stations)
            for station in stations:
                rows.append(station_row(args, table, blade, model, cell, station,
                                        data[station], experiment))
    return rows


def station_row(args, table, blade, model, cell, station, value, experiment):
    d = effective_distance(blade, station * args.radius, args.radius)
    cn_exp = min(experiment.items(), key=lambda kv: abs(kv[0] - station))[1]["cn"]
    cn = value["cn"]
    if args.apply == "cl":
        _, fcl, fae = functions_at(table, d, args.kernel, args.sigma_over_c)
        applied = fcl
    else:
        fl, fcl, fae = functions_at(table, d, args.kernel, args.sigma_over_c)
        applied = fl
    spread = [interp_functions(rows, d)[1] for rows in table.values()]
    lift = value["lift_part"]
    corrected = apply_lift_factor(cn, lift, 1.0 - applied)
    scaled = apply_scale(cn, 1.0 - applied)
    err_u, err_c = error_pct(cn, cn_exp), error_pct(corrected, cn_exp)
    return {
        "model": model, "cell": cell, "r_over_R": f"{station:.2f}",
        "d_eff_over_c": f"{d:.4f}", "apply": args.apply,
        "kernel": args.kernel if args.apply == "full" else "any",
        "sigma_over_c": f"{args.sigma_over_c}" if args.apply == "full" else "any",
        "F_Cl": f"{fcl:.4f}", "F_alpha_e": f"{fae:.4f}", "F_applied": f"{applied:.4f}",
        "F_Cl_min": f"{min(spread):.4f}", "F_Cl_max": f"{max(spread):.4f}",
        "cn_exp": f"{cn_exp:.4f}", "cn_uncorr": f"{cn:.4f}",
        "err_uncorr_pct": f"{err_u:.1f}", "in_band_uncorr": str(abs(err_u) <= 100 * BAND).lower(),
        "lift_part": f"{lift:.4f}", "cn_corr": f"{corrected:.4f}",
        "err_corr_pct": f"{err_c:.1f}", "in_band_corr": str(abs(err_c) <= 100 * BAND).lower(),
        "cn_corr_scale": f"{scaled:.4f}",
        "err_corr_scale_pct": f"{error_pct(scaled, cn_exp):.1f}",
        "scale_vs_lift_pp": f"{error_pct(scaled, cn_exp) - err_c:.2f}",
        "err_corr_FClmin_pct": f"{error_pct(apply_lift_factor(cn, lift, 1.0 - min(spread)), cn_exp):.1f}",
        "err_corr_FClmax_pct": f"{error_pct(apply_lift_factor(cn, lift, 1.0 - max(spread)), cn_exp):.1f}",
        "double_counts_DS": str(args.apply == "full" and model == "alm").lower(),
    }


def write_profile(path: Path, table, blade, radius, kernel, sigma):
    """F_Cl / F_alpha_e at every blade-table radius; beyond the table range: blank."""
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["radius_m", "r_over_R", "chord_m", "d_eff_over_c", "F_Cl", "F_alpha_e"])
        for x, c in blade:
            d = effective_distance(blade, x, radius)
            try:
                _, fcl, fae = functions_at(table, d, kernel, sigma)
                cells = [f"{fcl:.4f}", f"{fae:.4f}"]
            except InputError:
                cells = ["", ""]
            writer.writerow([f"{x:.4f}", f"{x / radius:.4f}", f"{c:.4f}", f"{d:.4f}", *cells])


def summarize(paths) -> str:
    """Band counts (|error| <= 10 %) per model before/after and the c_n-scaling error."""
    lines = []
    for path in paths:
        rows = _csv_rows(Path(path))
        lines.append(f"{path}: apply={rows[0]['apply']} kernel={rows[0]['kernel']} "
                     f"sigma/c={rows[0]['sigma_over_c']}")
        for model in MODELS:
            mine = [r for r in rows if r["model"] == model]
            if not mine:
                continue
            before = sum(r["in_band_uncorr"] == "true" for r in mine)
            after = sum(r["in_band_corr"] == "true" for r in mine)
            worst = max(abs(float(r["scale_vs_lift_pp"])) for r in mine)
            lines.append(f"  {model}: inside 10 % {before}/{len(mine)} -> {after}/{len(mine)}; "
                         f"max |c_n-scaling - lift-only| = {worst:.2f} pp")
    return "\n".join(lines)


def build_parser():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--summarize", nargs="+", metavar="CSV",
                   help="print band counts per model for station CSVs written by this tool and exit")
    p.add_argument("--apply", choices=("cl", "full"),
                   help="cl: lift part x (1 - F_Cl); full: lift part x (1 - F_Cl)(1 - F_alpha_e)")
    p.add_argument("--kernel", choices=KERNELS, default="3D",
                   help="table family for F_Cl/F_alpha_e (cl mode: F_Cl of this family; default 3D)")
    p.add_argument("--sigma-over-c", type=float, default=0.25,
                   help="mollification size over chord, in [0.25, 1] (default 0.25)")
    p.add_argument("--stations", type=float, nargs="+", default=[0.80, 0.95],
                   help="r/R stations (default 0.80 0.95)")
    p.add_argument("--cells", nargs="+", help="subset of S5 S6 S7 S8 H7 (default all)")
    p.add_argument("--models", nargs="+", choices=MODELS, help="default alm olaf-dp bem")
    p.add_argument("--runs-dir", default=str(ROOT / "runs"),
                   help="directory holding alm-U*-... and aerodyn-*-<seq>U* run dirs")
    p.add_argument("--experiment-dir", default=str(DEFAULT_EXPERIMENT))
    p.add_argument("--table", default=str(DEFAULT_TABLE))
    p.add_argument("--blade", default=str(DEFAULT_BLADE))
    p.add_argument("--config", default=str(DEFAULT_CONFIG))
    p.add_argument("--radius", type=float, default=RADIUS_M, help="rotor radius [m]")
    p.add_argument("--out", help="station CSV (default: stdout)")
    p.add_argument("--profile-out",
                   help="also write F_Cl/F_alpha_e at every blade-table radius to this CSV")
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.summarize:
        try:
            print(summarize(args.summarize))
        except (InputError, KeyError, IndexError) as error:
            print(f"applyNearTipFunctions: error: {error}", file=sys.stderr)
            return 2
        return 0
    if args.apply is None:
        parser.error("--apply is required")
    try:
        if args.profile_out:
            write_profile(Path(args.profile_out), read_table(Path(args.table)),
                          read_blade(Path(args.blade)), args.radius, args.kernel,
                          args.sigma_over_c)
        rows = process(args)
    except (InputError, FileNotFoundError, KeyError, ValueError) as error:
        print(f"applyNearTipFunctions: error: {error}", file=sys.stderr)
        return 2
    stream = open(args.out, "w", newline="", encoding="utf-8") if args.out else sys.stdout
    try:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    finally:
        if args.out:
            stream.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
