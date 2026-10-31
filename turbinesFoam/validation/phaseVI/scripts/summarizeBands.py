#!/usr/bin/env python3
"""Judge comparePhaseVI.py outputs against the pre-registered bands.

Acceptance criteria (validation-model-definition.md), selected with --criteria:
  r3 (default, owner 2026-10-30): |dP|, |dT| and |dc_n| <= 10 % at r/R 0.30,
     0.47, 0.63, 0.80 and 0.95.
  r2 (frozen, reproducible): |dP| <= 10 %, |dT| <= 15 %, c_n +-10 % at r/R
     0.47-0.80, +-15 % at 0.30, 0.95 reported only.
Usage: summarizeBands.py <cmp_dir> [<cmp_dir> ...] [--criteria r2|r3] [--allow-nonconforming]

Run directories come from metrics.json models.<model>.run_dir (written by
comparePhaseVI.py). Every model must conform to config/model-definition.yaml.
Unknown, unreadable or non-conforming runs remain diagnostic: band lines are
printed with [not of record], and exit is 1 unless --allow-nonconforming.
A window comparePhaseVI recorded as drifting (models.<model>.drift.flag, S4:
judge only quasi-steady windows) is likewise [not of record] with exit 1.
The override permits diagnostic execution, never an of-record verdict.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

from checkModelDefinition import check_run, load_definition
from comparePhaseVI import DRIFT_TOLERANCE

CRITERIA = {
    "r2": {"power": 0.10, "thrust": 0.15,
           "cn": {0.30: 0.15, 0.47: 0.10, 0.63: 0.10, 0.80: 0.10}},
    "r3": {"power": 0.10, "thrust": 0.10,
           "cn": {0.30: 0.10, 0.47: 0.10, 0.63: 0.10, 0.80: 0.10, 0.95: 0.10}},
}
DEFAULT_CRITERIA = "r3"


def definition_status(directory, definition):
    """Check all models; old comparisons without provenance fail closed."""
    try:
        models = json.loads((directory / "metrics.json").read_text()).get("models", {})
        if not models or any(not entry.get("run_dir") for entry in models.values()):
            return "definition: UNKNOWN (run dir not recorded)", False
        mismatches = []
        for entry in models.values():
            run = Path(entry["run_dir"])
            # comparePhaseVI records absolute paths; resolve legacy relative
            # paths from the Phase VI package, never the caller's directory.
            if not run.is_absolute():
                run = Path(__file__).resolve().parents[1] / run
            mismatches.extend(check_run(run, definition))
    except FileNotFoundError as exc:
        if exc.filename == str(directory / "metrics.json"):
            return "definition: UNKNOWN (run dir not recorded)", False
        mismatches = [f"unreadable input: {exc}"]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        mismatches = [f"unreadable input: {exc}"]
    version = definition["version"]
    if mismatches:
        return (f"definition {version}: NON-CONFORMING ("
                + "; ".join(dict.fromkeys(mismatches)) + ") -> NOT OF RECORD", False)
    return f"definition {version}: CONFORMS", True


def drift_status(directory):
    """Drift line for models whose recorded window drifts; None when none does.

    Comparisons without a recorded drift entry keep their previous output.
    """
    try:
        models = json.loads((directory / "metrics.json").read_text()).get("models", {})
    except (OSError, ValueError, AttributeError):
        return None
    parts = []
    for name, entry in models.items():
        drift = entry.get("drift") if isinstance(entry, dict) else None
        if not isinstance(drift, dict) or not drift.get("flag"):
            continue
        variations = ", ".join(
            f"{key} variation {100 * drift[key]['variation']:.2f} %"
            if isinstance(drift.get(key), dict) and drift[key].get("variation") is not None
            else f"{key} variation unknown"
            for key in ("cp", "cd"))
        parts.append(f"{name}: {variations}")
    if not parts:
        return None
    return ("window: DRIFT (" + "; ".join(parts)
            + f"; tolerance {100 * DRIFT_TOLERANCE:.0f} %) -> NOT OF RECORD")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dirs", nargs="+", type=Path)
    parser.add_argument("--criteria", choices=sorted(CRITERIA), default=DEFAULT_CRITERIA,
                        help="acceptance criteria: r3 uniform 10 %% incl. r/R 0.95 "
                             "(default), r2 the frozen earlier bands")
    parser.add_argument("--allow-nonconforming", action="store_true",
                        help="allow diagnostic exit 0; results stay not of record")
    args = parser.parse_args(argv)
    criteria = CRITERIA[args.criteria]
    definition = load_definition()
    all_conform = True
    for d in args.dirs:
        print(f"== {d.name}")
        line, conforms = definition_status(d, definition)
        print(f"  {line}")
        if args.criteria != "r2":
            print(f"  criteria {args.criteria.upper()}: P, T, c_n at r/R "
                  + ", ".join(f"{x:.2f}" for x in criteria["cn"])
                  + f" within {100 * criteria['power']:.0f} %")
        drift = drift_status(d)
        if drift is not None:
            print(f"  {drift}")
            conforms = False
        all_conform = all_conform and conforms
        suffix = "" if conforms else " [not of record]"
        with open(d / "turbine_comparison.csv") as f:
            for r in csv.DictReader(f):
                if r["quantity"] not in ("power", "thrust"):
                    continue
                band = criteria["power" if r["quantity"] == "power" else "thrust"]
                dv = float(r["delta_frac"])
                print(f"  {r['quantity']:6s} sim {float(r['sim']):9.2f} exp {float(r['experiment']):9.2f} "
                      f"{100*dv:+6.1f} %  band {100*band:.0f} %  {'PASS' if abs(dv) <= band else 'FAIL'}{suffix}")
        with open(d / "spanwise_comparison.csv") as f:
            for r in csv.DictReader(f):
                x = round(float(r["r_over_R"]), 2)
                dv = float(r["dcn_frac"])
                b = criteria["cn"].get(x)
                tag = "report" if b is None else ("PASS" if abs(dv) <= b else "FAIL")
                print(f"  c_n r/R {x:.2f} sim {float(r['c_ref_n']):.3f} exp {float(r['cn_exp']):.3f} {100*dv:+6.1f} %  {tag}{suffix}")
    return int(not all_conform and not args.allow_nonconforming)


if __name__ == "__main__":
    raise SystemExit(main())
