# Feature: IEA 15 MW ASM cases (actuator surface, without and with mesh)

- **Status:** design (implementation next)
- **Branch:** `feat/dagsorensen-tip-correction`
- **Created:** 2026-10-01
- **Package:** `turbinesFoam/validation/iea15mw/`
- **Related:** `odd/tasks/iea15mw-p3-run.md` (ALM runs), `iea15mw-blade-geometry-mapping.md`

## Objective

Add the **actuator-surface (ASM)** model to the IEA 15 MW case, in two steps:

- **ASM (no mesh)** — `elementType actuatorSurfaceElement`: like the ALM but the
  force is spread over `nChordwise` chord strips (the chord line, no profile
  shape), with a mesh-based projection width.
- **ASM + mesh** — the same plus `surfaceGeometry "<stl>"`, so the element
  samples an imported triangulated blade surface (from Aeroelast).

Both must respect the **Aeroelast convention: the blade rotates clockwise**.

## What turbinesFoam provides (verified in source)

`actuatorSurfaceElement` (`actuatorLineElement/actuatorSurfaceElement.C`):
- `chordPoint(k) = position + (chordMount − (k+0.5)/nChordwise)·c·ĉ`;
- `ε = 2·cbrt(V[cell])·meshFactor` (mesh-based, from Troldborg 2008);
- the force is applied around each chord strip with a Gaussian.

`actuatorLineSource` reads the optional `surfaceGeometry` (a filename): when set
it activates surface sampling (`actuatorLineSource.C:76, 211, 602`). The only
difference between the Phase VI `fvOptions.ASM` and `fvOptions.ASM-MESH` twins
is that single line.

## Rotation direction — a real blocker

`turbineALSource` fixes the direction: `omega_ = tipSpeedRatio·mag(V)/R`
(always positive) and `azimuthalDirection_ = axis × vertical`; the header says
*"Positive anti-clockwise when looking along axis direction"*. There is **no
direction switch**. The current ALM case therefore rotates counter-clockwise;
Aeroelast states *"clockwise when viewed from above (wind comes from the
left)"*. Decision: add a **`--rotation {ccw,cw}`** option, default **cw**, which
flips the applied azimuth (a C++ direction factor on the azimuth, not on the
TSR, so the coefficient normalisation keeps its sign). The exact Aeroelast sign
must be confirmed against CCBlade before it is frozen.

## Mesh — the ASM needs the chord resolved

The ASM projection width is set by the local cell (`ε = 2·cbrt(V)·meshFactor`),
so the chord must be resolved: the 15 MW max chord is 5.765 m, the tip chord
0.5 m. At D/32 the cell is 7.5 m — the chord is **smaller than one cell**. A
uniformly refined D/128 domain is prohibitive.

**Approach (maintainer):** keep a **less dense background mesh** (the current
parametric box) and use **`snappyHexMesh`** to refine **only around the blade**
(the staged blade STL), targeting the local chord. That is a refinement-zone
problem, not a whole-domain one.

## Tasks

1. [ ] **Rotation**: add a C++ `rotationDirection`/sign factor to the ALM
       azimuth (default counter-clockwise, unchanged for existing cases) and a
       `--rotation {ccw,cw}` in `generate_case.py`; confirm the Aeroelast
       (= CCBlade) sign.
2. [ ] **ASM case (no mesh)**: `--model {alm,asm,asm-mesh}` in the generator;
       emit the `actuatorSurfaceElement` blade dict with `nChordwise`, plus the
       `fvOptions.ASM` / `fvOptions.ASM-MESH` twins. Default model stays `alm`.
3. [ ] **Blade surface STL from Aeroelast**: `aeroelast --export-mesh`/`--export-parts-dir`
       (`BladeMesh`/`RotorMesh`), committed under `geometry/` with a sha256, and a
       `stage_blade_stl.py`-style staging into `constant/triSurface/`.
4. [ ] **Background + snappyHexMesh**: keep the parametric background box; add a
       `snappyHexMeshDict` with a `refinementSurfaces`/`searchableBox` region
       around the blade sized from the local chord; verify the tip chord (0.5 m)
       is resolved and the cell count stays bounded.
5. [ ] **Meshing tests + a `--check`** for the snappy stage; document the ASM
       mesh requirement in the README.

## Open questions

- Which exact Aeroelast/CCBlade rotation is "clockwise", and viewed from where.
- The `snappyHexMesh` target cell size vs the local chord (a rule, e.g. ≥4 cells
  per local chord), and the resulting cell budget.
- Whether the tower/hub need the ASM too, or stay ALM (they are drag bodies).
