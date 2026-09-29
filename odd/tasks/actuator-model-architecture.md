# Arquitectura objetivo: modelos de actuador y acoplamiento FSI en turbinesFoam

- **Status:** diseño (documento de arquitectura). No implementa código.
- **Branch:** `feat/nacelle-actuator-surface`
- **Created:** 2026-09-28
- **Alcance de la implementación:** sólo la funcionalidad existente (ALM + ASM
  sin malla + ASM con malla + FSI actual del ASM con malla). Los contratos de
  extensión para ALM y ASM-sin-malla FSI se **definen acá y se implementan más
  adelante**, sin rehacer código, siguiendo el contrato.
- **Documento relacionado:** `odd/tasks/actuator-surface-fsi.md` (plan v5 del
  FSI actual).

## Objetivo

Dejar `turbinesFoam/` organizado alrededor de **ejes ortogonales (A–E)**, de
modo que:

1. las físicas de actuador (línea / superficie) sean pares de primera clase;
2. la proyección de carga a la malla sea una estrategia explícita reutilizable;
3. el acoplamiento FSI sea un colaborador independiente, definido contra una
   **interfaz de acoplamiento abstracta** — no contra un sampler concreto;
4. agregar FSI para ALM o ASM-sin-malla en el futuro sea **implementar un
   contrato**, no reescribir la cadena.

## Problema (diagnóstico, con evidencia)

La organización actual es **ALM-céntrica** y el ASM entró por tres mecanismos
distintos, ninguno par del ALM:

| # | Mecanismo | Cómo se activa | Dónde vive |
|---|---|---|---|
| 1 | `actuatorSurfaceElement` (`: public actuatorLineElement`, override de 3 métodos, `.H:81,85,88`) | `elementType actuatorSurfaceElement` | `.../actuatorLineSource/**actuatorLineElement**/` |
| 2 | `bladeSurfaceSource` + `bladeSurfaceSampler` (redistribuidor post-hoc; no es `fv::option`, no está en RTS) | `surfaceGeometry "<stl>"` | `.../bladeSurface/` |
| 3 | `nacelleSurfaceSource` (`: public cellSetOption`, con RTS propia, `.H:103`) | `type nacelleSurfaceSource` | `.../nacelleSurface/` |

Síntomas concretos, verificados:

- **Base subexplotada / duplicación.** `turbineALSource` deja como stubs vacíos
  lo que debería unificar (`turbineALSource.C:100,106,350,436,446,457`). El tail
  de torque/power/drag de `addSup` es idéntico en las derivadas
  (`axialFlowTurbineALSource.C:904-916` vs `crossFlowTurbineALSource.C:634-646`)
  y se repite 3× por clase. `printCoeffs` es byte-idéntico en base y derivadas
  (`turbineALSource.C:467`, `axialFlowTurbineALSource.C:1064`,
  `crossFlowTurbineALSource.C:766`). La matriz de rotación está copiada 5×
  (`turbineALSource.C:65`, `actuatorLineElement.C:213` y `:1065`,
  `bladeSurfaceSampler.C:352`, `surfaceSamplerBase.C:392`).
- **God classes.** `actuatorLineElement.C` (1438 líneas) mezcla BEM, stall,
  augmentation, proyección, IO y FSI; `axialFlowTurbineALSource.C` (1128);
  `profileData.C` (941); `bladeSurfaceSampler.C` (881); `surfaceSamplerBase.C`
  (728).
- **Proyección partida en dos niveles.** El elemento proyecta
  (`actuatorLineElement::applyForceField`) y la fuente vuelve a proyectar
  (`bladeSurfaceSource::distribute`), con un booleano `surface_.valid()` que
  anula la proyección del elemento (`actuatorLineSource.C:814-817,868`).
- **FSI escondido.** Toda la capa FSI vive dentro de `surfaceSamplerBase`
  (creación de los registry fields `surfaceCoords`/`surfaceForces`/
  `surfaceDisplacement`, `surfaceSamplerBase.C:209-295`; captura de referencia y
  ley `R(total)·(ref + u)` en `fsiUpdateGeometry`, `:469-513`), físicamente
  ubicada en `nacelleSurface/` pero compartida por `bladeSurface/`. El paso de
  acoplamiento ocurre como efecto colateral de `addSup`
  (`actuatorLineSource.C:814-817`) y **sólo es alcanzable con ASM con malla**.
