#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the IEA 22-280-RWT in standalone OpenFAST v5.0.0 (AeroDyn BEMT or OLAF).

Counterpart of ``iea15mw/scripts/openfast_sweep.py`` (+ the ad-hoc extraction that
produced the IEA-15 ``spanwise_olaf.csv``): a rigid, fixed-speed, uniform-inflow
rotor, no controller and no generator DOF, so the run isolates the aerodynamics.
Templates: ``data/openfast-v5-templates`` (built by ``build_openfast_templates.py``).

    openfast_iea22.py setup  OUTDIR --wake bem|olaf [--speed U --rpm N --pitch P]
                             [--revs 4] [--olaf-panels N --olaf-free N]
                             [--tower on|off] [--tilt] [--name NAME]
    openfast_iea22.py sweep  OUTDIR --wake bem|olaf [--xlsx FILE] [--speeds U ...]
    openfast_iea22.py run    CASEDIR [--openfast BIN]        (run + extract)
    openfast_iea22.py extract CASEDIR [--revs N]             (metrics.json + spanwise.csv)

``extract`` averages over whole revolutions counted back from the end of the run and
writes ``metrics.json`` (power, thrust, torque, Cp, Ct, convergence) and
``spanwise.csv`` (``node,r_over_R,radius_m,Alpha,Cn,Ct,...``), the input of
``import_olaf_reference.py``. The source repository is untrusted data (hash-checked,
copied, never executed). Nothing here tunes a model coefficient.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
sys.path.insert(0, str(HERE))
import build_openfast_templates as tpl  # noqa: E402

TEMPLATES = tpl.DEFAULT_OUT
ROOT = tpl.ROOT
BLADE_CSV = PACKAGE / "data" / "iea22mw_blade.csv"
DEFAULT_SOURCE = tpl.DEFAULT_SOURCE
DEFAULT_XLSX = DEFAULT_SOURCE / "Documentation" / "IEA-22-280-RWT_tabular.xlsx"
OPENFAST = os.environ.get("OPENFAST_BIN", "/scratch/leahk/eduardo.donestevez/openfast-5.0.0-dp/bin/openfast")

AIR_DENSITY = 1.225
ROTOR_RADIUS = tpl.ROTOR_RADIUS
SWEPT_AREA = math.pi * ROTOR_RADIUS ** 2

#: sha256 of the staged source files (PROVENANCE.md; ElastoDyn blade file recorded in the template README).
BLADE_SHA256 = "828528ff3d19bb6ea6bb750ef596c9c40026f55daf71b64fa143ff4cab58cf85"
POLARS_COMBINED_SHA256 = "9700d9daaca0d9fac9eb3a2094aba900923212ad59d75684da9657c08d3b0dd1"
ED_BLADE_SHA256 = "0b7fb7f5e4d19bab0ede1f8a2ef80afbf7b42d663ff513777263653fa42f4459"

SPANWISE_COLUMNS = ("Alpha", "Cn", "Ct", "Vrel", "AxInd", "TnInd", "Fn", "Ft")
WORKBOOK_SHEET = "Rotor Performance - WISDEM"
SWEEP_DEFAULT_SPEEDS = (6.0, 8.0, 10.0, tpl.RATED_U, 13.0, 16.0, 20.0, 25.0)


# --- staging of the untrusted source files --------------------------------------
def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def polars_combined_sha(airfoil_dir: Path) -> str:
    lines = "".join(f"{_sha256(p)}  {p.name}\n" for p in sorted(airfoil_dir.glob("IEA-22-280-RWT_AeroDyn15_Polar_*.dat")))
    return hashlib.sha256(lines.encode()).hexdigest()


def stage_inputs(case_dir: Path, source_root: Path) -> None:
    """Copy blade table, ElastoDyn blade and the 59 polars into ``case_dir`` (hash-checked)."""
    base = source_root / "OpenFAST" / "IEA-22-280-RWT"
    blade, ed_blade, airfoils = base / "IEA-22-280-RWT_AeroDyn15_blade.dat", base / "IEA-22-280-RWT_ElastoDyn_blade.dat", base / "Airfoils"
    for path, expected in ((blade, BLADE_SHA256), (ed_blade, ED_BLADE_SHA256)):
        if _sha256(path) != expected:
            raise SystemExit(f"sha256 mismatch for {path}: not the commit recorded in PROVENANCE.md")
    if polars_combined_sha(airfoils) != POLARS_COMBINED_SHA256:
        raise SystemExit(f"polar set in {airfoils} differs from PROVENANCE.md")
    shutil.copy(blade, case_dir / "IEA-22-280-RWT_AeroDyn15_blade.dat")
    shutil.copy(ed_blade, case_dir / f"{ROOT}_ElastoDyn_blade.dat")
    (case_dir / "Airfoils").mkdir(exist_ok=True)
    # the polar files name their coordinate files (``..._AFnn_Coords.txt``); AirfoilInfo opens them
    for airfoil_file in sorted(airfoils.glob("IEA-22-280-RWT_*")):
        shutil.copy(airfoil_file, case_dir / "Airfoils" / airfoil_file.name)


