# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase VI diagnostics must include restart segments without changing windows."""

import ast
import csv
import math
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "validation" / "phaseVI" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import compareSectionLoads as sections  # noqa: E402


def write_element(run, segment, samples):
    path = run / "postProcessing" / "actuatorLineElements" / segment / "turbine.blade1.element1.csv"
    path.parent.mkdir(parents=True)
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("time", "cl", "cd", "c_ref_n", "c_ref_t", "alpha_deg",
                         "root_dist", "f_ref_n", "f_ref_t"))
        for time, lift in samples:
            writer.writerow((time, lift, 0.1, lift, -0.1, 5, 0.5, lift * 10, lift * 2))
    return path


@pytest.mark.parametrize("resumed", [False, True], ids=["unresumed", "resumed"])
def test_section_profile_keeps_window_and_uses_latest_segment(tmp_path, capsys, resumed):
    paths = [write_element(tmp_path, "0", [(0, 9), (1, 1), (2, 1)])]
    if resumed:
        paths.append(write_element(tmp_path, "2", [(2, 2), (3, 4), (4, 99)]))
    before = [path.read_bytes() for path in paths]
    profile, dropped = sections.sim_profile(tmp_path, 1, 3)
    lift = 7 / 3 if resumed else 1
    radius = sections.CUT / sections.R + 0.5 * (1 - sections.CUT / sections.R)
    assert dropped == 0
    assert len(profile) == 1
    assert profile[0] == pytest.approx((radius, lift, 0.1, math.hypot(lift, 0.1),
                                       0, 5, -5, lift * 10, lift * 2), abs=1e-5)
    if resumed:
        # Segment 0 has no rows in this later window.
        late, dropped = sections.sim_profile(tmp_path, 3, 3)
        assert dropped == 0
        assert late[0][1] == 4
        assert late[0][7:] == (40, 8)
    assert [path.read_bytes() for path in paths] == before
    assert capsys.readouterr() == ("", "")


def test_all_segment_zero_readers_use_resume_reader():
    offenders = []
    for path in sorted(SCRIPTS.glob("*.py")):
        if path.name == "comparePhaseVI.py":
            continue
        source = path.read_text()
        strings = {node.value for node in ast.walk(ast.parse(source))
                   if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        literal_path = any("postProcessing/actuatorLineElements/0" in value
                           or "postProcessing/turbines/0" in value for value in strings)
        constant_path = ("postProcessing" in strings and "0" in strings
                         and bool({"actuatorLineElements", "turbines"} & strings))
        if (literal_path or constant_path) and "read_rows_resumed" not in source:
            offenders.append(path.name)
    assert not offenders, f"segment-0-only readers: {offenders}"
