# IEA 15-240-RWT — referencias y estado de la validación (registro vivo)

- **Creado:** 2026-10-03
- **Rama:** `feat/dagsorensen-tip-correction`
- **Packages:** `turbinesFoam/validation/iea15mw/`
- **Relacionado:** `odd/tasks/iea15mw-validation-campaign.md` (el plan y el
  veredicto de la Fase A), `odd/tasks/iea15mw-asm-cases.md` (la campaña de
  comparación de modelos), `odd/tasks/iea15mw-olaf-reference.md`

Este documento existe para no volver a leer los artículos: reúne **cada valor de
referencia** que usamos, con su método, su punto de operación, su procedencia
exacta y sus advertencias, más el estado medido de nuestras corridas y **cómo
reproducir todo**.

## 0. Nuestro punto nominal

`V = 10.659 m/s`, `Ω = 7.518 rpm` (TSR 8.913), `pitch = 0`, `precone = 4°`,
inflow uniforme, rotor + torre (sin hub ni nacelle), dominio 3D / 7D / ±3D,
malla castellada de **11.612.692 celdas**, `deltaT = 0.00937 s`.

## 1. Referencias integradas en el punto nominal (o equivalente)

| fuente | método | condición | Cp | Ct | empuje | torque | procedencia | advertencia |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| WISDEM / tabla publicada | BEM cuasi-estático | V = 10.659 | **0,4618** | 0,7718 | 2,457 MN | 19,91 MN·m | `iea15mw-olaf-reference.md:45-47` | cuasi-estático |
| OpenFAST BEM | BEM + pérdida de punta | V = 10.659 | **0,4820** | 0,8030 | 2,748 MN | 19,51 MN·m | `iea15mw-olaf-reference.md:43` | 15 rev, quasi-estático |
| **CCBlade nuestro (Aeroelast)** | BEM con los polares del yaml | V = 10.659, precone 4, shear 0 | **0,4910** | **0,7934** | **2,532 MN** | **21,2 MN·m** | reproducido 2026-10-03, ver §3 | idem |
| OLAF | estela libre (free vortex) | V = 10.659 | **0,5312** | 0,8288 | 2,868 MN | 22,26 MN·m | `iea15mw-olaf-reference.md:41` | **convergido** (15 rev) |
| **turbinesFoam ALM — Miroux (TU Delft 2024)** | **ALM, el mismo código** + torre + VolturnUS-S | V = 10.59, TSR 9, Ω 7.581 | **0,527** | **0,804** | **2,50 MN** | — | `articles/Msc_thesis_Mathis_Miroux_final_draft.pdf`, Tabla 4.5 (p. 77) | corrida independiente; flotante |
| OpenFAST en ese mismo paper | BEM | V = 10.59 | 0,491 | 0,806 | 2,55 MN | — | ídem | — |
| Yi et al. 2026 | blade-resolved URANS (STAR-CCM+, 2,4·10⁷) | V = 9 | ~0,45 | — | 1,637 MN | — | `articles/Aerodynamic modeling and wake characterization...pdf`, Tabla 4 | a 9 m/s, no nuestro punto |
| de Oliveira et al. OMAE2023 | blade-resolved URANS, 35,4 M celdas, y⁺ 60-350 | V = 10 | **≈0,37** | ≈0,68 | 1,91 MN | — | `articles/OMAE2023_105084...pdf`, Figs 5-6 (pp. 7-8) | subestima 15-25 % contra su propio OpenFAST |
| Bernardi et al. WES 2026 | LES + ALM **con FSI de dos vías** | V = 10, TSR 9 | — | — | — | — | `articles/wes-11-2345-2026.pdf` | cualitativo (historias de Cp/Ct) |

**Lectura**: la banda físicamente creíble es **0,46-0,53**. La **estela libre
(OLAF) y el ALM independiente de Miroux coinciden al 1 %** (0,5312 vs 0,527) y
ambos van ~8-10 % arriba del BEM: el nivel de carga del ALM está corroborado por
un método de vórtices, y el BEM es el que se aparta. Los blade-resolved acotan
**desde abajo** (0,37-0,45) pero subestiman contra su propio BEM, así que no son
árbitro absoluto.

