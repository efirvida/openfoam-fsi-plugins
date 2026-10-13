#!/usr/bin/env python3
"""P1.5 E3: relative change of turbine and spanwise loads, equispaced vs committed layout.

Reads the `turbine_comparison.csv` / `spanwise_comparison.csv` written by
`comparePhaseVI.py --out <dir>` for a test arm and its reference arm and prints
the relative change of the simulated values (test/ref - 1). Acceptance bound:
the ALM-vs-ASM cp difference of the Model Definition (2 %).

usage: compareEquispacedArms.py TEST_DIR:REF_DIR [TEST_DIR:REF_DIR ...] [--bound 0.02]
"""
import argparse
import csv
import sys
from pathlib import Path


def rows(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pairs", nargs="+", help="TEST_DIR:REF_DIR of comparePhaseVI output dirs")
    ap.add_argument("--bound", type=float, default=0.02)
    args = ap.parse_args()
    worst = 0.0
    for pair in args.pairs:
        test, ref = (Path(p) for p in pair.split(":"))
        print(f"== {test.name} vs {ref.name}")
        for t, r in zip(rows(test / "turbine_comparison.csv"), rows(ref / "turbine_comparison.csv")):
            d = float(t["sim"]) / float(r["sim"]) - 1.0
            worst = max(worst, abs(d))
            print(f"  {t['quantity']:7s} {float(r['sim']):10.4f} -> {float(t['sim']):10.4f}  {100*d:+.3f} %")
        for t, r in zip(rows(test / "spanwise_comparison.csv"), rows(ref / "spanwise_comparison.csv")):
            dn = float(t["c_ref_n"]) / float(r["c_ref_n"]) - 1.0
            dt = float(t["c_ref_t"]) / float(r["c_ref_t"]) - 1.0
            worst = max(worst, abs(dn), abs(dt))
            print(f"  r/R {t['r_over_R']}  cn {100*dn:+.3f} %  ct {100*dt:+.3f} %")
    verdict = "WITHIN" if worst <= args.bound else "OUTSIDE"
    print(f"max |change| = {100*worst:.3f} % -> {verdict} bound {100*args.bound:.1f} %")
    return 0 if worst <= args.bound else 3


if __name__ == "__main__":
    sys.exit(main())