# --- case construction ------------------------------------------------------------
def make_case(wake: str, speed: float, rpm: float, pitch: float, *, revs: float = 4.0, tower: bool = True,
              tilt: bool = False, olaf_panels: int | None = None, olaf_free: int | None = None,
              name: str | None = None) -> dict:
    """Pure description of one case (everything ``write_case`` needs); no file access."""
    if wake not in ("bem", "olaf"):
        raise ValueError(f"wake must be bem or olaf, not {wake!r}")
    period = 60.0 / rpm
    case = {"name": name or f"{wake}-U{speed:06.3f}-rpm{rpm:.3f}-p{pitch:.3f}", "wake": wake, "U": speed, "rpm": rpm,
            "pitch": pitch, "period_s": period, "tower": tower, "tilt": tilt, "revs": revs,
            "rho": AIR_DENSITY, "R": ROTOR_RADIUS}
    if wake == "bem":
        case.update(dt=period / 72.0, tmax=revs * period)  # 5 deg per step
    else:
        size = tpl.olaf_sizing(rpm, speed)
        near = int(olaf_panels if olaf_panels is not None else size["near"])
        free = int(olaf_free if olaf_free is not None else min(size["free"], near))
        steps_per_rev = round(period / size["dt"])
        case.update(dt=size["dt"], nNWPanels=near, guideline_panels=size["near"], nNWPanelsFree=free,
                    full_circ_start=min(size["full_circ_start"], near * size["dt"]),
                    wake_length_m=near * 0.5 * speed * size["dt"],
                    wake_revolutions=near / steps_per_rev,
                    tmax=(near + revs * steps_per_rev) * size["dt"])
    return case


def write_case(case: dict, out: Path, *, stage: bool = True, source_root: Path = DEFAULT_SOURCE,
               templates: Path = TEMPLATES) -> Path:
    directory = out / case["name"]
    directory.mkdir(parents=True, exist_ok=True)
    for source in templates.glob(f"{ROOT}*"):
        if source.suffix in (".dat", ".fst"):
            shutil.copy(source, directory / source.name)
    if stage:
        stage_inputs(directory, source_root)
    ed = directory / f"{ROOT}_ElastoDyn.dat"
    text = tpl.set_value(ed.read_text(), "RotSpeed", f"{case['rpm']:.6f}")
    for blade in (1, 2, 3):
        text = tpl.set_value(text, f"BlPitch({blade})", f"{case['pitch']:.6f}")
    if case["tilt"]:  # opt-in: the real 6 deg tilted shaft (templates are tilt 0)
        for key, value in tpl.TILTED_ED.items():
            text = tpl.set_value(text, key, value)
    ed.write_text(text)
    inflow = directory / f"{ROOT}_InflowFile.dat"
    inflow.write_text(tpl.set_value(inflow.read_text(), "HWindSpeed", f"{case['U']:.6f}"))
    fst = directory / f"{ROOT}.fst"
    text = tpl.set_value(fst.read_text(), "TMax", f"{case['tmax']:.4f}")
    fst.write_text(tpl.set_value(text, "DT", f"{case['dt']:.6f}"))
    ad = directory / f"{ROOT}_AeroDyn15.dat"
    text = ad.read_text()
    text = tpl.set_value(text, "Wake_Mod", "1" if case["wake"] == "bem" else "3")
    if not case["tower"]:
        for key, value in (("TwrPotent", "0"), ("TwrShadow", "0"), ("TwrAero", "False")):
            text = tpl.set_value(text, key, value)
    ad.write_text(text)
    if case["wake"] == "olaf":
        olaf = directory / f"{ROOT}_OLAF.dat"
        text = tpl.set_value(olaf.read_text(), "DTfvw", f"{case['dt']:.6f}")
        text = tpl.set_value(text, "FullCircStart", f"{case['full_circ_start']:.4f}")
        text = tpl.set_value(text, "nNWPanel", str(case["nNWPanels"]))
        text = tpl.set_value(text, "nNWPanelsFree", str(case["nNWPanelsFree"]))
        olaf.write_text(text)
    (directory / "case.json").write_text(json.dumps(case, indent=2) + "\n")
    return directory


def operating_table(xlsx: Path) -> list[tuple[float, float, float]]:
    import openpyxl
    sheet = openpyxl.load_workbook(xlsx, data_only=True)[WORKBOOK_SHEET]
    rows = sheet.iter_rows(values_only=True)
    header = [str(h) for h in next(rows)]
    wind, pitch, rpm = (header.index(n) for n in ("Wind [m/s]", "Pitch [deg]", "Rotor Speed [rpm]"))
    return [(r[wind], r[pitch], r[rpm]) for r in rows if isinstance(r[wind], (int, float))]


