# Rotational Augmentation Specification

## Purpose

Defines the Du–Selig rotational augmentation (3D stall delay) correction in the
shared actuator element load chain. The correction is additive and default-off:
when the `rotationalAugmentation` block is absent or inactive the chain is
byte-identical, and when active it raises the deep-stall lift of rotating
elements. Because it lives in the single chain every model inherits, ALM, ASM and
the mesh-backed surface all receive it without per-model code.

## ADDED Requirements

### Requirement: Du–Selig correction in the shared load chain

The system MUST apply the Du–Selig rotational augmentation inside the shared
element force method, in place on `liftCoefficient_` and `dragCoefficient_`,
after the static coefficient lookup and before the dynamic-stall correction, so
that the dynamic-stall, added-mass, end-effect and per-element CSV stages all
consume the corrected coefficients. The correction MUST NOT be re-applied by any
downstream stage.

#### Scenario: Correction applied after the static lookup

- GIVEN an active augmentation block and an element whose static lookup has produced `CL,2D`/`CD,2D`
- WHEN the element computes its force
- THEN `liftCoefficient_`/`dragCoefficient_` hold the corrected `CL,3D`/`CD,3D` before any later correction runs

#### Scenario: Ordering relative to dynamic stall

- GIVEN an element with both rotational augmentation and dynamic stall active
- WHEN the force is computed
- THEN the augmentation is applied first and the dynamic-stall model receives the augmented coefficients

#### Scenario: Pre-stall lift unchanged

- GIVEN an angle of attack below stall where `CL,2D = CL,p`
- WHEN the correction is applied
- THEN `CL,3D = CL,2D` (the lift correction vanishes) and the drag follows Eq. 10

### Requirement: Equation form and paper constants

The system MUST implement Du–Selig Eqs. 9–12 in the **original prefactor form**
(Du & Selig 1998, AIAA-98-0021): `CL,3D = CL,2D + fL(CL,p − CL,2D)`,
`CD,3D = CD,2D − fD(CD,2D − CD,0)`,
`fL = (1/2π)[(1.6(c/r)/0.1267)·(a − (c/r)^((d/Λ)(R/r))) / (b + (c/r)^((d/Λ)(R/r))) − 1]`,
`fD = (1/2π)[(1.6(c/r)/0.1267)·(a − (c/r)^((d/(2Λ))(R/r))) / (b + (c/r)^((d/(2Λ))(R/r))) − 1]`,
with `CL,p = 2π(α − α0)`, `CD,0` the 2D drag at zero angle of attack, and
`Λ = ΩR/√(U² + (ΩR)²)`. `1.6(c/r)/0.1267` is a prefactor on the fraction
`(a − X)/(b + X)`; `a` and `b` are the numerator/denominator constants, not an
exponent or multiplier of `c/r`. The constants MUST default to `a = b = d = 1`.
The exponent MUST be `(d/Λ)(R/r)` for `fL` and `(d/(2Λ))(R/r)` for `fD`; the
text-dump reading `d·ΛR/r` MUST NOT be used.

**Correction (2026-09-24):** arXiv:1702.02108v4 Eqs. 11–12 print a *different*,
split form — `(1.6(c/r)a − X)/(0.1267b + X) − 1`. That printed form is a
transcription error and MUST NOT be implemented. Evidence and the independent
reproductions (NREL AirfoilPrep.py, BYU CCBlade.jl, Munduate 2002, IOP 2024,
Li/Liu/Yang 2022 *Energies* 15:6533): `research-formulation-fidelity.md`
(Engram #179).

#### Scenario: Hand-computed sample matches

- GIVEN a mid-span element at U13 with `c/r ≈ 0.271`, `R/r ≈ 2.27`, `Λ ≈ 0.95`, and `a=b=d=1`
- WHEN the correction is evaluated
- THEN `fL ≈ 0.34` and `CL,3D ≈ 1.53`, matching the hand-computed prefactor-form Eqs. 9–12 value (the split form would give `fL ≈ 0.20`, `CL,3D ≈ 1.19`)

#### Scenario: Near-tip behavior is recorded, not clamped

- GIVEN an element near the tip where `fL < 0`
- WHEN the correction is evaluated
- THEN Eqs. 9–12 are applied literally with no invented clamp and the behavior is documented in the sensitivity note

### Requirement: Per-element radial geometry interface

The system MUST provide each element a local radius and the rotor radius, read
additively (`lookupOrDefault`) from the element dictionary, and MUST derive
`c/r = chordLength/radius`, `R/r = rotorRadius/radius`, and
`Λ = omega·rotorRadius/√(|freeStreamVelocity|² + (omega·rotorRadius)²)`. The
injected `radius` MUST equal the local radial station used by the comparison
tool (`r = rootRadius + rootDistance·(rotorRadius − rootRadius)`). The values
MUST be pure per-element scalars carrying no new restart state.

#### Scenario: Keys present compute the ratios

- GIVEN an element dict carrying `radius` and `rotorRadius`
- WHEN the correction is evaluated
- THEN `c/r`, `R/r` and `Λ` are computed from those scalars and the element's own chord/omega

#### Scenario: Absent keys keep the old dictionary valid

- GIVEN an element dict without `radius` or `rotorRadius`
- WHEN the element is constructed
- THEN construction succeeds with the prior behavior and no correction is applied

#### Scenario: Parallel and restart safety

- GIVEN a decomposed run that writes and restarts from a time directory
- WHEN the augmentation is active
- THEN the per-element scalars reproduce identically and no halo exchange or restart state is added

### Requirement: Additive default-off switch

The system MUST read an additive `rotationalAugmentation` block —
`active off`, `model DuSelig`, `a 1`, `b 1`, `d 1` — defaulting to off, mirroring
`dynamicStall`/`endEffects`. With the block absent or `active off`, the produced
element, line and turbine output MUST be byte-identical to a pre-change run; with
`active on`, the correction MUST be applied. An unregistered model name MUST fail
loudly.

#### Scenario: Default-off byte-identical output

- GIVEN an existing case with no `rotationalAugmentation` block
- WHEN it runs against the new library
- THEN its element, line and turbine output is byte-identical to the baseline and the existing tests pass unchanged

#### Scenario: Switch on applies the correction

- GIVEN the same case with `rotationalAugmentation { active on; }`
- WHEN it runs
- THEN the deep-stall coefficients are augmented per Eqs. 9–12

#### Scenario: Unknown model rejected

- GIVEN a block selecting an unregistered `model`
- WHEN the element is configured
- THEN configuration fails loudly instead of silently skipping the correction

### Requirement: Single-chain inheritance by ALM, ASM and the mesh surface

The system MUST reach every element force through the one shared chain, so that
the actuator line, the no-mesh actuator surface and the mesh-backed surface all
reflect the correction with no per-model code.

#### Scenario: All models reflect the correction

- GIVEN an augmentation-on case run as ALM, ASM and ASM-mesh
- WHEN their element/turbine outputs are compared with an augmentation-off run
- THEN all three differ from the off run and share the same corrected chain, with no per-model correction code

### Requirement: Formulation documentation and claim boundary

The repository docs MUST state the formulation (Eqs. 9–12, exact algebra from
the source PDF, `a=b=d=1`), the sensitivity note (no free-parameter calibration;
near-tip `fL < 0` behavior), and the honest claim boundary. The root
`CHANGELOG.md` MUST record the change in `Files:` / `Problem:` / `Fix:` format.

#### Scenario: Documentation complete

- GIVEN the updated docs
- WHEN they are inspected
- THEN they state the equations, the constants, the sensitivity note and the claim boundary, and the changelog entry follows the repository format
