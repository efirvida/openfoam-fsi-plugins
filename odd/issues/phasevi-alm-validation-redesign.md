# Issue: rediseñar la validación del ALM en NREL Phase VI con la configuración validada

- **Estado:** abierto — listo para ejecutar en una sesión nueva
- **Alcance:** **sólo ALM** (sin ASM ni asm-mesh)
- **Creado:** 2026-10-07
- **Paquete:** `turbinesFoam/validation/phaseVI/`
- **Relacionado:** `odd/tasks/iea15mw-references.md` (la configuración validada del IEA),
  `odd/tasks/phasevi-tip-correction-dagsorensen.md`, `odd/tasks/phasevi-endeffect-diagnostic.md`,
  `CAMPAIGN.md` (la campaña de augmentación rotacional, sólo preparada)

## Por qué

El ALM del IEA 15 MW quedó **validado** (cp 0,5366 contra una estela libre de 0,5312, +1,0 %)
con una configuración que costó cinco hipótesis medir. Phase VI es el complemento natural
porque **tiene datos de túnel de viento**: validar ahí el mismo método con la misma
configuración daría **dos validaciones independientes** — una contra códigos, otra contra
medición.

Y hay algo más fuerte: **los dos bugs que encontramos afectan a Phase VI exactamente igual**,
y pueden invalidar la conclusión de la campaña anterior.

## La configuración a aplicar (el patrón validado)

| componente | valor | por qué |
| --- | --- | --- |
| polares | **`liftReCorrExp 0`** | los polares de Phase VI declaran `Re` (`data/polars/S809_*.dat`), así que `profileData::updateRe` les aplica el mismo reescalado `cl_new(a) = K*cl_org(a/K)` que **corre el ángulo de sustentación nula** 1,65° e infla el `cl` **+12,5 %**. Es el bug del issue #6, no una preferencia |
| muestreo | **`velocitySampleRadius 3.3`, `nVelocitySamples 16`** | el mecanismo confirmado en el IEA (Δα +1,27 → +0,45°). El generador de Phase VI **no expone estas claves** — hay que espejarlas |
| pérdida de punta | **`endEffects on`** (Glauert, `tipEffects on` + `rootEffects on`) | el ganador medido en el IEA (cp 0,5801 → 0,5366) |
| augmentación rotacional | **off** | la física neutra, que es como se validó el IEA |
| modelo | **`--model alm`** | el alcance pedido |

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
integrar cuánto vale en potencia. Eso decide si la Etapa 4 existe.

## Las etapas

| etapa | costo | qué |
| --- | --- | --- |
| **1. Cuantificar** | 0 corridas | la línea `Re`, `K` por estación, el corrimiento de α₀ y su efecto en potencia |
| **2. Habilitar** | código | espejar `--velocity-sample-radius` / `--n-velocity-samples` (y `--mesh-factor` si se usa) en el generador de Phase VI, con default byte-idéntico; aplicar `liftReCorrExp 0` a sus polares |
| **3. Validar** | 1 corrida | ALM con la configuración completa, secuencia H a 7 m/s, contra `data/experiment/sequence_H_performance.csv` y `sequence_H_spanwise.csv` |
| **4. Re-testear la augmentación** | 2-4 corridas | **sólo si la Etapa 3 deja un residuo que la justifique** (banda ±15 %) |

## Criterios de aceptación

- **Potencia**: dentro del **±15 %** del experimento a 7 m/s (el criterio que la campaña ya usaba),
  y si es posible dentro del ±10 %.
- **Empuje**: reportado, sin criterio duro (el de 7 m/s es el punto de referencia).
- **Spanwise**: `c_n` en las 5 estaciones instrumentadas del experimento (25/35/60/82/92 % de
  envergadura) contra `sequence_H_spanwise.csv`.
- **Convergencia**: tabla por revolución y drift < 0,2 %/rev sostenido 5 rev (el protocolo de
  `odd/tasks/iea15mw-asm-mesh-convergence.md` — sirve igual).

## Insumos que ya están

- **Librería al día**: `libturbinesFoam.so` recompilada el 2026-10-07 14:02 con todo el árbol
  actual (incluye el fix de `writeNodeCsv`). No hace falta recompilar salvo que se toque C++.
- **Datos experimentales**: `data/experiment/sequence_{H,S}_{performance,spanwise}.csv` con
  `PROVENANCE.md`.
- **Polares**: `data/polars/` + `data/polars/raw/` con procedencia documentada (y la advertencia
  de que el scaffold `S809_Re1M_extended` no se usa: tiene `Cm` invertidos).
- **El generador**: `tools/generate_case.py` con `--rotational-augmentation`, `--root-effects`,
  `--tip-effects`, `--tip-correction`, `--polar`, `--mesh`, `--speed`, `--sequence`, `--profile`,
  `--n-elements`, `--n-chordwise`, `--surface-kernel`.
- **Las armas viejas**: `runs/alm-U{10,13}-coarse-aug-*` y `-tipcorr-*` — sirven de **control
  histórico** para comparar antes/después del fix, no para re-analizar.

## Lo que NO hay que hacer

- **No correr la matriz de augmentación** (la Etapa 4) antes de la Etapa 1: si el bug de polares
  explica el exceso, esa matriz mide un fantasma.
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
