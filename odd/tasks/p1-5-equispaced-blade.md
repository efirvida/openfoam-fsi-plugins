# P1.5 — Equispaced blade discretisation (proposal, NOT started)

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

- [ ] **E1** Loft/element resampling with a chosen `dz` tied to `h` (the rule is NOT settled: the table
      above only measured fixed dz = 0.05 and 0.1 m; scan dz/h before choosing), exact S809 outboard, circle ->
      S809 morph kept in the root segments; surface area and chord/twist deviation vs the
      committed loft reported (area 4.88423 m^2 today).
- [ ] **E2** Same resampling for `elementData` (ALM, ASM, ASM+mesh stay consistent); station
      comparison rule in `compareSectionLoads.py`.
- [ ] **E3** A/B on the coarse mesh: ALM and ASM+mesh, committed vs equispaced, 4 revs. Accept
      only if the change is within the ALM-ASM bound of the Model Definition.
- [ ] **E4** Model Definition v1.1 entry; Phase VI baselines are re-run in P2.1 anyway, so doing
      this BEFORE P2.1 costs no extra baseline.
