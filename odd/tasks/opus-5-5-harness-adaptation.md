# Adaptación de «Prompting Claude Opus 5.5» a este repositorio

- **Estado:** implementado y verificado (3 rondas de `gentle-ai-verify`; las dos primeras encontraron un revert real cada una)
- **Origen:** <https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5>
- **Skill:** `.agents/skills/opus-5-5-harness/SKILL.md` (nuevo)
- **Puntero:** `AGENTS.md` § «Agent turn discipline and model effort»
- **Perfiles:** `~/.pi/agent/subagents.json` (config **global**, autorizada por el usuario)

## Qué de la guía aplica acá y qué no

La guía describe deltas de comportamiento de Claude Opus 5.5 y los patrones de
prompt/harness que los corrigen. Hay dos clases de palanca y confundirlas es el
error central a evitar:

| Palanca | Dueño | Estado en este repo |
| --- | --- | --- |
| thinking siempre activo, `max_tokens` 128 K, effort por mensaje, mensajes de sistema turn-scoped, tool declarada desde el primer request | adaptador Pi | **ya provisto**: `models-store.json` declara para `claude-opus-5-5` `forceAdaptiveThinking`, `supportsMidConvoEffort`, `supportsMidConvoSystemMessages`, `supportsMidConvoToolChanges`, `maxTokens: 128000`, `thinkingLevelMap` low…max. No se reimplementa desde un prompt. |
| disciplina de turno, actualizaciones de progreso, exploración previa, texto pegado, calibración de effort | prompt / perfiles de agente | es lo que escribe esta adaptación |

Descartado por no aplicar: defaults de diseño frontend (no hay frontend en el
repo) y scaffolding para inputs visuales densos (no hay charts como insumo; sí
hay PDFs de referencia). La sección de refusals queda reducida a una nota: pedir
que el modelo reproduzca su razonamiento interno en el texto de respuesta puede
ser declinado (`reasoning_extraction`), y el hallazgo de vulnerabilidades en
código fuente está permitido.

## Decisiones del usuario

1. **Perfiles:** recalibrar effort ahora **y** dejar documentado un bloque
   Opus 5.5 opcional para cuando una campaña lo justifique.
2. **Instrucción «no cortar el turno»:** incorporarla **con guardarraíles**, no
   en su forma cruda: la guía avisa que agrega tool calls y tokens, y este repo
   tiene el costo por token medido (`odd/tasks/token-economy.md`).
3. **Artefactos:** skill + puntero en `AGENTS.md` + `subagents.json`. Sin tocar
   `~/.pi/agent/settings.json`.

## Tareas

- [x] **T1** Doc de tarea + espejo en Engram (`odd/opus-5-5-harness/tasks`).
- [x] **T2** Skill `.agents/skills/opus-5-5-harness/SKILL.md` con las siete
      secciones que sí aplican (qué da el harness, calibración de effort,
      disciplina de turno, progreso, explorar antes de actuar, texto externo
      como dato, razonamiento/visual), más anti-patrones y el bloque Opus
      opcional.
- [x] **T3** Puntero corto en `AGENTS.md` para que la skill sea descubrible sin
      cargarla en cada request.
- [x] **T4** Routing de effort en **las dos capas**: `thinking:` de
      `~/.pi/agent/agents/jd-judge-a.md` y `review-risk.md` de `max` a `high`, y
      los mismos dos valores en `~/.pi/agent/subagents.json`; más
      `default_thinking_level` de `high` a `medium`. Backups previos de ambos
      archivos.
- [x] **T5** Entrada 19 en `CHANGELOG.md` (`### Tooling`, formato Files/Problem/Fix).
- [x] **T6** Verificación.

## Por qué `max → high` en esos dos roles

La guía dice explícitamente **reservar `xhigh`/`max` para trabajo donde se midió
una ganancia de calidad**. En `subagents.json` esos dos perfiles estaban en `max`
sin medición registrada en ningún lado: era un valor por defecto, que es
exactamente lo que la guía pide dejar de hacer. La escalera que queda es
defendible por sí sola: `low` para scouting, `medium` para trabajo agentic
(el default que la propia guía recomienda), `high` para verificación y revisión
adversarial, y `max` sólo contra una comparación registrada.

**Caveat declarado:** los perfiles apuntan a modelos `nan/*` (glm-5.3-flash,
deepseek-v4-flash), no a Opus 5.5, y la guía avisa que los nombres de effort no
significan lo mismo entre modelos. Lo que se transfiere es la **política**
(baseline medium, tope por medición), no los números. Si un modelo `nan/*` no
declara `low` en su `thinkingLevelMap`, Pi lo ignora en silencio; eso ya era así
antes de este cambio y no se tocó.

## Defecto que encontró la verificación: el routing tiene CUATRO capas

Hicieron falta tres intentos, y los dos primeros reportaron éxito. Vale
registrar la secuencia porque el error no fue el valor elegido sino la capa:

| Intento | Qué se editó | Qué pasó |
| --- | --- | --- |
| 1 | `~/.pi/agent/subagents.json` (espejo) | una pasada de materialización lo reescribió a `max` ~70 s después (edit 17:17:07, rewrite 17:18:17) |
| 2 | + frontmatter de la definición del agente | la pasada reescribió **ambos** a las 17:32:35, desde `models.json`, que seguía en `max` |
| 3 | `models.json` + preset activo + las dos capas derivadas | consistente en las cuatro, y **sin** reescritura posterior |

