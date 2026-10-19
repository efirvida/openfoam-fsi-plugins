"""Contracts for the UAE6 raw-archive reference tables.

The archive itself is gitignored, so these tests pin the *committed* derived
tables and the decoder, which is what the ALM comparison actually reads. The
tests that need the archive skip cleanly when it is not present; the decoder and
schema tests always run.

See `data/experiment/uae6-archive/PROVENANCE.md`.
"""

from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
TURBINESFOAM = TESTS_DIR.parent
PACKAGE = TURBINESFOAM / "validation" / "phaseVI"
REFERENCE_DIR = PACKAGE / "data" / "experiment" / "uae6-archive"
ARCHIVE_DIR = TURBINESFOAM / "articles" / "uae6"

EXTRACTOR_PATH = PACKAGE / "scripts" / "extractUAE6Reference.py"
CONVERTER_PATH = ARCHIVE_DIR / "eng2parquet.py"


def _load_module(path: Path, name: str):
    """Load a script by path, registering it for `@dataclass` to resolve."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # `@dataclass` resolves `cls.__module__` through `sys.modules` while the
    # module body runs, so it must be registered before `exec_module`.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


extract = _load_module(EXTRACTOR_PATH, "extract_uae6_reference")

PERFORMANCE_COLUMNS = [
    "file_name", "sequence", "wind_speed_m_s", "yaw_token", "yaw_deg",
    "repetition", "rpm", "tsr", "rotpow_kw", "lsstqcor_nm", "eaeroth_n",
    "wtbaro_pa", "wtatemp_degc", "rho_kg_m3",
]
SPANWISE_COLUMNS = ["file_name", "sequence", "wind_speed_m_s", "r_over_R",
                    "cn", "ct", "cm", "cth", "ctq", "qnorm_pa"]
STATIONS = [0.3, 0.47, 0.63, 0.8, 0.95]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        # The 135 deg trap: reading the yaw field by position turns this into
        # 13 deg with repetition 5.
        ("uae6.z18.00.s0501350", (5, 135, 0, "0135")),
        ("uae6.z18.00.s0500050", (5, 5, 0, "0005")),
        ("uae6.z18.00.s0700000", (7, 0, 0, "0000")),
        ("uae6.z18.00.s2500001", (25, 0, 1, "0000")),
        # The `m` marker is a negative sign, not a neutral marker: h05m0050
        # measures -5.141 deg.
        ("uae6.z07.00.h05m0050", (5, -5, 0, "m005")),
        ("uae6.z07.00.h20m0000", (20, 0, 0, "m000")),
        ("uae6.z07.00.h05m0001", (5, 0, 1, "m000")),
    ],
)
def test_stem_grammar_decodes_speed_yaw_and_repetition(stem, expected):
    parsed = extract.parse_stem(stem)
    assert parsed is not None, stem
    speed, yaw_deg, repetition, token = expected
    assert parsed.speed == speed
    assert parsed.yaw_deg == yaw_deg
    assert parsed.repetition == repetition
    assert parsed.yaw_token == token
    assert parsed.name == stem.split(".")[-1]


@pytest.mark.parametrize(
    "stem",
    [
        "uae6.z18.00.s07ysu00",   # 1 deg/s 360 deg yaw sweep, variable yaw
        "uae6.z18.00.s10ysu00",
        "uae6.z15.00.p10000a0",   # P's pitch-marker naming variant
        "uae6.z11.00.l2000rd0",   # Sequence L: ramp/step, not a fixed yaw
        "uae6.z14.00.o30001",     # Sequence O: sinusoidal AOA, sequential index
    ],
)
def test_stem_grammar_rejects_non_fixed_yaw_points(stem):
    assert extract.parse_stem(stem) is None


@pytest.mark.parametrize("sequence", ["S", "H"])
def test_archive_frame_enrichment(tmp_path, monkeypatch, sequence):
    """All added channels use the same good-frame mask, not header means."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    archive = tmp_path / "raw"
    (archive / "parquet").mkdir(parents=True)
    name = f"uae6.z07.00.{sequence.lower()}0500000"
    columns = {key: [2.0, 4.0, 999.0] for key in extract.POINT_COLUMNS}
    columns.update(err=[128, 128, 0], YAW=[0.0, 0.0, 90.0])
    for prefix, _ in extract.STATIONS:
        for kind, value in (("CTH", 0.2), ("CTQ", 0.03), ("QNORM", 100.0)):
            columns[f"{kind}{prefix}"] = [value, 3 * value, 999.0]
    if sequence == "H":
        for prefix in ("34", "51", "67", "84", "91"):
            for kind in ("A", "F"):
                columns[f"5HP{prefix}{kind}"] = [1.0, 3.0, 999.0]
    pq.write_table(pa.table(columns), archive / "parquet" / f"{name}.parquet")
    (archive / f"{name}.eng").write_bytes(b"synthetic")
    monkeypatch.setattr(extract, "ARCHIVE_DIR", archive)
    before = {p: p.read_bytes() for p in archive.rglob("*") if p.is_file()}
    performance, stations, digest = extract.read_point(extract.parse_stem(name), False)
    assert performance["rpm"] == 3.0  # existing field preserved
    assert digest["err_flagged_frames"] == 1
    for row in stations:
        assert row["cn"] == 3.0
        assert row["cth"] == pytest.approx(0.4)
        assert row["ctq"] == pytest.approx(0.06)
        assert row["qnorm_pa"] == 200.0
    if sequence == "H":
        for channel in extract.PROBE_CHANNELS:
            assert performance[channel] == 2.0
    assert {p: p.read_bytes() for p in archive.rglob("*") if p.is_file()} == before
    (archive / f"{name}.hd1").write_text("synthetic header")
    out = tmp_path / "out"
    monkeypatch.setattr(extract, "ROOT", tmp_path)
    monkeypatch.setattr(extract, "OUT_DIR", out)
    # This mode must not even inspect or render the separate workbook tables.
    monkeypatch.setattr(extract, "build_committed_enrichment",
                        lambda: pytest.fail("archive-only touched workbook tables"))
    assert extract.main(["--sequences", sequence, "--no-hash", "--archive-only"]) == 0
    if sequence == "H":
        probes = read_rows(out / "sequence_H_probes.csv")
        assert len(probes) == 5
        assert [float(row["r_over_R"]) for row in probes] == [0.34, 0.51, 0.67, 0.84, 0.91]
        assert all(float(row["local_flow_angle_deg"]) == 2 for row in probes)
        assert all(float(row["spanwise_flow_angle_deg"]) == 2 for row in probes)
    written = {p: p.read_bytes() for p in out.iterdir()}
    assert extract.main(["--sequences", sequence, "--no-hash", "--archive-only", "--check"]) == 0
    assert {p: p.read_bytes() for p in out.iterdir()} == written
    target = out / f"sequence_{sequence}_spanwise.csv"
    target.write_text(target.read_text().replace("200", "201"))
    stale = {p: p.read_bytes() for p in out.iterdir()}
    assert extract.main(["--sequences", sequence, "--no-hash", "--archive-only", "--check"]) == 1
    assert {p: p.read_bytes() for p in out.iterdir()} == stale


