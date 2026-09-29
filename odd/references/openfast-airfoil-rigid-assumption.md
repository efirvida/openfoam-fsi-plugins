# OpenFAST: cómo entra la deformación estructural en AeroDyn

Referencia consultada para decidir si el ASM de turbinesFoam puede asumir el
perfil 2D rígido (Opción A del plan `actuator-surface-fsi`).

## Fuente

- Repositorio: `https://github.com/OpenFAST/openfast` (clon local en `refs/openfast`, fuera de git)
- Commit: `2895884d2be01862173c88d70f86b358d2f1a50a` (rama `main`, 2026-03-12)
- Módulo relevante: `modules/aerodyn/src/` (AeroDyn)

## Hallazgo

**AeroDyn asume el perfil 2D rígido.** La deformación aeroelástica entra
exclusivamente como **posición + orientación + velocidad** de los nodos de la
pala. Los coeficientes aerodinámicos salen de una **tabla estática** `Cl(α)`,
`Cd(α)`, `Cm(α)` que no cambia con la deformación.

### 1. La deformación entra como orientación, no como forma

`modules/aerodyn/src/AeroDyn.f90:3769` — `TwistToeCant_FromLocalPolar` extrae
twist/toe/cant de la orientación instantánea del mesh de la pala:

```fortran
twist(j) = -thetas(3)  ! twist (including pitch and aeroelastic deformation)
```
(`AeroDyn.f90:3782`)

`modules/aerodyn/src/AeroDyn.f90:3576` — ese twist se pasa a BEM como el
ángulo local de la sección:

```fortran
m%BEMT_u(indx)%theta(j,k) = thetaBladeNds(j,k) ! local pitch + twist (aerodynamic + elastic) angle of the jth node in the kth blade
```

Es decir: la deformación elástica se representa como un cambio de ángulo
local y de posición del nodo, **no** como un cambio de la geometría del perfil.

### 2. Los coeficientes salen de una tabla estática de α (y opcionalmente Re)

`modules/aerodyn/src/AirfoilInfo.f90:1790`:

```fortran
subroutine AFI_ComputeAirfoilCoefs( AOA, Re, UserProp, p, AFI_interp, errStat, errMsg )
   real(ReKi), intent(in   ) :: AOA           ! ángulo de ataque
   real(ReKi), intent(in   ) :: Re            ! Reynolds
   real(ReKi), intent(in   ) :: UserProp      ! propiedad de control del usuario
```

Invocada desde `modules/aerodyn/src/BEMT.f90:1373`:

```fortran
call AFI_ComputeAirfoilCoefs( y%AOA(i,j), y%Re(i,j), u%UserProp(i,j), AFInfo(p%AFindx(i,j)), AFI_interp, ...)
```

El `y%AOA` se calcula del inflow local y del `theta` (que incluye la
deformación elástica). No hay dependencia de la forma del perfil deformado.

### 3. La forma del perfil no se usa para aerodinámica

- `AirfoilInfo.f90:441`: *"NonDimArea is currently unused by AirfoilInfo or codes using AirfoilInfo."*
- `docs/source/user/aerodyn/input.rst:666`: *"The airfoil shape is currently unused by AeroDyn, but when AeroDyn is coupled to OpenFAST, the airfoil shape will be used by OpenFAST for blade surface visualization when enabled."*

### 4. Mecanismo de tablas múltiples (segunda variable de interpolación)

`docs/source/user/aerodyn/input.rst:681` y `:868`:

- `AFTabMod = 1`: tabla 1D sólo en α (toma la primera tabla)
- `AFTabMod = 2`: tablas 2D en α y `Re`
- `AFTabMod = 3`: tablas 2D en α y `UserProp` (propiedad de control definida por el usuario)

Nota de la doc (`input.rst:877`): *"OpenFAST currently sets the UserProp input value to 0 unless the DLL controller is used and sets the value, so using this feature may require a code change."*

## Conclusión para nuestro diseño

La **Opción A** (perfil 2D rígido, deformación rígida de secciones) es
exactamente el modelo que usa OpenFAST/AeroDyn, la referencia canónica del
dominio. Queda respaldada por el código fuente, no por memoria.

Además, la Opción B (tablas por estado de deformación) tiene un precedente
directo en el propio AeroDyn: el mecanismo `AFTabMod = 3` (`UserProp`) permite
tablas indexadas por una segunda variable de control. Es el camino natural si
en el futuro se quiere indexar polar por un parámetro de deformación.
