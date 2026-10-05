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
import re
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


def _v_add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _v_scale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _v_rot(v, axis, angle):
    """Rodrigues rotation about ``axis`` through the origin (matches
    ``actuatorLineElement::rotateVector``)."""
    x, y, z = axis
    c, s = math.cos(angle), math.sin(angle)
    rm = (
        (x * x + (1 - x * x) * c, x * y * (1 - c) - z * s, x * z * (1 - c) + y * s),
        (x * y * (1 - c) + z * s, y * y + (1 - y * y) * c, y * z * (1 - c) - x * s),
        (x * z * (1 - c) - y * s, y * z * (1 - c) + x * s, z * z + (1 - z * z) * c),
    )
    return tuple(sum(rm[i][j] * v[j] for j in range(3)) for i in range(3))


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
        assert all(len(row) == 7 for row in rows)
        geometry = blade_geometry.read_geometry(GEOMETRY)
        for element, row in zip(rows, geometry):
            assert element[0] == pytest.approx(row["axial_distance_m"], abs=1e-9)
            assert element[1] == pytest.approx(row["radius_m"], abs=1e-9)
            assert element[2] == pytest.approx(row["azimuth_deg"], abs=1e-9)
            assert element[3] == pytest.approx(row["chord_m"], abs=1e-9)
            assert element[4] == pytest.approx(row["chord_mount"], abs=1e-9)
            assert element[5] == pytest.approx(row["pitch_deg"], abs=1e-9)
            assert element[6] == pytest.approx(row["curve_angle_deg"], abs=1e-9)

    def test_blade_shape_columns_match_aerodyn(self):
        rows = blade_geometry.read_geometry(GEOMETRY)
        source = blade_geometry.read_blade_table()
        for row, station in zip(rows, source):
            # The committed CSV carries 10 significant digits.
            assert row["crv_ac_m"] == pytest.approx(station["crv_ac"], abs=1e-9)
            assert row["swp_ac_m"] == pytest.approx(station["swp_ac"], abs=1e-9)
            assert row["crv_ang_deg"] == pytest.approx(station["crv_ang"], abs=1e-9)
            # axialDistance = -BlCrvAC (prebend), curveAngle = BlCrvAng.
            assert row["axial_distance_m"] == pytest.approx(-station["crv_ac"], abs=1e-9)
            assert row["curve_angle_deg"] == pytest.approx(station["crv_ang"], abs=1e-9)
            # azimuth = asin(BlSwpAC / radius).
            expected = math.degrees(
                math.asin(max(-1.0, min(1.0, station["swp_ac"] / row["radius_m"])))
            )
            assert row["azimuth_deg"] == pytest.approx(expected, abs=1e-9)
        # The tip prebend is ~4 m upwind and the tip curve angle ~-5.77 deg.
        assert rows[-1]["axial_distance_m"] == pytest.approx(3.9987, abs=1e-3)
        assert rows[-1]["curve_angle_deg"] == pytest.approx(-5.7654, abs=1e-3)

    def test_element_positions_reproduce_aerodyn_locus(self):
        """The ALM aero-centre positions must match the AeroDyn node locus.

        Mirrors ``axialFlowTurbineALSource.C`` (cone about the tangential,
        azimuth about the rotor axis) and AeroDyn's ``position = root +
        RefOrientation @ (BlCrvAC, BlSwpAC, BlSpn)`` with ``RefOrientation``
        the ElastoDyn ``PreCone``. The circular/transition root stations use a
        different ``chordMount`` reference line and are excluded; every lifting
        station (``chord_mount == 0.25``) must match to < 5 mm.
        """
        precone = math.radians(-4.0)
        cone = 4.0
        hub = blade_geometry.HUB_RADIUS
        source = blade_geometry.read_blade_table()
        rows = blade_geometry.read_geometry(GEOMETRY)
        axis, radial, tangential = (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)
        for row, station in zip(rows, source):
            point = _v_add(
                _v_scale(axis, row["axial_distance_m"]),
                _v_scale(radial, row["radius_m"]),
            )
            point = _v_add(
                point,
                _v_scale(tangential, -(row["chord_mount"] - 0.25) * row["chord_m"]),
            )
            point = _v_rot(point, tangential, math.radians(-cone))
            point = _v_rot(point, axis, math.radians(row["azimuth_deg"]))
            aerodyn = _v_add(
                _v_rot((0.0, 0.0, hub), (0.0, 1.0, 0.0), precone),
                _v_rot(
                    (station["crv_ac"], station["swp_ac"], station["span"]),
                    (0.0, 1.0, 0.0),
                    precone,
                ),
            )
            residual = math.dist(point, aerodyn)
            if row["chord_mount"] == pytest.approx(0.25, abs=1e-9):
                assert residual < 5e-3, (row["span_m"], residual)

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

    def test_lift_re_correction_is_disabled(self):
        # profileData::updateRe rescales the lift table as
        # cl_new(alpha) = K*cl_org(alpha/K) unless liftReCorrExp is 0. That
        # shifts the zero-lift angle, a geometric and Re-independent property,
        # so every committed polar must pin the key and keep the source Re and
        # rows; otherwise the rescaling could silently come back on a rerun.
        for name in (f"polar_{station:02d}.dat" for station in range(50)):
            text = (POLARS / name).read_text(encoding="utf-8")
            assert "liftReCorrExp 0;" in text, name
        sources = _sources()
        for station, source in sorted(sources.items()):
            parsed = build_polars.parse_airfoilinfo(source)
            path = POLARS / build_polars.OUTPUT_TEMPLATE.format(station=station)
            text = path.read_text(encoding="utf-8")
            assert f"Re {parsed['re_millions'] * 1e6:g};" in text
            assert len(_read_emitted_rows(path)) == len(parsed["rows"]) == 200

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


# ---------------------------------------------------------------------------
# P2 — case assembly (rendered skeleton, fvOptions, mesh arithmetic)
# ---------------------------------------------------------------------------
generate_case = _load(
    "iea15mw_generate_case", PACKAGE / "tools" / "generate_case.py"
)

CASE_DIR = PACKAGE / "case"
EXPECTED_CELL_COUNT = 4_299_792
RATED_TSR = 8.913185552348528
RATED_RADIUS = 120.67532316
EXPECTED_FILES = (
    "system/blockMeshDict",
    "system/topoSetDict",
    "system/controlDict",
    "system/decomposeParDict",
    "system/fvSchemes",
    "system/fvSolution",
    "system/fvOptions",
    "constant/transportProperties",
    "constant/turbulenceProperties",
    "0.org/U",
    "0.org/p",
    "0.org/k",
    "0.org/omega",
    "0.org/nut",
)


