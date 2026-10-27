#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify the AeroDyn BEM (OpenFAST v5) against every Phase VI experiment table on disk.

The repository holds one experiment, the NREL UAE Phase VI archive. This tool builds one AeroDyn
driver case (`buildAeroDynCase.build_point_case`, BEMT, v1.3 inputs: tip pitch reference geometry,
OSU total polar, cylinder root, rigid, no tower, cone 0, tilt 0) for each selected measured point,
with the point's own rpm (the table's measured rotor speed, not `tsr * U / R`), density, wind speed,
tip pitch and yaw; runs the local `aerodyn_driver` serially; and compares power, thrust, torque and
the chord-referenced c_n / c_t at r/R 0.30 .. 0.95 with `compareAeroDyn.compare_case`.

Families and the selection rule:

    s-curve   data/experiment/uae6-archive/sequence_S_*.csv: every speed (5-25 m/s), 0 deg yaw, 3 deg pitch
    pitch     data/experiment/yaw-pitch/pitch_*.csv: every row (sequences I, T, H, S, U, J), 0 deg yaw
    yaw-S/H   data/experiment/yaw-pitch/yaw_{S,H}_*.csv: speeds up to --max-yaw-speed (default 10 m/s),
              every nominal yaw, first (lowest) repetition per (speed, nominal yaw), ties by file name

Skewed-wake model (v5.0.0 names) for yawed points only: `Skew_Mod=1`, `SkewMomCorr=True`,
`SkewRedistr_Mod=1`; a `SkewMomCorr=False` run of every yawed point is reported as a sensitivity.

Derived tables (odd/tasks/v13-adoption-asm.md L12): power and thrust error per speed on the S curve,
dP/dpitch and dT/dpitch signs per speed (model vs experiment, finite differences between consecutive
pitch levels), power error at 5-7 m/s per pitch, and the mean-power ratio P(yaw)/P(0) per speed
and yaw (model vs experiment, difference in percentage points).

Usage:
    verifyAeroDyn.py --list
    verifyAeroDyn.py --out analysis/aerodyn-verification --work /tmp/ad-verify
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import math
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tools"))

import buildAeroDynCase  # noqa: E402
import compareAeroDyn  # noqa: E402

ARCHIVE = ROOT / "data" / "experiment" / "uae6-archive"
YAW_PITCH = ROOT / "data" / "experiment" / "yaw-pitch"
OUT_DEFAULT = ROOT / "analysis" / "aerodyn-verification"
OPENFAST_ENV_DEFAULT = Path("/scratch/leahk/eduardo.donestevez/openfast-5.0.0-dp")
STATIONS = compareAeroDyn.STATIONS
FAMILIES = ("s-curve", "pitch", "yaw")
ATTACHED_SPEEDS = (5.0, 6.0, 7.0)
#: A pitch step whose experimental change is below this fraction of its mean value is "flat" (noise-level).
FLAT_STEP_FRACTION = 0.03
DRIVER_TIMEOUT_S = 300.0


# --- tables and point selection ---------------------------------------------


def read_table(path: Path) -> list[dict]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def _spanwise_by_file(rows: list[dict]) -> dict[str, dict[float, dict]]:
    table: dict[str, dict[float, dict]] = {}
    for row in rows:
        table.setdefault(row["file_name"], {})[float(row["r_over_R"])] = {"cn": float(row["cn"]), "ct": float(row["ct"])}
    return table


def _point(family: str, row: dict, spanwise: dict, pitch: float, yaw: float) -> dict:
    name = row["file_name"]
    if name not in spanwise or not all(s in spanwise[name] for s in STATIONS):
        raise KeyError(f"{name}: spanwise rows for stations {STATIONS} not found")
    return {
        "family": family,
        "id": name,
        "sequence": row["sequence"],
        "wind_speed_m_s": float(row["wind_speed_m_s"]),
        "rpm": float(row["rpm"]),
        "rho_kg_m3": float(row["rho_kg_m3"]),
        "pitch_deg": float(pitch),
        "yaw_deg": float(yaw),
        "repetition": int(row["repetition"]),
        "performance": {
            "file_name": name,
            "rotpow_kw": float(row["rotpow_kw"]),
            "eaeroth_n": float(row["eaeroth_n"]),
            "lsstqcor_nm": float(row["lsstqcor_nm"]),
        },
        "spanwise": spanwise[name],
    }


