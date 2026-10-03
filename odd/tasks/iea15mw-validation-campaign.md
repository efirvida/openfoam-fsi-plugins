# Feature: IEA 15 MW — campaña mínima de validación contra la referencia

- **Status:** design (esperando el go del mantenedor para lanzar)
- **Branch:** `feat/dagsorensen-tip-correction`
- **Created:** 2026-10-03
- **Package:** `turbinesFoam/validation/iea15mw/`
- **Relacionado:** `odd/tasks/iea15mw-asm-cases.md` (Etapa D, la comparación de
  modelos), `odd/tasks/iea15mw-olaf-reference.md`,
  `odd/tasks/phasevi-tip-correction-dagsorensen.md`,
  `odd/tasks/phasevi-endeffect-diagnostic.md`

## Objetivo

Cerrar la **validación** del punto nominal (V = 10,659 m/s, Ω = 7,518 rpm,
pitch colectivo 0) contra la banda de referencia, con el **mínimo** de
simulaciones, dejando la misma configuración lista para comparar ALM vs ASM vs
ASM-mesh (las correcciones viven en la cadena de carga compartida, así que una
sola configuración sirve para los tres modelos — ver `actuatorSurfaceElement.H`).

## Punto de partida (medido, no supuesto)

Baseline neutro = lo que está corriendo ahora: `dynamicStall off`,
`rotationalAugmentation off`, `endEffects off`, `tipCorrection` ausente
(default de C++). Medido en la corrida `11606597` (malla de 11.612.692 celdas):

```text
rev:      0        1        2        3        4        5        6
cp:    1,0400   0,8814   0,8189   0,7849   0,7625   0,7466   0,7367
Δcp:      -     -0,1586  -0,0625  -0,0340  -0,0224  -0,0159  -0,0099
```

Ratio de decaimiento ≈ 0,65 → la cola desde la rev 6 suma ≈ 0,028 →
**asíntota ≈ 0,709**.

| referencia | Cp | Ct | procedencia |
| --- | --- | --- | --- |
| WISDEM / tabla publicada | 0,4618 | 0,7718 | `iea15mw-olaf-reference.md:45-47` |
| OpenFAST BEM (15 rev) | 0,4820 | 0,8030 | `iea15mw-olaf-reference.md:43` |
| OLAF free wake (15 rev, convergido) | 0,5312 | 0,8288 | `iea15mw-olaf-reference.md:41` |
| **turbinesFoam ALM independiente** (Miroux, TU Delft 2024, V = 10,59 m/s, TSR 9, Ω 7,581 rpm, con torre + VolturnUS-S) | **0,527** | **0,804** | `turbinesFoam/articles/Msc_thesis_Mathis_Miroux_final_draft.pdf` Tabla 4.5 (p. 77) |
| OpenFAST en ese mismo paper (V = 10,59 m/s) | 0,491 | 0,806 | ídem Tabla 4.5 |

**El dato que más importa de esa tabla**: la fila de Miroux es **otra corrida del
mismo código (turbinesFoam ALM) sobre el mismo rotor**, en un punto equivalente
al nuestro (ΔTSR 1 %), y da **cp = 0,527 / ct = 0,804 / empuje 2,50 MN**.
Nuestro baseline da **cp ≈ 0,71 / ct ≈ 0,985 / empuje ≈ 3,15 MN**: **+39 % en
cp y +23 % en empuje contra una corrida independiente del mismo solver**. O sea,
no es "el método sobrepredice", es un desvío nuestro que hay que explicar.

Gap del baseline: **+34 % a +54 %**. La banda de referencia es ancha (0,462 →
0,531, 15 %), así que el criterio de aceptación tiene que ser explícito.

## Evidencia de la calibración previa (Phase VI, 7 m/s)

Lo medido en la campaña Phase VI, contra el experimento:

| configuración | potencia vs experimento |
| --- | --- |
| sin pérdida de punta, sin augmentación (C′) | **+14,3 %** |
| sin pérdida de punta, Du-Selig on (A′) | **+19,5 %** (+5,2 pts de la augmentación) |
| **Glauert `endEffects on`** | **−7,19 %** |
| **Dag & Sorensen `tipCorrection on`** (pérdida de punta off) | **+9,64 %** (OSU) / +8,76 % (CSU) |

Fuentes: `phasevi-endeffect-diagnostic.md:142,154`;
`phasevi-tip-correction-dagsorensen.md` tarea 7 (el veredicto).

Cuatro lecciones que ordenan el plan:

1. **La pérdida de punta es la palanca dominante**: el swing entre A′ (off) y
   Glauert (on) es de **26,6 puntos** de potencia.
2. **El D&S implementado cierra ~10 de los 19,5 pts**, pero no alcanza, y el
   Glauert queda **más cerca en error absoluto**. No es un silver bullet: es una
   abscisa más.
3. **Queda un residuo de ~14 % que no es pérdida de punta ni augmentación**
   (arm C′). Eso hay que **diagnosticarlo con los datos que ya tenemos**, no
   adivinarlo con corridas.
4. **Defecto de formulación conocido (H3a)**: `endEffectFactor_` multiplica
   **sólo el lift** (`actuatorLineElement.C:1036`), mientras Shen 2005 (Eqs.
   23-24) y Yang 2017 (Eqs. 13-14) escalan **lift y drag**. Es un candidato a
   corrección de **código**, no de configuración, y explica parte del −7,19 %
   de Glauert.

## Evidencia nueva (2026-10-03): los artículos + chequeo spanwise propio

### Los cuatro artículos nuevos (`turbinesFoam/articles/`)

| artículo | qué es | aporte al plan |
| --- | --- | --- |
| **Miroux, TU Delft MSc 2024** | turbinesFoam **ALM** + torre + VolturnUS-S, V = 10,59 y 8 m/s | **la referencia más valiosa**: mismo código, mismo rotor, nuestro punto. Tabla 4.5 (números), Fig 4.5 (empuje y fuerza tangencial por unidad de longitud, ALM vs BEM), Fig 4.6a (α por estación: su ALM ~9,5° a mitad de pala vs ~8° del BEM) |
| **Yi et al., Applied Ocean Research 2026** | blade-resolved URANS (STAR-CCM+, 2,4·10⁷ celdas), V = 8 y 9 m/s | **referencia spanwise de CFD resuelto**: Fig 13 da Fn [kN/m] y Q [kNm/m] por r/R. Su veredicto: el BEMT **sobrepredice** la carga contra su CFD, y sugiere que la formulación clásica de pérdida de punta puede no aplicar a palas tan esbeltas |
| **de Oliveira et al., OMAE2023-105084** | blade-resolved URANS, V = 10 m/s, 35,4 M celdas, estudio de Δt (CFL 1/2/4) | 10,28 MW y 1,91 MN a CFL = 1 (cp ≈ 0,37, **muy por debajo del BEM**); el paper se enfoca en la discretización temporal y reporta que su CFD **subestima** las fuerzas spanwise contra OpenFAST |
| **Bernardi et al., WES 11, 2345 (2026)** | LES + ALM con **FSI de dos vías**, V = 10 m/s, TSR 9 | el camino FSI del mantenedor; historias de Cp/Ct y una caída de ~10 % de Cp cuando la pala pasa frente a la torre |

### Chequeo spanwise propio (0 simulaciones, ya hecho)

Con los 147 CSV por pala de la corrida `11606597` en vuelo se verificaron dos
cosas antes de gastar cola:

1. **Los coeficientes reportados NO tienen bug de agregación.** Integrando las
   fuerzas por elemento (`f_ref_n`, `f_ref_t`) sobre 147 elementos × 3 palas:
   ct implícito = **1,00** y cp implícito = **0,728**, contra los reportados
   0,985 y 0,737. Coinciden. **La carga realmente es alta.**