def _strip_foam_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def _parse_foam(text: str) -> dict:
    """Minimal OpenFOAM dictionary reader for the rendered files.

    Handles nested ``{}`` dictionaries, ``(...)`` lists (including nested
    lists), ``key value;`` entries, ``$dict;`` inheritance and ``#include``
    directives. It is deliberately not a full OpenFOAM parser: it only has to
    survive the generated dictionaries so the tests can inspect structure.
    """
    tokens = re.findall(r"[{}();]|\"[^\"]*\"|[^\s{}();]+", _strip_foam_comments(text))
    pos = 0

    def parse_list() -> list:
        nonlocal pos
        items: list = []
        while pos < len(tokens):
            token = tokens[pos]
            if token == ")":
                pos += 1
                return items
            if token == "(":
                pos += 1
                items.append(parse_list())
            elif token == ";":
                pos += 1
            elif token.startswith("#"):
                pos += 1
                if pos < len(tokens) and tokens[pos].startswith('"'):
                    pos += 1
            else:
                items.append(token)
                pos += 1
        return items

    def parse_block() -> dict:
        nonlocal pos
        result: dict = {}
        while pos < len(tokens):
            token = tokens[pos]
            if token == "}":
                pos += 1
                return result
            if token in (";", "{"):
                pos += 1
                continue
            if token.startswith("#"):
                pos += 1
                if pos < len(tokens) and tokens[pos].startswith('"'):
                    pos += 1
                continue
            if token.startswith("$"):
                pos += 1
                if pos < len(tokens) and tokens[pos] == ";":
                    pos += 1
                continue
            key = token
            pos += 1
            if pos >= len(tokens):
                result[key] = None
                break
            nxt = tokens[pos]
            if nxt == "{":
                pos += 1
                result[key] = parse_block()
            elif nxt == "(":
                pos += 1
                result[key] = parse_list()
            else:
                result[key] = nxt
                pos += 1
                if pos < len(tokens) and tokens[pos] == ";":
                    pos += 1
        return result

    return parse_block()


def _coeffs(fvoptions: dict) -> dict:
    return fvoptions["turbine"]["axialFlowTurbineALSourceCoeffs"]


@pytest.fixture(scope="module")
def fvoptions() -> dict:
    return _parse_foam((CASE_DIR / "system" / "fvOptions").read_text(encoding="utf-8"))


class TestRatedOperatingPoint:
    def test_tip_speed_ratio_is_computed(self):
        tsr = generate_case.tip_speed_ratio(10.659, 7.518)
        assert tsr == pytest.approx(RATED_TSR, abs=1e-9)
        # The frozen anchor is the analytic Omega*R/V, not a table lookup.
        assert tsr == pytest.approx(
            generate_case.omega_from_rpm(7.518) * RATED_RADIUS / 10.659, abs=1e-12
        )

    def test_readiness_proposal_9_0786_is_not_reproduced(self):
        # 9.0786 implies 7.6575 rpm, not the rated 7.518 rpm.
        implied_rpm = 9.0786 * 10.659 / RATED_RADIUS * 60.0 / (2.0 * math.pi)
        assert implied_rpm == pytest.approx(7.6575, abs=1e-3)
        assert abs(implied_rpm - 7.518) > 0.1

    def test_omega_and_revolution_period(self):
        omega = generate_case.omega_from_rpm(7.518)
        assert omega == pytest.approx(0.7872831189896021, abs=1e-15)
        assert generate_case.revolution_period(7.518) == pytest.approx(
            7.980845969672786, abs=1e-12
        )


class TestFvOptions:
    def test_parses_and_carries_rotor_keys(self, fvoptions):
        coeffs = _coeffs(fvoptions)
        assert fvoptions["turbine"]["type"] == "axialFlowTurbineALSource"
        assert fvoptions["turbine"]["active"] == "on"
        assert float(coeffs["tipSpeedRatio"]) == pytest.approx(RATED_TSR, abs=1e-6)
        assert float(coeffs["rotorRadius"]) == pytest.approx(RATED_RADIUS, abs=1e-4)
        assert [float(v) for v in coeffs["freeStreamVelocity"]] == [0.0, 10.659, 0.0]
        assert [float(v) for v in coeffs["origin"]] == [0.0, 0.0, 0.0]
        assert [float(v) for v in coeffs["axis"]] == [0.0, -1.0, 0.0]
        assert [float(v) for v in coeffs["verticalDirection"]] == [0.0, 0.0, 1.0]

    def test_three_blades_120_apart(self, fvoptions):
        blades = _coeffs(fvoptions)["blades"]
        assert list(blades) == ["blade1", "blade2", "blade3"]
        assert float(blades["blade2"]["azimuthalOffset"]) == 120.0
        assert float(blades["blade3"]["azimuthalOffset"]) == 240.0
        assert "azimuthalOffset" not in blades["blade1"]

    def test_nelements_is_a_multiple_of_49(self, fvoptions):
        blades = _coeffs(fvoptions)["blades"]
        n_elements = int(blades["blade1"]["nElements"])
        assert n_elements == 147
        assert n_elements % 49 == 0

    def test_neutral_baseline(self, fvoptions):
        coeffs = _coeffs(fvoptions)
        assert coeffs["dynamicStall"]["active"] == "off"
        assert coeffs["rotationalAugmentation"]["active"] == "off"
        assert coeffs["endEffects"]["active"] == "off"
        assert coeffs["endEffects"]["GlauertCoeffs"]["tipEffects"] == "off"
        assert coeffs["endEffects"]["GlauertCoeffs"]["rootEffects"] == "off"
        # No tipCorrection block anywhere in the rendered dictionary.
        text = (CASE_DIR / "system" / "fvOptions").read_text(encoding="utf-8")
        assert "tipCorrection" not in text

    def test_element_data_matches_csv(self, fvoptions):
        rows = _coeffs(fvoptions)["blades"]["blade1"]["elementData"]
        geometry = blade_geometry.read_geometry(GEOMETRY)
        assert len(rows) == len(geometry) == 50
        for element, row in zip(rows, geometry):
            assert len(element) == 7
            assert float(element[0]) == pytest.approx(
                row["axial_distance_m"], abs=1e-6
            )
            assert float(element[1]) == pytest.approx(row["radius_m"], abs=1e-6)
            assert float(element[2]) == pytest.approx(row["azimuth_deg"], abs=1e-6)
            assert float(element[3]) == pytest.approx(row["chord_m"], abs=1e-6)
            assert float(element[4]) == pytest.approx(row["chord_mount"], abs=1e-6)
            assert float(element[5]) == pytest.approx(row["pitch_deg"], abs=1e-6)
            assert float(element[6]) == pytest.approx(row["curve_angle_deg"], abs=1e-6)

    def test_element_twist_sign(self, fvoptions):
        rows = _coeffs(fvoptions)["blades"]["blade1"]["elementData"]
        geometry = blade_geometry.read_geometry(GEOMETRY)
        for element, row in zip(rows, geometry):
            if row["twist_deg"] > 0:
                assert float(element[5]) < 0
            elif row["twist_deg"] < 0:
                assert float(element[5]) > 0

    def test_physical_radius_with_cone_projects_to_rotor_radius(self, fvoptions):
        coeffs = _coeffs(fvoptions)
        rows = coeffs["blades"]["blade1"]["elementData"]
        tip = float(rows[-1][1])
        # Option (b): the physical along-blade radius, coned by 4 deg.
        assert tip == pytest.approx(120.9699, abs=1e-3)
        assert tip > float(coeffs["rotorRadius"])
        assert float(coeffs["coneAngle"]) == pytest.approx(4.0)
        projected = tip * math.cos(math.radians(4.0))
        assert projected == pytest.approx(float(coeffs["rotorRadius"]), abs=1e-3)

    def test_polar_mapping_by_airfoil_id(self, fvoptions):
        coeffs = _coeffs(fvoptions)
        profiles = coeffs["blades"]["blade1"]["elementProfiles"]
        profile_data = coeffs["profileData"]
        geometry = blade_geometry.read_geometry(GEOMETRY)
        assert profiles == generate_case.blade_profile_names()
        assert len(profiles) == 50
        for row in geometry:
            name = f"polar_{int(row['airfoil_id']) - 1:02d}"
            assert name in profiles
            assert name in profile_data
            assert (POLARS / f"{name}.dat").exists()
        assert "cylinder" in profile_data
        # The rendered include path resolves to the committed P1 polars.
        text = (CASE_DIR / "system" / "fvOptions").read_text(encoding="utf-8")
        assert '#include "../../data/polars/polar_00.dat"' in text

    def test_hub_is_optional_and_matches_the_windio_diameter(self, tmp_path):
        # Default off: AeroDyn has no hub aero, so the reference excludes it.
        text = (CASE_DIR / "system" / "fvOptions").read_text(encoding="utf-8")
        assert "\n        hub\n" not in text
        # On: a 7.94 m cylinder matching WindIO components.hub.diameter.
        case_dir = tmp_path / "case"
        assert generate_case.main(["--case-dir", str(case_dir), "--hub", "on"]) == 0
        fv = (case_dir / "system" / "fvOptions").read_text(encoding="utf-8")
        assert "\n        hub\n" in fv
        assert "(0 3.97 7.94)" in fv
        assert "(0 -3.97 7.94)" in fv
        assert "elementProfiles (cylinder)" in fv


