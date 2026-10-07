# Feature: phasevi-sequence-s-validation

Rediseñar y ejecutar la validación del ALM de NREL Phase VI contra la **campaña
Sequence S** real, aprovechando el archivo crudo completo que ya vive en el repo.

- **Issue:** #8 `Phase VI: reorientar la validacion del ALM a la campana Sequence S`
  (`odd/issues/phasevi-alm-validation-redesign.md`)
- **Paquete:** `turbinesFoam/validation/phaseVI/`
- **Rama:** `feat/phasevi-sequence-s`
- **Definición experimental:** `turbinesFoam/articles/29955.pdf`
  (NREL/TP-500-29955), sha256
  `822ee980e97780599ad4ec1dc8b4cc8ad41131b0cbbdffa19999d571f6ce4958`
- **Insumo nuevo:** `turbinesFoam/articles/uae6/` — **522 puntos de ensayo en 8
  secuencias** (H, J, L, O, P, S, T, U) en crudo (`.hd1` + `.eng`) + Parquet,
  `channels.csv` (285 canales) y `manifest.csv`
- **Catálogo y selección:** `data/experiment/uae6-archive/CATALOG.md` — definición,
  inventario cruzado, gramática del nombre y evaluación de qué secuencia validar
- **Decisión del usuario (2026-10-07):** la secuencia de validación es
  **Sequence S** (7 m/s puntual y curva a 0° yaw), y pidió documentar el resto de
  lo descargado para poder evaluar cuál conviene. El archivo crudo ya trae las 8
  secuencias, **H incluida**, así que la recomendación del catálogo es **S como
  principal y H como confirmación independiente**: mismo rig, mismo pitch 3°,
  mismas 21 velocidades a 0° yaw — cambia sólo la referencia. El diseño queda
  **agnóstico de secuencia**.

## Por qué

El paquete valida hoy contra `data/experiment/*.csv`, derivado del workbook WDH
`wt_loads_statistics.xls` (medias de registros, 0° yaw, 5 estaciones): 6 filas H
+ **1 sola fila S**. El archivo crudo de Sequence S trae la medición completa.

Evidencia ya verificada (2026-10-07):

| Chequeo | Resultado |
| --- | --- |
| Inventario local vs Tabla C-18 (p. 202 / PDF 212) | **106 = 106**; coincide el desglose **104 × 30 s + 2 × 6 min** |
| `articles/29955.pdf` sha256 vs el `29955_nlr.pdf` del openspec | idéntico (`822ee980…ce4958`) |
| `s07ysu00` / `s10ysu00` = 199 502 frames (383 s) | los barridos de yaw a 1°/s que el reporte describe para 7 y 10 m/s |
| Convención `SWWYYYYR` (p. 212) vs canal medido `YAW` | `0050`→5,05°; `0100`→10,02°; `0200`→20,02°; `0300`→29,95°; `0450`→44,98°; `0600`→59,98°; `0750`→75,04°; `0900`→90,04°; `1350`→135,06° |
| Crudo `s0700000` vs `data/experiment/sequence_S_performance.csv` | rpm 71,8667 / 6,0304 kW / 801,265 Nm / 1149,53 N — **idéntico** |
| Crudo `s0700000` vs `sequence_S_spanwise.csv` | cn/ct/cm de las 5 estaciones, **idénticos dígito a dígito** |
| Cobertura 0° yaw | **21 velocidades** (5…25 m/s) |
| Cobertura de yaw | juego completo a 5, 7, 10 y 15 m/s; 5°/10° en el resto |

Dos consecuencias: (1) el workbook queda **corroborado** por los bytes crudos;
(2) el paquete usa hoy una sola fila S y el archivo trae 21 velocidades a 0°.

Dos defectos del issue que esta feature corrige: estaciones spanwise escritas
como 25/35/60/82/92 % (son de MEXICO; las reales son 30/47/63/80/95 %) y la
Etapa 3 apuntando a secuencia H sin respaldo crudo.

## Anclas verificadas en el código

Leídas directamente, no inferidas.

