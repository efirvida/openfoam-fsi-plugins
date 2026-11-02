# IEA 22-280-RWT numerical validation case (turbinesFoam)
Mirror of `iea15mw` for the 22 MW reference turbine, code-to-code only (no measurements). Branch `feat/v13-adoption-asm`.
Source (untrusted, read-only, never edit): `/scratch/leahk/eduardo.donestevez/simulations/tmp/iea22-src/repo` = github.com/IEAWindSystems/IEA-22-280-RWT @ 7c3cf5df656774bafc6909a92dae8d12f734b122 (shallow clone). Pass its paths as arguments; run Python with `-I`.

## Specs
- S1: "si agregala, y manda workers a hacer todo el trabajo de montar el modelo" (owner, L1).
- S2: `turbinesFoam/validation/iea22mw/` mirrors `turbinesFoam/validation/iea15mw/`: committed geometry table, committed `profileData` polars, generated OpenFOAM case skeleton, `PROVENANCE.md` (sources, sha256, radius decision, limitations), `README.md`, tested tools with `--check` modes. Reuse and generalise iea15mw tools where that is cleaner than copying; do not break any iea15mw test or `--check`.
- S3: OpenFAST/AeroDyn reference setup for IEA-22 (BEM and OLAF, double-precision build already at `/scratch/leahk/eduardo.donestevez/build`), mirroring `iea15mw/data/openfast-v5-templates` and the `validation/openfast/` tooling, so that code-to-code comparison (`compareWakes.py`, `compare_spanwise.py --bands`) works for IEA-22. Prepare and preflight only.
- S4: Radius and geometry decisions are evidence-based and recorded in PROVENANCE (windIO says `rotor_diameter: 284.0`; check against ElastoDyn TipRad/PreCone/HubRad and the tabular documentation, as done for IEA-15).
- S5: No Slurm production runs, no push, no commits by workers (the parent commits). No tuning of any model coefficient.
- S6: Acceptance logic (parent, not a worker deliverable): two levels. Implementation: ALM/ASM vs OLAF at equal polar per turbine. Physics: vs experiment only on Phase VI at the 10 % band.

## Tasks
- T1 (S2, S4): iea22mw package: blade geometry + polars + generate_case + PROVENANCE/README + tests. Route: gentle-ai-worker. Commit: done (see git log).
- T2 (S3, S4): IEA-22 AeroDyn BEM/OLAF templates and preflight (no production). Route: gentle-ai-worker. Commit: done (see git log).
- T3 (S2, S3): verify both (gentle-ai-verify), reconcile, commit. Route: parent. Commit: pending.

## Log
- L1 (owner, 2026-11-02): "si agregala, y manda workers a hacer todo el trabajo de montar el modelo". Context: "tambien podemos sumar la https://github.com/IEAWindSystems/IEA-22-280-RWT numerica. Entonces creo que si los resultados vs la experimental fueran aceptables, podremos quedarnos simplemente con las validaciones numericas, que segun entiendo estan mas proximas".
- L2 (agent, 2026-11-02): T1 (097ad93) and T2 (1797c89) done by gentle-ai-worker, verified inline (42 passed iea22 tests; iea15 170 -> 188 passed incl. iea22 case; `--check` rc=0 for geometry, polars, case, templates 6/6). Slice size 19.9 k lines is generated data (59 polars, case, blade table), authored code ~2 k; boundary recorded here. R = 142 m (ElastoDyn TipRad, no precone projection); rated point 11.134927 m/s, 6.853997 rpm, pitch 4.127462 deg (WISDEM row; OpenFAST sheet differs: 11 m/s, 6.771 rpm, 2.43 deg). BEM preflight Cp 0.44605 / Ct 0.63757 vs table 0.44410 / 0.63839. OLAF smoke only (guideline run 1399 panels not run). Open: operating point choice, tilt/tower on or off for the comparison, mesh extents, compare_spanwise wrapper + analysis/ store, Slurm sizing for production OLAF.