class TestCaseSkeleton:
    def test_all_expected_files_rendered(self):
        for relative in EXPECTED_FILES:
            assert (CASE_DIR / relative).exists(), relative

    def test_decompose_par_48_ranks(self):
        text = (CASE_DIR / "system" / "decomposeParDict").read_text(encoding="utf-8")
        assert "numberOfSubdomains 48;" in text
        assert generate_case.NUMBER_OF_SUBDOMAINS == 48

    def test_control_dict_time_step_and_end_time(self):
        text = (CASE_DIR / "system" / "controlDict").read_text(encoding="utf-8")
        assert "deltaT 0.075;" in text
        assert "endTime 23.942538;" in text
        assert "libturbinesFoam.so" in text
        # The tip displacement per step stays below the hub-adjacent cell.
        tip_speed = generate_case.omega_from_rpm(7.518) * RATED_RADIUS
        assert tip_speed * 0.075 < generate_case.hub_cell_size("coarse")

    def test_u_field_prescribes_rated_speed(self):
        text = (CASE_DIR / "0.org" / "U").read_text(encoding="utf-8")
        assert "uniform (0 10.659 0)" in text

    def test_ground_is_a_wall_hub_height_below_the_rotor(self):
        # Rotor/hub at the origin; the floor is one hub height below (z = -150).
        u = (CASE_DIR / "0.org" / "U").read_text(encoding="utf-8")
        assert "type noSlip;" in u
        breaks, cells, _ = generate_case.vertical_mesh()
        assert breaks[0] == pytest.approx(-generate_case.HUB_HEIGHT)
        assert breaks[1] == pytest.approx(0.0)
        assert cells[0] >= 2  # a graded ground layer for the wall function

    def test_domain_top_is_configurable(self):
        top = 3.0 * generate_case.ROTOR_DIAMETER
        breaks, _, _ = generate_case.vertical_mesh(top)
        assert breaks[-1] == pytest.approx(top)
        # The hub-adjacent cell stays ~D/32 for the coarse mesh.
        domain = generate_case.domain_spec("coarse", top=top)
        assert generate_case.hub_cell_size(domain) == pytest.approx(
            generate_case.ROTOR_DIAMETER / 32.0, rel=0.03
        )

    def test_mesh_resolution_and_domain_are_parametric(self):
        coarse = generate_case.domain_spec("coarse")
        fine = generate_case.domain_spec("fine")
        # A finer mesh has a smaller hub cell and more cells.
        assert generate_case.hub_cell_size(fine) < generate_case.hub_cell_size(coarse)
        assert generate_case.cell_count(fine) > generate_case.cell_count(coarse)
        # A smaller domain has fewer cells.
        small = generate_case.domain_spec(
            "coarse", upstream=2.5, downstream=7.5, lateral=2.5
        )
        assert generate_case.cell_count(small) < generate_case.cell_count(coarse)
        # A compact finer domain can cost about the same as the big coarse one.
        compact_medium = generate_case.domain_spec(
            "medium", upstream=2.5, downstream=7.5, lateral=2.5
        )
        assert generate_case.cell_count(compact_medium) < 2.0 * generate_case.cell_count(
            coarse
        )

    def test_flow_axis_y_points_flow_and_rotor_along_y(self, tmp_path):
        """The Aeroelast/FSI orientation: fluid +Y, rotor axis -Y, blade axis +Z."""
        case_dir = tmp_path / "y"
        assert (
            generate_case.main(["--case-dir", str(case_dir), "--flow-axis", "y"])
            == 0
        )
        fv = (case_dir / "system" / "fvOptions").read_text(encoding="utf-8")
        assert "axis (0 -1 0);" in fv
        assert "verticalDirection (0 0 1);" in fv
        assert "freeStreamVelocity (0 10.659 0);" in fv
        u = (case_dir / "0.org" / "U").read_text(encoding="utf-8")
        assert "uniform (0 10.659 0)" in u
        # The domain is the R_z(+90) image: flow (Y) 20D, lateral (X) 8D.
        text = (case_dir / "system" / "blockMeshDict").read_text(encoding="utf-8")
        block = text.split("vertices")[1].split("blocks")[0]
        pts = [
            tuple(float(value) for value in group.split())
            for group in re.findall(r"\(([-0-9.eE+ ]+)\)", block)
        ]
        d = generate_case.ROTOR_DIAMETER
        assert max(p[1] for p in pts) - min(p[1] for p in pts) == pytest.approx(20 * d)
        assert max(p[0] for p in pts) - min(p[0] for p in pts) == pytest.approx(8 * d)

    def test_default_flow_axis_is_aeroelast_y(self):
        fv = (CASE_DIR / "system" / "fvOptions").read_text(encoding="utf-8")
        assert "axis (0 -1 0);" in fv
        assert "freeStreamVelocity (0 10.659 0);" in fv

    def test_tower_alm_is_included_from_the_windio_tower(self, fvoptions):
        tower = _coeffs(fvoptions)["tower"]
        assert int(tower["nElements"]) == generate_case.TOWER_N_ELEMENTS
        assert "tower" in tower["elementProfiles"]
        rows = tower["elementData"]
        assert len(rows) == 11
        heights = [float(row[1]) for row in rows]
        assert max(heights) < 0  # the tower is below the hub
        assert min(heights) > -generate_case.HUB_HEIGHT  # above the floor
        diameters = [float(row[2]) for row in rows]
        assert diameters[0] == pytest.approx(10.0)
        assert diameters[-1] == pytest.approx(6.5)
        text = (CASE_DIR / "system" / "fvOptions").read_text(encoding="utf-8")
        assert "tower { data ((-180 0 0.5 0) (180 0 0.5 0)); }" in text

    def test_tower_can_be_disabled(self, tmp_path):
        case_dir = tmp_path / "case"
        assert (
            generate_case.main(["--case-dir", str(case_dir), "--tower", "off"]) == 0
        )
        text = (case_dir / "system" / "fvOptions").read_text(encoding="utf-8")
        assert "elementProfiles (tower)" not in text

    def test_tower_is_offset_downwind_by_the_windio_overhang(self, fvoptions):
        # Rotor at the origin: the tower (yaw axis) is one WindIO overhang
        # downwind, so axialDistance = -overhang (the rotor axis points upwind).
        overhang = blade_geometry.read_tower_overhang()
        assert overhang == pytest.approx(12.0313, abs=1e-3)
        rows = _coeffs(fvoptions)["tower"]["elementData"]
        for row in rows:
            assert float(row[0]) == pytest.approx(-overhang, abs=1e-9)

    def test_rotation_defaults_to_ccw(self, tmp_path):
        # The physical rotation sense is not yet pinned to the CCBlade label (a
        # naive flip inverts the rotor thrust), so the default stays the
        # turbinesFoam ccw convention; --rotation cw is available but unused.
        fv = (CASE_DIR / "system" / "fvOptions").read_text(encoding="utf-8")
        assert "rotationDirection 1;" in fv
        case_dir = tmp_path / "cw"
        assert (
            generate_case.main(["--case-dir", str(case_dir), "--rotation", "cw"])
            == 0
        )
        assert "rotationDirection -1;" in (
            case_dir / "system" / "fvOptions"
        ).read_text(encoding="utf-8")

    def test_model_twins_select_the_actuator_model(self, tmp_path):
        alm = (CASE_DIR / "system" / "fvOptions.ALM").read_text(encoding="utf-8")
        asm = (CASE_DIR / "system" / "fvOptions.ASM").read_text(encoding="utf-8")
        mesh = (CASE_DIR / "system" / "fvOptions.ASM-MESH").read_text(encoding="utf-8")
        assert "elementType actuatorLineElement;" in alm
        assert "nChordwise" not in alm
        assert "elementType actuatorSurfaceElement;" in asm
        assert "nChordwise 5;" in asm
        assert "surfaceGeometry" not in asm
        assert 'surfaceGeometry "constant/triSurface/iea15mw_blade.stl";' in mesh
        # --model picks which twin is installed as system/fvOptions
        case_dir = tmp_path / "asm-mesh"
        assert (
            generate_case.main(["--case-dir", str(case_dir), "--model", "asm-mesh"])
            == 0
        )
        selected = (case_dir / "system" / "fvOptions").read_text(encoding="utf-8")
        assert "elementType actuatorSurfaceElement;" in selected
        assert "surfaceGeometry" in selected

    def test_purge_write_keeps_exactly_one_revolution(self, tmp_path):
        # A 15-rev campaign with purgeWrite 0 wrote ~300 GB of fields per run and
        # blew the group /scratch quota; the fields now keep the last revolution.
        case_dir = tmp_path / "pw"
        for degrees, snaps in ((6, 60), (60, 6), (120, 3), (360, 1)):
            assert (
                generate_case.main(
                    ["--case-dir", str(case_dir), "--write-interval-deg", str(degrees)]
                )
                == 0
            )
            control = (case_dir / "system" / "controlDict").read_text(encoding="utf-8")
            assert f"purgeWrite {snaps};" in control

    def test_snappy_flag_decouples_the_refined_mesh_from_the_model(self, tmp_path):
        # The model comparison (ALM vs ASM vs ASM-mesh) needs all three on the
        # SAME castellated mesh, so the refinement must be selectable on its own.
        base = generate_case.delta_t(generate_case.domain_spec("coarse"))
        refined = generate_case.delta_t(generate_case.domain_spec("coarse"), snappy_level=3)
        for model in ("alm", "asm"):
            # default: not refined, so the background time step
            case_dir = tmp_path / f"{model}-bg"
            assert generate_case.main(["--case-dir", str(case_dir), "--model", model]) == 0
            assert f"deltaT {base:.8g};" in (
                case_dir / "system" / "controlDict"
            ).read_text(encoding="utf-8")
            # forced on: same model, refined time step
            case_dir = tmp_path / f"{model}-ref"
            assert (
                generate_case.main(
                    ["--case-dir", str(case_dir), "--model", model, "--snappy", "on"]
                )
                == 0
            )
            assert f"deltaT {refined:.8g};" in (
                case_dir / "system" / "controlDict"
            ).read_text(encoding="utf-8")
        # forced off on asm-mesh gives the background step back
        case_dir = tmp_path / "asmmesh-bg"
        assert (
            generate_case.main(
                ["--case-dir", str(case_dir), "--model", "asm-mesh", "--snappy", "off"]
            )
            == 0
        )
        assert f"deltaT {base:.8g};" in (
            case_dir / "system" / "controlDict"
        ).read_text(encoding="utf-8")

    def test_snappy_refines_the_tower_and_its_shadow(self, tmp_path):
        # The rotor-disk cylinder alone left the tower unrefined and, worse, its
        # wake -- the shadow the blades cross at the bottom of the rotation -- at
        # the background cell size, so the tower shadow was not measurable.
        case_dir = tmp_path / "tower"
        assert (
            generate_case.main(
                ["--case-dir", str(case_dir), "--model", "asm-mesh", "--snappy", "on"]
            )
            == 0
        )
        text = (case_dir / "system" / "snappyHexMeshDict").read_text(encoding="utf-8")
        assert "towerWake" in text
        assert "type searchableBox;" in text
        marker = "type searchableBox;"
        body = text[text.index(marker) :]
        low = [float(v) for v in body.split("min (")[1].split(")")[0].split()]
        high = [float(v) for v in body.split("max (")[1].split(")")[0].split()]
        overhang = generate_case.blade_geometry.read_tower_overhang()
        # Upwind of the rotor: same sign as the ALM tower rows' axialDistance
        assert low[1] < -overhang < high[1]
        # The shadow reaches well downstream of the rotor plane
        assert high[1] > generate_case.ROTOR_DIAMETER
        # Vertical span covers the tower (hub-frame z) with margin
        tower_z = [
            station["z"] - generate_case.HUB_HEIGHT
            for station in generate_case.blade_geometry.read_tower_table()
        ]
        assert low[2] < min(tower_z) and high[2] > max(tower_z)
        assert high[0] > 0.0 > low[0]
        # The wake region is coarser than the rotor disk
        assert "levels ((1e15 3))" in text
        assert "levels ((1e15 2))" in text

    def test_snappy_refines_the_rotor_wake_downstream(self, tmp_path):
        # Downstream of the rotor disk nothing above the tower band was refined,
        # so the rotor wake -- which reaches z = +R -- ran at the background cell
        # size. The rotorWake cylinder covers it one level below the disk, along
        # DOWNSTREAM = inflow_direction (never a hardcoded +1), and it nests the
        # disk both radially and axially, so the level-2/level-3 jump is not a
        # cliff on the tip vortex.
        origin = generate_case.turbine_origin()
        for flow_axis in ("y", "x"):
            case_dir = tmp_path / flow_axis
            assert (
                generate_case.main(
                    [
                        "--case-dir",
                        str(case_dir),
                        "--flow-axis",
                        flow_axis,
                        "--model",
                        "asm-mesh",
                        "--snappy",
                        "on",
                    ]
                )
                == 0
            )
            parsed = _parse_foam(
                (case_dir / "system" / "snappyHexMeshDict").read_text(
                    encoding="utf-8"
                )
            )
            downstream = generate_case.inflow_direction(flow_axis)

            disk = parsed["geometry"]["rotorDisk"]
            assert disk["type"] == "searchableCylinder"
            assert float(disk["radius"]) == pytest.approx(
                generate_case.SNAPPY_DISK_RADIUS, abs=1e-6
            )
            disk_up = [
                origin[i]
                - generate_case.SNAPPY_DISK_HALF_THICKNESS * downstream[i]
                for i in range(3)
            ]
            disk_down = [
                origin[i]
                + generate_case.SNAPPY_DISK_HALF_THICKNESS * downstream[i]
                for i in range(3)
            ]
            disk_faces = (
                [float(v) for v in disk["point1"]],
                [float(v) for v in disk["point2"]],
            )
            assert any(face == pytest.approx(disk_up, abs=1e-6) for face in disk_faces)
            assert any(
                face == pytest.approx(disk_down, abs=1e-6) for face in disk_faces
            )
            assert 0.5 * math.dist(disk_faces[0], disk_faces[1]) == pytest.approx(
                generate_case.SNAPPY_DISK_HALF_THICKNESS, abs=1e-6
            )

            wake = parsed["geometry"]["rotorWake"]
            assert wake["type"] == "searchableCylinder"
            assert float(wake["radius"]) == pytest.approx(
                generate_case.SNAPPY_WAKE_RADIUS, abs=1e-6
            )
            wake_up = [
                origin[i]
                - generate_case.SNAPPY_WAKE_UPSTREAM * downstream[i]
                for i in range(3)
            ]
            wake_down = [
                origin[i]
                + generate_case.SNAPPY_WAKE_DOWNSTREAM * downstream[i]
                for i in range(3)
            ]
            assert [float(v) for v in wake["point1"]] == pytest.approx(
                wake_up, abs=1e-6
            )
            assert [float(v) for v in wake["point2"]] == pytest.approx(
                wake_down, abs=1e-6
            )

            # The nesting invariant: the coarser wake strictly encloses the finer
            # disk radially (wake radius > disk radius) and axially, with its
            # upstream face upwind of the disk's and its downstream end past it.
            assert float(wake["radius"]) > float(disk["radius"])
            assert generate_case.SNAPPY_WAKE_UPSTREAM > (
                generate_case.SNAPPY_DISK_HALF_THICKNESS
            )
            assert generate_case.SNAPPY_WAKE_DOWNSTREAM > (
                generate_case.SNAPPY_DISK_HALF_THICKNESS
            )
            assert sum(
                (wake_up[i] - disk_up[i]) * downstream[i] for i in range(3)
            ) < 0.0
            assert sum(
                (wake_down[i] - disk_down[i]) * downstream[i] for i in range(3)
            ) > 0.0
            # The downstream point moves with the fluid: +y for the default y
            # axis, +x for the OpenFAST x axis (the sign cannot silently flip).
            streamwise = 1 if flow_axis == "y" else 0
            assert wake_down[streamwise] > 0.0
            regions = parsed["castellatedMeshControls"]["refinementRegions"]
            assert int(regions["rotorDisk"]["levels"][0][1]) == (
                generate_case.DEFAULT_SNAPPY_LEVEL
            )
            assert int(regions["rotorWake"]["levels"][0][1]) == (
                generate_case.DEFAULT_SNAPPY_LEVEL - 1
            )
            # The wake adds no refinement surface either (see the disk test).
            assert parsed["castellatedMeshControls"]["refinementSurfaces"] == {}

    def test_snappy_absolute_extents_are_pinned(self):
        # The maintainer's hand-tuned absolute extents. The wake is sized so the
        # ~19 m flow-direction blade-tip deflection expected in the coming FSI
        # work stays inside a refined zone; shrinking any of these would let the
        # deflected tip cross into the coarse background, so pin the absolute
        # numbers here rather than only asserting the nesting ratios.
        assert generate_case.SNAPPY_DISK_RADIUS == pytest.approx(150.0)
        assert generate_case.SNAPPY_DISK_HALF_THICKNESS == pytest.approx(10.0)
        assert generate_case.SNAPPY_WAKE_RADIUS == pytest.approx(170.0)
        assert generate_case.SNAPPY_WAKE_UPSTREAM == pytest.approx(20.0)
        assert generate_case.SNAPPY_WAKE_DOWNSTREAM == pytest.approx(470.0)
        assert generate_case.SNAPPY_TOWER_UPSTREAM == pytest.approx(20.0)
        assert generate_case.SNAPPY_TOWER_DOWNSTREAM == pytest.approx(470.0)
        assert generate_case.SNAPPY_TOWER_Z_MIN == pytest.approx(-170.0)
        assert generate_case.SNAPPY_TOWER_Z_MAX == pytest.approx(10.0)
        # ... and the committed default case renders exactly them (default
        # flow axis y).
        parsed = _parse_foam(
            (CASE_DIR / "system" / "snappyHexMeshDict").read_text(encoding="utf-8")
        )
        geometry = parsed["geometry"]
        assert float(geometry["rotorDisk"]["radius"]) == pytest.approx(150.0)
        assert [float(v) for v in geometry["rotorDisk"]["point1"]] == pytest.approx(
            [0.0, 10.0, 0.0]
        )
        assert [float(v) for v in geometry["rotorDisk"]["point2"]] == pytest.approx(
            [0.0, -10.0, 0.0]
        )
        assert float(geometry["rotorWake"]["radius"]) == pytest.approx(170.0)
        assert [float(v) for v in geometry["rotorWake"]["point1"]] == pytest.approx(
            [0.0, -20.0, 0.0]
        )
        assert [float(v) for v in geometry["rotorWake"]["point2"]] == pytest.approx(
            [0.0, 470.0, 0.0]
        )
        assert [float(v) for v in geometry["towerWake"]["min"]] == pytest.approx(
            [-20.0, -20.0, -170.0]
        )
        assert [float(v) for v in geometry["towerWake"]["max"]] == pytest.approx(
            [20.0, 470.0, 10.0]
        )
        assert [
            float(v) for v in parsed["castellatedMeshControls"]["locationInMesh"]
        ] == pytest.approx([0.0, 0.0, 0.0])

    def test_snappy_rotor_wake_level_follows_the_disk(self):
        # The wake is one castellation level coarser than the rotor disk
        # (2 when the disk is 3) and clamps to 0 for a disk at level <= 1.
        for level, expected in ((5, 4), (3, 2), (2, 1), (1, 0), (0, 0)):
            regions = _parse_foam(generate_case.render_snappy_dict(level=level))[
                "castellatedMeshControls"
            ]["refinementRegions"]
            assert int(regions["rotorDisk"]["levels"][0][1]) == level
            assert int(regions["rotorWake"]["levels"][0][1]) == expected

    def test_snappy_dict_refines_the_rotor_disk_without_a_surface(self, tmp_path):
        text = (CASE_DIR / "system" / "snappyHexMeshDict").read_text(encoding="utf-8")
        assert "castellatedMesh true;" in text
        assert "snap false;" in text and "addLayers false;" in text
        assert "searchableCylinder" in text
        assert "levels ((1e15 3))" in text
        # The STL must never be a refinementSurface: it is the actuator force
        # surface, not a body. The castellated flood fill would treat the blade
        # interior as enclosed, delete it and leave a solid wall.
        assert "refinementSurfaces\n    {\n    }" in text
        assert "triSurface" not in text
        # Level is plumbed through.
        case_dir = tmp_path / "snappy5"
        assert (
            generate_case.main(
                ["--case-dir", str(case_dir), "--model", "asm-mesh", "--snappy-level", "5"]
            )
            == 0
        )
        assert "levels ((1e15 5))" in (
            case_dir / "system" / "snappyHexMeshDict"
        ).read_text(encoding="utf-8")

    def test_snappy_level_tightens_the_time_step(self, tmp_path):
        # The castellated rotor-disk cell constrains deltaT, not the background
        # hub cell: leaving it at the background value drove Courant max 4.19.
        coarse = generate_case.domain_spec("coarse")
        base = generate_case.delta_t(coarse)
        refined = generate_case.delta_t(coarse, snappy_level=3)
        assert 0.0 < refined < base
        assert abs(refined * 8.0 - base) < 1e-3
        case_dir = tmp_path / "asm"
        assert generate_case.main(["--case-dir", str(case_dir), "--model", "asm-mesh"]) == 0
        control = (case_dir / "system" / "controlDict").read_text(encoding="utf-8")
        assert f"deltaT {refined:.8g};" in control

    def test_flow_axis_x_is_the_openfast_orientation(self, tmp_path):
        case_dir = tmp_path / "x"
        assert (
            generate_case.main(["--case-dir", str(case_dir), "--flow-axis", "x"])
            == 0
        )
        fv = (case_dir / "system" / "fvOptions").read_text(encoding="utf-8")
        assert "axis (-1 0 0);" in fv
        assert "freeStreamVelocity (10.659 0 0);" in fv
        u = (case_dir / "0.org" / "U").read_text(encoding="utf-8")
        assert "uniform (10.659 0 0)" in u

    def test_inflow_k_and_omega_consistent(self):
        fields = generate_case.inflow_fields(10.659)
        assert fields["k"] == pytest.approx(0.0042605355375, abs=1e-12)
        assert fields["omega"] == pytest.approx(0.007053829573451254, abs=1e-15)


