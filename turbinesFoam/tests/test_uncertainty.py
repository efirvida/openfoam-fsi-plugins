# SPDX-License-Identifier: GPL-3.0-or-later
"""R6: every validation number carries its combined uncertainty."""

import copy
import csv
import math
import sys
from pathlib import Path

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "validation" / "phaseVI" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import comparePhaseVI
import quantifyUncertainty as qu

RHO = 1.2
SPEED = 7.0
ROOT_DISTS = (0.0, 0.25, 0.5, 0.75, 1.0)


def synthetic_run(tmp_path, sequence="H"):
    """Turbine and element CSVs whose cp, cd and cl ramp linearly with the revolution."""
    cfg = comparePhaseVI.load_config(comparePhaseVI.DEFAULT_CONFIG)
    _, _, period = comparePhaseVI.window_bounds(cfg, SPEED, sequence)
    tsr = float(comparePhaseVI.select_speed(cfg, SPEED, sequence)["tsr"])
    turbine = tmp_path / comparePhaseVI.TURBINE_CSV
    turbine.parent.mkdir(parents=True)
    fields = ("time", "tsr", "cp", "cd", "ct", "cd_blade1", "cd_blade2")
    with turbine.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for step in range(1301):
            rev = step / 100
            cp = 0.3 + 0.01 * rev
            cd = 0.8 + 0.02 * rev
            writer.writerow(dict(time=rev * period, tsr=tsr, cp=cp, cd=cd,
                                 ct=cp / tsr, cd_blade1=cd / 2, cd_blade2=cd / 2))
    element_dir = tmp_path / comparePhaseVI.ELEMENT_DIR
    element_dir.mkdir(parents=True)
    for index, root_dist in enumerate(ROOT_DISTS):
        with (element_dir / f"turbine.blade1.element{index}.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=(
                "time", "root_dist", "alpha_deg", "cl", "cd", "c_ref_n", "c_ref_t", "fx"))
            writer.writeheader()
            for step in range(1301):
                rev = step / 100
                writer.writerow(dict(time=rev * period, root_dist=root_dist, alpha_deg=0.0,
                                     cl=1.0 + 0.05 * rev, cd=0.0, c_ref_n=1.0, c_ref_t=0.1, fx=1.0))
    return cfg, period


def test_quadrature_sum_and_missing_terms():
    assert qu.quadrature(3.0, 4.0) == pytest.approx(5.0)
    assert qu.quadrature(3.0, None, 4.0, 12.0) == pytest.approx(13.0)
    assert qu.quadrature(0.0) == 0.0
    assert qu.quadrature(None, None) is None


def test_window_deviation_is_the_largest_departure_from_the_definition_window():
    values = {"4-12": 10.0, "6-12": 10.5, "8-12": 9.2}
    assert qu.window_deviation(values, "4-12") == pytest.approx(0.8)
    assert qu.window_deviation({"4-12": 10.0, "6-12": 10.0}, "4-12") == 0.0


def test_window_sensitivity_on_synthetic_ramp(tmp_path):
    cfg, _ = synthetic_run(tmp_path)
    before = (tmp_path / comparePhaseVI.TURBINE_CSV).read_bytes()
    result = qu.window_sensitivity(tmp_path, cfg, SPEED, "H", RHO, "blade")
    assert list(result["windows"]) == ["4-12", "6-12", "8-12"]
    area = math.pi * float(cfg["turbine"]["radius"]) ** 2
    q_dyn = 0.5 * RHO * area * SPEED**2
    # window means of a linear ramp are the mid-points: 8, 9 and 10 revolutions
    assert result["deviation"]["power"] == pytest.approx(0.01 * 2 * q_dyn * SPEED / 1e3, rel=1e-6)
    assert result["deviation"]["thrust"] == pytest.approx(0.02 * 2 * q_dyn, rel=1e-6)
    for station in ("0.30", "0.47", "0.63", "0.80", "0.95"):
        assert result["deviation"][f"cn{station}"] == pytest.approx(0.05 * 2, rel=1e-6)
    assert result["values"]["4-12"]["power"] == pytest.approx(
        (0.3 + 0.01 * 8) * q_dyn * SPEED / 1e3, rel=1e-6)
    assert (tmp_path / comparePhaseVI.TURBINE_CSV).read_bytes() == before
    # the caller's configuration is not left on a shifted window
    assert cfg["solver"]["discard_revolutions"] == 4


