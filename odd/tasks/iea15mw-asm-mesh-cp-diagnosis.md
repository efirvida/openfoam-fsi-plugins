# Issue #5 — el `cp` imposible del ASM+mesh: diagnóstico cerrado

- **Status:** cerrado en su pregunta central (¿diagnóstico o física?); deja un
  follow-up abierto y acotado.
- **Issue:** efirvida/openfoam-fsi-plugins#5
- **Branch:** `fix/surface-node-dump-frame` (desde `feat/dagsorensen-tip-correction`)
- **Creado:** 2026-10-07
- **Relacionado:** `odd/tasks/iea15mw-asm-mesh-convergence.md` (Etapa 1),
  `odd/tasks/iea15mw-asm-cases.md`, `odd/tasks/iea15mw-references.md`

## La pregunta del issue, y la respuesta

El issue pedía decidir una cosa: **el `cp` imposible (1,068) es un error de
contabilidad del torque —arreglable en el volcado— o hay que arreglar la física.**
Cerró la sesión con un único insumo sin verificar: `positionsGlobal()`, o sea el
brazo de momento.

**Respuesta: es la física, no la contabilidad.** El brazo de momento, la partición
de unidad y `moment()` están **correctos**, medidos contra los propios CSV de
elemento al 0,2 %. El `cp` reportado *es* el torque BEM de los elementos de esa
corrida: no hay eslabón perdido entre lo que se deposita y lo que se reporta.

## La medición (datos en disco, sin corridas nuevas)

La corrida `runs/iea15mw-asm-mesh-nodedump` (12 pasos, 0,089 rev) tiene el volcado
de nodos **anterior** a `6d32161`: posiciones y fuerzas en el **frame del cuerpo**
(la traspuesta de `bodyToGlobal`), no en el global. La comparación "−73,3e6 vs
+13,9e6" del issue comparaba entonces peras con manzanas:
`+73,3e6` es la **componente y del frame del cuerpo**, mientras `−13,9e6` es la
**proyección sobre el eje del rotor en el frame global**. Ninguna de las dos es
"el momento de nodos" ni "el de elementos".

La comparación correcta necesita el frame del cuerpo exacto. Se reconstruye y se
**valida** así: si la partición de unidad se cumple, la fuerza total de los
elementos rotada al frame del cuerpo tiene que reproducir la fuerza total que el
volcado de nodos ya trae. Reproduce `error = 0.0` (16 dígitos), en los dos
instantes:

| t | eje e1 del cuerpo (global) | T_nodos (volcado) | T_elem rotada | error |
| --- | --- | --- | --- | --- |
| 0,00937 | (−0,010795, −0,103723, 0,994548) | (−103003, 870443, 105770) | idéntica | 0,0 |
| 0,11244 | idem (el frame es fijo) | (8982,7, 268695,7, −871294,7) | idéntica | 0,0 |

`e1` sale del ajuste `station_e = r_e · e1` sobre los 147 elementos (residuo
4,2e-08) y se corrige por el acimut reportado en `turbine.csv` (0,42° y 5,07°).
Que el mismo `e1` sirva para los dos instantes y que reproduzca la fuerza exacta
es la prueba de que el frame reconstruido es el real.

Con ese frame, el momento de nodos y el de elementos:

| t | M_elem (global) | M_nodos (global) | \|M\| nodos/elem | torque nodos/elem |
| --- | --- | --- | --- | --- |
| 0,00937 | (−68,875, −11,057, −1,224)e6 | (−68,891, −11,079, −1,304)e6 | 1,0003 | **1,0019** |
| 0,11244 | (−75,149, −13,934, −7,696)e6 | (−75,177, −13,971, −7,643)e6 | 1,0004 | **1,0026** |

O sea: **mismo signo y cociente ≈ 1**, que es exactamente el criterio de
aceptación del issue. El 0,2 % de diferencia es el corrimiento teórico entre el
centroide de área del parche y el punto del elemento (unos pocos metros de brazo
sobre ~120 m).

