# P1.5 — Equispaced blade discretisation (all done 2026-10-13)

Origin: owner observation 2026-10-12 (the ASM+mesh blade surface has sections unevenly spread
along the span; proposal: resample at constant spanwise distance, using that the blade carries
one airfoil, S809, outboard of r = 1.0085 m). Plan: `odd/tasks/validation-master-plan.md`.

## Measured (scripts committed, numbers pinned by `tests/test_blade_surface_layout.py`)

`validation/phaseVI/scripts/inspectBladeSurface.py geometry/stl/phaseVI_blade.stl`:
25 segments from the NREL station table, `dz` 0.013 .. 0.305 m (ratio 23.5), 120 triangles per
segment, triangle aspect ratio (`Lmax^2/2A`) up to 212, mean 20-30 in the long segments.

`validation/phaseVI/scripts/spanwiseDepositRipple.py` (1D model of the cosine-kernel deposit of a
uniform load per area, against the continuous deposit of the same surface; max error / mean):

| h [m] | mesh | committed loft (3000 nodes) | equispaced dz = 0.05 | equispaced dz = 0.1 |
|---|---|---|---|---|
| 0.310 | coarse (used in P1.4, P2) | 1.6 % | 1.0 % | 0.7 % |
| 0.155 | refine level 1 | 7.5 % | 2.3 % | 2.0 % |
| 0.078 | refine level 2 | **55 %** | 4.7 % | 5.2 % |
| 0.039 | refine level 3 | **126 %** | 8.9 % | 37 % |

Reading: on the coarse mesh the layout is harmless (1.6 %); it breaks as the mesh is refined,
because the cell size falls below the 0.3 m node spacing and the deposit becomes a comb.
So an ASM+mesh mesh-convergence ladder on the committed loft is not interpretable. The
triangle aspect ratio itself is NOT the cause (nodes are point sources; the chordwise step
0.01-0.025 m is always far below h); the cause is the spanwise spacing against h.
Limits: 1D, uniform load, no chordwise direction, no flow.

## Coupling that the proposal must respect