def test_window_ending_a_step_short_of_its_nominal_end_is_still_available(tmp_path):
    cfg, period = synthetic_run(tmp_path)
    path = tmp_path / comparePhaseVI.TURBINE_CSV
    kept = [line for line in path.read_text().splitlines()
            if not line.split(",")[0].replace(".", "").isdigit()
            or float(line.split(",")[0]) <= 12 * period - 1e-6]
    path.write_text("\n".join(kept) + "\n")
    for element in (tmp_path / comparePhaseVI.ELEMENT_DIR).glob("*.csv"):
        lines = element.read_text().splitlines()
        element.write_text("\n".join(
            line for line in lines
            if not line[0].isdigit() or float(line.split(",")[0]) <= 12 * period - 1e-6) + "\n")
    result = qu.window_sensitivity(tmp_path, cfg, SPEED, "H", RHO, "blade")
    assert result["unavailable"] == []
    assert list(result["windows"]) == ["4-12", "6-12", "8-12"]


def test_window_not_reached_is_reported_not_invented(tmp_path):
    cfg, _ = synthetic_run(tmp_path)
    cfg = copy.deepcopy(cfg)
    cfg["solver"]["discard_revolutions"] = 6
    cfg["solver"]["end_revolutions"] = 14
    result = qu.window_sensitivity(tmp_path, cfg, SPEED, "H", RHO, "blade")
    # the run holds 13 revolutions: 8-14 covers 5 of its 6, 10-14 only 3
    assert set(result["unavailable"]) == {"8-14", "10-14"}
    assert list(result["windows"]) == ["6-14"]


def ar1(phi, n, seed=3):
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n)
    x = np.empty(n)
    x[0] = noise[0] / math.sqrt(1 - phi**2)
    for index in range(1, n):
        x[index] = phi * x[index - 1] + noise[index]
    return x


def test_effective_sample_size_against_ar1_analytic_value():
    phi, n = 0.8, 200_000
    x = ar1(phi, n)
    analytic_tau = (1 + phi) / (1 - phi)
    assert qu.effective_sample_size(x) == pytest.approx(n / analytic_tau, rel=0.15)
    sigma_x = 1 / math.sqrt(1 - phi**2)
    analytic_sem = sigma_x * math.sqrt(analytic_tau / n)
    assert qu.standard_error(x) == pytest.approx(analytic_sem, rel=0.10)


def test_white_noise_has_full_sample_size_and_iid_error():
    x = np.random.default_rng(5).standard_normal(50_000)
    assert qu.effective_sample_size(x) == pytest.approx(50_000, rel=0.1)
    assert qu.standard_error(x) == pytest.approx(1 / math.sqrt(50_000), rel=0.1)


def test_effective_sample_size_never_exceeds_sample_count_or_drops_below_one():
    x = np.tile([1.0, -1.0], 500)  # perfectly anti-correlated
    assert qu.effective_sample_size(x) <= 1000
    assert qu.effective_sample_size(np.ones(10) + np.arange(10)) >= 1.0


def test_verdict_wording():
    inside = qu.verdict(0.8, 1.0)
    assert inside == "agrees within the combined numerical and experimental uncertainty"
    outside = qu.verdict(-1.5, 1.0)
    assert "agrees within" not in outside
    assert "outside the combined uncertainty" in outside
    assert qu.verdict(1.0, 1.0) == inside
    assert qu.verdict(1.5, 1.0, coverage=2.0) == inside
    incomplete = qu.verdict(0.1, 1.0, missing=["experiment repeatability"])
    assert "agrees within" not in incomplete
    assert "experiment repeatability" in incomplete


def write_point(path, power, n=2000, rpm=72.0, cn_offset=0.0, yaw=0.0):
    pa = pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq
    rng = np.random.default_rng(int(power * 1000))
    columns = {"err": np.full(n, 128, dtype="uint8"),
               "RPM": np.full(n, rpm, dtype="float32"),
               "ROTPOW": (power + 0.05 * rng.standard_normal(n)).astype("float32"),
               "EAEROTH": np.full(n, 1000.0, dtype="float32"),
               "YAW": np.full(n, yaw, dtype="float32"),
               "VTUN": np.full(n, 7.05, dtype="float32")}
    for station in ("30", "47", "63", "80", "95"):
        columns[f"CN{station}"] = np.full(n, 0.8 + cn_offset, dtype="float32")
    pq.write_table(pa.table(columns), str(path))


def test_repeatability_uses_file_to_file_scatter_when_repeats_exist(tmp_path):
    write_point(tmp_path / "uae6.z07.00.h0700000.parquet", 6.0)
    write_point(tmp_path / "uae6.z07.00.h0700001.parquet", 6.2, cn_offset=0.01)
    result = qu.experiment_repeatability(tmp_path, "H", 7)
    power = result["power"]
    assert power["method"].startswith("file-to-file")
    assert power["files"] == ["h0700000", "h0700001"]
    assert power["u"] == pytest.approx(0.2 / math.sqrt(2), rel=0.02)
    assert result["cn0.30"]["u"] == pytest.approx(0.01 / math.sqrt(2), rel=0.02)
    assert result["thrust"]["u"] == pytest.approx(0.0, abs=1e-6)