def sweep_cases(table, wake: str, speeds, **kwargs) -> list[dict]:
    cases = []
    for target in speeds:
        speed, pitch, rpm = min(table, key=lambda r: abs(r[0] - target))
        cases.append(make_case(wake, speed, rpm, pitch, **kwargs))
    return cases


# --- OpenFAST output --------------------------------------------------------------
UNIT_FACTORS = {"(kW)": 1e3, "(W)": 1.0, "(MW)": 1e6, "(kN)": 1e3, "(N)": 1.0, "(kN-m)": 1e3, "(N-m)": 1.0, "(kN·m)": 1e3}


def read_out(path: Path):
    """Return ``(header, units, rows)`` of an OpenFAST text output file."""
    lines = path.read_text(errors="replace").splitlines()
    start = next(i for i, l in enumerate(lines) if l.split() and l.split()[0] == "Time")
    header = lines[start].split()
    units = lines[start + 1].split()
    rows = [[float(v) for v in l.split()] for l in lines[start + 2:] if l.strip()]
    return header, units, rows


def _mean(rows, col, lo, hi):
    sel = [r[col] for r in rows if lo <= r[0] <= hi]
    return sum(sel) / len(sel) if sel else float("nan")


def blade_radii(csv_path: Path = BLADE_CSV) -> list[tuple[float, float]]:
    """``[(r_over_R, radius_m)]`` per AeroDyn node, node 1 first."""
    with csv_path.open() as handle:
        reader = csv.DictReader(line for line in handle if not line.startswith("#"))
        return [(float(r["r_over_R"]), float(r["radius_m"])) for r in reader]