`bladeSurfaceSampler.C:118-150` assigns every node to the NEAREST element station and aborts
("owns no face centroid") when an element receives no node. The elements come from the same
table (50 = 25 segments x 2, some 6.5 mm wide). A coarser or equispaced surface therefore needs
an equispaced ELEMENT layout as well (the owner's second point): the surface step must be a
fraction of the element width. Equispaced elements also remove the 23:1 spread of element
widths, but they move the elements away from the experimental stations (r/R 0.30, 0.47, 0.63,
0.80, 0.95): the comparison must then use the nearest element or an interpolation.

## Proposed work (to decide)

- [x] **E1 (cfaeeff)** Loft/element resampling with a chosen `dz` tied to `h` (the rule is NOT settled: the table
      above only measured fixed dz = 0.05 and 0.1 m; scan dz/h before choosing), exact S809 outboard, circle ->
      S809 morph kept in the root segments; surface area and chord/twist deviation vs the
      committed loft reported (area 4.88423 m^2 today).
- [x] **E2 (elements: one per segment of the same table; sampler invariant checked in Python: 0 empty elements)** Same resampling for `elementData` (ALM, ASM, ASM+mesh stay consistent); station
      comparison rule in `compareSectionLoads.py`.
- [x] **E3 (done 2026-10-13, accepted: max change 0.69 %, see Result E3)** A/B on the coarse mesh: ALM and ASM+mesh, committed vs equispaced, 4 revs. Accept
      only if the change is within the ALM-ASM bound of the Model Definition.
- [x] **E4 (done 2026-10-13, v1.1 row in the Model Definition)** Model Definition v1.1 entry; Phase VI baselines are re-run in P2.1 anyway, so doing
      this BEFORE P2.1 costs no extra baseline.


## Result 2026-10-12 (no cluster needed; `scripts/scanEquispacedDz.py`, `tools/blade_resample.py`, `tests/test_blade_resample.py`)

Rule settled: **dz = min(0.05 m, h/2)**, root stations (r < 1.0085 m) kept verbatim.

- Deposit ripple with dz = f*h: f = 0.25..0.5 gives <= 2 % at every h (0.31 .. 0.039 m); f = 0.75 gives up to 7.6 %; f = 1.5 gives up to 11 %.
- Geometry kept (linear interpolation of the 26-station table): dz <= 0.05 m gives chord dev 0.0013 m, twist dev 0.06 deg, chord-area dev 0.001 %. dz = 0.1 m already loses 1.85 deg of twist at the root transition (r 1.0 .. 1.26 m), so h/2 alone is wrong on the coarse mesh; the 0.05 m cap is the geometric floor.
- Stations: dz 0.05 m gives 85 rows (3 root + 82 outboard) against 26.

Pending: E1 STL (needs `blade_phasevi.py` to accept a station list; `N_STATIONS`/`input_sha256` are pinned to 26), E2 (`blade_element_rows` already takes a station list; the sampler needs the element count tied to dz), E3 (4-rev A/B, needs the queue).

## E3 submitted 2026-10-12 (4 revs, coarse, 7 m/s, H, 84 tasks; `scripts/slurm/equispaced-blade.slurm`)

| label | model | layout | job | comparator |
|---|---|---|---|---|
| `eqb-mesh-ref` | asm-mesh | committed | 11613555 | none exists: this is the first ASM+mesh baseline |
| `eqb-mesh-dz05` | asm-mesh | dz 0.05 | 11613556 | `eqb-mesh-ref` |
| `eqb-alm-dz05` | alm | dz 0.05 | 11613557 | `alm-U7-coarse-hubfix` |
| `eqb-asm-dz05` | asm | dz 0.05 | 11613558 | `asm-U7-coarse-asm-mf1` |

Read with `comparePhaseVI.py --run-dir runs/<model>-U7-coarse-<label> --speed 7 --sequence H --allow-short-window`
and `compareSectionLoads.py --alm-dir ...` (check `run.json` `blade_dz` first). Accept only if
equispaced is within the ALM-ASM bound of the Model Definition.

## Resume here (written 2026-10-12, end of session)

- Branch `feat/phasevi-equispaced-blade` (commits cfaeeff, ecfe724, 8893814). Jobs 11613555-58 (`squeue`/`sacct` first; 11613558 was pending on AssocMaxJobsLimit).
- Then: read the four arms (recipe above), write the table here, decide acceptance, close P1.5 in `validation-master-plan.md`, Model Definition v1.1 entry (E4), continue with P2.1.
- Open decision: `validation/phaseVI/geometry/phaseVI_blade_dz0p05.{stl,json}` are untracked; proposal is to version them (0.5 MB).
- Do not rebuild `libturbinesFoam` while any arm is queued or running.


## Result E3 2026-10-13 (`scripts/compareEquispacedArms.py`, jobs 11613555-58 all COMPLETED, `run.json` `blade_dz` 0.05 in the three equispaced arms, null in the references)

Relative change of the simulated value, equispaced dz 0.05 against committed layout (4 revs, coarse, 7 m/s, H, short window):

| arm | P | T | cn max over r/R | ct max over r/R |
|---|---|---|---|---|
| ASM+mesh (`eqb-mesh-dz05` vs `eqb-mesh-ref`) | -0.072 % | -0.028 % | 0.14 % (0.47) | 0.11 % |
| ALM (`eqb-alm-dz05` vs `alm-U7-coarse-hubfix`) | -0.077 % | -0.036 % | 0.13 % (0.95) | 0.69 % (0.30) |
| ASM (`eqb-asm-dz05` vs `asm-U7-coarse-asm-mf1`) | -0.067 % | -0.045 % | 0.13 % (0.95) | 0.66 % (0.30) |

Acceptance (bound: ALM-ASM cp difference of the Model Definition, 2 %): **accepted**, worst case 0.69 %
(ct at r/R 0.30, the station nearest the root transition; cn there changes 0.02 %). The change is the same
in ALM and ASM, so it is a layout effect on the ALM/ASM element integral, not a model effect. Absolute
levels unchanged: P vs measured -10.8 % (ALM 5.301 kW, ASM 5.308 kW, ASM+mesh 5.112 kW vs 5.946 kW),
all within the +-15 % band.

Side finding, not P1.5: the first ASM+mesh baseline sits 3.6 % below ALM in power (5.116 vs 5.305 kW, committed
loft), outside the 2 % ALM-ASM band for "ASM+mesh against ALM". Same on the equispaced layout (-3.6 %), so the
layout does not cause it; it belongs to the ASM+mesh residual issue (`odd/issues/asm-mesh-residual-vs-alm.md`).

Remaining: E4 (Model Definition v1.1 entry); decide whether to version `geometry/phaseVI_blade_dz0p05.{stl,json}`.
