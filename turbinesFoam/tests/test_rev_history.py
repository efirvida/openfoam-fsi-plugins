# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the per-revolution history reader (`validation/tools/rev_history.py`).

The reader exists because a resumed run splits its history: the module writes
``postProcessing/turbines/<timeName>/turbine.csv`` named after the run's start
time, so one continuous run lands in several folders whose names sort wrongly as
text ("31.9209" after "159.6232") and whose row counts differ when the time step
changes. Reading one folder alone reports a fraction of the run, which is the
mistake the reader removes.

These tests pin the properties that make it a safe substitute: it reads the
union, it orders the folders numerically, it takes the revolution from the
cumulative angle, and it reports a gap instead of hiding one.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
TOOL = PACKAGE / "validation" / "tools" / "rev_history.py"

HEADER = "time,angle_deg,tsr,cp,cd,ct,cd_blade1,ct_blade1\n"

#: Folder names that separate the numeric order from the lexical one, taken from
#: the real run: lexical "159.6232" < "31.9209" < "0", numeric 0 < 31.9209.
LEXICAL_TRAP = ("0", "31.9209", "159.6232")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_history(
    root: Path,
    time_name: str,
    first_rev: int,
    last_rev: int,
    cp_by_rev: dict[int, float],
    ct: float = 0.06,
    rows_per_rev: int = 4,
) -> None:
    """Write one synthetic turbine.csv, with the angle cumulative as the module's.

    ``angle_deg`` counts from the case start, not from the restart, which is why
    the revolution can be rebuilt from the union even though the folders are
    separate files.
    """
    target = root / "postProcessing" / "turbines" / time_name
    target.mkdir(parents=True, exist_ok=True)
    lines = [HEADER]
    for rev in range(first_rev, last_rev + 1):
        for index in range(rows_per_rev):
            angle = (rev - 1) * 360.0 + 360.0 * (index + 0.5) / rows_per_rev
            time = angle / 360.0 * 8.0
            lines.append(
                f"{time:.6f},{angle:.6f},8.9131856,{cp_by_rev[rev]:.8f},0.4,{ct:.8f},0,0\n"
            )
    (target / "turbine.csv").write_text("".join(lines), encoding="utf-8")


def _split_run(tmp_path: Path) -> Path:
    """Three folders holding revolutions 1-6 of one continuous run."""
    cp = {1: 0.60, 2: 0.58, 3: 0.56, 4: 0.55, 5: 0.54, 6: 0.539}
    _write_history(tmp_path, "0", 1, 2, cp)  # the original run
    _write_history(tmp_path, "31.9209", 3, 4, cp)  # first resume
    _write_history(tmp_path, "159.6232", 5, 6, cp)  # second resume
    return tmp_path


def _two_arm_run(tmp_path: Path) -> Path:
    """Revolutions 1-3 of one arm, then a much cheaper tail (gap at 4).

    The tail's cp is far below the head's, so a plateau taken from the tail
    silently reports the second arm; only ``--max-rev 3`` recovers the first.
    """
    cp = {1: 0.60, 2: 0.61, 3: 0.62, 5: 0.40, 6: 0.38}
    _write_history(tmp_path, "0", 1, 3, cp)
    _write_history(tmp_path, "31.9209", 5, 6, cp)
    return tmp_path


def test_the_union_is_read_not_one_folder(tmp_path):
    module = _load("rev_history", TOOL)
    result = module.analyse(_split_run(tmp_path))
    assert result["revolutions"] == 6
    assert result["first_rev"] == 1
    assert result["last_rev"] == 6
    assert len(result["histories"]) == 3
    assert result["gaps"] == []


def test_histories_are_ordered_numerically_not_lexically(tmp_path):
    module = _load("rev_history", TOOL)
    result = module.analyse(_split_run(tmp_path))
    names = [Path(path).parent.name for path in result["histories"]]
    assert names == list(LEXICAL_TRAP)
    assert sorted(names) != names, "the fixture must separate the two orders"
    # The revolutions the split holds, in order, regardless of folder order.
    assert [entry["rev"] for entry in result["series"]] == [1, 2, 3, 4, 5, 6]