## 2. Referencias spanwise (digitizadas, ±10 %)

Viven en `scripts/plot_3models_spanwise.py` como arrays con su procedencia, y en
`analysis/spanwise-references.csv`:

- **de Oliveira, Fig 6 (p. 8)** — `Radius [m]` 0-120, curvas `CFL=2` y
  `OpenFAST-AeroDyn v15`, V = 10 m/s. Pico de la normal ≈ **10,3 kN/m en
  r/R ≈ 0,82** (OpenFAST ≈ 11,2 kN/m en 0,84); tangencial en meseta
  ≈ **0,75 kN/m** (OpenFAST ≈ 0,96 kN/m). Su CFD baja 7-29 % de su OpenFAST.
- **Yi et al., Fig 13 (p. 11)** — `Fn` y `Q` vs `r/R`, V = 9 m/s, `Present`
  (URANS) vs `BEMT`. Pico de Fn ≈ 9,5 kN/m en r/R ≈ 0,9; Q ≈ 105 kNm/m en 0,8
  para el CFD, por encima del BEMT en la mitad exterior.

## 3. Cómo reproducir

### El BEM propio (CCBlade vía Aeroelast) — receta validada

```sh
cd /scratch/leahk/eduardo.donestevez/fem-shell
LD_LIBRARY_PATH=/scratch/app/gcc/14.2.0/lib64:$LD_LIBRARY_PATH PYTHONPATH=src \
  /scratch/leahk/eduardo.donestevez/venv/bin/python
```

```python
from aeroelast.models.blade.aerodynamics import load_blade_aero
from aeroelast.solvers.bem.engine import BEMSolver
ba = load_blade_aero("tests/IEA-15-240-RWT.yaml", hub_radius=3.97, n_blades=3)
r  = BEMSolver(ba, rho=1.225, precone=4.0, tilt=0.0, yaw=0.0,
               hub_height=150.0, shear_exp=0.0).compute(10.659, 7.518, 0.0, 0.0)
# -> CP 0.4910, CT 0.7934, empuje 2.5322e6 N, torque 2.1215e7 Nm (auto-chequeo)
# BEMResult: r, alpha, cl, cd, a, ap, cn, ct, Np, Tp, Re, CP, CT, CQ, ...
```

Dos trampas: el `LD_LIBRARY_PATH` del GCC 14.2 hay que **prefijarlo** (si se
reemplaza, `binascii` no encuentra `libpsm_infinipath.so.1`), y sin esa ruta
`aeroelast` falla con `CXXABI_1.3.15`. `shear_exp=0` es obligatorio para
comparar contra nuestra entrada uniforme (el default es 0,2).

### Las figuras

```sh
cd <repo>
PY=/scratch/leahk/eduardo.donestevez/venv/bin/python
$PY turbinesFoam/validation/iea15mw/scripts/compare_spanwise.py        # perfil + cierre
$PY turbinesFoam/validation/iea15mw/scripts/plot_spanwise_diagnosis.py # ALM vs BEM
$PY turbinesFoam/validation/iea15mw/scripts/plot_3models_spanwise.py   # 3 modelos + referencias
```

Salidas versionadas: `analysis/spanwise-diagnosis.png`,
`analysis/spanwise-3models.png`, `analysis/spanwise-references.png`. Los datos
para rehacerlas sin depender de los runs: `analysis/spanwise-profiles.csv` y
`analysis/spanwise-references.csv`.

### Los datos crudos

Los run dirs (`runs/`) están gitignored. Las campañas y sus jobs:

| run dir | job | modelo | estado |
| --- | --- | --- | --- |
| `runs/iea15mw-asmcmp-alm` | 11606597 | ALM | 20 rev |
| `runs/iea15mw-asmcmp-asm` | 11606598 | ASM (nChordwise 5) | 20 rev |
| `runs/iea15mw-asmcmp-asm-mesh` | 11606599 | ASM + malla importada | 20 rev |
| `runs/iea15mw-alm-corrpolars` | 11607032 | ALM, **polares corregidos** | 12 rev (verificación) |