- **Intención FSI genérica ya presente pero sin contrato.** `actuatorLineElement`
  ya expone `setFsiGeometry(...)` (`.H:366`, `.C:281`) y
  `bladeSurfaceSampler::fsiUpdateElements` ya ajusta los elementos ALM con un
  rigid fit de Kabsch (`bladeSurfaceSampler.C:798`, `:766,788`). O sea: el
  FSI ya deforma elementos ALM, pero entrando sólo por la superficie con malla y
  sin contrato explícito.
- **`nacelleSurfaceSource` hereda la capacidad FSI y nunca la cablea** (su
  `addSup` no llama `fsiUpdateGeometry`).

## Principio de diseño: ejes ortogonales (A–E)

| Eje | Pregunta | Responsabilidad |
|---|---|---|
| **A. Topología** | ¿axial / cross-flow? ¿dónde rotor, hub, tower, nacelle? | layout y bookkeeping del rotor |
| **B. Modelo de elemento** | ¿cómo *genera* fuerza una estación/pánel? | **cadena ordenada de correcciones** + muestreo de inflow |
| **C. Proyección de carga** | ¿cómo *llega* la fuerza a las celdas? | kernel de distribución sobre el fluido |
| **D. Frontera FSI** | ¿cómo se *acopla* una superficie con la estructura? | IO de acoplamiento + cinemática de la frontera |
| **E. Cinemática / movimiento prescrito** | ¿cómo se mueve el rotor y sus cuerpos? | azimut, TSR/oscilación, tilt/yaw, pitching armónico |

Los ejes son independientes en el **modelo**, pero el código actual tiene
**escrituras cruzadas** entre ellos (ver H3/H4). El objetivo no es sólo
separarlos, sino **definir el contrato de esas escrituras** para que no salteen
los límites de eje.

Una simulación es una **combinación** (p.ej. ALM + proyección Gaussiana + sin
FSI; ASM-con-malla + proyección STL + `fsiBoundary`).

## Árbol objetivo

```
src/fvOptions/
  turbine/                       # EJE A — topología
    turbineALSource.{H,C}
    axialFlowTurbineALSource.{H,C}
    crossFlowTurbineALSource.{H,C}

  actuator/
    element/                     # EJE B — generación de fuerza
      actuatorElement.{H,C}          # base renombrada (RTS)
      actuatorLineElement.{H,C}      # concreta (nombre RTS PRESERVADO)
      actuatorSurfaceElement.{H,C}   # concreta (nombre RTS PRESERVADO)
      dynamicStall/  addedMassModel/  profileData/
    source/
      actuatorSource.{H,C}           # renombre interno de actuatorLineSource
    projection/                  # EJE C — fuerza → celdas
      loadProjection.{H,C}           # base abstracta
      pointGaussianProjection.{H,C}  # ALM
      chordStripProjection.{H,C}     # ASM sin malla
      meshSurfaceProjection.{H,C}    # ASM con STL ← absorbe bladeSurfaceSource
      surfaceSamplerBase / bladeSurfaceSampler / nacelleSurfaceSampler
    coupling/                    # EJE D — frontera de acoplamiento
      couplingInterface.{H,C}        # puntos + normales + pesos + frame
      fsiBoundary.{H,C}              # registry IO + cinemática, SOBRE couplingInterface
    kinematics/                  # EJE E — movimiento prescrito
      rotorKinematics.{H,C}          # azimut (forma cerrada), TSR/oscilación, persistencia
      harmonicPitching.{H,C}         # pitching por pala
  bodySurface/                   # nacelle como body-source
    nacelleSurfaceSource.{H,C}
```

## Contratos (interfaces objetivo)

### Eje B — `actuatorElement` (renombre del base `actuatorLineElement`)

Genera fuerza y expone sus datos; **no** proyecta a la malla.

