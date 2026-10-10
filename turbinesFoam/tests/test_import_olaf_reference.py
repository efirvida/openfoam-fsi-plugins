# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the OLAF free-vortex-wake reference importer.

``analysis/spanwise-references.csv`` is the committed long-format reference
store every spanwise comparison reads, and it is hand-curated data behind
published figures. The OLAF profile lives only in a gitignored ``reference/``
directory, so it must be transformed by a committed, re-runnable producer rather
than transcribed by hand.

These tests pin the properties that make the producer safe: the column mapping
and units, one row per station per quantity, that a second run does not
duplicate rows, that **no other source's row changes byte for byte**, that a
missing source CSV or column fails loudly with a distinct non-zero code, and
that ``--dry-run`` writes nothing. Because a fresh clone has no ``reference/``
directory, the source is always a synthetic CSV in ``tmp_path``.
"""

from __future__ import annotations

import csv
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPT = PACKAGE / "validation" / "iea15mw" / "scripts" / "import_olaf_reference.py"

SOURCE_HEADER = "node,r_over_R,Vrel,Alpha,Vindx,Vindy,Cn,Ct,Fn,Ft,TnInd,AxInd\n"
REFERENCE_HEADER = "source,quantity,r_over_R_or_radius_m,value,unit,note\n"

#: (node, r/R, Alpha, Cn, Ct) -- deliberately simple values so the formatting
#: assertion reads cleanly.
STATIONS = [
    ("AB1N001", 0.1, 6.49, 1.14, 0.118944),
    ("AB1N002", 0.5, 4.0, 0.8, 0.05),
    ("AB1N003", 1.0, 2.5, 0.5, 0.01),
]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


importer = _load("import_olaf_reference", SCRIPT)


def _write_source(path: Path) -> Path:
    """Write a synthetic 3-station OLAF spanwise CSV and return its path."""
    body = [SOURCE_HEADER]
    for node, rr, alpha, cn, ct in STATIONS:
        body.append(
            f"{node},{rr:.8f},10.0,{alpha:.6g},0.1,0.2,{cn:.6g},{ct:.6g},"
            "1.0,1.0,0.0,0.0\n"
        )
    path.write_text("".join(body))
    return path


def _read_rows(store: Path) -> list[dict[str, str]]:
    with store.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_block_maps_columns_units_and_one_row_per_station(tmp_path: Path) -> None:
    source = _write_source(tmp_path / "spanwise_olaf.csv")
    store = tmp_path / "spanwise-references.csv"

    count = importer.refresh_reference(source, store)

    # 3 stations x {alpha_deg, cn, ct}.
    assert count == 9
    rows = _read_rows(store)
    assert {row["source"] for row in rows} == {"olaf-fvw"}

    by_quantity: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_quantity.setdefault(row["quantity"], []).append(row)
    assert set(by_quantity) == {"alpha_deg", "cn", "ct"}
    assert {quantity: len(found) for quantity, found in by_quantity.items()} == {
        "alpha_deg": 3,
        "cn": 3,
        "ct": 3,
    }

    # Units: degrees for alpha, dimensionless for the coefficients.
    assert {row["unit"] for row in by_quantity["alpha_deg"]} == {"deg"}
    assert {row["unit"] for row in by_quantity["cn"]} == {"-"}
    assert {row["unit"] for row in by_quantity["ct"]} == {"-"}

    def sorted_by_x(quantity: str) -> list[dict[str, str]]:
        return sorted(
            by_quantity[quantity], key=lambda row: float(row["r_over_R_or_radius_m"])
        )

    # r_over_R is written from the source column, in order, not a radius.
    assert [float(row["r_over_R_or_radius_m"]) for row in sorted_by_x("alpha_deg")] == (
        pytest.approx([0.1, 0.5, 1.0])
    )
    # Alpha -> alpha_deg, Cn -> cn, Ct -> ct.
    assert [float(row["value"]) for row in sorted_by_x("alpha_deg")] == pytest.approx(
        [6.49, 4.0, 2.5]
    )
    assert [float(row["value"]) for row in sorted_by_x("cn")] == pytest.approx(
        [1.14, 0.8, 0.5]
    )
    assert [float(row["value"]) for row in sorted_by_x("ct")] == pytest.approx(
        [0.118944, 0.05, 0.01]
    )

    note = rows[0]["note"]
    for fact in (
        "OpenFAST v5.0.0",
        "OLAF",
        "free-vortex-wake",
        "no Prandtl/Glauert tip loss",
        "IEA-15-240-RWT-Monopile",
        "10.659 m/s",
        "7.518 rpm",
        "15-revolution",
        "reference/olaf-rated/spanwise_olaf.csv",
        "11605824",
        "AeroDyn",
    ):
        assert fact in note, fact


def test_values_round_trip_at_ten_significant_digits(tmp_path: Path) -> None:
    source = _write_source(tmp_path / "spanwise_olaf.csv")
    store = tmp_path / "spanwise-references.csv"

    importer.refresh_reference(source, store)

    for row in _read_rows(store):
        assert len(row["value"]) <= 12
    # The stored text is the exact %.10g rendering of the source value.
    assert any(row["value"] == "0.118944" for row in _read_rows(store))


def test_running_twice_produces_an_identical_file(tmp_path: Path) -> None:
    source = _write_source(tmp_path / "spanwise_olaf.csv")
    store = tmp_path / "spanwise-references.csv"

    importer.refresh_reference(source, store)
    first = store.read_bytes()
    importer.refresh_reference(source, store)

    assert store.read_bytes() == first


def test_other_sources_are_left_byte_identical(tmp_path: Path) -> None:
    store = tmp_path / "spanwise-references.csv"
    store.write_text(
        REFERENCE_HEADER
        + 'other_a,cn,0.10,0.500000,-,"note with, comma"\n'
        + "other_b,ct,0.20,0.600000,-,plain note\n"
    )
    before = store.read_text(encoding="utf-8").splitlines(keepends=True)
    source = _write_source(tmp_path / "spanwise_olaf.csv")

    importer.refresh_reference(source, store)

    after = store.read_text(encoding="utf-8").splitlines(keepends=True)
    # The header and the two foreign sources are untouched, in place.
    assert after[0] == before[0]
    kept = [line for line in after[1:] if not line.startswith("olaf-fvw,")]
    assert kept == before[1:]
    # The new block is appended after them.
    assert [line for line in after[1:] if line.startswith("olaf-fvw,")]


def test_refresh_replaces_an_earlier_olaf_block_without_touching_others(
    tmp_path: Path,
) -> None:
    store = tmp_path / "spanwise-references.csv"
    store.write_text(
        REFERENCE_HEADER
        + "other_a,cn,0.10,0.500000,-,keep me\n"
        + "olaf-fvw,alpha_deg,0.10,999.0,deg,stale\n"
    )
    source = _write_source(tmp_path / "spanwise_olaf.csv")

    importer.refresh_reference(source, store)

    rows = _read_rows(store)
    assert not any(row["note"] == "stale" for row in rows)
    other = [row for row in rows if row["source"] == "other_a"]
    assert len(other) == 1
    assert other[0]["note"] == "keep me"


def test_crlf_store_line_endings_are_preserved(tmp_path: Path) -> None:
    """The real store is CRLF; a read must not rewrite every existing line."""
    store = tmp_path / "spanwise-references.csv"
    foreign = (
        b'other_a,cn,0.10,0.500000,-,"note with, comma"\r\n'
        b"other_b,ct,0.20,0.600000,-,plain note\r\n"
    )
    store.write_bytes(REFERENCE_HEADER.replace("\n", "\r\n").encode() + foreign)
    source = _write_source(tmp_path / "spanwise_olaf.csv")

    importer.refresh_reference(source, store)

    data = store.read_bytes()
    # Foreign rows survive byte for byte, CRLF included.
    assert foreign in data
    # The new block uses the store's own line ending, and no bare LF appears.
    assert data.endswith(b"\r\n")
    assert b"olaf-fvw," in data
    assert b"\n" not in data.replace(b"\r\n", b"")


def test_missing_source_csv_raises_a_typed_error(tmp_path: Path) -> None:
    with pytest.raises(importer.OlafImportError) as caught:
        importer.refresh_reference(tmp_path / "absent.csv", tmp_path / "refs.csv")

    assert caught.value.code == importer.EXIT_SOURCE_MISSING
    assert "absent.csv" in str(caught.value)


def test_missing_source_csv_cli_fails_loudly(tmp_path: Path) -> None:
    store = tmp_path / "spanwise-references.csv"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-csv",
            str(tmp_path / "absent.csv"),
            "--store",
            str(store),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == importer.EXIT_SOURCE_MISSING
    assert "absent.csv" in result.stderr
    assert "Traceback" not in result.stderr
    assert not store.exists()


def test_missing_required_column_fails_loudly(tmp_path: Path) -> None:
    source = tmp_path / "spanwise_olaf.csv"
    source.write_text("node,r_over_R,Alpha\nAB1N001,0.10,6.49\n")
    store = tmp_path / "spanwise-references.csv"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-csv",
            str(source),
            "--store",
            str(store),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == importer.EXIT_COLUMN_MISSING
    assert "Cn" in result.stderr and "Ct" in result.stderr
    assert "Traceback" not in result.stderr
    assert not store.exists()


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    source = _write_source(tmp_path / "spanwise_olaf.csv")
    store = tmp_path / "spanwise-references.csv"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-csv",
            str(source),
            "--store",
            str(store),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert not store.exists()
    assert "9" in result.stdout


def test_dry_run_leaves_an_existing_store_untouched(tmp_path: Path) -> None:
    store = tmp_path / "spanwise-references.csv"
    store.write_text(REFERENCE_HEADER + "other_a,cn,0.10,0.500000,-,keep me\n")
    before = store.read_bytes()
    source = _write_source(tmp_path / "spanwise_olaf.csv")

    importer.refresh_reference(source, store, dry_run=True)

    assert store.read_bytes() == before
