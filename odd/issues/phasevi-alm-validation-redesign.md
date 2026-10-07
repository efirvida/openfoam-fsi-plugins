# Issue: rediseñar la validación del ALM en NREL Phase VI con la configuración validada

- **Estado:** abierto — listo para ejecutar en una sesión nueva
- **Alcance:** **sólo ALM** (sin ASM ni asm-mesh)
- **Creado:** 2026-10-07 · **Revisado:** 2026-10-07 (correcciones C1–C3 + reorientación a Sequence S)
- **Paquete:** `turbinesFoam/validation/phaseVI/`
- **Feature:** `odd/tasks/phasevi-sequence-s-validation.md`
- **Relacionado:** `odd/tasks/iea15mw-references.md` (la configuración validada del IEA),
  `odd/tasks/phasevi-tip-correction-dagsorensen.md`, `odd/tasks/phasevi-endeffect-diagnostic.md`,
  `CAMPAIGN.md` (la campaña de augmentación rotacional, sólo preparada)

## Correcciones de esta revisión

| # | Defecto | Corrección |
| --- | --- | --- |
| **C1** | Las estaciones spanwise de aceptación decían **25/35/60/82/92 %**. Esas son de MEXICO, no del Phase VI | Las instrumentadas reales son **30/47/63/80/95 %**. Coinciden tres fuentes: `data/experiment/PROVENANCE.md`, el README del paquete y las 22 descripciones por estación de `articles/uae6/channels.csv` |
| **C2** | La Etapa 3 validaba contra **secuencia H**, que no tiene respaldo crudo en el repo | La secuencia de validación pasa a ser **Sequence S**. H queda diferida hasta que aparezca su archivo crudo |
| **C3** | El archivo experimental real de Sequence S no estaba registrado en el issue | Se registra abajo, con la verificación que lo respalda |

### Por qué

El ALM del IEA 15 MW quedó **validado** (cp 0,5366 contra una estela libre de 0,5312, +1,0 %)
con una configuración que costó cinco hipótesis medir. Phase VI es el complemento natural
porque **tiene datos de túnel de viento**: validar ahí el mismo método con la misma
configuración daría **dos validaciones independientes** — una contra códigos, otra contra
medición.

Y hay algo más fuerte: **los dos bugs que encontramos afectan a Phase VI exactamente igual**,
y pueden invalidar la conclusión de la campaña anterior.

Y ahora hay algo mejor que en septiembre: **el archivo experimental real de Sequence S está
en el repo**, y su inventario cierra contra el propio reporte. La validación puede dejar de
apoyarse sólo en el workbook.

## El insumo nuevo — el archivo Sequence S real

`turbinesFoam/articles/uae6/` contiene la **campaña Sequence S completa** del Phase VI en
formato original (`<stem>.hd1` + `<stem>.eng`), más su conversión a Parquet (`parquet/`, 106
archivos), la tabla de canales (`channels.csv`, 285 filas) y el inventario (`manifest.csv`).

La definición de la campaña es `turbinesFoam/articles/29955.pdf` (NREL/TP-500-29955), sha256
`822ee980e97780599ad4ec1dc8b4cc8ad41131b0cbbdffa19999d571f6ce4958` — **el mismo**
`29955_nlr.pdf` que el openspec ya cita como fuente verificada. No es una copia nueva.

Sequence S (reporte, p. 31): upwind, turbina rígida, cono 0°, 5–25 m/s, yaw 0–180°, pitch de
punta 3°, 72 rpm, sondas de 5 agujeros desmontadas con los tapones instalados.

### Qué está verificado

| Chequeo | Resultado |
| --- | --- |
| Inventario local vs Tabla C-18 (p. 202 del texto / 212 del PDF) | **106 = 106**; coincide el desglose **104 archivos de 30 s + 2 de 6 min** |
| Los 2 archivos de 6 min | `s07ysu00` y `s10ysu00` (199 502 frames = 383 s): son los barridos de yaw a 1°/s que el reporte describe para 7 y 10 m/s |
| Convención de nombre `SWWYYYYR` (p. 212) | `s` + velocidad(2) + **yaw en grados(4)** + repetición(1). O sea `s0500050` = 5 m/s, yaw 5°, rep 0 |
| Ese decode contra el canal medido `YAW` | `0050`→5,05°; `0100`→10,02°; `0200`→20,02°; `0300`→29,95°; `0450`→44,98°; `0600`→59,98°; `0750`→75,04°; `0900`→90,04°; `1350`→135,06° |
| Crudo `s0700000` vs `data/experiment/sequence_S_performance.csv` | rpm 71,8667 / ROTPOW 6,0304 kW / LSSTQCOR 801,265 Nm / EAEROTH 1149,53 N — **idéntico** |
| Crudo `s0700000` vs `sequence_S_spanwise.csv` | cn/ct/cm de las 5 estaciones, **idénticos dígito a dígito** (0,8034/0,0961/−0,0274 …) |
| Cobertura a 0° yaw | **21 velocidades** (5…25 m/s): curva de potencia completa |
| Cobertura de yaw | juego completo (5/10/20/30/45/60/75/90/135/180°) a 5, 7, 10 y 15 m/s; 5°/10° en el resto |

