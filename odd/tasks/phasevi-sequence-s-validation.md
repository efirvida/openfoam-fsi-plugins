# Feature: phasevi-sequence-s-validation

Rediseñar y ejecutar la validación del ALM de NREL Phase VI contra la **campaña
Sequence S** real, aprovechando el archivo crudo completo que ya vive en el repo.

- **Issue:** #8 `Phase VI: redisenar la validacion del ALM con la configuracion
  validada en el IEA` (`odd/issues/phasevi-alm-validation-redesign.md`)
- **Paquete:** `turbinesFoam/validation/phaseVI/`
- **Definición experimental:** `turbinesFoam/articles/29955.pdf`
  (NREL/TP-500-29955), sha256
  `822ee980e97780599ad4ec1dc8b4cc8ad41131b0cbbdffa19999d571f6ce4958`
- **Insumo nuevo:** `turbinesFoam/articles/uae6/` — 106 puntos de ensayo
  Sequence S en crudo (`.hd1` + `.eng`) + conversión Parquet, `channels.csv`
  (285 canales) y `manifest.csv`
- **Decisión del usuario (2026-10-07):** la secuencia de validación es
  **Sequence S** (7 m/s puntual y curva de potencia a 0° yaw). Sequence H queda
  fuera por ahora; el usuario está buscando el archivo crudo H. El diseño debe
  quedar **agnóstico de la secuencia** para poder sumar H sin rediseñar.

## Por qué

El paquete valida hoy contra `data/experiment/*.csv`, derivado del workbook WDH
`wt_loads_statistics.xls` (medias de registros, 0° yaw, 5 estaciones): 6 filas H
+ **1 sola fila S**. El archivo crudo de Sequence S trae la medición completa —
y su inventario cierra exactamente contra la Tabla C-18 del reporte (104
archivos de 30 s + 2 de 6 min = 106).

Evidencia ya verificada (2026-10-07, esta sesión):

| Chequeo | Resultado |
| --- | --- |
| Inventario local vs Tabla C-18 (p. 202 / PDF 212) | 106 = 106, coincide el desglose 104 × 30 s + 2 × 6 min |
| `articles/29955.pdf` sha256 vs el `29955_nlr.pdf` del openspec | idéntico (`822ee980…ce4958`) |
| `s07ysu00` / `s10ysu00` = 199 502 frames (383 s) | son los barridos de yaw a 1°/s que el reporte describe para 7 y 10 m/s |
| Convención `SWWYYYYR` (p. 212) vs canal medido `YAW` | token `0050`→5,05°; `0100`→10,02°; `0200`→20,02°; `0300`→29,95°; `0450`→44,98°; `0600`→59,98°; `0750`→75,04°; `0900`→90,04°; `1350`→135,06° |
| Crudo `s0700000` vs `data/experiment/sequence_S_performance.csv` | rpm 71,8667 / 6,0304 kW / 801,265 Nm / 1149,53 N — idéntico |
| Crudo `s0700000` vs `sequence_S_spanwise.csv` (5 estaciones) | cn/ct/cm idénticos dígito a dígito |
| Cobertura 0° yaw | **21 velocidades** (5…25 m/s) — curva de potencia completa |
| Cobertura de yaw | juego completo (5/10/20/30/45/60/75/90/135/180°) a 5, 7, 10 y 15 m/s; 5°/10° en el resto |

Dos defectos detectados en el issue #8 que esta feature corrige:

1. Las estaciones spanwise de aceptación están escritas como **25/35/60/82/92 %**
   (son de MEXICO). Las reales del Phase VI son **30/47/63/80/95 %**
   (`PROVENANCE.md`, README del paquete y `channels.csv` coinciden).
2. La Etapa 3 apuntaba a **secuencia H**, sin respaldo crudo en el repo.

## Alcance

**In:** el issue #8; la procedencia versionada del dataset Sequence S; el
generador y los polares de Phase VI; el comparador; la corrida de validación ALM
a 7 m/s; tests y documentación del paquete.

**Out:** ASM y ASM-mesh (el alcance es ALM); Sequence H (diferida hasta que
aparezca el crudo); push, PR y merge; la matriz de augmentación antes de que el
residuo la justifique.

## Tareas

### S0 — Corregir el issue #8 y registrar el archivo Sequence S
- [ ] Corregir las estaciones spanwise a 30/47/63/80/95 %.
- [ ] Reorientar las Etapas 3–5 a Sequence S (7 m/s + curva a 0°).
- [ ] Registrar el archivo crudo: inventario, definición, cobertura y la
      verificación cruzada crudo-vs-workbook.
- [ ] Dejar explícito que H queda diferida y por qué.
- **AC:** el issue no contiene ningún radio inexistente y toda cifra que afirma
  tiene su fuente (tabla del reporte o chequeo reproducible).

### S1 — Procedencia versionada del dataset Sequence S
- [ ] Decodificar el yaw en `manifest.csv` (token `YYYYR`, con la
      correspondencia verificada contra el canal `YAW`) y documentarlo en el
      README del dataset.
- [ ] Registrar en el repo (no en `/articles/`, que está gitignored) un
      `PROVENANCE.md` con: definición (reportero + sha256 del PDF), inventario,
      sha256 por archivo (o del inventario), script de extracción, y la
      verificación cruzada contra `data/experiment/sequence_S_*.csv`.
- **AC:** un clon limpio puede reproducir y auditar la procedencia; el spec
  `phasevi-data-provenance` queda satisfecho para la fuente nueva.

### S2 — Etapa 1: cuantificar el bug de polares (0 corridas)
- [ ] Leer la línea `Re` de cada polar commiteado de Phase VI.
- [ ] Calcular `K = (Re_local/Re_polar)^0.23` y el corrimiento de α₀ por estación.
- [ ] Integrar el efecto en potencia y decidir si la Etapa de augmentación
      existe.
- **AC:** escribe el número y decide; sin corridas de solver.

### S3 — Etapa 2: habilitar la configuración validada (código)
- [ ] Espejar `velocitySampleRadius` / `nVelocitySamples` (y `meshFactor` si
      aplica) en `tools/generate_case.py`, **con default byte-idéntico** al
      render actual.
- [ ] Aplicar `liftReCorrExp 0` a los polares de Phase VI.
- **AC:** `generate_case.py --check` pasa sin cambios en `case/`; los tests de
  contrato del caso siguen verdes; el render por defecto es byte-idéntico.

### S4 — Etapa 3: la referencia experimental Sequence S
- [ ] Derivar la curva a 0° yaw (21 velocidades) y las estaciones spanwise del
      crudo, con el `err` byte enmascarado.
- [ ] Extender `data/experiment/` (o un directorio nuevo) + PROVENANCE.
- [ ] Hacer que `scripts/comparePhaseVI.py` consuma la referencia nueva sin
      romper la actual; mantenerlo agnóstico de la secuencia.
- **AC:** los valores del crudo reproducen la fila `s0700000` del workbook; un
  test lo fija.

### S5 — Etapa 4: la corrida de validación
- [ ] ALM D/32 con la configuración completa, Sequence S 7 m/s.
- [ ] Potencia dentro de ±15 % (ideal ±10 %); empuje reportado; spanwise `c_n` en
      las 5 estaciones; tabla por revolución con drift < 0,2 %/rev sostenido 5 rev.
- **AC:** resultado verificado dos veces antes de reportarlo.

### S6 — Etapa 5: augmentación rotacional (condicional)
- [ ] Sólo si S5 deja un residuo que la justifique.

## Registro de evidencia

| Fecha | Qué | Resultado |
| --- | --- | --- |
| 2026-10-07 | Archivo Sequence S verificado contra Tabla C-18 y contra los CSV commiteados | OK, ver tabla de arriba |

## Registro de commits

(pendiente)
