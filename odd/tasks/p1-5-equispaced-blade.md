# P1.5 — Equispaced blade discretisation (in progress: E1 resampler done, integration pending)

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

- [~] **E1 (station resampler + rule done 2026-10-12; STL loft rebuild pending)** Loft/element resampling with a chosen `dz` tied to `h` (the rule is NOT settled: the table
      above only measured fixed dz = 0.05 and 0.1 m; scan dz/h before choosing), exact S809 outboard, circle ->
      S809 morph kept in the root segments; surface area and chord/twist deviation vs the
      committed loft reported (area 4.88423 m^2 today).
- [ ] **E2** Same resampling for `elementData` (ALM, ASM, ASM+mesh stay consistent); station
      comparison rule in `compareSectionLoads.py`.
- [ ] **E3** A/B on the coarse mesh: ALM and ASM+mesh, committed vs equispaced, 4 revs. Accept
      only if the change is within the ALM-ASM bound of the Model Definition.
- [ ] **E4** Model Definition v1.1 entry; Phase VI baselines are re-run in P2.1 anyway, so doing
      this BEFORE P2.1 costs no extra baseline.


## Result 2026-10-12 (no cluster needed; `scripts/scanEquispacedDz.py`, `tools/blade_resample.py`, `tests/test_blade_resample.py`)

Rule settled: **dz = min(0.05 m, h/2)**, root stations (r < 1.0085 m) kept verbatim.

- Deposit ripple with dz = f*h: f = 0.25..0.5 gives <= 2 % at every h (0.31 .. 0.039 m); f = 0.75 gives up to 7.6 %; f = 1.5 gives up to 11 %.
- Geometry kept (linear interpolation of the 26-station table): dz <= 0.05 m gives chord dev 0.0013 m, twist dev 0.06 deg, chord-area dev 0.001 %. dz = 0.1 m already loses 1.85 deg of twist at the root transition (r 1.0 .. 1.26 m), so h/2 alone is wrong on the coarse mesh; the 0.05 m cap is the geometric floor.
- Stations: dz 0.05 m gives 85 rows (3 root + 82 outboard) against 26.

Pending: E1 STL (needs `blade_phasevi.py` to accept a station list; `N_STATIONS`/`input_sha256` are pinned to 26), E2 (`blade_element_rows` already takes a station list; the sampler needs the element count tied to dz), E3 (4-rev A/B, needs the queue).
