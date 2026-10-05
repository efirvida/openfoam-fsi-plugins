# IEA 15 MW — esquema de muestreo del ALM (la inconsistencia que queda)

- **Estado:** diseño listo, no implementado
- **Contexto:** `odd/tasks/iea15mw-validation-campaign.md` (Fase 3),
  `odd/tasks/iea15mw-references.md` (registro de referencias)

## El problema

El ALM corre **+0,81° de α** sobre CCBlade (media en r/R 0,3-0,9, a 20 rev
convergidas) y su inducción axial implícita es 0,25 contra 0,31 del BEM. El ASM,
sobre la misma malla, dominio y punto, corre **+0,23°**. Ya quedaron refutados con
mediciones: los polares (bug real, corregido, no cerró el α), el ancho de kernel ε
(apretarlo a 0,22c lo empeoró: +0,95 → +1,86), la geometría y el mapeo
elemento→polar.

## El hallazgo: el knob ya está en el código

`turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorLineElement.C`:

```cpp
 99:  dict_.lookup("velocitySampleRadius") >> velocitySampleRadius_;
100:  dict_.lookup("nVelocitySamples") >> nVelocitySamples_;
...
703:  if (velocitySampleRadius_ <= 0.0)        // <- rama de muestreo puntual (la actual)
...
722:  scalar sampleRadius = calcProjectionEpsilon()*velocitySampleRadius_;
729:  for (label point = 0; point < nVelocitySamples_; point++)   // anillo de N muestras
770:  inflowVelocity_ = 1.0/nVelocitySamples_ * velocitySum;     // promedio
```

Dos cosas decisivas:

1. **El radio se expresa YA en unidades de ε**: `sampleRadius = calcProjectionEpsilon() * velocitySampleRadius_`.
2. `velocitySampleRadius <= 0` → muestreo puntual (lo que usamos hoy; el caso
   renderizado **no escribe ninguna de las dos claves**), y `> 0` → **promedio en
   anillo de N puntos a esa distancia**.

## Lo que pide la literatura (Zormpa et al. 2024, Wind Energy)

La muestra tiene que caer **fuera de la gaussiana de fuerza**: `rs/rg = 1,1` con
`rg = 3ε`. O sea **`rs = 3,3ε`**. Muestrear dentro (lo nuestro) es lo que infla el
α, y el error **crece al concentrar más la fuerza** — exactamente lo que medimos al
bajar ε a 0,5.

Con ε = 1,89 m en el disco: `rs = 3,3 · 1,89 ≈ 6,2 m`.

## El cambio propuesto (configuración, no código)

1. `generate_case.py`: renderizar `velocitySampleRadius` y `nVelocitySamples` en
   los dicts de pala, con **default 0 / 1 = comportamiento actual byte-idéntico**
   (rama puntual, `actuatorLineElement.C:703`), como se hizo con `meshFactor` y
   `liftReCorrExp`. Flag `--velocity-sample-radius` / `--n-velocity-samples` y
   puente de entorno mientras el runner no se pueda editar.
2. Una corrida con `velocitySampleRadius 3.3` y `nVelocitySamples 16` (12 rev).
3. Criterio: el Δα tiene que caer de **+0,81° hacia ≤ +0,3°** (el nivel del ASM) y
   el `c_t` de **1,39 hacia ≤ 1,25**.

## Por qué esto reemplaza el trabajo de C++ que se había propuesto

El explore propuso agregar una clave nueva (`samplingModel point|lineAverage|…`)
con una rama en `actuatorLineElement.C:642`. **Es innecesario**: el promedio en
anillo ya existe, ya está probado en el árbol y su radio ya está normalizado por ε.
Lo único que falta es escribirlo en el diccionario.

## Cuidados

- **MPI**: hay un test de invariancia paralela en la suite (`tipCorrection`) que
  conviene extender al muestreo antes de confiar en la corrida.
- **Costo**: N interpolaciones por elemento y por paso; N = 16 es barato.
- **El ASM no se toca**: su `calculateInflowVelocity` es un override que promedia
  sobre la cuerda; la clave nueva no lo afecta. Si el ASM ya tiene el α bueno, esto
  lo deja como está.
- **Pendiente de verificar en el árbol**: de dónde lee esas claves cada pala (el
  `read()` del elemento, línea 99) y si el turbine source las inyecta con default
  cuando faltan — el caso renderizado no las escribe y las corridas no fallan, así
  que hay un default inyectado en algún lado y hay que encontrarlo antes de
  renderizar las claves.