```cpp
class actuatorElement {
    virtual void calculateForce(const volVectorField& Uin);  // cadena compartida
    virtual void sampleInflow(const volVectorField& Uin);    // hook: punto vs cord-averaged
    const vector& force() const;                             // por unidad de densidad
    vector moment(const point&) const;
    // Los nombres RTS "actuatorLineElement" y "actuatorSurfaceElement" se preservan.
};
// Se MUEVEN fuera del elemento (hoy en actuatorLineElement.H:267,276):
//   calcProjectionEpsilon(), applyForceField()
```

### Eje C — `loadProjection` (propiedad de la fuente, no del elemento)

```cpp
class loadProjection {
    virtual void project(volVectorField& field,
        const PtrList<actuatorElement>& es,
        const volScalarField* rho = nullptr) const = 0;
    virtual scalar epsilon() const = 0;
};
```

- `pointGaussianProjection` — extracción verbatim del `applyForceField` de ALM.
- `chordStripProjection` — distribución por franjas (`actuatorSurfaceElement`).
- `meshSurfaceProjection` — absorbe `bladeSurfaceSource` + `bladeSurfaceSampler`
  + su lockstep FSI/CSV.

### Eje D — `fsiBoundary` + `couplingInterface`

**Decisión arquitectónica central para evitar rehacer código:** `fsiBoundary`
se define **contra `couplingInterface`**, nunca contra `surfaceSamplerBase`. Hoy
el FSI está atado a `surfaceSamplerBase`, por lo que agregar FSI a ALM obligaría
a reescribir. La dependencia debe invertirse.

```cpp
// Lo provee la geometría/física. Es el único punto de extensión que hay que
// implementar para habilitar FSI en una física nueva.
struct couplingInterface {
    pointField  points;    // vértices de acoplamiento (global frame)
    pointField  normals;   // normales por vértice
    scalarField weights;   // pesos de partición de unidad (por vértice)
    tensor      frame;     // frame cuerpo→global
};
virtual couplingInterface couplingInterfaceSet() const = 0;

// Colaborador independiente: no sabe nada de Voronoi/kernel/distribución.
class fsiBoundary {
    void createFields(const dictionary& fsiDict);  // surfaceCoords/Forces/Displacement
    void captureReference();                       // congela la config de acoplamiento
    void accumulateRotation(point, axis, radians); // cinemática, alimentada por topología
    void applyDisplacement();                      // current = R(total)·(ref + u_fsi)
    void publishCoordinates();
    void publishForces(const pointField& vertexForces);
    // Compat: nombres y subdict 'fsi' sin cambios.
};
```

Composición y paso de acoplamiento **explícito** (hoy implícito en `addSup`):

```cpp
// actuatorSource
PtrList<actuatorElement>  elements_;     // EJE B
loadProjection*           projection_;   // EJE C
fsiBoundary*              fsi_;          // EJE D

void actuatorSource::couplingStep() {    // etapa nombrada del pipeline
    if (fsi_) { fsi_->applyDisplacement(); projection_->syncGeometry(fsi_->currentPoints()); }
}
```

Propiedades que esto habilita:

- `nacelleSurfaceSource` se vuelve FSI-capaz sin código nuevo (compone un
  `fsiBoundary`).
- ALM y ASM-sin-malla pueden exponer una nube de acoplamiento implementando
  `couplingInterfaceSet()` **sin tocar `fsiBoundary` ni la cadena de fuerza**.

## Extension points diferidos (ALM y ASM sin malla) — contrato definido, no implementado

Estos dos quedan **definidos pero no implementados**. Cuando haya disponibilidad,
se implementan siguiendo el contrato, sin mover archivos ni reescribir la
cadena:

| Física | `couplingInterfaceSet()` a implementar (futuro) | Interfaz |
|---|---|---|
| ALM | nube de las estaciones spanwise | **línea (1D)** |
| ASM sin malla | grilla span×cuerda desde `chordPoint(k)` / `nChordwise_` (`actuatorSurfaceElement.C:51`, `.H:70`) | **grilla 2D regular** |
| ASM con malla | vértices de la triangulación importada (implementación **actual**) | **superficie mojada** |

