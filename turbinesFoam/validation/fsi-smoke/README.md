# ASM FSI smoke test

Minimal two-participant harness to exercise the turbinesFoam actuator-surface
FSI provider end to end, before the real structural solver is wired in.

```
Fluid  = OpenFOAM (Phase VI ASM-MESH base case) + precice-openfoam-adapter
Solid  = dummy-solid (mock structural participant, spring law)
```

The interface is the imported blade point cloud. The fluid publishes the
aerodynamic `Force` (global frame) and reads `Displacement`; the dummy applies
`u = k * F` (clamped) and returns it on the same vertices.

This is a **behaviour** test: it verifies that the point cloud registers, the
forces are written, the displacements are read and applied, and the coupling is
stable. It is not a validation of the structural response.

## Layout

```
precice-config.xml          two participants, nearest-neighbor mapping
dummy-solid/
    solverdummy.cpp         mock structural participant (preCICE)
    build.sh                build with GCC 14 (matching libstdc++)
tools/
    stl_vertices.py         unique binary-STL vertices -> coordinates file
scripts/                    (added with the case wiring)
```

## Build the dummy

```sh
cd dummy-solid && ./build.sh
```

preCICE lives in the project venv and is built with GCC 14; the system `g++`
(8.5) cannot link it. `build.sh` defaults to `/scratch/app/gcc/14.2.0/bin/g++`
and `~/venv`; override `GXX`, `VENV`, `GCC_LIB` if needed.

## Interface coordinates

The dummy must share the fluid point cloud. Extract it from the same STL the
actuator surface reads:

```sh
python3 tools/stl_vertices.py \
    ../../geometry/stl/phaseVI_blade.stl \
    runs/<id>/solid-coords.dat
```

The preCICE nearest-neighbor mapping only needs the coordinates (order is
irrelevant), so the fluid and the solid may differ in vertex count; using the
same STL gives an exact 1:1 cloud.

## Case wiring (fluid side)

On top of the rendered ASM-MESH base case:

1. `system/fvOptions`: add the `fsi` block to the blade subdictionary
   (`blade1`; `blade2` inherits with `$blade1`, so give the second blade
   distinct field names or disable it for a single-cloud test):

   ```
   fsi
   {
       coordinateField     surfaceCoords;
       forceField          surfaceForces;
       displacementField   surfaceDisplacement;
   }
   ```

2. `system/preciceDict`:

   ```
   preciceConfig "precice-config.xml";
   participant   Fluid;
   modules       (generic);

   interfaces
   {
       ActuatorSurface
       {
           mesh            Fluid-Mesh;
           locations       pointCloud;
           coordinateField surfaceCoords;

           writeData
           (
               Force
               {
                   name        Force;
                   solver_name surfaceForces;
               }
           );
           readData
           (
               Displacement
               {
                   name        Displacement;
                   solver_name surfaceDisplacement;
               }
           );
       };
   };
   ```

   `locations pointCloud` + the `generic` module are enough: the FSI module is
   not required for a point-cloud interface.

3. `system/controlDict`: load the adapter and add the function object:

   ```
   libs
   (
       "libturbinesFoam.so"
       "libpreciceAdapterFunctionObject.so"
   );

   functions
   {
       preCICE_Adapter
       {
           type preciceAdapterFunctionObject;
       }
   }
   ```

## Run

Launch the two participants concurrently (the adapter waits for the solid). On
the development queue, run both in a single allocation: the OpenFOAM solver in
the background and the dummy in the foreground, both writing to the same
`precice-config.xml`.

See `scripts/` for the SLURM driver.
