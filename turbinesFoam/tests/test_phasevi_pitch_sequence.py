# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase VI pitch sequences T (2 deg), U (4 deg), J (6 deg), I (0 deg): renderer, runner, audit.

The sequences share the Sequence S rotor and case (0 yaw, 72 rpm); only the collective tip
pitch differs. `generate_case.py --pitch-deg` overrides it, `runPhaseVI.sh --sequence T|U|J|I`
maps the sequence to its pitch, names the run `-seqT` and records `pitch_deg` in run.json, and
`compareYawPitch.py --pitch` fails closed when that record disagrees with the requested pitch.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PACKAGE = TESTS_DIR.parent / "validation" / "phaseVI"
GENERATOR = PACKAGE / "tools" / "generate_case.py"
sys.path.insert(0, str(TESTS_DIR))

from test_phasevi_case import _prepare_sandbox  # noqa: E402
from test_phasevi_compare import write_run  # noqa: E402
from test_phasevi_compare_yaw_pitch import cyp, make_experiment, run_main  # noqa: E402

PITCH = {"I": 0.0, "T": 2.0, "U": 4.0, "J": 6.0}
ROW = re.compile(r"\((0 [-\d.e]+ 0 [-\d.e]+ [-\d.e]+ ([-\d.e]+))\)")

# sha256 (polar include path neutralised) of the Sequence S 5 m/s render at the base commit
# (before --pitch-deg existed): coarse, long domain, urans, 84 ranks.
FROZEN_S5 = {
    "system/fvOptions.ALM": "0de01fe2a851b9a57359196a0089c10f6a152c0ff998bd9acd576ac8d91f9ba0",
    "system/fvOptions.ASM": "f9ac8a9665eceb602829b2959cba8fd73b0ac7b6316951e0557ef650b93d5a0c",
    "system/fvOptions.ASM-MESH": "381687a3d57d62b06b1929c9fce5fb687af0a689eabd7c6c748d7df17fcc73d4",
    "system/topoSetDict": "0f50b3621b2fc4c0c0aa8b42f2c77bfd8d1e66fd6aa3e30505dc675ad6fc82ca",
}


def _render(tmp_path, name, *extra):
    case = tmp_path / name
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--mesh", "coarse", "--speed", "5", "--sequence", "S",
         "--case-dir", str(case), "--ranks", "84", *extra],
        capture_output=True, text=True)
    return result, case


def _digest(path):
    text = re.sub(r'#include "[^"]*/data/polars/', '#include "POLARS/', path.read_text())
    return hashlib.sha256(text.encode()).hexdigest()


def _element_pitches(case):
    text = (case / "system" / "fvOptions.ALM").read_text()
    return [float(match.group(2)) for match in ROW.finditer(text)]


def test_s_render_is_unchanged_without_pitch_override(tmp_path):
    # The frozen digests predate v1.4: pin the near-tip correction off (the v1.3 render).
    result, case = _render(tmp_path, "s", "--near-tip-correction", "off")
    assert result.returncode == 0, result.stderr
    for name, digest in FROZEN_S5.items():
        assert _digest(case / name) == digest, name
    explicit, case3 = _render(tmp_path, "s3", "--pitch-deg", "3", "--near-tip-correction", "off")
    assert explicit.returncode == 0, explicit.stderr
    for name in FROZEN_S5:
        assert _digest(case3 / name) == _digest(case / name), name


@pytest.mark.parametrize("pitch", [2.0, 4.0, 6.0])
def test_pitch_override_shifts_every_element_by_the_pitch_difference(tmp_path, pitch):
    _, base = _render(tmp_path, "base")
    result, case = _render(tmp_path, "p", "--pitch-deg", f"{pitch:g}")
    assert result.returncode == 0, result.stderr
    old, new = _element_pitches(base), _element_pitches(case)
    assert len(old) == len(new) > 10
    assert new[-1] == pytest.approx(-pitch)  # tip mounting = -pitch (tip reference)
    for before, after in zip(old, new, strict=True):
        assert after - before == pytest.approx(3.0 - pitch, abs=2e-4)


