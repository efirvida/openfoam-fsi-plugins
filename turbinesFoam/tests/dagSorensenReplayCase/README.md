# Dag & Sorensen replay reference case

Fixture for `turbinesFoam/tests/test_replay_dag_sorensen.py` and
`validation/phaseVI/scripts/replayDagSorensen.py validate`.

It reuses the one-blade rotor of `../tipCorrection/rotor` (6 elements, uniform
0.1 m mesh, TSR 5) and only adds the `debug true` variants of the correction:

| variant   | `epsilon`              | projection width used by the solver |
|-----------|------------------------|-------------------------------------|
| `meshEps` | 0 (mesh-based)         | 2 cbrt(V) meshFactor = 0.4 m        |
| `eps006`  | 0.06                   | 0.06 m                              |
| `off`     | correction off         | control for the first corrected step |

`./Allrun <workdir>` runs the three variants for 4 steps (needs OpenFOAM and
`libturbinesFoam.so` on `LD_LIBRARY_PATH`; use a private build, never
`$FOAM_USER_LIBBIN`) and `./collect <workdir>` copies the outputs to
`reference/` (about 100 kB). The tests read `reference/` only, so they need no
OpenFOAM. `reference/` was produced with OpenFOAM v2506, solver commit
`696473f` (source at HEAD, built in a private directory).
