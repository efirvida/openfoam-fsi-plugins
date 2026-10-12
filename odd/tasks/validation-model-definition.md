# Validation Model Definition v1 — ALM / ASM / ASM+mesh

**Status:** DRAFT until the owner confirms the three decisions below and the P0.4
tip-correction asymptote is read (see "Open items"). It becomes **v1 frozen** when
the status line is changed and the commit is tagged in the master plan.
**Plan:** `odd/tasks/validation-master-plan.md` (P0.3) · **Date:** 2026-10-12

One definition serves both pillars (Phase VI against the experiment, IEA 15 MW
against OLAF/BEM). A knob that differs between pillars is listed in "Knobs that
differ" with its reason; nothing else may differ.

## Decisions to confirm (owner)

1. **Rotational augmentation off in both pillars** (recommended). Evidence: the
   Du-Selig A/B on the frozen IEA L2 (`ff58337`, `odd/tasks/iea15mw-platform-freeze.md`)
   moves cp by +0.74 % and acts only at the stalled root (alpha 52-56 deg,
   r/R < 0.1); it does not reproduce the +49...+71 % inboard tangential force of the
   URANS-vs-BEM paper pairs, and needs coefficients fitted per profile, which this
   plan forbids (rule: no free-parameter calibration). The Phase VI acceptance points
   (7 and 10 m/s) are attached flow. Consequence to state in every result: the
   stall onset on the 21-point Sequence S curve is read **without** stall delay,
   so a late measured onset is a known limit, not a failure; an RA-on variant of
   that curve is an ablation, labelled as such.
2. **The bands below** (written before the v1 runs; see the caveat under them).
3. **Which D&S status counts as "frozen"** if the P0.4 asymptote is inconsistent
   (see "Open items").

## Frozen knobs (both pillars)

| Knob | Value | Source / reason |
| --- | --- | --- |
| Tip model | **Dag & Sorensen 2020** induced-velocity correction: `wakeTurns 2`, `wakeAzimuthalStep 2`, `epsilon 0` (each element's own projection width) | owner decision 2026-10-11 |
| Glauert tip loss | **off** (`tipEffects off`) | D&S replaces it; they are alternatives |
| Root effect | Glauert branch = **Prandtl hub loss** `f_hub = (B/2)(r - rHub)/rHub`, `rootEffects on`, `hubRadius` = blade root radius (Phase VI 0.5083 m, IEA 3.97 m) | `4c49dc3`; the solver aborts without `hubRadius` |
| Rotational augmentation | off (decision 1) | Du-Selig A/B |
| Dynamic stall, added mass | off | as committed; steady operating points |
| Velocity sampling | `velocitySampleRadius 3.3`, `nVelocitySamples 16` | validated method (Phase VI), same on the IEA platform |
| Lift Re correction | `liftReCorrExp 0` | the declared polar Re sits above the run Re; `quantifyPolarReScaling.py` |
| ALM width | `eps = max(2*cbrt(V)*meshFactor, c/4, drag term)`, `meshFactor 1` | `actuatorLineElement::calcProjectionEpsilon` |
| ASM width | `eps = 2*cbrt(V)*meshFactor`, `meshFactor 1`, `nChordwise 5` (default `meshFactor 2` = `4*cbrt(V)` is **not** used) | `actuatorSurfaceElement`; hybrid of Yang & Sotiropoulos sampling and the Massie et al. Gaussian (README, `ad49eef`) |
| ASM+mesh kernel | smoothed cosine kernel, support `2.5*h` | `bladeSurface` (Yang & Sotiropoulos Eq. 8) |
| Cell prefilter (ASM) | chord box grown by `eps*sqrt(ln 1000)` metres | `914aa72`; results taken before it used a truncated kernel |

## Knobs that differ between pillars

| Knob | Phase VI | IEA 15 MW | Reason |
| --- | --- | --- | --- |
| Polar | S809, OSU Re 1e6 total (`data/polars/S809_OSU_Re1M_total.dat`); cylinder placeholder at the root | table from `buildPolars.py`; stalled root polar still reads `cl = 0` at alpha 41-56 deg, r/R < 0.07 (P3.1) | different airfoils; the IEA root is open until P3.1 |
| Mesh | D/32 coarse, D/48 medium, D/64 fine | snappy L2, finest cell 1.87 m, 2.36 M cells | resolution closed per pillar |
| Operating point | 7 and 10 m/s calibration (Sequence H), evaluation on Sequence S | rated 10.659 m/s, TSR 8.913 | pillar definition |
| Elements | 50 | 147 | blade discretisation |

## Pre-registered bands

Written on 2026-10-12, **before** any run with this definition. Caveat: the
owner and the agent had already seen the previous-platform numbers (IEA frozen ALM
cp 0.534, ASM 0.574, Phase VI 7 m/s torque -7.6 % with Glauert tip), so the
bands are justified from the references and the published spread, not from those
results. They are proposals until decision 2 is taken.

| Pillar | Quantity | Band | Justification |
| --- | --- | --- | --- |
| Phase VI | `abs(%P)` and `abs(%T)` at 7 and 10 m/s, Sequence S, no configuration change after Sequence H | <= 15 % | measurement uncertainty plus the spread among published ALM validations of this rotor; deep stall excluded |
| Phase VI | spanwise `c_n` at r/R 0.30, 0.47, 0.63, 0.80 | within +-15 % of the experiment | station uncertainty of the pressure-tap sections |
| Phase VI | r/R 0.95 | reported, not an acceptance criterion | inside one epsilon of the tip (eps = 0.63 m on the coarse mesh) |
| Phase VI | 13-25 m/s | reported, not a criterion | deep stall is a known limit of the formulation |
| IEA | rotor `cp` at rated | between the committed CCBlade/BEM value 0.4910 and the OLAF free wake 0.5312, widened by 0.015 on each side: **[0.476, 0.546]** | the two committed references bracket the answer; the width is 3 % of their midpoint |
| IEA | spanwise `c_n` per band r/R 0.3-0.5, 0.5-0.7, 0.7-0.9 | within +-10 % of OLAF | the frozen ALM sat +2.7 % over BEM and within +-6 % of OLAF (reference/ours 1.06, 1.04, 0.99 in the three bands) |
| IEA | tip band r/R 0.9-1.0 | reported against OLAF, not an acceptance criterion until an OLAF tip reference is committed | `spanwise-references.csv` stops at 0.9 |
| Both | `abs(cp_ASM - cp_ALM) / cp_ALM` | <= 3 % | ten times the 0.3 % that Santoni et al. 2024 publish; Phase VI showed 0.3 %. The IEA ASM measured +7.05 % on the previous platform: P3.4 explains it, and the band stands |
| Both | ASM+mesh against ALM | same bands as ASM | the mesh is a different realisation of the same loading |

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