2. **El exceso está en la fuerza TANGENCIAL, no en la normal.** En r/R = 0,5:
   nuestro empuje por unidad de longitud ≈ 9.650 N/m (comparable a los
   ~10.000 N/m de la Fig 4.5a de Miroux), pero nuestra fuerza tangencial
   ≈ 1.596 N/m contra ~1.150 N/m de ellos → **+39 %**, exactamente el exceso de
   cp. El cociente `c_t/c_n` es **0,165 contra 0,105-0,115**: el sospechoso es el
   ángulo de incidencia local φ, no la punta.

Perfil medido de `c_t/c_n` (baja con el radio, como manda tan φ ∝ 1/r: la forma
es sana, lo que está corrido es el nivel):

```text
r/R      0,17   0,37   0,50   0,78   0,99
c_t/c_n  0,43   0,23   0,165  0,131  0,092
```

**Consecuencia sobre el orden de las fases**: el exceso es **ancho, no
localizado en la punta**, así que empezar por la ablación de pérdida de punta
sería atacar el síntoma equivocado. La Fase A deja de ser un diagnóstico
opcional y pasa a ser **puerta obligatoria**, y ahora tiene referencias spanwise
externas (Miroux Fig 4.5, Yi Fig 13) además de CCBlade.

## Diseño: 4 fases, 2 simulaciones obligatorias

### Fase A — diagnóstico spanwise (0 simulaciones, 0 h de cola)

Los datos ya existen: las corridas en vuelo escriben **147 CSV por pala**, uno
por elemento, con

```text
time, root_dist, x, y, z, rel_vel_mag, Re, alpha_deg, alpha_geom_deg,
cl, cd, fx, fy, fz, end_effect_factor, c_ref_t, c_ref_n, f_ref_t, f_ref_n
```

(`runs/iea15mw-asmcmp-alm/postProcessing/actuatorLineElements/0/turbine.blade1.elementN.csv`).

Referencia spanwise: **CCBlade / Aeroelast**
(`fem-shell/src/aeroelast/solvers/bem/engine.py::BEMSolver.distributedAeroLoads`),
offline y ya usada en la sesión previa. **OLAF no sirve para spanwise**: su
`OutList` sólo trae los integrados (`RtFldFxh/Yh/Zh`, `RtFldCp/Ct`,
`RtVAvgxh`) — no hay canales `AB1N*`/`B1N*`.

La pregunta que decide todo: graficar `c_ref_n(ALM) / Cn(CCBlade)` **y `c_ref_t(ALM) / Ct(CCBlade)` por estación**, junto con el α local, contra dos referencias spanwise que ya existen gratis:

- **CCBlade / Aeroelast** (`fem-shell/src/aeroelast/solvers/bem/engine.py::BEMSolver.distributedAeroLoads`), offline, ya usada en la sesión previa;
- **Miroux Fig 4.5** (ALM independiente vs BEM, empuje y fuerza tangencial por unidad de longitud a 10,59 m/s) y **Fig 4.6a** (α por estación) — leerlas con visión de la página 85-86 del PDF;
- y, para blade-resolved, **Yi Fig 13** (Fn y Q por r/R a 8 y 9 m/s).

Como el chequeo ya hecho muestra que el exceso es **tangencial y ancho**, el árbol de decisión es:

- si el **α local** está por encima del suyo en toda la envergadura → el sospechoso es la geometría (twist, `curveAngle`, `chordMount`) y se revisa contra el yaml **sin correr nada**;
- si el α coincide pero el `cl` es mayor → **los polares** (tabla de Re que elige `buildPolars.py`) — se compara contra la tabla AirfoilInfo;
- si α y `cl` coinciden pero `c_t/c_n` difiere → **φ** (el ángulo de incidencia): la velocidad inducida o la velocidad relativa, o sea la proyección/ε del ALM;
- sólo si el exceso crece **hacia la punta** entra la pérdida de punta (Fase B).

