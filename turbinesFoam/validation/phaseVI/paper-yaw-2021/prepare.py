#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare/audit four isolated Phase VI ALM dictionaries, never execute them."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sys

# Do not populate shared helper __pycache__ even when invoked without -B.
sys.dont_write_bytecode = True
PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parent
sys.path.insert(0, str(ROOT / 'tools'))
import case_config as cc
import element_data as ed
import generate_case as gen

CONFIG_SHA256 = '357924b7ab7a0cc738299e79f7498873ca6ff5c2643f6167e4fd776baea58d51'
BLOCKERS = [
    'Run blockMesh, snappyHexMesh and checkMesh under separate authorization; actual topology, spacing and cell count not obtained.',
    'Obtain measured Courant/time stability and temporal-convergence evidence; nominal estimates are NOT measured Co.',
    'Verify root SGC compatibility with unchanged cylinder polar: potential unsafe static polar-fit paths found by source inspection, NO runtime failure reproduced; also verify epsilon/sampling envelope.',
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return json.dumps(value, indent=2, sort_keys=True) + '\n'


def group_hash(files):
    return digest(encode(files).encode())


def read_spec(path):
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f'cannot read config: {path}') from exc
    # This is a frozen preparation specification, not a parameter sweep interface.
    # Byte validation also refuses unknown/duplicate keys, NaN and silent omissions.
    if digest(raw) != CONFIG_SHA256:
        raise ValueError('config does not match the supported preparation specification')
    return json.loads(raw)


def mesh_config(base, spec):
    cfg = copy.deepcopy(base)
    diameter = cfg['turbine']['diameter']
    cfg['domain_D'] = {'x': spec['x_extents_D'],
                       'y': [-12.2 / diameter, 12.2 / diameter],
                       'z_offset': [-18.3 / diameter, 18.3 / diameter]}
    cfg['mesh']['breaks_D'] = {'x': [-2, 8], 'y': [-12.2 / diameter, 12.2 / diameter],
                               'z': [-18.3 / diameter, 18.3 / diameter]}
    lengths = [10 * diameter, 24.4, 36.6]
    counts = [math.ceil(length / spec['base_max_width_m']) for length in lengths]
    cfg['mesh']['resolutions']['paper'] = {
        axis: {'cells': [n], 'grading': [1]} for axis, n in zip('xyz', counts)}
    cfg['mesh']['resolutions']['paper'].update(delta_t=spec['delta_t_s'], target_cells=[0, 1000000000])
    return cfg, [length / n for length, n in zip(lengths, counts)], counts


def render_mesh(cfg, spec):
    block = gen.render_block_mesh(cfg, 'paper', 'long', 'production')
    # Reuse existing castellation controls; replace only geometry and regions.
    snappy = gen.render_snappy_dict(cfg, 1)
    hub = cc.turbine_origin(cfg)
    geometry, regions = [], []
    for level, (low, high) in enumerate(spec['nested_boxes_hub_relative_m'], 1):
        minimum = [a + b for a, b in zip(low, hub)]
        maximum = [a + b for a, b in zip(high, hub)]
        geometry.append(f'    zone{level}\n    {{\n        type searchableBox;\n'
                        f'        min {cc.foam_vector(minimum)};\n        max {cc.foam_vector(maximum)};\n    }}')
        regions.append(f'        zone{level}\n        {{\n            mode inside;\n'
                       f'            levels ((1e15 {level}));\n        }}')
    start = snappy.index('geometry\n')
    end = snappy.index('castellatedMeshControls', start)
    snappy = snappy[:start] + 'geometry\n{\n' + '\n'.join(geometry) + '\n}\n\n' + snappy[end:]
    start = snappy.index('    refinementRegions\n')
    end = snappy.index('    locationInMesh', start)
    snappy = snappy[:start] + '    refinementRegions\n    {\n' + '\n'.join(regions) + '\n    }\n\n' + snappy[end:]
    # locationInMesh is inside the reconstructed domain; no solid surfaces exist.
    return {'system/blockMeshDict': block, 'system/snappyHexMeshDict': snappy,
            'system/topoSetDict': gen.render_toposet(cfg)}