def test_the_revolution_comes_from_the_cumulative_angle(tmp_path):
    module = _load("rev_history", TOOL)
    # A row count that changes with deltaT must not change the revolution: here
    # the resumed folders have half the rows per revolution of the first.
    cp = {1: 0.60, 2: 0.58, 3: 0.56, 4: 0.55}
    _write_history(tmp_path, "0", 1, 2, cp, rows_per_rev=8)
    _write_history(tmp_path, "31.9209", 3, 4, cp, rows_per_rev=16)
    result = module.analyse(tmp_path)
    assert [entry["rows"] for entry in result["series"]] == [8, 8, 16, 16]
    assert [entry["rev"] for entry in result["series"]] == [1, 2, 3, 4]


def test_drift_and_plateau_use_the_tail(tmp_path):
    module = _load("rev_history", TOOL)
    result = module.analyse(_split_run(tmp_path), window=2, drift_window=2)
    assert result["series"][0]["drift_cp_pct"] is None
    assert result["series"][1]["drift_cp_pct"] < 0
    # Plateau = mean of revolutions 5 and 6; the drift = the mean of the last two
    # changes (window 2 spans two of them, each against its own predecessor).
    assert result["plateau_cp"] == (0.54 + 0.539) / 2
    assert result["plateau_ct"] == 0.06
    expected = ((0.54 - 0.55) / 0.55 * 100.0 + (0.539 - 0.54) / 0.54 * 100.0) / 2
    assert abs(result["mean_drift_cp_pct"] - expected) < 1e-9


def test_a_gap_is_reported_not_hidden(tmp_path):
    module = _load("rev_history", TOOL)
    cp = {1: 0.60, 2: 0.59, 5: 0.55, 6: 0.549}
    _write_history(tmp_path, "0", 1, 2, cp)
    _write_history(tmp_path, "31.9209", 5, 6, cp)
    result = module.analyse(tmp_path)
    assert result["gaps"] == [3, 4]


def test_a_stub_revolution_is_flagged_and_kept_out(tmp_path):
    module = _load("rev_history", TOOL)
    _write_history(tmp_path, "0", 1, 4, {1: 0.60, 2: 0.58, 3: 0.56, 4: 0.55})
    # The run stopped a hair into revolution 5 and wrote a single row, which is
    # what the real rotational-augmentation run left at endTime.
    csv = tmp_path / "postProcessing" / "turbines" / "0" / "turbine.csv"
    with csv.open("a", encoding="utf-8") as handle:
        handle.write(f"{32.0:.6f},{1440.7:.6f},8.9131856,0.549,0.4,0.06,0,0\n")
    result = module.analyse(tmp_path, window=2)
    assert result["partial_revs"] == [5]
    assert result["gaps"] == []
    # The plateau ignores the stub: it is the mean of revolutions 3 and 4.
    assert result["plateau_cp"] == (0.56 + 0.55) / 2
    # And the stub invents no drift: the last real change is revolution 4's.
    assert result["series"][-1]["drift_cp_pct"] is None
    expected = (0.55 - 0.56) / 0.56 * 100.0
    assert abs(result["series"][-2]["drift_cp_pct"] - expected) < 1e-9


def test_missing_column_fails_loudly(tmp_path):
    module = _load("rev_history", TOOL)
    target = tmp_path / "postProcessing" / "turbines" / "0"
    target.mkdir(parents=True)
    (target / "turbine.csv").write_text("time,angle_deg,tsr\n0,0,8.9\n", encoding="utf-8")
    try:
        module.analyse(tmp_path)
    except ValueError as error:
        assert "cp" in str(error)
    else:  # pragma: no cover - the point is that it raises
        raise AssertionError("a missing column must not pass silently")


def test_cli_writes_the_series_and_compares_plateaus(tmp_path):
    module = _load("rev_history", TOOL)
    run = _split_run(tmp_path / "run")
    other = _split_run(tmp_path / "other")
    out = tmp_path / "series.csv"
    assert module.main([str(run), str(other), "--csv", str(out)]) == 0
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "run,rev,time,rows,cp,ct,drift_cp_pct"
    assert len(lines) == 13  # header + 6 revolutions x 2 runs
    assert module.main([str(tmp_path / "absent")]) == 1