Insumos extra del mismo CSV, gratis: `Re` por estación (contra el Re de la tabla
de polares que eligió `buildPolars.py`), `alpha_deg` vs `alpha_geom_deg`, y
`end_effect_factor` (debe ser 1,0 con `endEffects off`).

**Costo: 0 h de cola.** Es el paso que evita quemar campañas a ciegas.

#### Fase A′ — spanwise de free wake (opcional, 1 corrida, 1 core, ~5 h en paralelo)

Si se quiere el spanwise contra **free wake** y no sólo contra BEM: relanzar
OLAF con los canales `AB1N*` en el `OutList` de
`reference/olaf-15rev/IEA-15-240-RWT-OLAF_rated_AeroDyn15.dat`. Mismo `TMax`,
mismo costo de pared (sólo agrega salida), 1 core, **no ocupa la cola de
producción**. Da el perfil de `Cn` por estación del modelo de vorticidad libre.

### Fase B — ablación de la pérdida de punta (2 corridas en paralelo, ALM)

> **Sólo entra si la Fase A muestra el exceso creciendo hacia la punta.** El
> chequeo spanwise ya hecho dice que el exceso es ancho (`c_t/c_n` alto en toda
> la envergadura), así que por defecto la Fase B va **después** del diagnóstico,
> no antes.

Misma malla (11.612.692 celdas), mismo dominio (3D / 7D / ±3D), mismo `deltaT`
(0,00937 s), mismo caso. Sólo cambia el bloque del modelo:

| arm | dict | por qué |
| --- | --- | --- |
| **B1** | `endEffects { active on; endEffectsModel Glauert; GlauertCoeffs { tipEffects on; rootEffects on; } }` | es la **misma familia** de pérdida de punta que usan BEM y el OpenFAST de referencia → comparación manzana con manzana |
| **B2** | `tipCorrection { active on; model DagSorensen; wakeTurns 2; wakeAzimuthalStep 2.0; epsilon <auto> }` con `endEffects off` | el modelo prescrito ataca la causa física (vorticidad ligada truncada) y es el que va al FSI; **no se combina** con `endEffects` (no está validada la suma) |

Horizonte: **12 rev**, no 20. Con el decaimiento medido (ratio 0,65) a la rev 12
ya estás a **0,002** de la asíntota, o sea la mitad del error que se quiere
resolver; 12 rev en vez de 20 es **−40 % de pared** (~11,5 h vs ~19 h por
corrida). Criterio de corte documentado: deriva < 0,002/rev en las últimas 3
rev.

Decisión: gana el que minimice `|Δcp|` contra la banda **y** no empeore el perfil
spanwise de punta (el Glauert de este repo tiene el defecto H3a, así que puede
"acertar" el integral por la razón equivocada — hay que mirar el spanwise, no
sólo el número).

### Fase C — el residuo (condicional, 0-1 corridas)

Sólo lo que indique la Fase A:

| si el diagnóstico dice | sospechoso | ¿corrida? |
| --- | --- | --- |
| α uniformemente alto | twist / pitch / `chordMount` | **no**: se revisa contra el yaml antes de correr |
| `cl(α)` alto a igual α | los polares y su Re (`buildPolars.py`) | 1 corrida sólo si hay que cambiar de tabla |
| déficit **inboard** | `rotationalAugmentation` (Du-Selig o Lindenburg) | 1 corrida |
| punta alta **con** Glauert activo | defecto H3a (`endFactor` sólo al lift) | **no**: es un fix de código (multiplicar `Cn` y `Ct`), y recién ahí una corrida de confirmación |

### Fase D — comparación de modelos en la configuración ganadora (3 corridas, opcional)

Es lo que da **validación + comparación con el mismo juego de knobs**: ALM, ASM
y ASM-mesh con la pérdida de punta ganadora, misma malla y mismo dominio. Sin
esto se tiene la validación del ALM y la comparación de modelos por separado
(que es lo que corre hoy), pero no ambas cosas a la vez.

