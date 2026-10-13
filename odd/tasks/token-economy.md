# Economía de tokens del flujo de trabajo (local al repositorio)

- **Estado:** implementado y verificado (medición + reglas + herramientas locales)
- **Ámbito:** solo este repositorio. No toca configuración global de Pi, del
  harness ni de otros proyectos.
- **Evidencia base:** los 14 registros de sesión de Pi en
  `~/.pi/agent/sessions/--scratch-...-tmp-of-plugins--/` (156 MB, 3280 llamadas
  al modelo, 25/09/2026 – 09/10/2026). Reproducible con `tools/session_cost.py`.

## 1. Cómo se ejecuta el trabajo en este repositorio

Campañas de validación de CFD: se prepara un caso (`tools/generate_case.py`),
se encola en Slurm (SDumont), se espera horas o días, se leen planos de salida y
se comparan contra datos experimentales (NREL Phase VI, IEA 15 MW) con
`scripts/comparePhaseVI.py`, `scripts/compare_spanwise.py` y
`scripts/compareNacelle.py`. En paralelo se leen referencias (PDF de NREL,
Dagsørensen, etc.) para resolver formulaciones físicas.

Consecuencia medida: las sesiones son **largas y de espera** (629–684 llamadas,
6–14 h). El contexto crece de forma casi lineal con la sesión y nunca se reinicia.

## 2. Dónde se consume realmente

Cifras medidas, no estimadas:

| concepto | valor |
|---|---|
| llamadas al modelo | 3280 |
| tokens de entrada sin caché | 155.0 M |
| tokens de salida | 5.3 M (3.5 M de razonamiento) |
| lecturas de caché | 1174 M — **coste $3.59 de $19.91** |
| coste total | $19.91 (entrada $13.97, salida $2.35, caché $3.59) |

**Concentración del coste (hecho comprobado):** 303 llamadas de 3280 (9.2 %)
acumulan **149.4 M de los 155 M de tokens de entrada (96.4 %)** y **$13.97 de
$19.91**. Son *cache miss* con prefijo de ~950 K tokens: la pausa mediana antes
de ellas es de 233 s, así que la caché del proveedor expira y **todo el contexto
se vuelve a facturar a precio pleno de entrada**.

No es cambio de modelo (1 de 276 casos), ni el tamaño bruto de las lecturas.

**Composición del contexto** (sesión 2026-10-01, 684 llamadas; estimación
chars/4 contrastada contra el prefijo medido, ratio 0.91):

| componente | tokens | % |
|---|---|---|
| bloques de *thinking* del asistente | 736 K | 60.3 % |
| argumentos de `edit` / `write` / `bash` | 186 K | 15.2 % |
| resultados de `bash` | 155 K | 12.7 % |
| resultados de `read` | 72 K | 5.9 % |
| texto del asistente | 48 K | 3.9 % |
| prompt de sistema (AGENTS.md + skills + tools) | ~7 K | 0.6 % |

El ratio estimado-con-thinking / medido es **0.91** frente a **0.37** sin
thinking: **los bloques de razonamiento se retienen en la transcripción y se
re-envían en cada llamada posterior**. Es el 60 % del contexto y, por lo tanto,
el 60 % de cada re-facturación a precio pleno.

### Hipótesis refutadas por la medición

- **"Las imágenes dominan el consumo."** Falso. 98.4 % de los caracteres leídos
  son imágenes/PDF (76.9 M de 78.2 M), pero Pi las **redimensiona** antes de
  enviarlas: crecimiento mediano del prefijo por imagen = **3125 tokens**, no
  ~600 K. Es un problema de peso de sesión en disco (156 MB), no de tokens.
- **"Los subagentes son un gasto redundante."** Falso: 55 resultados de
  `subagent_run`, 299 K caracteres en total, media 5.4 K por llamada. Son un
  ahorro de contexto, no un coste.
- **"Releer archivos de texto es el problema."** Marginal: 1.3 M caracteres de
  texto leído en total, frente a 155 M tokens de entrada. `generate_case.py` se
  leyó 38 veces, pero el coste agregado es despreciable.

### Modelo contrafactual (estimación, no medición)

Asumiendo que el prefijo se reinicia al abrir sesión y que el coste sigue al
prefijo acumulado:

| corte de sesión | tokens de prefijo acumulados | variación |
|---|---|---|
| sin corte (real) | 1.33 B | — |
| ≤ 300 llamadas | 0.70 B | −47 % |
| ≤ 200 llamadas | 0.49 B | −63 % |
| ≤ 120 llamadas | 0.32 B | −76 % |

Estimación conservadora y solo sobre el término dominante medido: si el contexto
fuera de ~200 K en lugar de ~950 K, esas 303 llamadas en frío costarían ~$4 en
lugar de $13.97.

## 3. Mejoras locales implementadas

1. **Reglas de economía de contexto en `AGENTS.md`** — se cargan siempre en este
   repositorio (0.6 % del contexto: ampliarlas es casi gratis frente al 60 % de
   thinking retenido).