Controles adicionales sobre los mismos datos:

- **Partición de unidad:** `|Σ nodeForces_| = |Σ F_e|` idéntico a 10 dígitos
  (911829,1644901214 vs 911829,1645020541), y la igualdad vectorial exacta vía el
  frame (arriba).
- **Ensamblado de la fuerza del elemento:** `|F| / sqrt(f_ref_n² + f_ref_t²)` da
  0,7963–0,7993 en toda la envergadura, que es exactamente el `spanLength` por
  elemento (116,4 m / 147 = 0,792) — las `f_ref_*` son por unidad de span por
  diseño. No hay factor espurio.
- **El `cp` reportado sale de los CSV de elemento:** a t=0,00937 el torque de los
  elementos da cp = 0,9422 contra 0,94457 reportado (0,25 %). La cadena
  BEM → fuerza → momento → `cp` cierra.

## El defecto que sí apareció en el camino

`6d32161` cambió el volcado de nodos a frame global **a medias**: pasó posiciones
y fuerzas a global y **dejó las normales en el frame del cuerpo**. El archivo
quedó con dos frames mezclados, el contrato en `bladeSurfaceSource.H` siguió
diciendo "the per-node quantities are the body-frame SI contract", y los tres
tests que fijan el contrato quedaron en rojo:

```text
test_station_and_node_csv        station == x            (ahora x es global)
test_rotation_lockstep           rota el volcado con el basis del cuerpo
test_surface_moment_in_torque    convierte el volcado con el basis del cuerpo
```

El primer caso, además, expone una ambigüedad de diseño real: `station` es una
**etiqueta estática** (la coordenada z del STL, calculada una vez en el
constructor) mientras `positions()` es un **frame que se mueve** con la pala, así
que `station == x` sólo vale si el frame del cuerpo coincide con el del cuerpo en
el instante de construcción. Escribir el volcado en global elimina la ambigüedad:
las tres magnitudes (posición, normal, fuerza) quedan en el mismo frame que los
CSV de elemento, y el oráculo de momento deja de necesitar una rotación.

## Criterio de aceptación, ahora como comando

`turbinesFoam/tests/test_blade_surface.py` ya tenía el oráculo del momento
(`test_surface_moment_in_torque`, rtol 1e-6 contra `turbine.csv`). Con el volcado
global queda **directo**: `Σ X_i × F_i` sobre el CSV de nodos, sin conversión de
frame, contra el `ct` de `turbine.csv`. Lo mismo para el lockstep de rotación, que
ahora comprueba los frames de verdad. La suite entera de `test_blade_surface.py`
tiene que terminar en verde.

## La anomalía de cargas: causa encontrada, y es un bug del depósito

La sospecha de arriba (ancho de deposición, muestreo de cuerda) era **la
pregunta equivocada**. La causa es más simple y más grave:

`bladeSurfaceSampler::buildCandidates()` cacheaba **una sola vez**, en el
constructor, las celdas locales dentro del soporte de cada nodo — el propio
comentario dice *"once: the background mesh and h_i are static"*. La malla de
fondo es estática; **los nodos no**. Después `distributeNodeForces()` evaluaba el
kernel en la posición **actual** del nodo sobre esa lista del instante de
construcción, así que a medida que la pala avanza por la malla euleriana las
celdas cacheadas se salen del soporte `2,5·h_i` y el depósito se apaga.

Medido en el fixture rotante (`tests/bladeSurfaceAFTAL`: malla uniforme de
0,1 m → soporte 0,25 m; nodos hasta 0,44 m del eje; 0,005 s = 38° por paso), la
integral volumétrica de la fuerza que recibe el flujo contra la fuerza reportada
de la pala:

| t | acimut | fuerza reportada (pala) | integral del campo (flujo) | fracción |
| --- | --- | --- | --- | --- |
| 0,005 | 38° | (2,62, 9,63, 7,57) | (−0,87, −3,20, −2,52) | **33 %** |
| 0,010 | 76° | (2,62, 2,87, 11,87) | (−0,002, −0,003, −0,011) | **0,1 %** |
| 0,015 | 115° | (2,62, −5,09, 11,13) | (0, 0, 0) | **0 %** |
| 0,020 | 153° | (2,62, −10,89, 5,60) | (0, 0, 0) | **0 %** |

Por qué esto explica todo lo medido en #5:

- **El flujo nunca recibe la carga de la pala** → no se desarrolla la inducción
  → el BEM ve un inflow sin cargar y responde con **α y `Vrel` más altos** → `cp`
  alto y creciente con el acimut (1,154 a 5,07°, contra 0,625 del ALM).
- **Todos los oráculos por CSV quedan verdes**: `moment()`, el CSV por estación y
  el volcado por nodo salen de `nodeForces_`, no del campo. Por eso el lado
  "diagnóstico" del issue cerraba bien mientras el modelo mentía.
- **El ASM sin malla nunca estuvo afectado**: recorre todas las celdas locales por
  nodo (`distributeForce` con `candidates = nullptr`), sin lista cacheada. Esa es
  la razón de que la anomalía pareciera propia del camino de superficie.
- **El paso 1 coincide con el ALM**: con el campo uniforme la carga es la misma, y
  el primer depósito todavía está casi alineado; la divergencia empieza en el
  segundo paso.

## El fix

- El **grid de bins** por rango (que depende sólo de la malla) pasa a ser la
  **única** estructura cacheada.
- `distributeNodeForce()` consulta los bins que cubren la caja de soporte del nodo
  **en su posición actual** y aplica el prefiltro S1: las celdas receptoras siguen
  al nodo.
- `h_i` (ancho del kernel y soporte de la consulta) se refresca en cada movimiento
  rígido y en la actualización de geometría FSI con `refreshNodeH()`: un `findCell`
  por nodo más **una sola reducción de lista**. El centinela por nodo al que
  reemplaza costaba un colectivo por nodo (100.236 en la superficie del IEA 15 MW),
  así que la construcción y el camino por paso salen **más baratos** que antes.
- La instrumentación D6 reporta las celdas receptoras efectivamente visitadas, no
  el tamaño de una lista estática.

Test de regresión: `test_deposit_partition_of_unity_under_rotation` (serial y
paralelo de 2 rangos) corre el fixture rotante hasta 153° de acimut y exige que la
integral de la fuerza sobre el flujo sea menos el total reportado en **cada** paso.
En rojo antes del fix (33 % / 0,1 % / 0 / 0), en verde después.

## Lo que queda

- **Rehacer la validación del ASM+mesh**: con este fix el modelo deposita lo que
  reporta, así que **ninguna corrida ASM+mesh anterior sirve** (ni las de
  `_archive`, ni las del volcado de nodos). El próximo paso es la corrida de 0,2 rev
  con la librería arreglada; si el `cp` decae como el del ALM, la anomalía de #5
  está cerrada de punta a punta.
- **La pregunta del ancho de deposición queda pospuesta**: no tiene sentido medir
  `ε` contra el ALM mientras el flujo no reciba la carga. Después de la corrida se
  sabrá si además hace falta acotar el ancho por cuerda.

## Lo que NO hay que hacer

- No volver a comparar componentes de momento entre frames distintos: fue el
  origen del "+73,3e6 / −13,9e6". El dump global lo hace innecesario.
- No citar el `cp` 1,068 ni los `cp` 0,32/1,07 de las campañas ASM+mesh anteriores:
  todas son de código previo a este fix (y el 1,068 también a `8898179`).
- No buscar la causa del `cp` en el ancho del kernel ni en el muestreo de cuerda
  antes de repetir la corrida con el depósito arreglado.
- No confiar en un oráculo que sólo lea CSV: el reporte (`nodeForces_`) y el campo
  son dos cosas distintas y pueden discrepar en silencio. El invariante es la
  integral del campo contra el total reportado, y ya es un test.
