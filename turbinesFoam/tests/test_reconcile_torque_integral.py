# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only public diagnostic contracts on analytical, resumed histories."""
import csv
import math
import os
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "validation/phaseVI/scripts"
sys.path.insert(0, str(SCRIPTS))
import comparePhaseVI as rotor


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def diagnostic_run(root, speed=5, sequence="S", resumed=True, end_rev=10, tail=True):
    cfg = rotor.load_config(rotor.DEFAULT_CONFIG)
    tsr = float(rotor.select_speed(cfg, speed, sequence)["tsr"])
    period = 2 * math.pi * cfg["turbine"]["radius"] / (tsr * speed)
    denom = 0.5 * math.pi * 5.029**3 * speed**2
    # Two elements, torque 2*(1*2 + 3*4) = 28 per rotor.
    # Rotating position and force: mean cross product != cross of means.
    for segment, first, last in (("0", 0, 250), ("2", 200, end_rev*100)) if resumed else (("0", 0, end_rev*100),):
        turbine, elements = [], {0: [], 1: []}
        for step in range(first, last + 1):
            rev = step / 100
            stale = resumed and segment == "0" and step >= 200
            torque = 280 if stale or (tail and rev > 8) else 28
            turbine.append(dict(time=rev*period, tsr=tsr, cp=torque/denom*tsr,
                                ct=torque/denom, cd=0.8))
            theta = rev * 2 * math.pi
            for i, (radius, force) in enumerate(((1, 2), (3, 4))):
                elements[i].append(dict(time=rev*period, root_dist=(radius-0.5083)/(5.029-0.5083),
                    x=0, y=radius*math.cos(theta), z=12.192+radius*math.sin(theta),
                    fx=0, fy=force*math.sin(theta), fz=-force*math.cos(theta),
                    cl=9 if stale or (tail and rev > 8) else 1, cd=0.1, c_ref_n=1, c_ref_t=2 if stale else 0.2,
                    alpha_deg=5, alpha_geom_deg=6, f_ref_n=10, f_ref_t=999,
                    rel_vel_mag=20, end_effect_factor=1))
        write_csv(root / "postProcessing/turbines" / segment / "turbine.csv", turbine)
        for i, rows in elements.items():
            write_csv(root / "postProcessing/actuatorLineElements" / segment /
                      f"turbine.blade1.element{i}.csv", rows)
    (root / "system").mkdir()
    (root / "system/fvOptions").write_text("""turbine {
        type axialFlowTurbineALSource;
        axialFlowTurbineALSourceCoeffs {
            origin (0 0 12.192); axis (-1 0 0);
            blades {
                blade1 { elementType actuatorLineElement; nElements 2; elementData ((0 0.5083 0 0.5) (0 5.029 0 0.2)); }
                blade2 { $blade1; }
            }
        }
    }
    """)
    experiment = root / "experiment"
    write_csv(experiment / f"sequence_{sequence}_spanwise.csv", [
        dict(wind_speed_m_s=speed, r_over_R=r, cn=1, ct=0.2, cth=1, ctq=0.2, qnorm_pa=100)
        for r in (0.3, 0.47, 0.63, 0.8, 0.95)])
    write_csv(experiment / f"sequence_{sequence}_performance.csv", [
        dict(wind_speed_m_s=speed, rho_kg_m3=1.2)])
    return period


def cli(name, args):
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / name), *map(str, args)],
                          capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("resumed", [False, True])
