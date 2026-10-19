#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check Phase VI run directories against effective Model Definition v1.2.

Usage: python3 scripts/checkModelDefinition.py RUN_DIR [RUN_DIR ...]
       [--definition PATH]
Exit 0: all conform; 1: mismatches; 2: unreadable/malformed input.
`check_run(run_dir, definition)` returns every mismatch without writing files;
`definition` is the mapping returned by `load_definition`.

Absent dictionary keys use the YAML's cited solver defaults, never the expected
value. Unknown defaults fail closed. nVelocitySamples is inert for the frozen
point sampling. The parser handles comments, nested dictionaries, lists and
local $blade1 inheritance; it does not execute OpenFOAM directives or includes.
Only the polar include path is inspected, not the included data. Unsupported
syntax fails rather than silently certifying a run.

meshFactor must equal 2**refine_level: run.json takes precedence, otherwise the
runner's -r<N> name token is used (also before a run label), defaulting to 0.
blade_dz is checked only when non-null metadata is recorded; geometry is not
inferred from the committed non-equispaced render.
"""
import argparse
import copy
import json
import math
from pathlib import Path
import re
import sys

import yaml

DEFAULT_DEFINITION = Path(__file__).resolve().parents[1] / "config/model-definition.yaml"


def load_definition(path=DEFAULT_DEFINITION):
    definition = yaml.safe_load(Path(path).read_text())
    if not isinstance(definition, dict) or not isinstance(definition.get("knobs"), dict):
        raise ValueError("definition must contain a knobs mapping")
    return definition


FLAG_RULES = {
    '--end-effects-model': 'endEffectsModel',
    '--tip-correction': 'tipCorrection.active',
    '--rotational-augmentation': 'rotationalAugmentation.active',
    '--velocity-sample-radius': 'velocitySampleRadius',
    '--n-velocity-samples': 'nVelocitySamples',
}


def load_variants():
    registry = yaml.safe_load((DEFAULT_DEFINITION.parent / 'model-variants.yaml').read_text())
    variants = registry['variants']
    for name, entry in variants.items():
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', name):
            raise ValueError(f'invalid variant name: {name}')
        for flag, value in entry['flags'].items():
            if flag not in FLAG_RULES:
                raise ValueError(f'unsupported variant flag: {flag}')
            if flag == '--end-effects-model':
                valid = value in ('Glauert', 'Shen', 'liftingLine')
            elif flag in ('--tip-correction', '--rotational-augmentation'):
                valid = value in ('on', 'off')
            else:
                valid = (isinstance(value, (int, float)) and not isinstance(value, bool)
                         and math.isfinite(value) and value >= 0)
                if flag == '--n-velocity-samples':
                    valid = valid and isinstance(value, int) and value > 0
            if not valid:
                raise ValueError(f'invalid variant flag value: {flag}={value}')
    return variants


def variant_definition(definition, name):
    variants = load_variants()
    if name not in variants:
        raise ValueError(f'unknown variant: {name}')
    result = copy.deepcopy(definition)
    result['version'] = name
    knobs = result['knobs']
    for flag, value in variants[name]['flags'].items():
        rule = knobs[FLAG_RULES[flag]]
        rule['expected'] = value
        rule.pop('inert', None)
    # Constants become active with their correction, so certify them as well.
    def add(path, value, default=None):
        knobs[path] = dict(path=path, expected=value, solver_default=default)
    if knobs['endEffectsModel']['expected'] == 'Shen':
        for key in ('tipEffects', 'rootEffects'):
            knobs[key]['path'] = 'endEffects.ShenCoeffs.' + key
        add('endEffects.ShenCoeffs.c1', 0.125)
        add('endEffects.ShenCoeffs.c2', 21)
    if knobs['rotationalAugmentation.active']['expected'] == 'on':
        add('rotationalAugmentation.model', 'DuSelig', 'DuSelig')
        for key in ('a', 'b', 'd'):
            add('rotationalAugmentation.' + key, 1, 1)
    if knobs['tipCorrection.active']['expected'] == 'on':
        for key, value in [('model', 'DagSorensen'), ('wakeTurns', 2),
                           ('wakeAzimuthalStep', 2), ('epsilon', 0)]:
            add('tipCorrection.' + key, value, value)
    return result


def parse_dictionary(text):
    """Parse dictionary structure, retaining list values as token lists."""
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|/\*.*?\*/|//[^\n]*|[{}();]|[^\s{}();]+',
                        text, re.DOTALL)
    tokens = [t for t in tokens if not t.startswith(("/*", "//"))]
    pos = 0

    def block(nested=False):
        nonlocal pos
        result = {}
        while pos < len(tokens):
            key = tokens[pos]
            pos += 1
            if key == "}":
                if not nested:
                    raise ValueError("unexpected closing brace")
                return result
            if key.startswith("$"):
                parent = result.get(key[1:])
                if parent is None:
                    # Local inheritance is resolved by the containing block below.
                    result[key] = None
                else:
                    result.update(parent)
                if pos < len(tokens) and tokens[pos] == ";":
                    pos += 1
                continue
            if pos >= len(tokens):
                raise ValueError(f"missing value for {key}")
            if tokens[pos] == "{":
                pos += 1
                value = block(True)
                for inherited in [k for k in value if k.startswith("$")]:
                    source = result.get(inherited[1:])
                    if not isinstance(source, dict):
                        raise ValueError(f"unsupported inheritance {inherited}")
                    value = {**source, **{k: v for k, v in value.items() if k != inherited}}
            else:
                value = []
                depth = 0
                while pos < len(tokens):
                    token = tokens[pos]
                    pos += 1
                    if token == ";" and depth == 0:
                        break
                    if token == "(":
                        depth += 1
                    elif token == ")":
                        depth -= 1
                    if token in ("{", "}") or depth < 0:
                        raise ValueError(f"invalid value for {key}")
                    value.append(token)
                else:
                    raise ValueError(f"unterminated value for {key}")
                value = value[0].strip('"') if len(value) == 1 else value
            if key in result:
                raise ValueError(f"duplicate key {key}")
            result[key] = value
        if nested:
            raise ValueError("unclosed dictionary")
        return result

    return block()


def lookup(tree, path):
    for key in path.split("."):
        if not isinstance(tree, dict):
            return None
        tree = tree.get(key)
    return tree


def display(value):
    if isinstance(value, bool):
        return "on" if value else "off"
    return f"{value:g}" if isinstance(value, (int, float)) else str(value)


def equal(found, expected):
    if isinstance(expected, bool) or expected in ("on", "off"):
        aliases = {"true": "on", "yes": "on", "1": "on",
                   "false": "off", "no": "off", "0": "off"}
        a, b = display(found), display(expected)
        return aliases.get(a, a) == aliases.get(b, b)
    if isinstance(expected, (int, float)):
        try:
            return math.isclose(float(found), expected, rel_tol=1e-9, abs_tol=1e-12)
        except (TypeError, ValueError):
            return False
    return found == expected


def check_run(run_dir, definition):
    """Return mismatches; raise OSError/ValueError for unusable input."""
    run_dir = Path(run_dir)
    tree = parse_dictionary((run_dir / "system/fvOptions").read_text())
    coeffs = lookup(tree, definition["coefficients"])
    if not isinstance(coeffs, dict):
        raise ValueError(f"missing coefficients dictionary {definition['coefficients']}")
    metadata_path = run_dir / "run.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    if not isinstance(metadata, dict):
        raise ValueError("run.json must contain an object")
    match = re.search(r"-r(\d+)(?:-|$)", run_dir.name)
    level = metadata.get("refine_level", int(match[1]) if match else 0)
    if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level <= 30:
        raise ValueError("refine_level must be an integer between 0 and 30")
    mismatches = []
    for name, rule in definition["knobs"].items():
        if rule.get("inert"):
            continue
        expected = rule["expected"]
        if rule.get("scale_with_refinement"):
            expected *= 2 ** level
        path = rule["path"]
        if "*" in path:
            prefix, suffix = path.split(".*.")
            branches = lookup(coeffs, prefix)
            if not isinstance(branches, dict) or not branches:
                mismatches.append(f"{name}=ABSENT (no solver default known)")
                continue
            values = [lookup(branch, suffix) for branch in branches.values()
                      if not rule.get("element_type") or
                      branch.get("elementType") == rule["element_type"]]
        else:
            values = [lookup(coeffs, path)]
        for found in values:
            if found is None:
                found = rule["solver_default"]
            if found is None:
                message = f"{name}=ABSENT (no solver default known)"
            elif rule.get("comparison") == "include_suffix":
                includes = [str(v).strip('"') for v in found] if isinstance(found, list) else []
                found = includes[includes.index("#include") + 1] if "#include" in includes else display(found)
                if found.endswith(expected):
                    continue
                message = f"{name}={found} (expected suffix {expected})"
            elif equal(found, expected):
                continue
            else:
                message = f"{name}={display(found)} (expected {display(expected)})"
            if message not in mismatches:
                mismatches.append(message)
    for name, rule in definition.get("metadata", {}).items():
        found = metadata.get(name)
        if found is not None and not equal(found, rule["expected"]):
            mismatches.append(f"{name}={display(found)} (expected {display(rule['expected'])})")
    return mismatches


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="*", type=Path)
    parser.add_argument('--variant', help='check a named A/B arm, never of record for v1.2')
    parser.add_argument('--renderer-flags', action='store_true',
                        help='print validated variant override tokens, one per line; no run required')
    parser.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    args = parser.parse_args(argv)
    status = 0
    try:
        definition = load_definition(args.definition)
        if args.variant is not None:
            definition = variant_definition(definition, args.variant)
        if args.renderer_flags:
            if args.variant is None:
                raise ValueError('--renderer-flags requires --variant')
            for flag, value in load_variants()[args.variant]['flags'].items():
                print(flag)
                print(value)
            return 0
        if not args.run_dirs:
            parser.error('at least one run directory is required')
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for run in args.run_dirs:
        try:
            mismatches = check_run(run, definition)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"error: {run}: {exc}", file=sys.stderr)
            status = 2
            continue
        verdict = (f"NON-CONFORMING {definition['version']}: " + "; ".join(mismatches)
                   if mismatches else f"CONFORMS {definition['version']}")
        print(f"{run}: {verdict}")
        if mismatches and status == 0:
            status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
