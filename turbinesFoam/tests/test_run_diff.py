# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the read-only two-run differ (`validation/tools/run_diff.py`).

The differ answers one regression question: did a rebuilt library or a changed
renderer reproduce a reference run? It aligns the two runs' own CSV rows on
time and reports how far each shared column moved. These tests pin what makes
that answer trustworthy: resumed segments are joined the way the other readers
join them, absent columns and files are reported and never compared, the run
directories are never touched, and the exit code carries the verdict.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
TOOL = PACKAGE / "validation" / "tools" / "run_diff.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run_diff = _load("run_diff", TOOL)


def _write(run: Path, family: str, segment: str, name: str, header: list[str],
           rows: list[list[float]]) -> None:
    path = run / "postProcessing" / family / segment / name
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(header)]
    lines += [",".join(f"{value:.12g}" for value in row) for row in rows]
    path.write_text("\n".join(lines) + "\n")


TURBINE_HEADER = ["time", "angle_deg", "cp", "ct"]
ELEMENT_HEADER = ["time", "alpha_deg", "cl"]


def _turbine_rows(start: int, stop: int, cp_shift: float = 0.0) -> list[list[float]]:
    return [[0.1 * i, 10.0 * i, 0.5 + 0.001 * i + cp_shift, 0.06] for i in range(start, stop)]


def _element_rows(start: int, stop: int) -> list[list[float]]:
    return [[0.1 * i, 5.0 + 0.01 * i, 0.8] for i in range(start, stop)]


@pytest.fixture()
def pair(tmp_path: Path) -> tuple[Path, Path]:
    """Reference resumed at t=0.5 (overlapping row), candidate in one segment."""
    ref = tmp_path / "ref"
    cand = tmp_path / "cand"
    _write(ref, "turbines", "0", "turbine.csv", TURBINE_HEADER, _turbine_rows(1, 6))
    _write(ref, "turbines", "0.5", "turbine.csv", TURBINE_HEADER, _turbine_rows(5, 10))
    _write(ref, "actuatorLineElements", "0", "turbine.blade1.element0.csv", ELEMENT_HEADER,
           _element_rows(1, 10))
    _write(cand, "turbines", "0", "turbine.csv", TURBINE_HEADER, _turbine_rows(1, 10))
    _write(cand, "actuatorLineElements", "0", "turbine.blade1.element0.csv", ELEMENT_HEADER,
           _element_rows(1, 10))
    return ref, cand


def _digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        digest.update(str(path.relative_to(root)).encode())
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True)


def test_identical_runs_with_resumed_reference_match_exactly(pair):
    ref, cand = pair
    report = run_diff.diff_runs(ref, cand)
    turbine = report["files"]["turbines/turbine.csv"]
    assert turbine["common_rows"] == 9
    assert turbine["reference_only_rows"] == 0 and turbine["candidate_only_rows"] == 0
    assert turbine["columns"]["cp"]["max_abs"] == 0.0
    assert report["worst"]["max_rel"] == 0.0
    result = _cli(str(ref), str(cand), "--tolerance", "0")
    assert result.returncode == 0, result.stderr


def test_perturbed_column_is_measured_and_fails_the_tolerance(pair):
    ref, cand = pair
    _write(cand, "turbines", "0", "turbine.csv", TURBINE_HEADER, _turbine_rows(1, 10, cp_shift=0.0054))
    report = run_diff.diff_runs(ref, cand)
    cp = report["files"]["turbines/turbine.csv"]["columns"]["cp"]
    assert cp["max_abs"] == pytest.approx(0.0054, rel=1e-6)
    # relative to the reference column scale max|cp_ref| = 0.509
    assert cp["max_rel"] == pytest.approx(0.0054 / 0.509, rel=1e-6)
    assert report["worst"]["column"] == "cp"
    assert report["worst"]["file"] == "turbines/turbine.csv"
    assert _cli(str(ref), str(cand), "--tolerance", "1e-3").returncode == 3
    assert _cli(str(ref), str(cand), "--tolerance", "0.02").returncode == 0


def test_absent_columns_and_files_are_reported_not_compared(pair):
    ref, cand = pair
    _write(cand, "actuatorLineElements", "0", "turbine.blade1.element0.csv",
           ELEMENT_HEADER + ["end_effect_phi_deg"],
           [row + [12.0] for row in _element_rows(1, 10)])
    _write(ref, "actuatorLineElements", "0", "turbine.blade1.element1.csv", ELEMENT_HEADER,
           _element_rows(1, 10))
    report = run_diff.diff_runs(ref, cand)
    element = report["files"]["actuatorLineElements/turbine.blade1.element0.csv"]
    assert element["candidate_only_columns"] == ["end_effect_phi_deg"]
    assert "end_effect_phi_deg" not in element["columns"]
    assert report["reference_only_files"] == ["actuatorLineElements/turbine.blade1.element1.csv"]
    assert report["candidate_only_files"] == []


def test_until_bounds_the_compared_rows(pair):
    ref, cand = pair
    rows = _turbine_rows(1, 10)
    rows[-1][2] += 1.0  # only t = 0.9 differs
    _write(cand, "turbines", "0", "turbine.csv", TURBINE_HEADER, rows)
    assert run_diff.diff_runs(ref, cand)["worst"]["max_abs"] == pytest.approx(1.0)
    bounded = run_diff.diff_runs(ref, cand, until=0.85)
    assert bounded["files"]["turbines/turbine.csv"]["common_rows"] == 8
    assert bounded["worst"]["max_abs"] == 0.0


def test_runs_are_not_mutated_and_json_parses(pair):
    ref, cand = pair
    before = (_digest(ref), _digest(cand))
    result = _cli(str(ref), str(cand), "--json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["worst"]["max_rel"] == 0.0
    _cli(str(ref), str(cand))
    assert (_digest(ref), _digest(cand)) == before


def test_missing_directory_and_missing_output_have_distinct_codes(tmp_path, pair):
    ref, _ = pair
    missing = _cli(str(ref), str(tmp_path / "nope"))
    assert missing.returncode == 1
    assert "does not exist" in missing.stderr
    empty = tmp_path / "empty"
    empty.mkdir()
    no_output = _cli(str(ref), str(empty))
    assert no_output.returncode == 2
    assert "postProcessing" in no_output.stderr
