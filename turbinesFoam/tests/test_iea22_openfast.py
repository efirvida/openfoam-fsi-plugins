# SPDX-License-Identifier: GPL-3.0-or-later
"""IEA 22-280-RWT OpenFAST reference setup (``validation/iea22mw``): templates, case
writer, output extraction, table plausibility check and the reference-store importer.

Needs neither OpenFAST nor the external IEA-22 source repository, except the one
``--check`` test that rebuilds the templates from it (skipped when it is absent).
"""

from __future__ import annotations

import csv
import importlib.util
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PACKAGE = TESTS_DIR.parent / "validation" / "iea22mw"
SCRIPTS = PACKAGE / "scripts"
TEMPLATES = PACKAGE / "data" / "openfast-v5-templates"
ROOT = "IEA-22-280-RWT-OLAF_rated"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(SCRIPTS))
builder = _load("iea22_test_build_openfast_templates", SCRIPTS / "build_openfast_templates.py")
runner = _load("iea22_test_openfast_iea22", SCRIPTS / "openfast_iea22.py")
table_check = _load("iea22_test_rated_table_check", SCRIPTS / "rated_table_check.py")
importer = _load("iea22_test_import_olaf_reference", SCRIPTS / "import_olaf_reference.py")

needs_source = pytest.mark.skipif(
    not (builder.DEFAULT_SOURCE / "OpenFAST" / "IEA-22-280-RWT-Monopile").exists(),
    reason="IEA-22 read-only source repository not available",
)


def _text(suffix: str) -> str:
    return (TEMPLATES / f"{ROOT}{suffix}").read_text()


# --- templates -------------------------------------------------------------------
def test_templates_have_no_absolute_paths_and_all_files_exist():
    names = [".fst", "_ElastoDyn.dat", "_ElastoDyn_tower.dat", "_InflowFile.dat", "_AeroDyn15.dat", "_OLAF.dat"]
    for suffix in names:
        assert "/scratch" not in _text(suffix), suffix
        assert "IEA-15" not in _text(suffix), suffix


def test_aerodyn_template_lists_the_59_polars_of_the_blade_table():
    text = _text("_AeroDyn15.dat")
    names = re.findall(r'^"Airfoils/IEA-22-280-RWT_AeroDyn15_Polar_(\d\d)\.dat"', text, re.M)
    rows = [r for r in csv.DictReader(l for l in (PACKAGE / "data" / "iea22mw_blade.csv").open() if not l.startswith("#"))]
    assert builder.get_value(text, "NumAFfiles") == "59"
    assert names == [f"{i:02d}" for i in range(59)]
    assert len(rows) == 59


def test_aerodyn_template_is_the_like_for_like_option_set():
    text = _text("_AeroDyn15.dat")
    expected = {"Wake_Mod": "1", "BEM_Mod": "2", "UA_Mod": "0", "DBEMT_Mod": "0", "TipLoss": "True", "HubLoss": "True",
                "AFTabMod": "1", "AoA34": "False", "TwrAero": "True", "NumTwrNds": "31"}
    for key, value in expected.items():
        assert builder.get_value(text, key) == value, key
    assert len(re.findall(r"^\s*\d+\.\d+\s+\S+\s+0\.5\s+0\.1\s+", text, re.M)) == 31


def test_elastodyn_template_is_the_rigid_iea22_rotor_at_the_rated_point():
    text = _text("_ElastoDyn.dat")
    for key in ("FlapDOF1", "FlapDOF2", "EdgeDOF", "GenDOF", "DrTrDOF", "YawDOF", "TwFADOF1", "PtfmSgDOF"):
        assert builder.get_value(text, key) == "False", key
    assert float(builder.get_value(text, "TipRad")) == 142.0
    assert float(builder.get_value(text, "HubRad")) == 4.2
    assert [float(builder.get_value(text, f"PreCone({i})")) for i in (1, 2, 3)] == [-4.0] * 3
    # no shaft tilt (owner decision 2026-11-02); hub stays at 170 m, overhang 14 m horizontal
    assert float(builder.get_value(text, "ShftTilt")) == 0.0
    assert float(builder.get_value(text, "OverHang")) == pytest.approx(-14.0)
    assert float(builder.get_value(text, "TowerHt")) + float(builder.get_value(text, "Twr2Shft")) == pytest.approx(170.0)
    assert float(builder.get_value(text, "RotSpeed")) == 6.853997
    assert [float(builder.get_value(text, f"BlPitch({i})")) for i in (1, 2, 3)] == [4.127462] * 3
    assert builder.get_value(text, "NumBl") == "3"
    inflow = _text("_InflowFile.dat")
    assert float(builder.get_value(inflow, "HWindSpeed")) == 11.134927
    assert float(builder.get_value(inflow, "RefHt")) == 170.0
    assert float(builder.get_value(inflow, "PLexp")) == 0.0


