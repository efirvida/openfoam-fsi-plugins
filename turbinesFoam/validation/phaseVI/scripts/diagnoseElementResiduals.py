#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only Phase VI element residual diagnosis (no solver or output files).

Run from validation/phaseVI:
    python3 scripts/diagnoseElementResiduals.py [--alm-dir runs/alm-U7-coarse-d1-pdrag]

Uses compareSectionLoads' convergence gate and configured revolution window.
Blocks: (a) station interpolation, (b) one-step Glauert lag when the appended
end_effect_phi_deg column exists, (c) normalisation, (d) frozen-inflow
first-order polar/Re sensitivity. Block (b) reports tip-element means over the
convergence window of consecutive rows: lag = phi(t) - phi(t+1) and the factor
recomputed with phi(t+1) (the angle sampled at t) versus the written factor.
`inflow_ref_angle_deg` is a 3-D angle against the chord reference direction, a
different definition from the factor's rotor-plane phi, so it is not subtracted.
Uncomputed end-effect angles (end effects off/liftingLine) are NaN, not zero.
The factor-free reconstruction is a diagnostic, not a replacement load model.
Reynolds sensitivity holds alpha, drag, end factor and sampled velocity fixed;
CSU versus OSU also changes facility, so it is not a pure Reynolds correction.
"""
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path
from statistics import mean

import comparePhaseVI as comparison
from compareSectionLoads import (
    CUT, QNORM, R, STATIONS, angle_from_pair, chord_at, converged_window,
    element_number, read_density, read_experiment,
)
from closeExperimentIntegral import case_chord
from quantifyPolarReScaling import interp, read_polar


def glauert_factor(root_dist, phi, blades=2, root_effects=False,
                   radius=R, cut=CUT):
    """Solver Glauert tip times optional Prandtl hub factor; phi in radians.

    root_dist is blade-arc fraction from the cutout, NOT r/R. This is the
    straight-blade mapping of actuatorLineSource::createElements.
    """
    sine = math.sin(phi)
    if not 0 < root_dist <= 1 or sine <= 0:
        raise ValueError("Glauert requires 0 < root_dist <= 1 and sin(phi) > 0")
    tip = 2 / math.pi * math.acos(math.exp(-blades / 2 * (1 / root_dist - 1) / sine))
    if root_effects:
        local_r = cut + root_dist * (radius - cut)
        tip *= 2 / math.pi * math.acos(
            math.exp(-blades / 2 * (local_r - cut) / cut / sine)
        )
    return tip


def bracket(profile, station):
    """Return enclosing rows of a sorted (r/R, ...) profile; no extrapolation."""
    if not profile or not profile[0][0] <= station <= profile[-1][0]:
        raise ValueError(f"station {station:g} outside element span")
    for left, right in zip(profile, profile[1:]):
        if left[0] <= station <= right[0]:
            return left, right
    raise ValueError("at least two elements required")


def station_values(profile, station):
    """Interpolate through the established comparison implementation."""
    bracket(profile, station)
    return comparison.interpolate(profile, station)


def normalisation_ratio(qnorm, rho, speed):
    """Experimental pressure / simulated sampled-relative dynamic pressure."""
    return qnorm / (0.5 * rho * speed**2)


def polar_cl(path, alpha):
    """Use the existing single-Re reader and linear table interpolation."""
    alphas, cls = read_polar(path)
    if not alphas or not alphas[0] <= alpha <= alphas[-1]:
        raise ValueError(f"{path}: alpha outside polar range")
    return interp(alpha, alphas, cls)


def multi_re_cls(path, alpha):
    """Read committed OpenFOAM multiRe lift table; no extrapolation in Re."""
    text = re.sub(r"//[^\n]*", "", path.read_text())
    levels = [float(x) for x in re.search(r"ReList\s*\((.*?)\);", text, re.S)[1].split()]
    block = re.search(r"clData\s*\((.*?)\);", text, re.S)[1]
    rows = sorted(tuple(map(float, row.split()))
                  for row in re.findall(r"\(([^()]*)\)", block))
    return list(zip(levels, station_values(rows, alpha)))


def element_data(run_dir, start, end):
    """Read blade 1 once; reuse the row-wise chord-frame reconstruction."""
    elements = [(path, rows) for path, rows in comparison.read_elements(
        run_dir / comparison.ELEMENT_DIR) if "blade1.element" in path.name]
    windows = [(path, [r for r in rows if start <= r['time'] <= end])
               for path, rows in elements]
    if not windows or any(not rows for _, rows in windows):
        raise ValueError("missing blade-1 samples in averaging window")
    chord_profile = comparison.spanwise_profile(windows, start, end, False, R)
    cn_by_radius = {row[0]: row[1] for row in chord_profile}
    profile, samples = [], {}
    for path, rows in windows:
        avg = lambda key: mean(float(row[key]) for row in rows)
        rr = comparison.r_over_r_from_root_dist(
            comparison.mean([float(row['root_dist']) for row in rows]), R)
        # Keep sentinel/blended elements: bracketing is geometric, not filtered.
        factor = avg('end_effect_factor') if 'end_effect_factor' in rows[0] else math.nan
        speed = avg('rel_vel_mag') if 'rel_vel_mag' in rows[0] else math.nan
        phi = mean(angle_from_pair(row['c_ref_n'], row['c_ref_t'], row['cl'], row['cd'])
                   for row in rows)
        free_cl = (mean(row['cl'] / row['end_effect_factor'] for row in rows)
                   if math.isfinite(factor) and all(row['end_effect_factor'] > 0 for row in rows)
                   else math.nan)
        profile.append((rr, avg('cl'), avg('cd'), avg('alpha_deg'), factor,
                        cn_by_radius[rr], speed, phi, free_cl))
        samples[rr] = (element_number(str(path)), rows)
    return sorted(profile), samples


def report_glauert_lag(samples, blades, root_effects):
    """One-step lag of the Glauert factor for tip elements (r/R >= 0.85).

    `end_effect_phi_deg` at step t is the angle the factor written at t was
    evaluated with (sampled one step earlier); the value stored at t+1 is the
    angle sampled at t, with the identical rotor-plane definition. So per
    consecutive pair: lag = phi(t) - phi(t+1), and the same-step factor at t is
    the Glauert factor of phi(t+1).
    """
    tips = [(rr, number, rows) for rr, (number, rows) in sorted(samples.items())
            if rr >= 0.85]
    if any('end_effect_phi_deg' not in row for _, _, rows in tips for row in rows):
        # Preserve the historical report for CSVs predating the angle column.
        print('  SKIPPED: CSV exposes rel_vel_mag, but no relative-velocity vector/components.')
        print('  Cannot obtain atan2(W_axis, W_opposite_element_velocity) from magnitude alone.')
        print('  No mean/max relative difference claimed; recovered force angle is not sampled velocity.')
        return
    print('  element  r/R       lag_mean[deg] F_same_step F_written delta_F')
    for rr, number, rows in tips:
        rows = sorted(rows, key=lambda row: row['time'])
        if len(rows) < 2 or any(not math.isfinite(row[key]) for row in rows
                                for key in ('end_effect_phi_deg', 'end_effect_factor')):
            print(f'  element{number} {rr:.6f} SKIPPED: non-finite end-effect angle or factor.')
            continue
        pairs = list(zip(rows, rows[1:]))
        try:
            same_step = mean(glauert_factor(now['root_dist'], math.radians(nxt['end_effect_phi_deg']),
                                            blades, root_effects) for now, nxt in pairs)
        except ValueError:
            print(f'  element{number} {rr:.6f} SKIPPED: angle outside Glauert domain.')
            continue
        lag = mean(now['end_effect_phi_deg'] - nxt['end_effect_phi_deg'] for now, nxt in pairs)
        written = mean(now['end_effect_factor'] for now, _ in pairs)
        print(f'  element{number} {rr:.6f} {lag:+14.6f} {same_step:.6f} '
              f'{written:.6f} {same_step - written:+.6f}')


def rebuilt_cn(cl, cd, alpha):
    """Use comparePhaseVI for even counterfactual chord-frame conversion."""
    rows = [{'time': 0.0, 'root_dist': 0.5, 'alpha_deg': alpha, 'cl': cl, 'cd': cd}]
    return comparison.spanwise_profile([(Path('counterfactual'), rows)], 0, 0, False, R)[0][1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--alm-dir', type=Path, default=Path('runs/alm-U7-coarse-d1-pdrag'))
    parser.add_argument('--speed', type=float, default=7.0)
    parser.add_argument('--sequence', choices=('H', 'S'), default='H')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    start, end, info = converged_window(args.alm_dir, args.speed, args.sequence)
    experiment = read_experiment(root / 'data/experiment', args.speed, args.sequence)
    rho = read_density(root / 'data/experiment', args.speed, args.sequence)
    cfg = comparison.load_config(comparison.DEFAULT_CONFIG)
    nu = float(cfg['inflow']['kinematic_viscosity'])
    blades = int(cfg['turbine']['n_blades'])
    options = (args.alm_dir / 'system/fvOptions').read_text()
    if not re.search(r'endEffectsModel\s+Glauert\s*;', options):
        raise ValueError('this diagnostic requires a Glauert run')
    root_effects = bool(re.search(r'rootEffects\s+(on|true|yes)\s*;', options))
    profile, samples = element_data(args.alm_dir, start, end)
    print(f'run {args.alm_dir} | sequence {args.sequence} U={args.speed:g} m/s')
    print(f"window rev {info['discard_revolutions']}..{info['end_revolutions']} "
          f't=[{start:.6f}, {end:.6f}] s; drift=False; blade1 elements={len(profile)}')
    print(f'rho={rho:.6f} kg/m3 (experiment); nu={nu:g} m2/s (config); hub loss={root_effects}')
    print('\n(a) Station interpolation: time means; cn is chord-referenced per row')
    print('  label       r/R       cl       cd    alpha       F       cn    cn_exp')
    for station in (0.30, 0.95):
        for row in bracket(profile, station):
            number = samples[row[0]][0]
            print(f'  element{number:<3} {row[0]:.6f} {row[1]:8.5f} {row[2]:8.5f} '
                  f'{row[3]:8.4f} {row[4]:7.5f} {row[5]:8.5f} {experiment[station][0]:8.5f}')
        values = station_values(profile, station)
        cl, cd, alpha, factor, cn, speed, phi, free_cl = values
        print(f'  station    {station:.6f} {cl:8.5f} {cd:8.5f} {alpha:8.4f} '
              f'{factor:7.5f} {cn:8.5f} {experiment[station][0]:8.5f} '
              f'({100 * (cn / experiment[station][0] - 1):+.2f}%)')
        if math.isfinite(free_cl):
            f_station = glauert_factor((station * R - CUT) / (R - CUT), phi,
                                       blades, root_effects)
            counter = rebuilt_cn(free_cl * f_station, cd, alpha)
            print(f'  factor-free @ {station:.2f}: F(station)={f_station:.6f}, cn={counter:.6f}; '
                  f'change={100 * (counter / cn - 1):+.3f}%, residual='
                  f'{100 * (counter / experiment[station][0] - 1):+.3f}%')
        else:
            print(f'  factor-free @ {station:.2f}: skipped (missing/zero end_effect_factor)')
    print('  F(station) uses mean phi recovered from plane cn/ct + cl/cd; not a lag measurement.')

    print('\n(b) Glauert-factor lag: same-step sampled relative velocity')
    report_glauert_lag(samples, blades, root_effects)

    print('\n(c) Normalisation: same simulated force, local q versus experimental QNORM')
    print('  r/R    W[m/s] QNORM[Pa] q_sim[Pa]   ratio  cn_local cn_QNORM cn_exp  residual_Q[%]')
    for station in STATIONS:
        values = station_values(profile, station)
        cn, speed = values[4:6]
        ratio = normalisation_ratio(QNORM[station], rho, speed)
        renorm = cn / ratio
        print(f'  {station:.2f} {speed:9.4f} {QNORM[station]:9.3f} '
              f'{0.5 * rho * speed**2:9.3f} {ratio:7.5f} {cn:9.5f} {renorm:8.5f} '
              f'{experiment[station][0]:7.5f} {100 * (renorm / experiment[station][0] - 1):+9.3f}')
    print('  W is the interpolated element time-mean |W|; q_sim=0.5*rho*W^2 (not mean q).')

    print('\n(d) First-order Reynolds sensitivity at r/R=0.30 (fixed inflow, cd and F)')
    cl, cd, alpha, factor, cn, speed, phi, free_cl = station_values(profile, 0.30)
    chord = chord_at(0.30 * R, case_chord(args.alm_dir))
    reynolds = speed * chord / nu
    print(f'  alpha={alpha:.5f} deg; W={speed:.5f} m/s; chord={chord:.6f} m; Re={reynolds:.0f}')
    polars = root / 'data/polars'
    base = polar_cl(polars / 'S809_OSU_Re1M_pressure.dat', alpha)
    base_cn = rebuilt_cn(base * factor, cd, alpha)
    print(f'  OSU 1M pressure: cl={base:.6f}; frozen cn={base_cn:.6f} (run cn={cn:.6f})')
    variants = [('CSU 0.65M', polar_cl(polars / 'S809_CSU_Re0.65M_total.dat', alpha))]
    multi = polars / 'S809_multiRe.dat'
    if multi.is_file():
        levels = multi_re_cls(multi, alpha)
        variants.extend((f'OSU multiRe {reynolds_level / 1e6:g}M', lift)
                        for reynolds_level, lift in levels)
        if levels[0][0] <= reynolds <= levels[-1][0]:
            variants.append(('OSU multiRe local Re', interp(reynolds, *zip(*levels))))
        else:
            print(f'  local Re outside multiRe range [{levels[0][0]:.0f}, {levels[-1][0]:.0f}]; no extrapolation')
    else:
        print('  multiRe table absent; skipped')
    for label, lift in variants:
        new_cn = rebuilt_cn(lift * factor, cd, alpha)
        print(f'  {label}: cl={lift:.6f}; cn={new_cn:.6f}; '
              f'dcn={100 * (new_cn / base_cn - 1):+.3f}%; '
              f'residual={100 * (new_cn / experiment[0.30][0] - 1):+.3f}%')
    print('  CSU/OSU changes facility too; multiRe is OSU-only. No fitted correction or feedback applied.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