class TestMesh:
    def test_recorded_cell_count(self):
        assert generate_case.cell_count("coarse") == EXPECTED_CELL_COUNT
        assert generate_case.EXPECTED_CELL_COUNT == EXPECTED_CELL_COUNT

    def test_block_mesh_dict_18_hex_blocks(self):
        text = (CASE_DIR / "system" / "blockMeshDict").read_text(encoding="utf-8")
        pattern = re.compile(
            r"^\s+hex \(([^)]*)\) \((\d+) (\d+) (\d+)\) simpleGrading \(",
            re.MULTILINE,
        )
        blocks = pattern.findall(text)
        assert len(blocks) == 18
        total = sum(int(nx) * int(ny) * int(nz) for _, nx, ny, nz in blocks)
        assert total == EXPECTED_CELL_COUNT
        for name in ("inlet", "outlet", "bottom", "top", "sideMinus", "sidePlus"):
            assert f"    {name}\n" in text
        assert text.count("type symmetryPlane;") == 3
        assert text.count("type wall;") == 1

    def test_hub_adjacent_cell_is_d_over_32(self):
        hub = generate_case.hub_cell_size("coarse")
        assert hub == pytest.approx(generate_case.ROTOR_DIAMETER / 32.0, rel=0.01)


class TestCheckMode:
    def test_check_passes_for_committed_case(self):
        assert generate_case.main(["--check", "--case-dir", str(CASE_DIR)]) == 0

    def test_start_from_latest_time(self, tmp_path):
        case_dir = tmp_path / "case"
        assert (
            generate_case.main(
                ["--case-dir", str(case_dir), "--start-from", "latestTime"]
            )
            == 0
        )
        text = (case_dir / "system" / "controlDict").read_text(encoding="utf-8")
        assert "startFrom latestTime;" in text
        # The default stays startTime (the committed case must be unchanged).
        assert (
            generate_case.main(["--case-dir", str(case_dir), "--check"])
            == 1
        )

    def test_check_fails_when_stale(self, tmp_path):
        case_dir = tmp_path / "case"
        assert generate_case.main(["--case-dir", str(case_dir)]) == 0
        assert generate_case.main(["--check", "--case-dir", str(case_dir)]) == 0
        stale = case_dir / "system" / "fvOptions"
        stale.write_text(
            stale.read_text(encoding="utf-8") + "// tampered\n", encoding="utf-8"
        )
        assert generate_case.main(["--check", "--case-dir", str(case_dir)]) == 1

    def test_check_fails_when_missing(self, tmp_path):
        assert (
            generate_case.main(["--check", "--case-dir", str(tmp_path / "nope")]) == 1
        )

    def test_operating_point_is_a_parameter(self, tmp_path):
        case_dir = tmp_path / "case"
        assert (
            generate_case.main(
                ["--speed", "9.0", "--rpm", "6.0", "--case-dir", str(case_dir)]
            )
            == 0
        )
        text = (case_dir / "system" / "fvOptions").read_text(encoding="utf-8")
        expected = generate_case.tip_speed_ratio(9.0, 6.0)
        assert f"tipSpeedRatio {expected:.8g};" in text
        assert "freeStreamVelocity (0 9 0);" in text


