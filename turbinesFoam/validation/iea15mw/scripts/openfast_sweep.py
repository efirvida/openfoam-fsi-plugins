#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Operating-envelope sweep of the IEA 15-240-RWT with standalone OpenFAST (BEMT).

``setup`` builds one case directory per operating point from the committed
OpenFAST rated case (``data/openfast-v5-templates``): the published operating table
(``IEA-15-240-RWT_tabular.xlsx``, sheet "Rotor Performance": wind speed, pitch,
rotor speed) plus off-design perturbations at a few wind speeds (nacelle yaw,
power-law shear, a static overspeed gust). The rotor speed is fixed (no
generator DOF, no controller), so the run isolates the aerodynamics.

``summarize`` reads the per-node blade-1 angle of attack of every finished case
over its last rotor revolutions and reports the stall margin per case with the
same polar descriptors as ``stall_margin.py``.

Usage:
    openfast_sweep.py setup OUTDIR [--tmax 90] [--xlsx FILE]
    openfast_sweep.py summarize OUTDIR [--revs 2] [--margin 3]
"""
import argparse
import csv
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import stall_margin  # noqa: E402

TEMPLATE = ROOT / "data" / "openfast-v5-templates"
ROOTNAME = "IEA-15-240-RWT-OLAF_rated"
DEFAULT_XLSX = Path("/scratch/leahk/eduardo.donestevez/IEA-15-240-RWT/Documentation/IEA-15-240-RWT_tabular.xlsx")
OPENFAST = "/scratch/leahk/eduardo.donestevez/conda-envs/openfast/bin/openfast"

#: Wind speeds (m/s) at which the off-design perturbations are applied.
PERTURB_AT = (6.0, 8.0, 10.6, 13.0, 18.0, 25.0)
YAW_DEG = 15.0
SHEAR_EXP = 0.2
GUST_FACTOR = 1.15


def operating_table(xlsx):
    import openpyxl
    sheet = openpyxl.load_workbook(xlsx, data_only=True)["Rotor Performance"]
    rows = sheet.iter_rows(values_only=True)
    header = [str(h) for h in next(rows)]
    wind, pitch, rpm = (header.index(n) for n in ("Wind [m/s]", "Pitch [deg]", "Rotor Speed [rpm]"))
    return [(r[wind], r[pitch], r[rpm]) for r in rows if isinstance(r[wind], (int, float))]


def build_cases(table):
    cases = [{"name": f"base-U{u:05.2f}", "U": u, "pitch": p, "rpm": n, "yaw": 0.0, "shear": 0.0}
             for u, p, n in table]
    for target in PERTURB_AT:
        u, p, n = min(table, key=lambda r: abs(r[0] - target))
        tag = f"U{u:05.2f}"
        cases += [
            {"name": f"yawp-{tag}", "U": u, "pitch": p, "rpm": n, "yaw": YAW_DEG, "shear": 0.0},
            {"name": f"yawm-{tag}", "U": u, "pitch": p, "rpm": n, "yaw": -YAW_DEG, "shear": 0.0},
            {"name": f"shear-{tag}", "U": u, "pitch": p, "rpm": n, "yaw": 0.0, "shear": SHEAR_EXP},
            {"name": f"gust-{tag}", "U": u * GUST_FACTOR, "pitch": p, "rpm": n, "yaw": 0.0, "shear": 0.0},
        ]
    return cases


def set_value(text, key, value):
    """Replace the leading value of the input line that documents ``key``."""
    pattern = re.compile(rf"^(\s*)\S+(\s+{re.escape(key)}(?!\w))", re.M)
    new, count = pattern.subn(lambda m: f"{m.group(1)}{value}{m.group(2)}", text, count=1)
    if count != 1:
        raise KeyError(key)
    return new


def write_case(case, out, tmax):
    directory = out / case["name"]
    directory.mkdir(parents=True, exist_ok=True)
    for source in TEMPLATE.glob(f"{ROOTNAME}*"):
        if source.suffix in (".dat", ".fst"):
            shutil.copy(source, directory / source.name)
    ed = directory / f"{ROOTNAME}_ElastoDyn.dat"
    text = ed.read_text()
    text = set_value(text, "RotSpeed", f"{case['rpm']:.6f}")
    text = set_value(text, "NacYaw", f"{case['yaw']:.3f}")
    for blade in (1, 2, 3):
        text = set_value(text, f"BlPitch({blade})", f"{case['pitch']:.6f}")
    ed.write_text(text)
    inflow = directory / f"{ROOTNAME}_InflowFile.dat"
    text = set_value(inflow.read_text(), "HWindSpeed", f"{case['U']:.6f}")
    inflow.write_text(set_value(text, "PLexp", f"{case['shear']:.3f}"))
    fst = directory / f"{ROOTNAME}.fst"
    fst.write_text(set_value(fst.read_text(), "TMax", f"{tmax:.1f}"))


def cmd_setup(args):
    cases = build_cases(operating_table(args.xlsx))
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "cases.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "U", "pitch", "rpm", "yaw", "shear"])
        writer.writeheader()
        for case in cases:
            write_case(case, args.out, args.tmax)
            writer.writerow(case)
    slurm = args.out / "run_case.slurm"
    slurm.write_text(f"""#!/bin/bash
