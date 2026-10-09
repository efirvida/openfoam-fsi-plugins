# IEA 15 MW — serie de convergencia del ALM (malla y paso de tiempo)

- **Estado:** **etapa 1** enviada (job `11610406`, 112 rangos / 5 nodos, serie
  `M1 → M2 → M3`); **M4 y M5 frenados** a propósito. Run dirs
  `runs/iea15mw-mconv-*`, logs por fase en `runs/mconv-M<k>.log`
- **Creado:** 2026-10-07
- **Relacionado:** `odd/tasks/iea15mw-references.md` (configuración validada y el
  eje de malla medido), `odd/issues/asm-mesh-residual-vs-alm.md` (issue #9),
  `odd/tasks/iea15mw-validation-campaign.md` (Fase B/D),
  `scripts/slurm/mesh-convergence.slurm`

## Por qué una serie y no "una malla más"

`generate_case.delta_t()` deriva el paso de la celda más fina que ve el rotor
(`0,95·celda/velocidad de punta`). Eso es correcto — el paso derivado mantiene el
desplazamiento de punta por paso por debajo de una celda, y su docstring registra
qué pasa si no (Courant 4,19 y cargas salvajes) — pero significa que **refinar la
malla y refinar el tiempo son la misma palanca**. Una serie de mallas a sus
propios pasos mueve los dos ejes a la vez.

Los tres puntos que hay hoy lo muestran:

| malla | celda más fina | `deltaT` | pasos/rev | rev | cp | deriva/rev |
| --- | --- | --- | --- | --- | --- | --- |
| coarse D/32 | 7,50 m | 0,0750 | 106 | 20 | 0,5591 | −0,057 % |
| medium D/48 | 4,98 m | 0,0498 | 160 | 12 | 0,5490 | **−0,239 %** |
| castellated L3 | 0,94 m | 0,00937 | 852 | 12 | 0,5370 | +0,063 % |
| *referencia OLAF* | — | — | — | 15 | *0,5312* | — |

Dos defectos: las caídas **no se achican** al refinar (−0,0101 y después −0,0121
sobre una malla 5,3× más fina: ningún `p` único ajusta `cp(h) = cp∞ + C·h^p`, o
sea no hay extrapolación de Richardson creíble), y los puntos **no están igual de
converjidos en el tiempo** (la deriva del medium es 4× la de sus vecinos, así que
a 12 revs está ~2 % arriba de su asíntota). La serie está confundida con el
transitorio.

## El diseño (fases de la más barata a la más cara)

Configuración **idéntica** en todas: polares con `liftReCorrExp 0`,
`velocitySampleRadius 3.3`, `nVelocitySamples 16`, `endEffects Glauert` con
tip+root on, dominio 3D/7D/±3D, 112 rangos, `writeInterval` cada 60°. Sólo cambia
la resolución (y en M5 sólo el paso, con la malla fija).

| fase | malla | celda | paso | pasos/rev | rev | costo | para qué |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M1 | medium D/48 | 4,98 m | 0,0498 | 160 | 20 | ~3-6 h | repone el punto medium a un horizonte convergido |
| M2 | fine uniforme D/64 | 3,75 m | 0,0375 | 213 | 20 | ~6-10 h | segunda familia de refinamiento (global, no el disco local) |
| M3 | snappy L2 | 1,87 m | 0,0187 | 427 | 20 | ~6-10 h | puente entre la fine uniforme y la castellated |
| M4 | snappy L3 | 0,94 m | 0,00937 | 852 | 20 | ~26-50 h | donde vive el 0,5366 del registro (y chequeo de reproducibilidad) |
| M5 | snappy L3, `--dt-factor 0.5` | 0,94 m | 0,004685 | 1704 | 8 | ~10-20 h | **eje temporal a malla fija**, contra la ventana de 8 revs de M4 |

M1..M3 + el punto coarse que ya existe (`runs/iea15mw-alm-20rev`, misma config,
20 rev) completan una serie espacial de **cuatro puntos**. M4 agrega el punto fino
y M5 el chequeo temporal.

## Alcance: dos etapas, la segunda condicionada

**Etapa 1 — el eje espacial, TAMIZ a 4 revoluciones.** Decisión del usuario
(2026-10-07): para *decidir qué malla* no hace falta buscar la convergencia
temporal completa. El objetivo es medir **cuánto cambia el comportamiento del rotor
con la malla**, no validar; una vez que la curva diga dónde el resultado deja de
moverse, **ese** es el número de producción y se corre a horizonte largo. Con 4
revs cada punto cuesta ~5× menos que a 20 y entra en cualquier ventana de cola.

Caveats que van con el tamiz, porque el transitorio no es chico a los 4 revs:

1. **El horizonte tiene que ser común** a todas las mallas (4 revs exactas), y hay
   que extraer la *misma* ventana de los runs que ya existen (el coarse está a 20
   rev) para que la comparación sea manzana con manzana.
2. **Reportar la deriva por revolución junto al valor**: a los 4 revs el coarse
   deriva del orden del % por vuelta contra pasos de malla del ~2 %, o sea **la
   señal y el ruido son del mismo orden**. El espaciado entre mallas a 4 revs puede
   estar contaminado por el transitorio, así que el tamiz decide *candidatas*, no
   cierra el número.
3. **El número de producción sale de una corrida larga de la malla elegida** (no de
   esta serie), que es exactamente el plan.

M1, M2 y M3 en serie en una sola tarea, con la configuración de particionado que
salga de los estudios de escalado y de métodos (en curso), a **4 revoluciones** cada
una, más el punto coarse
que ya existe (`runs/iea15mw-alm-20rev`, misma configuración). Con cuatro puntos
se puede ajustar **un** orden `p` y ver si las cargas se asientan dentro de la
banda de referencia en vez de deambular.

| fase | malla | celda | paso | pasos/rev | rev |
| --- | --- | --- | --- | --- | --- |
| M1 | medium D/48 | 4,98 m | 0,0498 | 160 | 20 |
| M2 | fine uniforme D/64 | 3,75 m | 0,0375 | 213 | 20 |
| M3 | snappy L2 | 1,87 m | 0,0187 | 427 | 20 |

**Etapa 2 (frenada) — el eje temporal y el punto fino.** M4 (snappy L3, 0,94 m,
852 pasos/rev, donde vive el 0,5366 del registro) y M5 (L3 con `--dt-factor 0.5`,
el chequeo temporal a malla fija) están **definidas pero no se lanzan**: son la
mitad caras (~26 h y ~10 h a 112 rangos) y no tiene sentido gastar cola en ellas
hasta que la etapa 1 diga que la serie es válida. Se corren explícitamente con
`TURBINE_MCONV_PHASES=M4` (o `M5`) cuando exista el veredicto.

## Por qué 112 rangos y no una asignación grande

Medido en este clúster: cinco jobs de 112 rangos arrancaron en segundos, mientras
un job único de 360 CPUs quedó en la **posición #132 de 199 pendientes con ETA a
2 días**. No era falta de recursos totales (360 CPUs = 3 % de la máquina): los 8
nodos totalmente libres estaban en estado `plnd` — Slurm se los había reservado al
backfill de otro job pendiente — y el pedido necesitaba **15 nodos con ≥24 CPUs
libres simultáneos** mientras los 131 jobs de adelante piden 24 CPUs y entran en
cualquier fragmento. Los fragmentos se consumen en minutos (a los 15 min de ver 35
nodos con ≥24 libres, quedaban cero). Las fases de la etapa 1 son baratas: la
espera de cola las domina, así que conviene el pedido chico.

Cómo se ve la cola ahora mismo, para no volver a diagnosticarlo desde cero:

- `sequana_cpu`: **197 pendientes, 0 CPUs libres**, mi job en la posición ~#138,
  `StartTime` estimado a ~24 h.
- `sequana_cpu_dev` (tope 20 h): **5 nodos idle y 1 job pendiente**. M1/M2/M3
  entran cada una en 20 h, así que un job con slices + `requeue` — el patrón que
  la campaña ya usó en esa cola — arrancaría ya con la misma semántica (una sola
  tarea, fases en serie, `scontrol requeue` para continuar slices sin gastar
  envíos). Es la palanca si se quiere el resultado hoy en vez de mañana.

## Algoritmo de descomposición: hoy todo es scotch (pendiente)

`render_decompose_par` escribe `method scotch;` **hardcodeado** (no hay bandera) y
todos los runs de la campaña son scotch: el propio `decomposePar` lo reporta
(`Decomposition method scotch [192]`), y en la malla medium de 6,5 M de celdas
tardó 53 s en descomponer.

**Por qué importa justo acá**: la malla es un `blockMesh` **estructurado pero
graduado** (celdas no uniformes + zonas castellated). `simple`/`hierarchical`
cortan por **coordenadas**, así que en una malla estructurada suelen dar
subdominios contiguos, menos halo y mejor localidad de caché; `scotch` optimiza el
**balance del grafo** (número de celdas por subdominio) y por eso gana en mallas
irregulares o muy cargadas, a costa de un borde más irregular. Ninguno domina:
**hay que medirlo**, y hasta ahora nunca se midió.

**Cómo medirlo (siguiente paso, barato)**:

1. Exponer `--decomp-method` en el generador (con el env bridge `TURBINE_*` como
   las otras perillas; hoy es una línea fija en `render_decompose_par`), más
   `--decomp-n` para el `n (x y z)` de `simple`/`hierarchical`.
2. Comparar a **un conteo de rangos FIJO** (p. ej. 192) en vez de repetir el
   barrido entero: es más directo y mucho más barato. Un método por corrida con
   `TURBINE_SCALE_TAG=-<metodo>`, que ya separa dirs y CSV.
3. Métricas: **segundos por paso** (la misma mediana de los deltas de
   `ExecutionTime`), **celdas por rank** (el balance real), el **tiempo de
   `decomposePar`** y el **tamaño del halo** (caras de interfaz entre
   subdominios). Con eso se elige método y recién ahí se repite el barrido con el
   ganador.

Los rangos por fase son **parte de la identidad de la fase**: un caso ya
descompuesto no se reusa con otra descomposición, así que un reenvío mantiene los
112. Si una fase muere o se saltea por tiempo, su run dir queda resumible (el
runner retoma de `latestTime`, con escritura cada 60°) y se reenvía sola con
`TURBINE_MCONV_PHASES=<fase>`.

## Criterio de aceptación (escrito antes de correr)

1. **Temporal**: el `cp` de M5 contra la ventana de 8 revs de M4 difiere **menos
   de 0,5 %**. Si no, el eje temporal no está cerrado y ninguna diferencia de
   malla es interpretable todavía.
2. **Espacial**: los cinco puntos ajustan `cp(h) = cp∞ + C·h^p` con un **orden
   único** `p` (una sola recta en log-log) y las caídas sucesivas decrecen. Sólo
   entonces `cp∞` tiene error estimable.
3. **Comparación**: `cp∞` contra la banda de referencia (OLAF estela libre
   **0,5312**, ALM independiente 0,527, CCBlade/BEM **0,4910**) — no contra un
   único valor, y no a una sola resolución.
4. Si la serie **no** converge (o converge por debajo de 0,49), el "+1,0 % del ALM
   validado" queda refutado como propiedad del modelo y hay que recalibrar antes
   de comparar modelos.

## Qué NO hacer

- **No citar un valor de una sola resolución como "el ALM validado"**: a la
  resolución coarse es +5,3 % contra la estela libre, a la medium ~+2 %, a la
  castellated +1,1 %.
- **No llamar convergencia de malla a una serie que movió el paso de tiempo**, ni
  al revés. Es el defecto de los tres puntos actuales.
- **No gastar 95 h en la asíntota temporal de UNA malla** antes de cerrar el eje
  espacial: es lo que el plan de 40-60 revs compraría.
- No comparar el ASM/ASM-mesh contra el ALM en mallas distintas: el error de malla
  del propio ALM (+4 % medido entre coarse y castellated) es del mismo orden que
  el hueco que el issue #9 quiere medir.

## Planteado (no ejecutar): dispersión del rendimiento suelto

La penalidad de la colocación suelta está medida como **una comparación de dos
muestras** (una asignación suelta contra una densa: +46 % a 96-112 rangos). Alcanza
para decidir acá, pero no para publicar: no dice **cuánto varía** entre corridas
idénticas ni cuánto depende del planificador — y esa variación es justamente lo que
hizo **no monótonos** los puntos de pocos rangos (36 peor que 48 y que 24).

Diseño planteado, para la fase de análisis publicable: **K repeticiones idénticas
del mismo punto en forma suelta** (p. ej. 96 rangos = la rodilla), cada una en su run
dir, mismo código y configuración, registrando por repetición la mediana por paso,
el wall y la **colocación real** (nodos, tareas/nodo, modelo de CPU). Salidas: media
± desvío, coeficiente de variación y una regresión del costo contra el número de
nodos, para que la afirmación pase de "cuesta 46 % más" a "cuesta tanto ± tanto y
depende tanto del planificador", y para separar la FORMA de la curva del ruido.

Costo: K × ~4 min por punto (0,1 rev); con K=10 son ~40 min de cola, así que
postergarlo no cuesta nada. **No ejecutar hasta la fase publicable.** Los resultados
viven en `analysis/hpc-performance.md`, que se regenera con
`tools/plot_hpc_performance.py`.

## RESULTADO del tamiz (2026-10-08, `runs/iea15mw-screen-*`)

Los **cuatro** puntos existen y son comparables entre sí: **mismo horizonte (4 revs),
misma configuración validada, mismos 96 rangos** (`method simple`, `n (4 6 4)`). El
coarse lo produjo el propio tamiz (`m0-coarse`, job `11611018`, 12:16) porque el run
de 20 revs que se iba a usar fue borrado.

| malla | celda | cp rev1 | rev2 | rev3 | rev4 | ct rev4 | deriva/rev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| coarse D/32 | 7,50 m | 0,7582 | 0,6554 | 0,6192 | **0,6005** | 0,06738 | −3,02 % |
| medium D/48 | 4,98 m | 0,7391 | 0,6373 | 0,6031 | **0,5850** | 0,06563 | −3,00 % |
| fine D/64 | 3,75 m | 0,7312 | 0,6310 | 0,5973 | **0,5795** | 0,06501 | −2,99 % |
| snappy L2 | 1,87 m | 0,7216 | 0,6288 | 0,5955 | **0,5778** | 0,06482 | −2,98 % |

**Lo que dice el tamiz:**

1. **El eje de malla converge rápido y el orden es alto.** Escalones **−2,59 %**
   (7,50 → 4,98 m), **−0,95 %** (4,98 → 3,75 m) y **−0,29 %** (3,75 → 1,87 m):
   decrecientes y fuertemente. El ajuste `cp(h) = cp∞ + C·h^p` sobre los cuatro
   puntos da **p = 2,82**, `cp∞ = 0,5770`, rms 0,00055 — y deja el **remanente de
   malla en L2 en +0,14 %**.
2. Consecuencia: **la malla está resuelta en L2**. Ir a L3 (0,94 m) compraría
   ~0,1 % por ~50 h. Para el eje espacial, L2 es la malla de producción.
3. **Cuidado con leer ese `p` como orden espacial.** `dt` se deriva de la celda
   (`0,95·h/velocidad de punta`), así que los cuatro puntos refinan **espacio y
   tiempo juntos**: el `p` medido es el orden *efectivo* del refinamiento acoplado,
   no el del esquema en espacio. **El eje temporal no está probado** por esto.
4. **El transitorio sigue dominando**: −3,0 %/rev en las cuatro mallas, contra
   escalones de malla ≤2,6 %. A 4 revs el nivel está ~+9 % sobre la banda de
   referencia (0,5770 extrapolado contra 0,5312), que es exactamente el
   transitorio, no un sesgo de malla.

**Lo que falta para "convergida y validada"** (el objetivo declarado: la malla que
va a sostener todo lo de después): una corrida **larga en L2** hasta que la deriva
baje del criterio (<0,2 %/rev sostenido), el chequeo de **`dt/2` a esa misma malla**
(que es lo que separa el eje temporal), y recién ahí la comparación contra la banda
y el spanwise de CCBlade. Congelada la malla+configuración, se reusa para el trío
del issue #9 y para el FSI.

**Paso 1 HECHO** (`scripts/slurm/l2-long.slurm`, job `11611026`, 96 rangos;
4:04 de pared, exit 0). Extendió el caso L2 del tamiz hasta **20 revoluciones**
(las 4 del tamiz + 16 nuevas) y el resultado es el que buscabas:

| rev | cp | deriva/rev | | rev | cp | deriva/rev |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 0,7216 | — | | 12 | 0,5417 | −0,25 % |
| 2 | 0,6288 | −12,87 % | | 16 | 0,5381 | −0,12 % |
| 4 | 0,5778 | −2,98 % | | 19 | 0,5367 | −0,077 % |
| 8 | 0,5493 | −0,71 % | | **20** | **0,5363** | **−0,065 %** |

- **Eje temporal cerrado**: la deriva media en las revs 16→20 es **−0,084 %/rev**,
  y viene por debajo del 0,2 %/rev del criterio desde ~la rev 13. El `cp` de la
  última revolución completa es **0,5363** (`ct` 0,0603).
- **Validación contra la referencia numérica**: 0,5363 es **+1,0 %** de la estela
  libre de OLAF (**0,5312**), +1,8 % del ALM independiente (0,5270) y +9,2 % del
  CCBlade/BEM (0,4910). Es exactamente la relación que la campaña había llamado
  "validado" (0,5366 = +1,0 %, medido en otra malla), ahora sobre una malla cuyo
  eje espacial está cerrado (remanente +0,14 %).

**Así que la plataforma queda definida**: **L2 (celda 1,87 m), 96 rangos,
configuración congelada, horizonte 20 revs** → `cp = 0,5363`, +1,0 % contra la
estela libre, con los dos ejes argumentados. El límite de poder de la validación
sigue siendo la **banda de referencia** (0,4910-0,5312 = 8 % de ancho): el integral
cae dentro; el discriminador fino es el spanwise de CCBlade, que falta correr.

**Trampa operativa que hay que recordar**: **retomar un run parte los CSV de
`postProcessing` en una carpeta nueva con el `timeName` de arranque**. Este run
arrancó en `31.9209` (las 4 revs del tamiz), así que sus 16 revs nuevas quedaron en
`postProcessing/turbines/31.9209/turbine.csv` y no en `.../0/`. Cualquier análisis
que lea una sola carpeta ve media historia (y a mí me pasó). Hay que **unir todas
las carpetas** de `<owner>` o consolidarlas.

**Lo que queda para cerrarla del todo**: el chequeo **`dt/2` a L2 continuando desde
el estado convergido** (no re-corriendo 20 revs: seguir ~5 revs con `dt/2` y exigir
que el `cp` no se mueva; ~2-3 h) — es lo que separa el eje temporal del espacial
porque `dt` se deriva de la celda; y el **spanwise** contra CCBlade, que se hace sin
cola.
3. Consecuencia práctica: **el punto L3 (26 h) probablemente no haga falta para la
   pregunta de malla** (la tendencia ya está aplanada), y la comparación de modelos
   del issue #9 se puede hacer en la malla barata (D/64 o L2) porque el sesgo de
   malla es ≲1 %.

**Corrección de un número mío.** El "+4,1 % entre coarse y castellated" que escribí
en `iea15mw-references.md` salió de comparar puntos con **derivas distintas** (el
medium a 12 revs derivaba −0,24 %/rev contra −0,06 % del coarse): estaba
contaminado por el transitorio, que es exactamente el defecto que este tamiz
corrige. A ventana común el efecto de malla es **≲1 %**, no 4 %. Los números
viejos no deben citarse.

**Dos problemas de datos que el tamiz dejó a la vista:**

- `runs/iea15mw-alm-20rev` (el coarse de 20 revs, la referencia de la banda y el
  origen del "cp 0,5591" y del 0,5366 castellated) **fue borrado del disco** por
  una limpieza: no está en `runs/` ni en `_archive/`. Sus valores sobreviven sólo
  en el registro. Para completar una serie de cuatro puntos hay que **volver a
  correr el coarse a 4 revs**, que es barato (~3 min a 96 rangos).
- El job `11611009` re-corrió el tamiz sobre casos que **ya estaban en su
  `endTime`**: el solver no avanza, el guard del runner lo reporta como
  `FALLO ... without advancing` y el job sale con error. No es un crash, pero el
  exit status miente. Si se reenvía, hay que borrar el `processor*/` o dejar
  `latest=0` para que el run sea real.
