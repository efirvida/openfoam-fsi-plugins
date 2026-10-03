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

## Rotation direction — RESOLVED: keep ccw

`turbineALSource` fixes the direction: `omega_ = tipSpeedRatio·mag(V)/R`
(always positive) and `azimuthalDirection_ = axis × vertical`; the header says
*"Positive anti-clockwise when looking along axis direction"*. A
`rotationSign_` (`fvOptions rotationDirection ±1`) and `--rotation {ccw,cw}` were
added, applied to the applied azimuth and the blade speed only (the TSR used for
cp/ct keeps its sign).

**A naive cw flip is WRONG.** A dev-queue smoke test (0.1 rev) showed that
`rotationDirection -1` inverts the azimuth *and* the rotor thrust (cd +1.13 →
−1.06), because the sense is coupled to the blade geometry (twist/AoA).

**Pinned by physics against CCBlade** (`BEMSolver.distributedAeroLoads` at the
rated point) vs the turbinesFoam ALM first step, at r/R ≈ 0.30:

| source | alpha | Cn / c_ref_n |
|---|---|---|
| CCBlade / Aeroelast | 9.16° | **+1.596** |
| turbinesFoam ccw (current) | 14.26° | **+2.306** |
| turbinesFoam cw (flip) | 26.74° | **−2.306** |

The CCBlade Cn is positive and only the ccw reproduces it. CCBlade carries
`OmegaV` along the wind axis (+X) while turbinesFoam carries `omega_` along
`axis_` (upwind); the **labels are opposite but the physical rotor is the
same**. So the default stays **ccw** (the physical Aeroelast rotation) and
`--rotation cw` remains available but unused.

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

- The `snappyHexMesh` target cell size vs the local chord (a rule, e.g. ≥4 cells
  per local chord), and the resulting cell budget.
- Whether the tower/hub need the ASM too, or stay ALM (they are drag bodies).

## Progress log — ASM implementation (2026-10-01)

### Etapa A — ASM sin malla ✅ (commit `9a49c37`)
- `generate_case.py --model {alm,asm,asm-mesh}` con los tres twins
  (`fvOptions.ALM`, `.ASM`, `.ASM-MESH`); `--model` instala el elegido como
  `system/fvOptions`. El runner reenvía `TURBINE_MODEL` / `TURBINE_N_CHORDWISE`.
- Smoke dev 11605633 (0.05 rev, coarse): `elementType actuatorSurfaceElement;
  nChordwise 5;`, coeficientes emitidos, `IEA 15 MW run complete`. ✅
- Caveat: en D/32 el `ε` del ASM es por celda (`2·∛V·meshFactor` ≈ 15 m) y la
  cuerda máxima es 5.77 m → la fuerza se embarrona. Corre, pero **no es
  físicamente válido**: hace falta la cuerda resuelta (etapa B).

### Etapa B — STL de pala ✅ (`bceeef1` + `ccec95c`)
- Exportado con Aeroelast desde el WindIO yaml (element_size 0.2 m, 100 236
  triángulos), commiteado binario (5 MB) en `geometry/stl/iea15mw_blade.stl`
  con `geometry/metadata/iea15mw_blade.json` (sha256 + procedencia) y
  `tools/stage_blade_stl.py` (verifica sha256 y stagea a
  `constant/triSurface/`); el runner lo stagea para `--model asm-mesh`.
- **Hallazgo (smoke 11605648 abortó, y fue correcto)**: `BladeMesh` exporta la
  pala en el frame raíz-de-pala (span Z 0..117 = `BlSpn`) mientras los
  elementos viven en r = `HubRad`..`HubRad+BlSpn` (3.97..120.97).
  `bladeSurfaceSampler::buildPartition` compara las coordenadas de span de
  nodos y elementos restando **el mismo** `surfaceOrigin` a ambos, así que el
  corrimiento relativo sobrevive → la última estación de elemento quedaba sin
  caras (`FatalError`). O sea: el aborto es una invariante sana, no un bug de
  config.
- **Fix**: exportar con `RotorMesh --n-blades 1 --hub-radius 3.97` (Z
  3.970..120.970 = frame del caso). `BladeMesh` no acepta placement; sólo
  `RotorMesh`/`RotorHubMesh` toman `hub_radius`.
- Re-smoke dev 11605660 ✅: `100236 nodes over 147 element patches` por pala
  (147 = `nElements` de la pala), cero `patch ... is empty`, run completo.
- Caveat del sampler: mapea la superficie con **un único eje de span rígido**,
  así que el prebend/sweep/`curveAngle` quedan representados sólo de forma
  aproximada. No hay frame curvilíneo.

### Pendiente
- Etapa B2: fondo paramétrico + `snappyHexMesh` refinando alrededor de la pala
  (cuerda resuelta, tip 0.5 m) → recién ahí la corrida ASM es físicamente
  comparable contra ALM/OLAF.

### Etapa C — comparacion ASM vs ALM vs ASM-mesh

**Objetivo**: comparar los tres modelos sobre LA MISMA malla (fondo coarse +
castellated del disco, nivel 3), para que la unica diferencia entre los casos sea
el modelo de fuerza, no la resolucion.

**Casos armados** (`runs/iea15mw-asmcmp-*`, generados con
`--snappy on --snappy-level 3 --write-interval-deg 60`):

