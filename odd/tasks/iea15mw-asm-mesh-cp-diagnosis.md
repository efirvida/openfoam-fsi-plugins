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

## Lo que queda abierto (follow-up, no es #5)

Cerrada la contabilidad, la anomalía **sobrevive** y ahora está localizada en las
**cargas**, no en el torque. Misma malla, mismo punto, mismo código: los 147
elementos del ASM-mesh y del ALM son **idénticos elemento a elemento** en el paso
1 (cl, α, Vrel iguales a 3 decimales) y divergen en 5° de acimut:

| t | ángulo | cp ASM-mesh | cp ALM | ratio | α @ r/R 0,57 | α ALM |
| --- | --- | --- | --- | --- | --- | --- |
| 0,00937 | 0,42° | 0,94457 | 0,94487 | 1,000 | 9,9° | 9,9° |
| 0,05622 | 2,54° | 0,58373 | 0,48536 | 1,203 | — | — |
| 0,11244 | 5,07° | 1,15437 | 0,62536 | 1,846 | 11,6–15,0° | 7,5–8,8° |

El ASM-mesh sube el α (y el `Vrel`) en vez de bajarlo con la inducción. Dos
diferencias de configuración respecto del ALM, ambas en el acoplamiento y no en
el BEM:

1. la **deposición** del ASM es `2·cbrt(V)·meshFactor` por celda, **sin cota de
   cuerda**, sobre una malla refinada por snappy en la superficie (el ALM usa
   `max(0,25c, malla)`);
2. el **muestreo** del ASM promedia 5 puntos de cuerda por interpolación puntual
   (el ALM muestrea el punto de la línea), y `velocitySampleRadius` está en 0 en
   este caso.

La nota de convergencia (`odd/tasks/iea15mw-asm-mesh-convergence.md`, Etapa 3) ya
nombra el eje correcto: el ε del ASM depende de la malla, así que el ASM+mesh
tiene un eje **espacial**, no sólo temporal. El próximo chequeo es una corrida
corta (0,2 rev) con el ancho de deposición fijado al del ALM; si el `cp` decae
como el del ALM, la causa es el ancho y la corrección es acotarlo por cuerda.

## Lo que NO hay que hacer

- No volver a comparar componentes de momento entre frames distintos: fue el
  origen del "+73,3e6 / −13,9e6". El dump global lo hace innecesario.
- No citar el `cp` 1,068: es de la campaña `asmcmp-2026-10-02` (código previo a
  `8898179`). La corrida actual arranca en 0,9446, igual que el ALM.
- No declarar resuelto #5 por el `cp`: lo resuelto es la **contabilidad**. El `cp`
  sigue alto y es una anomalía de cargas con su propio follow-up.
- No correr 20 rev del ASM+mesh hasta cerrar el ancho de deposición.
