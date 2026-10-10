# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the two-run spanwise comparison added to ``compare_spanwise.py``.

The tool already diagnoses one run; a campaign A/B needs the same reader to
answer "does run B show the same station-by-station signature as run A?" without
a second, drifting reader. These tests pin the properties that make the
comparison safe to publish: the band arithmetic, that the two runs must share
one element grid (a mismatch fails loudly, never interpolates), that an empty
band is reported absent, that neither run is written, and that the existing
single-run output is untouched when ``--compare-with`` is not given.
"""

from __future__ import annotations

import csv
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
TOOL = PACKAGE / "validation" / "iea15mw" / "scripts" / "compare_spanwise.py"

ELEMENT_HEADER = (
    "time,root_dist,alpha_deg,alpha_geom_deg,Re,cl,cd,"
    "c_ref_n,c_ref_t,f_ref_n,f_ref_t\n"
)
TURBINE_HEADER = "time,tsr,cp,cd,ct\n"

STORE_HEADER = "source,quantity,r_over_R_or_radius_m,value,unit,note\n"

#: Byte-exact stdout of the tool on the two-row synthetic fixture below.  It
#: pins that ``--references`` is strictly additive: with the flag absent the
#: single-run and two-run paths must print exactly these bytes.  ``{run_a}``
#: and ``{run_b}`` are the ``tmp_path`` run directories.
ALONE_GOLDEN = (
    "run: {run_a}\n"
    "window: last 0 revolutions = [100, 100] s (period 7.98085 s, 7.518 rpm)\n"
    "elements: 2 blade-1 CSVs\n"
    "\n"
    "spanwise time-mean (2 elements, dr = 58.50000 m)\n"
    "  r/R,alpha_deg,alpha_geom_deg,Re,cl,cd,c_n,c_t,Fn_per_len,Ft_per_len,c_t/c_n\n"
    "  0.4207,5.000,5.000,1000000,1.0000,0.0100,1.0000,0.5000,1.2,1.2,0.5000\n"
    "  0.6146,6.000,6.000,1000000,1.0000,0.0100,2.0000,0.6000,1.2,1.2,0.3000\n"
    "\n"
    "rotor integration (module normalisation, A = pi*R^2, R = 120.67532, "
    "V = 10.659, rhoRef = 1.225)\n"
    "  ours   : C_T 0.0001  C_Q 0.0001  C_P 0.0006\n"
    "  module : C_T 0.0600  C_Q 0.0600  C_P 0.4000  "
    "(turbine.csv columns cd/ct/cp; TSR 8.900000)\n"
    "  ratio  : C_T 0.0023  C_Q 0.0012  C_P 0.0016\n"
)
COMPARISON_GOLDEN = (
    "\n"
    "spanwise comparison: A = {run_a}, B = {run_b}\n"
    "  band,stations,alpha_a_deg,alpha_b_deg,delta_alpha_deg,c_n_ratio,c_t_ratio\n"
    "  0.3-0.5,1,5.0000,6.0000,+1.0000,1.1000,1.2000\n"
    "  0.5-0.7,1,6.0000,8.0000,+2.0000,1.0500,1.1667\n"
    "  0.7-0.9,0,absent,absent,absent,absent,absent\n"
    "  0.3-0.9,2,5.5000,7.0000,+1.5000,1.0667,1.1818\n"
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


compare_spanwise = _load("compare_spanwise", TOOL)


def _root_dist(r_over_r: float) -> float:
    """root_dist that projects to ``r_over_r`` with the module's geometry."""
    module = compare_spanwise
    return (
        r_over_r * module.ROTOR_RADIUS - module.HUB_RADIUS
    ) / module.BLADE_SPAN


def _profile(rows) -> list[dict]:
    """A synthetic averaged profile from ``(r/R, alpha, c_n, c_t)`` rows."""
    return [
        {
            "root_dist": _root_dist(rr),
            "alpha_deg": alpha,
            "c_ref_n": c_n,
            "c_ref_t": c_t,
        }
        for rr, alpha, c_n, c_t in rows
    ]