### Caveat de fidelidad (decisión abierta)

La ortogonalidad del mecanismo **no** implica equivalencia física:

- ALM proyecta una fuerza **volumétrica Gaussiana**, no una presión de
  superficie. Acoplar la línea a una viga o a una lámina reducida a la línea de
  cuarto de cuerda es razonable; acoplar ALM a una cáscara 3D exige reconstruir
  la huella de cuerda (no es directo).
- ASM con malla entrega presión de superficie; ASM-sin-malla entrega una
  superficie idealizada (grilla regular).

**Decisión abierta:** si ALM se ofrece como frontera FSI 1D con las
aproximaciones documentadas, o si se exige ASM (sin malla o con malla) para
acoplamiento a cáscaras.

## Compatibilidad (contrato con config y con el adapter)

Nada de configuración cambia. El refactor **no puede tocar**:

- `elementType actuatorLineElement | actuatorSurfaceElement` — nombres RTS
  preservados.
- `surfaceGeometry "<stl>"` — pasa a construir `meshSurfaceProjection`.
- `type turbineALSource | axialFlowTurbineALSource | crossFlowTurbineALSource |
  nacelleSurfaceSource`.
- `actuatorLineSourceCoeffs` — clave de subdict preservada.
- Subdict `fsi` con defaults `coordinateField surfaceCoords`, `forceField
  surfaceForces`, `displacementField surfaceDisplacement` — binding por nombre
  con `ReadWrite.H` (coupler de point cloud del adapter). El refactor no cambia
  el contrato.
- Renombre de clase `actuatorLineSource → actuatorSource`: es **interno**
  (se construye con `new`, no por RTS — `axialFlowTurbineALSource.C:353`), con
  alias si algún plugin externo incluye el header.

## Plan de fases (cada fase *behavior-preserving*)

Alcance: **sólo la funcionalidad actual** (las tres físicas existentes y el FSI
del ASM con malla). Ninguna fase agrega capacidad nueva.

| Fase | Movimiento | Riesgo |
|---|---|---|
| P0 | Extraer `loadProjection` + `pointGaussianProjection` desde `applyForceField` (verbatim) | bajo |
| P1 | `bladeSurfaceSource` → `meshSurfaceProjection` | bajo |
| P2 | Extraer `fsiBoundary` desde `surfaceSamplerBase` (IO + cinemática) e introducir `couplingInterface`; `meshSurfaceProjection` lo implementa | bajo |
| P3 | Nombrar la etapa `couplingStep` y sacarla del cuerpo de `addSup` (mismo orden) | medio |
| P4 | Renombre base `actuatorLineElement → actuatorElement` + movimiento de directorios (preservar RTS) | medio |
| P5 | `actuatorSurfaceElement` proyectando vía `chordStripProjection` | medio |
| P6 | `surfaceSamplerBase` fuera de `nacelleSurface/`; nacelle opta a `fsiBoundary` | medio |
| P7 | (aparte) dedup de `turbineALSource` / derivadas | — |

P2/P3 se priorizan temprano: es el eje que más condiciona el resto y el de menor
blast radius si se hace como **extracción pura** antes de mover archivos.

**Los bugs y las escrituras cruzadas NO son fases del refactor.** Son work
units separados, porque tocan comportamiento. Un refactor *behavior-preserving*
no los arregla en silencio ni los ignora.

## Work units (corrección y deuda) — no son fases del refactor

Registrados también en Engram (observaciones **214–219**; búsqueda por
`turbinesfoam/latent-bugs` o `turbinesfoam/actuator-architecture`), para que la
sesión de correcciones de física los tenga a mano desde cualquier sesión.