2. **`tools/session_cost.py`** — informe de coste real de las sesiones de Pi
   filtrado a este repositorio: entrada/salida/caché, coste, concentración de
   *cache miss* y composición estimada del contexto. Convierte este diagnóstico
   en algo re-ejecutable en lugar de un análisis de una sola vez.
3. **`turbinesFoam/validation/tools/case_state.py`** — lector de estado de un
   *run*: filas, tiempo primero/último, revoluciones y media de la última
   ventana de las columnas crudas de `turbine.csv`. Es un **lector puro**: no
   redefine métricas ni constantes experimentales.

## 4. Criterios de validez e invalidación

- `tools/session_cost.py`: válido mientras el formato del registro de sesión de
  Pi (`PI_SESSION_FILE`, JSONL v3) mantenga los campos `usage`. Si aparece
  `usage` vacío o el esquema cambia de versión, la herramienta lo reporta como
  error explícito en vez de imprimir ceros.
- `case_state.py`: válido para el esquema de `postProcessing` actual
  (`turbines/*/turbine.csv`, `actuatorLines/*`, `actuatorLineElements/*`). Una
  columna nueva no invalida el resultado; una columna ausente se omite y se
  reporta. **Nunca** sustituye a `scripts/comparePhaseVI.py`: los valores
  calibrados contra el experimento salen solo de ahí.
- Ningún resultado de estas herramientas se cachea en disco: sus entradas
  (registros de sesión, `turbine.csv`) cambian durante una campaña.

## 6. Cambios globales aplicados (autorizados en la segunda ronda)

Archivo: `~/.pi/agent/settings.json` (backup en `settings.json.bak-20261009T130719`).

**El mecanismo, demostrado antes de tocarlo:** con `contextWindow = 1 000 000` y
el `reserveTokens` por defecto de 16 384, Pi compacta por encima de 983 616
tokens. Los transcripts contienen **4 entradas `compaction`**, una con
`tokensBefore: 984 807` y un resumen de 15 170 caracteres. Es decir: el techo de
982 288 observado no era el límite del modelo sino el umbral de compactación, y
la compactación ya existía, sólo que tardía.

**Cambio aplicado** — bloque agregado a `~/.pi/agent/settings.json`:

```json
"compaction": {
  "keepRecentTokens": 50000,
  "modelOverrides": {
    "nan/deepseek-v4-flash":           { "reserveTokens": 600000 },
    "opencode-go/deepseek-v4.1-flash": { "reserveTokens": 600000 },
    "opencode-go/glm-5.3":             { "reserveTokens": 600000 }
  }
}
```

y `"showCacheMissNotices": true` para que los *cache miss* que dominan el costo
sean visibles en el momento.

**Por qué `modelOverrides` y no `reserveTokens` global:** la ventana más chica
del catálogo es 204 800 (minimax-m2.7) y hay modelos de 256 000 y 262 144. Un
`reserveTokens` global de 600 000 sería mayor que esas ventanas y haría que la
compactación disparara siempre. Con override, cada modelo conserva el
comportamiento por defecto salvo los que sí tienen ventana grande.

**Criterio de seguridad aplicado:** sólo se sobreescribe un modelo si su ventana
está **medida o declarada** ≥ 1 000 000, o si el prefijo máximo observado prueba
que la ventana supera los 600 000. `nan/deepseek-v4-flash` entra por medición
(prefijo máximo 820 469 ⇒ ventana ≥ 836 853). **`opencode-go/kimi-k2.6` queda
fuera a propósito**: su prefijo máximo observado es 88 221, así que no hay
evidencia de que su ventana aguante 600 000.

Efecto esperado (estimación, no medición): el contexto oscila entre 50 000 y
400 000 en lugar de entre 20 000 y 984 000. Como el costo dominante es
proporcional al contexto en cada *cache miss*, la reducción esperada ronda el
50 %. Es verificable re-ejecutando `tools/session_cost.py` en las próximas
sesiones: tienen que aparecer más entradas `compaction` con `tokensBefore`
cerca de 400 000 y bajar el `input` sin caché.

**Riesgo aceptado:** compactar más seguido resume y descarta más detalle. Se
mitiga con `keepRecentTokens` de 20 000 → 50 000 y con la regla de escribir los
hallazgos en `odd/tasks/*.md` y memoria antes de que la compactación los tome.

## 7. Lo que se decidió NO cambiar (y por qué)