## Criterio de aceptación (a confirmar antes de lanzar)

- `cp ∈ [0,45 ; 0,51]` → `|Δ| ≤ 5%` contra el BEM 0,4835, y dentro de la banda
  WISDEM↔OLAF `[0,462 ; 0,531]`.
- `ct ∈ [0,79 ± 0,04]`.
- Spanwise: `|Δ c_ref_n| ≤ 10 %` **y `|Δ c_ref_t| ≤ 10 %`** contra CCBlade y
  contra la Fig 4.5 de Miroux para `r/R ≥ 0,3`, **y sin el exceso del último
  10 %** (que es el síntoma de la pérdida de punta).
- Deriva < 0,002/rev de `cp` en las últimas 3 revoluciones.

## Descartado a propósito (y por qué, para no gastar)

- **`dynamicStall`**: el punto nominal es estacionario; no mueve el `cp` medio.
  Una corrida ahorrada.
- **`rotationalAugmentation`**: medido en Phase VI, **sube** la potencia (+5,2
  pts). Dirección contraria al gap. Sólo entra si la Fase A muestra un déficit
  inboard.
- **Hub / nacelle**: la referencia AeroDyn no los tiene (ya decidido en
  `iea15mw-asm-cases.md`); agregarlos compara problemas distintos.
- **Malla más fina**: la convergencia de malla es el eje P5, no éste; la malla
  actual ya está validada por conteo analítico y `checkMesh`.
- **20 rev en todo**: 12 rev alcanza para el criterio, −40 % de pared.
- **Los tres modelos en cada fase**: la configuración se decide con el ALM (más
  barato y más confiable en las integrales) y recién después se replica.

## Dependencias de código

1. **`tools/generate_case.py`: los knobs son inalcanzables hoy.** El generador
   escribe `active off` fijo para `dynamicStall`, `rotationalAugmentation` y
   `endEffects`, y **no escribe** `tipCorrection` (queda en el default de C++,
   apagado). Hay que exponerlos con flags cuyo default reproduzca el render
   actual **byte por byte** (para no romper `--check` ni el caso commiteado).
   No requiere cola: se puede hacer ya.
2. **`scripts/run_iea15mw_case.sh`**: reenviar los nuevos env vars al generador.
   **No se puede editar mientras haya jobs corriendo** (bash relee el script por
   offset: ya costó 4 h y un exit 127). Se hace cuando cierren los tres, o
   inmediatamente antes de lanzar si el mantenedor corta la campaña actual.
3. **Un slurm para la validación** (hermano de `asmcmp.slurm`): misma malla y
   dominio, un modelo por job, 112 ranks, `--no-requeue`.

## Costos

| fase | corridas | pared por corrida | cola |
| --- | --- | --- | --- |
| A diagnóstico spanwise | 0 | — | 0 |
| A′ OLAF con spanwise | 1 (1 core) | ~5 h | no usa producción |
| **B ablación de punta** | **2 en paralelo** | **~11,5 h** (12 rev) | 2 × 112 ranks |
| C residual | 0-1 | ~11,5 h | condicional |
| D comparación de modelos | 3 en paralelo | ~11,5 h | opcional |

**Mínimo para tener validación del ALM: 2 simulaciones (~12 h de pared).**
Mínimo para validación + comparación de los tres modelos: 5.

## Fase A — VEREDICTO (2026-10-03)

Corrido CCBlade (Aeroelast `BEMSolver`) en **nuestro punto exacto**: V = 10.659,
rpm = 7.518, pitch 0, `precone=4`, `shear_exp=0` (sin shear, para igualar nuestra
entrada uniforme), sobre el yaml WindIO. Receta:

```text
cd /scratch/leahk/eduardo.donestevez/fem-shell
LD_LIBRARY_PATH=/scratch/app/gcc/14.2.0/lib64:$LD_LIBRARY_PATH PYTHONPATH=src \
  /scratch/leahk/eduardo.donestevez/venv/bin/python
# from aeroelast.models.blade.aerodynamics import load_blade_aero
# from aeroelast.solvers.bem.engine import BEMSolver
# BEMSolver(load_blade_aero(yaml, hub_radius=3.97, n_blades=3), rho=1.225,
#           precone=4.0, shear_exp=0.0).compute(10.659, 7.518, 0.0, 0.0)
```

**Resultado: CP = 0,4910 · CT = 0,7934 · empuje 2,532 MN · torque 21,2 MN·m**
— reproduce la referencia (Miroux/OpenFAST 0,491/0,806/2,55 MN) y nuestro propio
BEM de 15 rev. La receta del BEM queda validada.

### Spanwise nuestro vs BEM (misma estación, mismo yaml)

| r/R | α nuestro | α BEM | c_n nuestro | c_n BEM | ratio c_n | c_t nuestro | c_t BEM | **ratio c_t** |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0,168 | 15,28 | 14,57 | 1,789 | 1,598 | 1,12 | 0,772 | 0,666 | 1,16 |
| 0,333 | 8,41 | 7,59 | 1,698 | 1,406 | 1,21 | 0,399 | 0,307 | 1,30 |
| 0,498 | 8,03 | 6,82 | 1,558 | 1,210 | 1,29 | 0,264 | 0,172 | **1,54** |
| 0,663 | 7,82 | 6,49 | 1,486 | 1,174 | 1,27 | 0,197 | 0,124 | **1,60** |
| 0,801 | 7,83 | 7,21 | 1,472 | 1,217 | 1,21 | 0,146 | 0,104 | **1,41** |
| 0,913 | 6,97 | 6,79 | 1,361 | 1,168 | 1,17 | 0,109 | 0,088 | 1,24 |
| 0,960 | 7,21 | 6,09 | 1,378 | 1,085 | 1,27 | 0,124 | 0,074 | **1,67** |

### Lectura

1. **El α local nuestro es +1,0 a +1,4° mayor que el del BEM en toda la
   envergadura**, con el máximo en la mitad exterior. Ancho, no de punta.
2. **La causa es la inducción axial**: en r/R = 0,5 el BEM tiene
   **a = 0,305-0,33** y el nuestro, deducido de φ = α + θ y
   V_a = Ωr·tanφ, da **a ≈ 0,23 (−25 %)**. Menos inducción → el flujo llega más
   rápido al disco → mayor φ → mayor α → más carga.
3. **`c_t` amplifica el error de φ**: es un residuo de números grandes
   (c_t ≈ cl·senφ − cd·cosφ). Un +1,2° en φ mueve `tan φ` ~20 %, el `c_n` ~1 %
   y el **`c_t` +40-60 %**. Por eso el exceso de cp (+47 %) es mucho mayor que el
   de empuje (+23 %): el mismo error de ángulo pega distinto en cada integral.
4. **Segundo aporte independiente**: a igual α, nuestro `cl` va **~15 % arriba**
   del del BEM (r/R = 0,498: 1,558 a 8,03° contra 1,210 a 6,82°; sobre la curva
del polar propio, 7,89° da 1,533). Hay que resolver el mapeo de polares y el
   `Re = 3e6` de todas las tablas antes de cerrar el balance.

### Ramas CERRADAS (con evidencia)

- **Agregación / reporte**: los coeficientes reportados coinciden con la
  integral de las fuerzas por elemento (`11606597`: CT 0,9842 vs 0,9783;
  CP 0,7224 vs 0,7245). Sin bug.
- **Polares (lookup)**: el `cl` de cada elemento coincide con el polar
  AirfoilInfo asignado dentro del **0,5 %** (elementos 95/116/140). El camino de
  búsqueda está bien.
