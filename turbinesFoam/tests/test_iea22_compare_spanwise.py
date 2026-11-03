# SPDX-License-Identifier: GPL-3.0-or-later
"""IEA-22 spanwise ALM-versus-reference comparison: window, radius map, band ratios."""
from __future__ import annotations

import csv
import importlib.util
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "validation" / "iea22mw" / "scripts"
TOOL = SCRIPTS / "compare_spanwise.py"
# iea15mw ships a module with the same name: load the IEA-22 one under its own name.
_spec = importlib.util.spec_from_file_location("iea22_blade_geometry", SCRIPTS.parent / "tools" / "blade_geometry.py")
bg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bg)

HEADER = ("time,root_dist,x,y,z,rel_vel_mag,Re,alpha_deg,alpha_geom_deg,cl,cd,fx,fy,fz,"
          "end_effect_factor,c_ref_t,c_ref_n,f_ref_t,f_ref_n\n")


def _element(path, root_dist, alpha, cn, ct):
    # t=0.5 lies before the 1 s window (60/rpm = 1 s, rpm 60) and must be ignored.
    rows = [(0.5, 99.0, 99.0, 99.0)] + [(1.0 + 0.25 * k, alpha, cn, ct) for k in range(1, 5)]
    path.write_text(HEADER + "".join(
        f"{t},{root_dist},0,0,0,0,0,{a},{a},0,0,0,0,0,1,{c_t},{c_n},0,0\n" for t, a, c_n, c_t in rows))


def _case(tmp_path, cn_alm):
    run = tmp_path / "run"
    elements = run / "postProcessing" / "actuatorLineElements" / "0"
    elements.mkdir(parents=True)
    store = tmp_path / "store.csv"
    lines = ["source,quantity,r_over_R_or_radius_m,value,unit,note\n"]
    for k, root_dist in enumerate((0.1, 0.5, 0.9)):
        _element(elements / f"turbine.blade1.element{k}.csv", root_dist, 5.0 + k, cn_alm, 0.1)
        r_over_R = (bg.HUB_RADIUS + root_dist * bg.BLADE_SPAN) / bg.TIP_RADIUS_STRUCTURAL
        for quantity, value in (("alpha_deg", 4.0 + k), ("cn", 1.0), ("ct", 0.1)):
            lines.append(f"olaf-fvw,{quantity},{r_over_R},{value},-,n\n")
    store.write_text("".join(lines))
    return run, store


def test_ratios_use_the_last_window_and_the_structural_radius(tmp_path):
    run, store = _case(tmp_path, cn_alm=1.1)
    out = tmp_path / "out.csv"
    result = subprocess.run(
        [sys.executable, "-I", str(TOOL), "--run-dir", str(run), "--rpm", "60", "--revs", "1",
         "--store", str(store), "--source", "olaf-fvw", "--out", str(out), "--bands", "0.0-0.5,0.5-1.0"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    rows = list(csv.DictReader(out.open()))
    assert [round(float(r["alpha_deg"]), 6) for r in rows] == [5.0, 6.0, 7.0]
    assert [round(float(r["cn_ratio"]), 6) for r in rows] == [1.1, 1.1, 1.1]
    assert [round(float(r["dalpha_deg"]), 6) for r in rows] == [1.0, 1.0, 1.0]
    assert "band 0.0-0.5" in result.stdout and "band 0.5-1.0" in result.stdout


def test_missing_elements_exit_nonzero(tmp_path):
    result = subprocess.run([sys.executable, "-I", str(TOOL), "--run-dir", str(tmp_path / "none")],
                            capture_output=True, text=True)
    assert result.returncode == 1 and "no element" in result.stderr