| Qué | Ancla |
| --- | --- |
| Bloque `axialFlowTurbineALSourceCoeffs` renderizado | `tools/generate_case.py:633` (dentro de `render_fv_options`, `:493`) |
| `Re 1e6;` y `GaussianCoeffs` viven en `…Coeffs.profileData.S809` | `generate_case.py:~703-711` |
| `meshFactor` sale de `turbine['gaussian_mesh_factor']` | `generate_case.py:708` |
| `velocitySampleRadius` / `nVelocitySamples` los lee el source | `src/fvOptions/axialFlowTurbineALSource/axialFlowTurbineALSource.C:358-364` (`coeffs_.lookupOrDefault`, defaults 0.0 y 20) |
| Nivel donde deben quedar | `axialFlowTurbineALSourceCoeffs` (el `coeffs_` del source) |
| `Re` y `liftReCorrExp` los lee `profileData` de **su propio** diccionario | `src/…/profileData/profileData.C:137` y `:714` (default 0.23) |
| Los polares `.dat` **no** declaran `Re` | formato `(alpha Cl Cd Cm)` + comentarios `//`; sólo `S809_multiRe.dat` tiene `tableType multiRe;` / `ReList` |
| Referencia experimental del comparador | `scripts/comparePhaseVI.py:143` `load_experiment` → `sequence_{sequence}_{performance,spanwise}.csv`; banda ±15 % en `:67` y `:598`; banda spanwise en `:68-69` y `:632-637` |
| `EXPERIMENT_DIR` y validación TSR | `tools/case_config.py:32`, `assert_tsr_matches_experiment` `:243` (sequence H en `:255`, bloque S en `:274-292`), `select_speed(...,"S")` `:301-311` |
| Config: tabla de velocidades H y fila S única | `config/case.yaml:32` (`kinematics.speeds`) y `:60-64` (`sequence_s`) |
| Tests que NO pueden romperse | `tests/test_phasevi_data.py:127` (`test_experimental_anchors`), `:146` (`test_sequence_s_repeat`), `:157-160` (`stations == [0.3, 0.47, 0.63, 0.8, 0.95]`), `:323` (`test_provenance_fields`), `:362` (`test_no_report_artefacts_committed`); `tests/test_phasevi_case.py:837` (`test_generated_case_is_current`) |
| El archivo no lo lee nadie | `grep` de `parquet\|pyarrow\|uae6\|\.eng` fuera de `articles/uae6/`: cero lectores |

## Decisiones de diseño

- **D1 — `liftReCorrExp` no va en los polares.** Va en el bloque `profileData/S809`
  renderizado por el generador, al lado de `Re 1e6;`, porque es de ahí de donde
  `profileData` lo lee. Tocar los `.dat` no serviría y rompería
  `test_original_polars_byte_unchanged`.
- **D2 — claves de muestreo ausentes por defecto.** `velocitySampleRadius` y
  `nVelocitySamples` se renderizan **sólo cuando difieren del default del
  source** (0.0 y 20), igual que `liftReCorrExp` respecto de 0.23. Así el render
  por defecto es **byte-idéntico**, `case/` no se toca, `--check` sigue pasando y
  el riesgo de la campaña futura queda aislado en el override. Contrapartida
  asumida: el caso commiteado no declara explícitamente el muestreo neutro.
- **D3 — la referencia nueva no reemplaza la vieja.** Se agrega un directorio
  propio con los **mismos nombres y esquema** (`sequence_S_performance.csv`,
  `sequence_S_spanwise.csv`) derivado del crudo, y se selecciona con el flag
  `--experiment` que ya existe. `data/experiment/` (workbook) queda intacto, así
  que los tests de procedencia y de la fila S siguen verdes, y el acuerdo entre
  las dos fuentes se fija con un test nuevo.
- **D4 — la tabla de TSR por velocidad sale del crudo.** El extractor emite
  `rpm` y `tsr` por punto; de ahí se genera el bloque de cinemática de las 21
  velocidades S. `kinematics.speeds` (H) no se toca.
