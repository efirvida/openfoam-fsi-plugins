# Nacelle on/off and root-error study (Phase VI and IEA 15 MW)

Empirical test of whether the nacelle (or the root factor) explains the root error of Phase VI (CN +13.6 % at r/R 0.30, 7 m/s, all methods).
Branch: `fix/compare-phasevi-surface-stations`. No `libturbinesFoam` rebuild. Do not edit existing scripts' behaviour by default. P2.2 (Sequence S) runs in parallel and is tracked in `validation-master-plan.md` / `p2-2-sequence-s.md`.

## Specs
- S1: "puedes evaluar los resultados de la iea15MW contra simulaciones numericas ahi donde esta la gondola ... apagandola en las configuraciones de los casos y ver su efecto"
- S2: "para el caso de IEA si las simulaciones no tienen gondola, entonces podriamos ponerse, y ver la diferencia ... eso solo una evaluacion digamos que empirica."
- S3: "entonces si, haz las dos cosas en paralelo" (Phase VI nacelle on/off, and IEA nacelle on/off).
- S4 (rewritten 2026-10-14, L2-L3): "el inform de NREL no trae la geometria de la gondola". NREL/TP-500-29955 Fig. 8 is "Drivetrain configuration"; its 1.469 / 1.79 / 0.91 m are drivetrain dimensions, not the nacelle fairing. The Phase VI nacelle body is therefore a surrogate, never quoted as the UAE geometry: it is sized so that its drag matches the measured nacelle drag of the aerodynamic tares (Appendix I, run 056 tower + nacelle minus run 058 tower only, yaw 0), and its shape sensitivity is bounded with at least two shapes of equal drag area.
- S5 (L4): plan chosen "Plan completo recomendado": A1 tare tool (nacelle CdA from 056 - 058), A3 IEA on/off, root-factor A/B (`--root-effects off`), P2.2 Sequence S in parallel; A2 Phase VI once the CdA exists.

## Tasks
- [x] N0 (S4) shared STL tool `validation/tools/make_nacelle_stl.py` + test — 7ef5aa0
- [x] A1 (S4,S5) tare tool: `scripts/extractAeroTare.py` + `data/experiment/aero-tare/runs_056_058.csv`, summary `analysis/aero-tare-nacelle-cda.csv` (L5)
- [ ] N2/A3 (S1,S2,S3,S5) IEA 15 MW `--nacelle on|off`: fix the 3 failing tests left by the worker, commit, run the on/off pair — inline
- [ ] H1 (S5) Phase VI root-factor A/B: ALM U7 H coarse, `--root-effects off`, same config as `alm-U7-coarse-p21` — submitted job 11615758 (`scripts/slurm/h1-rootoff.slurm`, run `alm-U7-coarse-p21-rootoff`)
- [ ] N1/A2 (S3,S4) Phase VI nacelle: drop the Fig. 8 provenance, size the surrogate to the A1 CdA, two shapes, ALM U7 on/off — inline
- [ ] N3 read, compare (band ratios, section loads), conclude — inline

## Log
- L1 (2026-10-14, user): "ok para el caso de IEA si las simulaciones no tienen gondola, entonces podriamos ponerse, y ver la diferencia, aun siendo un analisis numerico, y ahi podriamos evaluar si el comportamiento es similar al que tenemos en el PhaseVI, eso slo una evaluacion digamos que empirica. entonces si, haz las dos cosas en paralelo"
- L2 (2026-10-14, user): "la geometria de la gondola no esta en ningun lado del informe"
- L3 (2026-10-14, user): "vamos a continuar las validaciones. en la sesion anterior dijiste una cosa falsa sobre la gondola, el inform de NREL no trae la geometria de la gondola. vamos a ver que plan tenemos ahora para validar o mejorar los resultados bases que tenemos"
- L3a (agent, evidence): confirmed in `articles/29955.pdf`: Fig. 8 caption (PDF p. 21) "Drivetrain configuration, top view; drivetrain and yaw drive/brake, side view"; no nacelle fairing geometry. Appendix I (PDF p. 295-300): aerodynamic tare run 056 (tower + nacelle, blades removed; yaw sweep at 5, 7, 10, 15, 20, 25 m/s) and run 058 (tower only; 5-25 m/s). Raw balance channels, no tare applied, non-SI units (lb, psf).
- L3b (agent, evidence): the uncommitted N2 IEA code fails 3 of 6 tests (`make_nacelle_stl.py:99` unpack error; the rendered `nacelle` block carries a comment the test does not strip). The IEA nacelle is sized from internal generator radii (WindIO), so it is a surrogate as well.
- L4 (2026-10-14, user): chose "Plan completo recomendado".
- L5 (agent, A1 result): nacelle (+ hub, blades removed) drag area at yaw 0, `CdA(056) - CdA(058)`: 0.96 / 0.94 / 0.98 m^2 at 15 / 20 / 25 m/s; least-squares slope over all speeds 0.86 m^2. At 5-10 m/s (q 15-60 Pa) the per-speed value is 1.5-2.2 m^2, dominated by the balance offset (run 058 fitted offset -4 N, run 056 +36 N), so it is not used. Target for A2: **CdA ~ 0.9 m^2** (0.86-0.98). It includes the hub/teeter assembly and the tower-top interference (run 058 had the nacelle removed). For scale: a disc of 0.91 m diameter is 0.65 m^2 of frontal area, so the measured value is consistent with a bluff body of about 1 m diameter and Cd ~ 1.