- **Geometría**: el `twist` commiteado coincide exactamente con la fuente
  AeroDyn (`+1,828°` en r/R = 0,51) y el `pitch` del `elementData` es
  `−BlTwist`, que es justo lo que AeroDyn usa en
  `EulerConstruct((0, BlCrvAng, −BlTwist))`. El θ implícito del propio flujo
  (φ − α = 1,89°) coincide con el aplicado (1,83°).

### Ramas ABIERTAS (siguen siendo 0 simulaciones)

1. **Por qué la inducción es baja**: ε del ALM vs malla, 147 elementos, tamaño
   de dominio (3D aguas arriba), resolución de la estela. Test barato: comparar
   α en la primera revolución (sin estela desarrollada) contra la convergida; y
   el valor de ε efectivo por elemento.
2. **Mapeo y Re de los polares**: verificar qué `polar_XX` recibe cada estación
   y compararlo con el archivo AeroDyn de esa estación; y cuantificar el efecto
   del `Re = 3e6` nominal en todas las tablas.
3. **Discrepancia de `cd`**: nuestro `cd` es ~la mitad del del polar a igual α
   (0,0081 contra 0,0161 en r/R = 0,80). Menor, pero hay que explicarlo.

**Consecuencia**: la campaña de simulación sigue esperando. El próximo paso es
diagnóstico, no cola — y ahora se sabe exactamente qué mirar.

### Cierre de la Fase A (2026-10-03, tarde)

Las tres ramas abiertas quedaron resueltas y apareció la corrección:

| rama | veredicto |
| --- | --- |
| Polares (`buildPolars.py`) | **fieles**: los 50 `polar_XX.dat` son extracción exacta del AeroDyn fuente, error 0 |
| Mapeo elemento→polar | **correcto**: `elementProfiles_[e*50/147]` (actuatorLineSource.C:251) |
| `cd` la mitad del polar | **explicado**: es la corrección de drag de `profileData::updateRe` (`K = f(ReRef)/f(Re)` ≈ 1,30) |
| α efectivo +1,5 a +1,8° sobre el `alpha_deg` | **no es un bug de etiqueta**: el CSV imprime el α realmente usado (`angleOfAttack_`, `actuatorLineElement.C:817`); la brecha sale de `cl_new(α) = K·cl_org(α/K)` con K = 1,43 |

**La corrección aplicada** (commit `a368b9e`): `liftReCorrExp 0;` en los 50
polares. La mitad de sustentación de `updateRe` no cambiaba la pendiente sino
que **corría el ángulo de sustentación nula** `(K−1)·|α₀| = 0,43 × 3,84 =
1,65°`, lo que infla el `cl` **+12,5 %** en el punto nominal. El ángulo de
sustentación nula es geométrico y no depende del Re: la corrección era
inconsistente. La mitad de arrastre (que sí es correcta) queda intacta.

**Lo que queda después de la corrección**: el α local sigue ~+1,0° arriba del
BEM, y eso es **propiedad del método**, no de nuestra configuración — el ALM
independiente de Miroux muestra el mismo +1,5° contra su BEM. Ese sesgo (el ALM
subestima la inducción en el plano del rotor respecto del BEM) es el objeto de
la Fase siguiente, no de una corrección de datos.

**Herramientas agregadas**: `scripts/compare_spanwise.py` (perfil spanwise +
chequeo de cierre) y `scripts/plot_spanwise_diagnosis.py` (figura de 5 paneles,
salida en `runs/spanwise-diagnosis.png`).


## Riesgos

- El D&S necesita Γ suavizada (`epsilon`): sin eso el término de punto cercano
  diverge (`axialFlowTurbineALSource.C:339-345`). El costo por paso también
  sube (2 rev × 2° = 360 segmentos de estela por pala).
- Glauert y D&S juntos no están validados: la ablación los corre por separado.
- Si **ningún** knob cierra el gap, el sospechoso es el camino de carga
  compartido (α / polares / ε) y no el modelo de punta: la Fase A es la que lo
  decide, y por eso va primero.