def s_curve_points(archive: Path = ARCHIVE) -> list[dict]:
    """Sequence S, 0 deg yaw, 3 deg tip pitch, every speed of `sequence_S_performance.csv`."""
    perf = read_table(Path(archive) / "sequence_S_performance.csv")
    span = _spanwise_by_file(read_table(Path(archive) / "sequence_S_spanwise.csv"))
    points = []
    for row in perf:
        if row["yaw_token"] != "0000":
            raise ValueError(f"{row['file_name']}: expected a 0 deg yaw point, token {row['yaw_token']}")
        points.append(_point("s-curve", row, span, 3.0, 0.0))
    return sorted(points, key=lambda p: p["wind_speed_m_s"])


def pitch_points(yaw_pitch: Path = YAW_PITCH) -> list[dict]:
    """Every row of the blade-pitch table: the sequence's nominal tip pitch, 0 deg yaw."""
    perf = read_table(Path(yaw_pitch) / "pitch_performance.csv")
    span = _spanwise_by_file(read_table(Path(yaw_pitch) / "pitch_spanwise.csv"))
    points = [_point("pitch", row, span, float(row["pitch_nominal_deg"]), float(row["yaw_nominal_deg"])) for row in perf]
    return sorted(points, key=lambda p: (p["pitch_deg"], p["sequence"], p["wind_speed_m_s"]))


def yaw_points(yaw_pitch: Path = YAW_PITCH, sequence: str = "S", max_speed: float = 10.0) -> list[dict]:
    """Fixed-yaw points of Sequence S or H: first repetition per (speed, nominal yaw), speeds up to `max_speed`."""
    if sequence not in ("S", "H"):
        raise ValueError(f"yaw tables exist for sequences S and H, not {sequence!r}")
    perf = read_table(Path(yaw_pitch) / f"yaw_{sequence}_performance.csv")
    span = _spanwise_by_file(read_table(Path(yaw_pitch) / f"yaw_{sequence}_spanwise.csv"))
    first: dict[tuple[float, float], dict] = {}
    for row in sorted(perf, key=lambda r: (float(r["wind_speed_m_s"]), float(r["yaw_nominal_deg"]), int(r["repetition"]), r["file_name"])):
        speed = float(row["wind_speed_m_s"])
        if speed > max_speed:
            continue
        first.setdefault((speed, float(row["yaw_nominal_deg"])), row)
    return [_point(f"yaw-{sequence}", row, span, float(row["pitch_nominal_deg"]), float(row["yaw_nominal_deg"])) for _, row in sorted(first.items())]


# --- sign convention ----------------------------------------------------------


def bottom_blade_axial_velocity(clockwise_from_upwind: bool, yaw_clockwise_from_top_deg: float | None = None,
                                yaw_counterclockwise_from_top_deg: float | None = None) -> float:
    """Wind-direction velocity of the blade at 180 deg azimuth (pointing down), in units of omega R.

    Frame: x downwind, z up. The rotor axis (downwind) is x rotated by the yaw about z. A negative result
    means the blade moves into the wind, i.e. "advances into the wind at 180 deg azimuth" (Hand et al.,
    Fig. B-25). Exactly one yaw argument may be given; none means 0 deg.
    """
    if yaw_clockwise_from_top_deg is not None and yaw_counterclockwise_from_top_deg is not None:
        raise ValueError("give one yaw argument")
    psi = math.radians(yaw_counterclockwise_from_top_deg if yaw_counterclockwise_from_top_deg is not None else -(yaw_clockwise_from_top_deg or 0.0))
    axis = (math.cos(psi), math.sin(psi), 0.0)  # downwind rotor axis
    spin = 1.0 if clockwise_from_upwind else -1.0  # clockwise seen from upwind = +omega about the downwind axis
    omega = tuple(spin * a for a in axis)
    position = (0.0, 0.0, -1.0)
    velocity_x = omega[1] * position[2] - omega[2] * position[1]
    return velocity_x


