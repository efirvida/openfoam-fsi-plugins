# Nacelle on/off study (Phase VI and IEA 15 MW)

Empirical test of whether the nacelle explains the root error of Phase VI (CN +13.6 % at r/R 0.30, 7 m/s, all methods).
Branch: `fix/compare-phasevi-surface-stations`. No `libturbinesFoam` rebuild. Do not edit existing scripts' behaviour by default.

## Specs
- S1: "puedes evaluar los resultados de la iea15MW contra simulaciones numericas ahi donde esta la gondola ... apagandola en las configuraciones de los casos y ver su efecto"
- S2: "para el caso de IEA si las simulaciones no tienen gondola, entonces podriamos ponerse, y ver la diferencia ... eso solo una evaluacion digamos que empirica."
- S3: "entonces si, haz las dos cosas en paralelo" (Phase VI nacelle on/off from the NREL geometry, and IEA nacelle on/off).
- S4: Phase VI nacelle geometry (NREL/TP-500-29955 Fig. 8): length 1.79 + 1.469 m = 3.26 m about the tower axis, width 0.91 m (36 in); approximated as a cylinder R = 0.455 m with a rounded tail (`validation/tools/make_nacelle_stl.py`).

## Tasks
- [x] N0 (S4) shared STL tool `validation/tools/make_nacelle_stl.py` + test — lead
- [ ] N1 (S3,S4) Phase VI: nacelle on/off in the generator, STL, ALM 7 m/s case pair, slurm script — worker A (`validation/phaseVI/**`)
- [ ] N2 (S1,S2,S3) IEA 15 MW: `--nacelle on|off` (+ hub) in the generator, STL from WindIO drivetrain, case pair, slurm script — worker B (`validation/iea15mw/**`)
- [ ] N3 submit, read, compare (band ratios, figures), conclude — lead

## Log
- L1 (2026-10-14, user): "ok para el caso de IEA si las simulaciones no tienen gondola, entonces podriamos ponerse, y ver la diferencia, aun siendo un analisis numerico, y ahi podriamos evaluar si el comportamiento es similar al que tenemos en el PhaseVI, eso slo una evaluacion digamos que empirica. entonces si, haz las dos cosas en paralelo"