| caso | elementType | nChordwise | surfaceGeometry | deltaT |
| --- | --- | --- | --- | --- |
| alm | actuatorLineElement | - | - | 0.00937 |
| asm | actuatorSurfaceElement | 5 | no | 0.00937 |
| asm-mesh | actuatorSurfaceElement | 5 | si | 0.00937 |

**Cambio de generador que hizo falta**: `--snappy {on,off}` desacopla el
refinado del modelo. Antes el snappy estaba atado a `asm-mesh`, asi que ALM y ASM
no podian correr sobre la malla refinada, y su `deltaT` habria quedado en el del
fondo (7.5 m) dando Courant ~4 sobre celdas de 0.94 m. Ahora el refinado es
explicito y el `deltaT` lo sigue (`dt_level`), con default "on iff asm-mesh" para
no cambiar los casos existentes.

**Bloqueante para correrlos**: `scripts/run_iea15mw_case.sh` todavia ejecuta
`snappyHexMesh` solo cuando `TURBINE_MODEL=asm-mesh`. Necesita un
`TURBINE_SNAPPY` (default: on iff asm-mesh) para que los tres usen la misma
malla. No se puede editar con los P3 en vuelo (bash re-lee por offset).

**Salida esperada**: cp y empuje de rotor, mas las cargas spanwise
(`postProcessing/actuatorLineElements/<t0>/...` para el ALM y
`postProcessing/actuatorLines/<t0>/...` para los ASM) contra la referencia
OLAF/BEM y WISDEM.

**Nota de fisica**: los tres comparten `epsilon` del ASM segun celda
(`2*cbrt(V)*meshFactor`), que en la malla refinada da ~1.9 m frente a la cuerda
maxima de 5.77 m, asi que las tiras de cuerda (`nChordwise 5`) quedan resueltas.

## Etapa D — relanzamiento con dominio y refinado corregidos (2026-10-02)

El bloqueante de la Etapa C quedo resuelto en `ab705b3` (rename `TURBINE_*` +
`--snappy` desacoplado del modelo). Los 4 jobs de la primera tanda
(`11606518-11606521`) se cancelaron a las 20:25 tras ~10 rev; el analisis de
residencia mostro que ese horizonte no converge y el mantenedor fijo cuatro
correcciones (transcript de la sesion previa, mensajes 1813 y 1823):

| # | correccion | decision |
| --- | --- | --- |
| 1 | limpiar | solo los 3 `runs/iea15mw-asmcmp-*`; los CSV de `postProcessing/` se archivan, los campos y la malla se borran. `coarse-20rev` queda congelado |
| 2 | revoluciones | **20** (= 159,2 s = 7,05 D de recorrido del fluido) |
| 3 | dimensiones del dominio | **3D aguas arriba / 7D aguas abajo / ±3D lateral** (fondo 2,36 M celdas) |
| 4 | refinado snappy | nueva region `rotorWake`: cilindro de radio R desde el plano del rotor hasta 2D aguas abajo, **nivel 2** |

**Por que el punto 3**: con el dominio de 20D la residencia es 56,7 rev, asi que
20 rev eran 0,35 residencias y el `cp` caia por llenado de estela, no por fisica
del rotor. Con 3/7 el dominio mide 10D -> 28 rev de residencia y las 20 rev
quedan en ~0,7, con el outlet a 7D (justo donde la estela sale a las 20 rev).
Achicar el fondo (4,30 M -> 2,36 M celdas) ademas paga el refinado nuevo.

**Por que el punto 4**: `towerWake` cubre `z in [-145, +4,4] m` (la banda de la
torre) y ±20 m lateral. Aguas abajo del disco no habia refinado por encima de
z ~ +4,4 m, asi que la estela del rotor (hasta z = +121 m) corria a la celda del
fondo (7,5 m). La region nueva la cubre a nivel 2 (1,88 m), el mismo nivel que
el tower shadow, para que estela y sombra sean comparables.

**Juez externo (elegido)**: referencias cruzadas OLAF / BEM / WISDEM / tabla
publicada — no un revisor LLM.

### Tasks — Etapa D

1. [ ] `render_snappy_dict`: emitir la region `rotorWake`
       (`ASM_ROTOR_WAKE_DOWNSTREAM_D`, radio `ROTOR_RADIUS`, nivel
       `level - ASM_WAKE_LEVEL_OFFSET`), aguas abajo = `-rotor_axis`.
2. [ ] Tests en `turbinesFoam/tests/test_iea15mw_case.py`: geometria y nivel de
       `rotorWake`, y que el caso commiteado siga limpio en `--check`.
3. [ ] `scripts/slurm/asmcmp.slurm` versionado: los tres casos son la misma
       malla y el mismo dominio, solo cambia `TURBINE_MODEL`.
4. [ ] Regenerar el `case/` commiteado + README + `CHANGELOG.md`.
5. [ ] Limpiar los 3 run dirs (archivar CSV, borrar campos/malla).
6. [ ] Smoke en dev: conteo de celdas y `deltaT` esperados antes de gastar 31 h.
7. [ ] Lanzar los 3 jobs de produccion y verificar el arranque.
8. [ ] (post-run) Comparacion de `cp`, empuje y cargas spanwise contra OLAF /
       BEM / WISDEM / tabla publicada.

**Costo medido**: malla vieja 5,83 M celdas a 56 ranks = 0,74 rev/h (1,35 h/rev).
Con 6,8 M celdas estimadas -> ~0,60 rev/h -> **~31 h para las 20 rev**.
