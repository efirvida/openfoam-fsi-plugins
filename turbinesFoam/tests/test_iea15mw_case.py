# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure-Python checks for the IEA 15-240-RWT P0/P1 case package.

Covers the committed blade geometry table, the ALM conversion conventions, the
AirfoilInfo -> ``profileData`` converter and the committed polars. These tests
never require OpenFOAM; the external read-only inputs default to the documented
absolute paths and can be overridden with ``IEA15MW_BLADE_FILE``,
``IEA15MW_WINDIO`` and ``IEA15MW_AEROFOIL_DIR``.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
TURBINESFOAM = TESTS_DIR.parent
PACKAGE = TURBINESFOAM / "validation" / "iea15mw"
DATA = PACKAGE / "data"
GEOMETRY = DATA / "iea15mw_blade.csv"
POLARS = DATA / "polars"


def _load(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


blade_geometry = _load("iea15mw_blade_geometry", PACKAGE / "tools" / "blade_geometry.py")
build_polars = _load("iea15mw_build_polars", PACKAGE / "scripts" / "buildPolars.py")

#: Stated absolute tolerance for the converter round trip (alpha, Cl, Cd, Cm).
ROUND_TRIP_TOLERANCE = 1e-6


# ---------------------------------------------------------------------------
# P0 — geometry table
# ---------------------------------------------------------------------------
class TestGeometryTable:
    def test_fifty_monotone_stations(self):
        rows = blade_geometry.read_geometry(GEOMETRY)
        assert len(rows) == 50
        assert all(b["r_over_R"] > a["r_over_R"] for a, b in zip(rows, rows[1:]))
        assert all(b["radius_m"] > a["radius_m"] for a, b in zip(rows, rows[1:]))
        assert all(b["span_m"] > a["span_m"] for a, b in zip(rows, rows[1:]))

    def test_chord_and_twist_match_aerodyn_source(self):
        source = blade_geometry.read_blade_table()
        rows = blade_geometry.build_rows(source)
        assert len(rows) == len(source) == 50
        for row, station in zip(rows, source):
            assert row["chord_m"] == pytest.approx(station["chord"], abs=1e-9)
            assert row["twist_deg"] == pytest.approx(station["twist"], abs=1e-9)
            assert row["span_m"] == pytest.approx(station["span"], abs=1e-9)
            assert row["airfoil_id"] == pytest.approx(station["af_id"], abs=0)

    def test_committed_csv_matches_source(self):
        committed = blade_geometry.read_geometry(GEOMETRY)
        built = blade_geometry.build_rows(blade_geometry.read_blade_table())
        # ``pitch_axis`` is filled by the WindIO cross-check only; it is covered
        # by ``test_pitch_axis_is_not_the_chord_mount``.
        columns = [key for key in blade_geometry.COLUMNS if key != "pitch_axis"]
        for committed_row, built_row in zip(committed, built):
            for key in columns:
                # The committed CSV carries 10 significant digits.
                assert committed_row[key] == pytest.approx(built_row[key], abs=1e-6)

    def test_span_and_radius_reconcile_with_radius_decision(self):
        rows = blade_geometry.read_geometry(GEOMETRY)
        span_tip = rows[-1]["span_m"]
        radius_tip = rows[-1]["radius_m"]
        # Blade span is the yaml reference-axis extent (117.0 m nominal; the
        # AeroDyn table resolves it to 116.999931 m).
        assert span_tip == pytest.approx(117.0, abs=1e-3)
        # Along-blade radius = HubRad + span, matching ElastoDyn TipRad.
        assert radius_tip == pytest.approx(blade_geometry.HUB_RADIUS + span_tip, abs=1e-9)
        assert radius_tip == pytest.approx(120.9699, abs=1e-3)
        # The published radius is the 4 deg precone projection of TipRad. The
        # nominal span (117.0 m) reproduces the published value exactly; the
        # table's tip resolves 0.07 mm short, so its projected radius is 7e-5 m
        # below R (r/R -> 1.0 within 1e-6).
        assert (blade_geometry.HUB_RADIUS + blade_geometry.BLADE_SPAN) * math.cos(
            math.radians(blade_geometry.PRECONE_DEG)
        ) == pytest.approx(blade_geometry.ROTOR_RADIUS_PUBLISHED, abs=1e-6)
        projected = radius_tip * math.cos(math.radians(blade_geometry.PRECONE_DEG))
        assert projected == pytest.approx(blade_geometry.ROTOR_RADIUS_PUBLISHED, abs=1e-3)
        # ... and the table normalises by it, so the tip is at r/R = 1.
        assert rows[-1]["r_over_R"] == pytest.approx(1.0, abs=2e-6)
        assert rows[0]["r_over_R"] > 0.0

    def test_published_values(self):
        assert blade_geometry.ROTOR_DIAMETER_PUBLISHED == pytest.approx(241.35064632, abs=1e-8)
        assert blade_geometry.ROTOR_RADIUS_PUBLISHED == pytest.approx(120.67532316, abs=1e-8)
        assert blade_geometry.HUB_DIAMETER == pytest.approx(7.94, abs=1e-9)
        assert blade_geometry.HUB_RADIUS == pytest.approx(3.97, abs=1e-9)
        assert blade_geometry.TIP_RADIUS_STRUCTURAL == pytest.approx(120.97, abs=1e-9)
        assert blade_geometry.PRECONE_DEG == pytest.approx(4.0, abs=1e-9)

    def test_hub_radius_from_published_radius(self):
        # HubRad = R / cos(precone) - blade_span, i.e. the published R is not a
        # naive R - span subtraction.
        derived = (
            blade_geometry.ROTOR_RADIUS_PUBLISHED
            / math.cos(math.radians(blade_geometry.PRECONE_DEG))
            - blade_geometry.BLADE_SPAN
        )
        assert derived == pytest.approx(blade_geometry.HUB_RADIUS, abs=1e-6)
        naive = blade_geometry.ROTOR_RADIUS_PUBLISHED - blade_geometry.BLADE_SPAN
        assert abs(naive - blade_geometry.HUB_RADIUS) > 0.29  # the precone gap


class TestAlmConventions:
    def test_chord_mount_is_quarter_chord_outboard(self):
        rows = blade_geometry.read_geometry(GEOMETRY)
        # The FFA-W3 families (the outboard majority) are at the quarter chord.
        at_quarter = [row for row in rows if row["chord_mount"] == pytest.approx(0.25, abs=1e-9)]
        assert len(at_quarter) >= 35
        # Root cylinder at 0.5 and a monotone blend toward the lifting sections.
        assert rows[0]["chord_mount"] == pytest.approx(0.5, abs=1e-9)
        assert max(row["chord_mount"] for row in rows) == pytest.approx(0.5, abs=1e-9)
        assert rows[-1]["chord_mount"] == pytest.approx(0.25, abs=1e-9)

    def test_pitch_axis_is_not_the_chord_mount(self):
        rows = blade_geometry.read_geometry(GEOMETRY)
        # The structural pitch axis (0.5045 -> 0.3682) is a distinct quantity.
        assert rows[0]["pitch_axis"] == pytest.approx(0.5045454545, abs=1e-6)
        assert rows[-1]["pitch_axis"] == pytest.approx(0.3681818182, abs=1e-5)
        assert abs(rows[-1]["pitch_axis"] - rows[-1]["chord_mount"]) > 0.1

    def test_twist_sign_convention(self):
        rows = blade_geometry.read_geometry(GEOMETRY)
        # Phase VI convention: pitch = -(twist + collective).
        for row in rows:
            assert row["pitch_deg"] == pytest.approx(-row["twist_deg"], abs=1e-9)
        # Positive AeroDyn twist (nose-up/feather) at the root, slightly
        # negative at the tip -> the ALM mount flips both signs.
        assert rows[0]["twist_deg"] > 0 and rows[0]["pitch_deg"] < 0
        assert rows[-1]["twist_deg"] < 0 and rows[-1]["pitch_deg"] > 0

    def test_collective_pitch_sign(self):
        source = blade_geometry.read_blade_table()
        rows = blade_geometry.build_rows(source, collective_pitch_deg=3.0)
        for row in rows:
            assert row["pitch_deg"] == pytest.approx(-(row["twist_deg"] + 3.0), abs=1e-9)

    def test_element_rows_shape(self):
        rows = blade_geometry.element_rows(GEOMETRY)
        assert len(rows) == 50
        assert all(len(row) == 6 for row in rows)
        geometry = blade_geometry.read_geometry(GEOMETRY)
        for element, row in zip(rows, geometry):
            assert element[0] == 0.0
            assert element[1] == pytest.approx(row["radius_m"], abs=1e-9)
            assert element[2] == 0.0
            assert element[3] == pytest.approx(row["chord_m"], abs=1e-9)
            assert element[4] == pytest.approx(row["chord_mount"], abs=1e-9)
            assert element[5] == pytest.approx(row["pitch_deg"], abs=1e-9)

    def test_nelements_must_be_multiple_of_49(self):
        rows = blade_geometry.read_geometry(GEOMETRY)
        segments = len(rows) - 1
        assert segments == 49
        for n_elements in (49, 98, 147, 196):
            assert n_elements % segments == 0


# ---------------------------------------------------------------------------
# P1 — AirfoilInfo -> profileData converter
# ---------------------------------------------------------------------------
def _read_emitted_rows(path: Path) -> list[list[float]]:
    rows: list[list[float]] = []
    started = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.split("!", 1)[0].strip()
        if stripped.startswith("data"):
            started = True
            continue
        if not started or not stripped.startswith("("):
            continue
        values = [float(token) for token in stripped.strip("();").split()]
        if len(values) == 4:
            rows.append(values)
    return rows


def _sources() -> dict[int, Path]:
    try:
        return build_polars.discover_sources()
    except FileNotFoundError as error:
        pytest.skip(str(error))


class TestPolarConverter:
    def test_all_fifty_polars_committed(self):
        committed = sorted(POLARS.glob("polar_*.dat"))
        assert len(committed) == 50
        assert [path.name for path in committed] == [
            f"polar_{station:02d}.dat" for station in range(50)
        ]

    def test_round_trip_all_stations(self):
        sources = _sources()
        assert len(sources) == 50
        for station, source in sorted(sources.items()):
            parsed = build_polars.parse_airfoilinfo(source)
            emitted = _read_emitted_rows(POLARS / build_polars.OUTPUT_TEMPLATE.format(station=station))
            assert len(emitted) == len(parsed["rows"]) == 200
            for got, want in zip(emitted, parsed["rows"]):
                for column, (g, w) in enumerate(zip(got, want)):
                    assert abs(g - w) <= ROUND_TRIP_TOLERANCE, (
                        f"station {station} column {column}: {g} vs {w}"
                    )

    def test_cm_is_passed_through_unchanged(self):
        # No sign conversion: the emitted Cm equals the source Cm exactly.
        sources = _sources()
        for station, source in sorted(sources.items()):
            parsed = build_polars.parse_airfoilinfo(source)
            emitted = _read_emitted_rows(POLARS / build_polars.OUTPUT_TEMPLATE.format(station=station))
            for got, want in zip(emitted, parsed["rows"]):
                assert got[3] == pytest.approx(want[3], abs=ROUND_TRIP_TOLERANCE)
        # The physical sign is the standard quarter-chord nose-down at low
        # positive alpha; a flip would make it positive.
        mid = _read_emitted_rows(POLARS / "polar_30.dat")
        low_alpha = min(mid, key=lambda row: abs(row[0] - 6.0))
        assert low_alpha[3] < 0

    def test_ua_block_and_comments_handled(self):
        # Stations 00..04 carry InclUAdata False; 05..49 carry the UA block.
        no_ua = build_polars.parse_airfoilinfo(
            build_polars.DEFAULT_SOURCE_DIR / "IEA-15-240-RWT_AeroDyn15_Polar_00.dat"
        )
        with_ua = build_polars.parse_airfoilinfo(
            build_polars.DEFAULT_SOURCE_DIR / "IEA-15-240-RWT_AeroDyn15_Polar_07.dat"
        )
        assert no_ua["incl_ua"] is False
        assert with_ua["incl_ua"] is True
        # The UA block must not leak into the data rows.
        assert len(no_ua["rows"]) == 200
        assert len(with_ua["rows"]) == 200
        assert with_ua["rows"][0][0] == pytest.approx(-180.0)
        assert with_ua["rows"][-1][0] == pytest.approx(180.0)

    def test_re_header_is_in_millions(self):
        parsed = build_polars.parse_airfoilinfo(
            build_polars.DEFAULT_SOURCE_DIR / "IEA-15-240-RWT_AeroDyn15_Polar_00.dat"
        )
        assert parsed["re_millions"] == pytest.approx(3.0, abs=1e-9)
        text = (POLARS / "polar_00.dat").read_text(encoding="utf-8")
        assert "Re 3e+06;" in text

    def test_check_mode_passes_for_committed_files(self):
        assert build_polars.main(["--check"]) == 0

    def test_check_mode_fails_when_output_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(build_polars, "POLARS_DIR", tmp_path)
        assert build_polars.main(["--check"]) == 1

    def test_check_mode_fails_when_output_stale(self, tmp_path, monkeypatch):
        monkeypatch.setattr(build_polars, "POLARS_DIR", tmp_path)
        assert build_polars.main([]) == 0
        stale = tmp_path / "polar_30.dat"
        stale.write_text(stale.read_text(encoding="utf-8") + "// tampered\n", encoding="utf-8")
        assert build_polars.main(["--check"]) == 1

    def test_check_mode_fails_when_source_missing(self, tmp_path):
        assert build_polars.main(["--check", "--source-dir", str(tmp_path / "nope")]) == 1


# ---------------------------------------------------------------------------
# Cross-checks against the read-only external sources
# ---------------------------------------------------------------------------
class TestExternalCrossChecks:
    def test_geometry_check_mode_passes(self):
        assert blade_geometry.main(["--check"]) == 0

    def test_windio_chord_and_twist_agree(self):
        if not blade_geometry.DEFAULT_WINDIO.exists():
            pytest.skip(f"WindIO yaml not present: {blade_geometry.DEFAULT_WINDIO}")
        rows = blade_geometry.build_rows(blade_geometry.read_blade_table())
        # apply_windio_pitch_axis raises if the twist disagrees beyond 1e-4 deg
        # and returns the maximum chord difference.
        max_chord_diff = blade_geometry.apply_windio_pitch_axis(rows)
        assert max_chord_diff < 2e-4

    def test_cm_convention_matches_windio_sign(self):
        if not blade_geometry.DEFAULT_WINDIO.exists():
            pytest.skip(f"WindIO yaml not present: {blade_geometry.DEFAULT_WINDIO}")
        yaml = pytest.importorskip("yaml")
        data = yaml.safe_load(blade_geometry.DEFAULT_WINDIO.read_text(encoding="utf-8"))
        airfoil = next(entry for entry in data["airfoils"] if entry["name"] == "FFA-W3-241")
        polar = airfoil["polars"][0]
        alpha_deg = [math.degrees(value) for value in polar["c_l"]["grid"]]
        windio_cm = list(polar["c_m"]["values"])

        def interp_windio_cm(alpha: float) -> float:
            if alpha <= alpha_deg[0]:
                return windio_cm[0]
            if alpha >= alpha_deg[-1]:
                return windio_cm[-1]
            for i in range(len(alpha_deg) - 1):
                if alpha_deg[i] <= alpha <= alpha_deg[i + 1]:
                    ratio = (alpha - alpha_deg[i]) / (alpha_deg[i + 1] - alpha_deg[i])
                    return windio_cm[i] + ratio * (windio_cm[i + 1] - windio_cm[i])
            raise AssertionError("unreachable")

        emitted = _read_emitted_rows(POLARS / "polar_31.dat")
        pairs = [(row[3], interp_windio_cm(row[0])) for row in emitted]
        # Same sign convention: the AeroDyn Cm and the WindIO c_m correlate
        # strongly and positively (a sign flip would give ~ -1).
        n = len(pairs)
        mean_a = sum(a for a, _ in pairs) / n
        mean_b = sum(b for _, b in pairs) / n
        cov = sum((a - mean_a) * (b - mean_b) for a, b in pairs)
        var_a = sum((a - mean_a) ** 2 for a, _ in pairs)
        var_b = sum((b - mean_b) ** 2 for _, b in pairs)
        correlation = cov / math.sqrt(var_a * var_b)
        assert correlation > 0.99
