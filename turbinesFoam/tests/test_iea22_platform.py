# SPDX-License-Identifier: GPL-3.0-or-later
"""IEA-22 run platform (T4): derived values, submit dry run, no hard-coded IEA-15 numbers."""
from __future__ import annotations

import re
import subprocess
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "validation" / "iea22mw" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import olaf_trace  # noqa: E402
import platform_derive  # noqa: E402

AUTHORED = [SCRIPTS / "run_iea22mw_case.sh", SCRIPTS / "submit_iea22.sh", SCRIPTS / "platform_derive.py",
            *sorted((SCRIPTS / "slurm").glob("*.slurm"))]
#: Hard-coded IEA-15 numbers that must not appear in IEA-22 scripts.
IEA15_NUMBERS = re.compile(r"7\.518|10\.659|120\.675|\b121\.1|\b4 6 4\b|\b96\b(?!.*derive)")
SLURM = SCRIPTS / "slurm"


@pytest.fixture(scope="module")
def derived():
    return platform_derive.derive()


def sh(*args, env=None):
    return subprocess.run(["sh", str(SCRIPTS / "submit_iea22.sh"), *args], capture_output=True, text=True, env=env)


def test_lengths_identical_in_rotor_radius_units(derived):
    a, b = derived["iea15"], derived["iea22"]
    for key in ("base_cell_over_R", "castellated_cell_over_R", "domain_upstream_R", "domain_downstream_R", "domain_lateral_R"):
        assert a[key] == pytest.approx(b[key], rel=1e-9), key
    assert b["R_m"] == 142.0 and b["rpm"] == 6.853997


def test_ranks_follow_cells_per_rank_and_lattice(derived):
    n = [int(v) for v in derived["decomp_n"].split()]
    assert derived["ranks22"] == n[0] * n[1] * n[2]
    assert derived["ranks22"] == pytest.approx(derived["ranks_cells_rule"], rel=0.05)


def test_alm_slurm_matches_derived_and_ds_arm(derived):
    text = (SLURM / "l2-ds.slurm").read_text()
    assert f"#SBATCH --ntasks={derived['ranks22']}\n" in text
    assert "#SBATCH --no-requeue" in text and "-p sequana_cpu_bigmem" in text
    for flag in ("TURBINE_END_EFFECTS=on", "TURBINE_ROOT_EFFECTS=on", "TURBINE_TIP_EFFECTS=off", "TURBINE_TIP_CORRECTION=on"):
        assert flag in text
    assert 'TURBINE_TOTAL_REVS:-23' in text and "TURBINE_MODEL=alm" in text
    env = platform_derive.env_lines(derived)
    assert "export TURBINE_REQUEUE=0" in env and "export TURBINE_WRITE_DEG=120" in env


def test_no_iea15_numbers_in_iea22_scripts():
    for path in AUTHORED:
        for number, line in enumerate(path.read_text().splitlines(), 1):
            assert not IEA15_NUMBERS.search(line) or "ntasks" in line, f"{path.name}:{number}: {line}"


def test_dry_run_prints_commands_and_submits_nothing(derived, tmp_path):
    # An empty runs dir: the real one holds the finished production runs, which submit refuses.
    runs = str(tmp_path / "runs")
    done = sh(env={**os.environ, "IEA22_RUNS_DIR": runs})
    assert done.returncode == 0, done.stderr
    alm, olaf = done.stdout.strip().splitlines()
    assert alm.startswith("sbatch --partition=sequana_cpu_bigmem ") and f"--ntasks={derived['ranks22']} " in alm
    assert olaf.startswith("sbatch --partition=sequana_cpu ") and "--ntasks=1 " in olaf
    for line in (alm, olaf):
        assert "--exclude=sdumont6006,sdumont6009,sdumont6029" in line
        assert "--nodes" not in line and "--mem" not in line
    assert alm.endswith("scripts/slurm/l2-ds.slurm") and f"TURBINE_RUN_DIR={runs}/iea22mw-l2-ds" in alm
    assert olaf.endswith("scripts/slurm/olaf-dp.slurm") and f"OLAF_RUN_DIR={runs}/iea22mw-olaf-dp" in olaf


def test_existing_run_dir_is_refused(tmp_path, derived):
    (tmp_path / "iea22mw-l2-ds").mkdir()
    env = {"PATH": "/usr/bin:/bin", "PYTHON": sys.executable, "IEA22_RUNS_DIR": str(tmp_path)}
    # the generator reads the WindIO tower (PyYAML), which needs the loader path of the venv python
    env.update({k: os.environ[k] for k in ("LD_LIBRARY_PATH",) if k in os.environ})
    done = sh("alm", env=env)
    assert done.returncode == 1 and done.stdout == "" and "EXISTS" in done.stderr
    assert sh("olaf", env=env).returncode == 0  # the other run is not blocked


def test_bad_argument_exits_2():
    assert sh("--bogus").returncode == 2


def test_olaf_trace_fit_recovers_quadratic_cost():
    dt = 0.1
    trace = [(0.02 * n + 3e-5 * n * n, n * dt) for n in range(20, 400, 20)]
    got = olaf_trace.fit([(w, s / dt) for w, s in trace], 1640)
    assert got["wall_extrapolated_s"] == pytest.approx(0.02 * 1640 + 3e-5 * 1640**2, rel=1e-6)


def test_olaf_trace_truncate_sets_tmax(tmp_path):
    (tmp_path / "x.fst").write_text("239.1  TMax  - Total\n0.1459  DT  - step\n")
    assert olaf_trace.truncate(tmp_path, 100) == pytest.approx(14.59)
    assert (tmp_path / "x.fst").read_text().startswith("14.5900  TMax")


def test_bem_rated_reference_is_stored():
    import csv
    analysis = SCRIPTS.parent / "analysis"
    rows = list(csv.DictReader((analysis / "spanwise-references.csv").open()))
    assert {r["source"] for r in rows} >= {"openfast-bem"}
    assert sum(r["source"] == "openfast-bem" for r in rows) == 177
    import json
    metrics = json.loads((analysis / "bem-rated-metrics.json").read_text())
    assert metrics["converged"] and metrics["cp"] == pytest.approx(0.4524, abs=1e-3)


def test_olaf_slurm_is_single_task_and_sized():
    text = (SLURM / "olaf-dp.slurm").read_text()
    assert "#SBATCH --ntasks=1\n" in text and "#SBATCH -p sequana_cpu\n" in text
    assert "GFORTRAN_UNBUFFERED_PRECONNECTED=y" in text
