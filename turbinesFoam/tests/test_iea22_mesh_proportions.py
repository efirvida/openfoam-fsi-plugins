# SPDX-License-Identifier: GPL-3.0-or-later
"""IEA-22 mesh proportions equal IEA-15's in rotor-radius units, and no shaft tilt.

Owner decision 2026-11-02: "22MW a su velocidades nominales sin inclinaciones, con
la malla con las mismas proporciones que la IEA 15MW". Every mesh quantity of the
two rendered cases is divided by its own rotor radius R and compared; the hub
height is real turbine geometry and is the one documented exception.
"""

from __future__ import annotations

import importlib.util
import math
import re
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
VALIDATION = TESTS_DIR.parent / "validation"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gc22 = _load("iea22_prop_generate_case", VALIDATION / "iea22mw" / "tools" / "generate_case.py")
_previous = sys.modules.get("blade_geometry")
bg15 = _load("blade_geometry", VALIDATION / "iea15mw" / "tools" / "blade_geometry.py")
gc15 = _load("iea15_prop_generate_case", VALIDATION / "iea15mw" / "tools" / "generate_case.py")
if _previous is not None:
    sys.modules["blade_geometry"] = _previous

R15 = gc15.ROTOR_RADIUS
R22 = gc22.ROTOR_RADIUS
NUMBER = r"(-?[\d.]+(?:e[-+]?\d+)?)"


def _render(module, **kwargs):
    return {p.name: t for p, t in module.outputs(case_dir=Path("case"), **kwargs).items()}