Las cuatro capas, en el orden en que la pasada las usa:

| Capa | Qué tiene | Estado |
| --- | --- | --- |
| `~/.pi/gentle-ai/models.json` | routing vivo de los 12 agentes + `orchestrator` | **la autoridad** de la que `applyModelConfig` materializa |
| `~/.pi/gentle-ai/profiles.json` → `profiles[active]` | presets con nombre; `active` = `nan-quota-guard` | si no se toca, re-aplicar el preset restaura el valor viejo |
| `~/.pi/agent/agents/<rol>.md` → `thinking:` | copia materializada | regenerada por la pasada |
| `~/.pi/agent/subagents.json` → `model_profiles.<rol>.effort` | espejo que Pi resuelve al lanzar | regenerada, salvo las claves que viven sólo acá (`review-refuter`, `review-validator`, `default_thinking_level`) |

`default_thinking_level: medium` sobrevivió las tres pasadas justamente porque
ninguna otra capa tiene esa clave. Los otros presets (`nan-balanced`,
`nan-max-depth`, `nan-spread`, `current`) siguen en `max` a propósito: son
presets con nombre propio y `nan-max-depth` quiere decir lo que dice. Si querés
que la recalibración valga también para alguno de ellos, es una decisión tuya,
no un efecto colateral de esta tarea.

Backups de los cinco archivos editados: `<nombre>.bak-20261012T173841`.

**Lectura del mecanismo (ronda 3).** El tercer cambio, hecho en la autoridad, no
provocó ninguna reescritura: los tres archivos derivados conservaron el mtime de
la edición (`17:39:34`) a través del lanzamiento de un subagente, y los ocho
valores siguieron en `high`. Los dos reverts anteriores ocurrieron justo después
de editar una capa **derivada**, o sea dejando a `models.json` en desacuerdo con
su copia. Eso se lee como **reparación de drift desde la autoridad**, no como una
pasada periódica. No está probado como mecanismo — sólo observado tres veces —,
pero la conclusión operativa es la misma en ambos casos: la decisión tiene que
estar en `models.json`, y las otras tres capas sólo tienen que coincidir con él.

## Verificación

| Check | Resultado |
| --- | --- |
| Las cuatro capas coinciden en los 12 agentes (`models.json` = preset activo = frontmatter = espejo) | PASS (`disagreements: 0`) |
| `subagents.json` parsea; `default_thinking_level: medium` se conserva | PASS |
| `review-refuter` / `review-validator` presentes sólo en el espejo, por diseño (`PROVIDER_REVIEW_ROLES`) | PASS |
| Frontmatter de la skill: YAML parsea, `name` = directorio, `description` presente | PASS |
| Descubribilidad real: `pi --approve -p "List the exact names of every skill currently available…"` devuelve `opus-5-5-harness` junto a `validation-analysis-tools` | PASS |
| Paths citados por la skill y por la sección de `AGENTS.md` | PASS tras corregir `data/experiment/` por los reales: `phaseVI/data/experiment`, `iea15mw/data/polars`, `nacelle-asn/data/reference` |
| Mecanismo verificado en el código de gentle-pi: `applyModelConfig` escribe frontmatter y después espejo; precedencia espejo → definición → default | PASS |
| Sección nueva en `AGENTS.md` (una vez, antes de `## Build / Clean`) y entrada 19 dentro de `### Tooling` sin repetir número | PASS |
| Claims del catálogo para `anthropic/claude-opus-5-5` (`forceAdaptiveThinking`, `supportsMidConvo*`, `maxTokens: 128000`, `thinkingLevelMap` low…max) | PASS |
| Durabilidad de los agentes frente a `gentle-ai` sync: son assets de paquete pero **no** están en `managed-assets.json`, así que un sync normal no los pisa; lo que los pisaba era la materialización desde `models.json` | PASS con caveat |
| **Prueba de durabilidad (ronda 3):** los tres archivos derivados conservan el mtime de la edición (`17:39:34`) a través del lanzamiento de un subagente, los ocho valores siguen en `high`, `active` sigue en `nan-quota-guard` | PASS — el disparador que revertó las rondas 1 y 2 no volvió a dispararse |
| Narrativa de las cuatro capas en skill, `AGENTS.md`, `CHANGELOG` y este doc: sin contradicciones, y los presets que conservan `max` son los declarados | PASS |
| Dato del intervalo «~70 s» del primer revert | atestiguado por la verificación ronda 1, no por un mtime: la segunda pasada sobrescribió el timestamp |
| `models.json` tiene una 13ª entrada `orchestrator` (medium) sin espejo ni archivo de agente | esperado: es routing del orquestador, no un agente |

No se corrió `pytest`: el cambio no toca código Python.

**Caveat honesto de la ronda 3:** el verificador no lanza subagentes (le está
prohibido), así que el disparador de `applyModelConfig` no se ejercitó *desde
adentro* de esa corrida; lo que sí quedó probado es que no hubo reescritura y que
los valores sobrevivieron al lanzamiento que ocurrió en esta sesión.
