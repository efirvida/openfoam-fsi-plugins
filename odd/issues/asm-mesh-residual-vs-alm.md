# Issue: ASM+mesh — el ~10 % que queda contra el ALM (malla, muestreo o ancho de deposición)

- **GitHub:** [#9](https://github.com/efirvida/openfoam-fsi-plugins/issues/9)
- **Estado:** abierto, acotado
- **Prioridad:** media — el modelo ya deposita lo que reporta; esto es calibración,
  no correctitud
- **Creado:** 2026-10-07
- **Método:** `--model alm` / `asm` / `asm-mesh` con `--snappy on` para los tres
  (una sola malla), 0,2 rev por modelo
- **Relacionado:** [#5](https://github.com/efirvida/openfoam-fsi-plugins/issues/5)
  (cerrado por el bug del depósito), `odd/tasks/iea15mw-asm-mesh-cp-diagnosis.md`,
  `odd/tasks/iea15mw-asm-mesh-convergence.md` (Etapa 3),
  `scripts/slurm/asmcmp.slurm`

## Síntoma

Con el fix del depósito (`5026c97`), a 0,2 rev el ASM+mesh queda **por debajo**
del ALM, con un offset estable:

| acimut | cp ASM+mesh | cp ALM | ratio | ct ratio | cd ratio |
| --- | --- | --- | --- | --- | --- |
| 0,42° | 0,9446 | 0,9449 | 1,000 | 1,000 | 1,000 |
| 2,11° | 0,4328 | 0,4554 | 0,950 | 0,950 | — |
| 5,07° | 0,5563 | 0,6254 | 0,890 | 0,890 | 0,857 |
| 19,87° | 0,8150 | 0,8953 | 0,910 | 0,910 | 0,892 |
| 44,80° | 0,8706 | 0,9834 | 0,885 | 0,885 | — |
| 71,01° | 0,8828 | 1,0117 | 0,873 | 0,873 | 0,899 |

Que `cp`, `ct` y `cd` tengan **el mismo offset** es la firma de una diferencia de
**carga**, no de un brazo de momento ni de una normalización.

## Lo que ya está descartado

- **El brazo de momento**: cociente de torque nodos/elementos 1,0019 (t=0,00937) y
  1,0026 (t=0,11244), con el frame del cuerpo reconstruido y validado porque
  reproduce el vector de fuerza con error 0,0.
- **La partición de unidad**: exacta.
- **El depósito**: el flujo recibe la carga — `test_deposit_partition_of_unity_under_rotation`
  (serial y paralelo, hasta 153° de acimut) exige la igualdad en cada paso, y con
  el fix el `cp` dejó de divergir.
- **La contabilidad del reporte**: `moment()` y los CSV salen de `nodeForces_`.

## Hipótesis vivas, en orden de sospecha

1. **La malla.** El ASM+mesh corre sobre la superficie refinada por snappy; el ALM
   del comparador corre sobre otra malla. Es el confound clásico de la campaña:
   los tres modelos nunca compartieron la malla en los runs que estoy usando.
2. **El muestreo.** `actuatorSurfaceElement::calculateInflowVelocity()` promedia
   5 puntos de cuerda por interpolación puntual; el ALM muestrea el punto de la
   línea (`velocitySampleRadius` está en 0 en este caso, así que el ALM tampoco
   promedia en anillo). Es una diferencia de velocidad efectiva, no de BEM.
3. **El momento de cabeceo.** `bladeSurfaceSource::moment()` suma **sólo**
   `Σ X_i × F_i`: no incluye el término `0,5·c²·span·Cm·|Vrel|²·spanDirection` que
   `actuatorLineElement::moment()` **sí** suma. Con precono 4° el producto con el
   eje del rotor es `sin(4°) ≈ 0,07`, así que es chico pero no nulo. Es
   deliberado por consistencia con el campo (la carga depositada es sólo fuerza),
   pero explica una parte del offset entre ALM y ASM.
4. **El ancho de deposición.** El ASM usa `2,5·h` con `h = cbrt(V_cell)`, **sin
   cota de cuerda**; el ALM usa `max(0,25c, malla)`.

## Defecto lateral encontrado (no arreglado, necesita decisión)

`bladeSurfaceSampler::distributeNodeForce()` **ignora `meshFactor_`** en el camino
por defecto: el kernel coseno se evalúa como `kernel(dx/h)·kernel(dy/h)·kernel(dz/h)`
con `h` fijo, mientras que `eps = 2·h·meshFactor_` sólo entra en la rama gaussiana.
Consecuencia: `--mesh-factor` (y el `GaussianCoeffs/meshFactor` que renderiza el
generador en cada perfil) **no tiene ningún efecto sobre la deposición del
ASM+mesh** con el kernel por defecto. El knob que se documentó como "ancho del
kernel de fuerza" es inerte justo en el modelo que importa. Dos salidas, y hay
que elegir una:

- honrarlo también en el coseno (`h·meshFactor`, con `meshFactor 1` = el kernel
  del paper, así el default no cambia); o
- documentarlo como exclusivo de la rama gaussiana y sacarlo del camino ASM+mesh
  para no prometer lo que no hace.

## Chequeo concreto (3 corridas cortas + 1 ablativa)

1. Trío `alm`/`asm`/`asm-mesh` **sobre la misma malla** (`--snappy on` para los
   tres, como ya hace `scripts/slurm/asmcmp.slurm`), 0,2 rev cada uno.
2. Comparar por acimut: `cp`, `ct`, `cd` y el α spanwise por banda.
3. Discriminación: si **`asm` (sin superficie) también queda ~10 % abajo**, la
   causa es la malla o el muestreo (comparten el camino de BEM y el muestreo en
   cuerda, y sólo difieren en cómo proyectan). Si **sólo `asm-mesh` queda abajo**,
   es el ancho de deposición o el momento de cabeceo, y se separan con un
   `kernel gaussian` de ancho calibrado (D7) y/o con el término de cabeceo.

**Criterio de aceptación:** el trío sobre la misma malla con `cp`/`ct`/`cd` dentro
del 2 % entre los tres modelos, o la causa identificada con una corrida ablativa
por hipótesis.

## Lo que NO hay que hacer

- No tocar el ancho del kernel para "arreglar" el nivel antes de saber si la
  diferencia está en la malla: es exactamente el atajo que llevó a buscar el `cp`
  en el ε cuando el problema era que la carga no llegaba al flujo.
- No citar ninguna corrida ASM+mesh anterior a `5026c97`: su flujo nunca recibió
  la carga de la pala.
- No correr 40 rev hasta que el trío sobre la misma malla cierre: si el 10 % es
  malla, la curva de convergencia del ASM+mesh estaría midiendo otra cosa.
