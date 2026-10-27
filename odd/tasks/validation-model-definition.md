# Validation Model Definition v1.2 — ALM / ASM / ASM+mesh

> **v1.2 (owner, 2026-10-17)** changes three knobs, everything else is v1.1:
> 1. **Tip model: Glauert tip loss on, D&S off, in both pillars.** Every P2.1/P2.2 Phase VI run already ran
>    Glauert (the `config/case.yaml` default; the launchers passed no tip flag), not the frozen D&S, so v1.2
>    makes the definition match the evidence. Glauert under-loads the Phase VI tip (H 7 m/s c_n r/R 0.95
>    -14 %, flapwise -3.2 %); D&S over-loads it (`dagtip`: +50.8 %, flapwise +14.1 %; FLOWUnsteady shows the
>    same over-load). On the IEA rotor the P0.4 Glauert control (cp 0.5461) sits +2.8 % over OLAF 0.5312, D&S
>    +5.5..6 %. The IEA pillar is re-evaluated with Glauert (P0.4 control job 11613092 is the starting point).
> 2. **Phase VI polar: OSU Re 1e6 with pressure drag** (`data/polars/S809_OSU_Re1M_pressure.dat`, now the
>    `generate_case.py` default). D3 (`alm-U7-coarse-d1-pdrag`, H 7 m/s): power -11.0 -> -2.2 %, station-sum
>    torque -0.3 %, normal force unchanged. Adopted "for now" as the best result; the diagnosis continues.
>    The IEA polar is unchanged (its tables carry no pressure/friction split; open).
> 3. **Velocity sampling: point sampling at the element** (`velocitySampleRadius 0`, solver default). v1.1 froze a
>    3.3 eps / 16-point ring that no run on disk ever used (the `case.yaml` and IEA generator defaults are 0.0,
>    which render no key); every P2 result, D3 included, is point sampling. The ring is candidate I17 in
>    `model-improvements-register.md`. Found by the conformance check (P2.3 T10): an absent key means the
>    solver default, so conformance is judged on EFFECTIVE values.
> Evidence: `odd/tasks/p2-2-next-cycle-plan.md` ("Session 3 results", "Owner decisions 2026-10-17").
> The v1.1 tables below are kept as written; the two rows marked v1.2 supersede them.

**Status:** **v1.3 ADOPTED as the definition of record 2026-10-27** (tip pitch reference, Dag-Sorensen
tip correction on with Glauert tip off, OSU total polar; record and gate evidence in
`validation-model-definition-v1-3-record.md`). The v1.2 text below is kept as written and is no longer of
record: `config/model-definition-v1.2.yaml` is its frozen reproducible form (`checkModelDefinition.py --variant v1.2`).
Earlier status: **v1 FROZEN except the IEA cp band** (2026-10-12). The owner delegated decisions 1
and 2 to the agent's physical judgment and chose option (b) for decision 3. The IEA cp
band is re-centred after the 3-rev Glauert control (job 11613092) and the P3.1 root fix.
**Plan:** `odd/tasks/validation-master-plan.md` (P0.3) · **Date:** 2026-10-12

One definition serves both pillars (Phase VI against the experiment, IEA 15 MW
against OLAF/BEM). A knob that differs between pillars is listed in "Knobs that
differ" with its reason; nothing else may differ.

## Decisions taken

1. **Rotational augmentation off in both pillars, with a pre-registered RA-on
   variant.** Evidence: on Phase VI at 7 m/s with D&S and the root effect on,
   augmentation off gives %P +0.45 and Du-Selig on gives +6.24
   (`campaign-results/RESULTS.md`, those runs predate `4c49dc3`); on the frozen
   IEA L2 it moves cp +0.74 % and acts only at the stalled root, with
   coefficients that would need per-profile fitting (forbidden here). The
   acceptance points (7 and 10 m/s) are attached flow. The 21-point Sequence S
   curve is run in P2 **twice**, RA off (the definition) and RA on with the
   paper constants (a = b = d = 1, no fitting), both fixed before the run. The
   RA-on curve is judged only on stall onset (>= 10 m/s) and reported beside the
   definition, never replacing it.
2. **Bands: tightened where the physics supports it** (below). A band is only as
   precise as the reference it is judged against, so each carries its reason.
3. **D&S on IEA: option (b).** Keep D&S; re-centre the IEA cp band after the 3-rev
   Glauert control and the P3.1 root fix, then freeze it before the v1 IEA runs.