- **D5 — el archivo se versiona como tabla numérica derivada, no como binario.**
  `/articles/` está gitignored; lo que se versiona es el extractor, la tabla
  derivada y el `PROVENANCE.md` con sha256 del inventario — el mismo patrón que
  ya usa `data/experiment/PROVENANCE.md` ("no report PDF or workbook is
  redistributed").

## Tareas

### S0 — Corregir el issue #8 y registrar el archivo Sequence S ✅
- [x] Estaciones spanwise corregidas a 30/47/63/80/95 %.
- [x] Etapas 3–5 reorientadas a Sequence S; H declarada diferida.
- [x] Archivo registrado con inventario, definición, cobertura y la verificación
      cruzada crudo-vs-workbook.
- **Evidencia:** commit `9a4c932`; issue #8 de GitHub sincronizado.

### S1 — Procedencia versionada del archivo UAE6 ✅
- [x] `scripts/extractUAE6Reference.py` (committed): lee el Parquet del
      archivo, decodifica `<stem>` como `s<WW><YYYY><R>` (velocidad, yaw en
      grados, repetición), enmascara `err != 128`, y emite las dos tablas con el
      **esquema exacto** de `load_experiment` (`file_name`, `sequence`,
      `wind_speed_m_s`, `yaw_token`, `yaw_deg`, `repetition`, `rpm`, `tsr`,
      `rotpow_kw`, `lsstqcor_nm`, `eaeroth_n`, … / `r_over_R`, `cn`, `ct`, `cm`).
- [x] Salida a `data/experiment/uae6-archive/` + `PROVENANCE.md` con:
      definición (reporte + sha256 del PDF), la regla del nombre y su verificación
      contra el canal `YAW`, el cruce de inventario contra la Tabla C-18, el
      sha256 del inventario del archivo y la fecha de extracción.
- [ ] Decodificar yaw/repetition en `articles/uae6/manifest.csv` **desde el
      script** `eng2parquet.py` (no editar el CSV a mano: se regenera) y
      documentar la regla en su README §4.6.
- **AC:** el extractor corre desde un clon limpio salvo por el archivo
  (gitignored) y aborta con mensaje claro si falta; `PROVENANCE.md` pasa
  `test_provenance_fields`; los valores de `s0700000` reproducen la fila del
  workbook.
- **Verificación:** test nuevo que compara la tabla derivada contra
  `data/experiment/sequence_S_*.csv` en 7 m/s.

### S2 — Etapa 1: cuantificar el bug de polares (0 corridas)
- [ ] Por estación (30/47/63/80/95 %) y para el Re local simulado a 7 m/s:
      `K = (Re_local/Re_polar)^n` con `n = liftReCorrExp` (0,23) y el corrimiento
      de α₀, más el Δ`cl` en el α operativo.
- [ ] Integrar el efecto en potencia y **decidir si S6 existe**.
- **AC:** número escrito, con el método y sus límites declarados; sin correr el
  solver.
- **Ojo:** `Re 1e6` es el nivel declarado en el `profileData` renderizado, así que
  `K` se mide contra 1e6, no contra el Re del archivo.

### S3 — Etapa 2: habilitar la configuración validada (código) ✅
- [x] `config/case.yaml`: `actuator.velocity_sampling.{velocity_sample_radius:
      0.0, n_velocity_samples: 20}` y `profile.lift_re_corr_exp: 0.23`, cada uno
      documentado como "igual al default del source ⇒ no se renderiza" (D2).
- [x] `tools/generate_case.py`: tres flags nuevas
      (`--velocity-sample-radius`, `--n-velocity-samples`,
      `--lift-re-corr-exp`) espejando el patrón de `--root-effects`; render
      condicional en `render_fv_options`: las dos de muestreo al nivel
      `axialFlowTurbineALSourceCoeffs`, `liftReCorrExp` dentro de
      `profileData/S809` junto a `Re` (D1).
- [x] README del paquete: las tres flags, la tabla de defaults y por qué
      `liftReCorrExp 0` es lo que desarma el reescalado.
- **AC cumplido:** `--check` sale 0 y `git diff -- case/` queda **vacío** (render
  por defecto byte-idéntico); el override renderiza
  `velocitySampleRadius 3.3; / nVelocitySamples 16;` al nivel del coeffs y
  `liftReCorrExp 0;` inmediatamente después de `Re 1e6;`; los tres twins llevan
  las mismas claves.
- **Verificación:** 26 passed en `tests/test_phasevi_case.py` (2 tests nuevos);
  suite completa `turbinesFoam/tests/` **245 passed, 3 skipped**.
- **Anomalía observada, fuera de alcance:** el render de `fvOptions.ASM-MESH` no
  recibe `polar` (a diferencia de `fvOptions.ALM`/`.ASM`), así que una ablación
  de polar no llega al twin mesh-backed. Preexistente; no se toca en esta
  feature (el alcance es ALM).

### S4 — Etapa 3: la corrida de validación (preparación)
- [ ] Generalizar `sequence_s` a una tabla de velocidades (`sequence_s.speeds`)
      manteniendo la fila de 7 m/s como default, y extender `select_speed`/
      `assert_tsr_matches_experiment` sin cambiar el comportamiento de H (D4).
- [ ] Habilitar los 21 puntos a 0° yaw de la secuencia elegida (S y, si se
      confirma, H) en el runner y en el comparador. Extra barato: T (2°) y U (4°)
      como sensibilidad de pitch.
- **AC:** `--sequence S` acepta las 21 velocidades; H sigue byte-idéntico; un
  test fija el TSR de cada velocidad contra la tabla derivada en S1.

### S5 — Etapa 4: la corrida
- [ ] ALM D/32, configuración completa (S3), Sequence S 7 m/s.
- [ ] Potencia ±15 % (ideal ±10 %), empuje reportado, `c_n` en 30/47/63/80/95 %,
      tabla por revolución con drift < 0,2 %/rev sostenido 5 rev.
- **AC:** resultado medido dos veces antes de reportarlo.
- **Requiere:** autorización de cola larga (el runner la exige explícitamente).

### S6 — Etapa 5: augmentación rotacional (condicional a S2)
- [ ] Sólo si S5 deja un residuo que la justifique.

## Alcance

**In:** issue #8; procedencia versionada del archivo Sequence S; generador y
configuración del caso; comparador y referencia experimental; la corrida de
validación; tests y documentación del paquete.

**Out:** ASM y ASM-mesh (el alcance es ALM); las secuencias estacionadas L y O y
la de visualización P; push, PR y merge; la matriz de augmentación antes de que
S2 la justifique.

## Registro de evidencia

| Fecha | Qué | Resultado |
| --- | --- | --- |
| 2026-10-07 | Archivo Sequence S vs Tabla C-18 y vs los CSV commiteados | OK (tabla de arriba) |
| 2026-10-07 | Anclas de código leídas y fijadas | OK (tabla de anclas) |
| 2026-10-07 | S3: `--check` sale 0 y `git diff -- case/` vacío | OK, render por defecto byte-idéntico |
| 2026-10-07 | S3: `turbinesFoam/tests/` completo | **245 passed, 3 skipped** |
| 2026-10-07 | Inventario de las 8 secuencias vs las tablas C-7…C-20 del reporte | **522 = 522**, las 8 cierran |
| 2026-10-07 | Crudo vs workbook para `h0700000` (además de `s0700000`) | idéntico → H también queda corroborada por bytes |
| 2026-10-07 | Catálogo de secuencias y evaluación de candidatas | `data/experiment/uae6-archive/CATALOG.md` |
| 2026-10-07 | S1: crudo vs workbook en S (8 cantidades + 5 estaciones spanwise) | <1e-5 relativo; spanwise idéntico; `yaw_deg` difiere 2,1e-3 por redondeo del workbook |
| 2026-10-07 | S1: `extractUAE6Reference.py --check` | exit 0, tablas reproducibles |
| 2026-10-07 | S1: tests nuevos | **15 passed** (gramática del stem, cobertura, cruce con el workbook, inventario) |

## Registro de commits

| Commit | Tarea |
| --- | --- |
| `9a4c932` | S0 — issue #8 + doc de feature |
| `c99e09e` | S3 — muestreo y exponente de Re renderizables |
| `fd6ecdf` | Catálogo de las 8 secuencias + selección de candidata |
| `dfdb9d5` | Borrado del downloader + registro del método de descarga |
| _(S1)_ | Extractor, tablas derivadas, PROVENANCE e inventario |