| ID | Origen | Qué | Tipo | ¿Cambia comportamiento? | Prioridad para correcciones de física |
|---|---|---|---|---|---|
| WU-B1 | H8 | `binarySearch` extrapola fuera de tabla con tamaños impares | bug (verificado por ejecución) | sí | **alta** — afecta coeficientes cl/cd/cm |
| WU-B2 | H9 | `LeishmanBeddoes::alphaSS_` leído sin inicializar | bug (UB) | sí | **alta** — primer paso del stall dinámico |
| WU-B3 | H7 | `reduceParallel` del stall dinámico nunca se llama | bug (paralelo) | sí (MPI) | media |
| WU-B4 | H3 | end-effect incondicional + inputs comentados (alpha/relVelMag); escritura cruzada rotor→elemento | diseño + bug | sí | media |
| WU-B5 | H4 | actualización de geometría FSI incompleta (staleness radial/cuerda) | diseño (Eje D) | sí | media (sólo si hay FSI) |
| WU-B6 | H6 | semántica de unidades del CSV inconsistente incomp/comp | contrato | sí | baja |
| WU-B7 | H5 | base RTS instanciable con cuerpos vacíos (`type turbineALSource`) | robustez (fail-closed) | no | baja |
| WU-B8 | H10 | inventario de código muerto | limpieza | no | baja |

Detalle con evidencia `file:line` de cada uno: sección *Hallazgos de la lectura
profunda* (abajo) y observaciones de Engram 214–219.

**Ordenamiento con el refactor:** WU-B1/WU-B2 tocan la cadena que el refactor
quiere reordenar (coeficientes y stall). Decidir si se corrigen **antes** (para
que la validación del refactor compare contra una línea base correcta) o
**después** (para no mezclar cambios de comportamiento con movimientos
estructurales). Recomendación: corregir WU-B1/WU-B2 primero si las correcciones
de física dependen de coeficientes correctos.

## Contrato de validación

Invariante ya declarado en el repo: *"ALM remains the byte-identical default"*.
Es el contrato de regresión de cada fase. Herramientas existentes:

- `tests/` (pytest) y `turbinesFoam/Alltest`.
- tutorial `axialFlowTurbineASM` con `compareALMvsASM.py`.
- `validation/phaseVI` con `fvOptions.ALM` / `.ASM` / `.ASM-MESH`.
- `validation/fsi-smoke` (harness ASM-MESH + solverdummy).

Cada fase: ALM byte-idéntico; ASM y FSI con diferencia explicable.

## Decisiones abiertas

1. **Dueño de la proyección (eje C).** A nivel fuente (recomendado: unifica los
   3 caminos; mueve `applyForceField` fuera del elemento) vs a nivel elemento
   (menor blast radius, mantiene la partición actual).
2. **Fidelidad de la frontera ALM** (ver *Caveat de fidelidad*): ¿ALM como
   frontera 1D documentada, o ASM obligatorio para cáscaras?
3. **Costo de divergencia con upstream.** P0–P2 son baratos; P5–P6 ya son fork
   divergente.
4. **Representación nodal intermedia.** Para habilitar FSI en ALM/ASM-sin-malla
   hace falta una representación por nodos (hoy sólo la tiene el ASM con malla) y
   **dos objetivos de proyección**: celdas del fluido (eje C) y nube estructural
   (eje D). Definir si esa representación nodal se vuelve canónica.
5. **Secuencia de los work units de corrección** (WU-B1..B8): ¿antes o después
   del refactor? Recomendación: WU-B1 y WU-B2 antes, por afectar coeficientes y
   stall dinámico.

## Hallazgos de la lectura profunda del código (v2)

Estos puntos **no estaban contemplados** en la primera versión del modelo. Se
verificaron contra el **código** (no contra comentarios ni docs); donde el
comentario contradice al código, se reporta el código.

### H1. La cinemática es un concern de primera clase (→ Eje E)

`turbineALSource` no sólo lleva bookkeeping: contiene física de movimiento real
que no estaba en el modelo de 4 ejes:

- `azimuth()` (`turbineALSource.C:258-310`): azimut en **forma cerrada** para TSR
  oscilante (ODE separable, desdobla la rama del `atan`), no integración.
- `rotate()` (`:312-348`): dos caminos — override externo **integrado
  incrementalmente** vs azimut derivado del tiempo; persiste `angleDeg.<name>`
  **en cada paso** para restart/rollback de preCICE.
- Derivadas: `harmonicPitching`, `tilt`, `yaw`.

