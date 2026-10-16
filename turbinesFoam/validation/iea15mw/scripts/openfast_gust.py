#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""IEC extreme operating gust (EOG) on the controlled IEA 15-240-RWT with OpenFAST.

Complements ``openfast_sweep.py`` (steady, fixed-rpm BEMT) with the transient the
sweep cannot represent: the pitch/torque controller (ROSCO ``libdiscon.so``)
reacting late to a gust, with the Beddoes-Leishman unsteady-airfoil model
(``UA_Mod`` 3 of the monopile AeroDyn file) and flexible blades/tower. The
monopile case of the IEA-15-240-RWT repository is used as shipped, changing only
the ServoDyn library path, a per-case uniform wind file, the initial rotor speed
and pitch, the end time and the output format (text). SeaState, HydroDyn and
SubDyn are switched off (their repository input files predate the OpenFAST v5
layout): the tower is cantilevered at the transition piece, so substructure
flexibility and waves are not represented, and the platform DOFs of ElastoDyn
(True in the repository file because SubDyn drives them) are switched off. The merged .fst/ElastoDyn files keep
the v5 layout of ``data/openfast-v5-templates`` with the monopile values.

EOG (IEC 61400-1 ed. 3, class IB: Vref = 50 m/s, Iref = 0.14, D = 240 m,
Lambda1 = 42 m), starting at ``--t-gust``:
    V_e1   = 0.8 * 1.4 * Vref
    V_gust = min(1.35 * (V_e1 - Vhub), 3.3 * sigma1 / (1 + 0.1 * D / Lambda1))
    V(t)   = Vhub - 0.37 * V_gust * sin(3 pi t / T) * (1 - cos(2 pi t / T)),  T = 10.5 s
    sigma1 = Iref * (0.75 * Vhub + 5.6)

Usage:
    openfast_gust.py setup OUTDIR --libdiscon PATH [--speeds 8 10.66 12.5 18] [--tmax 220]
    openfast_gust.py summarize OUTDIR