## Frozen knobs (both pillars)

| Knob | Value | Source / reason |
| --- | --- | --- |
| Tip model (v1.2) | **Glauert tip loss** (`endEffectsModel Glauert`, `tipEffects on`); `tipCorrection` (D&S) **off** | owner decision 2026-10-17 (v1.2 note above) |
| ~~Tip model (v1.1)~~ | ~~**Dag & Sorensen 2020** induced-velocity correction: `wakeTurns 2`, `wakeAzimuthalStep 2`, `epsilon 0` (each element's own projection width)~~ | owner decision 2026-10-11, superseded by v1.2 |
| ~~Glauert tip loss (v1.1)~~ | ~~**off** (`tipEffects off`)~~ | superseded by v1.2 |
| Root effect | Glauert branch = **Prandtl hub loss** `f_hub = (B/2)(r - rHub)/rHub`, `rootEffects on`, `hubRadius` = blade root radius (Phase VI 0.5083 m, IEA 3.97 m) | `4c49dc3`; the solver aborts without `hubRadius` |
| Rotational augmentation | off (decision 1) | Du-Selig A/B |
| Dynamic stall, added mass | off | as committed; steady operating points |
| Velocity sampling (v1.2) | **point sampling at the element**: `velocitySampleRadius 0` (solver default; the key is not rendered), `nVelocitySamples` inert | owner decision 2026-10-17: every run on disk, both pillars, used it (`case.yaml` and the IEA generator default 0.0); D3 phi within +-0.7 deg |
| ~~Velocity sampling (v1.1)~~ | ~~`velocitySampleRadius 3.3`, `nVelocitySamples 16`~~ | ~~"validated method (Phase VI)"~~: no run on disk ever used it; superseded by v1.2 |
| Lift Re correction | `liftReCorrExp 0` | the declared polar Re sits above the run Re; `quantifyPolarReScaling.py` |
| ALM width | `eps = max(2*cbrt(V)*meshFactor, c/4, drag term)`, `meshFactor 1` | `actuatorLineElement::calcProjectionEpsilon` |
| ASM width | `eps = 2*cbrt(V)*meshFactor`, `meshFactor 1`, `nChordwise 5` (default `meshFactor 2` = `4*cbrt(V)` is **not** used) | `actuatorSurfaceElement`; hybrid of Yang & Sotiropoulos sampling and the Massie et al. Gaussian (README, `ad49eef`) |
| ASM+mesh width | paper cosine kernel, support `2.5*h`, `h = cbrt(V)` of the node's cell; **no free width**: `meshFactor` is inert here by design (P1.3), it acts only in the `kernel gaussian` ablation | `bladeSurfaceSampler::nodeSupport`; pinned by `test_mesh_factor_acts_only_in_gaussian_kernel` (cosine field bit-identical for `meshFactor` 1 and 3, gaussian differs 95 %) | the ASM+mesh width follows the cell, the ALM/ASM width follows `meshFactor`; a cell-size study moves the ASM+mesh width with `h` |
| ASM+mesh kernel | smoothed cosine kernel, support `2.5*h` | `bladeSurface` (Yang & Sotiropoulos Eq. 8) |
| Cell prefilter (ASM) | chord box grown by `eps*sqrt(ln 1000)` metres | `914aa72`; results taken before it used a truncated kernel |
| Blade layout (Phase VI) | **equispaced**: `dz = min(0.05 m, h/2)`, root stations (r < 1.0085 m) verbatim, exact S809 outboard; surface and elements from the same station list (v1.1, P1.5) | `tools/blade_resample.py`; deposit ripple <= 2 % at every h, section loads change < 0.7 % and P/T < 0.1 % vs the committed layout (`odd/tasks/p1-5-equispaced-blade.md`); geometry `geometry/phaseVI_blade_dz0p05.{stl,json}` |

## Knobs that differ between pillars

| Knob | Phase VI | IEA 15 MW | Reason |
| --- | --- | --- | --- |
| Polar | **v1.2:** S809, OSU Re 1e6 **pressure drag** (`data/polars/S809_OSU_Re1M_pressure.dat`; v1.1 was `..._total.dat`); cylinder placeholder at the root | table from `buildPolars.py`; stalled root polar still reads `cl = 0` at alpha 41-56 deg, r/R < 0.07 (P3.1) | different airfoils; the IEA root is open until P3.1 |
| Mesh | D/32 coarse, D/48 medium, D/64 fine | snappy L2, finest cell 1.87 m, 2.36 M cells | resolution closed per pillar |
| Operating point | 7 and 10 m/s calibration (Sequence H), evaluation on Sequence S | rated 10.659 m/s, TSR 8.913 | pillar definition |
| Elements | 50 | 147 | blade discretisation |

## Pre-registered bands

Written on 2026-10-12, **before** any run with this definition. Caveat: both of us had already seen the previous-platform numbers (IEA frozen ALM
cp 0.534, ASM 0.574, Phase VI 7 m/s torque -7.6 % with Glauert tip), so the
bands are justified from the references and the published spread, not from those
results. They are frozen except the IEA cp centre.

| Pillar | Quantity | Band | Justification |
| --- | --- | --- | --- |
| Phase VI | `abs(%P)` at 7 and 10 m/s, Sequence S, no configuration change after Sequence H | <= 10 % | attached flow, the regime the formulation claims; the previous-platform D&S + Prandtl run reached +0.45 % at 7 m/s, so 15 % would not discriminate |
| Phase VI | `abs(%T)` at 7 and 10 m/s | <= 15 % | thrust is the blade-root flap force, derived through a moment arm, so it carries more experimental uncertainty than torque |
| Phase VI | spanwise `c_n` at r/R 0.47, 0.63, 0.80 | within +-10 % of the experiment | the section loading matched within +-6 % there in the D&S diagnosis |
| Phase VI | spanwise `c_n` at r/R 0.30 | within +-15 % | inboard, root-effect region, wider scatter in the pressure-tap sections |
| Phase VI | r/R 0.95 | reported, not an acceptance criterion | inside one epsilon of the tip (eps = 0.63 m on the coarse mesh) |
| Phase VI | 13-25 m/s | reported, not a criterion | deep stall is a known limit of the formulation |
| IEA | rotor `cp` at rated | **DEFERRED to P3.1/P3.3** (decision 3b, plan order: Phase 1 and 2 run first); until then the provisional [0.476, 0.546] = the committed CCBlade/BEM 0.4910 and OLAF 0.5312 widened by 3 % of their midpoint | the references bracket the answer; the centre is moved only by physical corrections (3-rev control, P3.1 root), never by the v1 result |
| IEA | spanwise `c_n` per band r/R 0.3-0.5, 0.5-0.7, 0.7-0.9 | within +-10 % of OLAF | the frozen ALM sat +2.7 % over BEM and within +-6 % of OLAF (reference/ours 1.06, 1.04, 0.99 in the three bands) |
| IEA | tip band r/R 0.9-1.0 | reported against OLAF, not an acceptance criterion until an OLAF tip reference is committed | `spanwise-references.csv` stops at 0.9 |
| Phase VI | `abs(cp_ASM - cp_ALM) / cp_ALM` | <= 2 % | the published difference is 0.3 % (Santoni et al. 2024) and Phase VI showed 0.3 %; 2 % leaves room for the corrected kernel (`914aa72`) |
| IEA | `abs(cp_ASM - cp_ALM) / cp_ALM` | <= 3 % | chord is only about 2.7 cells there, so the surface and the line resolve differently; the previous-platform +7.05 % is explained by P3.4 and the band stands |
| Both | ASM+mesh against ALM | same band as the ASM of its pillar | the mesh is a different realisation of the same loading |

## Open items

- **D&S asymptote on the IEA rotor (P0.4) -- measured, and it fails the proposed
  IEA band.** Job 11613058 continued the D&S arm for 3 revolutions from the
  converged rev-20 state. cp per 120 deg window: 0.5748 -> 0.5721 -> 0.5702 ->
  0.5688 -> 0.5677 -> 0.5668 -> 0.5661 -> 0.5655 -> 0.5650 (steps -2.76e-3 ...
  -0.51e-3, still falling; an Aitken estimate on the last three windows gives
  about 0.562, a power-law tail would go lower). Reference points: OLAF 0.5312,
  CCBlade 0.4910, Glauert control (same library, 0.4 rev only) 0.5476, previous
  platform 0.534. So D&S is stable and its effect is where it should be (tip
  band r/R 0.95-1.0: normal force x1.68, tangential x1.49, alpha -0.97 deg), but
  on this rotor it adds about +3 % cp to a Glauert control that is already +3 %
  over OLAF, ending near +5.5...6 % over OLAF, outside the proposed band
  [0.476, 0.546]. The control was run 0.4 rev only; the +3 % split between tip
  model and flow relaxation is not separated until a 3-rev control exists.
  The owner decides (decision 3): (a) keep D&S frozen and accept that the IEA
  band fails, reporting it; (b) keep D&S and re-centre the IEA band on the
  evidence of a 3-rev control plus the P3.1 root fix, which also moves cp; (c) keep
  the Glauert tip loss for the IEA pillar, which breaks "one definition".
- **IEA stalled-root polar (P3.1)** and the **ASM+mesh arm** are Phase 3 work.
- **Frozen IEA numbers are stale.** The L2 platform (cp 0.534) was run before
  `4c49dc3`; with the current library and the same Glauert tip the control reads
  cp +2.4..2.7 % higher (root band only). Every IEA number quoted in this plan
  from before 2026-10-12 is labelled "previous platform".
- **Phase VI baselines are stale too.** The D&S results in `RESULTS.md` (+0.45 % at
  7 m/s) predate `4c49dc3`; P2.1 re-baselines them with the current root factor
  before any band is judged.

## Production-readiness criterion — APPROVED by the owner 2026-10-17

Owner question: "si todo sale bien podriamos considerar que la implementacion esta lista para produccion
cientifica?" Answer: not on Phase VI 7 m/s alone. The definition is declared ready for scientific production
(use on the IEA 15 MW and in FSI) only when ALL of R1-R6 hold, each with a committed script and data hash:

| id | condition | pass rule | status |
| --- | --- | --- | --- |
| R1 | Numerical independence: mesh ladder at FIXED eps (`meshFactor = 2^level`, levels 0-2) and a time-step pair, on H 7 m/s, v1.2 | P, T and F'n at r/R 0.47-0.95 change < 2 % between the two finest levels and between the two time steps | DONE 2026-10-21 (`compareLadder.py`, H 7 m/s, revs 4-12, drift-free): dt 0.0005 vs `d1-pdrag` max 0.11 %; level 0 -> 1 max 1.23 % (P); level 1 -> 2 (`r2-v12-l2`, resumed run) max 0.42 % (P), T -0.001 %, F'n 0.47-0.95 within 0.18 %: PASS |
| R2 | Attached-regime coverage on Sequence S, v1.2 frozen, no retuning: 5, 6, 7, 8 m/s | each speed inside the pre-registered bands (P 10 %, T 15 %, F'n/c_n bands as written, the 0.30 band judged per the owner's decision on the reference pressure) | ALM: 7 m/s 11618033, 5/6/8 m/s 11618058-60; ASM/ASM-mesh 7 m/s 11618034/35 (other speeds after ALM passes) |
| R3 | IEA 15 MW pillar re-evaluated with v1.2 (Glauert) against OLAF/BEM at rated, polar Re issue (I14) resolved or bounded | cp inside the re-centred IEA band; spanwise loads reported | open |
| R4 | Tip residual closed or bounded: the r/R 0.95 F'n deficit has an identified cause (P2.3 T4/T5) and its effect on the flapwise and edgewise root moments is quantified | either inside the 0.80 band or documented as a limit with its root-moment impact (currently flap -3.4 %, edge -0.3 %) | diagnosing: T5 job 11618046, T4 lag run (runs/lib-p23) |
| R5 | Definition conformance: every run quoted as validation passes `checkModelDefinition.py` and the judging script refuses non-conforming runs | automated | DONE: `checkModelDefinition.py`; `summarizeBands.py` refuses non-conforming runs (6f5f264) |
| R6 | Uncertainty attached to every validation number: experiment repeatability, averaging-window sensitivity, blockage (+1/+2 % inflow) | each quoted difference carries its combined uncertainty (evidence register section 4) | tool DONE (`quantifyUncertainty.py`): H 7 d1-pdrag combined k=1: P 4.0 % (blockage), T 1.6 %, c_n 1.4-3.8 % (repeatability); window <= 0.08 %. Open: tunnel speed (VTUN) offset, owner decision |

Declared alongside, not conditions: the limits chapter (stall regime, from existing results), the calibration
history (I1 chosen on H, I2 chosen after seeing H and S results), and the C++ solver having no automated tests
beyond the Python suite.
