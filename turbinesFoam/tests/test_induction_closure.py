# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the momentum-closure tool (`validation/tools/induction_closure.py`).

The tool compares the thrust an actuator rotor actually applies per unit radius
with the one the momentum relation ``dT = 2 rho U^2 a (1-a) dA`` predicts from
the induction ``a`` sampled in the flow. The relation degrades with loading, so
the tool reports a ratio and never a verdict; these tests pin that the ratio is
exactly 1 when the force is built from the theory, that a wrong force moves it
by the same factor, and that the element histories are read as a union.

The ring files are written in the format OpenFOAM v2506 produces for a ``circle``
set with ``setFormat raw``: ``<set>_U.xy``, tab-separated ``x y z Ux Uy Uz``,
one row per point, the closing point not repeated.
"""

from __future__ import annotations

import importlib.util
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import pytest

PACKAGE = Path(__file__).resolve().parents[1]
TOOL = PACKAGE / "validation" / "tools" / "induction_closure.py"

RADIUS = 5.0
U_INF = 7.0
RHO = 1.225
ORIGIN = (0.0, 0.0, 12.0)
N_ELEMENTS = 20
N_RINGS = 131  # r/R from 0.05 to 1.3 in steps of 0.01
POINTS_PER_RING = 12
AXIS = (-1.0, 0.0, 0.0)
HUB = 0.5  # hub radius in metres; root_dist is the span fraction measured from it
#: Appended to every analyse call: the rotor geometry the element radii come from.
ROTOR_ARGS = ["--origin", *map(str, ORIGIN), "--axis", *map(str, AXIS)]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load("induction_closure", TOOL)


def induction(r: float) -> float:
    """Smooth synthetic induction profile, zero at the root and tip."""
    return 0.25 * math.sin(math.pi * min(r, RADIUS) / RADIUS)


def theory_per_radius(r: float, a: float, rho: float = RHO) -> float:
    return 2.0 * rho * U_INF**2 * a * (1.0 - a) * 2.0 * math.pi * r


def _write_rings(
    samples: Path,
    planes: tuple[tuple[str, float], ...] = (("p0.0000", 1.0),),
    time_name: str = "3.339",
    a_of_r=induction,
) -> None:
    """One ring file per radius and plane, a azimuthally varying around its mean.

    The 12 equal-dTheta points make the cosine term cancel, so only an
    azimuthal MEAN recovers ``a``.
    """
    folder = samples / time_name
    folder.mkdir(parents=True)
    for plane, scale in planes:
        for k in range(N_RINGS):
            rel = 0.05 + 0.01 * k
            r = rel * RADIUS
            a = a_of_r(r) * scale
            lines = []
            for j in range(POINTS_PER_RING):
                theta = 2.0 * math.pi * j / POINTS_PER_RING
                ux = U_INF * (1.0 - a) * (1.0 + 0.1 * math.cos(theta))
                y = r * math.cos(theta)
                z = ORIGIN[2] + r * math.sin(theta)
                lines.append(f"0 \t{y:.8g} \t{z:.8g} \t{ux:.10g} \t0 \t0")
            (folder / f"ring_x{plane}_r{rel:.4f}_U.xy").write_text("\n".join(lines) + "\n")


ELEMENT_HEADER = "time,root_dist,x,y,z,rel_vel_mag,Re,alpha_deg,cl,cd,fx,fy,fz\n"


def _element_radii() -> list[float]:
    return [RADIUS * (0.2 + 0.75 * i / (N_ELEMENTS - 1)) for i in range(N_ELEMENTS)]


def _write_elements(
    run: Path,
    folder: str,
    times: list[float],
    scale: float = 1.0,
    a_of_r=induction,
    rho: float = RHO,
    blades: int = 3,
) -> None:
    """Element CSVs whose fx is the theory value times dr / blades, times scale."""
    radii = _element_radii()
    dr = radii[1] - radii[0]
    target = run / "postProcessing" / "actuatorLineElements" / folder
    target.mkdir(parents=True, exist_ok=True)
    for blade in range(1, blades + 1):
        for n, r in enumerate(radii):
            fx = theory_per_radius(r, a_of_r(r), rho) * dr / blades * scale
            # Real layout: root_dist is a 0..1 span fraction from the hub (NOT r/R),
            # and x,y,z sit at radius r around the axis, with an axial and a
            # lateral offset like the real blade (blade pointing +z).
            span = (r - HUB) / (RADIUS - HUB)
            y = -0.05
            z = ORIGIN[2] + math.sqrt(r * r - y * y)
            rows = [ELEMENT_HEADER]
            for t in times:
                rows.append(f"{t},{span:.10g},0.013,{y},{z:.10g},10,1e5,5,0.5,0.01,{fx:.12g},0,0\n")
            (target / f"turbine.blade{blade}.element{n}.csv").write_text("".join(rows))


def _case(tmp_path: Path, scale: float = 1.0) -> tuple[Path, Path]:
    samples = tmp_path / "postProcessing" / "inductionClosureSample"
    _write_rings(samples)
    run = tmp_path
    _write_elements(run, "0", [1.0, 2.0, 3.0, 4.0], scale=scale)
    return samples, run


def _run(tool, samples: Path, run: Path, *extra: str, capsys=None):
    argv = [
        "analyse",
        str(samples),
        str(run),
        "--rho",
        str(RHO),
        "--u-inf",
        str(U_INF),
        "--radius",
        str(RADIUS),
        "--wind",
        "1",
        "0",
        "0",
        *ROTOR_ARGS,
        "--t-from",
        "1",
        "--t-to",
        "4",
        "--json",
        *extra,
    ]
    code = tool.main(argv)
    out = capsys.readouterr().out if capsys else ""
    return code, out


def test_exact_force_gives_ratio_one(tool, tmp_path, capsys):
    samples, run = _case(tmp_path)
    code, out = _run(tool, samples, run, capsys=capsys)
    assert code == 0
    result = json.loads(out)
    plane = result["planes"][0]
    assert len(plane["rows"]) == N_ELEMENTS
    for row in plane["rows"]:
        assert row["ratio"] == pytest.approx(1.0, abs=2e-3)
    assert plane["integrated_ratio"] == pytest.approx(1.0, abs=1e-3)
    assert plane["integrated_actual"] == pytest.approx(plane["integrated_theory"], rel=1e-3)


def test_element_radius_comes_from_position_not_root_dist(tool, tmp_path, capsys):
    samples, run = _case(tmp_path)
    code, out = _run(tool, samples, run, capsys=capsys)
    assert code == 0
    got = [row["r_over_R"] for row in json.loads(out)["planes"][0]["rows"]]
    assert got == pytest.approx([r / RADIUS for r in _element_radii()], abs=1e-6)


def test_wrong_force_moves_the_ratio_by_the_same_factor(tool, tmp_path, capsys):
    samples, run = _case(tmp_path, scale=0.8)
    code, out = _run(tool, samples, run, capsys=capsys)
    assert code == 0
    plane = json.loads(out)["planes"][0]
    for row in plane["rows"]:
        assert row["ratio"] == pytest.approx(0.8, abs=2e-3)
    assert plane["integrated_ratio"] == pytest.approx(0.8, abs=1e-3)


def test_kinematic_forces_use_rho_one(tool, tmp_path, capsys):
    """Forces per unit density (the incompressible solver) pair with --rho 1."""
    samples = tmp_path / "postProcessing" / "inductionClosureSample"
    _write_rings(samples)
    _write_elements(tmp_path, "0", [1.0, 2.0, 3.0, 4.0], rho=1.0)
    argv = [
        "analyse", str(samples), str(tmp_path), "--rho", "1", "--u-inf", str(U_INF),
        "--radius", str(RADIUS), "--wind", "1", "0", "0", *ROTOR_ARGS,
        "--t-from", "1", "--t-to", "4", "--json",
    ]  # fmt: skip
    assert tool.main(argv) == 0
    plane = json.loads(capsys.readouterr().out)["planes"][0]
    assert plane["integrated_ratio"] == pytest.approx(1.0, abs=1e-3)


def test_split_history_is_read_as_a_union(tool, tmp_path, capsys):
    samples = tmp_path / "postProcessing" / "inductionClosureSample"
    _write_rings(samples)
    # "10" sorts before "2" as text; the numeric order is 2 then 10.
    _write_elements(tmp_path, "2", [2.0, 3.0, 4.0, 5.0], scale=1.0)
    _write_elements(tmp_path, "10", [6.0, 7.0, 8.0, 9.0], scale=0.6)
    code, out = _run(tool, samples, tmp_path, "--t-from", "2", "--t-to", "9", capsys=capsys)
    assert code == 0
    result = json.loads(out)
    assert result["window"]["t_from"] == 2.0
    assert result["window"]["t_to"] == 9.0
    assert result["window"]["rows"] == 8
    assert result["planes"][0]["integrated_ratio"] == pytest.approx(0.8, abs=1e-3)


def test_window_excludes_rows_outside_it(tool, tmp_path, capsys):
    samples = tmp_path / "postProcessing" / "inductionClosureSample"
    _write_rings(samples)
    _write_elements(tmp_path, "0", [1.0, 2.0], scale=5.0)  # junk transient
    _write_elements(tmp_path, "3", [3.0, 4.0], scale=1.0)
    code, out = _run(tool, samples, tmp_path, "--t-from", "3", "--t-to", "4", capsys=capsys)
    assert code == 0
    assert json.loads(out)["planes"][0]["integrated_ratio"] == pytest.approx(1.0, abs=1e-3)


def test_default_window_is_the_last_half_and_is_announced(tool, tmp_path, capsys):
    samples = tmp_path / "postProcessing" / "inductionClosureSample"
    _write_rings(samples)
    _write_elements(tmp_path, "0", [0.0, 1.0, 2.0, 3.0], scale=9.0)
    _write_elements(tmp_path, "4", [4.0, 5.0, 6.0, 7.0], scale=1.0)
    argv = [
        "analyse", str(samples), str(tmp_path), "--rho", str(RHO), "--u-inf", str(U_INF),
        "--radius", str(RADIUS), "--wind", "1", "0", "0", *ROTOR_ARGS,
    ]  # fmt: skip
    assert tool.main(argv) == 0
    text = capsys.readouterr().out
    assert "default window" in text
    assert "t = 3.5 .. 7" in text.replace("3.50", "3.5")
    assert tool.main([*argv, "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["window"]["defaulted"] is True
    assert result["planes"][0]["integrated_ratio"] == pytest.approx(1.0, abs=1e-3)


def test_high_induction_is_flagged(tool, tmp_path, capsys):
    def strong(r: float) -> float:
        return 0.5 * math.sin(math.pi * min(r, RADIUS) / RADIUS)

    samples = tmp_path / "postProcessing" / "inductionClosureSample"
    _write_rings(samples, a_of_r=strong)
    _write_elements(tmp_path, "0", [1.0, 2.0], a_of_r=strong)
    code, out = _run(tool, samples, tmp_path, "--t-to", "2", capsys=capsys)
    assert code == 0
    rows = json.loads(out)["planes"][0]["rows"]
    flagged = [row for row in rows if row["a"] >= 0.4]
    assert flagged and all(row["flag"] for row in flagged)
    assert all(not row["flag"] for row in rows if row["a"] < 0.4)


def test_each_plane_gets_its_own_table(tool, tmp_path, capsys):
    samples = tmp_path / "postProcessing" / "inductionClosureSample"
    _write_rings(samples, planes=(("p0.0000", 1.0), ("m0.2500", 0.9), ("m1.0000", 0.5)))
    _write_elements(tmp_path, "0", [1.0, 2.0])
    code, out = _run(tool, samples, tmp_path, "--t-to", "2", capsys=capsys)
    assert code == 0
    planes = json.loads(out)["planes"]
    assert [p["offset"] for p in planes] == [-1.0, -0.25, 0.0]
    assert planes[2]["integrated_ratio"] == pytest.approx(1.0, abs=1e-3)
    assert planes[1]["integrated_ratio"] != pytest.approx(1.0, abs=1e-2)


def test_csv_output_has_one_row_per_plane_and_element(tool, tmp_path, capsys):
    samples, run = _case(tmp_path)
    out = tmp_path / "closure.csv"
    code, _ = _run(tool, samples, run, "--csv", str(out), capsys=capsys)
    assert code == 0
    lines = out.read_text().splitlines()
    assert lines[0].split(",")[:3] == ["plane", "r_over_R", "a"]
    assert len(lines) == 1 + N_ELEMENTS


def test_write_dict_has_one_circle_set_per_radius_and_plane(tool, tmp_path):
    out = tmp_path / "inductionClosureSample"
    code = tool.main(
        [
            "write-dict", "--origin", "0", "0", "12.192", "--axis", "-1", "0", "0",
            "--wind", "1", "0", "0", "--radius", "5.029", "--n-radii", "7",
            "--out", str(out),
        ]
    )  # fmt: skip
    assert code == 0
    text = out.read_text()
    assert text.count("type            circle;") == 7 * 3
    assert "setFormat       raw;" in text
    assert "ring_xm0.2500_r0.0500" in text
    assert "ring_xp0.0000_r1.3000" in text
    assert "ring_xm1.0000_r0.6750" in text
    # upstream plane at -0.25 R along the wind (+x): origin x = -0.25 * 5.029
    assert "origin          (-1.25725 0 12.192);" in text


def _vector_entry(text: str, key: str) -> np.ndarray:
    match = re.search(key + r"\s+\(([^)]*)\)", text)
    assert match is not None, key
    return np.array([float(v) for v in match.group(1).split()])


def test_write_dict_start_point_is_perpendicular_at_ring_radius(tool, tmp_path):
    out = tmp_path / "d"
    assert tool.main(
        ["write-dict", "--origin", "1", "2", "3", "--axis", "1", "1", "0", "--radius", "2",
         "--n-radii", "2", "--planes", "0", "--out", str(out)]
    ) == 0  # fmt: skip
    text = out.read_text()
    origin = _vector_entry(text, "origin")
    start = _vector_entry(text, "startPoint")
    axis = np.array([1.0, 1.0, 0.0]) / math.sqrt(2.0)
    assert abs(np.dot(start - origin, axis)) < 1e-6
    assert np.linalg.norm(start - origin) == pytest.approx(0.05 * 2.0, rel=1e-6)


def test_missing_rho_exits_with_usage_code(tool, tmp_path):
    samples, run = _case(tmp_path)
    with pytest.raises(SystemExit) as exc:
        tool.main(["analyse", str(samples), str(run), "--u-inf", "7", "--radius", "5",
                   "--wind", "1", "0", "0"])  # fmt: skip
    assert exc.value.code == 2


def test_missing_paths_exit_one(tool, tmp_path, capsys):
    samples, run = _case(tmp_path)
    code, _ = _run(tool, tmp_path / "absent", run, capsys=capsys)
    assert code == 1
    code, _ = _run(tool, samples, tmp_path / "absent", capsys=capsys)
    assert code == 1


def test_run_without_element_csvs_exits_one(tool, tmp_path, capsys):
    samples = tmp_path / "postProcessing" / "inductionClosureSample"
    _write_rings(samples)
    code, _ = _run(tool, samples, tmp_path, capsys=capsys)
    assert code == 1


def test_empty_window_exits_three(tool, tmp_path, capsys):
    samples, run = _case(tmp_path)
    code, _ = _run(tool, samples, run, "--t-from", "50", "--t-to", "60", capsys=capsys)
    assert code == 3