class TestMeshFactor:
    """The ``GaussianCoeffs/meshFactor`` knob (ALM/ASM projection width).

    The factor scales epsilon = 2*cbrt(V_cell)*meshFactor; the published
    optimum is epsilon = 0.25*c, so the default 1.0 (1.89 m at mid-span) has to
    be selectable without touching the runner that the live jobs execute.
    """

    def test_default_constant_and_committed_case_unchanged(self, monkeypatch):
        monkeypatch.delenv(generate_case.MESH_FACTOR_ENV, raising=False)
        assert generate_case.DEFAULT_MESH_FACTOR == pytest.approx(1.0)
        assert generate_case.MESH_FACTOR_ENV == "TURBINE_MESH_FACTOR"
        assert generate_case.resolve_mesh_factor() == pytest.approx(1.0)
        # The committed case still carries meshFactor 1 (regeneration is a
        # separate, deliberate change); --check pins that in TestCheckMode.
        text = (CASE_DIR / "system" / "fvOptions").read_text(encoding="utf-8")
        assert "meshFactor 1;" in text

    def test_cli_flag_reaches_every_twin(self, tmp_path, monkeypatch):
        monkeypatch.delenv(generate_case.MESH_FACTOR_ENV, raising=False)
        case_dir = tmp_path / "case"
        assert (
            generate_case.main(["--case-dir", str(case_dir), "--mesh-factor", "0.5"])
            == 0
        )
        for name in (
            "fvOptions",
            "fvOptions.ALM",
            "fvOptions.ASM",
            "fvOptions.ASM-MESH",
        ):
            text = (case_dir / "system" / name).read_text(encoding="utf-8")
            assert "meshFactor 0.5;" in text, name
            assert "meshFactor 1;" not in text, name

    def test_env_bridge_changes_the_default_render(self, tmp_path, monkeypatch):
        monkeypatch.setenv(generate_case.MESH_FACTOR_ENV, "0.5")
        case_dir = tmp_path / "case"
        assert generate_case.main(["--case-dir", str(case_dir)]) == 0
        text = (case_dir / "system" / "fvOptions").read_text(encoding="utf-8")
        assert "meshFactor 0.5;" in text

    def test_cli_flag_beats_the_env_bridge(self, tmp_path, monkeypatch):
        monkeypatch.setenv(generate_case.MESH_FACTOR_ENV, "0.25")
        case_dir = tmp_path / "case"
        assert (
            generate_case.main(["--case-dir", str(case_dir), "--mesh-factor", "0.5"])
            == 0
        )
        text = (case_dir / "system" / "fvOptions").read_text(encoding="utf-8")
        assert "meshFactor 0.5;" in text
        assert "meshFactor 0.25;" not in text

    def test_resolve_precedence(self, monkeypatch):
        monkeypatch.delenv(generate_case.MESH_FACTOR_ENV, raising=False)
        assert generate_case.resolve_mesh_factor() == pytest.approx(
            generate_case.DEFAULT_MESH_FACTOR
        )
        assert generate_case.resolve_mesh_factor(0.5) == pytest.approx(0.5)
        monkeypatch.setenv(generate_case.MESH_FACTOR_ENV, "0.25")
        assert generate_case.resolve_mesh_factor() == pytest.approx(0.25)
        # An explicit flag wins over the environment.
        assert generate_case.resolve_mesh_factor(0.5) == pytest.approx(0.5)


