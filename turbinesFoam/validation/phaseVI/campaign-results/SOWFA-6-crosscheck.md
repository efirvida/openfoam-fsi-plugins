# Cross-check: our Phase VI case vs. SOWFA-6 `example.UAE_PhaseVI.ALMAdvanced`

**Purpose.** Compare the formulation of our turbinesFoam Phase VI case against
NREL's SOWFA-6 example, decide which differences are worth adopting, and set
out the minimal validation matrix. Experimental claims are grounded first in
the primary report (`NREL-TP-500-29955-crosscheck.md`).

**SOWFA source.** NREL SOWFA-6 `exampleCases/example.UAE_PhaseVI.ALMAdvanced`
(NREL's official actuator-line code, recently archived). Surveyed alongside its
open issues/PRs (§3).

## 1. SOWFA-6 example — extracted setup

| Setting | SOWFA-6 | Ours |
|---|---|---|
| TipRad | 5.029 m | 5.029 m |
| HubRad | 0.432 m | geometry root 0.5083 m |
| RotSpeed | 71.9 RPM | measured per speed (71.878–72.208) |
| Pitch | **4.815°** | **3.0°** |
| tipRootLossCorrType | **none** (Glauert commented out) | Glauert, tip **on**, root **on** (default) |
| bladeForceProjectionType | uniformGaussian | uniformGaussian |
| bladeEpsilon | (0.35, 0, 0) | `gaussian_mesh_factor`-derived |
| numBladePoints | 60 | `n_elements: 50` |
| fluidDensity | 1.23 | per experiment row (ideal gas) |
| Domain | x[−40, 80] y[±18.3] z[0, 24.4] m (test section) | x[−5D, 15D] y[±4D] z hub ±2.5D |
| Local refinements | 4 | mesh breaks in `config/case.yaml` |
| deltaT | 0.0025 s | 0.008 (coarse) / 0.005 (fine) |
| endTime | 20 s | 12 revolutions |
| purgeWrite | 0 | 1 |
| Airfoils | `Mod_S809_*` + `cylinder` | `S809_OSU_Re1M_total` + root cylinder |

## 2. Formulation comparison

### 2.1 Pitch — SOWFA 4.815° vs. our 3.0°

The experimental report fixes Sequence H at **3°** tip pitch (report p27; see
`NREL-TP-500-29955-crosscheck.md` §3). **Our case is right; SOWFA's 4.815° is
not the Sequence H setting** (likely a different campaign, or a
flattened/corrected pitch). **Do not change our pitch.**

### 2.2 Tip end effect — agreement

Both implement the Prandtl tip factor
`F_tip = (2/π)·acos(exp(−f_tip))` with `f_tip = (B/2)·(R−r)/(r·sinφ)`. SOWFA
disables it (`none`), we enable it. Our tip-loaded 7 m/s point is in band
(−7.2 % P), so this is an **ablation arm**, not a fix.

### 2.3 Root end effect — **disagreement (the key finding)**

All rows use `F_root = (2/π)·acos(exp(−f_root))`; only `f_root` differs.

| | `f_root` | At the hub (r = HubRad) |
|---|---|---|
| turbinesFoam (current) | `(B/2)·(1/(1−r/R) − 1)/sinφ = (B/2)·r/((R−r)·sinφ)` | `F_root ≈ 0.6–0.7` (**does not vanish**) |
| **SOWFA (confirmed)** | `(B/2)·(r−HubRad)/(R·sinφ)`, applied as `F_total = F_tip · F_root` | `F_root → 0` |
| Canonical Prandtl (literature) | `(B/2)·(r−HubRad)/(HubRad·sinφ)` | `F_root → 0` |

Our current root factor **does not vanish at the hub**, so the root section
keeps producing lift where Prandtl theory says the loading must go to zero. The
campaign evidence is consistent with this: `root-on` (arm B) is worse than
`root-off` (arm A) at every measured point —

- 10 m/s: −26.7 % (B) vs. −14.6 % (A)
- 13 m/s: −96.5 % (B) vs. −76.5 % (A)
- 15 m/s: −1.40 kW (B, non-physical) vs. +1.96 kW (A)

Our `r/(R−r)` is **not** the Prandtl root correction: it is the tip factor
mirrored, and it stays finite at the hub.

**SOWFA's exact form is now confirmed** (Mohammadi et al. 2024, *Wind Energy
Science* **9**, 1305–1324, §2): in their Eq. (7) the term `(R − r_p)` is replaced
by `(r_p − R_hub)`, keeping the same `2R·sinφ` denominator, and the two factors
are **multiplied**: `F_total = F_tip · F_root`. So SOWFA's root is
`F_root = (2/π)·acos(exp(−(B/2)·(r−HubRad)/(R·sinφ)))` — it **vanishes at the
hub**, unlike ours. (The earlier "as surveyed" guess `(r−HubRad)/r` was wrong.)