CSV por elemento para los tres modelos:
`runs/<run>/postProcessing/actuatorLineElements/0/turbine.blade1.element{0..146}.csv`.
`root_dist` es **fracción de envergadura** en [0,1] (no metros):
`r = 3.97 + root_dist*117.0`, `R = 120.67532`, `dr = 117/147 = 0.7959 m`.
`f_ref_n`/`f_ref_t` son fuerzas **por unidad de envergadura y por unidad de
densidad** (`normalRefForce() = 0.5*chord*c*|Vrel|²`, sin `dr`; verificado por el
cierre de C_T): la fuerza física por unidad de longitud es **`f_ref × ρ`**.

## 4. Estado medido y correcciones aplicadas

- **Cierre de coeficientes**: integrar `f_ref_n`/`f_ref_t` sobre 147 elementos ×
  3 palas reproduce los cp/ct que reporta el módulo (0,3-0,6 %). **No hay bug de
  agregación.**
- **Exceso de carga**: cp 0,722 vs 0,491 del BEM; empuje ~3,15 MN vs 2,53 MN.
  Spanwise, contra CCBlade: **Δα medio +1,0°**, **exceso de c_t medio +44 %**,
  **inducción axial en la mitad de pala 0,2515 vs 0,3119**.
- **Diagnóstico de Fase A**: el exceso es **de nivel, no de forma** — el ALM y el
  ASM siguen la forma de las referencias blade-resolved con un cociente casi
  constante (c_n 1,25-1,35×; c_t 1,4-1,7×). La geometría (twist = fuente AeroDyn),
  el mapeo de polares y el `cd` (corrección de Re de `profileData::updateRe`) se
  verificaron sanos.
- **Corrección aplicada** (commit `a368b9e`): `liftReCorrExp 0;` en los 50
  polares. La mitad de sustentación de `updateRe` es `cl_new(α) = K·cl_org(α/K)`
  con K = (Re/ReRef)^0.23 = 1,43, que **no cambia la pendiente sino que corre el
  ángulo de sustentación nula** 1,65° e infla el `cl` +12,5 % en el punto
  nominal. El ángulo de sustentación nula es geométrico y no depende del Re.
  La mitad de arrastre queda activa.
- **Pendiente conocido pero NO nuestro**: el α local queda ~+1,0° sobre el BEM, y
  eso es una propiedad del método — el ALM independiente de Miroux muestra el
  mismo +1,5°. Es el objeto de la Fase 3 del plan.
- **Anomalía abierta del ASM-mesh**: su cp (+48 % sobre el ALM) y su exceso de
  c_t (2,1-3,1× contra la referencia) no son un múltiplo uniforme del ALM. La
  fuerza por nodo está verificada al 0,2 %, así que el sospechoso es el **brazo
  de momento**; sus cargas spanwise son comparables pero su cp/torque absolutos
  no se citan.

## 5. Advertencias transversales

1. **Los blade-resolved subestiman** (de Oliveira 15-25 % contra su OpenFAST) y
   son sensibles al paso de tiempo y a la discretización **en la raíz**
   (r/R < 0,5), que es justo donde las tres curvas nuestras más se separan. La
   raíz es zona sin árbitro.
2. **El BEM no es la verdad**: su inducción es empírica (Prandtl + correcciones
   de alta inducción). La estela libre es el árbitro más físico de los baratos.
3. **Ningún valor absoluto se cita** de las corridas con los polares viejos
   (`11606597/8/9`): sus cp conservan la inflación del `liftReCorrExp`. La
   comparación **entre** ellos sigue siendo válida porque comparten el sesgo.
4. Los valores digitizados de las figuras son **±10 %** por construcción.

## 6. Potencia y torque medidos

Medias de la última revolución completa de cada corrida en vuelo, calculadas
desde el `cp` que reporta el módulo (`postProcessing/turbines/0/turbine.csv`).
El torque no es una columna del CSV: se obtiene con
`T = cp · ½ρAV³ / Ω`, con `A = πR²`, `R = 120.675 m`, `ρ = 1.225`,
`V = 10.659 m/s`, `Ω = 0.78719 rad/s`
(`P_disponible = ½ρAV³ = 33.93 MW`).