@pytest.mark.parametrize("name", ["compareElementStates.py", "compareSectionLoads.py", "compareInflowAngle.py", "reconcileTorqueIntegral.py"])
def test_resumed_public_cli_window_speed_and_nonmutation(tmp_path, name, resumed):
    period = diagnostic_run(tmp_path, resumed=resumed)
    before = snapshot(tmp_path)
    args = ["--speed", "5", "--sequence", "S"]
    if name == "compareElementStates.py":
        args += [tmp_path, "--discard-revolutions", "4", "--end-revolutions", "8", "--columns", "cl"]
    else:
        args += ["--alm-dir", tmp_path, "--revolutions", "4", "8"]
        if name != "reconcileTorqueIntegral.py":
            args += ["--experiment-dir", tmp_path / "experiment"]
    result = cli(name, args)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert snapshot(tmp_path) == before
    if name == "compareElementStates.py":
        assert f"time >= {4*period:.4f}" in result.stdout
        assert "                     1" in result.stdout
    else:
        assert "revolutions 4..8" in result.stdout
    if name == "compareSectionLoads.py":
        assert "  1.000" in result.stdout
    if name == "compareInflowAngle.py":
        assert "force-direction proxy" in result.stdout
        assert "not independent flow/induction evidence" in result.stdout
        assert "   23.82" in result.stdout  # atan(1/(7.550*0.3))
    if name == "reconcileTorqueIntegral.py":
        assert "Q elements / rho: 28.000000" in result.stdout
        assert "ratio = 1.000000" in result.stdout
        assert "blades found: 1; rotor blades: 2" in result.stdout
        assert "kinematic" in result.stdout
        bands = [float(line.split()[-1]) for line in result.stdout.splitlines() if line.startswith("band ")]
        assert sum(bands) == pytest.approx(28)


def test_reconcile_missing_force_fails_explicitly_without_mutation(tmp_path):
    diagnostic_run(tmp_path, resumed=False)
    path = tmp_path / "postProcessing/actuatorLineElements/0/turbine.blade1.element0.csv"
    rows = rotor.read_rows(path)
    for row in rows:
        del row["fy"]
    write_csv(path, rows)
    before = snapshot(tmp_path)
    result = cli("reconcileTorqueIntegral.py", ["--alm-dir", tmp_path, "--speed", "5", "--sequence", "S", "--revolutions", "4", "8"])
    assert result.returncode == 1
    assert result.stdout == ""
    assert "missing column fy" in result.stderr
    assert snapshot(tmp_path) == before


def test_reconcile_missing_terminal_element_is_not_silently_closed(tmp_path):
    diagnostic_run(tmp_path)
    path = tmp_path / "system/fvOptions"
    path.write_text(path.read_text().replace("nElements 2", "nElements 3"))
    before = snapshot(tmp_path)
    result = cli("reconcileTorqueIntegral.py", ["--alm-dir", tmp_path, "--speed", "5",
                 "--sequence", "S", "--revolutions", "4", "8"])
    assert result.returncode == 1
    assert result.stdout == ""
    assert "nElements" in result.stderr
    assert snapshot(tmp_path) == before


def test_reconcile_actual_force_moment_not_per_span_proxy(tmp_path):
    diagnostic_run(tmp_path, speed=7, sequence="H", resumed=False, end_rev=12, tail=False)
    result = cli("reconcileTorqueIntegral.py", ["--alm-dir", tmp_path, "--discard-revs", "1"])
    assert result.returncode == 0, result.stderr
    assert "Q elements / rho: 28.000000" in result.stdout
    bands = [float(line.split()[-1]) for line in result.stdout.splitlines() if line.startswith("band ")]
    assert sum(bands) == pytest.approx(28)


@pytest.mark.parametrize("speed, bounds", [(5, (16, 24)), (6, (16, 24)), (7, (4, 12)), (8, (4, 12))])
def test_reconcile_sequence_s_full_requested_windows(tmp_path, speed, bounds):
    diagnostic_run(tmp_path, speed=speed, sequence="S", end_rev=bounds[1], tail=False)
    before = snapshot(tmp_path)
    result = cli("reconcileTorqueIntegral.py", ["--alm-dir", tmp_path, "--speed", speed,
                 "--sequence", "S", "--revolutions", *bounds])
    assert (result.returncode, result.stderr) == (0, "")
    assert f"revolutions {bounds[0]}..{bounds[1]}" in result.stdout
    assert "ratio = 1.000000" in result.stdout
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("discard", [1, 1.5])
def test_reconcile_legacy_discard_option(tmp_path, discard):
    diagnostic_run(tmp_path, speed=7, sequence="H", resumed=False)
    before = snapshot(tmp_path)
    result = cli("reconcileTorqueIntegral.py", ["--alm-dir", tmp_path, "--discard-revs", discard, "--end-revs", "8"])
    assert (result.returncode, result.stderr) == (0, "")
    assert f"revolutions {discard}..8" in result.stdout
    assert "ratio = 1.000000" in result.stdout
    assert snapshot(tmp_path) == before