| cambio | decisión |
| --- | --- |
| `cacheWarming: "idle"` | **Inerte hoy.** Requiere que el catálogo declare `promptCache` (short/long); ningún modelo del store lo declara (0 coincidencias). Además medí la probabilidad de *miss* contra el hueco temporal y **no hay un escalón limpio**: 2.6 % a ≤60 s, 7.2 % a ≤300 s, 10.9 % a cualquier hueco. Sin TTL confirmado, fijar `promptCache` provocaría calentamientos que llegan tarde y salen a precio pleno. No se inventó. |
| `defaultThinkingLevel` | **No se bajó.** El *thinking* es 60 % del contexto, pero también es el razonamiento físico que prioriza el proyecto. Bajarlo global afectaría a todos los proyectos. Queda como decisión consciente: `modelThinkingLevels` permite fijarlo por modelo. |
| `images.autoResize` | Ya está en `true` (2000×2000, JPEG 80): confirma que las imágenes se redimensionan. Bajarlo reduciría fidelidad al leer gráficos y tablas de los papers. |
| hook de `rtk` | **No aplica a Pi.** `rtk init -g` instala el hook de Claude Code / Cursor / OpenCode. Para Pi el equivalente ya está activo: la extensión `pi-rtk-optimizer` con `config.json` propio. |
| `pi-rtk-optimizer` | Ya tiene los valores seguros puestos por el usuario: `readCompaction.enabled: false`, `sourceCodeFiltering: "none"`, `truncate.maxChars: 12000`. **Único punto a revisar por él:** `compactGitOutput: true` condensa `git diff`, y para revisión física rigurosa un diff condensado puede ocultar detalle. |

## 9. El bucle de mejora de herramientas

El detector no es un informe de una sola vez: es el mecanismo que hace que el
conjunto de herramientas crezca solo cuando hace falta.

**Detección automática — `tools/analysis_gap.py`.** Lee los transcripts, clasifica
cada llamada `bash` por evidencia transparente (`case-output`, `turbine-csv`,
`experiment-ref`, `pdf-page`, `pdf-render`, `slurm-queue`, ...), agrupa las que
son análisis inline por **la evidencia que tocan y no por el texto**, y marca las
que ya cubre una herramienta existente vía `TOOL_COVERAGE`. Sobre el corpus
registrado: **552 sitios inline contra 266 que ya llaman a una herramienta del
repo**.

**Promoción revisada — `.agents/skills/validation-analysis-tools/`.** La Skill
contiene el procedimiento (qué existe ya → lector o producto de métrica → test
primero → implementación read-only → registro en tres lugares) y se carga solo
cuando hace falta, no en cada request.

**Registro — `turbinesFoam/validation/tools/README.md`.** Una herramienta que
nadie encuentra no existe.

**Requisito operativo verificado:** las skills de proyecto bajo `.agents/skills/`
están gateadas por *project trust* (así lo dice el código de Pi:
``trust-requiring ... .agents/skills in cwd or one of its ancestors``). Verificado
end-to-end: sin trust el modelo responde `NONE`; con `--approve` responde
`validation-analysis-tools`. En una sesión interactiva Pi pregunta una vez. Si
AGENTS.md se está inyectando, el proyecto ya está confiado. Una sesión abierta
necesita `/reload` para ver una skill recién creada.

### Por qué no se genera el análisis automáticamente

Es la restricción central del diseño, y es deliberada. Un snippet generado no
puede saber que `cp` está definido contra el reporte NREL en
`comparePhaseVI.py`; una métrica plausible pero equivocada es **peor** que un
paso manual visible. Se automatiza detectar y rankear. Promover sigue siendo un
acto revisado.

### El bucle ya se validó a sí mismo con un caso

Mi diagnóstico previo descartó un lector de figuras PDF por evidencia de tokens
(las imágenes se redimensionan a ~3100 tokens, así que no eran el costo). La
evidencia de **recurrencia** dice lo contrario: `x39 python3 [repo-wide]
pdf-page pdf-render`, 39 reescrituras a mano en 4 sesiones, es el hueco real más
grande del repo. Dos señales distintas, dos conclusiones distintas — y la
segunda es la que importa para la reproducibilidad.

### Validez e invalidación

`TOOL_COVERAGE` es una declaración humana, no una inferencia: al agregar o
quitar una herramienta hay que actualizarla, o el detector empieza a recomendar
lo que ya existe (fue exactamente el primer defecto observado al ejecutarlo:
seguía proponiendo `case-output turbine-csv` después de `case_state.py`). Se
mantiene **angosta a propósito**: declarar cobertura de más esconde el próximo
hueco real.

## 10. Pendiente

Lo que queda **no tiene un setting que lo resuelva**, así que no se aplicó nada:

- **Retención de bloques de *thinking* en la transcripción** (60 % del contexto
  medido). No existe opción de configuración: revisitando `settings.md` y
  `message-types.md`, el único mecanismo que los descarta es la compactación,
  que ahora dispara a 400 000 en vez de 983 616. Eliminarlos antes exigiría una
  extensión propia sobre el hook `session_before_compact`, o un cambio aguas
  arriba. No se construyó infraestructura nueva por esto.
- **Nivel de razonamiento por tipo de tarea.** `defaultThinkingLevel` sigue en
  `medium`. Fijarlo por modelo con `modelThinkingLevels`, o bajarlo para tareas
  mecánicas, es una decisión de calidad que le corresponde al usuario.

Candidato local de segunda ronda, sin implementar por coste/beneficio dudoso:
extraer el bloque experimental repetido (`meas = {7:(5.9458,...)}`) a un módulo
compartido. El riesgo real ahí es de **reproducibilidad** (literales duplicados
que pueden divergir de `data/experiment/`), no de tokens.