def test_pitch_override_rejects_a_non_number(tmp_path):
    result, _ = _render(tmp_path, "bad", "--pitch-deg", "abc")
    assert result.returncode == 2


@pytest.fixture(scope="module")
def sandbox(tmp_path_factory):
    return _prepare_sandbox(tmp_path_factory.mktemp("pitchseq"))


def _runner(sandbox, *args):
    package, env = sandbox
    return subprocess.run(["sh", str(package / "scripts" / "runPhaseVI.sh"), *args],
                          cwd=package, capture_output=True, text=True, env=env)


@pytest.mark.parametrize("sequence", ["T", "U", "J", "I"])
def test_runner_maps_sequence_to_pitch_and_names_the_run(sandbox, sequence):
    package, _ = sandbox
    result = _runner(sandbox, "-m", "alm", "-u", "5", "-mesh", "coarse", "--sequence", sequence,
                     "--run-label", "lab")
    assert result.returncode == 0, result.stderr
    run_dir = package / "runs" / f"alm-U5-coarse-seq{sequence}-lab"
    payload = json.loads((run_dir / "run.json").read_text())
    assert payload["sequence"] == sequence
    assert payload["pitch_deg"] == PITCH[sequence]
    assert payload["pitch_reference"] == "tip"
    assert _element_pitches(run_dir)[-1] == pytest.approx(-PITCH[sequence])


def test_runner_s_run_keeps_its_name_and_records_pitch_three(sandbox):
    package, _ = sandbox
    result = _runner(sandbox, "-m", "alm", "-u", "5", "-mesh", "coarse", "--sequence", "S",
                     "--run-label", "lab")
    assert result.returncode == 0, result.stderr
    run_dir = package / "runs" / "alm-U5-coarse-seqS-lab"
    assert json.loads((run_dir / "run.json").read_text())["pitch_deg"] == 3.0
    assert _element_pitches(run_dir)[-1] == pytest.approx(-3.0)


def test_runner_refuses_asm_mesh_for_pitch_sequences(sandbox):
    result = _runner(sandbox, "-m", "asm-mesh", "-u", "5", "-mesh", "coarse", "--sequence", "T")
    assert result.returncode == 2
    assert "pitch sequence" in result.stderr


def test_variant_slurm_check_still_validates(sandbox):
    package, env = sandbox
    result = subprocess.run(["sh", str(package / "scripts/slurm/variant-run.slurm"), "--check"],
                            cwd=package, capture_output=True, text=True,
                            env={**env, "VARIANT": "tip-pitch-dag-sorensen-neartip"})
    assert result.returncode == 0, result.stderr


def _exp(tmp_path):
    return make_experiment(tmp_path / "exp")


def _write_run_json(run, **fields):
    (run / "run.json").write_text(json.dumps({"model": "alm", **fields}))


def test_compare_accepts_matching_pitch_and_records_the_audit(tmp_path):
    _exp(tmp_path)
    run = write_run(tmp_path / "run")
    _write_run_json(run, pitch_deg=6.0)
    rc, out = run_main(tmp_path, run, "--pitch", "6", "--sequence", "J")
    assert rc == cyp.EXIT_OK
    audit = json.loads((out / "metrics.json").read_text())["run_audit"]
    assert audit["run_pitch_audited"] is True
    assert audit["run_pitch_deg"] == 6.0
    assert audit["expected_pitch_deg"] == 6.0


def test_compare_rejects_a_pitch_mismatch(tmp_path):
    _exp(tmp_path)
    run = write_run(tmp_path / "run")
    _write_run_json(run, pitch_deg=3.0)
    rc, _ = run_main(tmp_path, run, "--pitch", "6", "--sequence", "J")
    assert rc == cyp.EXIT_PITCH_MISMATCH


def test_compare_without_a_recorded_pitch_stays_unaudited(tmp_path):
    _exp(tmp_path)
    run = write_run(tmp_path / "run")
    rc, out = run_main(tmp_path, run, "--pitch", "6")
    assert rc == cyp.EXIT_OK
    assert json.loads((out / "metrics.json").read_text())["run_audit"]["run_pitch_audited"] is False
