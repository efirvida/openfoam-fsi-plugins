#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Attach the R6 uncertainty to a run's Phase VI comparison (read-only).

Production-readiness criterion R6 (validation-model-definition.md): every
validation number carries its experiment repeatability, its averaging-window
sensitivity and the blockage sensitivity; each quoted difference carries the
combined uncertainty (validation-evidence-register.md, section 4).

Quantities (same definitions and loaders as comparePhaseVI.py): rotor power,
blade thrust (against EAEROTH, `--thrust-scope`) and the chord-referenced c_n at
r/R 0.30/0.47/0.63/0.80/0.95.

Sources, all quoted as standard-size terms of the quantity:

1. Experiment repeatability. The raw UAE6 frames are read from the Parquet
   archive (`turbinesFoam/articles/uae6/parquet`, gitignored, written by
   `eng2parquet.py`). Every 0-degree file of the (sequence, speed) pair gives
   one mean (err-flagged frames masked, the rule of `extractUAE6Reference.py`;
   files whose measured yaw is not within 0.5 degrees of zero are excluded);
   with two or more files the term is their sample standard deviation
   (file-to-file scatter, includes the small change of tunnel condition between
   files). With a single file the term is the standard error of the mean of the
   per-revolution means with an effective sample size from the autocorrelation
   (initial-positive-sequence estimator of Geyer 1992, n_eff = N / tau,
   tau = -1 + 2 sum of the positive autocorrelation pairs; the revolution means
   remove the periodic 1P content that would otherwise inflate tau). Without the
   archive the term is "not available" and no number is invented.
2. Averaging window of the simulation: the quantities are recomputed over the
   definition window (case.yaml, revolutions 4-12) and the windows that start 2
   and 4 revolutions later (6-12, 8-12); the term is the largest departure from
   the definition window.
3. Blockage: BEM-estimated (bemPhaseVI.py at the measured rpm and density)
   relative change of each quantity for an inflow +1 % and +2 % (NREL: tunnel
   blockage below 2 % in velocity). The larger of the two magnitudes (the +2 %
   value wherever the response is monotone) enters the combination as a
   ONE-SIDED bound: blockage raises the effective inflow, it never lowers it,
   so it is not a symmetric random term. If the BEM cannot be used the U^3 (power) and U^2 (thrust)
   bound is stated instead, and c_n is reported as not covered.

Combined = quadrature sum of (1) and (3, one-sided bound) for the experiment side and (2)
for the simulation side. The verdict wording is the evidence register's.

Exit codes:
    0  report produced
    1  run does not conform to the model definition (R5) and
       --allow-nonconforming was not given
    2  missing or unusable input
