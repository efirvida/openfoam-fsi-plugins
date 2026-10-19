# SPDX-License-Identifier: GPL-3.0-or-later
"""Deterministic offline element-residual diagnostics."""
import math
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]/"validation"/"phaseVI"/"scripts"
sys.path.insert(0, str(SCRIPTS))

from diagnoseElementResiduals import (  # noqa: E402
    bracket, element_data, glauert_factor, normalisation_ratio, polar_cl, station_values,
)


def test_glauert_hand_value():
    # B=2, rootDist=1/2, sin(phi)=1/2: exponent=-2.
    expected = 2 / math.pi * math.acos(math.exp(-2))
    assert glauert_factor(0.5, math.pi / 6) == pytest.approx(expected)
    assert glauert_factor(1.0, math.pi / 6) == 0.0
    hub = 2 / math.pi * math.acos(math.exp(-2 * (2.75 - 0.5) / 0.5))
    assert glauert_factor(0.5, math.pi / 6, root_effects=True,
                          radius=5.0, cut=0.5) == pytest.approx(expected * hub)


def test_bracket_and_station_interpolation():
    profile = [(0.29, 1.0, 0.8), (0.31, 3.0, 0.6), (0.96, 7.0, 0.2)]
    assert bracket(profile, 0.30) == (profile[0], profile[1])
    assert station_values(profile, 0.30) == pytest.approx((2.0, 0.7))
    assert bracket(profile, 0.95) == (profile[1], profile[2])
    assert station_values(profile, 0.29) == pytest.approx((1.0, 0.8))
    with pytest.raises(ValueError, match="outside element span"):
        bracket(profile, 0.99)


def test_element_reader_reuses_rowwise_chord_frame(tmp_path):
    directory = tmp_path / "postProcessing/actuatorLineElements/0"
    directory.mkdir(parents=True)
    # A non-binary root distance catches inconsistent radius mean arithmetic.
    header = "time,root_dist,cl,cd,alpha_deg,c_ref_n,c_ref_t,rel_vel_mag,end_effect_factor\n"
    rows = "".join(f"{i},0.2041234567,1,0,0,1,0,10,0.5\n" for i in range(15))
    (directory / "turbine.blade1.element12.csv").write_text(header + rows)
    profile, samples = element_data(tmp_path, 0, 14)
    assert len(profile) == 1
    assert profile[0][1:] == pytest.approx((1, 0, 0, 0.5, 1, 10, 0, 2))
    assert samples[profile[0][0]][0] == 12


@pytest.mark.parametrize("root_effects", [False, True])
def test_glauert_lag_from_consecutive_end_effect_angles(tmp_path, capsys, root_effects):
    """The factor written at step t used the angle sampled at t-1; the angle
    stored at t+1 is the one sampled at t, with the same definition."""
    import diagnoseElementResiduals as diagnostic

    directory = tmp_path / "postProcessing/actuatorLineElements/0"
    directory.mkdir(parents=True)
    header = "time,root_dist,cl,cd,alpha_deg,c_ref_n,c_ref_t,rel_vel_mag,end_effect_factor,end_effect_phi_deg\n"
    # Out-of-window rows (0 and 4) and an inboard element must not enter (b).
    for number, root_dist in ((12, 0.2), (45, 0.9)):
        rows = "".join(
            f"{time},{root_dist},1,0,0,1,0,10,{factor},{phi}\n"
            for time, factor, phi in ((0, 0.1, 80), (1, 0.4, 30), (2, 0.6, 50), (3, 0.5, 40), (4, 0.1, 80)))
        (directory / f"turbine.blade1.element{number}.csv").write_text(header + rows)
    before = {p: p.read_bytes() for p in directory.iterdir()}
    _, samples = element_data(tmp_path, 1, 3)
    diagnostic.report_glauert_lag(samples, 2, root_effects)
    same_step = sum(glauert_factor(0.9, math.radians(phi), 2, root_effects) for phi in (50, 40)) / 2
    rr = diagnostic.comparison.r_over_r_from_root_dist(0.9, diagnostic.R)
    assert capsys.readouterr() == (
        "  element  r/R       lag_mean[deg] F_same_step F_written delta_F\n"
        f"  element45 {rr:.6f}      -5.000000 {same_step:.6f} 0.500000 "
        f"{same_step - 0.5:+.6f}\n", "")
    assert {p: p.read_bytes() for p in directory.iterdir()} == before


def test_glauert_lag_legacy_csv_still_skipped(tmp_path, capsys):
    import diagnoseElementResiduals as diagnostic

    directory = tmp_path / "postProcessing/actuatorLineElements/0"
    directory.mkdir(parents=True)
    values = dict(time=1, root_dist=0.9, cl=1, cd=0, alpha_deg=0,
                  c_ref_n=1, c_ref_t=0, rel_vel_mag=10, end_effect_factor=0.5)
    (directory / "turbine.blade1.element45.csv").write_text(
        ",".join(values) + "\n" + ",".join(map(str, values.values())) + "\n")
    _, samples = element_data(tmp_path, 0, 2)
    diagnostic.report_glauert_lag(samples, 2, False)
    assert capsys.readouterr() == (
        "  SKIPPED: CSV exposes rel_vel_mag, but no relative-velocity vector/components.\n"
        "  Cannot obtain atan2(W_axis, W_opposite_element_velocity) from magnitude alone.\n"
        "  No mean/max relative difference claimed; recovered force angle is not sampled velocity.\n", "")


