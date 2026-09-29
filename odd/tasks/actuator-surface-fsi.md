# actuator-surface-fsi — Plan de implementación (v5)

## Objetivo

Dar al ASM de turbinesFoam la capacidad de (a) **exportar** las fuerzas
aerodinámicas sobre la geometría de la pala y (b) **deformar** esa geometría a
partir de un campo de desplazamientos, para acoplarlo como proveedor en el
pipeline FSI donde `precice-openfoam-adapter` es el participante OpenFOAM.

## Principio de diseño

**turbinesFoam no sabe que es un participante FSI.** Expone fuerzas y acepta
desplazamientos como **campos en el object registry**, siguiendo el patrón de
`omegaOverrideField_` / `fsiOmega`. El adapter es el único que habla con
preCICE. La interfaz es 100% por campos.

## Reconciliación con el código existente (corrección de v4)

El ASM **ya existe**: `surfaceSamplerBase` (en `nacelleSurface/`),
`bladeSurfaceSampler`, `nacelleSurfaceSampler`, `bladeSurfaceSource`,
`nacelleSurfaceSource`, y las specs OpenSpec `surface-sampling-contract`,
`blade-surface-source`, `nacelle-surface-source`, `actuator-surface-element`.

`surfaceSamplerBase` está explícitamente diseñado para extenderse
(*"Concrete samplers add their own force model, body frame and per-node force
lists"*).

**Decisión:** extender `surfaceSamplerBase` con una capa de vértices FSI,
**no** crear un fvOption nuevo. El camino AL/ASM queda intacto cuando la FSI
está apagada (default). Motivos: no duplicar ~1k líneas, reusar el contrato de
sampling, y mantener una sola fuente de verdad para la geometría.

## Acotación geométrica: mallas mixtas y múltiples formatos

`surfaceSamplerBase` usa hoy `triSurface` = `PrimitivePatch<List<labelledTri>>`
→ **solo triángulos**. Para caras mixtas (tri/quad/poly) y formatos múltiples
(STL, OBJ, VTK, …) se migra a **`MeshedSurface<face>`** =
`PrimitivePatch<List<face>>`.

Verificado en el source de OpenFOAM v2506:

- `MeshedSurface<face>::New(const fileName&)` — *"file type implicit from
  extension"* (auto-detección)
- Expone `faceCentres()`, `faceNormals()`, `magFaceAreas()` **y `points()`**

La migración es **backward-compatible**: para STL (siempre triángulos) el
comportamiento es idéntico. Solo cambia si el input tiene no-triángulos.

El **point cloud** que se comunica con preCICE son los **vértices** de la malla
(`surface_->points()`), no los centroides de caras.

## Supuesto aerodinámico: perfil 2D rígido (Opción A) — validado contra OpenFAST

La deformación estructural cambia posición/twist/sweep de las secciones, pero
cada sección usa su **tabla de perfil 2D original** (`cl(α)`, `cd(α)`, `cm(α)`).
Verificado en código de OpenFAST/AeroDyn — ver
`odd/references/openfast-airfoil-rigid-assumption.md`:

- `AeroDyn.f90:3782`: `twist(j) = -thetas(3)  ! twist (including pitch and aeroelastic deformation)`
- `AirfoilInfo.f90:1790`: `AFI_ComputeAirfoilCoefs( AOA, Re, UserProp, ... )` — lookup estático
- `input.rst:666`: *"The airfoil shape is currently unused by AeroDyn"*

Extensión futura (Opción B): el mecanismo `AFTabMod = 3` (`UserProp`) de
AeroDyn permite tablas indexadas por una segunda variable.

## Formulación FSI del proyecto: corrotacional, deformar→rotar

`README.md` sección *"FSI Motion Model"*:

```
U_total(x) = R(t) · (x + u_fsi(x)) - x
```

**Orden crítico:** 1) deformar `x' = x + u_fsi`; 2) rotar `x_final = R(t)·x'`.