"""

from __future__ import annotations

import argparse
import copy
import math
import sys
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import comparePhaseVI  # noqa: E402
from checkModelDefinition import check_run, load_definition  # noqa: E402

STATIONS = comparePhaseVI.STATIONS
QUANTITIES = ("power", "thrust") + tuple(f"cn{station:.2f}" for station in STATIONS)
WINDOW_SHIFTS = (0, 2, 4)
BLOCKAGE_INCREMENTS = (0.01, 0.02)
BLOCKAGE_LABEL = "BEM-estimated blockage sensitivity"
BLOCKAGE_BOUND_LABEL = "U^3 / U^2 bound (not a BEM estimate)"
FRAME_DT_S = 1.92e-3
PARTIAL_REVOLUTION_FRACTION = 0.9
MAX_ABS_YAW_DEG = comparePhaseVI.MAX_ABS_YAW_DEG
# The last logged step of a run is a fraction of a time step short of the end
# revolution: a shifted window shorter than its nominal length by less than
# this is still that window.
WINDOW_LENGTH_TOLERANCE_REV = 0.05

VERDICT_INSIDE = "agrees within the combined numerical and experimental uncertainty"
VERDICT_OUTSIDE = (
    "outside the combined uncertainty: report the difference and its likely cause"
)

EXIT_OK = 0
EXIT_NONCONFORMING = 1
EXIT_INPUT = 2


def quadrature(*terms):
    """Root of the sum of squares of the available terms (None when none is)."""
    present = [float(term) for term in terms if term is not None]
    if not present:
        return None
    return math.sqrt(sum(term * term for term in present))


def window_deviation(values, reference):
    """Largest absolute departure of any window value from the reference window."""
    return max(abs(value - values[reference]) for value in values.values())


def verdict(difference, combined, coverage=1.0, missing=()):
    """Evidence register section 4 wording; no claim when a term is missing."""
    if missing:
        return ("uncertainty incomplete (" + ", ".join(missing)
                + "): no agreement claim")
    if abs(difference) <= coverage * combined:
        return VERDICT_INSIDE
    return VERDICT_OUTSIDE


def effective_sample_size(series):
    """N / tau with the initial-positive-sequence estimate of tau (Geyer 1992).

    tau = -1 + 2 * sum_m (rho_2m + rho_2m+1) over the leading positive pairs;
    clamped to [1, N] so the result lies in [1, N] (anti-correlation is not
    credited with more than N independent samples).
    """
    x = np.asarray(series, dtype="float64")
    count = x.size
    if count < 3:
        return float(count)
    x = x - x.mean()
    spectrum = np.fft.rfft(x, 2 * count)
    autocovariance = np.fft.irfft(spectrum * np.conj(spectrum))[:count] / count
    if autocovariance[0] <= 0.0:
        return float(count)
    rho = autocovariance / autocovariance[0]
    usable = (count // 2) * 2
    pairs = rho[0:usable:2] + rho[1:usable:2]
    nonpositive = np.flatnonzero(pairs <= 0.0)
    stop = nonpositive[0] if nonpositive.size else pairs.size
    tau = -1.0 + 2.0 * float(pairs[:stop].sum())
    tau = min(max(tau, 1.0), float(count))
    return count / tau


def standard_error(series):
    """Standard error of the mean using the autocorrelation effective sample size."""
    x = np.asarray(series, dtype="float64")
    return float(np.std(x, ddof=1) / math.sqrt(effective_sample_size(x)))


def revolution_means(values, keep, period_s, dt_s=FRAME_DT_S):
    """Mean of the kept frames of each complete revolution (partial last one dropped)."""
    values = np.asarray(values, dtype="float64")
    keep = np.asarray(keep, dtype=bool)
    bins = np.floor(np.arange(values.size) * dt_s / period_s).astype(int)
    counts = np.bincount(bins[keep], minlength=bins.max() + 1)
    sums = np.bincount(bins[keep], weights=values[keep], minlength=bins.max() + 1)
    present = counts > 0
    means = sums[present] / counts[present]
    counts = counts[present]
    if counts.size > 1 and counts[-1] < PARTIAL_REVOLUTION_FRACTION * np.median(counts):
        means = means[:-1]
    return means


def channel_of(quantity):
    if quantity == "power":
        return "ROTPOW"
    if quantity == "thrust":
        return "EAEROTH"
    return f"CN{int(round(float(quantity[2:]) * 100)):02d}"


def file_statistics(path):
    """Per-quantity mean and in-file standard error of one raw test point."""
    import extractUAE6Reference as archive
    import pyarrow.parquet as pq

    channels = sorted({channel_of(q) for q in QUANTITIES} | {"err", "RPM", "YAW", "VTUN"})
    table = pq.read_table(str(path), columns=channels)
    frames = {name: table.column(name).to_numpy(zero_copy_only=False) for name in channels}
    keep = frames["err"] == archive.ERR_BYTE_OK
    if not keep.any():
        raise ValueError(f"{path}: every frame is flagged, nothing to average")
    period = 60.0 / float(np.mean(frames["RPM"][keep].astype("float64")))
    result = {
        "yaw": float(np.mean(frames["YAW"][keep].astype("float64"))),
        "vtun": float(np.mean(frames["VTUN"][keep].astype("float64"))),
    }
    for quantity in QUANTITIES:
        series = frames[channel_of(quantity)].astype("float64")
        result[quantity] = {
            "mean": float(np.mean(series[keep])),
            "sem": standard_error(revolution_means(series, keep, period)),
        }
    return result


def archive_files(archive_dir, sequence, speed):
    """Parquet files of the 0-degree test points of (sequence, speed), every repetition."""
    import extractUAE6Reference as archive

    if not Path(archive_dir).is_dir() or float(speed) != int(speed):
        return []
    found = []
    for path in sorted(Path(archive_dir).glob("*.parquet")):
        stem = archive.parse_stem(path.name[: -len(".parquet")])
        if (stem is not None and stem.sequence == sequence.lower()
                and stem.speed == int(speed) and stem.yaw_deg == 0):
            found.append((stem.name, path))
    return found


def experiment_repeatability(archive_dir, sequence, speed):
    """Per-quantity repeatability term of the experiment (see the module docstring)."""
    files = archive_files(archive_dir, sequence, speed)
    if not files:
        reason = (f"not available: no UAE6 parquet for {sequence} {speed:g} m/s "
                  f"under {archive_dir}")
        return {q: {"u": None, "method": reason, "files": [], "values": {}} for q in QUANTITIES}
    stats = {name: file_statistics(path) for name, path in files}
    stats = {name: item for name, item in stats.items() if abs(item["yaw"]) <= MAX_ABS_YAW_DEG}
    names = list(stats)
    if not names:
        reason = (f"not available: every {sequence} {speed:g} m/s file under "
                  f"{archive_dir} has a measured yaw beyond {MAX_ABS_YAW_DEG} deg")
        return {q: {"u": None, "method": reason, "files": [], "values": {}} for q in QUANTITIES}
    result = {}
    for quantity in QUANTITIES:
        values = {name: stats[name][quantity]["mean"] for name in names}
        if len(names) >= 2:
            u = float(np.std(list(values.values()), ddof=1))
            method = f"file-to-file (n={len(names)} files, sample standard deviation)"
        else:
            u = stats[names[0]][quantity]["sem"]
            method = ("in-file SEM (per-revolution means, autocorrelation "
                      "effective sample size)")
        result[quantity] = {"u": u, "method": method, "files": names, "values": values,
                            "sem": {name: stats[name][quantity]["sem"] for name in names},
                            "vtun": {name: stats[name]["vtun"] for name in names}}
    return result


def model_name(run_dir):
    return "asm-mesh" if Path(run_dir).name.startswith("asm-mesh") else None


def simulation_values(run_dir, cfg, speed, sequence, rho, thrust_scope, allow_short=False):
    """(quantities, revolutions averaged) of one averaging window."""
    result = comparePhaseVI.analyse_model(
        Path(run_dir), cfg, speed, sequence, rho, allow_short, thrust_scope,
        model=model_name(run_dir),
    )
    values = {
        "power": result["metrics"]["power_kw"],
        "thrust": result["metrics"]["thrust_n"],
    }
    for station in STATIONS:
        values[f"cn{station:.2f}"] = result["spanwise"][f"{station:.2f}"][0]
    return values, result["stats"]["revolutions_averaged"]


def window_sensitivity(run_dir, cfg, speed, sequence, rho, thrust_scope):
    """Quantities over the definition window and the later-starting ones."""
    discard = int(cfg["solver"]["discard_revolutions"])
    end = int(cfg["solver"]["end_revolutions"])
    windows, values, unavailable = {}, {}, []
    reference = f"{discard}-{end}"
    for shift in WINDOW_SHIFTS:
        if discard + shift >= end:
            continue
        label = f"{discard + shift}-{end}"
        shifted = copy.deepcopy(cfg)
        shifted["solver"]["discard_revolutions"] = discard + shift
        # The definition window is read strictly; a shifted window is accepted
        # when the run covers it (a short window falls back to the whole run
        # inside analyse_model, which the revolution count below rejects).
        try:
            window_values, revolutions = simulation_values(
                run_dir, shifted, speed, sequence, rho, thrust_scope,
                allow_short=label != reference)
        except comparePhaseVI.ShortWindow:
            if label == reference:
                raise
            unavailable.append(label)
            continue
        if label != reference and revolutions < end - (discard + shift) - WINDOW_LENGTH_TOLERANCE_REV:
            unavailable.append(label)
            continue
        values[label] = window_values
        windows[label] = (discard + shift, end)
    deviation = {
        quantity: window_deviation(
            {label: window[quantity] for label, window in values.items()}, reference)
        for quantity in QUANTITIES
    }
    return {"windows": windows, "values": values, "reference": reference,
            "deviation": deviation, "unavailable": unavailable}


def bem_quantities(args, bem):
    stations, thrust, _, power, radius = bem.run(args)
    radii = np.array([s["r"] for s in stations]) / radius
    chord_cn = np.array([
        s["cl"] * math.cos(math.radians(s["alpha"])) + s["cd"] * math.sin(math.radians(s["alpha"]))
        for s in stations
    ])
    values = {"power": power, "thrust": thrust}
    for station in STATIONS:
        values[f"cn{station:.2f}"] = float(np.interp(station, radii, chord_cn))
    return values


def blockage_sensitivity(rpm, rho, speed, pitch, increments=BLOCKAGE_INCREMENTS,
                         drag="pressure", tip="on"):
    """Relative change of each quantity for inflow x (1 + increment) at fixed rpm (BEM)."""
    import bemPhaseVI as bem

    def at(factor):
        return bem_quantities(argparse.Namespace(
            speed=speed * factor, rpm=rpm, rho=rho, pitch=pitch, blades=2, tip=tip,
            cd_scale=1.0, drag=drag, nstations=200), bem)

    base = at(1.0)
    relative = {}
    for increment in increments:
        raised = at(1.0 + increment)
        relative[increment] = {q: raised[q] / base[q] - 1.0 for q in QUANTITIES}
    return {"label": BLOCKAGE_LABEL, "relative": relative}


def blockage_bound(increments=BLOCKAGE_INCREMENTS):
    """Fallback: power ~ U^3, thrust ~ U^2; c_n is not covered."""
    return {
        "label": BLOCKAGE_BOUND_LABEL,
        "relative": {
            increment: {"power": (1.0 + increment) ** 3 - 1.0,
                        "thrust": (1.0 + increment) ** 2 - 1.0}
            for increment in increments
        },
    }


def combine(simulation, experiment_value, repeatability, blockage, window, coverage):
    """Per-quantity difference, terms, combined uncertainty and verdict."""
    rows = {}
    smallest, largest = min(blockage["relative"]), max(blockage["relative"])
    for quantity in QUANTITIES:
        rep = repeatability[quantity]["u"]
        relative = {inc: blockage["relative"][inc].get(quantity) for inc in blockage["relative"]}
        scale = abs(experiment_value[quantity])
        covered = all(value is not None for value in relative.values())
        blk = max(abs(value) for value in relative.values()) * scale if covered else None
        win = window["deviation"][quantity]
        terms = {"experiment repeatability": rep, "blockage": blk, "averaging window": win}
        missing = [name for name, value in terms.items() if value is None]
        combined = quadrature(quadrature(rep, blk), win)
        present = {name: value for name, value in terms.items() if value is not None}
        dominant = max(present, key=present.get) if present else "n/a"
        difference = simulation[quantity] - experiment_value[quantity]
        rows[quantity] = {
            "sim": simulation[quantity], "exp": experiment_value[quantity],
            "difference": difference, "rep": rep, "blk": blk, "win": win,
            "blk_low": None if relative[smallest] is None else relative[smallest] * scale,
            "blk_high": None if relative[largest] is None else relative[largest] * scale,
            "combined": combined, "dominant": dominant, "missing": missing,
            "verdict": verdict(difference, combined, coverage, missing),
        }
    return rows


def definition_line(run_dir):
    """(text, conforms) like summarizeBands: unreadable input fails closed."""
    try:
        definition = load_definition()
        mismatches = check_run(run_dir, definition)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return f"definition: NON-CONFORMING (unreadable input: {exc}) -> NOT OF RECORD", False
    version = definition["version"]
    if mismatches:
        return (f"definition {version}: NON-CONFORMING ("
                + "; ".join(dict.fromkeys(mismatches)) + ") -> NOT OF RECORD"), False
    return f"definition {version}: CONFORMS", True


def pct(value, reference):
    if value is None:
        return "   n/a"
    return f"{100.0 * value / abs(reference):6.2f}"


def format_value(quantity, value):
    return f"{value:9.4f}" if quantity.startswith("cn") else f"{value:9.2f}"


def unit_of(quantity):
    return {"power": "kW", "thrust": "N"}.get(quantity, "")


def print_report(args, rows, repeatability, blockage, window, tag, experiment_name,
                 blockage_note):
    print(f"R6 uncertainty - {args.sequence} {args.speed:g} m/s, run {args.run_dir.name}{tag}")
    print(f"experiment row {experiment_name}; sim window {window['reference']} revolutions; "
          f"thrust scope {args.thrust_scope} (vs EAEROTH); coverage k={args.coverage:g}")
    print("all uncertainties are % of the experiment value; blk = larger of the +1 %/+2 % "
          "magnitudes, one-sided")
    print(f"{'quantity':9s}{'sim':>10s}{'exp':>10s}{'sim-exp%':>9s}{'rep%':>7s}"
          f"{'blk+1%':>8s}{'blk+2%':>8s}{'blk%':>7s}{'win%':>7s}{'comb%':>7s}  dominant")
    for quantity in QUANTITIES:
        row = rows[quantity]
        print(f"{quantity:9s}{format_value(quantity, row['sim']):>10s}"
              f"{format_value(quantity, row['exp']):>10s}"
              f"{pct(row['difference'], row['exp']):>9s}{pct(row['rep'], row['exp']):>7s}"
              f"{pct(row['blk_low'], row['exp']):>8s}{pct(row['blk_high'], row['exp']):>8s}"
              f"{pct(row['blk'], row['exp']):>7s}{pct(row['win'], row['exp']):>7s}{pct(row['combined'], row['exp']):>7s}"
              f"  {row['dominant']}")
    print()
    for quantity in QUANTITIES:
        row = rows[quantity]
        unit = f" {unit_of(quantity)}" if unit_of(quantity) else ""
        combined = "n/a" if row["combined"] is None else f"{row['combined']:.4g}{unit}"
        print(f"{quantity}: sim - exp = {row['difference']:+.4g}{unit} "
              f"({100.0 * row['difference'] / abs(row['exp']):+.1f} %) "
              f"+/- {combined} ({row['dominant']} dominates): {row['verdict']}")
    print()
    first = repeatability["power"]
    print(f"repeatability method: {first['method']}")
    if first["files"]:
        print("  files: " + ", ".join(first["files"]))
        for quantity in ("power", "thrust"):
            values = repeatability[quantity]["values"]
            print(f"  {quantity}: " + "  ".join(f"{name} {value:.4g}" for name, value in values.items()))
        print("  measured VTUN (m/s, nominal " + f"{args.speed:g}): " + "  ".join(
            f"{name} {value:.3f}" for name, value in first["vtun"].items()))
    print(f"blockage: {blockage['label']}{blockage_note}")
    for increment, relative in sorted(blockage["relative"].items()):
        print(f"  inflow +{100 * increment:g} %: " + "  ".join(
            f"{q} {100 * relative[q]:+.2f}%" for q in QUANTITIES if q in relative))
    print("windows (revolutions): " + ", ".join(
        f"{label} P {window['values'][label]['power']:.4g} kW T "
        f"{window['values'][label]['thrust']:.4g} N" for label in window["windows"]))
    if window["unavailable"]:
        print("  windows not reached by the run: " + ", ".join(window["unavailable"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--sequence", choices=("H", "S"), required=True)
    parser.add_argument("--speed", type=float, required=True)
    parser.add_argument("--experiment-dir", type=Path, default=comparePhaseVI.DEFAULT_EXPERIMENT)
    parser.add_argument("--archive-dir", type=Path, default=None,
                        help="UAE6 parquet directory (default turbinesFoam/articles/uae6/parquet)")
    parser.add_argument("--config", type=Path, default=comparePhaseVI.DEFAULT_CONFIG)
    parser.add_argument("--thrust-scope", choices=("blade", "rotor"), default="blade")
    parser.add_argument("--coverage", type=float, default=1.0,
                        help="coverage factor k applied to the combined term (default 1)")
    parser.add_argument("--allow-nonconforming", action="store_true",
                        help="diagnostic report for a non-conforming run (never of record)")
    args = parser.parse_args(argv)

    line, conforms = definition_line(args.run_dir)
    print(line)
    if not conforms and not args.allow_nonconforming:
        print("refused: the run does not conform to the model definition "
              "(use --allow-nonconforming for a diagnostic report)", file=sys.stderr)
        return EXIT_NONCONFORMING
    tag = "" if conforms else " [not of record]"

    if args.archive_dir is None:
        import extractUAE6Reference as archive
        args.archive_dir = archive.ARCHIVE_DIR / "parquet"
    try:
        cfg = comparePhaseVI.load_config(args.config)
        experiment, spanwise = comparePhaseVI.load_experiment(
            args.experiment_dir, args.sequence, args.speed)
        rho = float(experiment["rho_kg_m3"])
        window = window_sensitivity(args.run_dir.resolve(), cfg, args.speed, args.sequence,
                                    rho, args.thrust_scope)
    except (FileNotFoundError, KeyError, ValueError, comparePhaseVI.MissingInput,
            comparePhaseVI.ShortWindow, comparePhaseVI.TsrMismatch) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INPUT

    measured = {"power": float(experiment["rotpow_kw"]), "thrust": float(experiment["eaeroth_n"])}
    for station in STATIONS:
        measured[f"cn{station:.2f}"] = spanwise[station]["cn"]
    simulation = window["values"][window["reference"]]

    repeatability = experiment_repeatability(args.archive_dir, args.sequence, args.speed)
    pitch = float(cfg["turbine"].get("pitch_deg", 3.0))
    blockage_note = ""
    try:
        blockage = blockage_sensitivity(float(experiment["rpm"]), rho, args.speed, pitch)
    except (ImportError, OSError, ValueError, KeyError) as exc:
        blockage = blockage_bound()
        blockage_note = f" (BEM unusable: {exc})"
    rows = combine(simulation, measured, repeatability, blockage, window, args.coverage)
    print_report(args, rows, repeatability, blockage, window, tag, experiment["file_name"],
                 blockage_note)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
