# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the read-only run-state reader (`validation/tools/case_state.py`).

The reader exists to replace ad-hoc ``python3 - <<PY`` snippets that were
re-derived every time a campaign needed "how far did this run get, and what does
the last window look like". Those snippets cost context and, worse, re-typed
experimental constants. These tests pin the properties that make the reader a
safe substitute: it reports only what the run wrote, it omits what is absent,
and it never mutates the run.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
TOOL = PACKAGE / "validation" / "tools" / "case_state.py"

HEADER = "time,angle_deg,tsr,cp,cd,ct,cd_blade1,ct_blade1\n"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


case_state = _load("case_state", TOOL)


def _write_turbine(case: Path, rows: list[tuple[float, float, float, float, float]]) -> Path:
    """Write a synthetic ``turbine.csv`` and return its path."""
    source = case / "postProcessing" / "turbines" / "0" / "turbine.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    body = [HEADER]
    for index, (time, cp, cd, ct, tsr) in enumerate(rows):
        body.append(
            f"{time:.3f},{index * 10.0:.3f},{tsr:.3f},{cp:.10f},{cd:.10f},{ct:.10f},"
            f"{cd / 2:.10f},{ct / 2:.10f}\n"
        )
    source.write_text("".join(body))
    return source


@pytest.fixture()
def case(tmp_path: Path) -> Path:
    """A minimal run directory with five converged-looking rows."""
    run = tmp_path / "alm-U7-coarse-s0"
    run.mkdir()
    (run / "run.json").write_text(
        json.dumps({"wind_speed_m_s": 7.0, "model": "alm", "mesh": "coarse"})
    )
    _write_turbine(
        run,
        [
            (0.000, 0.3000, 0.5000, 0.0600, 5.400),
            (0.001, 0.3400, 0.5200, 0.0650, 5.401),
            (0.002, 0.3800, 0.5400, 0.0700, 5.402),
            (0.003, 0.4000, 0.5600, 0.0720, 5.408),
            (0.004, 0.4200, 0.5800, 0.0740, 5.408),
        ],
    )
    return run


def test_last_row_is_reported_without_inventing_metrics(case: Path) -> None:
    state = case_state.inspect_run(case)

    assert state["rows"] == 5
    assert state["t_first"] == pytest.approx(0.000)
    assert state["t_last"] == pytest.approx(0.004)
    # The reader echoes the run's own columns; it does not compute cp from ct.
    assert state["means"]["cp"] == pytest.approx(0.4200)
    assert state["means"]["ct"] == pytest.approx(0.0740)
    assert state["means"]["tsr"] == pytest.approx(5.408)


def test_mean_last_averages_exactly_that_window(case: Path) -> None:
    state = case_state.inspect_run(case, mean_last=3)

    # Rows 3, 4, 5 of the fixture.
    assert state["means"]["cp"] == pytest.approx((0.3800 + 0.4000 + 0.4200) / 3)
    assert state["means"]["cd"] == pytest.approx((0.5400 + 0.5600 + 0.5800) / 3)


def test_mean_last_is_clamped_to_available_rows(case: Path) -> None:
    state = case_state.inspect_run(case, mean_last=99)

    assert state["rows"] == 5
    assert state["means"]["cp"] == pytest.approx((0.30 + 0.34 + 0.38 + 0.40 + 0.42) / 5)


def test_revolutions_come_from_the_requested_rpm_only(case: Path) -> None:
    without = case_state.inspect_run(case)
    assert without["revolutions"] is None

    with_rpm = case_state.inspect_run(case, rpm=60.0)
    # 0.004 s at 60 rpm is 0.004 revolutions; the reader does not guess a rate.
    assert with_rpm["revolutions"] == pytest.approx(0.004)


def test_missing_columns_are_omitted_not_synthesised(case: Path) -> None:
    source = case / "postProcessing" / "turbines" / "0" / "turbine.csv"
    source.write_text("time,cp\n1.0,0.5\n2.0,0.6\n")

    state = case_state.inspect_run(case)

    assert state["means"] == {"cp": pytest.approx(0.6)}
    assert "ct" not in state["means"]


def test_run_without_postprocessing_reports_a_typed_error(tmp_path: Path) -> None:
    bare = tmp_path / "never-started"
    bare.mkdir()

    with pytest.raises(case_state.CaseStateError) as caught:
        case_state.inspect_run(bare)

    assert caught.value.code == 2
    assert "postProcessing" in str(caught.value)