def numerical_dicts(cfg):
    schemes = gen.render_fv_schemes(cfg).replace('default         backward;', 'default         CrankNicolson 0.9;')
    schemes = schemes.replace('div(phi,omega)', 'div(phi,epsilon)')
    schemes = schemes.replace('Gauss linear orthogonal', 'Gauss linear corrected').replace('default         orthogonal;', 'default         corrected;')
    solution = gen.render_fv_solution(cfg).replace('omega', 'epsilon')
    solution = solution.replace('solver          smoothSolver;\n        smoother        symGaussSeidel;',
                                'solver          PBiCG;\n        preconditioner  DILU;')
    # The shared regex transport group has no literal U dictionary to inherit.
    solution = solution.replace('$U;', 'solver PBiCG;\n        preconditioner DILU;')
    solution = solution.replace('nNonOrthogonalCorrectors   0;', 'nNonOrthogonalCorrectors   2;')
    return {'system/fvSchemes': schemes, 'system/fvSolution': solution,
            'constant/transportProperties': gen.render_transport_properties(cfg),
            'constant/turbulenceProperties': gen.render_turbulence_properties(cfg)}


def epsilon_field(cfg, speed):
    k = cc.inflow_fields(cfg, speed)['k']
    length = cfg['inflow']['mixing_length_D'] * cfg['turbine']['diameter']
    epsilon = .09 ** .75 * k ** 1.5 / length
    text = gen.render_field_uniform(cfg, speed, 'k')
    text = text.replace('object      k;', 'object      epsilon;')
    text = text.replace('[0 2 -2 0 0 0 0]', '[0 2 -3 0 0 0 0]')
    text = text.replace(f'{k:.8g}', f'{epsilon:.8g}')
    return text, epsilon


def render_arm(cfg, spec, speed, arm, directory):
    cfg = copy.deepcopy(cfg)
    cfg['solver']['turbulence_model'] = 'realizableKE'
    cfg['kinematics']['sequence'] = 'S'
    cfg['inflow']['velocity'] = speed
    cfg['sequence_s']['speeds'][speed] = {
        'tsr': cc.tsr_from_rpm(spec['rpm'], speed, cfg['turbine']['radius']),
        'rotor_speed_rpm': spec['rpm'], 'row': f's{speed:02d}00000 (paper nominal RPM override)'}
    if arm == 'paper-like':
        cfg['actuator']['dynamic_stall'] = {'active': True, 'model': 'LeishmanBeddoesSGC'}
        cfg['actuator']['end_effects'].update(model='Shen', root=False)
        cfg['actuator']['velocity_sampling'] = {'velocity_sample_radius': 1, 'n_velocity_samples': 16}
    # The helper's legacy uniform-grading cell-size check has no grading=1
    # branch. Use its original mesh solely for its internal timestep guard;
    # the retained report independently checks the reconstructed rotor spacing.
    helper_cfg = copy.deepcopy(cfg)
    helper_cfg['mesh'] = copy.deepcopy(cc.load_config()['mesh'])
    helper_cfg['mesh']['resolutions']['coarse']['delta_t'] = spec['delta_t_s']
    foam = gen.render_fv_options(helper_cfg, str(speed), 'coarse', directory, gen.ALM_ELEMENT, sequence='S')
    if arm == 'paper-like':
        lines = []
        for key, value in spec['sgc_coefficients'].items():
            literal = str(value).lower() if isinstance(value, bool) else f'{value:g}'
            lines.append(f'                {key} {literal};')
        lines = '\n'.join(lines)
        anchor = '            dynamicStallModel LeishmanBeddoesSGC;'
        foam = foam.replace(anchor, anchor + '\n            LeishmanBeddoesSGCCoeffs\n            {\n' + lines + '\n            }')
    # Source defaults are off; spell these out at the rotor level for auditability.
    # rhoRef is the source's compressible-normalization key. Its incompressible
    # addSup overload uses per-unit-density forces and does not consume this key.
    foam = foam.replace('        azimuthalOffset 0;',
                        f"        rhoRef {cfg['inflow']['reference_density_kg_m3']:.8g};\n"
                        '        addedMass false;\n        flowCurvature { active false; }\n        azimuthalOffset 0;')
    epsilon, value = epsilon_field(cfg, str(speed))
    files = {'system/fvOptions': foam, 'case-config.json': encode(cfg),
             'system/controlDict': gen.render_control_dict(helper_cfg, str(speed), 'coarse', 'production', None, 'startTime', 'S'),
             'system/decomposeParDict': gen.render_decompose_par(cfg), '0.org/epsilon': epsilon}
    files.update({f'0.org/{field}': gen.render_field_uniform(cfg, str(speed), field)
                  for field in ('U', 'p', 'k', 'nut')})
    return files, cfg, value


