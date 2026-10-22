# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic public CLI contracts for the Phase VI A/B registry."""
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1] / 'validation/phaseVI'
ENV = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}


def call(script, *args):
    return subprocess.run([sys.executable, str(ROOT / script), *map(str, args)],
                          capture_output=True, text=True, env=ENV)


def render(tmp_path, name):
    registry = yaml.safe_load((ROOT / 'config/model-variants.yaml').read_text())
    flags = registry['variants'][name]['flags']
    case = tmp_path / name
    result = call('tools/generate_case.py', '--case-dir', case,
                  *[str(x) for k, v in flags.items() for x in (k, v)])
    assert result.returncode == 0, result.stderr
    (case / 'system/fvOptions').write_text((case / 'system/fvOptions.ALM').read_text())
    return case


@pytest.mark.parametrize('name', ['v1.2', 'shen-tip', 'dag-sorensen-tip',
                                  'ring-sampling', 'du-selig-ra', 'ch-ra', 'tip-pitch'])
def test_variants_render_and_check(tmp_path, name):
    case = render(tmp_path, name)
    text = (case / 'system/fvOptions').read_text()
    if name == 'shen-tip':
        assert 'endEffectsModel Shen;' in text
        assert 'c1 0.125;' in text and 'c2 21;' in text
    own = call('scripts/checkModelDefinition.py', case, '--variant', name)
    assert (own.returncode, own.stdout, own.stderr) == (0, f'{case}: CONFORMS {name}\n', '')
    baseline = call('scripts/checkModelDefinition.py', case)
    assert baseline.returncode == (0 if name == 'v1.2' else 1)
    assert baseline.stderr == ''
    if name == 'v1.2':
        assert baseline.stdout == f'{case}: CONFORMS v1.2\n'
    else:
        assert 'NON-CONFORMING v1.2:' in baseline.stdout


def test_unknown_variant_refused_before_input(tmp_path):
    result = call('scripts/checkModelDefinition.py', tmp_path / 'missing', '--variant', 'unknown')
    assert (result.returncode, result.stdout, result.stderr) == (2, '', 'error: unknown variant: unknown\n')
    result = subprocess.run(['sh', str(ROOT / 'scripts/slurm/variant-run.slurm')],
                            env={**ENV, 'VARIANT': 'unknown', 'SLURM_SUBMIT_DIR': str(ROOT)},
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert result.stdout == ''
    assert result.stderr == 'error: unknown variant: unknown\n'


@pytest.mark.parametrize('flag,value,message', [
    ('--rotational-augmentation-model', 'unknown', 'must be DuSelig or ChaviaropoulosHansen'),
    ('--end-effects-model', 'unknown', 'must be Glauert, Shen or liftingLine'),
    ('--velocity-sample-radius', '-1', 'must be a non-negative finite number'),
    ('--velocity-sample-radius', 'nan', 'must be a non-negative finite number'),
    ('--n-velocity-samples', '0', 'must be a positive integer'),
])
def test_runner_rejects_invalid_flags_before_environment(flag, value, message):
    result = subprocess.run(['bash', str(ROOT / 'scripts/runPhaseVI.sh'),
                             '-m', 'alm', '-u', '7', flag, value],
                            capture_output=True, text=True, env=ENV)
    assert (result.returncode, result.stdout, result.stderr) == (
        2, '', f'ERROR: {flag} {message}\n')


def test_known_variant_preflight():
    result = subprocess.run(['sh', 'scripts/slurm/variant-run.slurm', '--check'],
                            cwd=ROOT, env={**ENV, 'VARIANT': 'ring-sampling',
                                           'SLURM_SUBMIT_DIR': str(ROOT)},
                            capture_output=True, text=True)
    assert (result.returncode, result.stdout, result.stderr) == (0, '', '')


@pytest.mark.parametrize('ra_model', ['DuSelig', 'ChaviaropoulosHansen'])
def test_runner_forwards_sampling_and_model(tmp_path, ra_model):
    package = tmp_path / 'validation/phaseVI'
    shutil.copytree(ROOT, package, ignore=shutil.ignore_patterns(
        'runs', 'results', 'polyMesh', '__pycache__'))
    (tmp_path / 'geometry').symlink_to(ROOT.parents[1] / 'geometry')
    environment = package / 'scripts/check_environment.sh'
    environment.write_text('#!/bin/sh\nexit 0\n')
    mesh = package / 'runs/mesh-coarse/constant/polyMesh'
    mesh.mkdir(parents=True)
    (mesh / '.keep').write_text('')
    env = {k: v for k, v in ENV.items() if not k.startswith('SLURM_')}
    result = subprocess.run(['bash', str(package / 'scripts/runPhaseVI.sh'),
        '-m', 'alm', '-u', '7', '--end-effects-model', 'Shen',
        '--velocity-sample-radius', '3.3', '--n-velocity-samples', '16',
        '--rotational-augmentation-model', ra_model,
        '--rotational-augmentation', 'on'],
        capture_output=True, text=True, env=env, cwd=package)
    assert result.returncode == 0, result.stderr
    text = (package / 'runs/alm-U7-coarse/system/fvOptions').read_text()
    assert f'model {ra_model};' in text
    if ra_model == 'ChaviaropoulosHansen':
        assert 'a 2.2;' in text and 'h 1;' in text and 'n 4;' in text
        assert 'pitchOffset -3;' in text
    else:
        assert 'a 1;' in text and 'b 1;' in text and 'd 1;' in text
    assert 'endEffectsModel Shen;' in text
    assert 'velocitySampleRadius 3.3;' in text
    assert 'nVelocitySamples 16;' in text
    assert 'c1 0.125;' in text and 'c2 21;' in text


def test_summary(tmp_path):
    dirs = []
    for name, fraction in [('v1.2', 0.1), ('ring-sampling', 0.2)]:
        run = render(tmp_path, name)
        d = tmp_path / ('cmp-' + name)
        d.mkdir()
        (d / 'metrics.json').write_text(json.dumps({'case': {'sequence': 'S', 'speed_m_s': 7},
            'models': {'alm': {'run_dir': str(run), 'drift': {'flag': name != 'v1.2'}}}}))
        (d / 'turbine_comparison.csv').write_text('model,quantity,delta_frac\n'
            f'alm,power,{fraction}\nalm,thrust,{fraction}\n')
        (d / 'spanwise_comparison.csv').write_text('model,r_over_R,dcn_frac\n' +
            ''.join(f'alm,{r},{fraction}\n' for r in [0.30, 0.47, 0.63, 0.80, 0.95]))
        dirs.append(d)
    result = call('scripts/summarizeVariants.py', *dirs)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ''
    assert '== S U7' in result.stdout
    assert 'P' in result.stdout and 'cn0.95' in result.stdout
    assert 'ring-sampling' in result.stdout and 'DRIFT' in result.stdout
    assert '+20.0 (+10.0)' in result.stdout
    assert '[not of record]' in result.stdout
    # A named variant with an extra, unregistered override must fail its own gate.
    fv = tmp_path / 'ring-sampling/system/fvOptions'
    fv.write_text(fv.read_text().replace('tipEffects on;', 'tipEffects off;'))
    result = call('scripts/summarizeVariants.py', *dirs)
    assert result.returncode == 1
    assert 'NON-CONFORMING' in result.stdout
