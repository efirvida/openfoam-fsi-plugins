#!/usr/bin/env python3
"""Compare one Phase VI run against a yaw or blade-pitch reference point.

Same simulation-vs-experiment tables as `comparePhaseVI.py`
(turbine_comparison.csv, spanwise_comparison.csv, metrics.json, report.txt),
but the reference row comes from `data/experiment/yaw-pitch/` and is picked by
the requested nominal yaw or pitch angle.

The run's geometric yaw magnitude is audited from `system/fvOptions` (angle
between the free-stream velocity and the rotor axis). Its sign is not audited:
the mapping from the case azimuth/rotation to the report's "positive yaw =
blade advances into the wind at 180 deg azimuth" is not established for the
case templates. Pitch is not audited (run.json carries no pitch).
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import comparePhaseVI as base
from comparePhaseVI import (
    EXIT_MISSING_INPUT,
    EXIT_OK,
    EXIT_SHORT_WINDOW,
    EXIT_TSR_MISMATCH,
    MAX_ABS_YAW_DEG,
    ROOT,
    STATIONS,
    MissingInput,
    ShortWindow,
    TsrMismatch,
    _exit,
    analyse_model,
    read_rows,
    write_spanwise_comparison,
    write_turbine_comparison,
)

DEFAULT_EXPERIMENT = ROOT / "data" / "experiment" / "yaw-pitch"
EXIT_YAW_MISMATCH = 4

PITCH_SEQUENCE = {0.0: "I", 2.0: "T", 3.0: "H", 4.0: "U", 6.0: "J"}
NOMINAL_TOLERANCE = 1.0e-6

_VECTOR = r"{key}\s*\(\s*([^\s()]+)\s+([^\s()]+)\s+([^\s()]+)\s*\)"


def _same(a, b, tol=1.0e-9):
    return math.isclose(float(a), float(b), abs_tol=tol)


def load_reference(experiment_dir: Path, kind: str, sequence: str,
                   speed: float, value: float):
    """Return (row, stations) shaped like `comparePhaseVI.load_experiment`."""
    if kind not in ("yaw", "pitch"):
        raise ValueError(f"kind must be yaw or pitch, got {kind!r}")
    stem = f"yaw_{sequence}" if kind == "yaw" else "pitch"
    performance = experiment_dir / f"{stem}_performance.csv"
    spanwise = experiment_dir / f"{stem}_spanwise.csv"
    for path in (performance, spanwise):
        if not path.exists():
            raise FileNotFoundError(str(path))
    nominal_key = f"{kind}_nominal_deg"
    at_speed = [
        row for row in read_rows(performance)
        if _same(row["wind_speed_m_s"], speed)
    ]
    matches = [
        row for row in at_speed
        if abs(float(row[nominal_key]) - float(value)) <= NOMINAL_TOLERANCE
        and (kind == "yaw" or str(row["sequence"]) == sequence)
    ]
    if not matches:
        available = sorted({
            (float(row[nominal_key]), str(row["sequence"])) for row in at_speed
        })
        listing = ", ".join(f"{v:g} ({s})" for v, s in available) or "none"
        raise ValueError(
            f"{performance}: no {kind} {value:g} deg row (sequence {sequence}) "
            f"at {speed:g} m/s; available {kind} values: {listing}"
        )
    matches.sort(key=lambda row: (float(row.get("repetition", 0)),
                                  str(row["file_name"])))
    row = matches[0]
    stations = {}
    for candidate in read_rows(spanwise):
        if str(candidate["file_name"]) != str(row["file_name"]):
            continue
        stations[float(candidate["r_over_R"])] = {
            "cn": float(candidate["cn"]),
            "ct": float(candidate["ct"]),
            "cm": float(candidate["cm"]),
            "cth": candidate.get("cth"),
            "ctq": candidate.get("ctq"),
            "qnorm_pa": candidate.get("qnorm_pa"),
        }
    if not stations:
        raise KeyError(f"{spanwise}: no rows for {row['file_name']}")
    return row, stations


def audit_run_yaw(run_dir: Path):
    """Yaw magnitude [deg] from system/fvOptions, or None if unavailable."""
    path = run_dir / "system" / "fvOptions"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    vectors = {}
    for key in ("axis", "freeStreamVelocity"):
        found = re.search(_VECTOR.format(key=key), text)
        if found is None:
            return None
        try:
            vectors[key] = [float(item) for item in found.groups()]
        except ValueError:
            return None
    axis, wind = vectors["axis"], vectors["freeStreamVelocity"]
    norm = math.hypot(*axis) * math.hypot(*wind)
    if norm == 0.0:
        return None
    cosine = -sum(a * w for a, w in zip(axis, wind, strict=True)) / norm
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def resolve_sequences(kind, value, sequence, config_sequence):
    """Return (reference sequence, config sequence); ValueError if inconsistent."""
    if kind == "yaw":
        reference = sequence or "H"
        if reference not in ("H", "S"):
            raise ValueError("yaw sequence must be H or S")
    else:
        mapped = PITCH_SEQUENCE.get(float(value))
        if mapped is None:
            reference = sequence or "H"  # load_reference lists what exists
        elif sequence is None or sequence == mapped:
            reference = mapped
        elif mapped == "H" and sequence == "S":
            reference = "S"
        else:
            raise ValueError(
                f"pitch {value:g} deg belongs to sequence {mapped}, "
                f"not {sequence}"
            )
    config = config_sequence or (reference if reference in ("H", "S") else "H")
    return reference, config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--model", choices=("alm", "asm", "asm-mesh"),
                        default=None)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--yaw", type=float, help="nominal yaw [deg]")
    target.add_argument("--pitch", type=float, help="nominal pitch [deg]")
    parser.add_argument("--speed", type=float, required=True)
    parser.add_argument("--sequence", choices=("I", "T", "H", "U", "J", "S"),
                        default=None)
    parser.add_argument("--config-sequence", choices=("H", "S"), default=None)
    parser.add_argument("--experiment", type=Path, default=DEFAULT_EXPERIMENT)
    parser.add_argument("--config", type=Path, default=base.DEFAULT_CONFIG)
    parser.add_argument("--revolutions", nargs=2, type=float,
                        metavar=("DISCARD", "END"), default=None)
    parser.add_argument("--rho", default="auto", help="'auto' or kg/m^3")
    parser.add_argument("--thrust-scope", choices=("blade", "rotor"),
                        default="blade")
    parser.add_argument("--allow-short-window", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.yaw is not None:
        kind, value = "yaw", float(args.yaw)
    else:
        kind, value = "pitch", float(args.pitch)
    run_dir = args.run_dir.resolve()

    model = args.model
    if model is None:
        run_json = run_dir / "run.json"
        if run_json.is_file():
            try:
                found = json.loads(run_json.read_text(encoding="utf-8")).get("model")
            except ValueError:
                found = None
            if isinstance(found, str):
                model = found.lower()

    try:
        sequence, config_sequence = resolve_sequences(
            kind, value, args.sequence, args.config_sequence
        )
    except ValueError as exc:
        return _exit(str(exc), EXIT_MISSING_INPUT)

    out_dir = args.out if args.out is not None else (
        ROOT / "results" / f"{kind}{value:g}-U{args.speed:g}-{sequence}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        cfg = base.load_config(args.config)
        if args.revolutions is not None:
            cfg["solver"]["discard_revolutions"] = int(args.revolutions[0])
            cfg["solver"]["end_revolutions"] = int(args.revolutions[1])
        experiment, experiment_spanwise = load_reference(
            args.experiment, kind, sequence, args.speed, value
        )
    except (FileNotFoundError, KeyError, ValueError) as exc:
        return _exit(f"experiment/config input missing: {exc}", EXIT_MISSING_INPUT)

    # Run audit: yaw magnitude only (sign not established, see module doc).
    run_yaw = audit_run_yaw(run_dir)
    expected_yaw = abs(value) if kind == "yaw" else 0.0
    audit = {
        "run_yaw_magnitude_deg": run_yaw,
        "expected_yaw_magnitude_deg": expected_yaw,
        "yaw_sign_audited": False,
        "run_pitch_audited": False,
        "fvOptions_found": run_yaw is not None,
    }
    if run_yaw is not None and abs(run_yaw - expected_yaw) > MAX_ABS_YAW_DEG:
        return _exit(
            f"run yaw magnitude {run_yaw:.3f} deg (system/fvOptions) differs "
            f"from the requested {expected_yaw:g} deg by more than "
            f"{MAX_ABS_YAW_DEG} deg", EXIT_YAW_MISMATCH,
        )

    rho_value = (
        float(experiment["rho_kg_m3"]) if args.rho == "auto" else float(args.rho)
    )
    rho_source = (
        f"WTBARO/WTATEMP ideal gas (experiment row {experiment['file_name']})"
        if args.rho == "auto" else "user override (--rho)"
    )

    label = model or run_dir.name
    try:
        result = analyse_model(
            run_dir, cfg, args.speed, config_sequence, rho_value,
            args.allow_short_window, args.thrust_scope, model=model,
        )
    except (FileNotFoundError, MissingInput) as exc:
        return _exit(f"missing input for {label}: {exc}", EXIT_MISSING_INPUT)
    except ShortWindow as exc:
        return _exit(f"{label}: short averaging window: {exc}", EXIT_SHORT_WINDOW)
    except (TsrMismatch, ValueError) as exc:
        return _exit(f"{label}: {exc}", EXIT_TSR_MISMATCH)
    tsr_config = float(base.select_speed(cfg, args.speed, config_sequence)["tsr"])
    result["metrics"]["tsr_config"] = tsr_config
    result["metrics"]["rho_kg_m3"] = rho_value
    result["metrics"]["rho_source"] = rho_source
    results = {label: result}

    measured = write_turbine_comparison(
        out_dir / "turbine_comparison.csv", results, experiment,
        args.thrust_scope,
    )
    write_spanwise_comparison(
        out_dir / "spanwise_comparison.csv", results, experiment_spanwise
    )

    root_flap = {
        key: (float(experiment[key]) if key in experiment else None)
        for key in ("b1rfb_nm", "b3rfb_nm", "eaerorfb_nm")
    }
    metrics = {
        "case": {
            "kind": kind,
            "nominal_deg": value,
            "speed_m_s": args.speed,
            "sequence": sequence,
            "config_sequence": config_sequence,
            "tsr_reference": float(experiment["tsr"]),
            "tsr_config": tsr_config,
            "rotor_radius_m": float(cfg["turbine"]["radius"]),
            "rho_kg_m3": rho_value,
            "rho_source": rho_source,
            "thrust_scope": args.thrust_scope,
        },
        "reference": {
            "file_name": experiment["file_name"],
            "rotpow_kw": measured["power"],
            "lsstqcor_nm": measured["torque"],
            "eaeroth_n": measured["thrust"],
            "b3pitch_deg": float(experiment["b3pitch_deg"]),
            "root_flap_experiment_only": root_flap,
            "spanwise": {
                f"{station:.2f}": experiment_spanwise[station]
                for station in STATIONS if station in experiment_spanwise
            },
        },
        "run_audit": audit,
        "window": {
            "discard_revolutions": int(cfg["solver"]["discard_revolutions"]),
            "end_revolutions": int(cfg["solver"]["end_revolutions"]),
            "allow_short_window": args.allow_short_window,
        },
        "models": {
            label: {
                "run_dir": result["metrics"]["run_dir"],
                "metrics": result["metrics"],
                "drift": result["drift"],
                "revolutions_averaged": result["stats"]["revolutions_averaged"],
                "window_mode": result["stats"]["window_mode"],
                "spanwise": dict(result["spanwise"]),
            }
        },
        "limitations": base.LIMITATIONS,
    }
    (out_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    m = result["metrics"]
    lines = [
        f"NREL Phase VI {kind} comparison - nominal {value:g} deg, "
        f"sequence {sequence} (config sequence {config_sequence}), "
        f"{args.speed:g} m/s",
        f"reference row: {experiment['file_name']}",
        f"TSR: reference {float(experiment['tsr']):.4f}, "
        f"configured {tsr_config:.4f}",
        f"measured blade-3 pitch: {float(experiment['b3pitch_deg']):.3f} deg",
        f"rho: {rho_value:.6f} kg/m^3 ({rho_source})",
        f"  P {m['power_kw']:.4g} kW vs {measured['power']:.4g} kW; "
        f"Q {m['torque_nm']:.4g} Nm vs {measured['torque']:.4g} Nm; "
        f"T {m['thrust_n']:.4g} N vs {measured['thrust']:.4g} N "
        f"(scope {m['thrust_scope']})",
        "  root flap (experiment only, no simulated counterpart): "
        + ", ".join(f"{k} {v}" for k, v in root_flap.items()),
    ]
    if run_yaw is None:
        lines.append("WARNING: system/fvOptions axis/freeStreamVelocity not "
                     "found; run yaw not audited")
    else:
        lines.append(f"run yaw magnitude (fvOptions): {run_yaw:.3f} deg; "
                     "sign and pitch not audited")
    report = "\n".join(lines) + "\n"
    (out_dir / "report.txt").write_text(report, encoding="utf-8")
    print(report)
    print(f"outputs written to {out_dir}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