@pytest.mark.parametrize("sequence", ["S", "H"])
def test_enriched_seven_ms_crosscheck(sequence):
    derived = read_rows(REFERENCE_DIR / f"sequence_{sequence}_spanwise.csv")
    expected = read_rows(PACKAGE / "data/experiment" / f"sequence_{sequence}_spanwise.csv")
    for row in expected:
        if float(row["wind_speed_m_s"]) != 7:
            continue
        match = next(r for r in derived if r["file_name"] == row["file_name"]
                     and float(r["r_over_R"]) == float(row["r_over_R"]))
        for key in ("cth", "ctq", "qnorm_pa"):
            assert float(match[key]) == pytest.approx(float(row[key]), rel=1e-9)


@pytest.mark.parametrize("sequence", ["S", "H"])
def test_committed_reference_covers_the_0deg_power_curve(sequence):
    performance = read_rows(REFERENCE_DIR / f"sequence_{sequence}_performance.csv")
    assert list(performance[0]) == PERFORMANCE_COLUMNS
    assert len(performance) == 21
    assert sorted(int(row["wind_speed_m_s"]) for row in performance) == list(range(5, 26))
    assert {row["sequence"] for row in performance} == {sequence}
    for row in performance:
        # The canonical rows are the 0 deg points by construction.
        assert abs(float(row["yaw_deg"])) <= extract.YAW_ABS_TOLERANCE_DEG
        assert float(row["rpm"]) == pytest.approx(71.5, abs=1.0)
        assert float(row["tsr"]) > 0.0
        assert float(row["rho_kg_m3"]) == pytest.approx(1.2, abs=0.15)

    spanwise = read_rows(REFERENCE_DIR / f"sequence_{sequence}_spanwise.csv")
    assert list(spanwise[0]) == SPANWISE_COLUMNS
    assert len(spanwise) == 21 * len(STATIONS)
    for row in spanwise:
        assert row["sequence"] == sequence
        assert float(row["qnorm_pa"]) > 0
        assert all(row[key] for key in ("cth", "ctq"))
    per_speed = {}
    for row in spanwise:
        per_speed.setdefault(row["file_name"], []).append(float(row["r_over_R"]))
    assert len(per_speed) == 21
    for stations in per_speed.values():
        assert sorted(stations) == STATIONS


def test_crosscheck_cli_is_read_only(capsys):
    paths = list(REFERENCE_DIR.glob("*.csv"))
    before = {p: p.read_bytes() for p in paths}
    assert extract.main(["--cross-check"]) == 0
    expected = "".join(f"{sequence} 7 m/s {column}: max relative difference = 0\n"
                       for sequence in ("H", "S")
                       for column in ("cth", "ctq", "qnorm_pa"))
    assert capsys.readouterr() == (expected, "")
    assert {p: p.read_bytes() for p in paths} == before


