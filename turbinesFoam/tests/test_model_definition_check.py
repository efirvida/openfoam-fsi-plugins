# SPDX-License-Identifier: GPL-3.0-or-later
"""Public-interface tests for Phase VI definition conformance and judging."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1] / "validation/phaseVI"
CHECK = ROOT / "scripts/checkModelDefinition.py"
SUMMARY = ROOT / "scripts/summarizeBands.py"
POLAR = "data/polars/S809_OSU_Re1M_pressure.dat"


def invoke(script, *args):
    return subprocess.run([sys.executable, str(script), *map(str, args)],
                          capture_output=True, text=True,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


def make_run(tmp_path, twin="ALM", old=None, new=None, metadata=None, name="run"):
    run = tmp_path / name
    (run / "system").mkdir(parents=True)
    text = (ROOT / f"case/system/fvOptions.{twin}").read_text()
    if old is not None:
        assert old in text
        text = text.replace(old, new)
    (run / "system/fvOptions").write_text(text)
    if metadata is not None:
        (run / "run.json").write_text(json.dumps(metadata))
    return run


@pytest.mark.parametrize("twin", ["ALM", "ASM", "ASM-MESH"])
def test_committed_renders_conform(tmp_path, twin):
    run = make_run(tmp_path, twin)
    result = invoke(CHECK, run)
    assert (result.returncode, result.stdout, result.stderr) == (
        0, f"{run}: CONFORMS v1.2\n", "")


@pytest.mark.parametrize("old,new,mismatch", [
    ("tipEffects on;", "tipEffects off;", "tipEffects=off (expected on)"),
    ("tipCorrection\n        {\n            active off;",
     "tipCorrection\n        {\n            active on;",
     "tipCorrection.active=on (expected off)"),
    ("S809_OSU_Re1M_pressure.dat", "S809_OSU_Re1M_total.dat",
     f"polar=../../data/polars/S809_OSU_Re1M_total.dat (expected suffix {POLAR})"),
    ("meshFactor 1;", "meshFactor 2;", "meshFactor=2 (expected 1)"),
    ("hubRadius 0.5083;", "", "hubRadius=-VGREAT (expected 0.5083)"),
    ("endEffectsModel Glauert;", "", "endEffectsModel=ABSENT (no solver default known)"),
    ("azimuthalOffset 0;", "azimuthalOffset 0; velocitySampleRadius 3.3;",
     "velocitySampleRadius=3.3 (expected 0)"),
    ("liftReCorrExp 0;", "", "liftReCorrExp=0.23 (expected 0)"),
    ("dynamicStall\n        {\n            active off;",
     "dynamicStall\n        {\n            active on;",
     "dynamicStall.active=on (expected off)"),
    ("rotationalAugmentation\n        {\n            active off;",
     "rotationalAugmentation\n        {\n            active on;",
     "rotationalAugmentation.active=on (expected off)"),
    ("elementType actuatorLineElement;", "elementType actuatorLineElement; addedMass true;",
     "addedMass=true (expected off)"),
])
def test_exact_mismatch_and_no_mutation(tmp_path, old, new, mismatch):
    run = make_run(tmp_path, old=old, new=new)
    before = (run / "system/fvOptions").read_bytes()
    result = invoke(CHECK, run)
    assert (result.returncode, result.stdout, result.stderr) == (
        1, f"{run}: NON-CONFORMING v1.2: {mismatch}\n", "")
    assert (run / "system/fvOptions").read_bytes() == before


@pytest.mark.parametrize("metadata,name", [({"refine_level": 1}, "run"),
                                           ({}, "alm-U7-coarse-r1-label")])
def test_refinement_scaling(tmp_path, metadata, name):
    run = make_run(tmp_path, old="meshFactor 1;", new="meshFactor 2;",
                   metadata=metadata, name=name)
    result = invoke(CHECK, run)
    assert (result.returncode, result.stdout, result.stderr) == (
        0, f"{run}: CONFORMS v1.2\n", "")


def test_all_mismatches_and_public_function(tmp_path):
    run = make_run(tmp_path, old="tipEffects on;", new="tipEffects off;",
                   metadata={"blade_dz": 0.1})
    spec = importlib.util.spec_from_file_location("definition_check", CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.check_run(run, module.load_definition()) == [
        "tipEffects=off (expected on)", "blade_dz=0.1 (expected 0.05)"]


def test_surface_strip_count(tmp_path):
    run = make_run(tmp_path, twin="ASM", old="nChordwise 5;", new="nChordwise 7;")
    result = invoke(CHECK, run)
    assert (result.returncode, result.stdout, result.stderr) == (
        1, f"{run}: NON-CONFORMING v1.2: nChordwise=7 (expected 5)\n", "")


def test_explicit_defaults_comments_and_inert_sample_count(tmp_path):
    run = make_run(tmp_path, old="azimuthalOffset 0;",
                   new='azimuthalOffset 0; /* ignored { ; } */ velocitySampleRadius 0;\n'
                       '        nVelocitySamples 999; // inert\n')
    result = invoke(CHECK, run)
    assert (result.returncode, result.stdout, result.stderr) == (
        0, f"{run}: CONFORMS v1.2\n", "")


def test_unreadable_input(tmp_path):
    result = invoke(CHECK, tmp_path / "missing")
    assert result.returncode == 2
    assert result.stdout == ""
    assert "error:" in result.stderr


def test_definition_override(tmp_path):
    run = make_run(tmp_path)
    definition = tmp_path / "definition.yaml"
    definition.write_text((ROOT / "config/model-definition.yaml").read_text())
    result = invoke(CHECK, run, "--definition", definition)
    assert (result.returncode, result.stdout, result.stderr) == (
        0, f"{run}: CONFORMS v1.2\n", "")


def make_comparison(tmp_path, runs):
    cmp = tmp_path / "cmp"
    cmp.mkdir()
    (cmp / "turbine_comparison.csv").write_text(
        "model,quantity,sim,experiment,delta_frac\n"
        "alm,power,100,100,0\nalm,thrust,80,100,-0.2\n")
    (cmp / "spanwise_comparison.csv").write_text(
        "model,r_over_R,c_ref_n,cn_exp,dcn_frac\n"
        "alm,0.30,1,1,0\nalm,0.95,1,1,0\n")
    if runs is not None:
        (cmp / "metrics.json").write_text(json.dumps({"models": {
            str(i): {"run_dir": str(run)} for i, run in enumerate(runs)}}))
    return cmp


BAND_LINES = [
    "  power  sim    100.00 exp    100.00   +0.0 %  band 10 %  PASS",
    "  thrust sim     80.00 exp    100.00  -20.0 %  band 15 %  FAIL",
    "  c_n r/R 0.30 sim 1.000 exp 1.000   +0.0 %  PASS",
    "  c_n r/R 0.95 sim 1.000 exp 1.000   +0.0 %  report",
]


@pytest.mark.parametrize("bad,allow", [(False, False), (True, False), (True, True)])
def test_summary_gate_and_preserved_output(tmp_path, bad, allow):
    run = make_run(tmp_path, old="tipEffects on;",
                   new="tipEffects off;" if bad else "tipEffects on;")
    cmp = make_comparison(tmp_path, [run])
    result = invoke(SUMMARY, cmp, *(["--allow-nonconforming"] if allow else []))
    line = ("definition v1.2: NON-CONFORMING (tipEffects=off (expected on)) -> NOT OF RECORD"
            if bad else "definition v1.2: CONFORMS")
    suffix = " [not of record]" if bad else ""
    assert (result.returncode, result.stdout, result.stderr) == (
        int(bad and not allow),
        "\n".join(["== cmp", "  " + line, *[s + suffix for s in BAND_LINES]]) + "\n", "")


def test_summary_unknown_and_multiple_models(tmp_path):
    cmp = make_comparison(tmp_path, None)
    result = invoke(SUMMARY, cmp)
    assert result.returncode == 1
    assert "definition: UNKNOWN (run dir not recorded)" in result.stdout
    assert result.stdout.count("[not of record]") == 4
    good = make_run(tmp_path, name="good")
    bad = make_run(tmp_path, name="bad", old="tipEffects on;", new="tipEffects off;")
    (cmp / "metrics.json").write_text(json.dumps({"models": {
        "alm": {"run_dir": str(good)}, "asm": {"run_dir": str(bad)}}}))
    result = invoke(SUMMARY, cmp)
    assert result.returncode == 1
    assert "NON-CONFORMING" in result.stdout
    assert result.stdout.count("[not of record]") == 4


@pytest.mark.parametrize("flag,allow", [(False, False), (True, False), (True, True)])
def test_summary_drifting_window_is_not_of_record(tmp_path, flag, allow):
    """S4: a window comparePhaseVI flagged as drifting never gives an of-record verdict."""
    run = make_run(tmp_path)
    cmp = make_comparison(tmp_path, [run])
    drift = {"flag": flag, "cp": {"variation": 0.029, "flag": flag},
             "cd": {"variation": 0.0169, "flag": flag}}
    (cmp / "metrics.json").write_text(json.dumps({"models": {
        "alm": {"run_dir": str(run), "drift": drift}}}))
    before = (cmp / "metrics.json").read_bytes()
    result = invoke(SUMMARY, cmp, *(["--allow-nonconforming"] if allow else []))
    header = ["== cmp", "  definition v1.2: CONFORMS"]
    if flag:
        header.append("  window: DRIFT (alm: cp variation 2.90 %, cd variation 1.69 %; "
                      "tolerance 1 %) -> NOT OF RECORD")
    suffix = " [not of record]" if flag else ""
    assert (result.returncode, result.stdout, result.stderr) == (
        int(flag and not allow),
        "\n".join([*header, *[s + suffix for s in BAND_LINES]]) + "\n", "")
    assert (cmp / "metrics.json").read_bytes() == before
