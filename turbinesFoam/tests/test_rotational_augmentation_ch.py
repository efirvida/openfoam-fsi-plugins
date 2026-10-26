# SPDX-License-Identifier: GPL-3.0-or-later
"""CH CLI contracts and a hand-computed reference for the stateful C++ hook."""
import json
import math
import shutil
import subprocess

import pytest

from test_model_variants import ENV, ROOT, call, render


def test_ch_render_constants_and_gate(tmp_path):
    case = render(tmp_path, 'ch-ra')
    for twin in ('ALM', 'ASM', 'ASM-MESH'):
        text = (case / f'system/fvOptions.{twin}').read_text()
        assert 'model ChaviaropoulosHansen;' in text
        assert 'a 2.2;' in text and 'h 1;' in text and 'n 4;' in text
        assert 'pitchOffset -3;' in text
    fv = case / 'system/fvOptions'
    before = fv.read_text()
    fv.write_text(before.replace('a 2.2;', 'a 2.3;'))
    result = call('scripts/checkModelDefinition.py', case, '--variant', 'ch-ra')
    assert (result.returncode, result.stdout, result.stderr) == (
        1, f'{case}: NON-CONFORMING ch-ra: rotationalAugmentation.a=2.3 (expected 2.2)\n', '')
    assert fv.read_text() == before.replace('a 2.2;', 'a 2.3;')


def test_explicit_du_selig_is_default(tmp_path):
    case = tmp_path / 'case'
    args = ('--case-dir', case)
    result = call('tools/generate_case.py', *args)
    assert result.returncode == 0, result.stderr
    before = {p.relative_to(case): p.read_bytes() for p in case.rglob('*') if p.is_file()}
    result = call('tools/generate_case.py', *args,
                  '--rotational-augmentation-model', 'DuSelig')
    assert result.returncode == 0, result.stderr
    assert {p.relative_to(case): p.read_bytes() for p in case.rglob('*') if p.is_file()} == before
    result = call('tools/generate_case.py', *args,
                  '--rotational-augmentation-model', 'ChaviaropoulosHansen')
    assert result.returncode == 0, result.stderr
    # Selecting a model is not activation.
    text = (case / 'system/fvOptions.ALM').read_text()
    assert 'active off;\n            model ChaviaropoulosHansen;' in text


@pytest.mark.parametrize('local_lib', [False, True])
def test_variant_launcher_library_and_forwarding(tmp_path, local_lib):
    package = tmp_path / 'package'
    (package / 'scripts/slurm').mkdir(parents=True)
    shutil.copytree(ROOT / 'config', package / 'config')
    shutil.copy(ROOT / 'scripts/checkModelDefinition.py', package / 'scripts')
    shutil.copy(ROOT / 'scripts/slurm/variant-run.slurm', package / 'scripts/slurm')
    runner = package / 'scripts/runPhaseVI.sh'
    runner.write_text('#!/usr/bin/env python3\nimport json, os, sys\n'
                      'print(json.dumps([os.environ["LD_LIBRARY_PATH"], sys.argv[1:]]))\n')
    runner.chmod(0o755)
    foam = tmp_path / 'foam'
    (foam / 'etc').mkdir(parents=True)
    (foam / 'etc/bashrc').write_text('# synthetic OpenFOAM environment\n')
    shell_env = tmp_path / 'bash-env'
    shell_env.write_text('module() { :; }\n')
    lib = tmp_path / 'local-lib'
    lib.mkdir()
    (lib / 'libturbinesFoam.so').write_text('')
    inherited_ld = ENV.get('LD_LIBRARY_PATH', '') + ':sentinel'
    env = {**ENV, 'VARIANT': 'ch-ra', 'MODEL': 'alm', 'SPEED': '7', 'SEQUENCE': 'S',
           'SLURM_SUBMIT_DIR': str(package), 'SLURM_NTASKS': '84',
           'BASH_ENV': str(shell_env), 'WM_PROJECT_DIR': str(foam),
           'WM_PROJECT_USER_DIR': str(tmp_path / 'user'), 'LD_LIBRARY_PATH': inherited_ld}
    env.pop('LIB_DIR', None)
    if local_lib:
        env['LIB_DIR'] = str(lib)
    result = subprocess.run(['bash', str(package / 'scripts/slurm/variant-run.slurm')],
                            env=env, capture_output=True, text=True)
    assert (result.returncode, result.stderr) == (0, '')
    # The launcher reports the prepended run-local library on the job's .out
    # before the runner starts; without LIB_DIR it reports nothing.
    lines = result.stdout.splitlines()
    if local_lib:
        assert lines[0] == f'Using run-local library {lib}'
        lines = lines[1:]
    else:
        assert not any(x.startswith('Using run-local library') for x in lines)
    ld, args = json.loads('\n'.join(lines))
    expected = f'{tmp_path}/user/platforms/linux64GccDPInt64Opt/lib:{foam}/platforms/linux64GccDPInt64Opt/lib:{foam}/platforms/linux64GccDPInt64Opt/lib/sys-openmpi:{inherited_ld}'
    assert ld == (str(lib) + ':' if local_lib else '') + expected
    i = args.index('--rotational-augmentation-model')
    assert args[i + 1] == 'ChaviaropoulosHansen'
    # Registry's on overrides the launcher's baseline off (last value wins).
    values = [args[i + 1] for i, x in enumerate(args[:-1]) if x == '--rotational-augmentation']
    assert values == ['off', 'on']
    assert not (package / 'runs').exists()


def test_runner_refuses_model_with_legacy_submit():
    result = subprocess.run(['bash', str(ROOT / 'scripts/runPhaseVI.sh'),
                             '-m', 'alm', '-u', '7', '--rotational-augmentation-model',
                             'ChaviaropoulosHansen', '--submit'],
                            capture_output=True, text=True, env=ENV)
    assert (result.returncode, result.stdout, result.stderr) == (
        2, '', 'ERROR: use scripts/slurm/variant-run.slurm for --rotational-augmentation-model\n')


def test_ch_reference_point():
    # Burgos Tafur 2020 pp.307-308 Eqs.(1)-(4), original constants only.
    # c/r=1/5, theta=60 degrees => f=2.2/5/16=0.0275.
    # Choose alpha-alpha0=1/(2*pi) radians, so Cl_inv=1.
    # Cl2D=.6, Cd2D=.1, Cd(alpha=0)=.02 => Cl3D=.611, Cd3D=.1022.
    # This is the reference the stateful C++ polar/geometry hook must match;
    # it is not an execution test of that hook.
    alpha_delta = 1 / (2 * math.pi)
    factor = 2.2 * (1 / 5) ** 1 * math.cos(math.radians(60)) ** 4
    assert factor == pytest.approx(0.0275)
    assert .6 + factor * (2 * math.pi * alpha_delta - .6) == pytest.approx(.611)
    assert .1 + factor * (.1 - .02) == pytest.approx(.1022)