**Consecuencia:** el plan deja de tratarlo como “bookkeeping de A” y lo aísla en
el Eje E. El contrato de persistencia (`angleDeg.<name>`, `omegaOverrideField`)
es parte del Eje E, no de la topología.

### H2. La generación de fuerza es una cadena ordenada y gated (precisión de B)

`actuatorLineElement::calculateForce` (`actuatorLineElement.C:923-1047`) aplica,
**en este orden exacto**: muestreo de inflow → remoción de flujo spanwise → `Re`
→ AoA → corrección de curvatura (gated) → lookup de coeficientes → augmentación
rotacional (gated) → stall dinámico (gated) → masa agregada (gated) → factor de
end-effect → ensamblado de fuerza. El modelo de B debe representar este
**pipeline**, no un blob “BEM+stall+augmentation”: cada corrección es un modelo
conectable con su propio gate y el orden es semántico.

### H3. Escrituras cruzadas entre ejes (rompe la ortogonalidad hoy)

- `axialFlowTurbineALSource::calcEndEffects` escribe **estado del elemento** vía
  `elements[j].setEndEffectFactor(f)` (`axialFlowTurbineALSource.C:678`), y el
  elemento la aplica **incondicionalmente**: `liftCoefficient_ *= endEffectFactor_`
  (`actuatorLineElement.C:1036`). El default `1.0` (`.C:753`) la hace no-op sólo
  por default; el header documenta “[0, 1]” y el multiplicador no está gated.
  Además sólo afecta **lift** (drag/moment intactos).
- `calcEndEffects` lee `relativeVelocity()`/`velocity()` **del paso previo**
  (antes de que las palas recalculen fuerza este paso) → factor atrasado un paso.
- El camino *liftingLine* de end-effects es efectivamente **sólo geométrico**:
  las dos líneas que poblarían `alpha`/`relVelMag` están **comentadas**
  (`actuatorLineSource.C:498-499`), así que usa `alpha=0.1 rad`, `relVelMag=1.0`.

**Consecuencia:** el diseño debe declarar **quién puede escribir qué** entre
ejes. La escritura rotor→elemento debe pasar por una interfaz declarada (p.ej.
el Eje A aporta un `rotorCorrection` que el elemento aplica como un paso más de
la cadena B), y el factor debe estar gated como las demás correcciones.

### H4. La actualización de geometría FSI es **incompleta** (staleness)

`actuatorLineElement::setFsiGeometry` (`actuatorLineElement.C:281-289`) actualiza
**sólo** `position_`, `chordDirection_`, `spanDirection_`. NO actualiza
`chordLength_`, `rootDistance_`, `radius_`, `rotorRadius_`, `chordRefDirection_`.
Tras una deformación FSI:

- la augmentación rotacional usa geometría radial **vieja** (`chordLength_/radius_`,
  `rotorRadius_/radius_`);
- `inflowRefAngle()` y las columnas de referencia del CSV usan
  `chordRefDirection_` vieja;
- el end-effect usa `rootDistance()` viejo (H3).

**Consecuencia:** el Eje D necesita un contrato de actualización de geometría
**completo** (qué campos se refrescan y cuándo), no “setear posición/cuerda/span”.

### H5. Contrato con el framework `fvOptions` — clases registradas con cuerpo vacío

- `turbineALSource` está en la tabla RTS (`turbineALSource.C:45`) y sus virtuales
  son **vacías** (`:100,106,350,436,446,457`). Por lo tanto `type turbineALSource;`
  es **config válida** que construye una opción **inerte** (sin palas, sin
  acumulación de fuerza) **en silencio**.
- `actuatorLineSource` también está registrada (`actuatorLineSource.C:43`), aunque
  se construye internamente con `new`.
- Los 3 `addSup` (`fvMatrix<vector>&,label` / `rho` / `fvMatrix<scalar>&,label`)
  son el contrato del framework y **no se pueden cambiar** al refactorizar.
- `actuatorLineElement::addSup(fvMatrix<vector>&, volVectorField&)` es **otra**
  firma (nivel elemento) → hazard de overload por nombre.