@needs_source
def test_templates_are_up_to_date_with_the_source_repository():
    result = subprocess.run([sys.executable, "-I", str(SCRIPTS / "build_openfast_templates.py"), "--check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "6/6 templates up to date" in result.stdout


def test_builder_check_fails_on_a_stale_template(tmp_path):
    if not (builder.DEFAULT_SOURCE / "OpenFAST").exists():
        pytest.skip("source repository not available")
    for path in TEMPLATES.iterdir():
        (tmp_path / path.name).write_text(path.read_text())
    stale = tmp_path / f"{ROOT}_OLAF.dat"
    stale.write_text(stale.read_text().replace("WingRegFactor", "WingRegFactorX"))
    result = subprocess.run([sys.executable, "-I", str(SCRIPTS / "build_openfast_templates.py"), "--check", "--out", str(tmp_path)],
                            capture_output=True, text=True)
    assert result.returncode == 1


def test_olaf_sizing_follows_the_guideline_at_the_rated_point():
    size = builder.olaf_sizing(builder.RATED_RPM, builder.RATED_U)
    assert size["dt"] == pytest.approx(60.0 / builder.RATED_RPM / 60.0)  # 6 deg per step
    assert size["near"] == 1399 and size["free"] == 699
    assert size["near"] * 0.5 * builder.RATED_U * size["dt"] >= 4 * 284.0  # >= 4 D
    olaf = _text("_OLAF.dat")
    assert int(builder.get_value(olaf, "nNWPanel")) == 1399
    assert int(builder.get_value(olaf, "nNWPanelsFree")) == 699


# --- case writer -----------------------------------------------------------------
def test_make_case_bem_and_olaf_time_steps():
    bem = runner.make_case("bem", 11.134927, 6.853997, 4.127462, revs=4)
    assert bem["dt"] == pytest.approx(bem["period_s"] / 72)
    assert bem["tmax"] == pytest.approx(4 * bem["period_s"])
    olaf = runner.make_case("olaf", 11.134927, 6.853997, 4.127462, revs=4)
    assert olaf["nNWPanels"] == olaf["guideline_panels"] == 1399
    assert olaf["wake_length_m"] >= 4 * 284.0 and olaf["wake_revolutions"] >= 10
    assert olaf["tmax"] == pytest.approx((1399 + 4 * 60) * olaf["dt"])
    smoke = runner.make_case("olaf", 11.134927, 6.853997, 4.127462, revs=2, olaf_panels=120, olaf_free=60)
    assert (smoke["nNWPanels"], smoke["nNWPanelsFree"]) == (120, 60)
    with pytest.raises(ValueError):
        runner.make_case("bogus", 1, 1, 0)


def test_write_case_rewrites_the_operating_point_and_options(tmp_path):
    case = runner.make_case("olaf", 9.0, 6.0, 1.5, revs=2, tower=False, tilt=False, olaf_panels=100, olaf_free=50, name="c")
    directory = runner.write_case(case, tmp_path, stage=False)
    ed = (directory / f"{ROOT}_ElastoDyn.dat").read_text()
    assert float(builder.get_value(ed, "RotSpeed")) == 6.0
    assert float(builder.get_value(ed, "BlPitch(2)")) == 1.5
    assert float(builder.get_value(ed, "ShftTilt")) == 0.0
    assert float(builder.get_value((directory / f"{ROOT}_InflowFile.dat").read_text(), "HWindSpeed")) == 9.0
    ad = (directory / f"{ROOT}_AeroDyn15.dat").read_text()
    assert builder.get_value(ad, "Wake_Mod") == "3"
    assert [builder.get_value(ad, k) for k in ("TwrPotent", "TwrShadow", "TwrAero")] == ["0", "0", "False"]
    olaf = (directory / f"{ROOT}_OLAF.dat").read_text()
    assert (builder.get_value(olaf, "nNWPanel"), builder.get_value(olaf, "nNWPanelsFree")) == ("100", "50")
    fst = (directory / f"{ROOT}.fst").read_text()
    assert float(builder.get_value(fst, "DT")) == pytest.approx(case["dt"], abs=1e-6)
    assert json.loads((directory / "case.json").read_text())["wake"] == "olaf"


def test_write_case_default_has_no_tilt_keeps_tower_and_bem(tmp_path):
    directory = runner.write_case(runner.make_case("bem", 11.134927, 6.853997, 4.127462, name="d"), tmp_path, stage=False)
    ed = (directory / f"{ROOT}_ElastoDyn.dat").read_text()
    assert float(builder.get_value(ed, "ShftTilt")) == 0.0
    assert float(builder.get_value(ed, "OverHang")) == pytest.approx(-14.0)
    assert json.loads((directory / "case.json").read_text())["tilt"] is False
    ad = (directory / f"{ROOT}_AeroDyn15.dat").read_text()
    assert (builder.get_value(ad, "Wake_Mod"), builder.get_value(ad, "TwrAero")) == ("1", "True")


def test_sweep_cases_pick_the_nearest_table_row():
    table = [(6.0, 0.0, 5.0), (11.1, 4.1, 6.85), (20.0, 15.0, 6.85)]
    cases = runner.sweep_cases(table, "bem", (6.2, 11.0, 25.0))
    assert [(c["U"], c["pitch"], c["rpm"]) for c in cases] == [(6.0, 0.0, 5.0), (11.1, 4.1, 6.85), (20.0, 15.0, 6.85)]


def test_staging_refuses_a_source_that_is_not_the_recorded_commit(tmp_path):
    base = tmp_path / "OpenFAST" / "IEA-22-280-RWT"
    (base / "Airfoils").mkdir(parents=True)
    (base / "IEA-22-280-RWT_AeroDyn15_blade.dat").write_text("tampered")
    (base / "IEA-22-280-RWT_ElastoDyn_blade.dat").write_text("tampered")
    case = tmp_path / "case"
    case.mkdir()
    with pytest.raises(SystemExit, match="sha256 mismatch"):
        runner.stage_inputs(case, tmp_path)


# --- extraction -----------------------------------------------------------------
def _write_out(case_dir: Path, power_kw=20000.0, thrust_kn=3000.0, t_end=36.0, dt=0.5):
    n = 59
    names = ["Time", "RtAeroPwr", "RtAeroFxh", "RtAeroCp", "RtAeroCt", "RtArea"]
    units = ["(s)", "(kW)", "(kN)", "(-)", "(-)", "(m^2)"]
    for node in range(1, n + 1):
        for q, u in (("Alpha", "(deg)"), ("Cn", "(-)"), ("Ct", "(-)")):
            names.append(f"AB1N{node:03d}{q}")
            units.append(u)
    lines = ["Predictions were generated on today", "", "", "", "", "", "\t".join(names), "\t".join(units)]
    t = 0.0
    while t <= t_end + 1e-9:
        row = [t, power_kw, thrust_kn, 0.45, 0.63, 62610.0]
        for node in range(1, n + 1):
            row += [float(node), 0.5 + 0.01 * node, 0.01 * node]
        lines.append("\t".join(f"{v:.7e}" for v in row))
        t += dt
    (case_dir / f"{ROOT}.out").write_text("\n".join(lines) + "\n")


def test_extract_converts_units_and_normalises_with_r_142(tmp_path):
    case = runner.make_case("bem", 11.134927, 6.853997, 4.127462, name="e")
    directory = tmp_path / "e"
    directory.mkdir()
    (directory / "case.json").write_text(json.dumps(case))
    _write_out(directory)
    metrics = runner.extract(directory)
    assert metrics["power_w"] == pytest.approx(20.0e6)
    assert metrics["thrust_n"] == pytest.approx(3.0e6)
    q = 0.5 * 1.225 * 11.134927 ** 2
    area = 3.141592653589793 * 142.0 ** 2
    assert metrics["cp"] == pytest.approx(20.0e6 / (q * 11.134927 * area))
    assert metrics["ct"] == pytest.approx(3.0e6 / (q * area))
    assert metrics["tip_speed_ratio"] == pytest.approx(9.1532, abs=1e-4)
    assert metrics["converged"] is True
    rows = list(csv.DictReader((directory / "spanwise.csv").open()))
    assert len(rows) == 59
    assert float(rows[0]["r_over_R"]) == pytest.approx(0.02957746479)
    assert float(rows[-1]["r_over_R"]) == 1.0 and float(rows[-1]["radius_m"]) == 142.0
    assert float(rows[58]["Alpha"]) == pytest.approx(59.0) and float(rows[58]["Cn"]) == pytest.approx(0.5 + 0.59)


def test_olaf_short_wake_is_never_converged(tmp_path):
    case = runner.make_case("olaf", 11.134927, 6.853997, 4.127462, revs=2, olaf_panels=120, olaf_free=60, name="o")
    directory = tmp_path / "o"
    directory.mkdir()
    (directory / "case.json").write_text(json.dumps(case))
    _write_out(directory, t_end=case["tmax"], dt=case["dt"])
    metrics = runner.extract(directory)
    assert metrics["wake_filled"] is True and metrics["guideline_wake"] is False
    assert metrics["converged"] is False


def test_extract_flags_a_drifting_power(tmp_path):
    case = runner.make_case("bem", 11.134927, 6.853997, 4.127462, name="f")
    directory = tmp_path / "f"
    directory.mkdir()
    (directory / "case.json").write_text(json.dumps(case))
    _write_out(directory)
    text = (directory / f"{ROOT}.out").read_text().splitlines()
    head, body = text[:8], text[8:]
    drift = [l.split("\t") for l in body]
    for k, row in enumerate(drift):
        if float(row[0]) > 36.0 - case["period_s"]:
            row[1] = f"{22000.0:.7e}"
    (directory / f"{ROOT}.out").write_text("\n".join(head + ["\t".join(r) for r in drift]) + "\n")
    metrics = runner.extract(directory, revs=1)
    assert metrics["power_change_last_rev_pct"] > 1.0 and metrics["converged"] is False


# --- table plausibility ------------------------------------------------------------
TABLE = """# header
# Pitch angle vector, 2 entries - x axis (matrix columns) (deg)
0.0 10.0
# TSR vector, 2 entries - y axis (matrix rows) (-)
2.0 4.0
# Wind speed vector - z axis (m/s)
11.14

# Power coefficient

0.1 0.2
0.3 0.4

#  Thrust coefficient

1.0 2.0
3.0 4.0

# Torque coefficient

0.0 0.0
0.0 0.0
"""


def test_table_reader_and_bilinear_interpolation(tmp_path):
    path = tmp_path / "t.txt"
    path.write_text(TABLE)
    table = table_check.read_table(path)
    assert table["pitch"] == [0.0, 10.0] and table["tsr"] == [2.0, 4.0]
    assert table["cp"] == [[0.1, 0.2], [0.3, 0.4]] and table["ct"] == [[1.0, 2.0], [3.0, 4.0]]
    assert table_check.bilinear(table["pitch"], table["tsr"], table["cp"], 5.0, 3.0) == pytest.approx(0.25)
    assert table_check.bilinear(table["pitch"], table["tsr"], table["cp"], 0.0, 4.0) == pytest.approx(0.3)
    assert table_check.bilinear(table["pitch"], table["tsr"], table["cp"], 99.0, 99.0) == pytest.approx(0.4)  # clamped


def test_table_check_exit_status_follows_the_tolerance(tmp_path):
    table = tmp_path / "t.txt"
    table.write_text(TABLE)
    metrics = tmp_path / "metrics.json"
    metrics.write_text(json.dumps({"U": 11.1, "rpm": 6.8, "pitch": 5.0, "tip_speed_ratio": 3.0, "wake": "bem", "cp": 0.25, "ct": 2.5}))
    assert table_check.main([str(metrics), "--table", str(table)]) == 0
    metrics.write_text(json.dumps({"U": 11.1, "rpm": 6.8, "pitch": 5.0, "tip_speed_ratio": 3.0, "wake": "bem", "cp": 0.40, "ct": 2.5}))
    assert table_check.main([str(metrics), "--table", str(table)]) == 1


# --- importer ---------------------------------------------------------------------
def _imported_case(tmp_path, wake="bem", converged=True):
    case = runner.make_case(wake, 11.134927, 6.853997, 4.127462, name="i", **({"olaf_panels": 1400, "olaf_free": 700} if wake == "olaf" else {}))
    directory = tmp_path / "i"
    directory.mkdir()
    (directory / "case.json").write_text(json.dumps(case))
    (directory / "metrics.json").write_text(json.dumps({
        "U": 11.134927, "rpm": 6.853997, "pitch": 4.127462, "tower": True, "tilt": True, "revolutions_averaged": 1.0, "converged": converged}))
    with (directory / "spanwise.csv").open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["node", "r_over_R", "radius_m", "Alpha", "Cn", "Ct"])
        for node in range(1, 60):
            writer.writerow([node, node / 59, node * 142 / 59, node, 0.5, 0.05])
    return directory


def test_importer_writes_a_block_idempotently_and_keeps_foreign_rows(tmp_path):
    directory = _imported_case(tmp_path)
    store = tmp_path / "store.csv"
    foreign = "ccblade-bem,cn,0.5,0.9,-,\"keep, me\"\n"
    store.write_text("source,quantity,r_over_R_or_radius_m,value,unit,note\n" + foreign)
    assert importer.main([str(directory), "--source", "openfast-bem", "--store", str(store)]) == 0
    once = store.read_text()
    assert importer.main([str(directory), "--source", "openfast-bem", "--store", str(store)]) == 0
    assert store.read_text() == once
    rows = list(csv.reader(store.open()))
    assert rows[1] == ["ccblade-bem", "cn", "0.5", "0.9", "-", "keep, me"]
    block = [r for r in rows if r[0] == "openfast-bem"]
    assert len(block) == 177 and {r[1] for r in block} == {"alpha_deg", "cn", "ct"}
    assert "V=11.1349 m/s" in block[0][5] and "AeroDyn BEMT" in block[0][5]


def test_importer_refuses_smoke_runs_and_wrong_wake(tmp_path, capsys):
    store = tmp_path / "store.csv"
    smoke = _imported_case(tmp_path, wake="olaf", converged=False)
    assert importer.main([str(smoke), "--source", "olaf-fvw", "--store", str(store)]) == importer.EXIT_UNCONVERGED
    assert not store.exists()
    assert importer.main([str(smoke), "--source", "olaf-fvw", "--store", str(store), "--allow-unconverged"]) == 0
    assert "1400 near-wake panels" in store.read_text()
    assert importer.main([str(smoke), "--source", "openfast-bem", "--store", str(store), "--allow-unconverged"]) == importer.EXIT_UNCONVERGED


def test_importer_does_not_change_the_iea15_importer_constants(tmp_path):
    iea15 = _load("iea15_importer_unchanged", importer.IEA15_IMPORTER)
    importer.refresh(_imported_case(tmp_path, "bem"), "openfast-bem", tmp_path / "s.csv")
    assert iea15.SOURCE == "olaf-fvw" and "IEA-15" in iea15.NOTE


# --- command line ---------------------------------------------------------------------
@pytest.mark.parametrize("script", ["build_openfast_templates.py", "openfast_iea22.py", "rated_table_check.py", "import_olaf_reference.py"])
def test_help_exits_zero(script):
    result = subprocess.run([sys.executable, "-I", str(SCRIPTS / script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0 and "usage" in result.stdout.lower()


def test_tilt_is_an_explicit_opt_in_with_consistent_hub_geometry(tmp_path):
    case = runner.make_case("bem", 11.134927, 6.853997, 4.127462, tilt=True, name="t")
    ed = (runner.write_case(case, tmp_path, stage=False) / f"{ROOT}_ElastoDyn.dat").read_text()
    tilt = float(builder.get_value(ed, "ShftTilt"))
    overhang = float(builder.get_value(ed, "OverHang"))
    assert tilt == pytest.approx(-6.0)
    assert float(builder.get_value(ed, "TowerHt")) + float(builder.get_value(ed, "Twr2Shft")) + abs(overhang) * math.sin(math.radians(6.0)) == pytest.approx(170.0, abs=1e-3)
    assert overhang * math.cos(math.radians(6.0)) == pytest.approx(-14.0, abs=1e-3)


def test_cli_tilt_flag(tmp_path):
    assert runner.main(["setup", str(tmp_path), "--wake", "bem", "--name", "a"]) == 0
    assert runner.main(["setup", str(tmp_path), "--wake", "bem", "--tilt", "--name", "b"]) == 0
    tilt = lambda n: float(builder.get_value((tmp_path / n / f"{ROOT}_ElastoDyn.dat").read_text(), "ShftTilt"))
    assert (tilt("a"), tilt("b")) == (0.0, pytest.approx(-6.0))


@pytest.mark.skipif(not (builder.DEFAULT_SOURCE / "OpenFAST").exists(), reason="IEA-22 source repository not available")
def test_tilted_opt_in_values_are_the_source_values():
    src = (builder.DEFAULT_SOURCE / "OpenFAST/IEA-22-280-RWT-Monopile/IEA-22-280-RWT_ElastoDyn.dat").read_text()
    for key, value in builder.TILTED_ED.items():
        assert float(builder.get_value(src, key)) == pytest.approx(float(value), rel=1e-12), key
