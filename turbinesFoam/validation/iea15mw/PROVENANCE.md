# Provenance — IEA 15-240-RWT case geometry and polars

All source files below are **read-only inputs**. Nothing under the input trees
was modified; the committed geometry table and polars are derived from them.

## Sources

| Source | Local path (not committed) | sha256 |
|---|---|---|
| IEA 15-240-RWT WindIO definition (sim root, *modified* copy) | `/scratch/leahk/eduardo.donestevez/IEA-15-240-RWT.yaml` | `4b9d1afbe6449d57335a253b31e7124909c6c405c2519d86ae183c33e5f7786b` |
| IEA 15-240-RWT WindIO definition (repo ontology, **authoritative**) | `/scratch/leahk/eduardo.donestevez/IEA-15-240-RWT/WT_Ontology/IEA-15-240-RWT.yaml` | `af51499e4d4b35293f9c6bca7701a9af6df0b3884c532891b1cc133efd420978` |
| AeroDyn15 blade table (chord/twist/span authority) | `/scratch/leahk/eduardo.donestevez/IEA-15-240-RWT/OpenFAST/IEA-15-240-RWT/IEA-15-240-RWT_AeroDyn15_blade.dat` | `ed8eaaa11813946594bc791e9c808eba18d8078bf9409956814a00ba3c3ccef0` |
| 50 AirfoilInfo per-station polars | `/scratch/leahk/eduardo.donestevez/IEA-15-240-RWT/OpenFAST/IEA-15-240-RWT/Airfoils/IEA-15-240-RWT_AeroDyn15_Polar_00..49.dat` | combined `74563608b91b77dcd214c0c595e58ab75e45cf5b4ef35002e474a230f71a2b25` (sha256 of the sorted `sha256sum` list); station 30 = `b1d20cfe2d8ae485999700b7b38461da17966f639d472b0c34266bb186823cfa` |
| OpenFAST ElastoDyn (radius/`PitchAxis` cross-check) | `/scratch/leahk/eduardo.donestevez/IEA-15-240-RWT/OpenFAST/IEA-15-240-RWT-Monopile/IEA-15-240-RWT-Monopile_ElastoDyn.dat` | `be58f41b85580db71c66fc2de1eaafc768e0cb96b206d95c7a61aeaf3c48e934` |
| NREL/TP-5000-75698 (definition report) | `fem-shell/tests/IEA15MW/validation papers/75698.pdf` | `93762e252922b1e75df59a453d2c08ef3f556367adf57229bc1800a4b1b11dbd` |
| IEA-15-240-RWT_tabular.xlsx (WISDEM quasi-static) | `fem-shell/tests/IEA15MW/validation papers/github-IEA-15-240-RWT/Documentation/IEA-15-240-RWT_tabular.xlsx` | `9ed6ee219a97c443d0b900498e3ef4fefa12d855d9a7c9e4c5b9bc0702b9078a` |

The sim-root yaml is **byte-identical** (md5 `b95c6759342d1f6245be7a3a3d16128f`)
to `fem-shell/tests/IEA-15-240-RWT.yaml`. It differs from the repo ontology yaml
by the windIO-2.0 re-serialization (twist radians, `pitch_axis` added) **and** one
value: `assembly.rotor_diameter` is `242.23775645` instead of the ontology's
`241.35064632`. See `README.md` "Radius decision".

## Derivation

| Committed file | Built from | Rule |
|---|---|---|
| `data/iea15mw_blade.csv` | AeroDyn15 blade table | one row per blade node; `radius_m = HubRad + BlSpn`, `r_over_R = radius_m*cos(precone)/R_published`, `chord_mount` = section aerodynamic centre, `pitch_deg = -(twist_deg + collective)`. Emitter: `tools/blade_geometry.py`. |
| `data/polars/polar_NN.dat` | AirfoilInfo `..._Polar_NN.dat` | `Re` + `data ( (alpha Cl Cd Cm) )`; `Cm` passed through unchanged. Converter: `scripts/buildPolars.py`. |

Rebuild and staleness-check (source directories default to the paths above;
override with `IEA15MW_BLADE_FILE`, `IEA15MW_WINDIO`, `IEA15MW_AEROFOIL_DIR`):

```sh
python turbinesFoam/validation/iea15mw/tools/blade_geometry.py
python turbinesFoam/validation/iea15mw/tools/blade_geometry.py --check
python turbinesFoam/validation/iea15mw/scripts/buildPolars.py
python turbinesFoam/validation/iea15mw/scripts/buildPolars.py --check
```

## Known input limitations (not fixed here)

- `Re = 3.0e6` in every one of the 50 AirfoilInfo headers, while the WindIO
  airfoils carry per-section Re levels 3.0e6 / 8.1e6 / 1.0e7. The header Re is
  effectively nominal/collapsed; `profileData` therefore receives 3.0e6 for all
  stations. A multi-Re sensitivity arm is out of scope for P1.
- The AirfoilInfo polars are the 2-D tables, with **no** 3-D stall-delay
  correction (the WindIO sections say so explicitly). The 3-D-corrected HAWC2
  polars are a separate sensitivity file and are not used here.
