# SPDX-License-Identifier: GPL-3.0-or-later
"""Smoke contract for `plotComparisonFigures.py` on synthetic comparison output.

The directories below mimic what `comparePhaseVI.py --out` writes; no run data
is read and no figure content is judged, only that every figure is produced
from the documented inputs.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR.parent / "validation" / "phaseVI" / "scripts"))

import plotComparisonFigures as figures  # noqa: E402

MODELS = ("alm", "asm", "asm-mesh")
STATIONS = ("0.30", "0.47", "0.63", "0.80", "0.95")


def write_comparison(root: Path, speed: float, models=MODELS) -> Path:
    out = root / f"U{speed:g}"
    out.mkdir(parents=True)
    with (out / "turbine_comparison.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["model", "quantity", "sim", "experiment", "delta_frac",
                         "band_frac", "within_band", "units"])
        for model in models:
            for quantity, sim, exp in (("power", 5.0, 6.0), ("torque", 700.0, 790.0),
                                       ("thrust", 1100.0, 1130.0)):
                writer.writerow([model, quantity, sim, exp, (sim - exp) / exp, 0.15,
                                 "yes", "u"])
    with (out / "spanwise_comparison.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["model", "r_over_R", "c_ref_n", "cn_exp", "dcn_frac", "c_ref_t",
                         "ct_exp", "dct_frac", "within_band", "c_ref_n_plane", "cth_exp",
                         "c_ref_t_plane", "ctq_exp"])
        for model in models:
            for station in STATIONS:
                writer.writerow([model, station, 0.9, 0.8, 0.125, 0.1, 0.09, 0.11,
                                 "yes", 0.85, 0.8, 0.3, 0.3])
    metrics = {"window": {"discard_revolutions": 1, "end_revolutions": 3}, "models": {}}
    for model in models:
        run = root / f"run-{model}-{speed:g}"
        (run / figures.TURBINE_CSV.parent).mkdir(parents=True)
        with (run / figures.TURBINE_CSV).open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["time", "tsr", "cp"])
            for step in range(1, 40):
                writer.writerow([step * 0.05, 5.4, 0.3])
        metrics["models"][model] = {
            "metrics": {"run_dir": str(run)},
            "drift": {"cp": {"per_revolution": [0.30, 0.31]}},
        }
    (out / "metrics.json").write_text(json.dumps(metrics))
    return out


def test_p21_writes_every_figure(tmp_path):
    cases = [str(f"{s}={write_comparison(tmp_path, s)}") for s in (7.0, 10.0)]
    out_dir = tmp_path / "figs"
    assert figures.main(["p21", "--out-dir", str(out_dir), "--case", *cases[:1],
                         "--case", cases[1]]) == 0
    names = sorted(path.name for path in out_dir.glob("*.png"))
    assert names == ["p21-cp-drift.png", "p21-cp-history.png", "p21-spanwise-chord.png",
                     "p21-spanwise-error.png", "p21-spanwise-plane.png",
                     "p21-turbine-loads.png"]


def test_eps_writes_turbine_and_spanwise_figures(tmp_path):
    reference = write_comparison(tmp_path / "ref", 7.0, models=("alm",))
    arms = []
    for ratio in (1, 2, 4):
        arm = write_comparison(tmp_path / f"arm{ratio}", 7.0, models=("asm",))
        arms += ["--arm", f"{ratio}={arm}"]
    out_dir = tmp_path / "figs"
    assert figures.main(["eps", "--out-dir", str(out_dir), "--reference",
                         str(reference), *arms]) == 0
    assert sorted(p.name for p in out_dir.glob("*.png")) == [
        "p14-epsilon-spanwise.png", "p14-epsilon-turbine.png"]
