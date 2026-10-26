# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase VI --pitch-reference twist-zero|tip (Model Definition v1.2 vs tip chord).

NREL/TP-500-29955 p.20 defines the pitch at the blade tip chord, while Table A-1
note 2 gives the twist relative to zero at 75 % span. `tip` subtracts the table
twist at the rotor radius; `twist-zero` is the v1.2 rendering, byte-identical.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

PACKAGE = Path(__file__).resolve().parents[1] / "validation" / "phaseVI"
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
sys.path.insert(0, str(PACKAGE / "tools"))

from case_config import load_config, read_blade  # noqa: E402
import element_data  # noqa: E402
from element_data import blade_element_rows  # noqa: E402

TWIST_TIP = read_blade()[-1]["twist"]


def _cfg(reference=None, blade_dz=None):
    cfg = load_config()
    if reference is not None:
        cfg["turbine"]["pitch_reference"] = reference
    if blade_dz is not None:
        cfg["turbine"]["blade_dz"] = blade_dz
    return cfg


def _render(tmp_path, name, *flags):
    case = tmp_path / name
    result = subprocess.run(
        [sys.executable, str(PACKAGE / "tools/generate_case.py"), "--case-dir", str(case), *flags],
        capture_output=True, text=True, env=ENV)
    assert result.returncode == 0, result.stderr
    (case / "system/fvOptions").write_text((case / "system/fvOptions.ALM").read_text())
    return case


def _check(*args):
    return subprocess.run([sys.executable, str(PACKAGE / "scripts/checkModelDefinition.py"), *map(str, args)],
                          capture_output=True, text=True, env=ENV)


def _sandbox(tmp_path):
    package = tmp_path / "validation/phaseVI"
    shutil.copytree(PACKAGE, package, ignore=shutil.ignore_patterns(
        "runs", "results", "polyMesh", "__pycache__"))
    (tmp_path / "geometry").symlink_to(PACKAGE.parents[1] / "geometry")
    (package / "scripts/check_environment.sh").write_text("#!/bin/sh\nexit 0\n")
    mesh = package / "runs/mesh-coarse/constant/polyMesh"
    mesh.mkdir(parents=True)
    (mesh / ".keep").write_text("")
    return package, {k: v for k, v in ENV.items() if not k.startswith("SLURM_")}


def test_tip_twist_comes_from_the_rotor_radius_row():
    assert read_blade()[-1]["radius"] == 5.029
    assert TWIST_TIP == -1.815


def test_tip_reference_mounts_the_tip_at_minus_pitch_and_shifts_every_row():
    default = blade_element_rows(_cfg())
    tip = blade_element_rows(_cfg("tip"))
    assert tip[-1][5] == -3.0
    assert default[-1][5] == pytest.approx(-1.185)
    for old, new in zip(default, tip):
        assert new[:5] == old[:5]
        assert new[5] == pytest.approx(old[5] + TWIST_TIP)


def test_tip_reference_on_the_equispaced_path_uses_the_original_table_tip():
    default = blade_element_rows(_cfg(blade_dz=0.05))
    tip = blade_element_rows(_cfg("tip", blade_dz=0.05))
    assert tip[-1][5] == -3.0
    assert [new[5] - old[5] for old, new in zip(default, tip)] == pytest.approx([TWIST_TIP] * len(tip))


def test_unknown_pitch_reference_is_refused_by_the_generator(tmp_path):
    result = subprocess.run(
        [sys.executable, str(PACKAGE / "tools/generate_case.py"), "--case-dir", str(tmp_path / "c"),
         "--pitch-reference", "root"], capture_output=True, text=True, env=ENV)
    assert result.returncode == 2
    assert "invalid choice: 'root'" in result.stderr


@pytest.mark.parametrize("flags", [[], ["--pitch-reference", "twist-zero"]])
def test_default_and_explicit_twist_zero_match_the_committed_v12_render(flags):
    result = subprocess.run([sys.executable, str(PACKAGE / "tools/generate_case.py"), "--check", *flags],
                            capture_output=True, text=True, env=ENV)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_default_render_keeps_the_v12_tip_row(tmp_path):
    default = _render(tmp_path, "default")
    explicit = _render(tmp_path, "explicit", "--pitch-reference", "twist-zero")
    for name in ("fvOptions.ALM", "fvOptions.ASM", "fvOptions.ASM-MESH"):
        assert (default / "system" / name).read_bytes() == (explicit / "system" / name).read_bytes()
    assert "(0 5.029 0 0.3551 0.3 -1.185)" in (default / "system/fvOptions").read_text()


def test_tip_render_only_differs_in_the_mounting_column(tmp_path):
    default = (_render(tmp_path, "default") / "system/fvOptions").read_text()
    tip = (_render(tmp_path, "tip", "--pitch-reference", "tip") / "system/fvOptions").read_text()
    assert "(0 5.029 0 0.3551 0.3 -3)" in tip
    row = re.compile(r"^(\s+\(0 [\d.]+ 0 [\d.]+ [\d.]+) [-\d.]+\)$", re.M)
    assert row.sub(r"\1)", default) == row.sub(r"\1)", tip)