"""
import argparse
import csv
import math
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import openfast_sweep as sweep  # noqa: E402
import stall_margin  # noqa: E402

ROOT_DIR = HERE.parent
REPO = Path("/scratch/leahk/eduardo.donestevez/IEA-15-240-RWT/OpenFAST")
CASE_DIR = REPO / "IEA-15-240-RWT-Monopile"
SHARED_DIR = REPO / "IEA-15-240-RWT"
ROOT = "IEA-15-240-RWT-Monopile"
VREF, IREF, DIAMETER, LAMBDA1, PERIOD = 50.0, 0.14, 240.0, 42.0, 10.5


def eog_speed(v_hub, t):
    """EOG wind speed at time ``t`` (s) after the gust start."""
    sigma1 = IREF * (0.75 * v_hub + 5.6)
    v_gust = min(1.35 * (0.8 * 1.4 * VREF - v_hub), 3.3 * sigma1 / (1.0 + 0.1 * DIAMETER / LAMBDA1))
    if t < 0.0 or t > PERIOD:
        return v_hub
    return v_hub - 0.37 * v_gust * math.sin(3.0 * math.pi * t / PERIOD) * (1.0 - math.cos(2.0 * math.pi * t / PERIOD))


def wind_file(v_hub, t_gust, tmax, dt=0.05):
    lines = ["! EOG uniform wind file written by openfast_gust.py",
             "! Time  Wind  Wind  Vert.  Horiz.  Vert.  LinV  Gust",
             "! (s)   Speed Dir   Speed  Shear   Shear  Shear Speed"]
    n = int(round(tmax / dt)) + 1
    for i in range(n):
        t = i * dt
        lines.append(f"{t:.3f} {eog_speed(v_hub, t - t_gust):.4f} 0.0 0.0 0.0 0.0 0.0 0.0")
    return "\n".join(lines) + "\n"


def merge_fst(template, monopile):
    """The monopile .fst is in an older layout than OpenFAST v5.

    Keep the v5 layout of the committed template (extra keys such as
    ModCoupling, NRotors, CompSoil) and take every value the monopile file also
    defines, so the monopile modules, files and environment are kept.
    """
    def key_of(line):
        tokens = line.split()
        if len(tokens) > 2 and " - " in line and tokens[1][0].isalpha() and not line.startswith(("-", "!", "=")):
            return tokens[1]
        return None

    values = {key_of(l): l for l in monopile.splitlines() if key_of(l)}
    merged = [values.get(key_of(l), l) for l in template.splitlines()]
    return "\n".join(merged) + "\n"


def cmd_setup(args):
    table = sweep.operating_table(args.xlsx)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    shared = out / "IEA-15-240-RWT"
    if not shared.exists():
        shutil.copytree(SHARED_DIR, shared)
    rows = []
    for v_hub in args.speeds:
        u, pitch, rpm = min(table, key=lambda r: abs(r[0] - v_hub))
        name = f"eog-U{v_hub:05.2f}"
        root = out / name
        if root.exists():
            shutil.rmtree(root)
        case = root / ROOT
        shutil.copytree(CASE_DIR, case)
        (root / "IEA-15-240-RWT").symlink_to(shared)
        (case / "gust.wnd").write_text(wind_file(v_hub, args.t_gust, args.tmax))
        inflow = (shared / "IEA-15-240-RWT_InflowFile.dat").read_text()
        inflow = sweep.set_value(inflow, "WindType", "2")
        inflow = sweep.set_value(inflow, "Filename_Uni", '"gust.wnd"')
        (case / "InflowFile.dat").write_text(inflow)
        template = (sweep.TEMPLATE / f"{sweep.ROOTNAME}.fst").read_text()
        fst = merge_fst(template, (case / f"{ROOT}.fst").read_text())
        fst = sweep.set_value(fst, "TMax", f"{args.tmax:.1f}")
        fst = sweep.set_value(fst, "OutFileFmt", "1")
        for module in ("CompSeaSt", "CompHydro", "CompSub"):
            fst = sweep.set_value(fst, module, "0")
        fst = sweep.set_value(fst, "InflowFile", '"InflowFile.dat"')
        (case / f"{ROOT}.fst").write_text(fst)
        servo = merge_fst((ROOT_DIR / "data" / "openfast-v5-templates" / "ServoDyn_r-test_v5.0.0.dat").read_text(),
                          (case / f"{ROOT}_ServoDyn.dat").read_text())
        (case / f"{ROOT}_ServoDyn.dat").write_text(sweep.set_value(servo, "DLL_FileName", f'"{args.libdiscon}"'))
        ed = merge_fst((sweep.TEMPLATE / f"{sweep.ROOTNAME}_ElastoDyn.dat").read_text(),
                       (case / f"{ROOT}_ElastoDyn.dat").read_text())
        ed = sweep.set_value(ed, "RotSpeed", f"{rpm:.6f}")
        for blade in (1, 2, 3):
            ed = sweep.set_value(ed, f"BlPitch({blade})", f"{pitch:.6f}")
        for dof in ("PtfmSgDOF", "PtfmSwDOF", "PtfmHvDOF", "PtfmRDOF", "PtfmPDOF", "PtfmYDOF"):
            ed = sweep.set_value(ed, dof, "False")
        (case / f"{ROOT}_ElastoDyn.dat").write_text(ed)
        (case / f"{ROOT}_AeroDyn15.dat").write_text(
            merge_fst((sweep.TEMPLATE / f"{sweep.ROOTNAME}_AeroDyn15.dat").read_text(),
                      (case / f"{ROOT}_AeroDyn15.dat").read_text()))
        rows.append({"name": name, "Vhub": v_hub, "rpm0": rpm, "pitch0": pitch, "t_gust": args.t_gust})
    with (out / "cases.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (out / "run_gust.slurm").write_text(f"""#!/bin/bash