# --- L12 metrics ----------------------------------------------------------------


def pitch_slopes(values_by_pitch: dict[float, float]) -> list[dict]:
    """Finite differences between consecutive pitch levels: slope per degree, change and mean of the step."""
    levels = sorted(values_by_pitch)
    steps = []
    for lo, hi in zip(levels, levels[1:]):
        delta = values_by_pitch[hi] - values_by_pitch[lo]
        steps.append({"pitch_lo": lo, "pitch_hi": hi, "slope": delta / (hi - lo), "delta": delta,
                      "mean": 0.5 * (values_by_pitch[hi] + values_by_pitch[lo])})
    return steps


def sign_agreement(model: list[dict], experiment: list[dict], min_exp_relative_change: float = 0.0) -> dict:
    """Pairwise sign agreement of model and experiment slopes on matching (pitch_lo, pitch_hi) steps.

    A zero experimental slope has no sign to agree with. With `min_exp_relative_change > 0`, steps whose
    experimental change is below that fraction of the step mean are left out of the count.
    """
    by_step = {(s["pitch_lo"], s["pitch_hi"]): s for s in model}
    pairs, agree = [], 0
    for exp in experiment:
        mod = by_step.get((exp["pitch_lo"], exp["pitch_hi"]))
        if mod is None:
            continue
        if min_exp_relative_change > 0.0:
            mean = abs(exp.get("mean", 0.0))
            if mean == 0.0 or abs(exp.get("delta", 0.0)) / mean < min_exp_relative_change:
                continue
        same = exp["slope"] != 0.0 and mod["slope"] != 0.0 and (exp["slope"] > 0.0) == (mod["slope"] > 0.0)
        agree += int(same)
        pairs.append({"pitch_lo": exp["pitch_lo"], "pitch_hi": exp["pitch_hi"], "model_slope": mod["slope"],
                      "exp_slope": exp["slope"], "agree": same})
    return {"agree": agree, "total": len(pairs), "pairs": pairs}


def power_ratios(points: list[dict]) -> list[dict]:
    """P(yaw)/P(0) per (sequence, speed) for model and experiment; the difference is in percentage points.

    Each point keeps its own measured rpm and density in the model, so the experiment ratio carries the same
    small condition changes. Yawed points without a yaw-0 partner at the same speed are left out.
    """
    zero = {(p["sequence"], p["wind_speed_m_s"]): p for p in points if p["yaw_deg"] == 0.0}
    rows = []
    for p in points:
        base = zero.get((p["sequence"], p["wind_speed_m_s"]))
        if p["yaw_deg"] == 0.0 or base is None:
            continue
        ratio_model = p["model_power_kw"] / base["model_power_kw"]
        ratio_exp = p["exp_power_kw"] / base["exp_power_kw"]
        rows.append({"sequence": p["sequence"], "wind_speed_m_s": p["wind_speed_m_s"], "yaw_deg": p["yaw_deg"],
                     "ratio_model": ratio_model, "ratio_exp": ratio_exp, "diff_pp": 100.0 * (ratio_model - ratio_exp)})
    return sorted(rows, key=lambda r: (r["sequence"], r["wind_speed_m_s"], r["yaw_deg"]))


def attached_power_errors(rows: list[dict], speeds: tuple[float, ...] = ATTACHED_SPEEDS) -> list[dict]:
    """Power error rows at the attached-flow speeds, ordered by pitch, speed, sequence."""
    kept = [r for r in rows if r["wind_speed_m_s"] in speeds]
    return sorted(kept, key=lambda r: (r["pitch_deg"], r["wind_speed_m_s"], r.get("sequence", "")))