Verificado en `solidBodyDisplacementLaplacianZoneFvMotionSolver.C:476-487`:

```cpp
const pointField allDeformed = points0() + pointDisplacement_.primitiveField();
curPoints = transformPoints(solidBodyMotionPtr_().transformation(), allDeformed);
```

Implicancias:

- `u_fsi` llega en el **frame global**, relativo a la configuración de
  **referencia (no rotada)**.
- El ASM reproduce: `currentPoints = R(t) · (referencePoints + u_fsi)`.
- **Recomputar desde la referencia cada paso**, no acumular incrementalmente.
- **Lockstep:** `R(t)` es la misma rotación que el motion solver.
- El sampler hoy rota **incrementalmente** (`turbineALSource::rotate()`,
  `turbineALSource.C:312`). Hay que exponer el **ángulo total** (`angleDeg_`) y
  recomputar desde la referencia.

## Gestión del estado geométrico: referencia vs actual

| Dato | Rigidez (rotar/trasladar/pitch) | Deformación (no rígida) |
|---|---|---|
| `points()` / vértices | rotar | + desplazamiento por vértice |
| centroides `positions_` | recomputar de `points` | recomputar de `points` |
| `normals_`, `areas_` | recomputar | recomputar |
| asociación nodo↔elemento | fija | **fija** (identidad de referencia) |
| `candidates_` | fija | **reconstruir** si el desplazamiento es grande |
| geometría de elementos BEM | sigue la rotación | actualizar desde el mapeo |

Puntos de código: `bladeSurfaceSampler.C:620` (candidates una sola vez),
`buildPartition()` (asociación desde la geometría de construcción),
`areas_` desde `magFaceAreas()`.

## Campos del registry (contrato)

| Campo | Tipo | Escribe | Lee | Contenido |
|---|---|---|---|---|
| `surfaceCoords` | `vectorIOField` | turbinesFoam | adapter | Vértices de la malla (frame global) |
| `surfaceForces` | `vectorIOField` | turbinesFoam | adapter | Fuerza por vértice (frame global) |
| `surfaceDisplacement` | `vectorIOField` | adapter | turbinesFoam | `u_fsi` por vértice (frame global) |

Configurables en el sub-dict `fsi` del sampler. Default-off: sin `fsi` no se crea
ningún campo y el comportamiento es el actual.

### Convención de frames (global)

Igual que el adapter de wall. `ForceBase.C:149-156`:

```cpp
forceField.boundaryFieldRef()[patchID] = surface * pb[patchID] * rhob[patchID];
forceField.boundaryFieldRef()[patchID] += surface & devRhoReffb[patchID];
```

`Sf()` y `devRhoReffb` son globales. Los tres campos van en el frame global.

### Omega: constante o desde preCICE

Reusar el patrón dual de `turbineALSource::updateTSROmega()`
(`turbineALSource.C:237`): sin `omegaOverrideField` → constante / ley de TSR;
con `omegaOverrideField` → campo del registry actualizado por el adapter vía
`globalData` (`AngularVelocity`), igual que `fsiOmega`. Ortogonal al coupling de
fuerzas y desplazamientos.

## Arquitectura

```
turbinesFoam (ASM)                          precice-openfoam-adapter
┌───────────────────────────────┐          ┌────────────────────────────────┐
│ surfaceSamplerBase            │          │ Interface (pointCloud)         │
│  └ capa de vértices FSI       │          │  ├ lee surfaceCoords → setMesh │
│     · surfaceCoords           │◀────────▶│  └ update coordinates          │
│     · surfaceForces           │  campos  │ PointCloudVectorCoupler        │
│     · surfaceDisplacement     │  registry│  ├ write() surfaceForces       │
│ bladeSurfaceSampler           │          │  └ read()  surfaceDisplacement │
│  └ R(t)·(ref + u_fsi)         │          └────────────────────────────────┘
└───────────────────────────────┘                        │
                                                         ▼
                                                   preCICE ↔ sólido
```