class TestVelocitySampling:
    """The ALM inflow-sampling knob (``velocitySampleRadius``/``nVelocitySamples``).

    ``axialFlowTurbineALSource`` already reads both keys and forwards them to
    every blade, but the committed case rendered neither, so every run to date
    used the point-sampling branch (``radius <= 0``). The radius is in units of
    the projection epsilon; Zormpa et al. 2024 (Wind Energy) require the sample
    outside the force Gaussian (``rs/rg = 1.1`` with ``rg = 3*epsilon``), i.e.
    ``rs = 3.3*epsilon``. Each key is rendered only when it differs from its
    default, so the committed default render stays byte-identical.
    """

    def _clear_env(self, monkeypatch):
        monkeypatch.delenv(generate_case.VELOCITY_SAMPLE_RADIUS_ENV, raising=False)
        monkeypatch.delenv(generate_case.N_VELOCITY_SAMPLES_ENV, raising=False)

    def test_default_constant_and_committed_case_unchanged(self, monkeypatch):
        self._clear_env(monkeypatch)
        assert generate_case.DEFAULT_VELOCITY_SAMPLE_RADIUS == pytest.approx(0.0)
        assert generate_case.DEFAULT_N_VELOCITY_SAMPLES == 20
        assert generate_case.VELOCITY_SAMPLE_RADIUS_ENV == "TURBINE_VELOCITY_SAMPLE_RADIUS"
        assert generate_case.N_VELOCITY_SAMPLES_ENV == "TURBINE_N_VELOCITY_SAMPLES"
        assert generate_case.resolve_velocity_sample_radius() == pytest.approx(0.0)
        assert generate_case.resolve_n_velocity_samples() == 20
        # Default = point sampling: neither key is rendered, so the committed
        # case is unchanged (the C++ default branch).
        default = generate_case.render_fv_options()
        assert "velocitySampleRadius" not in default
        assert "nVelocitySamples" not in default
        committed = (CASE_DIR / "system" / "fvOptions").read_text(encoding="utf-8")
        assert "velocitySampleRadius" not in committed
        assert "nVelocitySamples" not in committed

    def test_each_flag_changes_only_its_own_rendered_value(self, monkeypatch):
        self._clear_env(monkeypatch)
        default = generate_case.render_fv_options()

        def added(text):
            return [line for line in text.splitlines() if line not in default.splitlines()]

        radius = generate_case.render_fv_options(velocity_sample_radius=3.3)
        assert added(radius) == ["        velocitySampleRadius 3.3;"]
        samples = generate_case.render_fv_options(n_velocity_samples=16)
        assert added(samples) == ["        nVelocitySamples 16;"]
        both = generate_case.render_fv_options(
            velocity_sample_radius=3.3, n_velocity_samples=16
        )
        assert added(both) == [
            "        velocitySampleRadius 3.3;",
            "        nVelocitySamples 16;",
        ]

    def test_cli_flags_render_both_keys_and_reach_every_twin(
        self, tmp_path, monkeypatch
    ):
        self._clear_env(monkeypatch)
        case_dir = tmp_path / "case"
        assert (
            generate_case.main(
                [
                    "--case-dir",
                    str(case_dir),
                    "--velocity-sample-radius",
                    "3.3",
                    "--n-velocity-samples",
                    "16",
                ]
            )
            == 0
        )
        for name in (
            "fvOptions",
            "fvOptions.ALM",
            "fvOptions.ASM",
            "fvOptions.ASM-MESH",
        ):
            text = (case_dir / "system" / name).read_text(encoding="utf-8")
            assert "velocitySampleRadius 3.3;" in text, name
            assert "nVelocitySamples 16;" in text, name

    def test_env_bridge_changes_the_default_render(self, tmp_path, monkeypatch):
        monkeypatch.setenv(generate_case.VELOCITY_SAMPLE_RADIUS_ENV, "3.3")
        monkeypatch.setenv(generate_case.N_VELOCITY_SAMPLES_ENV, "16")
        case_dir = tmp_path / "case"
        assert generate_case.main(["--case-dir", str(case_dir)]) == 0
        text = (case_dir / "system" / "fvOptions").read_text(encoding="utf-8")
        assert "velocitySampleRadius 3.3;" in text
        assert "nVelocitySamples 16;" in text

    def test_cli_flag_beats_the_env_bridge(self, tmp_path, monkeypatch):
        monkeypatch.setenv(generate_case.VELOCITY_SAMPLE_RADIUS_ENV, "0.5")
        monkeypatch.setenv(generate_case.N_VELOCITY_SAMPLES_ENV, "4")
        case_dir = tmp_path / "case"
        assert (
            generate_case.main(
                [
                    "--case-dir",
                    str(case_dir),
                    "--velocity-sample-radius",
                    "3.3",
                    "--n-velocity-samples",
                    "16",
                ]
            )
            == 0
        )
        text = (case_dir / "system" / "fvOptions").read_text(encoding="utf-8")
        assert "velocitySampleRadius 3.3;" in text
        assert "nVelocitySamples 16;" in text
        assert "velocitySampleRadius 0.5;" not in text
        assert "nVelocitySamples 4;" not in text

    def test_resolve_precedence(self, monkeypatch):
        self._clear_env(monkeypatch)
        assert generate_case.resolve_velocity_sample_radius() == pytest.approx(
            generate_case.DEFAULT_VELOCITY_SAMPLE_RADIUS
        )
        assert generate_case.resolve_n_velocity_samples() == 20
        assert generate_case.resolve_velocity_sample_radius(3.3) == pytest.approx(3.3)
        assert generate_case.resolve_n_velocity_samples(16) == 16
        monkeypatch.setenv(generate_case.VELOCITY_SAMPLE_RADIUS_ENV, "2.2")
        monkeypatch.setenv(generate_case.N_VELOCITY_SAMPLES_ENV, "8")
        assert generate_case.resolve_velocity_sample_radius() == pytest.approx(2.2)
        assert generate_case.resolve_n_velocity_samples() == 8
        # An explicit flag wins over the environment.
        assert generate_case.resolve_velocity_sample_radius(3.3) == pytest.approx(3.3)
        assert generate_case.resolve_n_velocity_samples(16) == 16


