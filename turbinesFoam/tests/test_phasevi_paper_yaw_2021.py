# SPDX-License-Identifier: GPL-3.0-or-later
"""Public-interface contract for preparation only; no OpenFOAM execution."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1] / 'validation' / 'phaseVI'
PACKAGE = ROOT / 'paper-yaw-2021'
CLI = PACKAGE / 'prepare.py'
CONFIG = PACKAGE / 'config.json'


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes()
            for p in root.rglob('*') if p.is_file()}


def call(output, mode, *extra):
    return subprocess.run([sys.executable, str(CLI), mode, '--output', str(output), *extra],
                          capture_output=True, text=True, timeout=8,
                          env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})


def success(result, text):
    assert (result.returncode, result.stdout, result.stderr) == (0, text, '')


@pytest.fixture
def prepared(tmp_path):
    output = tmp_path / 'pilot'
    baseline = {p: snapshot(ROOT / p) for p in ('config', 'case', 'tools', 'data')}
    success(call(output, '--prepare'), 'Prepared 4 cases; execution_ready=false.\n')
    assert baseline == {p: snapshot(ROOT / p) for p in baseline}
    return output


def test_matrix_dictionaries_and_frozen_inputs(prepared):
    before = {p: snapshot(ROOT / p) for p in ('config', 'case', 'tools', 'data')}
    success(call(prepared, '--check'), 'Configuration audit passed; execution_ready=false.\n')
    result = call(prepared, '--report')
    report = json.loads(result.stdout)
    assert result.returncode == 0 and result.stderr == ''
    assert result.stdout == json.dumps(report, indent=2, sort_keys=True) + '\n'
    assert set(report['cases']) == {'U7-control', 'U7-paper-like', 'U13-control', 'U13-paper-like'}
    assert report['execution_ready'] is False
    assert len(report['blockers']) == 3
    assert 'NOT identical topology' in report['mesh']['topology']
    assert report['mesh']['polyMesh_exists'] is False
    assert max(report['mesh']['rotor_cell_widths_m']) < .125
    assert len(report['mesh']['zone_widths_m']) == 4
    assert len({c['mesh_hash'] for c in report['cases'].values()}) == 1
    assert len({c['numerics_hash'] for c in report['cases'].values()}) == 1
    for relative in ('system/blockMeshDict', 'system/snappyHexMeshDict', 'system/topoSetDict',
                     'system/fvSchemes', 'system/fvSolution', 'constant/transportProperties',
                     'constant/turbulenceProperties'):
        assert len({(prepared / name / relative).read_bytes() for name in report['cases']}) == 1
    assert report['mesh']['nominal_cell_count_NOT_measured'] > 400000
    for name, case in report['cases'].items():
        directory = prepared / name
        speed = 7 if name.startswith('U7-') else 13
        arm = name.split('-', 1)[1]
        foam = (directory / 'system/fvOptions').read_text()
        assert 'cylinder { data ((-180 0 1.1 0) (180 0 1.1 0)); }' in foam
        assert 'dynamicStallActive' not in foam
        assert 'addedMass false;' in foam and 'flowCurvature { active false; }' in foam
        assert 'liftReCorrExp 0;' in foam
        polar = re.search(r'#include "([^"]+)"', foam).group(1)
        assert (directory / 'system' / polar).resolve().read_bytes() == (ROOT / 'data/polars/S809_OSU_Re1M_pressure.dat').read_bytes()
        tsr = float(re.search(r'tipSpeedRatio ([^;]+);', foam).group(1))
        assert tsr * speed / 5.029 * 60 / (2 * math.pi) == pytest.approx(71.63, rel=1e-8)
        if arm == 'paper-like':
            for token in ('c1 0.125;', 'c2 21;', 'rootEffects off;', 'dynamicStallModel LeishmanBeddoesSGC;',
                          'LeishmanBeddoesSGCCoeffs', 'calcAlphaEquiv true;', 'velocitySampleRadius 1;', 'nVelocitySamples 16;'):
                assert token in foam
        else:
            assert 'endEffectsModel Glauert;' in foam and 'dynamicStallModel LeishmanBeddoes;' in foam
            assert 'velocitySampleRadius' not in foam
        assert 'deltaT 0.001;' in (directory / 'system/controlDict').read_text()
        schemes = (directory / 'system/fvSchemes').read_text()
        assert 'CrankNicolson 0.9' in schemes and 'div(phi,epsilon)' in schemes
        assert 'corrected' in schemes
        solution = (directory / 'system/fvSolution').read_text()
        assert re.findall(r'solver\s+(PBiCG\w*);', solution) == ['PBiCG', 'PBiCG']
        assert 'DILU' in solution and 'epsilon' in solution
        assert 'RASModel realizableKE;' in (directory / 'constant/turbulenceProperties').read_text()
        assert not (directory / '0.org/omega').exists()
        for field in ('U', 'p', 'k', 'epsilon', 'nut'):
            assert (directory / '0.org' / field).read_text().count('type symmetryPlane;') == 4
        k = 1.5 * (.005 * speed) ** 2
        epsilon = .09 ** .75 * k ** 1.5 / (.07 * 10.058)
        text = (directory / '0.org/epsilon').read_text()
        assert '[0 2 -3 0 0 0 0]' in text
        assert float(re.search(r'internalField\s+uniform ([^;]+)', text).group(1)) == pytest.approx(epsilon, rel=1e-7)
        assert case['effective_tsr'] == pytest.approx(71.63 * 2 * math.pi * 5.029 / 60 / speed)
        assert case['angular_step_deg'] == pytest.approx(71.63 * 6 * .001)
        displacement = 71.63 * 2 * math.pi / 60 * 5.029 * .001
        assert case['tip_displacement_m'] == pytest.approx(displacement)
        h = min(report['mesh']['rotor_cell_widths_m'])
        assert case['tip_displacement_over_min_h'] == pytest.approx(displacement / h)
        assert case['nominal_advective_Co_NOT_measured'] == pytest.approx(speed * .001 / h)
        assert case['epsilon_inflow'] == pytest.approx(epsilon)
        for relative, digest in case['dictionary_sha256'].items():
            assert hashlib.sha256((directory / relative).read_bytes()).hexdigest() == digest
        isolated = json.loads((directory / 'case-config.json').read_text())
        assert isolated['sequence_s']['speeds'][str(speed)]['rotor_speed_rpm'] == 71.63
    assert before == {p: snapshot(ROOT / p) for p in before}
    for relative, digest in report['input_sha256'].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize('rule', ['equivalent-incidence', 'linear-solver', 'transport', 'density', 'provenance'])
def test_published_settings_and_actual_input_dependencies(prepared, rule):
    before = snapshot(prepared)
    result = call(prepared, '--report')
    report = json.loads(result.stdout)
    assert result.returncode == 0 and result.stderr == ''
    assert result.stdout == json.dumps(report, indent=2, sort_keys=True) + '\n'
    for name in report['cases']:
        directory = prepared / name
        cfg = json.loads((directory / 'case-config.json').read_text())
        foam = (directory / 'system/fvOptions').read_text()
        if rule == 'equivalent-incidence' and name.endswith('paper-like'):
            assert 'calcAlphaEquiv true;' in foam and 'calcAlphaEquiv false;' not in foam
        elif rule == 'linear-solver':
            solution = (directory / 'system/fvSolution').read_text()
            assert re.findall(r'solver\s+(PBiCG\w*);', solution) == ['PBiCG', 'PBiCG']
            assert solution.count('DILU;') == 2
        elif rule == 'transport':
            assert cfg['inflow']['kinematic_viscosity'] == 1.46e-5
            transport = (directory / 'constant/transportProperties').read_text()
            assert re.search(r'nu\s+nu\s+\[0 2 -1 0 0 0 0\]\s+1\.46e-05;', transport)
            assert report['fluid']['kinematic_viscosity_m2_s'] == 1.46e-5
        elif rule == 'density':
            assert cfg['inflow']['reference_density_kg_m3'] == 1.23
            assert re.search(r'\brhoRef\s+1\.23;', foam)
            assert report['fluid']['reference_density_kg_m3'] == 1.23
            assert report['fluid']['density_used_by_incompressible_ALM'] is False
        elif rule == 'provenance':
            assert set(report['input_sha256']) == {
                'config/case.yaml', 'data/geometry/phaseVI_blade.csv',
                'data/polars/S809_OSU_Re1M_pressure.dat',
                'paper-yaw-2021/config.json', 'paper-yaw-2021/prepare.py',
                'tools/case_config.py', 'tools/element_data.py',
                'tools/blade_resample.py', 'tools/generate_case.py'}
            assert not any(p.startswith('case/') or '__pycache__' in p or p.endswith('.log')
                           for p in report['input_sha256'])
    assert before == snapshot(prepared)


def test_check_report_and_reprepare_never_mutate(prepared):
    frozen = snapshot(prepared)
    success(call(prepared, '--check'), 'Configuration audit passed; execution_ready=false.\n')
    assert call(prepared, '--report').returncode == 0
    rejected = call(prepared, '--prepare')
    assert (rejected.returncode, rejected.stdout, rejected.stderr) == (2, '', 'error: output must be absent or an empty directory\n')
    assert snapshot(prepared) == frozen


@pytest.mark.parametrize('mode', ['--prepare', '--check', '--report'])
def test_invalid_config_has_no_effect(tmp_path, mode):
    output = tmp_path / 'pilot'
    bad = tmp_path / 'bad.json'
    bad.write_text('{}')
    result = call(output, mode, '--config', str(bad))
    assert (result.returncode, result.stdout, result.stderr) == (2, '', 'error: config does not match the supported preparation specification\n')
    assert not output.exists()


@pytest.mark.parametrize('mode', ['--check', '--report'])
def test_missing_and_tampered_readonly(prepared, tmp_path, mode):
    missing = tmp_path / 'missing'
    result = call(missing, mode)
    assert (result.returncode, result.stdout, result.stderr) == (1, '', 'error: missing or changed output: U7-control/system/blockMeshDict\n')
    assert not missing.exists()
    target = prepared / 'U7-control/system/blockMeshDict'
    target.write_text('tampered')
    before = snapshot(prepared)
    result = call(prepared, mode)
    assert (result.returncode, result.stdout, result.stderr) == (1, '', 'error: missing or changed output: U7-control/system/blockMeshDict\n')
    assert snapshot(prepared) == before


def test_conflict_symlink_and_missing_config(tmp_path):
    output = tmp_path / 'occupied'
    output.mkdir()
    (output / 'keep').write_text('untouched')
    before = snapshot(output)
    result = call(output, '--prepare')
    assert (result.returncode, result.stdout, result.stderr) == (2, '', 'error: output must be absent or an empty directory\n')
    assert snapshot(output) == before
    link = tmp_path / 'link'
    link.symlink_to(output, target_is_directory=True)
    result = call(link, '--prepare')
    assert (result.returncode, result.stdout, result.stderr) == (2, '', 'error: symlink output paths are not allowed\n')
    assert snapshot(output) == before
    result = call(output, '--prepare', '--config', str(tmp_path / 'absent.json'))
    assert result.returncode == 2 and result.stdout == ''
    assert result.stderr.startswith('error: cannot read config: ')
    assert snapshot(output) == before


def test_missing_polar_input_is_rejected_before_writes(tmp_path):
    mirror = tmp_path / 'phaseVI'
    for name in ('tools', 'config', 'case', 'data', 'paper-yaw-2021'):
        shutil.copytree(ROOT / name, mirror / name,
                        ignore=shutil.ignore_patterns('S809_OSU_Re1M_pressure.dat', '__pycache__'))
    output = tmp_path / 'pilot'
    result = subprocess.run([sys.executable, str(mirror / 'paper-yaw-2021/prepare.py'),
                             '--prepare', '--output', str(output)], capture_output=True, text=True)
    assert result.returncode == 2 and result.stdout == ''
    assert result.stderr == f"error: [Errno 2] No such file or directory: '{mirror / 'data/polars/S809_OSU_Re1M_pressure.dat'}'\n"
    assert not output.exists()


def test_extra_entries_and_missing_files(prepared):
    field = prepared / 'U7-control/0.org/epsilon'
    field.rename(field.with_name('epsilon.hidden'))
    before = snapshot(prepared)
    result = call(prepared, '--check')
    assert (result.returncode, result.stdout, result.stderr) == (1, '', 'error: missing or changed output: U7-control/0.org/epsilon\n')
    assert before == snapshot(prepared)


def test_help_and_no_execution_flags(tmp_path):
    result = subprocess.run([sys.executable, str(CLI), '--help'], capture_output=True, text=True)
    assert result.returncode == 0 and result.stderr == ''
    for flag in ('--prepare', '--check', '--report', '--output', '--config'):
        assert flag in result.stdout
    for flag in ('--run', '--submit', '--force'):
        result = call(tmp_path / 'pilot', '--prepare', flag)
        assert result.returncode == 2 and result.stdout == ''
        assert result.stderr.endswith(f'error: unrecognized arguments: {flag}\n')
        assert not (tmp_path / 'pilot').exists()