**Consecuencia:** el refactor debe (a) no exponer la base como instanciable, o
hacer que falle con `FatalError`; y (b) preservar exactamente las firmas del
framework.

### H6. Semántica de unidades/densidad de la salida es inconsistente

`multiplyForceRho` se aplica **sólo** en el camino compresible
(`actuatorLineElement.C:1268`) y **antes** de `writePerf()`. Por lo tanto las
columnas `fx,fy,fz` del CSV son **fuerza por unidad de densidad** en
incompresible y **fuerza real** (×ρ) en compresible. `moment()` mezcla
`forceVector_` con el término de momento de cabeceo. Es un contrato de salida a
fijar antes de mover IO.

### H7. Sincronización MPI prevista y nunca ejecutada

`dynamicStallModel::reduceParallel` y `LeishmanBeddoes::reduceParallel` están
definidas y la segunda **sobreescrita**, pero **no hay ningún llamador** en el
repo (grep). O sea: la sincronización de estado del stall dinámico entre ranks
diseñada para el LB **nunca corre**. Cualquier refactor debe decidir si se cablea
o se borra, explícitamente.

### H8. Bug de interpolación verificado por ejecución

`interpolateUtils::binarySearch` (`interpolateUtils.C:28-59`) **no llega al
último índice** para ciertos tamaños impares de tabla (verificado ejecutando la
función: falla con n=3, 5, 9). Consecuencia: `getPart`
(`interpolateUtils.C:94-120`) nunca entra a la rama de borde superior
(`xIndex + 1 == xList.size()`) y para un valor **por encima** del máximo de la
tabla **extrapola** con los dos últimos puntos en lugar de clampear. El
comentario dice “*use the highest value*” (`:100-107`); el código extrapola.
Afecta a `profileData` (interpolación por Re/AoA) y a
`LeishmanBeddoes::interpolateStaticParam`. Depende de la paridad del tamaño.

**Consecuencia:** es un **bug de corrección**, no un refactor. Debe ser un work
unit separado y explícito; un refactor *behavior-preserving* **no** debe
arreglarlo en silencio (cambiaría resultados), pero tampoco puede ignorarlo.

### H9. Lectura de no inicializado (verificada por lectura del ctor)

`LeishmanBeddoes::alphaSS_` (`.H:233`) se lee en `.C:641`
(`if (profileData_.staticStallAngleRad() != alphaSS_)`) antes de que
`evalStaticData` la asigne (`.C:105,109`). El ctor (`.C:499-553`) **no** la
inicializa (el init list termina en `Re_(0.0)`). Es una **lectura no
inicializada (UB)** en el primer `correct()`; en la práctica casi siempre
difiere del ángulo de stall y dispara `evalStaticData`, pero la corrección del
primer paso descansa en eso. Mismo patrón para otros miembros que sólo asigna
`evalStaticData`.

### H10. Inventory de código muerto (trampas de refactor)

Sin llamadores en el repo:

- `profileData::New` (`profileData.C:559`), `addedMassModel::New` (`:71`).
- `interpolateUtils::linearSearch`, el `interpolate1D` de 4 args, y **los tres
  `interpolate2D`**.
- `profileData::convertToCL`/`convertToCD`, `normalCoefficient()`,
  `chordwiseCoefficientList()`, `correctRe()`.
- Elemento: `rhoRef_` (`.H:118`), `freeStreamDirection_` (`.H:111`, asignada en
  `.C:97`, nunca leída).
- `LeishmanBeddoes::Re_` (`.C:553`), `dynamicStallModel::correct(alpha,cl,cd)`
  vacío, `reduceParallel` (H7).

**Policy:** el refactor **no** borra ni arregla esto en las fases
behavior-preserving. Cada item es un work unit propio (borrar o cablear) con su
decisión de comportamiento. Este inventario es la lista de candidatos.

## Fuera de alcance

- Implementar FSI para ALM o ASM-sin-malla.
- Cambiar la ley de movimiento (rotación rígida prescrita + `u` elástico).
- Cambiar los nombres de config o el contrato con `precice-openfoam-adapter`.
- Reescribir los archivos heredados del fork vendoreado más allá de lo que cada
  fase exige.
