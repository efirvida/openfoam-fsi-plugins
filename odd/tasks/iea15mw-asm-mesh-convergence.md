# IEA 15 MW — cómo validar la convergencia del ASM+mesh (el caso crítico del FSI)

- **Creado:** 2026-10-07
- **Relacionado:** `odd/tasks/iea15mw-references.md` (configuración validada),
  `odd/tasks/iea15mw-asm-cases.md` (la implementación del ASM)

## El problema, y por qué no es sólo "correr más"

Los datos del ASM-mesh (misma malla, dominio y punto que el ALM):

| rev | cp | torque |
| --- | --- | --- |
| 12 | 1,0678 | 46,0 MN·m |
| 20 | **0,3205** | **13,8 MN·m** |

Una caída de **3,3×** entre la rev 12 y la 20 no es una convergencia lenta: es
o una constante de tiempo enorme, o un problema del modelo. Y hay un segundo
síntoma **independiente del transitorio**: su `c_t` spanwise es **2,1-2,3×** el
del ALM, cuando la fuerza por nodo ya está verificada al 0,2 %.

Son **dos cosas separadas** y hay que tratarlas distinto:

- **(a) la anomalía de momento/torque** — determinista, presente en toda
  revolución. Sospechoso: `bladeSurfaceSource::moment()` (el brazo de momento:
  los nodos del STL no están donde están los elementos).
- **(b) la deriva larga** — transitorio, o interacción con el borde del dominio.

Mientras (a) no se cierre, ninguna curva de convergencia es interpretable.

## Etapa 1 — separar "no convergió" de "está mal" (0 corridas, datos en disco)

El run del ASM-mesh ya escribe todo lo necesario: los 147 CSV por elemento (mismas
columnas que el ALM) y `postProcessing/bladeSurface/0/turbine.blade1.surface.csv`
(los nodos de la superficie).

1. **El brazo de momento.** Calcular el torque de dos formas para el MISMO
   instante: (i) de los nodos de la superficie, Σ rᵢ×Fᵢ (el camino de `moment()`);
   (ii) de los elementos, Σ rₑ×Fₑ repartido por la longitud del elemento. Si el
   cociente es ~1,6, el brazo de momento es el culpable y es un fix de **código**
   (las posiciones de nodo no coinciden con las de elemento).
2. **Partición de unidad.** La suma sobre los nodos de la fuerza depositada contra
   el `forceVector_` del elemento: debe dar 1,00. Si no, `distributeNodeForces` o
   el peso por área (`patchArea_`) están mal.
3. **La forma del transitorio.** El `cp` por revolución de TODAS las
   revoluciones, ajustado a una exponencial → la constante de tiempo → las
   revoluciones necesarias para el umbral. **Si decae monótonamente, va a
   converger con más revs; si oscila, es problema de modelo o de borde.**
4. **Primer paso vs convergido.** El mismo test que cerró el diagnóstico del ALM:
   si el primer paso ya viene con el exceso, no es la estela.

## Etapa 2 — el protocolo de convergencia (cuando la 1 diga que el modelo es sano)

Los criterios **hay que escribirlos**, hoy no existen:

- `|Δ cp|` por revolución **< 0,2 %** sostenido 5 revoluciones, y lo mismo para el
  torque y el empuje;
- spanwise: el drift por banda (r/R 0,3-0,5 / 0,5-0,7 / 0,7-0,9) **< 2 %** entre
  la anteúltima y la última;
- el ripple 3/rev estable en amplitud **y fase**;
- Courant y residuales de continuidad dentro de rango.

El **horizonte sale del ajuste de la Etapa 1**, no de una corazonada. Y la
evidencia es la **tabla por revolución**, no un punto final: la convergencia se
valida mostrando la curva, no el último número.

**Presupuesto**: a 0,42 rev/h (medido), 40 rev = **95 h**, justo en el límite de
las 96 h de `sequana_cpu`. Conviene el mecanismo de slices con reanudación que el
runner ya tiene probado, para que una interrupción no pierda nada.

## Etapa 3 — el eje de malla

El ε del ASM es **por celda** (`2·cbrt(V)·meshFactor`), así que la convergencia del
ASM+mesh tiene un eje **espacial**, no sólo temporal: hace falta mostrar al menos
**dos resoluciones**. Con las zonas del snappy ahora parametrizables, la segunda
malla es un flag (`--snappy-level 4` en el disco, o la malla medium) — no un
proyecto.

## Etapa 4 — la convergencia acoplada (lo que el FSI necesita de verdad)

Con FSI, el ASM+mesh **no** converge a un estado estacionario: converge a un
**estado periódico acoplado**. Los criterios son otros:

- la **deflexión del tip** (los ~19 m de referencia) y su amplitud por ciclo deben
  ser periódicas: |Δ| < 1 % entre rotaciones sucesivas;
- las cargas integradas, ídem;
- **el lazo interno**: la sub-iteración de acoplamiento fluido↔estructura tiene que
  converger en **cada** paso de tiempo, no alcanza con el residuo del fluido;
- la **historia de la deflexión** tiene que caer dentro de la zona refinada — por
  eso las extensiones de snappy que hiciste (disco ±10 m, estela radio 170 desde
  −20 hasta +470).

Esa es la validación que el FSI necesita, y se hace **después** de que el rígido
converja: si el rígido no cierra, el acoplado hereda el problema y encima lo
esconde.

## Orden recomendado

| # | etapa | costo | por qué en ese lugar |
| --- | --- | --- | --- |
| 1 | brazo de momento y partición de unidad | **0 corridas** | cierra (a) antes de interpretar cualquier curva |
| 2 | leer la corrida `11609926` (config validada) | ya corriendo | si con polares+muestreo+Glauert deja de derivar, media Etapa 2 hecha |
| 3 | Etapa 2 con el horizonte medido | 40-60 rev | la evidencia de convergencia |
| 4 | Etapa 3, segunda malla | 1 corrida | demuestra que no es artefacto de resolución |
| 5 | Etapa 4, acoplado con Aeroelast | el proyecto FSI | recién con el rígido cerrado |

## Lo que NO sirve

- **Correr 40 rev sin la Etapa 1**: si el brazo de momento está mal, vas a gastar
  95 h para obtener una curva de convergencia de una cantidad mal calculada.
- **Citar el `cp` 0,3205**: hoy es un punto de una trayectoria que se derrumba, no
  un resultado.
- **Declarar convergencia por el último valor**: sin la tabla por revolución no hay
  evidencia.