SNAPPY_EXTENT_ENV_VARS = (
    generate_case.SNAPPY_DISK_RADIUS_ENV,
    generate_case.SNAPPY_DISK_HALF_THICKNESS_ENV,
    generate_case.SNAPPY_WAKE_RADIUS_ENV,
    generate_case.SNAPPY_WAKE_UPSTREAM_ENV,
    generate_case.SNAPPY_WAKE_DOWNSTREAM_ENV,
    generate_case.SNAPPY_TOWER_UPSTREAM_ENV,
    generate_case.SNAPPY_TOWER_DOWNSTREAM_ENV,
    generate_case.SNAPPY_TOWER_Z_MIN_ENV,
    generate_case.SNAPPY_TOWER_Z_MAX_ENV,
    generate_case.SNAPPY_TOWER_LATERAL_FACTOR_ENV,
    generate_case.SNAPPY_WAKE_LEVEL_OFFSET_ENV,
)


#: Flag -> ``render_snappy_dict`` kwarg for each castellated knob.
SNAPPY_FLAG_PARAMS = {
    "--snappy-disk-radius": "disk_radius",
    "--snappy-disk-half-thickness": "disk_half_thickness",
    "--snappy-wake-radius": "wake_radius",
    "--snappy-wake-upstream": "wake_upstream",
    "--snappy-wake-downstream": "wake_downstream",
    "--snappy-tower-upstream": "tower_upstream",
    "--snappy-tower-downstream": "tower_downstream",
    "--snappy-tower-z-min": "tower_z_min",
    "--snappy-tower-z-max": "tower_z_max",
    "--snappy-tower-lateral-factor": "tower_lateral_factor",
    "--snappy-wake-level-offset": "wake_level_offset",
}

