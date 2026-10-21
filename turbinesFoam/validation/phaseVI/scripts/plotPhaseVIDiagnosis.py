#!/usr/bin/env python3
"""Spanwise diagnosis of one Phase VI run, for review by eye.

Reads the element CSVs of a run, averages the four ladder revolutions and plots
the four quantities that explain the power deficit: the Glauert end-effect factor,
the angle of attack, the effective lift, and the chord-referenced normal load
against the five instrumented stations of the experiment.

Usage:
    python3 scripts/plotPhaseVIDiagnosis.py runs/alm-U7-coarse analysis/spanwise-diagnosis.png
"""
from __future__ import annotations
import sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from comparePhaseVI import read_rows_resumed  # noqa: E402

R, CUT = 5.029, 0.5083
STATIONS = [0.30, 0.47, 0.63, 0.80, 0.95]
MEASURED_CN = {0.30: 0.8139, 0.47: 0.9204, 0.63: 0.8668, 0.80: 0.7673, 0.95: 0.5175}
MEASURED_CT = {0.30: 0.0973, 0.47: 0.1184, 0.63: 0.0956, 0.80: 0.0730, 0.95: 0.0407}


def read_run(run_dir: Path, discard_revs: float = 1.0):
    period = 2.0 * 3.141592653589793 * R / (5.408 * 7.0)
    out = []
    for path in sorted(run_dir.glob("postProcessing/actuatorLineElements/0/*.csv")):
        rows = [r for r in read_rows_resumed(Path(path)) if float(r["time"]) >= discard_revs * period]
        if not rows:
            continue
        mean = lambda k: sum(float(r[k]) for r in rows) / len(rows)   # noqa: E731
        rr = CUT / R + mean("root_dist") * (1.0 - CUT / R)
        out.append((rr, mean("end_effect_factor"), mean("alpha_deg"), mean("alpha_geom_deg"),
                    mean("cl"), mean("cd"), mean("c_ref_n"), mean("c_ref_t")))
    return sorted(out)


def main(argv):
    run = Path(argv[1] if len(argv) > 1 else "runs/alm-U7-coarse")
    out = Path(argv[2] if len(argv) > 2 else "analysis/spanwise-diagnosis.png")
    data = read_run(run)
    if not data:
        raise SystemExit(f"no element CSVs under {run}")
    rr = [d[0] for d in data]
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.suptitle(f"Phase VI spanwise diagnosis — {run}   (mean of revolutions 1-4)", fontsize=13)

    ax = axes[0][0]
    ax.plot(rr, [d[1] for d in data], "o-", color="crimson")
    ax.axhline(1.0, color="grey", ls=":", lw=1)
    for s in STATIONS:
        ax.axvline(s, color="grey", ls="--", lw=0.7, alpha=0.5)
    ax.set(title="Glauert end-effect factor (the multiplier on lift)",
           xlabel="r/R", ylabel="factor", ylim=(0, 1.1))
    ax.grid(alpha=0.3)

    ax = axes[0][1]
    ax.plot(rr, [d[2] for d in data], "o-", label="alpha (effective)")
    ax.plot(rr, [d[3] for d in data], "s--", label="alpha (geometric)")
    ax.set(title="Angle of attack", xlabel="r/R", ylabel="alpha [deg]")
    ax.legend(); ax.grid(alpha=0.3)

    ax = axes[1][0]
    ax.plot(rr, [d[4] for d in data], "o-", color="darkgreen", label="cl (post end-effect)")
    ax.plot(rr, [d[5] for d in data], "s-", color="darkorange", label="cd (post end-effect)")
    ax.set(title="Section coefficients actually used for the force",
           xlabel="r/R", ylabel="coefficient")
    ax.legend(); ax.grid(alpha=0.3)

    ax = axes[1][1]
    ax.plot(rr, [d[6] for d in data], "-", color="navy", label="sim c_ref_n (plane)")
    ax.plot(STATIONS, [MEASURED_CN[s] for s in STATIONS], "ko", ms=9, label="measured CN")
    ax.plot(rr, [d[7] for d in data], "-", color="teal", label="sim c_ref_t (plane)")
    ax.plot(STATIONS, [MEASURED_CT[s] for s in STATIONS], "k^", ms=8, label="measured CT")
    ax.set(title="Loads: simulation vs the five instrumented stations",
           xlabel="r/R", ylabel="coefficient")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)

    fig.tight_layout(rect=(0, 0, 1, 0.97))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140)
    print(f"wrote {out}")
    print(f"{'r/R':>6} {'endEff':>8} {'alpha':>7} {'cl':>8} {'cd':>7} {'c_ref_n':>8} {'c_ref_t':>8}")
    for d in data[::3]:
        print(f"{d[0]:>6.3f} {d[1]:>8.4f} {d[2]:>7.2f} {d[4]:>8.4f} {d[5]:>7.4f} {d[6]:>8.4f} {d[7]:>8.4f}")


if __name__ == "__main__":
    main(sys.argv)
