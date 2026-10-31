#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Summarize comparePhaseVI --out directories, grouped by sequence and speed.

Cells are percent error vs experiment, then change vs the matching baseline
error (default the version of record, config/model-definition.yaml; --baseline
picks another registry entry, e.g. v1.2) in percentage points. Baselines match
model, sequence and speed. Missing or
ambiguous baselines give n/a. Variant identity uses run.json variant, the default
var-<variant> label, or a unique conformance match. Custom labels on malformed
runs need run.json variant to identify their intended arm. Diagnostic only;
non-baseline arms are never of record. Exit 1 for unidentifiable/nonconforming
runs, 2 for unusable comparison input; DRIFT is marked without suppressing data.
"""
import argparse
import csv
import json
from pathlib import Path
import sys

from checkModelDefinition import load_base_definition, load_definition, load_variants, variant_definition, check_run

ROOT = Path(__file__).resolve().parents[1]
STATIONS = (0.30, 0.47, 0.63, 0.80, 0.95)


def identify(run, definitions):
    metadata = run / 'run.json'
    declared = json.loads(metadata.read_text()).get('variant') if metadata.exists() else None
    if declared is not None:
        return declared
    for name in sorted(definitions, key=len, reverse=True):
        if run.name == name or run.name.endswith('-var-' + name):
            return name
    matches = [name for name, definition in definitions.items() if not check_run(run, definition)]
    return matches[0] if len(matches) == 1 else 'UNKNOWN'


def rows(directory, definitions):
    data = json.loads((directory / 'metrics.json').read_text())
    turbine = list(csv.DictReader((directory / 'turbine_comparison.csv').open()))
    span = list(csv.DictReader((directory / 'spanwise_comparison.csv').open()))
    for model, entry in data['models'].items():
        run = Path(entry['run_dir'])
        if not run.is_absolute():
            run = ROOT / run
        try:
            name = identify(run, definitions)
            errors = check_run(run, definitions[name]) if name in definitions else ['unknown variant']
        except (OSError, ValueError, KeyError, TypeError) as exc:
            name, errors = 'UNKNOWN', [str(exc)]
        values = []
        for quantity in ('power', 'thrust'):
            matches = [float(r['delta_frac']) * 100 for r in turbine
                       if r['model'] == model and r['quantity'] == quantity]
            values.append(matches[0] if len(matches) == 1 else None)
        for station in STATIONS:
            matches = [float(r['dcn_frac']) * 100 for r in span
                       if r['model'] == model and round(float(r['r_over_R']), 2) == station]
            values.append(matches[0] if len(matches) == 1 else None)
        yield dict(group=(data['case']['sequence'], float(data['case']['speed_m_s'])),
                   model=model, variant=name, values=values, errors=errors,
                   drift=entry.get('drift', {}).get('flag', False), source=directory.name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dirs', nargs='+', type=Path)
    parser.add_argument('--baseline', help='registry entry used as baseline (default: the version of record)')
    args = parser.parse_args(argv)
    try:
        record = load_definition()['version']
        baseline_name = args.baseline or record
        base = load_base_definition()
        definitions = {name: variant_definition(base, name) for name in load_variants()}
        if baseline_name not in definitions:
            raise ValueError(f'unknown baseline: {baseline_name}')
        entries = [row for directory in args.dirs for row in rows(directory, definitions)]
        for group in sorted({r['group'] for r in entries}):
            print(f'== {group[0]} U{group[1]:g}')
            print('variant | model | P | T | ' + ' | '.join(f'cn{x:.2f}' for x in STATIONS)
                  + f' | status / source (errors %, change vs {baseline_name} in pp)')
            group_rows = [r for r in entries if r['group'] == group]
            for row in sorted(group_rows, key=lambda r: (r['variant'] != baseline_name, r['variant'], r['model'], r['source'])):
                baselines = [r for r in group_rows if r['variant'] == baseline_name
                             and r['model'] == row['model'] and not r['errors'] and not r['drift']]
                baseline = baselines[0]['values'] if len(baselines) == 1 else [None] * 7
                cells = ['n/a' if value is None else
                         f'{value:+.1f} (' + ('n/a' if ref is None else f'{value-ref:+.1f}') + ')'
                         for value, ref in zip(row['values'], baseline)]
                tags = ['NON-CONFORMING: ' + '; '.join(row['errors']) if row['errors'] else 'CONFORMS']
                if row['drift']:
                    tags.append('DRIFT')
                if row['variant'] != record or row['errors'] or row['drift']:
                    tags.append('[not of record]')
                print(' | '.join([row['variant'], row['model'], *cells, ' '.join(tags), row['source']]))
        return int(any(r['errors'] for r in entries))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
