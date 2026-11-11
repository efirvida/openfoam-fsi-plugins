# Work while T16 runs: OLAF c_t frame, stall references, documentation audit
Branch `feat/v13-adoption-asm`, worktree `.worktrees/tip-pitch`. Three independent units while the T16 F_Cl runs (tip-model-analysis.md) are in Slurm.
Context: iea22-case-readiness.md L8 (c_t frame open, shared with IEA-15 L26); tip-model-analysis.md L15-L17 (stall comparison).

## Specs
- S1 (agent proposal accepted by owner): "Arreglar la comparación tangencial contra OLAF (recomendado). Hoy nuestro script compara c_t contra un c_t de OLAF en otro sistema de referencia, por eso no puedo decir de dónde sale el +8.9 % de potencia en IEA-22 (ni el +6.7 % en IEA-15). Es revisar qué canal de AeroDyn usamos y en qué ejes, corregir la proyección en `compare_spanwise` (IEA-15 e IEA-22), con test, y re-comparar las corridas existentes."
- S2 (agent proposal accepted by owner): "Preparar la comparación en pérdida con las referencias baratas. Correr AeroDyn BEM en S10/13/15/20/25 (minutos, `sequana_cpu_dev`) y extender la herramienta de T10 a esas velocidades. No incluye OLAF ni ALM (los caros); esos los decidimos con T16."
- S3 (owner question): "tambien quiero preguntarte si nuestro codigo esta bien documentado y referencias de los articulos implementados esta todo bien documentado tambien?" Read-only audit; answer with evidence, no edits.

## Tasks
- T1 [done, 322d4c7] (S1): c_t frame fix in IEA-15/IEA-22 `compare_spanwise`, test-first, re-compare existing runs. Route: gentle-ai-worker. Commit: 322d4c7.
- T2 [done, 4d66e6f] (S2): AeroDyn BEM stall references S10/13/15/20/25 + T10 tool cells extended. Route: gentle-ai-worker. Commit: 4d66e6f.
- T3 [done, L4] (S3): documentation and article-reference audit (code headers, READMEs, PROVENANCE, CHANGELOG vs implemented models). Route: gentle-ai-explore. Commit: n/a.

## Log
- L1 (owner, 2026-11-10): "vamos con 1 y 2. tambien quiero preguntarte si nuestro codigo esta bien documentado y referencias de los articulos implementados esta todo bien documentado tambien?"
- L2 (agent, 2026-11-10): T1 worker report (S1).
  - Frame evidence (OpenFAST v5.0.0 `AeroDyn_IO.f90:477-487`, `BEMTUncoupled.f90:265-276`, `actuatorLineElement.C:1074-1100`): the AeroDyn store holds the chord-frame BNCn/BNCt. The ALM c_ref_n/c_ref_t are the rotor-plane pair Cx/Cy. The old "c_t ratio" divided Cy by Ct. Fix: Cx = Cn cos(theta) - Ct sin(theta), Cy = Cn sin(theta) + Ct cos(theta), theta = twist + pitch.
  - Integral closure (IEA-22): OLAF torque 0.991, thrust 0.995; BEM torque 0.987; ALM 0.992. The "informational" caveat is removed.
  - IEA-22 ALM/OLAF torque 1.091 (= the +8.9 % cp). The gap is tangential and outboard: about 6 of 9 pp come from r/R 0.6-0.95, with 2.4 pp from the 0.9-0.95 band alone (c_y ratio 1.28). c_n is within 2 % to 0.9.
  - IEA-15 (OLAF/ALM): c_y 1.09-1.15 inboard of 0.6 and 0.85-0.92 outboard of 0.8, i.e. the ALM tangential force is under OLAF inboard and over it outboard. There is no raw IEA-15 OLAF Fn/Ft, so there is no own integral check; the rotation is validated by analogy.
  - Left as is: the committed `iea22mw/analysis/alm-vs-*.csv` still carry the old ct_ratio column. Note: the existing cn_ratio compares chord-normal (AeroDyn) with plane-normal (ALM) and differs from cx_ratio by about cos(theta).
- L3 (agent, 2026-11-10): T2 worker report (S2).
  - BEM stall refs: `runs/aerodyn-bem-SU{10,13,15,20,25}` (sequana_cpu_dev, jobs 11723390/93/94/96/98). `buildAeroDynCase.py` needed no change.
  - `applyNearTipFunctions.py`: `--cells` now accepts S10-S25. The default is still the five original cells, byte-identical to the committed cl.csv and full_3D_s0.25.csv. A model without a run is skipped with a stderr message. This also applies to the default cells, which previously exited 2.
  - 11 new tests, RED then GREEN (39 passed).
  - Offline BEM c_n error at r/R 0.95, uncorrected -> F_Cl, with tip alpha: U10 +23.0 -> +1.2 (8.5 deg); U13 +23.0 -> +1.3 (13.1 deg); U15 +26.9 -> +4.8 (16.1 deg); U20 +21.5 -> +4.2 (23.8 deg); U25 +87.7 -> +63.7 (30.3 deg). Only U10 is near the 3-7 deg derivation range.
  - Reading: the stall tip "fix" from 13 to 20 m/s is an extrapolation (F_Cl is a fixed factor of cl). It must not be claimed as validation; it must be shown with F_Cl on and off. Inboard stall errors (-10 to -57 %) dominate and are polar/3-D stall effects.
- L4 (agent, 2026-11-10): T3 audit (S3, read-only).
  - Well documented: Trigaux F_Cl (code, README with DOI, PROVENANCE with sha256), Phase VI data provenance, and Du-Selig / Chaviaropoulos-Hansen rotational augmentation (secondary sources with DOI).
  - Gaps, ranked:
    (1) No central bibliography.
    (2) Dag & Sorensen without journal/DOI outside odd/.
    (3) Glauert/Prandtl, Shen (possible sign inversion in g flagged in phasevi-endeffect-diagnostic.md:31) and Leishman-Beddoes classes without citations.
    (4) Projection epsilon (Massie 2019, Mendoza) without full citation; the bladeSurface "paper Eq. 8/18" is unidentified.
    (5) Primary Du & Selig 1998 and Chaviaropoulos & Hansen 2000 missing in code; Lindenburg and added mass unreferenced.
  - Not checked: the root plugins, the Python scripts/tools, and the IEA PROVENANCE files.
- L5 (agent, 2026-11-10): parent verification: focused tests 81 passed (compare_spanwise x3, near_tip_functions). The 3 full-suite failures (test_element_residuals header with near_tip columns; test_phasevi_yaw_pitch_reference [H]/[S]) fail identically on a clean HEAD worktree, so they pre-exist and are not caused by T1/T2; open follow-up. Commits 322d4c7 (T1) and 4d66e6f (T2); CHANGELOG entries for both in 322d4c7.