def _snappy(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for name in ("rotorDisk", "rotorWake"):
        block = text[text.index(f"{name}\n") :]
        p1 = re.search(rf"point1 \({NUMBER} {NUMBER} {NUMBER}\)", block).groups()
        p2 = re.search(rf"point2 \({NUMBER} {NUMBER} {NUMBER}\)", block).groups()
        radius = float(re.search(rf"radius {NUMBER};", block).group(1))
        out[f"{name}.radius"] = radius
        out[f"{name}.upstream"] = float(p1[1])
        out[f"{name}.downstream"] = float(p2[1])
    box = text[text.index("towerBox") :] if "towerBox" in text else text[text.index("min (") - 200 :]
    lo = re.search(rf"min \({NUMBER} {NUMBER} {NUMBER}\)", box).groups()
    hi = re.search(rf"max \({NUMBER} {NUMBER} {NUMBER}\)", box).groups()
    for key, value in zip(("x", "y", "z"), lo):
        out[f"tower.min.{key}"] = float(value)
    for key, value in zip(("x", "y", "z"), hi):
        out[f"tower.max.{key}"] = float(value)
    return out


@pytest.fixture(scope="module")
def renders():
    return _render(gc15), _render(gc22)


def test_snappy_extents_in_rotor_radius_units_equal_iea15(renders):
    a, b = (_snappy(r["snappyHexMeshDict"]) for r in renders)
    assert a.keys() == b.keys() and len(a) == 12
    for key in a:
        assert b[key] / R22 == pytest.approx(a[key] / R15, rel=1e-4, abs=1e-9), key


def test_previous_guessed_extents_are_gone(renders):
    b = _snappy(renders[1]["snappyHexMeshDict"])
    assert b["rotorDisk.radius"] != 175.0 and b["rotorWake.radius"] != 200.0
    assert b["tower.min.z"] != -190.0
    assert b["rotorDisk.radius"] / R22 == pytest.approx(150.0 / R15, rel=1e-4)


def _block_mesh(text: str):
    verts = [tuple(float(v) for v in m.groups()) for m in re.finditer(rf"^\s*\({NUMBER} {NUMBER} {NUMBER}\)$", text, re.M)]
    xs = sorted({v[0] for v in verts})
    ys = sorted({v[1] for v in verts})
    zs = sorted({v[2] for v in verts})
    cells = [tuple(int(c) for c in m.groups()) for m in re.finditer(r"hex \([^)]*\) \((\d+) (\d+) (\d+)\)", text)]
    return xs, ys, zs, cells


def test_domain_and_base_cells_in_rotor_radius_units_equal_iea15(renders):
    xa, ya, za, ca = _block_mesh(renders[0]["blockMeshDict"])
    xb, yb, zb, cb = _block_mesh(renders[1]["blockMeshDict"])
    for a, b in ((xa, xb), (ya, yb)):
        assert [v / R22 for v in b] == pytest.approx([v / R15 for v in a], rel=1e-5)
    assert zb[-1] / R22 == pytest.approx(za[-1] / R15, rel=1e-5)  # domain top
    assert [c[:2] for c in ca] == [c[:2] for c in cb]  # horizontal cell counts
    # nominal base cell D/32 is identical in R units; the realised hub-adjacent
    # vertical cell differs by the integer layer count that the (real) hub height
    # imposes, so it is only close.
    assert gc22.Z_HUB_CELL / R22 == pytest.approx(gc15.Z_HUB_CELL / R15, rel=1e-9)
    assert gc22.Z_HUB_CELL == pytest.approx(2 * R22 / 32.0)
    assert gc22.hub_cell_size() / R22 == pytest.approx(gc15.hub_cell_size() / R15, rel=2e-2)
    assert gc22.Z_GROUND_CELL / R22 == pytest.approx(gc15.Z_GROUND_CELL / R15, rel=1e-9)


def test_hub_height_is_the_documented_exception():
    assert gc22.HUB_HEIGHT == 170.0 and gc15.HUB_HEIGHT == 150.0
    assert gc22.HUB_HEIGHT / R22 != pytest.approx(gc15.HUB_HEIGHT / R15, rel=1e-2)


def test_snappy_level_and_tower_lateral_proportions():
    assert gc22.DEFAULT_SNAPPY_LEVEL == gc15.DEFAULT_SNAPPY_LEVEL
    assert gc22.ASM_WAKE_LEVEL_OFFSET == gc15.ASM_WAKE_LEVEL_OFFSET
    assert gc22.DEFAULT_VELOCITY_SAMPLE_RADIUS == gc15.DEFAULT_VELOCITY_SAMPLE_RADIUS == 0.0
    assert gc22.DEFAULT_N_VELOCITY_SAMPLES == gc15.DEFAULT_N_VELOCITY_SAMPLES


def test_time_step_in_tip_travel_units_equal_iea15():
    for level in (0, 3):
        d15 = gc15.delta_t(gc15.domain_spec(), gc15.RATED_RPM, level)
        d22 = gc22.delta_t(gc22.domain_spec(), gc22.RATED_RPM, level)
        travel15 = d15 * gc15.omega_from_rpm(gc15.RATED_RPM) * R15 / R15
        travel22 = d22 * gc22.omega_from_rpm(gc22.RATED_RPM) * R22 / R22
        assert travel22 == pytest.approx(travel15, rel=3e-2)  # 3-digit rounding + realised hub-adjacent cell (hub height)


def test_cell_count_is_reported_not_guessed():
    assert gc15.cell_count() == 4_299_792
    assert gc22.EXPECTED_CELL_COUNT == gc22.cell_count()
    # same horizontal blocks, so the count differs only through the vertical layers
    n15 = sum(gc15.vertical_mesh()[1])
    n22 = sum(gc22.vertical_mesh()[1])
    assert gc22.cell_count() == gc15.cell_count() // n15 * n22


# --- no shaft tilt -------------------------------------------------------------
def test_iea22_nacelle_has_no_tilt_by_default():
    spec = gc22.nacelle_spec("y")
    assert spec["uptilt_deg"] == 0.0
    assert spec["axis"] == pytest.approx(gc22.inflow_direction("y"))
    assert spec["start"][2] == 0.0


def test_iea22_tilt_is_an_explicit_opt_in():
    spec = gc22.nacelle_spec("y", tilt_deg="windio")
    assert spec["uptilt_deg"] == pytest.approx(6.0)
    assert spec["axis"][2] == pytest.approx(-math.sin(math.radians(6.0)))
    on = gc22.outputs(case_dir=Path("case"), nacelle=True, nacelle_tilt_deg="windio")
    off = gc22.outputs(case_dir=Path("case"), nacelle=True)
    key = next(p for p in on if p.name == "fvOptions")
    assert on[key] != off[key]
    assert "nacelle" in off[key]


def test_iea15_default_tilt_is_unchanged():
    assert gc15.nacelle_spec("y")["uptilt_deg"] == pytest.approx(6.0)


def test_cli_flag_shaft_tilt(tmp_path, capsys):
    assert gc22.main(["--case-dir", str(tmp_path), "--nacelle", "on"]) == 0
    stl = (tmp_path / "constant" / "triSurface" / "iea22mw_nacelle.stl").read_bytes()
    assert gc22.main(["--case-dir", str(tmp_path / "t"), "--nacelle", "on", "--shaft-tilt", "on"]) == 0
    tilted = (tmp_path / "t" / "constant" / "triSurface" / "iea22mw_nacelle.stl").read_bytes()
    assert stl != tilted
    assert gc22.main(["--case-dir", str(tmp_path / "t"), "--shaft-tilt", "on", "--check"]) == 1


def test_mesh_proportions_tool_table_and_exit_code(capsys):
    tool = _load("iea22_prop_table", VALIDATION / "iea22mw" / "tools" / "mesh_proportions.py")
    assert tool.main() == 0
    out = capsys.readouterr().out
    assert "| rotorDisk radius | 150 | 1.24300 | 176.5 | 1.24300 |" in out
    assert "hub height (real geometry) (exception)" in out
    assert "4,299,792" in out and "4,171,440" in out


def _tower_element_size_over_R(bg, gc):
    stations = bg.read_tower_table()
    height = stations[-1]["z"] - stations[0]["z"]
    return height / gc.TOWER_N_ELEMENTS / gc.ROTOR_RADIUS, len(stations) - 1


def test_tower_elements_divide_the_tower_segments():
    """actuatorLineSource requires nElements to be a multiple of the geometry
    segments; a fixed IEA-15 value (40) aborts the 30-segment IEA-22 monopile."""
    _, segments = _tower_element_size_over_R(gc22.blade_geometry, gc22)
    assert gc22.TOWER_N_ELEMENTS % segments == 0


def test_tower_element_size_follows_iea15_in_rotor_radius_units():
    """Element length <= IEA-15's in R units, within one segment multiple."""
    size15, _ = _tower_element_size_over_R(bg15, gc15)
    size22, segments = _tower_element_size_over_R(gc22.blade_geometry, gc22)
    assert size22 <= size15 * (1.0 + 1e-9)
    # not finer than needed: one fewer segment multiple would be coarser than IEA-15
    coarser = (gc22.TOWER_N_ELEMENTS - segments)
    if coarser > 0:
        height = size22 * gc22.ROTOR_RADIUS * gc22.TOWER_N_ELEMENTS
        assert height / coarser / gc22.ROTOR_RADIUS > size15


def test_rendered_tower_n_elements_matches_constant():
    text = gc22.render_fvoptions() if hasattr(gc22, "render_fvoptions") else None
    if text is None:
        pytest.skip("no fvOptions renderer exposed")
    assert f"nElements {gc22.TOWER_N_ELEMENTS};" in text