@pytest.mark.parametrize("reference,offset", [("twist-zero", -3.0), ("tip", -(3.0 + 1.815))])
def test_ch_ra_pitch_offset_excludes_the_collective_pitch(tmp_path, reference, offset):
    case = _render(tmp_path, reference, "--rotational-augmentation", "on",
                   "--rotational-augmentation-model", "ChaviaropoulosHansen",
                   "--pitch-reference", reference)
    found = re.findall(r"pitchOffset\s+([^;]+);", (case / "system/fvOptions").read_text())
    assert [float(v) for v in found] == pytest.approx([offset])
    if reference == "twist-zero":
        assert found == ["-3"]


def test_runner_rejects_an_unknown_pitch_reference():
    result = subprocess.run(["bash", str(PACKAGE / "scripts/runPhaseVI.sh"), "-m", "alm", "-u", "7",
                             "--pitch-reference", "root"], capture_output=True, text=True, env=ENV)
    assert (result.returncode, result.stdout, result.stderr) == (
        2, "", "ERROR: --pitch-reference takes twist-zero or tip (got: root)\n")


@pytest.mark.parametrize("reference", ["twist-zero", "tip"])
def test_runner_records_pitch_reference_and_checker_certifies_it(tmp_path, reference):
    package, env = _sandbox(tmp_path)
    result = subprocess.run(["bash", str(package / "scripts/runPhaseVI.sh"), "-m", "alm", "-u", "7",
                             "--pitch-reference", reference], capture_output=True, text=True,
                            env=env, cwd=package)
    assert result.returncode == 0, result.stderr
    run = package / "runs/alm-U7-coarse"
    assert f'"pitch_reference": "{reference}"' in (run / "run.json").read_text()
    tip_row = "(0 5.029 0 0.3551 0.3 %s)" % ("-3" if reference == "tip" else "-1.185")
    assert tip_row in (run / "system/fvOptions").read_text()
    verdict = _check(run, "--variant", "tip-pitch")
    assert verdict.stderr == ""
    assert (verdict.returncode == 0) == (reference == "tip")
    if reference == "tip":
        assert verdict.stdout == f"{run}: CONFORMS tip-pitch\n"


def test_checker_enum_mirrors_the_renderer_enum():
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_model_definition", PACKAGE / "scripts/checkModelDefinition.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.PITCH_REFERENCES == element_data.PITCH_REFERENCES


def test_registry_declares_tip_pitch_and_refuses_an_unknown_enum(tmp_path):
    registry = yaml.safe_load((PACKAGE / "config/model-variants.yaml").read_text())
    entry = registry["variants"]["tip-pitch"]
    assert entry["flags"] == {"--pitch-reference": "tip"}
    assert "TP-500-29955 p.20" in entry["reference"] and "Table A-1" in entry["reference"]
    assert "never of record" in entry["note"]
    result = _check("--variant", "tip-pitch", "--renderer-flags")
    assert (result.returncode, result.stdout, result.stderr) == (0, "--pitch-reference\ntip\n", "")
    v12 = _check("--variant", "v1.2", "--renderer-flags")
    assert (v12.returncode, v12.stdout, v12.stderr) == (0, "", "")

    package = tmp_path / "validation/phaseVI"
    shutil.copytree(PACKAGE, package, ignore=shutil.ignore_patterns("runs", "results", "__pycache__"))
    path = package / "config/model-variants.yaml"
    path.write_text(path.read_text().replace("--pitch-reference: tip", "--pitch-reference: root"))
    bad = subprocess.run([sys.executable, str(package / "scripts/checkModelDefinition.py"),
                          "--variant", "tip-pitch", "--renderer-flags"],
                         capture_output=True, text=True, env=ENV)
    assert (bad.returncode, bad.stdout, bad.stderr) == (
        2, "", "error: invalid variant flag value: --pitch-reference=root\n")


def test_tip_pitch_variant_preflight_exits_zero():
    result = subprocess.run(["sh", "scripts/slurm/variant-run.slurm", "--check"], cwd=PACKAGE,
                            env={**ENV, "VARIANT": "tip-pitch", "SLURM_SUBMIT_DIR": str(PACKAGE)},
                            capture_output=True, text=True)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_checker_certifies_tip_pitch_and_flags_it_against_v12(tmp_path):
    case = _render(tmp_path, "tip", "--pitch-reference", "tip")
    own = _check(case, "--variant", "tip-pitch")
    assert (own.returncode, own.stdout, own.stderr) == (0, f"{case}: CONFORMS tip-pitch\n", "")
    base = _check(case)
    assert base.returncode == 1 and base.stderr == ""
    assert "tipMounting=-3 (expected -1.185, pitch reference twist-zero)" in base.stdout
    default = _render(tmp_path, "default")
    assert _check(default).stdout == f"{default}: CONFORMS v1.2\n"
    wrong = _check(default, "--variant", "tip-pitch")
    assert wrong.returncode == 1
    assert "tipMounting=-1.185 (expected -3, pitch reference tip)" in wrong.stdout