#SBATCH -p sequana_cpu
#SBATCH --ntasks=12
#SBATCH -J of-sweep
#SBATCH --time=01:00:00
#SBATCH -e %j.err
#SBATCH -o %j.out
set -eu
export OMP_NUM_THREADS=1
cd "{args.out.resolve()}"
run_one() {{ (cd "$1" && {OPENFAST} {ROOTNAME}.fst > run.log 2>&1); }}
export -f run_one
tail -n +2 cases.csv | cut -d, -f1 | xargs -P 12 -I{{}} bash -c 'run_one {{}}'
""")
    print(f"{len(cases)} cases in {args.out}; submit with: sbatch {slurm}")
    return 0


def read_out(path):
    """Return (header, rows) of an OpenFAST text output file."""
    lines = path.read_text().splitlines()
    start = next(i for i, l in enumerate(lines) if l.split() and l.split()[0] == "Time")
    header = lines[start].split()
    rows = [[float(v) for v in l.split()] for l in lines[start + 2:] if l.strip()]
    return header, rows


def alpha_columns(header):
    pattern = re.compile(r"^(?:AB1N|B1N|)(\d+)Alpha|^Alpha_?\[?(\d+)")
    cols = {}
    for i, name in enumerate(header):
        m = re.match(r"^(?:AB1N|B1N)(\d+)Alpha", name)
        if m:
            cols[int(m.group(1))] = i
    return cols


def find_nodal_out(directory):
    for path in sorted(directory.glob("*.out")):
        if path.name in ("run.out",):
            continue
        try:
            header, _ = read_out(path)
        except StopIteration:
            continue
        if alpha_columns(header):
            return path
    return None


def cmd_summarize(args):
    blade = stall_margin.read_blade()
    cache = {}
    with (args.out / "cases.csv").open() as handle:
        cases = list(csv.DictReader(handle))
    print("case                    U     rpm  pitch  alphaMax(zone)      minMarginMax  minMarginDev  worst r/R  flags(outer)")
    summary = []
    for case in cases:
        path = find_nodal_out(args.out / case["name"])
        if path is None:
            print(f"{case['name']:<22} (no nodal output)")
            continue
        header, rows = read_out(path)
        cols = alpha_columns(header)
        period = 60.0 / float(case["rpm"])
        t_end = rows[-1][0]
        window = [r for r in rows if r[0] >= t_end - args.revs * period]
        worst = None
        flags = {"ok": 0, "NEAR": 0, "NONLIN": 0, "STALL": 0}
        alpha_outer = 0.0
        for node, col in cols.items():
            r_r, index = blade[node - 1][0], blade[node - 1][1]
            if not args.rmin < r_r <= args.rmax:
                continue
            if index not in cache:
                cache[index] = stall_margin.polar_metrics(stall_margin.read_polar(stall_margin.POLARS_DIR / f"polar_{index:02d}.dat"))
            metrics = cache[index]
            alpha = max(r[col] for r in window)
            alpha_outer = max(alpha_outer, alpha)
            flag = stall_margin.classify(alpha, metrics, args.margin)
            flags[flag if flag in flags else "ok"] += 1
            if metrics and metrics["alpha_clmax"] is not None:
                margin_max = metrics["alpha_clmax"] - alpha
                margin_dev = (metrics["alpha_dev"] - alpha) if metrics["alpha_dev"] is not None else float("nan")
                if worst is None or margin_max < worst[0]:
                    worst = (margin_max, margin_dev, r_r)
        mm, md, rr = worst if worst else (float("nan"),) * 3
        print(f"{case['name']:<22} {float(case['U']):5.2f} {float(case['rpm']):6.3f} {float(case['pitch']):6.2f}   {alpha_outer:8.1f}         {mm:8.1f}      {md:8.1f}      {rr:.2f}   "
              + " ".join(f"{k}={v}" for k, v in flags.items() if v))
        summary.append({"case": case["name"], "alpha_outer_max": alpha_outer, "margin_clmax": mm, "margin_dev": md, "r_R_worst": rr})
    with (args.out / "stall_margin_summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]) if summary else ["case"])
        writer.writeheader()
        writer.writerows(summary)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    setup = sub.add_parser("setup")
    setup.add_argument("out", type=Path)
    setup.add_argument("--tmax", type=float, default=90.0)
    setup.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    summarize = sub.add_parser("summarize")
    summarize.add_argument("out", type=Path)
    summarize.add_argument("--rmin", type=float, default=0.5, help="exclusive lower r/R bound")
    summarize.add_argument("--rmax", type=float, default=1.0)
    summarize.add_argument("--revs", type=float, default=2.0)
    summarize.add_argument("--margin", type=float, default=3.0)
    args = parser.parse_args(argv)
    return cmd_setup(args) if args.cmd == "setup" else cmd_summarize(args)


if __name__ == "__main__":
    sys.exit(main())
