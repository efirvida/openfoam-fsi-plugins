# SPDX-License-Identifier: GPL-3.0-or-later
"""FLOWUnsteady database writer (`validation/phaseVI/scripts/buildFlowUnsteadyDatabase.py`).

Pins what FLOWUnsteady's `read_rotor`/`read_blade` need: the file tree, the
radius normalisation, the pitch = twist + tip pitch rule, the contour ordering
(trailing edge -> upper -> leading edge -> lower) and that the +-180 deg polar
closure is not written (FLOWUnsteady applies its own Viterna extension).
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "validation" / "phaseVI" / "scripts"
sys.path.insert(0, str(SCRIPTS))
builder = pytest.importorskip("buildFlowUnsteadyDatabase")


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open() as stream:
        return list(csv.DictReader(stream))


@pytest.fixture(scope="module")
def database(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("fu-db")
    builder.build(out, "total", 3.0)
    return out


def test_rotor_file_has_the_four_properties_read_rotor_expects(database: Path) -> None:
    rows = _rows(database / "rotors" / "phaseVI.csv")
    assert [r["property"] for r in rows[:4]] == ["Rtip", "Rhub", "B", "blade"]
    assert float(rows[0]["file"]) == 5.029
    assert float(rows[1]["file"]) == 0.5083
    assert int(rows[2]["file"]) == 2


def test_blade_file_lists_files_in_read_blade_order(database: Path) -> None:
    rows = _rows(database / "rotors" / "phaseVI_blade.csv")
    assert [r["property"] for r in rows] == [
        "chorddist", "pitchdist", "sweepdist", "heightdist", "airfoil_files", "spl_k", "spl_s",
    ]
    for row in rows[:5]:
        assert (database / "rotors" / row["file"]).is_file()


def test_pitch_is_twist_plus_tip_pitch_and_radius_is_normalised(database: Path) -> None:
    pitch = _rows(database / "rotors" / "phaseVI_pitchdist.csv")
    tip = pitch[-1]
    assert float(tip["r/R"]) == pytest.approx(1.0)
    assert float(tip["pitch (deg)"]) == pytest.approx(-1.815 + 3.0)
    assert float(pitch[0]["r/R"]) == pytest.approx(0.5083 / 5.029)


def test_chord_is_normalised_by_the_tip_radius(database: Path) -> None:
    chord = _rows(database / "rotors" / "phaseVI_chorddist.csv")
    assert float(chord[-1]["c/R"]) == pytest.approx(0.3551 / 5.029)


def test_contour_runs_from_the_trailing_edge_over_the_upper_surface(database: Path) -> None:
    contour = [(float(r["x/c"]), float(r["y/c"])) for r in _rows(database / "airfoils" / "s809_rfl.csv")]
    assert contour[0] == (1.0, 0.0)
    assert contour[-1] == (1.0, 0.0)
    leading_edge = min(range(len(contour)), key=lambda i: contour[i][0])
    assert all(y >= -1e-9 for _, y in contour[: leading_edge // 2])
    assert all(y <= 1e-3 for _, y in contour[leading_edge + 2 : -10])  # the S809 lower surface rises slightly above the chord line aft of x/c 0.9
    assert all(a != b for a, b in zip(contour, contour[1:], strict=False))


def test_polar_is_limited_to_the_measured_range(database: Path) -> None:
    polar = _rows(database / "airfoils" / "s809-total.csv")
    alphas = [float(r["Alpha"]) for r in polar]
    assert alphas == sorted(alphas)
    assert min(alphas) < -19.0 and max(alphas) <= builder.ALPHA_MAX
    assert 0.0 in alphas


def test_pressure_polar_has_less_drag_than_total_at_the_same_alpha(tmp_path: Path) -> None:
    builder.build(tmp_path, "pressure", 3.0)
    pressure = {float(r["Alpha"]): float(r["Cd"]) for r in _rows(tmp_path / "airfoils" / "s809-pressure.csv")}
    builder.build(tmp_path / "t", "total", 3.0)
    total = {float(r["Alpha"]): float(r["Cd"]) for r in _rows(tmp_path / "t" / "airfoils" / "s809-total.csv")}
    assert pressure.keys() == total.keys()
    assert sum(pressure.values()) < sum(total.values())