def probe_configuration_rows(rows: list[dict]) -> list[dict]:
    """Sequence H (five-hole probes installed) against S (probes removed, holes plugged) at 3 deg pitch, 0 deg yaw.

    Same rotor otherwise (Hand et al., Sequences H and S: upwind, rigid, 0 deg cone, 72 rpm). The model
    cannot see the probes, so its H/S ratio only carries the two points' rpm and density.
    """
    by = {(r["sequence"], r["wind_speed_m_s"]): r for r in rows if r["family"] == "pitch" and r["status"] == "ok" and r["sequence"] in ("H", "S")}
    table = []
    for speed in sorted({k[1] for k in by}):
        h, s = by.get(("H", speed)), by.get(("S", speed))
        if h is None or s is None:
            continue
        table.append({"wind_speed_m_s": speed, "power_exp_H_over_S": h["power_exp_kw"] / s["power_exp_kw"],
                      "power_model_H_over_S": h["power_kw"] / s["power_kw"],
                      "thrust_exp_H_over_S": h["thrust_exp_n"] / s["thrust_exp_n"], "thrust_model_H_over_S": h["thrust_n"] / s["thrust_n"],
                      "power_error_H_pct": h["power_error_pct"], "power_error_S_pct": s["power_error_pct"]})
    return table


def l12_summary(s_rows: list[dict], attached: list[dict], ratios: list[dict], band_pct: float = 10.0,
                yaw_speeds: tuple[float, ...] = ATTACHED_SPEEDS, small_yaw_deg: float = 20.0, ratio_band_pp: float = 5.0) -> dict:
    """The three judged quantities in one place: S-curve power band, attached-flow power by pitch, yaw ratio at 5-7 m/s."""
    ok = [r for r in s_rows if r["status"] == "ok"]
    worst = max(ok, key=lambda r: abs(r["power_error_pct"])) if ok else None
    small = [r for r in ratios if r["wind_speed_m_s"] in yaw_speeds and abs(r["yaw_deg"]) <= small_yaw_deg]
    large = [r for r in ratios if r["wind_speed_m_s"] in yaw_speeds and small_yaw_deg < abs(r["yaw_deg"]) <= 90.0]
    def extreme(rows):
        top = max(rows, key=lambda r: abs(r["diff_pp"])) if rows else None
        return {"max_abs_diff_pp": abs(top["diff_pp"]), "at": f"{top['sequence']} {top['wind_speed_m_s']:g} m/s yaw {top['yaw_deg']:g}"} if top else None
    return {
        "s_curve_power_within_band": [r["wind_speed_m_s"] for r in ok if abs(r["power_error_pct"]) <= band_pct],
        "s_curve_worst_power": {"wind_speed_m_s": worst["wind_speed_m_s"], "error_pct": worst["power_error_pct"]} if worst else None,
        "attached_power_max_abs_error_pct_by_pitch": {f"{pitch:g}": max(abs(r["power_error_pct"]) for r in attached if r["pitch_deg"] == pitch) for pitch in sorted({r["pitch_deg"] for r in attached})},
        "attached_power_within_band": sum(abs(r["power_error_pct"]) <= band_pct for r in attached), "attached_power_total": len(attached),
        "yaw_ratio_small_yaw": {**(extreme(small) or {}), "within_band": sum(abs(r["diff_pp"]) <= ratio_band_pp for r in small), "total": len(small)},
        "yaw_ratio_20_to_90_deg": {**(extreme(large) or {}), "within_band": sum(abs(r["diff_pp"]) <= ratio_band_pp for r in large), "total": len(large)},
    }


# --- running ----------------------------------------------------------------------


def driver_path(openfast_env: Path) -> Path:
    return Path(openfast_env) / "bin" / "aerodyn_driver"


def driver_version(openfast_env: Path) -> str:
    done = subprocess.run([str(driver_path(openfast_env))], capture_output=True, text=True, timeout=60)
    match = re.search(r"AeroDyn_driver-v[\w.\-]+", done.stdout + done.stderr)
    return match.group(0) if match else "unknown"