## Extensión del adapter

### 1. `LocationType::pointCloud`

Nuevo valor en `CouplingDataUser.H`. En `Interface.C`, branch para
`locations pointCloud`:
- Lee `coordinateField` del `preciceDict`
- Busca el `vectorIOField` en el registry
- Registra vértices con `precice_.setMeshVertices()`
- No usa patches ni cellSets

### 2. Sin actualización de coordenadas (decisión cerrada)

La malla se conecta **una sola vez**: preCICE arma el mapeo en la configuración
de referencia y lo mantiene constante, asumiendo que las mallas se mantienen
**solidarias** durante todo el acoplamiento. Solo se intercambian el vector de
fuerza y el vector de deformación.

preCICE 3.4.1 **no expone** actualización de coordenadas tras `initialize()`
(verificado: `setMeshVertices` solo antes de `initialize()` o tras
`resetMesh()`). El adapter registra el point cloud una vez desde
`surfaceCoords`; esa referencia es la de setup (t=0) y **no se reescribe** en
el loop. No hace falta ningún método de actualización.

### 3. `PointCloudVectorCoupler`

`CouplingDataUser` genérico que lee/escribe un `vectorIOField` del registry:
- `write()`: copia el campo de datos al buffer
- `read()`: copia del buffer al campo de datos
- `isLocationTypeSupported()`: solo `pointCloud`

### 4. `preciceDict`

```cpp
interfaces
{
    TurbineSurface
    {
        mesh            Turbine-Surface-Mesh;
        locations       pointCloud;
        coordinateField surfaceCoords;

        writeData ( Force { name Force; solver_name surfaceForces; } );
        readData  ( Displacement { name Displacement; solver_name surfaceDisplacement; } );
    };
};
```

## Tareas (orden de ejecución)

### T1 — Reconciliar diseño y contrato ✅ (este documento)
- Extender `surfaceSamplerBase`, no fvOption nuevo
- Migrar a `MeshedSurface<face>`
- Contrato de campos, frames, omega, composición corrotacional

### T2 — Migrar `surfaceSamplerBase` a `MeshedSurface<face>` + acceso a vértices
- `autoPtr<triSurface>` → `autoPtr<MeshedSurface<face>>`
- `triSurface::New` → `MeshedSurface<face>::New`
- Accessor `const pointField& surfacePoints()`
- Verificar backward-compat con STL (Phase VI, nacelle)

### T3 — Campos FSI en el sampler
- Sub-dict `fsi` opcional; default-off
- Crear `surfaceCoords`, `surfaceForces`, `surfaceDisplacement` (`vectorIOField`)
- Escribir `surfaceCoords` desde `surfacePoints()`

### T4 — Adapter: `LocationType::pointCloud` + registro de vértices ✅
- Enum, parsing en `Adapter.C`, branch en `Interface::configureMesh()`
- Registro replicado desde el `vectorIOField` de coordenadas (una vez)
- read/write con semántica `globalData` (master + broadcast/consistencia)
- Commit `c16f306`

### T5 — Adapter: `PointCloudVectorCoupler`
- Nuevo `CouplingDataUser`; wiring en el módulo generic

### T6 — Vertical slice: build + verificación de registro y read/write
- `./Allwmake` en ambos lados
- Caso mínimo: coordenadas registradas, datos escritos/leídos

### T7 — Proyección de fuerzas faciales→vértices + export

Hoy `bladeSurfaceSource::distribute()` calcula una fuerza **por centroide de
cara** (`sampler_.nodeForces_` = `patchAreaShare_*element.force()` y
`distributed[]` con densidad aplicada, frame global). El point cloud FSI son
**vértices** (`surface_->points()`), en orden 1:1 con la cara (nodo i = cara i).