| corrida | model | última rev completa | C_P medio | torque medido | estado |
| --- | --- | --- | --- | --- | --- |
| `iea15mw-asmcmp-alm` | ALM | 19-20 | **0.6927** | **29.86 MN·m** | 20 rev, completo |
| `iea15mw-asmcmp-asm` | ASM | 19-20 | **0.6266** | **27.01 MN·m** | 20 rev, completo |
| `iea15mw-asmcmp-asm-mesh` | ASM + malla | 12-13 | **1.0678** | **46.03 MN·m** | parcial/transitorio (corrida viva) |

El ALM y el ASM están terminados (20 rev) y sus medias no cambian. El
ASM-mesh **sigue corriendo**, así que su "última revolución completa" y su
media avanzan entre mediciones (con la corrida a ~13 rev dio 1.0678 /
46.03 MN·m; una medición previa a ~11.5 rev dio 1.0686 / 46.07 MN·m).

Referencias del §1 para comparar (mismo punto): WISDEM C_P 0.4618 /
19.91 MN·m, OpenFAST BEM 0.4820 / 19.51 MN·m, CCBlade propio 0.4910 /
21.2 MN·m, Miroux ALM 0.527 (sin torque publicado), OLAF 0.5312 / 22.26 MN·m.

**Advertencia honesta:** las tres corridas en vuelo usaron los polares
**ANTES** de la corrección `liftReCorrExp 0` del commit `a368b9e`, así que
sus niveles absolutos de C_P y torque arrastran esa inflación: el ALM y el ASM
quedan ~20-50 % por encima de la banda de referencias y el ASM-mesh casi al
doble, además de seguir en transitorio. Esos números **no** se citan como
valor absoluto. La comparación **entre** las tres corridas sí es válida porque
comparten ese mismo sesgo: el orden ALM > ASM se mantiene, y el ASM-mesh se
descarta por transitorio.

Figuras: `analysis/power-torque-vs-rev.png` (trazas crudas + media por
revolución, con las cinco referencias etiquetadas),
`analysis/power-torque-last-revs.png` (zoom a las últimas 5 revoluciones de
cada corrida) y `analysis/torque-ripple.png` (ripple: crudo a 3 rev, plegado
módulo 120° a 5 rev y las tres palas del ALM). Se regeneran con:

```sh
PY=/scratch/leahk/eduardo.donestevez/venv/bin/python
$PY turbinesFoam/validation/iea15mw/scripts/plot_power_torque.py
$PY turbinesFoam/validation/iea15mw/scripts/tower_azimuthal_signature.py
$PY turbinesFoam/validation/iea15mw/scripts/torque_ripple.py
```

### Ripple de torque medido

Medido con `scripts/torque_ripple.py` (solo lee `runs/`; el torque se calcula
con la fórmula de arriba, que da `cp × 43,108` y no 43,112: esa diferencia
del 0,009 % no cambia ninguna cifra significativa). En las
últimas 3 revoluciones completas el torque crudo del ALM tiene un
pico-a-pico de **1,021 MN·m (3,42 % de su media)** y el del ASM **0,609 MN·m
(2,26 %)**; el ASM-mesh, en transitorio, da 63,2 MN·m, que **no** es ripple
físico. Al plegar el torque módulo 120° (componente 3/rev de paso de pala,
últimas 5 revoluciones, bins de 1°) el pico-a-pico es **0,727 MN·m (2,43 %)**
para el ALM y **0,497 MN·m (1,84 %)** para el ASM; la amplitud de la armónica
3/rev es 0,290 MN·m (0,97 %) y 0,208 MN·m (0,77 %) respectivamente. La
componente 1/rev —la que delataría asimetría entre palas— queda en **0,072 %**
(ALM) y **0,059 %** (ASM), por debajo del 1 %: no hay asimetría de palas
apreciable a ese nivel. El `cp` pliega exactamente con la misma forma (los
factores de escala cancelan), lo que confirma que la oscilación no es un
escalón del post-proceso. En el ALM cada pala cae una vez por revolución
(≈−3,5 % de su media) y los tres mínimos están a 120,0/119,6/120,4°. El
ASM-mesh, en cambio, muestra una oscilación 1/rev enorme (de 13,8 a
76,9 MN·m) que es artefacto de la corrida viva, no ripple de paso de pala.
