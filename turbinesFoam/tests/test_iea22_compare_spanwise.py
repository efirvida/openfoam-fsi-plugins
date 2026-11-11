# SPDX-License-Identifier: GPL-3.0-or-later
"""IEA-22 spanwise ALM-versus-reference comparison: window, radius map, band ratios."""
from __future__ import annotations

import csv
import importlib.util
import json
import math
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


def _element(path, root_dist, alpha, cn, ct, f_t=0.0):
    # t=0.5 lies before the 1 s window (60/rpm = 1 s, rpm 60) and must be ignored.
    rows = [(0.5, 99.0, 99.0, 99.0)] + [(1.0 + 0.25 * k, alpha, cn, ct) for k in range(1, 5)]
    path.write_text(HEADER + "".join(
        f"{t},{root_dist},0,0,0,0,0,{a},{a},0,0,0,0,0,1,{c_t},{c_n},{f_t},0\n" for t, a, c_n, c_t in rows))


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


PITCH = 4.0


def _theta_deg(r_over_R):
    """Twist plus collective pitch at ``r/R`` from the committed IEA-22 geometry table."""
    table = bg.read_geometry()
    xs = [row["r_over_R"] for row in table]
    ys = [row["twist_deg"] for row in table]
    for k in range(1, len(xs)):
        if r_over_R <= xs[k]:
            weight = (r_over_R - xs[k - 1]) / (xs[k] - xs[k - 1])
            return ys[k - 1] + weight * (ys[k] - ys[k - 1]) + PITCH
    return ys[-1] + PITCH


def _run(tmp_path, *extra):
    run = tmp_path / "run"
    return subprocess.run(
        [sys.executable, "-I", str(TOOL), "--run-dir", str(run), "--rpm", "60", "--revs", "1",
         "--store", str(tmp_path / "store.csv"), "--source", "olaf-fvw", "--pitch", str(PITCH),
         "--out", str(tmp_path / "out.csv"), "--bands", "0.0-1.0", *extra],
        capture_output=True, text=True)


def _frame_case(tmp_path, cx, cy):
    """ALM in the rotor-plane frame (c_ref_n = Cx, c_ref_t = Cy); reference in the AeroDyn chord frame."""
    run = tmp_path / "run"
    elements = run / "postProcessing" / "actuatorLineElements" / "0"
    elements.mkdir(parents=True)
    lines = ["source,quantity,r_over_R_or_radius_m,value,unit,note\n"]
    for k, root_dist in enumerate((0.1, 0.5, 0.9)):
        _element(elements / f"turbine.blade1.element{k}.csv", root_dist, 5.0, cx, cy)
        r_over_R = (bg.HUB_RADIUS + root_dist * bg.BLADE_SPAN) / bg.TIP_RADIUS_STRUCTURAL
        theta = math.radians(_theta_deg(r_over_R))
        # AeroDyn BNCn/BNCt (AeroDyn_IO.f90): rotate the plane pair (Cx, Cy) by twist + pitch.
        chord = {"alpha_deg": 5.0, "cn": cx * math.cos(theta) + cy * math.sin(theta),
                 "ct": -cx * math.sin(theta) + cy * math.cos(theta)}
        for quantity, value in chord.items():
            lines.append(f"olaf-fvw,{quantity},{r_over_R},{value},-,n\n")
    (tmp_path / "store.csv").write_text("".join(lines))


def test_tangential_ratio_is_taken_in_the_rotor_plane_frame(tmp_path):
    _frame_case(tmp_path, cx=1.2, cy=0.4)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    rows = list(csv.DictReader((tmp_path / "out.csv").open()))
    assert [round(float(r["cy_ratio"]), 6) for r in rows] == [1.0, 1.0, 1.0]
    assert [round(float(r["cx_ratio"]), 6) for r in rows] == [1.0, 1.0, 1.0]
    assert "c_y ratio 1.000" in result.stdout
    assert "informational" not in result.stdout


def _integral_case(tmp_path, f_t, torque_scale=1.0):
    """Three ALM cells at the cell centres and a reference whose tangential force integrates to the same torque."""
    run = tmp_path / "run"
    elements = run / "postProcessing" / "actuatorLineElements" / "0"
    elements.mkdir(parents=True)
    for k in range(3):
        _element(elements / f"turbine.blade1.element{k}.csv", (k + 0.5) / 3, 5.0, 0.0, 0.0, f_t=f_t)
    store = ["source,quantity,r_over_R_or_radius_m,value,unit,note\n"]
    ref = tmp_path / "ref"
    ref.mkdir()
    force = f_t * 1.225  # N/m, the ALM f_ref is per unit density
    nodes = [bg.HUB_RADIUS + k * bg.BLADE_SPAN / 4 for k in range(5)]
    spanwise = ["node,r_over_R,radius_m,Alpha,Cn,Ct,Vrel,AxInd,TnInd,Fn,Ft"]
    for k, radius in enumerate(nodes):
        r_over_R = radius / bg.TIP_RADIUS_STRUCTURAL
        theta = math.radians(_theta_deg(r_over_R))
        spanwise.append(f"{k + 1},{r_over_R},{radius},5.0,0,0,10,0,0,{force * math.sin(theta)},{force * math.cos(theta)}")
        for quantity in ("alpha_deg", "cn", "ct"):
            store.append(f"olaf-fvw,{quantity},{r_over_R},1.0,-,n\n")
    (ref / "spanwise.csv").write_text("\n".join(spanwise) + "\n")
    torque = 3 * force * (bg.TIP_RADIUS_STRUCTURAL ** 2 - bg.HUB_RADIUS ** 2) / 2 * torque_scale
    (ref / "metrics.json").write_text(json.dumps({"pitch": PITCH, "torque_nm": torque, "thrust_n": 0.0}))
    (tmp_path / "store.csv").write_text("".join(store))
    return ref


def test_tangential_force_integrates_to_the_reference_torque(tmp_path):
    ref = _integral_case(tmp_path, f_t=100.0)
    result = _run(tmp_path, "--reference-case", str(ref))
    assert result.returncode == 0, result.stderr
    line = next(l for l in result.stdout.splitlines() if l.startswith("integral torque"))
    assert "reference/metrics 1.000" in line and "ALM/reference 1.000" in line


def test_integral_check_flags_a_torque_the_forces_do_not_reproduce(tmp_path):
    ref = _integral_case(tmp_path, f_t=100.0, torque_scale=1.1)
    result = _run(tmp_path, "--reference-case", str(ref))
    line = next(l for l in result.stdout.splitlines() if l.startswith("integral torque"))
    assert "reference/metrics 0.909" in line
