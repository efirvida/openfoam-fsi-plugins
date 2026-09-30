# Phase VI thrust diagnosis — the "+9.3 %" is mostly a comparison-scope artefact

Config diagnosed: D&S tip correction ON, Glauert tip loss OFF, Glauert root ON,
Du-Selig OFF; 7 m/s, Sequence H, coarse D/32
(`runs/alm-U7-coarse-tipcorr-augoff-rooton`). Read-only; no solver run.

## 1. Headline — and a correction to the first reading

The reported `T = 1236.9 N vs 1132.1 N (+9.3 %)` compares **two different radial
ranges**:

- our `T_blade` integrates the **whole blade**, `r/R = 0.101 → 1.0`;
- the measured `EAEROTH` (WDH `ldsmean`, row `h0700000`, column 54) is a blade
  pressure integration **from 25 % span to the tip**, i.e. `r/R ≥ 0.25`
  (`data/experiment/PROVENANCE.md`; the project already ships
  `comparePhaseVI.py --match-eaeroth-span` for exactly this).

Running that flag on the existing output (offline, no queue):

| scope | sim T (N) | exp T (N) | %T |
|---|---:|---:|---:|
| whole blade (the default comparison) | 1236.9 | 1132.1 | **+9.3 %** |
| `r/R ≥ 0.25`, matched to `EAEROTH` | **987.8** | 1132.1 | **−12.7 %** |

The root band `r/R = 0.101 … 0.25` therefore carries **≈ 249 N, ~20 % of the
axial force** — not the ~10 N (< 1 %) the first estimate assumed. **The +9.3 %
is dominated by the scope mismatch, and the apples-to-apples axial error is an
under-prediction, not an over-prediction.**

Span-matched %T for the other runs (same command):

| run | %T whole blade | %T matched (r/R ≥ 0.25) |
|---|---:|---:|
| U7 D&S, root ON, aug OFF (best) | +9.26 | **−12.7** |
| U7 D&S, root ON, aug ON | +13.71 | **−9.4** |
| U10 D&S root ON | +0.20 | **−20.9** |
| U13 D&S root ON | −9.64 | **−29.7** |
| U15 D&S root ON | −10.06 | **−30.3** |
| U25 D&S root ON | +2.78 | **−19.5** |

So in the range the experiment actually measures, the axial loading is
**consistently 9–30 % low**; the whole-blade integral hides that behind the root
band. **Every `%T` in the campaign tables (including the earlier handoff) carries
this bias and must be recomputed with `--match-eaeroth-span` or flagged.**

## 2. What is genuinely ruled out

- **Blade vs rotor scope is a no-op.** `cd ≡ Σ_i cd_blade_i` by construction
  (`axialFlowTurbineALSource.C:1305`, `turbineALSource.C:483`; `force_` is the sum
  of the blade forces), so `T_rotor ≡ T_blade` and `--thrust-scope` cannot move
  the number. The report's "hub included" label is a mislabel; there is no
  hub/tower force in this model.
- **`q_dyn` is consistent** on both sides (`½ρAU² = 2401.6 N` with
  `ρ = 1.2337256`, `A = πR²`, `R = 5.029`); the experiment side is a force.
- **`C_TQ = 2·CT*` is torque-only.** Reproducing the measured torque from the
  measured spanwise `ct` needs the ×2 twice (C_TQ and two blades): 195.6 × 2 × 2 =
  **782.4 Nm vs 789.9** (1.009). The measured spanwise `CN` reproduces the thrust
  with **no** factor (ratio 1.019). So the factor does not enter thrust.
- **A fixed definitional offset would be constant in speed — it is not.**

## 3. The spanwise picture (7 m/s, best config)

Chord-referenced `cn` rebuilt as the comparison does (`cl·cosα + cd·sinα`):

| r/R | our cn | exp CN | Δ |
|---|---:|---:|---:|
| 0.30 | 0.556 | 0.814 | **−31.7 %** |
| 0.47 | 0.827 | 0.920 | −10.2 % |
| 0.63 | 0.898 | 0.867 | +3.6 % |
| 0.80 | 0.888 | 0.767 | **+15.7 %** |
| 0.95 | 0.795 | 0.518 | **+53.6 %** |

**The loading profile is wrong at both ends** — under-predicted inboard,
over-predicted outboard — and the *integrated torque happens to come out right
because the two errors partially cancel*. That is the most important caveat on
the "+0.45 %" result: **a matching integral does not validate the distribution.**

## 4. The tip is still the outboard problem, and it is the same one

At `r/R = 0.95` the measurement (0.518) sits **between** the two end-effect
models we have: Glauert tip loss ON gives `cn = 0.435` (**−16 %**, torque −7.2 %)
and the D&S correction gives `0.795` (**+53.6 %**, torque +0.45 %). The needed
correction is bracketed, and the D&S correction is **too weak** at the tip — the
same conclusion `RESULTS.md` reached about its resolution dependence. The
outboard `cn` excess is what carries the (whole-blade) thrust excess.

## 5. Caveats that must travel with any conclusion

- **The spanwise `ct` is reference-frame/normalisation-inconsistent and must not
  be read as a torque error**: the rebuilt `ct` is `+51 %`/`+97 %` at
  `0.80`/`0.95`, yet a strip integration of it gives **553 Nm against the actual
  793.4 Nm**. Only the chord-referenced `cn` is validated by strip integration
  (measured-CN strip 1141.5 N vs `EAEROTH` 1132.1 N, +0.8 %).
- **Missing tower/hub cannot explain a high simulation** (it removes axial
  force); its sign is wrong for both the +9.3 % and the −12.7 %.
- **Blockage** likewise has the wrong sign.
- The geometry's last station (5.00 → 5.029 m) makes the last element tiny
  (span ≈ 0.0145 m), so raw element-force sums are non-uniform in span; the
  physical strip integral is the right weighting.

## 6. Recommended actions

1. **Recompute every `%T` with `--match-eaeroth-span`** (or make it the default
   for the thrust row) and record the scope next to the number. The present
   tables understate the axial error by ~20 points.
2. Treat the "+0.45 % torque / +0.45 % power" result as **not a validated
   configuration**: the inboard and outboard loading errors cancel.
3. The two live levers remain the ones already queued/planned:
   **the tip correction is too weak** (tip `cn` +54 %), and **the inboard is
   under-loaded** once Du-Selig is removed (−32 % at r/R = 0.30) — i.e. the
   stall-delay replacement must not simply be deleted, it must be *replaced* by a
   bounded/separation-based model (see `phasevi-stall-delay-literature.md`).

### Uncertainty ledger

- **Measured:** `EAEROTH = 1132.0692 N`, `LSSTQCOR = 789.8572 Nm`,
  `ROTPOW = 5.9458 kW`, spanwise CN/CT (WDH `ldsmean`, row `h0700000`).
- **Simulated (harness):** the `turbine_comparison.csv` and
  `spanwise_comparison.csv` rows quoted above.
- **Computed here:** the `--match-eaeroth-span` thrust rows (§1) and the root-band
  contribution (249 N).
- **Inherited from the delegated analysis and NOT independently re-verified:**
  the panel/strip weighting table (the +110 N at r/R = 0.95 etc.). Its aggregate
  the delegated work reported (simulated 1266 N vs turbine 1236.9 N, +2.4 %) is
  consistent with the harness, but the per-station attribution is an offline
  reconstruction and its root-band estimate was shown wrong by §1.
