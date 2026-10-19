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
- C4 (S2.4): I7 Chaviaropoulos-Hansen rotational augmentation (a = 2.2, Burgos Tafur 2020) as a rotational-augmentation model option. PENDING.
- C5: build into a run-local lib dir, smoke run, then A/B runs on H 7 and S 5/7/8 per switch; summary table vs v1.2. PENDING.

## Log
- L1 (user, 2026-10-18): "3- vamos a implementar las correcciones con flags que se puedan activar y desactivar, para testar que dio mejor resultado"
- L2 (user, 2026-10-18): selected all four options (S2).
- L3 (agent): evidence to keep in mind (P2.3 L19): halving eps left the tip unchanged, Shen c2=21 and Dag & Sorensen overshoot the tip offline (+37.5 %, +50..77 %), the FLL offline estimate was < 2 points; R2 shows a speed-dependent error (S5 +28 %, S8 -20 % power) that the tip switches alone are not expected to remove.