def _make_run(root: Path, rows) -> Path:
    """Write a minimal run directory holding per-element and turbine CSVs.

    Every element carries two time rows (0.0 and 100.0); the CLI is invoked
    with ``--revs 0`` so the window collapses onto the 100.0 sample.
    """
    element_dir = root / "postProcessing" / "actuatorLineElements" / "0"
    element_dir.mkdir(parents=True)
    for index, (rd, alpha, c_n, c_t) in enumerate(rows):
        (element_dir / f"turbine.blade1.element{index}.csv").write_text(
            ELEMENT_HEADER
            + f"0.0,{rd},{alpha},{alpha},1000000,1.0,0.01,{c_n},{c_t},1.0,1.0\n"
            + f"100.0,{rd},{alpha},{alpha},1000000,1.0,0.01,{c_n},{c_t},1.0,1.0\n",
            encoding="utf-8",
        )
    turbine_dir = root / "postProcessing" / "turbines" / "0"
    turbine_dir.mkdir(parents=True)
    (turbine_dir / "turbine.csv").write_text(
        TURBINE_HEADER + "0.0,8.9,0.40,0.06,0.06\n100.0,8.9,0.40,0.06,0.06\n",
        encoding="utf-8",
    )
    return root


def _files(root: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def _write_store(path: Path, stations) -> Path:
    """A synthetic long-format store from ``{source: {r/R: {quantity: value}}}``."""
    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write(STORE_HEADER)
        for source, by_radius in stations.items():
            for radius, quantities in by_radius.items():
                for quantity, value in quantities.items():
                    stream.write(
                        f'{source},{quantity},{radius},{value},-,"synthetic"\n'
                    )
    return path


def _two_source_store(path: Path) -> Path:
    """``srcA`` on three stations, ``srcB`` only on the first band."""
    return _write_store(path, {
        "srcA": {
            0.4: {"alpha_deg": 4.0, "cn": 1.2, "ct": 0.5},
            0.6: {"alpha_deg": 6.0, "cn": 2.4, "ct": 0.9},
            0.8: {"alpha_deg": 8.0, "cn": 3.6, "ct": 1.3},
        },
        "srcB": {
            0.4: {"alpha_deg": 5.0, "cn": 1.5, "ct": 0.7},
        },
    })


REFERENCE_ROWS_A = [
    (0.4, 5.0, 1.0, 0.5), (0.6, 6.0, 2.0, 0.6), (0.8, 7.0, 3.0, 0.7),
]
REFERENCE_ROWS_B = [
    (0.4, 6.0, 1.1, 0.6), (0.6, 8.0, 2.1, 0.7), (0.8, 9.0, 3.1, 0.8),
]


def test_band_arithmetic_uses_the_paired_stations() -> None:
    run_a = _profile(
        [(0.4, 5.0, 1.0, 0.5), (0.6, 6.0, 2.0, 0.6), (0.8, 7.0, 3.0, 0.7)]
    )
    run_b = _profile(
        [(0.4, 6.0, 1.1, 0.6), (0.6, 8.0, 2.1, 0.7), (0.8, 9.0, 3.1, 0.8)]
    )

    results = compare_spanwise.compare_profiles(run_a, "runA", run_b, "runB")
    by_band = {item["band"]: item for item in results}

    band = by_band[(0.3, 0.5)]
    assert band["stations"] == 1
    assert band["alpha_a"] == pytest.approx(5.0)
    assert band["alpha_b"] == pytest.approx(6.0)
    assert band["delta_alpha"] == pytest.approx(1.0)
    assert band["c_n_ratio"] == pytest.approx(1.1)
    assert band["c_t_ratio"] == pytest.approx(1.2)

    overall = by_band[(0.3, 0.9)]
    assert overall["stations"] == 3
    assert overall["alpha_a"] == pytest.approx(6.0)
    assert overall["alpha_b"] == pytest.approx((6.0 + 8.0 + 9.0) / 3)
    assert overall["delta_alpha"] == pytest.approx((6.0 + 8.0 + 9.0) / 3 - 6.0)
    assert overall["c_n_ratio"] == pytest.approx(2.1 / 2.0)
    assert overall["c_t_ratio"] == pytest.approx(0.7 / 0.6)


def test_different_station_counts_fail_loudly() -> None:
    run_a = _profile([(0.4, 5.0, 1.0, 0.5), (0.6, 6.0, 2.0, 0.6)])
    run_b = _profile(
        [(0.4, 5.0, 1.0, 0.5), (0.6, 6.0, 2.0, 0.6), (0.8, 7.0, 3.0, 0.7)]
    )

    with pytest.raises(compare_spanwise.StationGridMismatchError) as caught:
        compare_spanwise.compare_profiles(run_a, "runA", run_b, "runB")

    message = str(caught.value)
    assert "runA" in message and "runB" in message
    assert "2" in message and "3" in message


def test_r_over_r_grid_mismatch_fails_loudly() -> None:
    run_a = _profile([(0.40, 5.0, 1.0, 0.5)])
    run_b = _profile([(0.41, 5.0, 1.0, 0.5)])

    with pytest.raises(compare_spanwise.StationGridMismatchError) as caught:
        compare_spanwise.compare_profiles(run_a, "runA", run_b, "runB")

    message = str(caught.value)
    assert "runA" in message and "runB" in message
    assert "r/R" in message


def test_a_band_with_no_stations_is_reported_absent() -> None:
    run_a = _profile([(0.4, 5.0, 1.0, 0.5)])
    run_b = _profile([(0.4, 6.0, 1.1, 0.6)])

    results = compare_spanwise.compare_profiles(run_a, "runA", run_b, "runB")
    by_band = {item["band"]: item for item in results}

    assert set(by_band) == {(0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.3, 0.9)}
    for bounds in ((0.5, 0.7), (0.7, 0.9)):
        item = by_band[bounds]
        assert item["stations"] == 0
        assert item["alpha_a"] is None
        assert item["alpha_b"] is None
        assert item["delta_alpha"] is None
        assert item["c_n_ratio"] is None
        assert item["c_t_ratio"] is None


def test_comparison_never_mutates_either_run(tmp_path: Path) -> None:
    rows_a = [(0.40, 5.0, 1.0, 0.5), (0.60, 6.0, 2.0, 0.6)]
    rows_b = [(0.40, 6.0, 1.1, 0.6), (0.60, 8.0, 2.1, 0.7)]
    run_a = _make_run(tmp_path / "run-a", rows_a)
    run_b = _make_run(tmp_path / "run-b", rows_b)
    before_a, before_b = _files(run_a), _files(run_b)

    code = compare_spanwise.main([
        "--run-dir", str(run_a), "--time", "0", "--revs", "0",
        "--compare-with", str(run_b), "--compare-time", "0",
        "--out", str(tmp_path / "span.csv"),
        "--comparison-out", str(tmp_path / "comparison.csv"),
    ])

    assert code == 0
    assert _files(run_a) == before_a
    assert _files(run_b) == before_b


def test_comparison_out_writes_a_csv_that_names_both_runs(tmp_path: Path) -> None:
    rows_a = [(0.40, 5.0, 1.0, 0.5), (0.60, 6.0, 2.0, 0.6)]
    rows_b = [(0.40, 6.0, 1.1, 0.6), (0.60, 8.0, 2.1, 0.7)]
    run_a = _make_run(tmp_path / "run-a", rows_a)
    run_b = _make_run(tmp_path / "run-b", rows_b)
    out = tmp_path / "comparison.csv"

    result = subprocess.run(
        [
            sys.executable, str(TOOL),
            "--run-dir", str(run_a), "--time", "0", "--revs", "0",
            "--compare-with", str(run_b), "--compare-time", "0",
            "--comparison-out", str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    with out.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows
    assert rows[0]["run_a"] == str(run_a)
    assert rows[0]["run_b"] == str(run_b)
    assert {"band_lo", "band_hi", "stations", "delta_alpha_deg",
            "c_n_ratio", "c_t_ratio"} <= set(rows[0])


def test_without_compare_with_the_output_is_unchanged(tmp_path: Path) -> None:
    rows_a = [(0.40, 5.0, 1.0, 0.5), (0.60, 6.0, 2.0, 0.6)]
    rows_b = [(0.40, 6.0, 1.1, 0.6), (0.60, 8.0, 2.1, 0.7)]
    run_a = _make_run(tmp_path / "run-a", rows_a)
    run_b = _make_run(tmp_path / "run-b", rows_b)
    base = [sys.executable, str(TOOL), "--run-dir", str(run_a),
            "--time", "0", "--revs", "0"]

    alone = subprocess.run(base, capture_output=True, text=True, check=False)
    combined = subprocess.run(
        base + ["--compare-with", str(run_b), "--compare-time", "0"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert alone.returncode == 0, alone.stderr
    assert combined.returncode == 0, combined.stderr
    assert "comparison" not in alone.stdout.lower()
    # The flag only appends: the single-run output is a strict prefix.
    assert combined.stdout.startswith(alone.stdout)
    assert len(combined.stdout) > len(alone.stdout)


def test_reference_band_means_and_ratios_are_against_run_a(tmp_path: Path) -> None:
    store = _two_source_store(tmp_path / "refs.csv")
    results = compare_spanwise.attach_references(
        compare_spanwise.compare_profiles(
            _profile(REFERENCE_ROWS_A), "runA",
            _profile(REFERENCE_ROWS_B), "runB",
        ),
        compare_spanwise.load_reference_profiles(store, ("srcA", "srcB")),
        ("srcA", "srcB"),
    )
    by_band = {item["band"]: item for item in results}

    band = by_band[(0.3, 0.5)]["references"]["srcA"]
    assert band["stations"] == 1
    assert band["alpha_deg"] == pytest.approx(4.0)
    assert band["cn"] == pytest.approx(1.2)
    assert band["ct"] == pytest.approx(0.5)
    assert band["cn_ratio"] == pytest.approx(1.2)  # 1.2 / run-A 1.0
    assert band["ct_ratio"] == pytest.approx(1.0)  # 0.5 / run-A 0.5

    band = by_band[(0.5, 0.7)]["references"]["srcA"]
    assert band["stations"] == 1
    assert band["alpha_deg"] == pytest.approx(6.0)
    assert band["cn"] == pytest.approx(2.4)
    assert band["ct"] == pytest.approx(0.9)
    assert band["cn_ratio"] == pytest.approx(1.2)  # 2.4 / run-A 2.0
    assert band["ct_ratio"] == pytest.approx(1.5)  # 0.9 / run-A 0.6

    overall = by_band[(0.3, 0.9)]["references"]["srcA"]
    assert overall["stations"] == 3
    assert overall["alpha_deg"] == pytest.approx(6.0)
    assert overall["cn"] == pytest.approx(2.4)
    assert overall["ct"] == pytest.approx(0.9)
    assert overall["cn_ratio"] == pytest.approx(1.2)
    assert overall["ct_ratio"] == pytest.approx(1.5)


def test_unknown_reference_source_fails_loudly(tmp_path: Path) -> None:
    store = _two_source_store(tmp_path / "refs.csv")

    with pytest.raises(compare_spanwise.UnknownReferenceSourceError) as caught:
        compare_spanwise.load_reference_profiles(store, ("srcZ",))

    message = str(caught.value)
    assert "srcZ" in message
    assert "srcA" in message and "srcB" in message


def test_metre_radius_column_fails_loudly(tmp_path: Path) -> None:
    store = _write_store(tmp_path / "refs.csv", {
        "paper-source": {
            0.119: {"normal_force_per_span": 100.0},
            30.0: {"normal_force_per_span": 200.0},
            116.8: {"normal_force_per_span": 300.0},
        },
    })

    with pytest.raises(compare_spanwise.ReferenceUnitError) as caught:
        compare_spanwise.load_reference_profiles(store, ("paper-source",))

    message = str(caught.value)
    assert "paper-source" in message
    assert "radius" in message


def test_a_band_with_no_reference_stations_is_reported_absent(
    tmp_path: Path,
) -> None:
    store = _two_source_store(tmp_path / "refs.csv")
    results = compare_spanwise.attach_references(
        compare_spanwise.compare_profiles(
            _profile(REFERENCE_ROWS_A), "runA",
            _profile(REFERENCE_ROWS_B), "runB",
        ),
        compare_spanwise.load_reference_profiles(store, ("srcA", "srcB")),
        ("srcA", "srcB"),
    )
    by_band = {item["band"]: item for item in results}

    band = by_band[(0.5, 0.7)]["references"]["srcB"]
    assert band["stations"] == 0
    assert band["alpha_deg"] is None
    assert band["cn"] is None
    assert band["ct"] is None
    assert band["cn_ratio"] is None
    assert band["ct_ratio"] is None


def test_references_flag_adds_reference_columns_to_the_table_and_csv(
    tmp_path: Path,
) -> None:
    store = _two_source_store(tmp_path / "refs.csv")
    run_a = _make_run(tmp_path / "run-a", REFERENCE_ROWS_A)
    run_b = _make_run(tmp_path / "run-b", REFERENCE_ROWS_B)
    out = tmp_path / "comparison.csv"

    result = subprocess.run(
        [
            sys.executable, str(TOOL),
            "--run-dir", str(run_a), "--time", "0", "--revs", "0",
            "--compare-with", str(run_b), "--compare-time", "0",
            "--references", "--reference-store", str(store),
            "--reference-source", "srcA", "--reference-source", "srcB",
            "--comparison-out", str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    lines = [line.strip() for line in result.stdout.splitlines()]
    header = next(line for line in lines if line.startswith("band,"))
    assert "srcA_n" in header and "srcA_cn_ratio" in header
    assert "srcB_ct_ratio" in header
    # The header names run A as the baseline the ratios are measured against.
    assert str(run_a) in result.stdout
    band_lo_high = header.split(",").index("srcB_n")
    empty_band = next(line for line in lines if line.startswith("0.5-0.7,"))
    fields = empty_band.split(",")
    assert fields[band_lo_high] == "0"
    assert fields[band_lo_high + 1] == "n/a"
    assert fields[band_lo_high + 2] == "n/a"

    with out.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert "srcA_n" in rows[0] and "srcA_cn_ratio" in rows[0]
    absent = next(row for row in rows if row["band_lo"] == "0.5")
    assert absent["srcB_n"] == "0"
    assert absent["srcB_cn"] == "" and absent["srcB_cn_ratio"] == ""


def test_without_references_the_output_is_byte_identical(tmp_path: Path) -> None:
    rows_a = [(0.40, 5.0, 1.0, 0.5), (0.60, 6.0, 2.0, 0.6)]
    rows_b = [(0.40, 6.0, 1.1, 0.6), (0.60, 8.0, 2.1, 0.7)]
    run_a = _make_run(tmp_path / "run-a", rows_a)
    run_b = _make_run(tmp_path / "run-b", rows_b)
    base = [sys.executable, str(TOOL), "--run-dir", str(run_a),
            "--time", "0", "--revs", "0"]

    alone = subprocess.run(base, capture_output=True, text=True, check=False)
    combined = subprocess.run(
        base + ["--compare-with", str(run_b), "--compare-time", "0"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert alone.returncode == 0, alone.stderr
    assert combined.returncode == 0, combined.stderr
    assert alone.stdout == ALONE_GOLDEN.format(run_a=run_a)
    assert combined.stdout == (ALONE_GOLDEN + COMPARISON_GOLDEN).format(
        run_a=run_a, run_b=run_b
    )
