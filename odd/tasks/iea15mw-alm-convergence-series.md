# IEA 15 MW — serie de convergencia del ALM (malla y paso de tiempo)

- **Estado:** corriendo — **un solo job** (`11610258`, 15 nodos, 360 tareas) con
  las fases concurrentes en dos olas; run dirs `runs/iea15mw-mconv-*` y logs por
  fase en `runs/mconv-M<k>.log`
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

**Modo de envío: un solo job, fases concurrentes en dos olas.** Las fases son
independientes (cada una con su run dir, sin consumir salida de otra), así que el
job reparte sus **15 nodos** en grupos **disjuntos** y confina el `mpirun` de cada
fase a su grupo con su propio `TURBINE_MPI_MCA`
(`--host <grupo> --map-by ppr:24:node`). Sin el `--host`, tres `mpirun`
concurrentes dentro de una misma asignación ven **toda** la asignación y
sobre-suscriben los mismos nodos: por eso el script hace un **smoke test** de
`mpirun --host` antes de arrancar y aborta con mensaje claro si el clúster no lo
permite (fallar en 10 s, no a las 20 h).

| ola | fases | rangos por fase | nodos por fase |
| --- | --- | --- | --- |
| 1 | M1 \|\| M2 \|\| M3 | 112 | 5 (24 slots/nodo, sobra el 5°) |
| 2 | M4 \|\| M5 | 168 | 7 |

Los rangos por fase son **parte de la identidad de la fase**: un caso ya
descompuesto no se puede reusar con otro número de rangos. M1/M2/M3 = 112 (M1 ya
tenía 112 con 0,5 rev escritas, así que **retoma**), M4/M5 = 168. El modo de fase
única para reenvíos puntuales es `TURBINE_MCONV_PHASE=M4` (usa toda la asignación).

**Una cola, no cinco.** Una entrada de 15 nodos de los 240 de la partición, en
vez de cinco jobs de 112 rangos cada uno. Las olas no cambian el trabajo total
mientras la asignación sea la misma; lo que cambia el reloj es el tamaño de la
asignación, y acá la concurrencia sirve para que la ola 1 corra mientras la 2
espera turno y para que un fallo no se lleve puestas las otras fases.

**Stagger de las dos castellations.** En la ola 2, M4 y M5 construyen su malla con
un `snappyHexMesh` **serie** cuyo pico cae en un nodo (15,5 GB para los 11,6 M de
celdas), y el script de batch corre en un solo nodo: **M5 espera a que M4 termine
su malla** (se detecta por `log.topoSet`) para que los dos picos no se solapen. En
la ola 1 hay una sola fase castellated, así que no hace falta.

Estimación de reloj con la tasa medida en vuelo (3,6 rev/h en medium a 112
rangos, la mitad de lo que dio el mismo caso en la campaña por co-tenencia de
nodos): ola 1 ≈ 12 h (el polo es M2, la malla fine) y ola 2 ≈ 13-26 h según cuánto
pese M4 a 168 rangos. Límite pedido: **48 h**. Si una fase muere, su run dir queda
resumible y se reenvía sola con `TURBINE_MCONV_PHASE=<fase>`.

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