#SBATCH -p sequana_cpu
#SBATCH --ntasks={len(rows)}
#SBATCH -J of-gust
#SBATCH --time=02:00:00
#SBATCH -e %j.err
#SBATCH -o %j.out
set -eu
export OMP_NUM_THREADS=1
export LD_LIBRARY_PATH={Path(args.libdiscon).parent}:${{LD_LIBRARY_PATH:-}}
cd "{out.resolve()}"
run_one() {{ (cd "$1/{ROOT}" && {sweep.OPENFAST} {ROOT}.fst > run.log 2>&1); }}
export -f run_one
tail -n +2 cases.csv | cut -d, -f1 | xargs -P {len(rows)} -I{{}} bash -c 'run_one {{}}'
""")
    print(f"{len(rows)} cases in {out}; submit with: sbatch {out / 'run_gust.slurm'}")
    return 0


def cmd_summarize(args):
    blade = stall_margin.read_blade()
    cache = {}
    for case in csv.DictReader((args.out / "cases.csv").open()):
        path = args.out / case["name"] / ROOT / f"{ROOT}.out"
        if not path.exists():
            print(f"{case['name']}: no output")
            continue
        header, rows = sweep.read_out(path)
        cols = sweep.alpha_columns(header)
        t_gust = float(case["t_gust"])
        window = [r for r in rows if t_gust - 10.0 <= r[0] <= t_gust + 60.0]
        worst = None
        for node, col in cols.items():
            r_r, index = blade[node - 1]
            if not args.rmin < r_r <= args.rmax:
                continue
            if index not in cache:
                cache[index] = stall_margin.polar_metrics(stall_margin.read_polar(stall_margin.POLARS_DIR / f"polar_{index:02d}.dat"))
            m = cache[index]
            peak = max(window, key=lambda r: r[col])
            if m and m["alpha_clmax"] is not None:
                margin = m["alpha_clmax"] - peak[col]
                dev = (m["alpha_dev"] - peak[col]) if m["alpha_dev"] is not None else float("nan")
                if worst is None or margin < worst[0]:
                    worst = (margin, dev, r_r, peak[col], peak[0])
        print(f"== {case['name']}  Vhub={case['Vhub']}  (window t={t_gust - 10:.0f}..{t_gust + 60:.0f} s, r/R in ({args.rmin}, {args.rmax}])")
        if worst:
            print(f"   peak alpha {worst[3]:.1f} deg at r/R {worst[2]:.2f}, t={worst[4]:.1f} s; margin to cl_max {worst[0]:.1f}, to departure {worst[1]:.1f} deg")
        for name in ("RotSpeed", "BldPitch1", "GenPwr", "RtFldCt", "Wind1VelX", "RtVAvgxh"):
            if name in header:
                col = header.index(name)
                values = [r[col] for r in window]
                print(f"   {name:<10} min {min(values):9.3f}  max {max(values):9.3f}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    setup = sub.add_parser("setup")
    setup.add_argument("out", type=Path)
    setup.add_argument("--libdiscon", required=True)
    setup.add_argument("--speeds", type=float, nargs="+", default=[8.0, 10.66, 12.5, 18.0])
    setup.add_argument("--tmax", type=float, default=220.0)
    setup.add_argument("--t-gust", type=float, default=120.0)
    setup.add_argument("--xlsx", type=Path, default=sweep.DEFAULT_XLSX)
    summarize = sub.add_parser("summarize")
    summarize.add_argument("out", type=Path)
    summarize.add_argument("--rmin", type=float, default=0.5, help="exclusive lower r/R bound")
    summarize.add_argument("--rmax", type=float, default=1.0)
    args = parser.parse_args(argv)
    return cmd_setup(args) if args.cmd == "setup" else cmd_summarize(args)


if __name__ == "__main__":
    sys.exit(main())
