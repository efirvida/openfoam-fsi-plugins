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
