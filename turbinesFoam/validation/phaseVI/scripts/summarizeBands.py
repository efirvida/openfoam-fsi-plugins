#!/usr/bin/env python3
"""Judge comparePhaseVI.py outputs against the pre-registered bands.

Bands (validation-model-definition.md): |dP| <= 10 %, |dT| <= 15 %,
c_n +-10 % at r/R 0.47-0.80, +-15 % at 0.30, 0.95 reported only.
Usage: summarizeBands.py <cmp_dir> [<cmp_dir> ...]
"""
import csv
import sys
from pathlib import Path

CN_BAND = {0.30: 0.15, 0.47: 0.10, 0.63: 0.10, 0.80: 0.10}


def main(dirs):
    for d in map(Path, dirs):
        print(f"== {d.name}")
        with open(d / "turbine_comparison.csv") as f:
            for r in csv.DictReader(f):
                if r["quantity"] not in ("power", "thrust"):
                    continue
                band = 0.10 if r["quantity"] == "power" else 0.15
                dv = float(r["delta_frac"])
                print(f"  {r['quantity']:6s} sim {float(r['sim']):9.2f} exp {float(r['experiment']):9.2f} "
                      f"{100*dv:+6.1f} %  band {100*band:.0f} %  {'PASS' if abs(dv) <= band else 'FAIL'}")
        with open(d / "spanwise_comparison.csv") as f:
            for r in csv.DictReader(f):
                x = round(float(r["r_over_R"]), 2)
                dv = float(r["dcn_frac"])
                b = CN_BAND.get(x)
                tag = "report" if b is None else ("PASS" if abs(dv) <= b else "FAIL")
                print(f"  c_n r/R {x:.2f} sim {float(r['c_ref_n']):.3f} exp {float(r['cn_exp']):.3f} {100*dv:+6.1f} %  {tag}")


if __name__ == "__main__":
    main(sys.argv[1:])
