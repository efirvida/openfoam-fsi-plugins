# Issue: ASM+mesh — el `cp` reportado es físicamente imposible

- **GitHub:** [#5](https://github.com/efirvida/openfoam-fsi-plugins/issues/5)
- **Estado:** abierto, acotado
- **Prioridad:** alta — es el modelo que el FSI va a usar
- **Creado:** 2026-10-07
- **Método:** `--model asm-mesh` (actuator surface + `surfaceGeometry`), el caso crítico del mantenedor
- **Relacionado:** `odd/tasks/iea15mw-asm-mesh-convergence.md` (el plan de convergencia),
  `odd/tasks/iea15mw-asm-cases.md`, `odd/tasks/iea15mw-references.md`

## Síntoma

El `cp` que el módulo reporta para el asm-mesh es **1,068**, plano desde el primer
paso y estable en las 20 revoluciones. **El límite de Betz es 0,593**, así que es
físicamente imposible: no es un problema de convergencia ni de transitorio, es un
error determinista en la contabilidad o en la carga.

Referencia: el ALM validado da 0,5366 y la estela libre (OLAF) 0,5312.

## Lo que YA está descartado con medición

| sospechoso | veredicto | evidencia |
| --- | --- | --- |
| **Convergencia / transitorio** | **no es** | el `cp` por revolución es plano (1,075 → 1,068 → 1,069) en las 20 rev, contra el ALM que decae de 1,040 a 0,693 |
| **Partición de unidad de la fuerza** | **correcta** | la suma de `nodeForces_` sobre 100.236 nodos da **1,0000** veces la fuerza del elemento (magnitud 911.829 vs 911.600) |
| **Agregación / doble conteo** | **correcta** | el `moment()` suma una vez por nodo (`forAll`), sin acumulación por rango |
| **Repartición por área (`patchAreaShare_`)** | **correcta** | es la que produce el 1,0000 de arriba |
| **Desincronización de acimut** | **no es** | rotar el volcado por ±5,07° no cambia el momento (invariante alrededor del eje, como debe ser) |

## La corrección importante: un artefacto MÍO en el diagnóstico

En una ronda anterior reporté que "la fuerza de los nodos tiene 871 kN a lo largo de
la envergadura, lo cual es imposible". **Eso era un artefacto de comparar frames
distintos.** La lectura de `bladeSurfaceSource::distribute`
(`bladeSurfaceSource.C:264-276`) lo aclara:

```cpp
vector F = sampler_.patchAreaShare_[i]*elements_[e].force();   // F: frame GLOBAL
sampler_.nodeForces_[i] = F;                                   // lo que se deposita y lo que usa moment()
sampler_.forces_[i] = sampler_.rhoRef()*(sampler_.bodyToGlobal().T() & F);   // <- TRANSPUESTA = frame del cuerpo
```

- `nodeForces_` (lo que se deposita en el campo y lo que suma `moment()`) está en
  **frame global** ✓ consistente con `positionsGlobal()` ✓.
- `forces_` — **lo que escribe el volcado de nodos** — está en **frame del cuerpo**
  (se le aplica la traspuesta de `bodyToGlobal()` a un vector global).

Por eso mi comparación contra los CSV de elemento (globales) mostró un vector
"rotado": **el dato del volcado es del frame del cuerpo.** El vector no está mal en
la física; está en otro sistema de referencia.

**Lección operativa**: el volcado de nodos no sirve para comparar contra los CSV de
elemento sin rotarlo. Para el próximo chequeo hay que volcar `nodeForces_`
(el global), no `forces_`.

## Lo que queda abierto, y es UN chequeo

Con la fuerza y la repartición verificadas, y con `moment()` usando
`positionsGlobal()` + `nodeForces_` (ambos globales ✓), el único insumo sin
verificar del `cp` es **la posición global de los nodos**.

- `positionsGlobal()` se inicializa desde la malla canónica del STL
  (`placeCanonicalNodes()`) y se actualiza con cada transformación rígida que la
  pala le pasa (`rotate()`). Si esa actualización falta, se aplica dos veces, o usa
  el punto/ángulo equivocado, el **brazo de momento** sale mal — y con él el `cp`
  reportado — aunque la fuerza depositada siga siendo correcta (porque el depósito
  usa `positions_[i]` y `nodeForces_[i]`, no el brazo).
- Consecuencia: si el brazo está mal, el **campo** puede estar bien y sólo mentir el
  diagnóstico. Eso define si el asm-mesh sirve para FSI con un fix de diagnóstico o
  si hay que arreglar la física.

### Chequeo concreto

1. Volcar `positionsGlobal()` junto a `nodeForces_` (o el momento ya calculado) —
   cambio de una línea en `writeNodeCsv`, más un volcado corto de 0,2 rev (~4 min
   en la cola dev, sin `snappy` si se usa `TURBINE_SNAPPY=off`).
2. Recalcular el momento a mano y compararlo con el de los elementos.

### Criterio de aceptación (ya medido, así que es un comando)

| cantidad | ahora | debe dar |
| --- | --- | --- |
| partición de unidad | 1,0000 ✓ | 1,0000 |
| momento nodos / elementos | +73,3e6 / −13,9e6 ✗ | mismo signo, cociente ≈ 1 |
| `cp` reportado | 1,068 ✗ | dentro de 0,46–0,53 |

## Lo que NO hay que hacer

- **No correr 20 rev del asm-mesh** hasta cerrar esto: el `cp` es imposible, así que
  la cola se gasta en un resultado que no se puede citar. (Ya se cortó una vez por
  esta razón.)
- No volver a comparar el CSV de nodos contra los de elemento sin rotar el primero.
- No concluir nada de un `cp` mayor que 0,593.

## Contexto de por qué importa

El mantenedor necesita el asm-mesh para FSI. La buena noticia es que la parte
específica del modelo de superficie —la repartición de la fuerza del elemento sobre
los nodos de la malla importada— está **verificada al cuarto decimal**. Lo que queda
es acotar si el defecto toca el campo (malo) o sólo el diagnóstico del torque
(arreglable). Eso es una sesión de lectura de código más un volcado corto.