def test_other_sources_are_listed_when_turbine_csv_is_absent(tmp_path: Path) -> None:
    partial = tmp_path / "partial-run"
    element = partial / "postProcessing" / "actuatorLineElements" / "0"
    element.mkdir(parents=True)
    (element / "turbine.blade1.element6.csv").write_text(
        "time,alpha_deg\n0.0,4.0\n0.1,5.0\n"
    )

    state = case_state.inspect_run(partial)

    assert state["source"] is None
    assert state["otherSources"] == {
        "actuatorLineElements/0/turbine.blade1.element6.csv": 2
    }


def test_reading_never_mutates_the_run(case: Path) -> None:
    source = case / "postProcessing" / "turbines" / "0" / "turbine.csv"
    before = source.read_bytes()
    stamp = source.stat().st_mtime_ns

    case_state.inspect_run(case, mean_last=2, rpm=60.0)

    assert source.read_bytes() == before
    assert source.stat().st_mtime_ns == stamp


def test_cli_emits_one_json_object_per_run(case: Path, tmp_path: Path) -> None:
    other = tmp_path / "alm-U7-coarse-r1"
    other.mkdir()
    _write_turbine(other, [(0.0, 0.1, 0.2, 0.3, 5.0), (0.5, 0.2, 0.3, 0.4, 5.1)])

    result = subprocess.run(
        [sys.executable, str(TOOL), "--json", str(case), str(other)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert [run["run"] for run in payload["runs"]] == [
        "alm-U7-coarse-s0",
        "alm-U7-coarse-r1",
    ]
    assert payload["runs"][1]["rows"] == 2


def test_cli_reports_a_missing_run_without_a_traceback(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(TOOL), str(tmp_path / "absent")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Traceback" not in result.stderr


def _write_segment(case: Path, segment: str, rows: list[tuple[float, float]]) -> None:
    """Write a resume segment ``turbines/<segment>/turbine.csv`` of (time, cp) rows."""
    source = case / "postProcessing" / "turbines" / segment / "turbine.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "time,cp\n" + "".join(f"{time:.3f},{cp:.4f}\n" for time, cp in rows)
    )


def test_resume_segments_are_joined_and_later_rows_replace_overlap(tmp_path: Path) -> None:
    run = tmp_path / "alm-U5-coarse-seqS-v12"
    _write_segment(run, "0", [(0.000, 0.30), (0.001, 0.31), (0.002, 0.32), (0.003, 0.33)])
    # resume-run.slurm restarts from the last written time, so the new segment
    # repeats rows the old one already had; the later segment wins.
    _write_segment(run, "0.002", [(0.002, 0.42), (0.003, 0.43), (0.004, 0.44)])

    state = case_state.inspect_run(run, mean_last=3, rpm=60.0)

    assert state["rows"] == 5
    assert state["t_first"] == pytest.approx(0.000)
    assert state["t_last"] == pytest.approx(0.004)
    assert state["revolutions"] == pytest.approx(0.004)
    assert state["means"]["cp"] == pytest.approx((0.42 + 0.43 + 0.44) / 3)
    assert state["source"] == "turbines/0/turbine.csv"
    assert state["segments"] == ["turbines/0/turbine.csv", "turbines/0.002/turbine.csv"]


def test_resume_segments_follow_numeric_not_lexicographic_order(tmp_path: Path) -> None:
    run = tmp_path / "alm-U5-coarse-seqS-v12"
    _write_segment(run, "0", [(0.0, 0.1), (5.0, 0.2)])
    _write_segment(run, "9.5", [(9.5, 0.3), (10.0, 0.4)])
    _write_segment(run, "10.5", [(10.5, 0.5), (11.0, 0.6)])

    state = case_state.inspect_run(run)

    assert state["rows"] == 6
    assert state["t_last"] == pytest.approx(11.0)
    assert state["means"]["cp"] == pytest.approx(0.6)
    assert [Path(name).parent.name for name in state["segments"]] == ["0", "9.5", "10.5"]


def test_single_segment_run_reports_one_segment(case: Path) -> None:
    state = case_state.inspect_run(case)

    assert state["rows"] == 5
    assert state["segments"] == ["turbines/0/turbine.csv"]


def test_text_report_names_the_resume_segments(tmp_path: Path) -> None:
    run = tmp_path / "alm-U5-coarse-seqS-v12"
    _write_segment(run, "0", [(0.000, 0.30), (0.001, 0.31)])
    _write_segment(run, "0.001", [(0.001, 0.41), (0.002, 0.42)])

    result = subprocess.run(
        [sys.executable, str(TOOL), str(run)], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "alm-U5-coarse-seqS-v12  turbines/0/turbine.csv + resume 0.001\n" in result.stdout
    assert "rows=3  t=[0, 0.002]" in result.stdout
