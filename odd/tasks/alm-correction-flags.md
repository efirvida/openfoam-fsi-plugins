# ALM literature corrections behind on/off flags (A/B bench)
Owner request from P2.3 (`p2-3-v12-diagnosis.md` L21-L22). Every correction is a switch, default OFF, so v1.2 stays
reproducible; each is judged by A/B runs against the experiment with the existing tools. No fitted coefficient.

## Specs
- S1 (owner, 2026-10-18): "vamos a implementar las correcciones con flags que se puedan activar y desactivar, para testar que dio mejor resultado"
- S2 (owner, selected set): "1. Banco A/B de las ya existentes (Recomendado)", "2. Muscari 2024 / Xie 2021 (I4)", "3. Filtered lifting line, Martinez-Tossas (I5)", "4. Chaviaropoulos-Hansen RA (I7)".
- Standing rules (P2.3 S-list and definition rules): no fitted coefficient; literature constants only; Slurm `--ntasks` only;
  do not rebuild/install `libturbinesFoam` into `$FOAM_USER_LIBBIN` while a job runs (build into a run-local lib dir, as `runs/lib-p23`).

## Tasks
- C1 (S2.1): DONE (worker; parent differential: default render and checkModelDefinition output identical). Variants v1.2, shen-tip (c1 0.125, c2 21; also changes the hub formula), dag-sorensen-tip, ring-sampling (3.3 eps, 16 pts), du-selig-ra; `config/model-variants.yaml`, `checkModelDefinition --variant`, `slurm/variant-run.slurm`, `summarizeVariants.py`. A/B bench of the switches that already exist (endEffectsModel Glauert/Shen/liftingLine, Dag & Sorensen tipCorrection, ring velocity sampling, Du-Selig rotational augmentation): registered as named variants in the definition/checker (variant != v1.2 is never of record) + one sweep launcher + one comparison summary. PENDING.
- C2 (S2.2): I4 effective-velocity sampling (Muscari 2024) / Lagrangian-averaged sampling (Xie 2021) as a velocity-sampling switch. Equations from `turbinesFoam/articles/` PDFs. PENDING.
- C3 (S2.3): I5 filtered lifting line correction (Martinez-Tossas 2019/2023; Meyer Forsting 2020 fast smearing correction as the reference implementation) as a switch. PENDING.
- C4 (S2.4): DONE. Burgos Tafur 2020 Eqs.(1)-(4), a=2.2 h=1 n=4; parent decisions: Cl_inv = 2*pi*(alpha-alpha0) as Du-Selig, dCd vs Cd(alpha=0) (plus sign), theta = local twist without pitch. Variant `ch-ra`; built into runs/lib-flags (installed lib untouched, mtime 2026-10-12); default renders identical. I7 Chaviaropoulos-Hansen rotational augmentation (a = 2.2, Burgos Tafur 2020) as a rotational-augmentation model option. PENDING.
- C5: build into a run-local lib dir, smoke run, then A/B runs on H 7 and S 5/7/8 per switch; summary table vs v1.2. PENDING.

## Log
- L1 (user, 2026-10-18): "3- vamos a implementar las correcciones con flags que se puedan activar y desactivar, para testar que dio mejor resultado"
- L2 (user, 2026-10-18): selected all four options (S2).
- L3 (agent): evidence to keep in mind (P2.3 L19): halving eps left the tip unchanged, Shen c2=21 and Dag & Sorensen overshoot the tip offline (+37.5 %, +50..77 %), the FLL offline estimate was < 2 points; R2 shows a speed-dependent error (S5 +28 %, S8 -20 % power) that the tip switches alone are not expected to remove.
- L4 (agent, 2026-10-18): C1 committed c965793. First A/B wave submitted (variant-run.slurm, 12 rev, sequana_cpu): shen-tip S7/S8 11618455/56, dag-sorensen-tip 11618457/58, ring-sampling 11618459/60, du-selig-ra 11618461/62. S 5 m/s arms wait for T11 (window length). Next: C4 (simplest C++), then C2, C3, each built into a run-local lib dir.
- L5 (agent): C4 committed 27ec5aa; ch-ra S7/S8 submitted 11618472/73 with LIB_DIR=runs/lib-flags. Branch delivery (push/PR, 352 unpushed commits) remains the owner's decision (P2.3 HANDOFF 3.3); each C-task is its own commit. Next: C2 (I4), C3 (I5).
- L6 (agent): C2 worker failed twice with a provider error ("assistant reported an error"): the C4 continuation after doing most of the work (finished and verified by the parent), and C2 before any edit (tree clean). Not retried in this session; C2 and C3 start in a fresh session from this document (C2 handoff: implement `effectiveVelocity` (Muscari 2024) and `lagrangianAveraged` (Xie 2021) as velocity-sampling options, constants from the papers, build into runs/lib-c2 — NOT runs/lib-flags, which queued ch-ra jobs load).
- L7 (agent, 2026-10-20): C5 partial A/B on Sequence S, ALM coarse, 12 rev, errors % vs UAE6 archive (`--experiment data/experiment/uae6-archive`), diagnostic only, none of record. P / T:
  v1.2 U7 -2.1/-0.8, U8 -19.9/-12.7 (U5 +28.3/+16.7 and U6 +14.2/+13.5 flag DRIFT);
  shen-tip U7 +11.7/+12.4 (cn0.95 +44.2), U8 -3.9/+2.3; dag-sorensen-tip U7 -4.0/-1.4, U8 -20.2/-12.8 (no effect);
  ring-sampling U7 -0.4/-0.8, U8 -17.7/-12.6 (neutral); du-selig-ra U7 +1.8/+2.7 (cn0.30 +27.7), U8 -12.1/-6.2;
  ch-ra U7 +1.2/+5.7 (cn0.30 +31.6), U8 -11.0/+0.6. Conclusion: no isolated switch removes the speed-dependent error without breaking U7 or the root/tip. Pending: H 7 and S 5 arms, DRIFT on U5/U6, C2, C3.
- L8 (agent, 2026-10-20): defect found: `comparePhaseVI.py` read only `postProcessing/<object>/0/`, ignoring resume segments (ring-sampling U8 looked like 1.3 rev, S U5 v12 was read to 18.2 s of 20.1 s). Fixed with `read_rows_resumed` (later segment replaces the overlap) + 2 tests. `plotComparisonFigures.py` and `proxyRotationalAugmentation.py` still hardcode segment 0.
