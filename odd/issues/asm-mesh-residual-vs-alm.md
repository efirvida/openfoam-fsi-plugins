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

## Es formulación, no implementación (medido, sin corridas nuevas)

Los tríos `asmcmp` ya corrieron los modelos sobre la **misma malla**, así que el
par `alm`/`asm` —sin superficie— aísla el camino de elementos:

| batch (misma malla, mismos polares) | rev 1 | rev 10 | rev 20 |
| --- | --- | --- | --- |
| `_archive/2026-10-07-historicas` asm/alm | 0,871 | 0,899 | **0,903** |
| `_archive/asmcmp-2026-10-02-...` asm/alm | 0,913 | 0,932 | — |

`cp` y `ct` se mueven **juntos** en las dos mediciones. El ASM **sin
`surfaceGeometry`** ya da 0,87-0,93 del ALM durante 20 revoluciones: el depósito de
superficie queda **excluido** como origen del offset. Y en ese par las únicas
diferencias son las dos que el modelo de superficie del paper introduce en el
elemento — el **muestreo promediado en cuerda** (5 puntos, centrados en el 50 %,
contra el punto único del `chordMount`) y la **proyección en 5 franjas** con
`force/nChordwise` cada una —, así que por construcción el offset sale de ahí.

Del lado del depósito, los invariantes están exactos y son tests (el campo recibe
la fuerza reportada a cualquier acimut, serial y paralelo; partición de unidad
exacta; momento de nodos = de elementos al 0,2 %; la cadena de CSV cierra), y el
ASM+mesh arreglado cae en la **misma banda** que el ASM puro. Un bug de
implementación se manifiesta como un invariante roto: no hay ninguno.

Mecanismo, a rev 20 sobre la misma malla: **Δα medio −0,325°** (hasta −0,65° en
0,4-0,6 r/R, ≈0 en la punta) con `|Vrel|` casi intacto (−0,1 %). La carga amplifica
el α: ~30 % por grado.

## "No es un bug" no es "está bien"

Contra las referencias del repo (OLAF estela libre **0,5312**; un ALM
independiente 0,527; CCBlade/BEM 0,4910), el ALM validado da 0,5366 (**+1,0 %**).
Un offset de −7…−13 % dejaría al ASM en 0,47-0,50, o sea **−6 % a −11 % por debajo
de la estela libre**. Salvedad que hay que respetar: los dos ALM comparadores de
arriba **no son el ALM validado** (terminan en 0,70-0,77 contra 0,5366), así que
proyectar el ratio sobre 0,5366 es extrapolación, no medición.

## Estado de cada mecanismo

1. **El muestreo promediado en cuerda + la proyección en franjas**: **confirmado
   como el origen** del offset de nivel (el ASM sin superficie lo muestra y en ese
   par sólo difieren esas dos cosas).
2. **La malla**: no explica el nivel (el offset aparece en pares que comparten
   malla). Queda descartarla también en la configuración validada.
3. **El momento de cabeceo**: descartado por orden de magnitud. Techo generoso:
   `0,5·c²·span·Cm·|Vrel|²·sin(precono)` ≈ 1,8e3 N·m por elemento × 147 × 0,07 ≈
   2e4 N·m, contra un torque de referencia de 2,23e7 N·m → **≈0,1 %**.
4. **El ancho de deposición**: descartado como origen del offset (el ASM sin
   superficie usa el mismo ε del ALM y muestra el mismo offset; el ASM+mesh
   arreglado cae en la misma banda). Sigue siendo una perilla legítima de
   calibración, no la causa.

## El chequeo que lo cierra

El trío en la **configuración validada** sobre **una sola malla** (`alm`/`asm`/
`asm-mesh` con `--snappy on` para los tres, polares corregidos, end effects como
el run validado), 0,2 rev, contra 0,5312:

- si el ASM conserva su −10 % contra el **ALM validado**, es un sesgo de
  formulación a calibrar, con las perillas ya expuestas (`--n-chordwise` hoy 5,
  `--velocity-sample-radius` hoy 0 o sea muestreo puntual crudo en los dos
  modelos, y el ancho de deposición);
- si el gap se cierra, el −10 % era artefacto de configuración (mallas y ajustes
  distintos) y no hay nada que calibrar.

Es el diseño de `scripts/slurm/asmcmp.slurm`; con 0,2 rev por modelo alcanza para
decidir.

## Hipótesis originales (superadas por lo medido arriba)

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

## Estado tras el congelamiento (2026-10-09)

La plataforma quedó congelada y validada (`odd/tasks/iea15mw-platform-freeze.md`):
snappy L2 (2 363 760 celdas), 96 rangos, `dt` 0,0187 s, 20 revoluciones, `cp`
convergido **0,534** (+0,6 % contra la estela libre de OLAF, +8,8 % contra
CCBlade/BEM), con los dos ejes cerrados (malla +0,14 %, tiempo −0,13 %).

Publicado en el issue #9 (comentario `issuecomment-6086582709`):

- el par ALM/ASM **0,871-0,903 no es la respuesta** — otra malla, otro argumento
  de muestreo y 0,2 rev: hay que rehacerlo sobre la plataforma con las mismas 20
  revoluciones que el ALM;
- los dos residuos de modelo quedan caracterizados por separado: el **exceso
  tangencial outboard** contra el BEM (+10-13 %, creciente hacia afuera) y el
  **déficit inboard** contra el CFD (+49 a +71 % en los pares de papers), que el
  `rotationalAugmentation` con coeficientes unitarios no arregla (+0,74 % en `cp`,
  casi todo en la raíz en pérdida profunda).

Siguiente paso registrado en el issue: ASM sobre la misma malla, 96 rangos y 20
revoluciones, verificando primero el test de partición de la unidad del depósito
(serial y 2 rangos), obligatorio desde `5026c97`.