def test_max_rev_takes_the_plateau_and_drift_from_the_first_n(tmp_path):
    module = _load("rev_history", TOOL)
    run = _two_arm_run(tmp_path)
    full = module.analyse(run, window=2, drift_window=2)
    cut = module.analyse(run, window=2, drift_window=2, max_rev=3)
    # Without the cut the cheap tail wins the plateau and the gap is reported ...
    assert full["plateau_cp"] == (0.40 + 0.38) / 2
    assert full["gaps"] == [4]
    # ... with it both the plateau and the drift come from the first three, the
    # gap beyond the cut is not reported, and the discarded revs are named.
    assert [entry["rev"] for entry in cut["series"]] == [1, 2, 3]
    assert cut["revolutions"] == 3
    assert cut["first_rev"] == 1
    assert cut["last_rev"] == 3
    assert cut["gaps"] == []
    assert cut["max_rev"] == 3
    assert cut["discarded_revs"] == [5, 6]
    assert cut["plateau_cp"] == (0.61 + 0.62) / 2
    assert cut["plateau_ct"] == 0.06
    expected = ((0.62 - 0.61) / 0.61 * 100.0 + (0.61 - 0.60) / 0.60 * 100.0) / 2
    assert abs(cut["mean_drift_cp_pct"] - expected) < 1e-9
    assert abs(cut["mean_drift_cp_pct"] - full["mean_drift_cp_pct"]) > 1.0


def test_a_stub_inside_the_cut_is_still_kept_out(tmp_path):
    module = _load("rev_history", TOOL)
    cp = {1: 0.60, 2: 0.58, 3: 0.56, 4: 0.55, 6: 0.53, 7: 0.52, 8: 0.51}
    _write_history(tmp_path, "0", 1, 4, cp)
    _write_history(tmp_path, "31.9209", 6, 8, cp)
    # One row at endTime partway into revolution 5: a stub, inside the cut.
    csv = tmp_path / "postProcessing" / "turbines" / "0" / "turbine.csv"
    with csv.open("a", encoding="utf-8") as handle:
        handle.write(f"{40.0:.6f},{1442.0:.6f},8.9131856,0.549,0.4,0.06,0,0\n")
    result = module.analyse(tmp_path, window=2, max_rev=6)
    assert result["partial_revs"] == [5]
    assert result["discarded_revs"] == [7, 8]
    assert [entry["rev"] for entry in result["series"]] == [1, 2, 3, 4, 5, 6]
    # The stub is not a revolution: the plateau is the last two complete revs.
    assert result["plateau_cp"] == (0.55 + 0.53) / 2


def test_max_rev_above_the_last_revolution_is_no_cut(tmp_path):
    module = _load("rev_history", TOOL)
    run = _split_run(tmp_path)
    full = module.analyse(run)
    above = module.analyse(run, max_rev=999)
    assert above["discarded_revs"] == []
    assert above["revolutions"] == full["revolutions"]
    assert above["plateau_cp"] == full["plateau_cp"]
    assert above["mean_drift_cp_pct"] == full["mean_drift_cp_pct"]
    assert [entry["rev"] for entry in above["series"]] == [
        entry["rev"] for entry in full["series"]
    ]


def test_cli_max_rev_cuts_the_csv_and_says_so(tmp_path, capsys):
    module = _load("rev_history", TOOL)
    run = _two_arm_run(tmp_path / "run")
    out = tmp_path / "series.csv"
    assert module.main([str(run), "--max-rev", "3", "--csv", str(out)]) == 0
    text = capsys.readouterr().out
    assert "recortado a rev <= 3 (2 revoluciones descartadas)" in text
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "run,rev,time,rows,cp,ct,drift_cp_pct"
    assert [line.split(",")[1] for line in lines[1:]] == ["1", "2", "3"]


def test_cli_json_reports_the_cut(tmp_path, capsys):
    module = _load("rev_history", TOOL)
    run = _two_arm_run(tmp_path / "run")
    assert module.main([str(run), "--max-rev", "3", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["max_rev"] == 3
    assert payload[0]["discarded_revs"] == [5, 6]


def test_cli_reports_no_cut_when_max_rev_is_above_the_last(tmp_path, capsys):
    module = _load("rev_history", TOOL)
    run = _split_run(tmp_path / "run")
    assert module.main([str(run), "--max-rev", "999"]) == 0
    assert "recortado" not in capsys.readouterr().out