def run_point(point: dict, wake: str, case_dir: Path, openfast_env: Path, skew_mom_corr: bool = buildAeroDynCase.SKEW_MOM_CORR) -> dict:
    """Build, run and compare one point; a failed run is a row with a status, never an exception."""
    row = {key: point[key] for key in ("family", "id", "sequence", "wind_speed_m_s", "rpm", "rho_kg_m3", "pitch_deg", "yaw_deg", "repetition")}
    started = time.time()
    case = buildAeroDynCase.build_point_case(point, wake, case_dir, skew_mom_corr=skew_mom_corr)
    try:
        done = subprocess.run([str(driver_path(openfast_env)), "ad_driver.dvr"], cwd=case, capture_output=True, text=True, timeout=DRIVER_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {**row, "status": "driver timeout", "wall_s": time.time() - started}
    text = (done.stdout + done.stderr).replace("\r", "\n")
    if done.returncode != 0 or "terminated normally" not in text:
        message = " ".join(line.strip() for line in text.splitlines() if "ERROR" in line.upper() or "not converge" in line.lower())[:200]
        return {**row, "status": f"driver failed rc={done.returncode} {message}".strip(), "wall_s": time.time() - started}
    try:
        metrics = compareAeroDyn.compare_case(case)["metrics"]
    except (compareAeroDyn.MissingInput, compareAeroDyn.ShortWindow, KeyError) as exc:
        return {**row, "status": f"compare failed: {exc}", "wall_s": time.time() - started}
    conv = metrics["convergence"]
    row.update({
        "status": "ok",
        "power_kw": metrics["power_kw"], "power_exp_kw": metrics["power_exp_kw"], "power_error_pct": metrics["power_error_pct"],
        "thrust_n": metrics["thrust_n"], "thrust_exp_n": metrics["thrust_exp_n"], "thrust_error_pct": metrics["thrust_error_pct"],
        "torque_nm": metrics["torque_nm"], "torque_exp_nm": metrics["torque_exp_nm"], "torque_error_pct": metrics["torque_error_pct"],
        "converged": bool(conv["converged"]) if conv else "",
        "stations": metrics["stations"],
        "wall_s": time.time() - started,
    })
    return row


# --- selection and tables ---------------------------------------------------------


def select_points(families: tuple[str, ...], archive: Path, yaw_pitch: Path, max_yaw_speed: float) -> list[dict]:
    points: list[dict] = []
    if "s-curve" in families:
        points += s_curve_points(archive)
    if "pitch" in families:
        points += pitch_points(yaw_pitch)
    if "yaw" in families:
        points += yaw_points(yaw_pitch, "S", max_yaw_speed) + yaw_points(yaw_pitch, "H", max_yaw_speed)
    return points


POINT_FIELDS = ["family", "id", "sequence", "wind_speed_m_s", "rpm", "rho_kg_m3", "pitch_deg", "yaw_deg", "repetition", "status",
                "power_kw", "power_exp_kw", "power_error_pct", "thrust_n", "thrust_exp_n", "thrust_error_pct",
                "torque_nm", "torque_exp_nm", "torque_error_pct", "converged", "wall_s"]
STATION_FIELDS = ["family", "id", "sequence", "wind_speed_m_s", "pitch_deg", "yaw_deg", "r_over_R", "cn", "cn_exp", "cn_error_pct",
                  "ct", "ct_exp", "ct_error_pct", "alpha_deg"]


def _fmt(value):
    return f"{value:.6g}" if isinstance(value, float) else value


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with Path(path).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", restval="")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _fmt(value) for key, value in row.items()})


def station_rows(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        for key, st in (row.get("stations") or {}).items():
            out.append({**{k: row[k] for k in ("family", "id", "sequence", "wind_speed_m_s", "pitch_deg", "yaw_deg")},
                        "r_over_R": key, "cn": st["cn"], "cn_exp": st["cn_exp"], "cn_error_pct": st["cn_error_pct"],
                        "ct": st["ct"], "ct_exp": st["ct_exp"], "ct_error_pct": st["ct_error_pct"], "alpha_deg": st["alpha_deg"]})
    return out


def pitch_slope_rows(rows: list[dict]) -> tuple[list[dict], dict]:
    """dP/dpitch and dT/dpitch per speed on two ladders: pitch 3 from S (no probes) and from H (probes)."""
    ok = [r for r in rows if r["family"] == "pitch" and r["status"] == "ok"]
    speeds = sorted({r["wind_speed_m_s"] for r in ok})
    table, tally = [], {}
    for ladder, level3 in (("S3", "S"), ("H3", "H")):
        for speed in speeds:
            chosen = [r for r in ok if r["wind_speed_m_s"] == speed and (r["pitch_deg"] != 3.0 or r["sequence"] == level3)]
            if len({r["pitch_deg"] for r in chosen}) < 2:
                continue
            steps = {}
            for quantity, model_key, exp_key in (("P", "power_kw", "power_exp_kw"), ("T", "thrust_n", "thrust_exp_n")):
                steps[quantity] = (pitch_slopes({r["pitch_deg"]: r[model_key] for r in chosen}), pitch_slopes({r["pitch_deg"]: r[exp_key] for r in chosen}))
            for i, exp_p in enumerate(steps["P"][1]):
                entry = {"ladder": ladder, "wind_speed_m_s": speed, "pitch_lo": exp_p["pitch_lo"], "pitch_hi": exp_p["pitch_hi"]}
                for quantity in ("P", "T"):
                    mod, exp = steps[quantity][0][i], steps[quantity][1][i]
                    agree = exp["slope"] != 0.0 and mod["slope"] != 0.0 and (exp["slope"] > 0.0) == (mod["slope"] > 0.0)
                    flat = exp["mean"] == 0.0 or abs(exp["delta"]) / abs(exp["mean"]) < FLAT_STEP_FRACTION
                    entry.update({f"d{quantity}_model_per_deg": mod["slope"], f"d{quantity}_exp_per_deg": exp["slope"],
                                  f"{quantity}_sign_agree": int(agree), f"{quantity}_exp_flat": int(flat)})
                table.append(entry)
    for ladder in ("S3", "H3"):
        subset = [r for r in table if r["ladder"] == ladder]
        for quantity in ("P", "T"):
            tally[f"{ladder}_{quantity}"] = {
                "steps": len(subset), "agree": sum(r[f"{quantity}_sign_agree"] for r in subset),
                "steps_not_flat": sum(1 - r[f"{quantity}_exp_flat"] for r in subset),
                "agree_not_flat": sum(r[f"{quantity}_sign_agree"] for r in subset if not r[f"{quantity}_exp_flat"]),
            }
    return table, tally


def yaw_ratio_rows(rows: list[dict], sensitivity: dict[str, dict]) -> list[dict]:
    ok = [r for r in rows if r["family"].startswith("yaw-") and r["status"] == "ok"]
    def prepare(source, key_power="power_kw"):
        return [{"sequence": r["sequence"], "wind_speed_m_s": r["wind_speed_m_s"], "yaw_deg": r["yaw_deg"], "id": r["id"],
                 "model_power_kw": r[key_power], "exp_power_kw": r["power_exp_kw"]} for r in source]
    main = power_ratios(prepare(ok))
    sens_points = prepare([r for r in ok if r["yaw_deg"] == 0.0] + [r for r in sensitivity.values() if r["status"] == "ok"])
    sens = {(r["sequence"], r["wind_speed_m_s"], r["yaw_deg"]): r for r in power_ratios(sens_points)}
    for row in main:
        other = sens.get((row["sequence"], row["wind_speed_m_s"], row["yaw_deg"]))
        row["ratio_model_no_momcorr"] = other["ratio_model"] if other else ""
        row["diff_pp_no_momcorr"] = other["diff_pp"] if other else ""
    return main


# --- main -----------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="print the selected points per family and exit (no OpenFAST needed)")
    parser.add_argument("--families", default=",".join(FAMILIES), help="comma list of s-curve,pitch,yaw (default all)")
    parser.add_argument("--max-yaw-speed", type=float, default=10.0, help="highest wind speed of the yaw tables (default 10 m/s)")
    parser.add_argument("--openfast-env", type=Path, default=OPENFAST_ENV_DEFAULT, help="OpenFAST install prefix with bin/aerodyn_driver")
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT, help="result directory (CSV tables, summary.json)")
    parser.add_argument("--work", type=Path, default=None, help="new scratch directory for the driver cases, outside the repository (default: a temp dir)")
    parser.add_argument("--no-skew-sensitivity", action="store_true", help="skip the SkewMomCorr=False run of the yawed points")
    parser.add_argument("--experiment", type=Path, default=ARCHIVE, help="Sequence S table directory (default data/experiment/uae6-archive)")
    parser.add_argument("--yaw-pitch", type=Path, default=YAW_PITCH, help="pitch and yaw table directory (default data/experiment/yaw-pitch)")
    args = parser.parse_args(argv)
    families = tuple(f for f in args.families.split(",") if f)
    unknown = [f for f in families if f not in FAMILIES]
    if unknown:
        parser.error(f"unknown family {unknown}; choose from {FAMILIES}")
    points = select_points(families, args.experiment, args.yaw_pitch, args.max_yaw_speed)
    counts = {}
    for p in points:
        counts[p["family"]] = counts.get(p["family"], 0) + 1
    if args.list:
        for family, count in counts.items():
            print(f"{family:<10}{count:>5} points")
        print(f"{'total':<10}{len(points):>5} points")
        return 0
    if not driver_path(args.openfast_env).is_file():
        print(f"aerodyn_driver not found at {driver_path(args.openfast_env)} (--openfast-env)", file=sys.stderr)
        return 1
    work = args.work or Path(tempfile.mkdtemp(prefix="ad-verify-"))
    work.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    rows, sensitivity = [], {}
    for index, point in enumerate(points, start=1):
        rows.append(run_point(point, "bem", work / f"{point['family']}-{point['id']}", args.openfast_env))
        if point["yaw_deg"] != 0.0 and not args.no_skew_sensitivity:
            sensitivity[point["id"]] = run_point(point, "bem", work / f"{point['family']}-{point['id']}-nomom", args.openfast_env, skew_mom_corr=False)
        if index % 25 == 0 or index == len(points):
            print(f"{index}/{len(points)} points, {time.time() - started:.0f} s", flush=True)
    write_csv(args.out / "points.csv", POINT_FIELDS, rows)
    write_csv(args.out / "stations.csv", STATION_FIELDS, station_rows(rows))
    s_rows = [r for r in rows if r["family"] == "s-curve"]
    write_csv(args.out / "s_curve.csv", ["wind_speed_m_s", "rpm", "rho_kg_m3", "status", "power_kw", "power_exp_kw", "power_error_pct", "thrust_n", "thrust_exp_n", "thrust_error_pct", "converged"], s_rows)
    slopes, tally = pitch_slope_rows(rows)
    if slopes:
        write_csv(args.out / "pitch_slopes.csv", list(slopes[0]), slopes)
    attached = attached_power_errors([r for r in rows if r["family"] == "pitch" and r["status"] == "ok"])
    write_csv(args.out / "pitch_attached_power.csv", ["sequence", "pitch_deg", "wind_speed_m_s", "power_kw", "power_exp_kw", "power_error_pct", "thrust_error_pct"], attached)
    write_csv(args.out / "probes_H_vs_S.csv", ["wind_speed_m_s", "power_exp_H_over_S", "power_model_H_over_S", "thrust_exp_H_over_S", "thrust_model_H_over_S", "power_error_H_pct", "power_error_S_pct"], probe_configuration_rows(rows))
    ratios = yaw_ratio_rows(rows, sensitivity)
    write_csv(args.out / "yaw_power_ratio.csv", ["sequence", "wind_speed_m_s", "yaw_deg", "ratio_model", "ratio_exp", "diff_pp", "ratio_model_no_momcorr", "diff_pp_no_momcorr"], ratios)
    failed = [r for r in rows if r["status"] != "ok"]
    summary = {
        "openfast": driver_version(args.openfast_env),
        "date": datetime.date.today().isoformat(),
        "command": "verifyAeroDyn.py " + " ".join(argv if argv is not None else sys.argv[1:]),
        "points": counts,
        "failed": [{"id": r["id"], "status": r["status"]} for r in failed],
        "not_converged": [r["id"] for r in rows if r["status"] == "ok" and r["converged"] is False],
        "pitch_sign_agreement": tally,
        "l12": l12_summary(s_rows, attached, ratios),
        "wall_s": time.time() - started,
        "skew": {"Skew_Mod": 1, "SkewMomCorr": buildAeroDynCase.SKEW_MOM_CORR, "SkewRedistr_Mod": buildAeroDynCase.SKEW_REDISTR_MOD},
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"{len(rows)} cases, {len(failed)} failed, {summary['wall_s']:.0f} s; tables in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
