# Phase VI validation extension (option B)

Extend the Phase VI ALM validation beyond S 0-yaw with v1.4 (= v1.3 + F_Cl near-tip correction) as definition of record.
Gap analysis: `odd/tasks/tip-model-analysis.md` L21. Branch `feat/v13-adoption-asm`, worktree `.worktrees/tip-pitch`.

## Specs

- S1 (L1, L20): adopt F_Cl in v1.4: "Si a los dos" (adopt F_Cl in v1.4; stall comparison as limitations documentation). v1.4 = v1.3 + `nearTipCorrection` on, exactly as registry variant `tip-pitch-dag-sorensen-neartip` (T14/T16 evidence, tip-model-analysis.md L19). v1.3 stays reproducible (frozen copy, as v1.2 was).
- S2 (G1): pitch sensitivity: ALM v1.4 runs at the pitch of sequences T (2 deg), U (4 deg), J (6 deg) at 5-8 m/s, compared with `compareYawPitch.py --pitch`. Needs a pitch override in the case renderer and the run scripts, and the pitch recorded in `run.json`.
- S3 (G2): H sequence at 5, 6, 8 m/s with v1.4.
- S4 (G3): H 5-hole probe flow angle (`data/experiment/uae6-archive/sequence_H_probes.csv`, 34/51/67/84/91 %) vs the ALM sampled inflow angle; document the probe upwash caveat; verify the probe extraction first (flow-angle column looks nearly speed-independent).
- S5 (G4): root flap bending moment (`eaerorfb_nm`, `b1rfb_nm` in `data/experiment/yaw-pitch/pitch_performance.csv`) vs the ALM integrated blade root moment.
- S6 (G6): stall limitations table S 10, 13, 15, 20, 25 m/s, v1.3 and F_Cl, with BEM refs `runs/aerodyn-bem-SU*`; reported as limitations, never as validation.

## Tasks

- T1 (S1): v1.4 adoption: model-definition record, frozen v1.3, registry, docs, tests. Route: writer W4. Commit: -
- T2 (S2): pitch override + run.json pitch audit. Route: writer W1. Commit: -
- T3 (S2): submit T/U/J runs after T2 (12 runs: pitch 2/4/6 x 5-8 m/s). Route: inline (Slurm). Commit: n/a
- T4 (S3): H5/H6/H8 runs: jobs 11725946/7/8 (sequana_cpu), submitted 2026-11-11 from `.worktrees/v15b-runs` (02651dd), LIB_DIR runs/lib-neartip-6f27aad, label var-tip-pitch-dag-sorensen-total-neartip. Route: inline. Commit: n/a
- T5 (S4): probe vs sampled inflow-angle reader. Route: writer W2. Commit: -
- T6 (S5): root flap moment reader. Route: writer W3. Commit: -
- T7 (S6): stall runs: nt S13 11725949, v1.3 S25 11725950 (sequana_cpu); v1.3 S13 11725951, nt S20 11725952, v1.3 S20 11725953, nt S25 11725954 (sequana_cpu_bigmem); same worktree/lib as T4. Then the limitations table. Route: inline. Commit: -
- T8 (S2-S6): judge all results, record, docs. Route: inline. Commit: -

## Log

- L1 (owner, 2026-11-11): "OK vamos con B todo el paralelo" (option B = G1, G2, G3, G4 + G6 of tip-model-analysis.md L21; earlier in L20: "Si a los dos" approving F_Cl in v1.4 and the stall comparison to document method limitations).
