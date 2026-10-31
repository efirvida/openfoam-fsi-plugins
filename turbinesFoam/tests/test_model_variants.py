# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic public CLI contracts for the Phase VI A/B registry.

Registry flags override the frozen Model Definition v1.2 base; v1.3 is the
definition of record and the renderer default, so a variant is rendered with every
v1.2 knob explicit first, exactly as scripts/slurm/variant-run.slurm does.
"""
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
V12_FLAGS = ['--pitch-reference', 'twist-zero', '--tip-effects', 'on', '--tip-correction', 'off',
             '--polar', 'S809_OSU_Re1M_pressure.dat']


def call(script, *args):
    return subprocess.run([sys.executable, str(ROOT / script), *map(str, args)],
                          capture_output=True, text=True, env=ENV)


def render(tmp_path, name):
    registry = yaml.safe_load((ROOT / 'config/model-variants.yaml').read_text())
    flags = registry['variants'][name]['flags']
    case = tmp_path / name
    result = call('tools/generate_case.py', '--case-dir', case, *V12_FLAGS,
                  *[str(x) for k, v in flags.items() for x in (k, v)])
    assert result.returncode == 0, result.stderr
    (case / 'system/fvOptions').write_text((case / 'system/fvOptions.ALM').read_text())
    return case


@pytest.mark.parametrize('name', ['v1.2', 'v1.3', 'shen-tip', 'dag-sorensen-tip',
                                  'ring-sampling', 'du-selig-ra', 'ch-ra', 'tip-pitch',
                                  'tip-pitch-dag-sorensen', 'tip-pitch-no-tip',
                                  'tip-pitch-du-selig-ra', 'tip-pitch-ch-ra'])
def test_variants_render_and_check(tmp_path, name):
    case = render(tmp_path, name)
    text = (case / 'system/fvOptions').read_text()
    if name == 'shen-tip':
        assert 'endEffectsModel Shen;' in text
        assert 'c1 0.125;' in text and 'c2 21;' in text
    own = call('scripts/checkModelDefinition.py', case, '--variant', name)
    assert (own.returncode, own.stdout, own.stderr) == (0, f'{case}: CONFORMS {name}\n', '')
    # No --variant checks against the record, v1.3.
    baseline = call('scripts/checkModelDefinition.py', case)
    assert baseline.returncode == (0 if name == 'v1.3' else 1)
    assert baseline.stderr == ''
    if name == 'v1.3':
        assert baseline.stdout == f'{case}: CONFORMS v1.3\n'
    else:
        assert 'NON-CONFORMING v1.3:' in baseline.stdout


# (tipEffects, rootEffects, tipCorrection.active, rotationalAugmentation.active/model)
TIP_PITCH_ARMS = {
    'tip-pitch-dag-sorensen': ('off', 'on', 'on', 'off', None),
    'tip-pitch-no-tip': ('off', 'on', 'off', 'off', None),
    'tip-pitch-du-selig-ra': ('on', 'on', 'off', 'on', 'DuSelig'),
    'tip-pitch-ch-ra': ('on', 'on', 'off', 'on', 'ChaviaropoulosHansen'),
}


@pytest.mark.parametrize('name', sorted(TIP_PITCH_ARMS))
def test_tip_pitch_arms_certified_from_rendered_case(tmp_path, name):
    tip, root, correction, ra, model = TIP_PITCH_ARMS[name]
    case = render(tmp_path, name)
    text = (case / 'system/fvOptions').read_text()
    assert f'tipEffects {tip};' in text and f'rootEffects {root};' in text
    assert f'active {correction};\n            model DagSorensen;' in text
    assert (f'model {model};' in text) == (model is not None)
    # CONFORMS also certifies the tip mounting (-3.0, last blade1 elementData row).
    assert call('scripts/checkModelDefinition.py', case, '--variant', name).stdout == \
        f'{case}: CONFORMS {name}\n'
    # A neighbouring arm that differs in the certified knob must reject the case.
    other = 'tip-pitch' if name != 'tip-pitch' else 'tip-pitch-no-tip'
    wrong = call('scripts/checkModelDefinition.py', case, '--variant', other)
    assert wrong.returncode == 1 and 'NON-CONFORMING' in wrong.stdout


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
        '-m', 'alm', '-u', '7', '--pitch-reference', 'twist-zero', '--end-effects-model', 'Shen',
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
    for name, fraction in [('v1.3', 0.1), ('ring-sampling', 0.2)]:
        run = render(tmp_path, name)
        d = tmp_path / ('cmp-' + name)
        d.mkdir()
        (d / 'metrics.json').write_text(json.dumps({'case': {'sequence': 'S', 'speed_m_s': 7},
            'models': {'alm': {'run_dir': str(run), 'drift': {'flag': name != 'v1.3'}}}}))
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
    assert 'change vs v1.3 in pp' in result.stdout
    # A named variant with an extra, unregistered override must fail its own gate.
    fv = tmp_path / 'ring-sampling/system/fvOptions'
    fv.write_text(fv.read_text().replace('tipEffects on;', 'tipEffects off;'))
    result = call('scripts/summarizeVariants.py', *dirs)
    assert result.returncode == 1
    assert 'NON-CONFORMING' in result.stdout


def test_summary_baseline_is_the_record_and_can_be_chosen(tmp_path):
    dirs = []
    for name, fraction in [('v1.2', 0.1), ('v1.3', 0.3)]:
        run = render(tmp_path, name)
        d = tmp_path / ('cmp-' + name)
        d.mkdir()
        (d / 'metrics.json').write_text(json.dumps({'case': {'sequence': 'S', 'speed_m_s': 7},
            'models': {'alm': {'run_dir': str(run)}}}))
        (d / 'turbine_comparison.csv').write_text('model,quantity,delta_frac\n'
            f'alm,power,{fraction}\nalm,thrust,{fraction}\n')
        (d / 'spanwise_comparison.csv').write_text('model,r_over_R,dcn_frac\n' +
            ''.join(f'alm,{r},{fraction}\n' for r in [0.30, 0.47, 0.63, 0.80, 0.95]))
        dirs.append(d)
    record = call('scripts/summarizeVariants.py', *dirs)
    assert (record.returncode, record.stderr) == (0, '')
    lines = record.stdout.splitlines()
    assert lines[2].startswith('v1.3 | alm | +30.0 (+0.0)')
    assert lines[3].startswith('v1.2 | alm | +10.0 (-20.0)') and lines[3].count('[not of record]') == 1
    assert 'CONFORMS [not of record]' not in lines[2]
    chosen = call('scripts/summarizeVariants.py', '--baseline', 'v1.2', *dirs)
    assert chosen.returncode == 0
    assert chosen.stdout.splitlines()[2].startswith('v1.2 | alm | +10.0 (+0.0)')
    assert chosen.stdout.splitlines()[3].startswith('v1.3 | alm | +30.0 (+20.0)')
    unknown = call('scripts/summarizeVariants.py', '--baseline', 'nope', *dirs)
    assert (unknown.returncode, unknown.stdout, unknown.stderr) == (2, '', 'error: unknown baseline: nope\n')


def load_checker():
    import importlib.util
    spec = importlib.util.spec_from_file_location('check_definition', ROOT / 'scripts/checkModelDefinition.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_registry_v13_on_the_v12_base_equals_the_record():
    module = load_checker()
    base = module.load_base_definition()
    assert base['version'] == 'v1.2' and base['pitch_reference'] == 'twist-zero'
    composed = module.variant_definition(base, 'v1.3')
    record = module.load_definition()
    assert record['version'] == 'v1.3' and record['pitch_reference'] == 'tip'
    assert composed == record
    registry = yaml.safe_load((ROOT / 'config/model-variants.yaml').read_text())
    assert registry['base'] == 'model-definition-v1.2.yaml'
    assert registry['variants']['v1.2']['flags'] == {}
    assert registry['variants']['v1.3']['flags'] == {
        '--pitch-reference': 'tip', '--tip-correction': 'on', '--tip-effects': 'off',
        '--polar': 'S809_OSU_Re1M_total.dat'}


def test_registry_v13_renderer_flags_are_exact():
    result = call('scripts/checkModelDefinition.py', '--variant', 'v1.3', '--renderer-flags')
    assert (result.returncode, result.stdout, result.stderr) == (
        0, '--pitch-reference\ntip\n--tip-correction\non\n--tip-effects\noff\n'
           '--polar\nS809_OSU_Re1M_total.dat\n', '')


def test_v13_equals_tip_pitch_dag_sorensen_plus_the_total_polar():
    module = load_checker()
    base = module.load_base_definition()
    gate = module.variant_definition(base, 'tip-pitch-dag-sorensen')
    record = module.load_definition()
    assert gate['knobs'].pop('polar')['expected'] == 'data/polars/S809_OSU_Re1M_pressure.dat'
    assert record['knobs'].pop('polar')['expected'] == 'data/polars/S809_OSU_Re1M_total.dat'
    gate['version'] = record['version']
    assert gate == record


# name -> (pitch_reference, tipEffects, tipCorrection.active, rotationalAugmentation.active, polar,
#          rotationalAugmentation.pitchOffset or None). Pinned so that moving the record never
#          changes what an existing variant certifies.
VARIANT_EXPECTED = {
    'v1.2': ('twist-zero', 'on', 'off', 'off', 'pressure', None),
    'shen-tip': ('twist-zero', 'on', 'off', 'off', 'pressure', None),
    'dag-sorensen-tip': ('twist-zero', 'on', 'on', 'off', 'pressure', None),
    'ring-sampling': ('twist-zero', 'on', 'off', 'off', 'pressure', None),
    'du-selig-ra': ('twist-zero', 'on', 'off', 'on', 'pressure', None),
    'ch-ra': ('twist-zero', 'on', 'off', 'on', 'pressure', -3),
    'tip-pitch': ('tip', 'on', 'off', 'off', 'pressure', None),
    'tip-pitch-dag-sorensen': ('tip', 'off', 'on', 'off', 'pressure', None),
    'tip-pitch-no-tip': ('tip', 'off', 'off', 'off', 'pressure', None),
    'tip-pitch-du-selig-ra': ('tip', 'on', 'off', 'on', 'pressure', None),
    'tip-pitch-ch-ra': ('tip', 'on', 'off', 'on', 'pressure', -4.815),
    'v1.3': ('tip', 'off', 'on', 'off', 'total', None),
}


def test_every_registered_variant_is_pinned():
    assert set(VARIANT_EXPECTED) == set(yaml.safe_load(
        (ROOT / 'config/model-variants.yaml').read_text())['variants'])


@pytest.mark.parametrize('name', sorted(VARIANT_EXPECTED))
def test_variant_definitions_are_unchanged_on_the_v12_base(name):
    module = load_checker()
    reference, tip, correction, ra, polar, offset = VARIANT_EXPECTED[name]
    knobs = module.variant_definition(module.load_base_definition(), name)['knobs']
    definition = module.variant_definition(module.load_base_definition(), name)
    assert definition['pitch_reference'] == reference
    assert knobs['tipEffects']['expected'] == tip
    assert knobs['tipCorrection.active']['expected'] == correction
    assert knobs['rotationalAugmentation.active']['expected'] == ra
    assert knobs['polar']['expected'] == f'data/polars/S809_OSU_Re1M_{polar}.dat'
    assert knobs['rootEffects']['expected'] == 'on'
    if offset is None:
        assert 'rotationalAugmentation.pitchOffset' not in knobs
    else:
        assert knobs['rotationalAugmentation.pitchOffset']['expected'] == pytest.approx(offset)


@pytest.mark.parametrize('value,message', [
    ('data/polars/S809_OSU_Re1M_total.dat', 'invalid variant flag value: --polar=data/polars/S809_OSU_Re1M_total.dat'),
    ('S809_OSU_Re1M_total.txt', 'invalid variant flag value: --polar=S809_OSU_Re1M_total.txt'),
    ('S809_missing.dat', 'invalid variant flag value: --polar=S809_missing.dat'),
    ('.hidden.dat', 'invalid variant flag value: --polar=.hidden.dat'),
])
def test_registry_polar_flag_is_validated_like_the_runner(tmp_path, value, message):
    package = tmp_path / 'validation/phaseVI'
    shutil.copytree(ROOT, package, ignore=shutil.ignore_patterns('runs', 'results', '__pycache__'))
    path = package / 'config/model-variants.yaml'
    path.write_text(path.read_text().replace('--polar: S809_OSU_Re1M_total.dat', f'--polar: {value}'))
    (package / 'data/polars/.hidden.dat').write_text('')
    result = subprocess.run([sys.executable, str(package / 'scripts/checkModelDefinition.py'),
                             '--variant', 'v1.3', '--renderer-flags'],
                            capture_output=True, text=True, env=ENV)
    assert (result.returncode, result.stdout, result.stderr) == (2, '', f'error: {message}\n')


def test_v13_variant_preflight_needs_no_polar_environment():
    environment = {k: v for k, v in ENV.items() if k != 'POLAR'}
    result = subprocess.run(['sh', 'scripts/slurm/variant-run.slurm', '--check'], cwd=ROOT,
                            env={**environment, 'VARIANT': 'v1.3', 'SLURM_SUBMIT_DIR': str(ROOT)},
                            capture_output=True, text=True)
    assert (result.returncode, result.stdout, result.stderr) == (0, '', '')


def test_variant_run_launcher_passes_every_v12_knob_before_the_registry_flags():
    text = (ROOT / 'scripts/slurm/variant-run.slurm').read_text()
    command = text[text.index('exec scripts/runPhaseVI.sh'):]
    v12 = ['--polar "$POLAR"', '--tip-effects on', '--tip-correction off', '--root-effects on',
           '--rotational-augmentation off', '--pitch-reference twist-zero']
    assert all(token in command for token in v12)
    assert max(command.index(token) for token in v12) < command.index('"$@"')
    assert 'POLAR=${POLAR:-S809_OSU_Re1M_pressure.dat}' in text


@pytest.mark.parametrize('launcher', ['v1-2-run', 'v1-2-evaluation', 'v1-2-lag', 'v1-2-small-eps'])
def test_v12_launchers_pass_every_v12_knob_explicitly(launcher):
    text = (ROOT / f'scripts/slurm/{launcher}.slurm').read_text()
    command = text[text.index('exec scripts/runPhaseVI.sh'):]
    for token in ['--polar', '--tip-effects on', '--tip-correction off', '--root-effects on',
                  '--rotational-augmentation off', '--pitch-reference twist-zero']:
        assert token in command
    assert 'S809_OSU_Re1M_pressure.dat' in command or 'POLAR=${POLAR:-S809_OSU_Re1M_pressure.dat}' in text