Dos consecuencias:

1. El workbook WDH (`ldsmean`) queda **corroborado por los bytes crudos** para `s0700000`. No
   es una fuente en disputa: es una fuente confirmada. La comparación cruzada que la nota de
   método pedía ya se hizo y salió bien.
2. El paquete usa hoy **una sola fila S** (7 m/s) y 6 filas H, todas del workbook. El archivo
   crudo trae 21 velocidades a 0° yaw.

### Dos cosas que el archivo NO es

- **No está versionado.** `turbinesFoam/.gitignore` ignora `/articles/` entero: el README, el
  conversor, `channels.csv`, `manifest.csv`, los 2,15 GiB crudos, los 1,24 GiB de Parquet y
  el propio `29955.pdf` son *untracked*. Un clon limpio no tiene nada. Por eso la **S1** de la
  feature crea un registro de procedencia **dentro** del paquete de validación, que sí se
  versiona.
- **No trae Sequence H.** El archivo es `uae6.z18.00.s*` y nada más. H existe hoy sólo como
  fila del workbook, sin corroboración por bytes.

## La configuración a aplicar (el patrón validado)

| componente | valor | por qué |
| --- | --- | --- |
| polares | **`liftReCorrExp 0`** | los polares de Phase VI declaran `Re` (`data/polars/S809_*.dat`), así que `profileData::updateRe` les aplica el mismo reescalado `cl_new(a) = K*cl_org(a/K)` que **corre el ángulo de sustentación nula** 1,65° e infla el `cl` **+12,5 %**. Es el bug del issue #6, no una preferencia |
| muestreo | **`velocitySampleRadius 3.3`, `nVelocitySamples 16`** | el mecanismo confirmado en el IEA (Δα +1,27 → +0,45°). El generador de Phase VI **no expone estas claves** — hay que espejarlas. Las claves existen y las consume `axialFlowTurbineALSource` (`lookupOrDefault`, default 0.0 y 20) |
| pérdida de punta | **`endEffects on`** (Glauert, `tipEffects on` + `rootEffects on`) | el ganador medido en el IEA (cp 0,5801 → 0,5366) |
| augmentación rotacional | **off** | la física neutra, que es como se validó el IEA |
| modelo | **`--model alm`** | el alcance pedido |
| secuencia | **`--sequence S`** | la que tiene respaldo crudo |

## La hipótesis que hay que testear ANTES de correr nada (Etapa 1, 0 corridas)

Los números que la campaña de septiembre midió a 7 m/s, contra el experimento:

| configuración | potencia |
| --- | --- |
| sin pérdida de punta, sin augmentación | **+19,5 %** |
| sin pérdida de punta, Du-Selig on | +19,5 % (la augmentación aporta 5,2 pts) |
| Glauert `endEffects on` | **−7,19 %** |
| Dag & Sørensen `tipCorrection on` (punta off) | +9,64 % |

La lectura de entonces fue que faltaba augmentación rotacional. **La lectura nueva: el +19,5 %
puede ser en buena parte los dos bugs.** Si el `cl` está +12,5 % por el bug de polares y el
muestreo aporta otro tanto, el exceso queda explicado y **la augmentación pasa de candidata a
innecesaria** — lo que ahorra la campaña entera de la matriz aug-on/off.

**Etapa 1, concreta y sin cola**: mirar la línea `Re` de cada polar commiteado de Phase VI,
calcular `K = (Re/ReRef)^0.23` para el Re local de cada estación y el corrimiento de α₀, e
integrar cuánto vale en potencia. Eso decide si la Etapa 5 existe.

## Las etapas

