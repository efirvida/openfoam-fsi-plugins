"""compareWakes.py: side-by-side AeroDyn cases (BEM vs OLAF) per Phase VI point."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

TOOL = (
    Path(__file__).resolve().parent.parent
    / "validation" / "phaseVI" / "openfast" / "compareWakes.py"
)
STATIONS = ("0.30", "0.47", "0.63", "0.80", "0.95")


def _case(root, name, wake, power_err, thrust_err, cn95_err, speed=8.0,
          converged=True):
    d = root / name
    d.mkdir()
    stations = {
        s: {"cn_error_pct": (cn95_err if s == "0.95" else 1.0)}
        for s in STATIONS
    }
    (d / "metrics.json").write_text(json.dumps({
        "wake": wake,
        "sequence": "S",
        "speed_m_s": speed,
        "power_error_pct": power_err,
        "thrust_error_pct": thrust_err,
        "stations": stations,
        "convergence": {"converged": converged},
    }))
    return d


def _run(*args):
    return subprocess.run(
        [sys.executable, str(TOOL), *map(str, args)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        universal_newlines=True,
    )


def test_table_has_each_case_and_the_difference(tmp_path):
    bem = _case(tmp_path, "aerodyn-bem-SU8", "bem", -10.0, -1.0, 19.1)
    olaf = _case(tmp_path, "aerodyn-olaf-dp-SU8", "olaf", -9.7, -0.7, 16.5)
    out = tmp_path / "table.csv"

    proc = _run(bem, olaf, "--out", out)

    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == ""
    lines = proc.stdout.splitlines()
    assert lines[0].split() == [
        "point", "quantity", "bem", "olaf-dp", "diff_pp",
    ]
    rows = {tuple(l.split()[:2]): l.split()[2:] for l in lines[1:] if l.strip()}
    assert rows[("S8", "P")] == ["-10.0", "-9.7", "+0.3"]
    assert rows[("S8", "T")] == ["-1.0", "-0.7", "+0.3"]
    assert rows[("S8", "cn0.95")] == ["+19.1", "+16.5", "-2.6"]
    assert rows[("S8", "cn0.30")] == ["+1.0", "+1.0", "+0.0"]
    # The CSV carries the same cells
    csv = out.read_text().splitlines()
    assert csv[0] == "point,quantity,bem,olaf-dp,diff_pp"
    assert "S8,cn0.95,19.1,16.5,-2.6" in csv


def test_points_are_grouped_and_unconverged_cases_flagged(tmp_path):
    a = _case(tmp_path, "aerodyn-bem-SU5", "bem", -7.4, -9.5, 0.6, speed=5.0)
    b = _case(tmp_path, "aerodyn-olaf-dp-SU5", "olaf", -5.0, -8.0, 1.8,
              speed=5.0, converged=False)

    proc = _run(a, b)

    assert proc.returncode == 0, proc.stderr
    assert "S5" in proc.stdout
    assert "not converged: olaf-dp S5" in proc.stdout


def test_columns_are_configurations_across_points(tmp_path):
    cases = [
        _case(tmp_path, "aerodyn-bem-SU5", "bem", -7.4, -9.5, 0.6, speed=5.0),
        _case(tmp_path, "aerodyn-olaf-dp-SU5", "olaf", -5.0, -8.0, 1.8,
              speed=5.0),
        _case(tmp_path, "aerodyn-bem-SU8", "bem", -10.0, -1.0, 19.1),
        _case(tmp_path, "aerodyn-olaf-dp-SU8", "olaf", -9.7, -0.7, 16.5),
    ]

    proc = _run(*cases)

    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.splitlines()
    assert lines[0].split()[2:] == ["bem", "olaf-dp", "diff_pp"]
    points = [l.split()[0] for l in lines[1:] if l.strip() and l[0] == "S"]
    assert points == ["S5"] * 7 + ["S8"] * 7


def test_missing_metrics_exits_1_without_output(tmp_path):
    good = _case(tmp_path, "aerodyn-bem-SU8", "bem", -10.0, -1.0, 19.1)
    empty = tmp_path / "aerodyn-olaf-SU8"
    empty.mkdir()
    out = tmp_path / "table.csv"

    proc = _run(good, empty, "--out", out)

    assert proc.returncode == 1
    assert proc.stdout == ""
    assert "metrics.json" in proc.stderr
    assert not out.exists()