Mapeo (conserva la fuerza total): cada cara reparte su fuerza por igual entre
sus vértices; cada vértice suma las contribuciones de sus caras adyacentes.

```
vertexForces[v] = sum over faces f incident to v of  F_f / nVertices(f)
```

- Nuevo `surfaceSamplerBase::writeForceField(const List<vector>& faceForces)`:
  proyecta y escribe `surfaceForces` (frame global, SI). No-op si la capa FSI
  está apagada.
- Llamado desde `bladeSurfaceSource::distribute()` con `distributed[]`.
- No toca la distribución al volumen (validada) ni el camino AL.

### T8 — Deformación corrotacional + recálculo
- `deform()` lee `surfaceDisplacement`
- `currentPoints = R(angleDeg_) · (referencePoints + u_fsi)`
- Actualizar `points()` de la `MeshedSurface`; recomputar centroides/normales/areas
- Mantener asociación desde la referencia; reconstruir candidates por umbral

### T9 — Validación completa y docs

**Harness acordado (absorbe T6):**

- Caso base: `turbinesFoam/validation/phaseVI/` variante **ASM-MESH**
  (`axialFlowTurbineALSource` + `surfaceGeometry constant/triSurface/phaseVI_blade.stl`).
- Solver estructural **dummy** (C++ + preCICE, molde del `solverdummy` de
  preCICE): lee `Force`, devuelve `Displacement` mock (p.ej. `u = k*F` o un
  perfil prescrito) sobre los **mismos vértices** del STL para mapeo 1:1.
- `precice-config.xml` con dos participantes (Fluid = adapter, Solid = dummy),
  mapeo `nearest-neighbor` o `rbf` sobre la malla de la pala.
- Variante de run con el sub-dict `fsi` en `blade1` (y nombres distintos en
  `blade2`, que hereda con `$blade1`) + `preciceDict` con `locations pointCloud`.

Verifica: registro del point cloud, escritura de fuerzas, lectura de
desplazamientos, y el acoplamiento estable con omega constante y con omega
anidado. Luego: `CHANGELOG.md` raíz y README.

## Archivos a crear

```
precice-openfoam-adapter/modules/generic/PointCloudVectorCoupler.H
precice-openfoam-adapter/modules/generic/PointCloudVectorCoupler.C
```

## Archivos a modificar

```
turbinesFoam/src/fvOptions/nacelleSurface/surfaceSamplerBase.H
turbinesFoam/src/fvOptions/nacelleSurface/surfaceSamplerBase.C
turbinesFoam/src/fvOptions/bladeSurface/bladeSurfaceSampler.H
turbinesFoam/src/fvOptions/bladeSurface/bladeSurfaceSampler.C
turbinesFoam/src/fvOptions/bladeSurface/bladeSurfaceSource.H
turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineSource.C
turbinesFoam/src/fvOptions/Make/files

precice-openfoam-adapter/CouplingDataUser.H
precice-openfoam-adapter/Interface.H
precice-openfoam-adapter/Interface.C
precice-openfoam-adapter/Adapter.C
precice-openfoam-adapter/modules/generic/ModuleGeneric.C
precice-openfoam-adapter/modules/generic/ReadWrite.H
precice-openfoam-adapter/modules/generic/ReadWrite.C
precice-openfoam-adapter/Make/files

.gitignore   # refs/ (referencia OpenFAST, fuera de git)
```

## Commits propuestos (work units)

1. `refactor(turbinesFoam): migrate surfaceSamplerBase to MeshedSurface<face>`
2. `feat(turbinesFoam): expose surface vertices and FSI registry fields`
3. `feat(adapter): add pointCloud location type and vertex registration`
4. `feat(adapter): add PointCloudVectorCoupler for vectorIOField exchange`
5. `feat(turbinesFoam): project surface forces to vertices and export`
6. `feat(turbinesFoam): corotational surface deformation from registry`
7. `docs: document the ASM FSI provider contract`