| etapa | costo | qué |
| --- | --- | --- |
| **1. Cuantificar** | 0 corridas | la línea `Re`, `K` por estación, el corrimiento de α₀ y su efecto en potencia |
| **2. Habilitar** | código | espejar `--velocity-sample-radius` / `--n-velocity-samples` (y `--mesh-factor` si se usa) en el generador de Phase VI, con default byte-idéntico; aplicar `liftReCorrExp 0` a sus polares |
| **3. Referencia** | datos | derivar del **crudo** la curva a 0° yaw (21 velocidades) y las estaciones spanwise, con el `err` byte enmascarado, y extender `data/experiment/` con PROVENANCE |
| **4. Validar** | 1 corrida | ALM con la configuración completa, **Sequence S a 7 m/s**, contra la referencia de la Etapa 3 |
| **5. Re-testear la augmentación** | 2-4 corridas | **sólo si la Etapa 4 deja un residuo que la justifique** (banda ±15 %) |

## Criterios de aceptación

- **Potencia**: dentro del **±15 %** del experimento de Sequence S a 7 m/s (el criterio que la
  campaña ya usaba), y si es posible dentro del ±10 %.
- **Empuje**: reportado, sin criterio duro (el de 7 m/s es el punto de referencia).
- **Spanwise**: `c_n` en las **5 estaciones instrumentadas** del experimento —**30/47/63/80/95 %
  de envergadura**— contra la referencia de Sequence S. *(Corregido: eran 25/35/60/82/92 %)*
- **Convergencia**: tabla por revolución y drift < 0,2 %/rev sostenido 5 rev (el protocolo de
  `odd/tasks/iea15mw-asm-mesh-convergence.md` — sirve igual).

## Insumos que ya están

- **Librería al día**: `libturbinesFoam.so` recompilada el 2026-10-07 14:02 con todo el árbol
  actual (incluye el fix de `writeNodeCsv`). No hace falta recompilar salvo que se toque C++.
- **Datos experimentales**: `data/experiment/sequence_{H,S}_{performance,spanwise}.csv` con
  `PROVENANCE.md` (workbook WDH). Para Sequence S quedan **corroborados por el crudo**; para H
  son la única fuente.
- **El archivo crudo Sequence S**: `articles/uae6/` — 106 puntos, 285 canales, 30 s a 520,83 Hz
  (más los dos sweeps de 6 min), Parquet listo para pandas/polars. Trae ya derivados `CN/CT/CM`
  y `QNORM` en las cinco estaciones, `B3AZI` (azimut) y el byte `err` por frame.
- **Polares**: `data/polars/` + `data/polars/raw/` con procedencia documentada (y la advertencia
  de que el scaffold `S809_Re1M_extended` no se usa: tiene `Cm` invertidos).
- **El generador**: `tools/generate_case.py` con `--rotational-augmentation`, `--root-effects`,
  `--tip-effects`, `--tip-correction`, `--polar`, `--mesh`, `--speed`, `--sequence`, `--profile`,
  `--n-elements`, `--n-chordwise`, `--surface-kernel`.
- **Las armas viejas**: `runs/alm-U{10,13}-coarse-aug-*` y `-tipcorr-*` — sirven de **control
  histórico** para comparar antes/después del fix, no para re-analizar.

## Lo que NO hay que hacer

- **No correr la matriz de augmentación** (la Etapa 5) antes de la Etapa 1: si el bug de polares
  explica el exceso, esa matriz mide un fantasma.
- **No validar contra Sequence H** hasta que el archivo crudo H esté en el repo: hoy H sólo
  existe como fila del workbook, sin corroboración por bytes.
- **No citar el archivo de `articles/uae6/` como versionado**: está gitignored. Si algo tiene
  que sobrevivir a un clon limpio, va al paquete, no a `articles/`.
- **No tocar el ASM/asm-mesh** en esta campaña: el alcance es ALM.
- **No citar una potencia de Phase VI** sin el fix de polares: el `cl` está +12,5 %.
- **No reemplazar el scaffold de polares** por `S809_Re1M_extended` (tiene `Cm` invertidos).
- No comparar contra el IEA: la validación de Phase VI es **contra el experimento**.

## Nota de método

Todo lo que se aprendió en el IEA aplica: escribir los criterios antes de correr, dejar la
tabla por revolución como evidencia, y **desconfiar de cualquier número reportado sin medirlo
dos veces** — en esa campaña cada cifra que reporté sin verificar resultó un artefacto mío
(una revolución parcial, una normalización, un frame distinto), y los tres quedaron
documentados.

Esta revisión es el mismo ejercicio aplicado a los insumos: el inventario se cruzó contra la
Tabla C-18 del reporte, el decode de yaw contra el canal medido `YAW`, y el crudo contra los
CSV ya commiteados. Las tres cruzaron. Y el ejercicio encontró dos defectos reales en este
documento (C1 y C2) que habrían costado corridas.
