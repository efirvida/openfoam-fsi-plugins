# IEA 15 MW — serie de convergencia del ALM (malla y paso de tiempo)

- **Estado:** corriendo en **paralelo**, un job por fase (`11610253` M1, `11610254`
  M2, `11610255` M3, `11610256` M4, `11610257` M5); run dirs
  `runs/iea15mw-mconv-*`
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

**Modo de envío.** Las fases son independientes (cada una con su run dir, sin
dependencias), así que van como **jobs separados en paralelo**
(`TURBINE_MCONV_PHASE=M1..M5`, un `sbatch --time=` por fase): el wall clock pasa a
ser el de la fase más larga en vez de la suma, y cada fase sobrevive o se reintenta
por su cuenta. El script también soporta el modo serie en una asignación
(`TURBINE_MCONV_PHASE=all`, el default) con guarda de tiempo por fase, como
fallback para cuando la cola está ajustada.

Los límites de pared por fase (12/20/20/72/24 h) son generosos a propósito: la
medición de M1 en vuelo (0,5 rev en 8,4 min = 3,6 rev/h contra los 7,3 rev/h del
mismo caso en la campaña) sugiere co-tenencia en los nodos, así que **los costos
de arriba pueden ser 2× optimistas**. Si una fase muere por límite, su run dir
queda resumible y se reenvía sin perder nada (el runner retoma de `latestTime` y
escribe cada 60°).

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