**However — see `formulation-review.md` §2:** the modern ALM literature (Meyer
Forsting 2019/2020; Kim 2015; Jha 2014; Mohammadi 2024) argues that a BEM-type
tip/root loss is the **wrong instrument** for an actuator line, because it
corrects a *disc* for missing discrete blades. The physically consistent fix is
to **restore the missing bound-circulation induction** — a vortex-based smearing
correction (Meyer Forsting) or the filtered-lifting-line correction
(Martínez-Tossas) — rather than to patch the loads with a Prandtl factor. This
must be **validated
empirically**, not assumed — hence the R′ arm below.

**Location:** `turbinesFoam/src/fvOptions/axialFlowTurbineALSource/axialFlowTurbineALSource.C`
(`endEffectsModel_ == "Glauert"`, ~line 629; defaults `tipEffects=true`,
`rootEffects=false`).

### 2.4 Domain / blockage

SOWFA's domain matches the NASA-Ames test section (x[−40, 80] m, y[±18.3] m,
z[0, 24.4] m). Ours is a free box (x[−5D, 15D], y[±4D], z hub ±2.5D) that does
**not** model the test section; `README.md` documents the blockage as
uncorrected. Candidate follow-up, not part of the current fix.

## 3. SOWFA issue/PR survey

Surveyed SOWFA-6 issues and pull requests: **no open item flags the tip/root
end-effect handling or the Phase VI example.** The tip/root difference is a
genuine formulation choice, not a known SOWFA bug. (Therefore we use SOWFA as a
*reference*, not as gospel: the root change is justified by Prandtl literature
and validated against our own runs.)

## 4. Improvement plan (minimal validation matrix)

Goal: isolate (a) turning the tip correction off, and (b) fixing the root
formula, against the existing arms.

**Prepared toggles.** `--tip-effects {on,off}` (**new**, mirroring the existing
`--root-effects {on,off}`) in `tools/generate_case.py` and
`scripts/runPhaseVI.sh`. The committed default stays tip-on/root-on; the toggle
is render-time only.

**Matrix (7 / 10 / 13 m/s, coarse, `alm`):**

| Arm | Rot. augmentation | Tip | Root | Purpose |
|---|---|---|---|---|
| A (existing) | on | on | off | campaign baseline |
| **A′ (new)** | on | **off** | off | isolate tip (A vs. A′) |
| **C′ (new)** | **off** | **off** | off | isolate augmentation (A′ vs. C′) |
| R′ (after fix) | on | on | **fixed** | isolate the root formula (A vs. R′) |

A′ and C′ are renderable **now**. R′ requires the root-formula change and a
fresh campaign.

**Acceptance.** Same ±15 % band as the campaign; a change is adopted only if it
moves the in-band points toward the measurement without breaking them.

**Arm C′ is SOWFA-aligned on end effects** (tip off, root off = SOWFA `none`),
so C′ also answers "does SOWFA's end-effect choice reproduce our measurements
better than ours?" at 7/10/13 m/s.

## 5. Status

- `--tip-effects` toggle: **implemented and tested** (32/32 Phase VI tests pass;
  committed default unchanged).
- Root formula: **candidate identified, not changed** — needs the R′ arm.
- Pitch: **no change** (3° is correct for Sequence H).
- Domain/blockage: documented; candidate follow-up.
- This document: SOWFA data + formulation comparison + plan, with the
  experimental validation in `NREL-TP-500-29955-crosscheck.md`.