def test_repeatability_excludes_files_whose_measured_yaw_is_not_zero(tmp_path):
    write_point(tmp_path / "uae6.z07.00.h0700000.parquet", 6.0)
    write_point(tmp_path / "uae6.z07.00.h0700001.parquet", 9.0, yaw=2.0)
    power = qu.experiment_repeatability(tmp_path, "H", 7)["power"]
    assert power["files"] == ["h0700000"]
    assert power["method"].startswith("in-file")


def test_repeatability_single_file_falls_back_to_in_file_standard_error(tmp_path):
    write_point(tmp_path / "uae6.z07.00.h0700000.parquet", 6.0, n=15625)
    power = qu.experiment_repeatability(tmp_path, "H", 7)["power"]
    assert power["method"].startswith("in-file")
    assert power["files"] == ["h0700000"]
    assert 0.0 < power["u"] < 0.01


def test_repeatability_not_available_names_the_searched_path(tmp_path):
    result = qu.experiment_repeatability(tmp_path / "missing", "H", 7)
    assert result["power"]["u"] is None
    assert "not available" in result["power"]["method"]
    assert str(tmp_path / "missing") in result["power"]["method"]


def test_blockage_sensitivity_is_bem_estimate_with_ordered_increments():
    result = qu.blockage_sensitivity(rpm=71.88, rho=1.2337, speed=7.0, pitch=3.0)
    assert result["label"] == "BEM-estimated blockage sensitivity"
    one, two = result["relative"][0.01], result["relative"][0.02]
    assert 0.0 < one["power"] < two["power"]
    assert 0.0 < one["thrust"] < two["thrust"]
    assert two["power"] < 1.03**3 - 1.0 and two["power"] > 0.02
    assert set(f"cn{s}" for s in ("0.30", "0.47", "0.63", "0.80", "0.95")) <= set(two)


def test_blockage_bound_fallback_is_u3_and_u2():
    result = qu.blockage_bound((0.01, 0.02))
    assert "bound" in result["label"]
    assert result["relative"][0.02]["power"] == pytest.approx(1.02**3 - 1.0)
    assert result["relative"][0.02]["thrust"] == pytest.approx(1.02**2 - 1.0)
    assert "cn0.30" not in result["relative"][0.02]


def test_nonconforming_run_is_refused_unless_allowed(tmp_path, capsys):
    synthetic_run(tmp_path)
    args = ["--run-dir", str(tmp_path), "--sequence", "H", "--speed", "7",
            "--archive-dir", str(tmp_path / "no-archive")]
    assert qu.main(args) == 1
    out = capsys.readouterr().out
    assert "NON-CONFORMING" in out and "NOT OF RECORD" in out
    assert "sim - exp" not in out


def test_report_for_run_with_allow_nonconforming(tmp_path, capsys, monkeypatch):
    synthetic_run(tmp_path)
    monkeypatch.setattr(qu, "check_run", lambda run, definition: ["polar=x (expected y)"])
    args = ["--run-dir", str(tmp_path), "--sequence", "H", "--speed", "7",
            "--archive-dir", str(tmp_path / "no-archive"), "--allow-nonconforming"]
    assert qu.main(args) == 0
    out = capsys.readouterr().out
    assert "[not of record]" in out
    assert "sim - exp" in out
    assert "not available" in out and str(tmp_path / "no-archive") in out
    assert "BEM-estimated blockage sensitivity" in out
    # repeatability missing: the claim of agreement is withheld
    assert "agrees within" not in out


def test_combine_uses_largest_blockage_magnitude_and_names_the_dominant_term():
    sim = {q: 1.0 for q in qu.QUANTITIES}
    exp = {q: 2.0 for q in qu.QUANTITIES}
    repeatability = {q: {"u": 0.02} for q in qu.QUANTITIES}
    relative = {0.01: {q: 0.01 for q in qu.QUANTITIES}, 0.02: {q: 0.005 for q in qu.QUANTITIES}}
    relative[0.02]["power"] = 0.03
    del relative[0.02]["thrust"], relative[0.01]["thrust"]
    window = {"deviation": {q: 0.01 for q in qu.QUANTITIES}}
    rows = qu.combine(sim, exp, repeatability, {"relative": relative}, window, 1.0)
    cn = rows["cn0.30"]
    assert cn["blk"] == pytest.approx(0.01 * 2.0)  # the +1 % magnitude exceeds the +2 % one
    assert cn["combined"] == pytest.approx(math.sqrt(0.02**2 + 0.02**2 + 0.01**2))
    assert cn["difference"] == -1.0 and "agrees within" not in cn["verdict"]
    assert rows["power"]["dominant"] == "blockage"
    assert rows["thrust"]["blk"] is None and rows["thrust"]["missing"] == ["blockage"]
    assert "blockage" in rows["thrust"]["verdict"]