def test_reference_reproduces_the_workbook_rows():
    """The two sources are independent encodings of the same measurements."""
    derived = {
        row["file_name"]: row
        for row in read_rows(REFERENCE_DIR / "sequence_S_performance.csv")
    }
    for workbook_row in read_rows(PACKAGE / "data" / "experiment" / "sequence_S_performance.csv"):
        name = workbook_row["file_name"]
        assert name in derived, f"{name} missing from the derived table"
        row = derived[name]
        for column in ("rpm", "tsr", "rotpow_kw", "lsstqcor_nm", "eaeroth_n",
                       "wtbaro_pa", "wtatemp_degc", "rho_kg_m3"):
            assert float(row[column]) == pytest.approx(
                float(workbook_row[column]), rel=1e-5
            ), column
        # The workbook rounds the measured yaw to three decimals.
        assert float(row["yaw_deg"]) == pytest.approx(
            float(workbook_row["yaw_deg"]), abs=2e-3
        )
        assert row["yaw_token"] == workbook_row["yaw_token"]
        assert int(row["repetition"]) == int(workbook_row["repetition"])

    derived_span = {
        (row["file_name"], float(row["r_over_R"])): row
        for row in read_rows(REFERENCE_DIR / "sequence_S_spanwise.csv")
    }
    workbook_span = read_rows(PACKAGE / "data" / "experiment" / "sequence_S_spanwise.csv")
    assert len(workbook_span) == 5
    for workbook_row in workbook_span:
        key = (workbook_row["file_name"], float(workbook_row["r_over_R"]))
        assert key in derived_span, key
        for column in ("cn", "ct", "cm"):
            assert float(derived_span[key][column]) == pytest.approx(
                float(workbook_row[column]), abs=1e-4
            ), column


@pytest.mark.skipif(
    not CONVERTER_PATH.is_file(), reason="UAE6 archive tool not present"
)
@pytest.mark.parametrize(
    "stem",
    [
        "uae6.z18.00.s0501350", "uae6.z18.00.s0500050",
        "uae6.z18.00.s0700000", "uae6.z18.00.s2500001",
        "uae6.z07.00.h05m0050", "uae6.z07.00.h20m0000",
        "uae6.z07.00.h05m0001",
        "uae6.z18.00.s07ysu00", "uae6.z15.00.p10000a0",
        "uae6.z11.00.l2000rd0", "uae6.z14.00.o30001",
    ],
)
def test_manifest_decoder_agrees_with_the_extractor(stem):
    """The converter's decoder and the extractor's must not drift apart.

    `eng2parquet.py` writes the decoded conditions into `manifest.csv`; the
    extractor is the authoritative decode because it also asserts every yaw
    against the measured `YAW` channel. Two implementations of one grammar are a
    drift risk, so this pins them to agree on every documented case, including
    the ones that must decode to nothing.
    """
    converter = _load_module(CONVERTER_PATH, "eng2parquet")
    decoded = converter.decode_stem(stem)
    parsed = extract.parse_stem(stem)
    if parsed is None:
        assert decoded == {
            "sequence": "", "speed_mps": "", "yaw_deg": "", "repetition": "",
        }, stem
        return
    assert decoded["sequence"] == parsed.sequence.upper(), stem
    assert decoded["speed_mps"] == parsed.speed, stem
    assert decoded["yaw_deg"] == parsed.yaw_deg, stem
    assert decoded["repetition"] == parsed.repetition, stem


@pytest.mark.skipif(not ARCHIVE_DIR.is_dir(), reason="UAE6 archive not present")
def test_inventory_accounts_for_every_sequence_s_archive_file():
    stems = sorted(path.stem for path in ARCHIVE_DIR.glob("uae6.*.*.s*.hd1"))
    assert len(stems) == 106
    skipped = sorted(stem for stem in stems if extract.parse_stem(stem) is None)
    assert skipped == ["uae6.z18.00.s07ysu00", "uae6.z18.00.s10ysu00"]

    inventory = read_rows(REFERENCE_DIR / "INVENTORY.csv")
    inventory = [row for row in inventory if row["sequence"] == "S"]
    assert len(inventory) + len(skipped) == len(stems)
    roles: dict[str, int] = {}
    for row in inventory:
        roles[row["role"]] = roles.get(row["role"], 0) + 1
    assert roles == {"canonical-0deg": 21, "alternate-0deg": 16, "off-axis": 67}
    # The inventory is the sha256 anchor for a gitignored archive.
    for row in inventory:
        assert len(row["eng_sha256"]) == 64
        assert len(row["hd1_sha256"]) == 64
        assert int(row["eng_bytes"]) == int(row["n_frames"]) * 1141
        assert int(row["err_flagged_frames"]) >= 0