def plan(spec, output, config):
    base = cc.load_config()
    cfg, widths, counts = mesh_config(base, spec)
    cfg['solver']['turbulence_model'] = 'realizableKE'
    cfg['inflow']['kinematic_viscosity'] = spec['kinematic_viscosity_m2_s']
    # The shared schema has no density input for incompressible rendering;
    # retain this explicit extension for reference/report normalization metadata.
    cfg['inflow']['reference_density_kg_m3'] = spec['reference_density_kg_m3']
    mesh = render_mesh(cfg, spec)
    numerics = numerical_dicts(cfg)
    rotor_widths = [width / 8 for width in widths]
    # Nominal count ignores cut-cell alignment and transition buffering, not measured.
    volumes = [math.prod([b - a for a, b in zip(low, high)])
               for low, high in spec['nested_boxes_hub_relative_m']]
    nominal = math.prod(counts)
    for level, volume in enumerate(volumes, 1):
        nominal += volume / math.prod(widths) * (8 ** level - 8 ** (level - 1))
    chord_max = max(row['chord'] for row in cc.read_blade())
    envelope = max(.25 * chord_max, chord_max, 2 * math.prod(rotor_widths) ** (1 / 3))
    low, high = spec['nested_boxes_hub_relative_m'][-1]
    radius = cfg['turbine']['radius']
    if not (low[0] < -envelope and high[0] > envelope and
            all(low[i] < -radius - envelope and high[i] > radius + envelope for i in (1, 2))):
        raise ValueError('finest region does not contain assumed rotor sampling envelope')
    if spec['rpm'] * 2 * math.pi / 60 * radius * spec['delta_t_s'] >= min(rotor_widths):
        raise ValueError('tip displacement reaches planned minimum rotor spacing')
    report = {'execution_ready': False, 'blockers': BLOCKERS, 'assumptions': spec['assumptions'],
              'sequence': 'S', 'rpm': spec['rpm'], 'delta_t_s': spec['delta_t_s'],
              'fluid': {'kinematic_viscosity_m2_s': cfg['inflow']['kinematic_viscosity'],
                        'reference_density_kg_m3': cfg['inflow']['reference_density_kg_m3'],
                        'density_used_by_incompressible_ALM': False,
                        'density_usage': 'Published reference metadata; fvOptions rhoRef is read only by the compressible overload. Incompressible ALM forces remain per unit density; no performance recomputation.'},
              'mesh': {'topology': spec['topology'], 'polyMesh_exists': False,
                       'bounds_hub_relative_m': [[-2 * cfg['turbine']['diameter'], -12.2, -18.3],
                                                 [8 * cfg['turbine']['diameter'], 12.2, 18.3]],
                       'nested_boxes_hub_relative_m': spec['nested_boxes_hub_relative_m'],
                       'base_cells_xyz': counts, 'zone_widths_m': [[w / 2 ** level for w in widths] for level in range(4)],
                       'rotor_cell_widths_m': rotor_widths, 'nominal_cell_count_NOT_measured': round(nominal),
                       'sampling_envelope_m_assuming_abs_Cd_le_2': envelope,
                       'actual_cell_count': None, 'actual_spacing_m': None}, 'cases': {}}
    # Only actual rendering inputs: baseline case/logs and the model-definition
    # document are not read to render and must not make this audit machine-local.
    inputs = [ROOT / 'config/case.yaml', cc.BLADE_CSV,
              cc.POLARS_DIR / 'S809_OSU_Re1M_pressure.dat', config, Path(__file__)]
    inputs += [ROOT / 'tools' / name for name in
               ('case_config.py', 'element_data.py', 'blade_resample.py', 'generate_case.py')]
    report['input_sha256'] = {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p): digest(p.read_bytes()) for p in inputs}
    rendered = {}
    for speed in spec['speeds_m_s']:
        for arm in spec['arms']:
            name = f'U{speed}-{arm}'
            files, isolated, epsilon = render_arm(cfg, spec, speed, arm, output / name)
            # Stable audit order starts with the shared mesh contract.
            files = {**mesh, **numerics, **files}
            # Correct the shared renderer banner: these are isolated overrides.
            files = {key: value.replace('Generated from config/case.yaml.',
                     'Generated by paper-yaw-2021/prepare.py from frozen inputs and isolated overrides.')
                     for key, value in files.items()}
            rendered.update({f'{name}/{key}': value for key, value in files.items()})
            omega = spec['rpm'] * 2 * math.pi / 60
            displacement = omega * radius * spec['delta_t_s']
            report['cases'][name] = {'mesh_hash': group_hash(mesh), 'numerics_hash': group_hash(numerics),
                'effective_tsr': cc.select_speed(isolated, speed, 'S')['tsr'],
                'angular_step_deg': spec['rpm'] * 6 * spec['delta_t_s'], 'tip_displacement_m': displacement,
                'tip_displacement_over_min_h': displacement / min(rotor_widths),
                'nominal_advective_Co_NOT_measured': speed * spec['delta_t_s'] / min(rotor_widths),
                'epsilon_inflow': epsilon, 'k_inflow': cc.inflow_fields(cfg, speed)['k'],
                'sampling_radius_epsilon_units': 1 if arm == 'paper-like' else 0,
                'dictionary_sha256': {key: digest(value.encode()) for key, value in files.items()}}
    report['common_mesh_specification_sha256'] = group_hash(report['mesh'])
    rendered['report.json'] = encode(report)
    rendered['preparation-config.json'] = config.read_text()
    return rendered, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False,
        epilog='Success is a configuration audit, NOT execution approval. Errors: exit 1 missing/changed output; exit 2 invalid config, path or CLI. No run/submit/force capability.')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true', help='write four cases only to absent/empty output; print Prepared 4 cases; execution_ready=false.')
    mode.add_argument('--check', action='store_true', help='read-only exact audit; print Configuration audit passed; execution_ready=false.')
    mode.add_argument('--report', action='store_true', help='read-only exact audit then print sorted JSON report')
    parser.add_argument('--output', type=Path, required=True, help='isolated output directory (required)')
    parser.add_argument('--config', type=Path, default=PACKAGE / 'config.json', help='frozen specification, byte-identical copies only (default: adjacent config.json)')
    args = parser.parse_args(argv)
    try:
        spec = read_spec(args.config)
        output = args.output.absolute()
        if any(p.is_symlink() for p in (output, *output.parents)):
            raise ValueError('symlink output paths are not allowed')
        if args.prepare and output.exists() and (not output.is_dir() or any(output.iterdir())):
            raise ValueError('output must be absent or an empty directory')
        files, report = plan(spec, output, args.config.absolute())
        if not args.prepare:
            if output.exists() and any(p.is_symlink() for p in output.rglob('*')):
                print('error: unexpected output entries', file=sys.stderr)
                return 1
            for relative, expected in files.items():
                path = output / relative
                if path.is_symlink() or not path.is_file() or path.read_bytes() != expected.encode():
                    print(f'error: missing or changed output: {relative}', file=sys.stderr)
                    return 1
            actual = {str(p.relative_to(output)) for p in output.rglob('*') if p.is_file() or p.is_symlink()}
            if actual != set(files):
                print('error: unexpected output entries', file=sys.stderr)
                return 1
            print(encode(report), end='') if args.report else print('Configuration audit passed; execution_ready=false.')
        else:
            # All input validation/rendering completes before the first write.
            for relative, content in files.items():
                path = output / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('x', encoding='utf-8') as stream:
                    stream.write(content)
            print('Prepared 4 cases; execution_ready=false.')
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
