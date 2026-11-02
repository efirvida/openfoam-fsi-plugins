# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure-Python checks for the IEA 22-280-RWT case package (``validation/iea22mw``).

Covers the radius decision, the committed geometry table, the committed
``profileData`` polars, the generated case skeleton and the ``--check`` modes.
The tests never need OpenFOAM. Checks that read the external, read-only source
repository (``IEA22MW_BLADE_FILE``, ``IEA22MW_WINDIO``, ``IEA22MW_AEROFOIL_DIR``;
defaults under ``tmp/iea22-src/repo``) skip when it is absent.
"""

from __future__ import annotations

import importlib.util
import math
import re
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PACKAGE = TESTS_DIR.parent / "validation" / "iea22mw"
IEA15_PACKAGE = TESTS_DIR.parent / "validation" / "iea15mw"
GEOMETRY = PACKAGE / "data" / "iea22mw_blade.csv"
POLARS = PACKAGE / "data" / "polars"


def _load(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


blade_geometry = _load("iea22mw_test_blade_geometry", PACKAGE / "tools" / "blade_geometry.py")
build_polars = _load("iea22mw_test_build_polars", PACKAGE / "scripts" / "buildPolars.py")
generate_case = _load("iea22mw_test_generate_case", PACKAGE / "tools" / "generate_case.py")

SOURCE_AVAILABLE = (
    blade_geometry.DEFAULT_BLADE_FILE.exists() and blade_geometry.DEFAULT_WINDIO.exists()
)
needs_source = pytest.mark.skipif(
    not SOURCE_AVAILABLE, reason="IEA-22 read-only source repository not available"
)


# --- radius decision (S4) ------------------------------------------------------
def test_radius_decision_is_the_unprojected_tip_radius():
    assert blade_geometry.ROTOR_DIAMETER_PUBLISHED == 284.0
    assert blade_geometry.ROTOR_RADIUS_PUBLISHED == 142.0
    assert blade_geometry.HUB_RADIUS == pytest.approx(4.2)
    assert blade_geometry.PRECONE_DEG == 4.0
    # R = HubRad + span (ElastoDyn TipRad), NOT the precone projection.
    assert blade_geometry.TIP_RADIUS_STRUCTURAL == pytest.approx(142.0)
    assert blade_geometry.ROTOR_RADIUS_PUBLISHED != pytest.approx(
        blade_geometry.TIP_RADIUS_STRUCTURAL * math.cos(math.radians(4.0)), abs=0.1
    )


@needs_source
def test_radius_matches_workbook_tip_speed_and_elastodyn():
    openpyxl = pytest.importorskip("openpyxl")
    src = blade_geometry.DEFAULT_WINDIO.parents[1]
    workbook = openpyxl.load_workbook(
        src / "Documentation" / "IEA-22-280-RWT_tabular.xlsx", data_only=True
    )
    rows = list(workbook["Rotor Performance - WISDEM"].iter_rows(values_only=True))
    rpm, tip_speed = rows[1][5], rows[1][6]
    assert tip_speed / (rpm * 2.0 * math.pi / 60.0) == pytest.approx(142.0, abs=1e-6)
    elastodyn = (
        src / "OpenFAST" / "IEA-22-280-RWT-Monopile" / "IEA-22-280-RWT_ElastoDyn.dat"
    ).read_text(encoding="utf-8")
    values = {
        key: float(re.search(rf"^\s*(\S+)\s+{key}\b", elastodyn, re.M).group(1))
        for key in ("TipRad", "HubRad")
    }
    assert values["TipRad"] == pytest.approx(blade_geometry.ROTOR_RADIUS_PUBLISHED)
    assert values["HubRad"] == pytest.approx(blade_geometry.HUB_RADIUS)


# --- committed geometry --------------------------------------------------------
def test_geometry_table_shape_and_radius():
    rows = blade_geometry.read_geometry()
    assert len(rows) == 59
    assert [r["airfoil_id"] for r in rows] == list(range(1, 60))
    assert rows[0]["radius_m"] == pytest.approx(4.2)
    assert rows[0]["span_m"] == 0.0
    assert rows[-1]["radius_m"] == pytest.approx(142.0)
    assert rows[-1]["r_over_R"] == pytest.approx(1.0)
    assert all(b["radius_m"] > a["radius_m"] for a, b in zip(rows, rows[1:]))
    assert all(
        r["r_over_R"] == pytest.approx(r["radius_m"] / 142.0, rel=1e-8) for r in rows
    )


def test_geometry_alm_conventions():
    rows = blade_geometry.read_geometry()
    for row in rows:
        assert row["pitch_deg"] == pytest.approx(-row["twist_deg"], abs=1e-8)
        assert row["axial_distance_m"] == pytest.approx(-row["crv_ac_m"], abs=1e-8)
        assert row["curve_angle_deg"] == pytest.approx(row["crv_ang_deg"], abs=1e-8)
        assert 0.25 - 1e-9 <= row["chord_mount"] <= 0.5 + 1e-9
    assert rows[0]["chord_mount"] == 0.5  # circular root
    assert rows[-1]["chord_mount"] == 0.25
    assert rows[-1]["axial_distance_m"] == pytest.approx(7.0)  # 7 m prebend
    assert rows[-1]["chord_m"] == pytest.approx(0.4)


def test_element_rows_apply_collective_pitch_with_alm_sign():
    base = blade_geometry.element_rows()
    shifted = blade_geometry.element_rows(collective_pitch_deg=2.0)
    assert len(base) == 59 and all(len(row) == 7 for row in base)
    for a, b in zip(base, shifted):
        assert b[5] == pytest.approx(a[5] - 2.0)
        assert b[:5] == a[:5] and b[6] == a[6]


def test_read_blade_table_rejects_wrong_station_count(tmp_path):
    table = tmp_path / "blade.dat"
    table.write_text(
        "header\n" + "\n".join(f"{i} 0 0 0 1 2 {i + 1}" for i in range(58)) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(blade_geometry.GeometryError, match="expected 59"):
        blade_geometry.read_blade_table(table)


@needs_source
def test_committed_geometry_is_not_stale():
    rows = blade_geometry.build_rows(
        blade_geometry.read_blade_table(),
        center_grid=blade_geometry.aerodynamic_center_grid(),
    )
    assert blade_geometry.render_csv(rows) == GEOMETRY.read_text(encoding="utf-8")
    chord_diff, twist_diff = blade_geometry.windio_cross_check(rows)
    assert chord_diff < 0.05 and twist_diff < 0.05


@needs_source
def test_geometry_main_check_modes(monkeypatch, tmp_path, capsys):
    assert blade_geometry.main(["--check"]) == 0
    monkeypatch.setattr(blade_geometry, "BLADE_CSV", tmp_path / "missing.csv")
    assert blade_geometry.main(["--check"]) == 1
    stale = tmp_path / "stale.csv"
    stale.write_text("stale\n", encoding="utf-8")
    monkeypatch.setattr(blade_geometry, "BLADE_CSV", stale)
    assert blade_geometry.main(["--check"]) == 1
    assert stale.read_text(encoding="utf-8") == "stale\n"  # --check never writes
    assert "stale geometry file" in capsys.readouterr().err


@needs_source
def test_windio_readers_feed_tower_and_nacelle():
    tower = blade_geometry.read_tower_table()
    assert tower[0]["z"] == pytest.approx(15.0)
    assert tower[-1]["z"] == pytest.approx(164.386)
    assert tower[0]["diameter"] == pytest.approx(10.0)
    assert {s["cd"] for s in tower} == {0.5}
    assert blade_geometry.read_tower_overhang() == pytest.approx(14.0)
    nacelle = blade_geometry.read_nacelle_drivetrain()
    assert math.degrees(nacelle["uptilt"]) == pytest.approx(6.0)
    assert nacelle["rad_ag"] == pytest.approx(4.89) and nacelle["h_m"] == nacelle["h_yr"] == 0.0


# --- committed polars ----------------------------------------------------------
def _polar_rows(path: Path) -> list[tuple[float, float, float, float]]:
    text = path.read_text(encoding="utf-8")
    body = text[text.index("data") :]
    return [
        tuple(float(v) for v in match.groups())
        for match in re.finditer(r"^\s*\(([-\d.e+]+) ([-\d.e+]+) ([-\d.e+]+) ([-\d.e+]+)\)", body, re.M)
    ]


def test_committed_polars_cover_every_station():
    files = sorted(POLARS.glob("polar_*.dat"))
    assert [f.name for f in files] == [f"polar_{i:02d}.dat" for i in range(59)]
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert re.search(r"^Re 3e\+06;$", text, re.M)
        assert re.search(r"^liftReCorrExp 0;$", text, re.M)
        rows = _polar_rows(path)
        assert len(rows) == 200
        alphas = [r[0] for r in rows]
        assert alphas[0] == -180.0 and alphas[-1] == 180.0
        assert all(b > a for a, b in zip(alphas, alphas[1:]))


@needs_source
def test_polars_round_trip_source_without_modification():
    sources = build_polars.discover_sources()
    assert sorted(sources) == list(range(59))
    for station, source in sources.items():
        parsed = build_polars.parse_airfoilinfo(source)
        committed = _polar_rows(POLARS / f"polar_{station:02d}.dat")
        assert len(committed) == len(parsed["rows"])
        for got, want in zip(committed, parsed["rows"]):
            assert got == pytest.approx(want, abs=1e-6)  # Cm unchanged too


@needs_source
def test_polar_index_matches_aerodyn_airfoil_order():
    aerodyn = (
        blade_geometry.DEFAULT_WINDIO.parents[1]
        / "OpenFAST"
        / "IEA-22-280-RWT-Monopile"
        / "IEA-22-280-RWT_AeroDyn15.dat"
    ).read_text(encoding="utf-8")
    names = re.findall(r'^"[^"]*Polar_(\d{2})\.dat"', aerodyn, re.M)
    assert names == [f"{i:02d}" for i in range(59)]


@needs_source
def test_polars_main_check_modes(monkeypatch, tmp_path, capsys):
    assert build_polars.main(["--check"]) == 0
    monkeypatch.setattr(build_polars, "POLARS_DIR", tmp_path)
    assert build_polars.main(["--check"]) == 1
    assert "missing polar file" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []  # --check never writes
    assert build_polars.main(["--check", "--source-dir", str(tmp_path / "none")]) == 1


# --- generated case ------------------------------------------------------------
@needs_source
def test_generated_case_is_not_stale():
    assert generate_case.main(["--check"]) == 0


def test_generated_case_uses_iea22_values():
    text = (PACKAGE / "case" / "system" / "fvOptions").read_text(encoding="utf-8")
    assert "rotorRadius 142;" in text
    assert "coneAngle 4;" in text
    assert "freeStreamVelocity (0 11.134927 0);" in text
    assert "tipSpeedRatio 9.1532" in text
    assert text.count("polar_") >= 59 and "polar_58" in text and "polar_59" not in text
    assert "nElements 174;" in text
    for path in (PACKAGE / "case").rglob("*"):
        if path.is_file():
            body = path.read_text(encoding="utf-8")
            assert "iea15" not in body.lower(), path
            assert "10.659" not in body, path
    block = (PACKAGE / "case" / "system" / "blockMeshDict").read_text(encoding="utf-8")
    assert "-170)" in block  # floor at -hub height


def test_generate_case_check_detects_stale_and_does_not_write(tmp_path, capsys):
    case = tmp_path / "case"
    assert generate_case.main(["--case-dir", str(case), "--check"]) == 1
    assert not case.exists()
    captured = capsys.readouterr()
    assert "missing" in (captured.out + captured.err).lower()


def test_generate_case_isolated_from_iea15(monkeypatch):
    previous = sys.modules.get("blade_geometry")
    iea15 = _load("iea22mw_test_iea15_generate_case", IEA15_PACKAGE / "tools" / "generate_case.py")
    assert sys.modules.get("blade_geometry") is not generate_case.blade_geometry
    assert len(iea15.blade_profile_names()) == 50
    assert len(generate_case.blade_profile_names()) == 59
    assert iea15.ROTOR_RADIUS == pytest.approx(120.67532316)
    assert generate_case.ROTOR_RADIUS == 142.0
    assert sys.modules.get("blade_geometry") is previous or previous is None


def test_generate_case_cli_defaults():
    assert generate_case.RATED_SPEED == pytest.approx(11.134927)
    assert generate_case.tip_speed_ratio(
        generate_case.RATED_SPEED, generate_case.RATED_RPM
    ) == pytest.approx(9.1532, abs=1e-3)
    assert generate_case.N_ELEMENTS == 3 * 58
    assert generate_case.ROTOR_DIAMETER == 284.0