def extract(case_dir: Path, revs: float | None = None) -> dict:
    case = json.loads((case_dir / "case.json").read_text())
    revs = revs if revs is not None else (1.0 if case["wake"] == "bem" else 2.0)
    path = case_dir / f"{ROOT}.out"
    header, units, rows = read_out(path)
    period, dt = case["period_s"], rows[1][0] - rows[0][0]
    t_end = rows[-1][0]
    lo, hi = t_end - revs * period + 0.5 * dt, t_end
    col = {name: i for i, name in enumerate(header)}
    factor = lambda name: UNIT_FACTORS.get(units[col[name]], 1.0)  # noqa: E731
    power = _mean(rows, col["RtAeroPwr"], lo, hi) * factor("RtAeroPwr")
    thrust = _mean(rows, col["RtAeroFxh"], lo, hi) * factor("RtAeroFxh")
    omega = case["rpm"] * 2.0 * math.pi / 60.0
    q = 0.5 * case["rho"] * case["U"] ** 2
    # last two whole revolutions: change of the per-revolution mean power
    prev = _mean(rows, col["RtAeroPwr"], t_end - 2 * period + 0.5 * dt, t_end - period) * factor("RtAeroPwr")
    last = _mean(rows, col["RtAeroPwr"], t_end - period + 0.5 * dt, t_end) * factor("RtAeroPwr")
    change = 100.0 * (last - prev) / prev if prev and t_end >= 2 * period else float("nan")
    filled = guideline = True
    if case["wake"] == "olaf":
        filled = (t_end - 2 * period) >= case["nNWPanels"] * case["dt"] - 0.5 * dt
        guideline = case["nNWPanels"] >= case.get("guideline_panels", case["nNWPanels"] + 1)  # a shorter wake is a smoke run, not a result
    metrics = {
        "wake": case["wake"], "U": case["U"], "rpm": case["rpm"], "pitch": case["pitch"], "tip_speed_ratio": omega * case["R"] / case["U"],
        "revolutions_averaged": revs, "t_end_s": t_end, "steps": len(rows), "tower": case["tower"], "tilt": case["tilt"],
        "power_w": power, "thrust_n": thrust, "torque_nm": power / omega,
        "cp": power / (q * case["U"] * SWEPT_AREA), "ct": thrust / (q * SWEPT_AREA),
        "cq": power / omega / (q * SWEPT_AREA * case["R"]),
        "cp_ad": _mean(rows, col["RtAeroCp"], lo, hi) if "RtAeroCp" in col else float("nan"),
        "ct_ad": _mean(rows, col["RtAeroCt"], lo, hi) if "RtAeroCt" in col else float("nan"),
        "rt_area_m2": _mean(rows, col["RtArea"], lo, hi) if "RtArea" in col else float("nan"),
        "power_change_last_rev_pct": change,
        "wake_filled": filled,
        "guideline_wake": guideline,
        "converged": bool(filled and guideline and abs(change) < 1.0),
    }
    radii = blade_radii()
    table = []
    for node, (r_over_r, radius) in enumerate(radii, start=1):
        row = {"node": node, "r_over_R": r_over_r, "radius_m": radius}
        for quantity in SPANWISE_COLUMNS:
            name = f"AB1N{node:03d}{quantity}"
            if name in col:
                row[quantity] = _mean(rows, col[name], lo, hi)
        table.append(row)
    fields = ["node", "r_over_R", "radius_m"] + [q for q in SPANWISE_COLUMNS if q in table[0]]
    with (case_dir / "spanwise.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({k: (f"{v:.10g}" if isinstance(v, float) else v) for k, v in row.items()} for row in table)
    (case_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    return metrics


def run_case(case_dir: Path, binary: str, revs: float | None) -> dict:
    with (case_dir / "run.log").open("w") as log:
        status = subprocess.run([binary, f"{ROOT}.fst"], cwd=case_dir, stdout=log, stderr=subprocess.STDOUT).returncode
    if status != 0:
        raise SystemExit(f"openfast exited {status}; see {case_dir / 'run.log'}")
    return extract(case_dir, revs)


# --- command line -----------------------------------------------------------------
def _case_kwargs(args) -> dict:
    return {"revs": args.revs, "tower": args.tower == "on", "tilt": args.tilt,
            "olaf_panels": args.olaf_panels, "olaf_free": args.olaf_free}


def cmd_setup(args) -> int:
    case = make_case(args.wake, args.speed, args.rpm, args.pitch, name=args.name, **_case_kwargs(args))
    directory = write_case(case, args.out, source_root=args.source_root)
    print(f"{directory}: dt {case['dt']:.5f} s, tmax {case['tmax']:.1f} s ({case['tmax'] / case['period_s']:.1f} rev)")
    return 0


def cmd_sweep(args) -> int:
    table = operating_table(args.xlsx)
    cases = sweep_cases(table, args.wake, args.speeds, **_case_kwargs(args))
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "cases.csv").open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["name", "U", "pitch", "rpm"])
        for case in cases:
            write_case(case, args.out, source_root=args.source_root)
            writer.writerow([case["name"], case["U"], case["pitch"], case["rpm"]])
    script = args.out / "run_all.sh"
    script.write_text(f"""#!/bin/sh
# Not submitted by the tooling: run on a node you own (one OpenFAST process per case).
cd "{args.out.resolve()}" || exit 1
tail -n +2 cases.csv | cut -d, -f1 | xargs -P "${{NPROC:-4}}" -I{{}} python3 -I "{HERE / 'openfast_iea22.py'}" run {{}}
""")
    print(f"{len(cases)} cases in {args.out}; run with: sh {script}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def common(p, sweep=False):
        p.add_argument("out", type=Path)
        p.add_argument("--wake", choices=("bem", "olaf"), required=True)
        p.add_argument("--revs", type=float, default=4.0, help="whole revolutions simulated after the OLAF wake is full (BEM: total)")
        p.add_argument("--olaf-panels", type=int, default=None, help="near-wake panels (default: guideline, >= 4 D and >= 10 rev)")
        p.add_argument("--olaf-free", type=int, default=None)
        p.add_argument("--tower", choices=("on", "off"), default="on")
        p.add_argument("--tilt", action="store_true", help="opt in to the real 6 deg shaft tilt (default: ShftTilt = 0, horizontal rotor axis, as the OpenFOAM case)")
        p.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)

    setup = sub.add_parser("setup", help="one case, default the rated point")
    common(setup)
    setup.add_argument("--speed", type=float, default=tpl.RATED_U)
    setup.add_argument("--rpm", type=float, default=tpl.RATED_RPM)
    setup.add_argument("--pitch", type=float, default=tpl.RATED_PITCH)
    setup.add_argument("--name", default=None)
    sweep = sub.add_parser("sweep", help="operating-table sweep from the tabular workbook")
    common(sweep)
    sweep.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    sweep.add_argument("--speeds", type=float, nargs="+", default=list(SWEEP_DEFAULT_SPEEDS))
    run = sub.add_parser("run", help="run OpenFAST in CASEDIR and extract")
    run.add_argument("case", type=Path)
    run.add_argument("--openfast", default=OPENFAST)
    run.add_argument("--revs", type=float, default=None)
    ext = sub.add_parser("extract", help="metrics.json and spanwise.csv from CASEDIR/<root>.out")
    ext.add_argument("case", type=Path)
    ext.add_argument("--revs", type=float, default=None)
    args = parser.parse_args(argv)
    if args.cmd == "setup":
        return cmd_setup(args)
    if args.cmd == "sweep":
        return cmd_sweep(args)
    if args.cmd == "run":
        metrics = run_case(args.case, args.openfast, args.revs)
    else:
        metrics = extract(args.case, args.revs)
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