#: ``(flag, CLI text, lines added, lines removed)`` for every castellated
#: extent and level. The added/removed lines are the exact symmetric difference
#: of that flag's render against the default, so a flag that leaked into
#: another zone would fail.
SNAPPY_EXTENT_CASES = (
    (
        "--snappy-disk-radius",
        "160",
        ["        radius 160;"],
        ["        radius 150;"],
    ),
    (
        "--snappy-disk-half-thickness",
        "12",
        ["        point1 (0 12 0);", "        point2 (0 -12 0);"],
        ["        point1 (0 10 0);", "        point2 (0 -10 0);"],
    ),
    (
        "--snappy-wake-radius",
        "180",
        ["        radius 180;"],
        ["        radius 170;"],
    ),
    (
        "--snappy-wake-upstream",
        "25",
        ["        point1 (0 -25 0);"],
        ["        point1 (0 -20 0);"],
    ),
    (
        "--snappy-wake-downstream",
        "480",
        ["        point2 (0 480 0);"],
        ["        point2 (0 470 0);"],
    ),
    (
        "--snappy-tower-upstream",
        "25",
        ["        min (-20 -25 -170);"],
        ["        min (-20 -20 -170);"],
    ),
    (
        "--snappy-tower-downstream",
        "480",
        ["        max (20 480 10);"],
        ["        max (20 470 10);"],
    ),
    (
        "--snappy-tower-z-min",
        "-180",
        ["        min (-20 -20 -180);"],
        ["        min (-20 -20 -170);"],
    ),
    (
        "--snappy-tower-z-max",
        "20",
        ["        max (20 470 20);"],
        ["        max (20 470 10);"],
    ),
    (
        "--snappy-tower-lateral-factor",
        "2.5",
        ["        min (-25 -20 -170);", "        max (25 470 10);"],
        ["        min (-20 -20 -170);", "        max (20 470 10);"],
    ),
    (
        "--snappy-wake-level-offset",
        "2",
        ["            levels ((1e15 1));"],
        ["            levels ((1e15 2));"],
    ),
)


class TestSnappyExtents:
    """Run-time overrides for every castellated zone extent and level.

    The maintainer's hand-tuned absolute extents are the defaults; each one is
    overridable with a flag, a documented temporary ``TURBINE_SNAPPY_*``
    environment bridge, and precedence flag > environment > default. The
    nesting invariant (the coarser wake must enclose the finer disk radially and
    axially, and the tower box must stay a box) is validated before rendering.
    """

    def _clear_env(self, monkeypatch):
        for name in SNAPPY_EXTENT_ENV_VARS:
            monkeypatch.delenv(name, raising=False)

    def test_default_render_is_byte_identical_to_the_committed_case(
        self, monkeypatch
    ):
        self._clear_env(monkeypatch)
        committed = (CASE_DIR / "system" / "snappyHexMeshDict").read_text(
            encoding="utf-8"
        )
        assert generate_case.render_snappy_dict() == committed

    @pytest.mark.parametrize("flag,value,added,removed", SNAPPY_EXTENT_CASES)
    def test_each_flag_changes_only_its_own_rendered_value(
        self, monkeypatch, flag, value, added, removed
    ):
        self._clear_env(monkeypatch)
        param = SNAPPY_FLAG_PARAMS[flag]
        number = int(value) if param == "wake_level_offset" else float(value)
        default = generate_case.render_snappy_dict()
        overridden = generate_case.render_snappy_dict(**{param: number})
        changed = set(overridden.splitlines()) ^ set(default.splitlines())
        assert changed == set(added) | set(removed)

    def test_every_flag_reaches_the_renderer(self, tmp_path, monkeypatch):
        self._clear_env(monkeypatch)
        case_dir = tmp_path / "case"
        args = ["--case-dir", str(case_dir)]
        overrides = {}
        for flag, value, _added, _removed in SNAPPY_EXTENT_CASES:
            param = SNAPPY_FLAG_PARAMS[flag]
            overrides[param] = (
                int(value) if param == "wake_level_offset" else float(value)
            )
            args += [flag, value]
        assert generate_case.main(args) == 0
        text = (case_dir / "system" / "snappyHexMeshDict").read_text(encoding="utf-8")
        assert text == generate_case.render_snappy_dict(**overrides)

    def test_environment_bridge_reaches_the_render(self, tmp_path, monkeypatch):
        self._clear_env(monkeypatch)
        monkeypatch.setenv(generate_case.SNAPPY_WAKE_RADIUS_ENV, "200")
        monkeypatch.setenv(generate_case.SNAPPY_TOWER_Z_MAX_ENV, "30")
        case_dir = tmp_path / "case"
        assert generate_case.main(["--case-dir", str(case_dir)]) == 0
        parsed = _parse_foam(
            (case_dir / "system" / "snappyHexMeshDict").read_text(encoding="utf-8")
        )
        assert float(parsed["geometry"]["rotorWake"]["radius"]) == pytest.approx(200.0)
        assert float(parsed["geometry"]["towerWake"]["max"][2]) == pytest.approx(30.0)

    def test_flag_beats_the_environment_bridge(self, tmp_path, monkeypatch):
        self._clear_env(monkeypatch)
        monkeypatch.setenv(generate_case.SNAPPY_WAKE_RADIUS_ENV, "200")
        case_dir = tmp_path / "case"
        assert (
            generate_case.main(
                ["--case-dir", str(case_dir), "--snappy-wake-radius", "180"]
            )
            == 0
        )
        parsed = _parse_foam(
            (case_dir / "system" / "snappyHexMeshDict").read_text(encoding="utf-8")
        )
        assert float(parsed["geometry"]["rotorWake"]["radius"]) == pytest.approx(180.0)

    def test_resolve_precedence(self, monkeypatch):
        self._clear_env(monkeypatch)
        assert generate_case.resolve_snappy_wake_radius() == pytest.approx(170.0)
        assert generate_case.resolve_snappy_wake_radius(180.0) == pytest.approx(180.0)
        monkeypatch.setenv(generate_case.SNAPPY_WAKE_RADIUS_ENV, "200")
        assert generate_case.resolve_snappy_wake_radius() == pytest.approx(200.0)
        # An explicit flag wins over the environment.
        assert generate_case.resolve_snappy_wake_radius(180.0) == pytest.approx(180.0)

    @pytest.mark.parametrize(
        "overrides,offending",
        [
            ({"wake_radius": 140.0}, "snappy wake radius 140"),
            ({"disk_half_thickness": 25.0}, "snappy wake upstream 20"),
            ({"tower_downstream": 15.0}, "snappy tower downstream 15"),
            ({"tower_z_min": 20.0}, "snappy tower z max 10"),
            ({"disk_radius": 0.0}, "snappy disk radius 0 must be positive"),
            ({"wake_level_offset": -1}, "snappy wake level offset -1"),
        ],
    )
    def test_nesting_validation_rejects_inconsistent_geometry(
        self, overrides, offending
    ):
        with pytest.raises(ValueError) as error:
            generate_case.render_snappy_dict(**overrides)
        assert offending in str(error.value)

    def test_invalid_combination_fails_generation_with_a_named_message(
        self, tmp_path, monkeypatch, capsys
    ):
        self._clear_env(monkeypatch)
        case_dir = tmp_path / "case"
        assert (
            generate_case.main(
                [
                    "--case-dir",
                    str(case_dir),
                    "--snappy-wake-radius",
                    "140",
                ]
            )
            == 2
        )
        assert "snappy wake radius 140" in capsys.readouterr().err