def test_glauert_lag_uncomputed_angle_is_explicit(capsys):
    import diagnoseElementResiduals as diagnostic

    diagnostic.report_glauert_lag({0.9: (45, [
        dict(time=1, end_effect_phi_deg=math.nan, end_effect_factor=1, root_dist=0.9),
        dict(time=2, end_effect_phi_deg=math.nan, end_effect_factor=1, root_dist=0.9)])}, 2, False)
    assert capsys.readouterr() == (
        "  element  r/R       lag_mean[deg] F_same_step F_written delta_F\n"
        "  element45 0.900000 SKIPPED: non-finite end-effect angle or factor.\n", "")


def test_element_csv_appends_angles_without_changing_existing_columns():
    import re

    source = (SCRIPTS.parents[2] / "src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorLineElement.C").read_text()
    header_block = source.split('*outputFile_<< "time,root_dist', 1)[1].split('<< endl;', 1)[0]
    header = "time,root_dist" + "".join(re.findall(r'"([^"\n]*)"', '"' + header_block))
    assert header == ("time,root_dist,x,y,z,rel_vel_mag,Re,alpha_deg,alpha_geom_deg,"
                      "cl,cd,fx,fy,fz,end_effect_factor,c_ref_t,c_ref_n,f_ref_t,f_ref_n,"
                      "end_effect_phi_deg,inflow_ref_angle_deg")


@pytest.mark.parametrize("directory", [None, "reference-fixture"])
def test_experiment_directory_pass_through(monkeypatch, directory):
    import diagnoseElementResiduals as diagnostic

    monkeypatch.setattr(diagnostic, "converged_window", lambda *a, **k: (0, 1, {}))
    seen = []

    class Stop(Exception):
        pass

    def read(directory, speed, sequence):
        seen.append((Path(directory), speed, sequence))
        return {}

    def density(directory, speed, sequence):
        seen.append((Path(directory), speed, sequence))
        raise Stop

    monkeypatch.setattr(diagnostic, "read_experiment", read)
    monkeypatch.setattr(diagnostic, "read_density", density)
    argv = ["--sequence", "S", "--speed", "6"]
    if directory is not None:
        argv += ["--experiment-dir", directory]
    with pytest.raises(Stop):
        diagnostic.main(argv)
    expected = Path(directory) if directory else SCRIPTS.parent / "data/experiment"
    assert seen == [(expected, 6.0, "S")] * 2


def test_normalisation_ratio():
    assert normalisation_ratio(104.0, 1.3, 10.0) == pytest.approx(1.6)


def test_polar_cl_between_rows(tmp_path):
    polar = tmp_path / "polar.dat"
    polar.write_text("// (alpha cl cd cm)\n(0 0.1 0.01 0)\n(10 1.1 0.02 0)\n")
    assert polar_cl(polar, 2.5) == pytest.approx(0.35)


@pytest.mark.parametrize("argv, expected", [
    ([], (None, False, False)),
    (["--revolutions", "2", "4", "--allow-drift", "--allow-short-window"], ((2, 4), True, True)),
])
def test_window_options_pass_through_to_convergence_gate(monkeypatch, argv, expected):
    """--revolutions/--allow-drift/--allow-short-window reach
    compareSectionLoads.converged_window unchanged; the default keeps the
    configured window and both refusals."""
    import diagnoseElementResiduals as diagnostic

    seen = {}

    class Stop(Exception):
        pass

    def gate(run_dir, speed, sequence, revolutions=None, allow_drift=False,
             allow_short_window=False):
        seen["window"] = (None if revolutions is None else tuple(revolutions), allow_drift,
                          allow_short_window)
        raise Stop

    monkeypatch.setattr(diagnostic, "converged_window", gate)
    with pytest.raises(Stop):
        diagnostic.main(["--alm-dir", "unused"] + argv)
    assert seen["window"] == expected


def test_window_header_reports_measured_drift(tmp_path, monkeypatch, capsys):
    """The header prints the gate's window and drift verdict, never a hard-coded False."""
    import diagnoseElementResiduals as diagnostic

    info = {"discard_revolutions": 2, "end_revolutions": 4, "drift": {"flag": True}}
    monkeypatch.setattr(diagnostic, "converged_window", lambda *a, **k: (1.0, 2.0, info))
    monkeypatch.setattr(diagnostic, "element_data", lambda *a: ([], {}))
    (tmp_path / "system").mkdir()
    (tmp_path / "system/fvOptions").write_text("endEffectsModel Glauert;\n")

    class Stop(Exception):
        pass

    def stop(*_):
        raise Stop

    monkeypatch.setattr(diagnostic, "bracket", stop)  # first call after the header
    with pytest.raises(Stop):
        diagnostic.main(["--alm-dir", str(tmp_path), "--allow-drift", "--revolutions", "2", "4"])
    out = capsys.readouterr().out
    assert "window rev 2..4" in out
    assert "drift=True" in out
