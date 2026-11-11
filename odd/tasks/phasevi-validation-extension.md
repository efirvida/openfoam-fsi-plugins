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

- T1 (S1): v1.4 adoption: record + frozen v1.3 + registry variant v1.4 + docs + record doc (8421f4a; 148 focused tests pass; all F_Cl runs CONFORM v1.4, v1.3 runs CONFORM v1.3). Pending: renderer default near-tip on (as 988fee6) + failing test_runner_default_is_the_record_and_forwards_the_reference, CHANGELOG/tool registration for T2/T4/T5/T6 (writer W5 in progress). Route: writer W4 (isolated wip/w4-v14), W5. Commit: 8421f4a
- T2 [done] (S2): pitch override (`generate_case.py --pitch-deg`, `runPhaseVI.sh -s T|U|J|I`, ALM only, run id `-seq<T>`), run.json `pitch_deg`, `compareYawPitch.py --pitch` exit 5 on mismatch; 15 new tests pass, S render byte-identical; shellcheck unavailable. Route: writer W1. Commit: 976f9e6
- T3 (S2): T/U/J x 5-8 m/s, variant tip-pitch-dag-sorensen-neartip, label var-tip-pitch-dag-sorensen-total-neartip, frozen worktree .worktrees/g1-runs at 976f9e6, LIB_DIR runs/lib-neartip-6f27aad; jobs T5-8 11725984/85/87/88, U5-8 11725989-92, J5-8 11725993-96 (cpu_long, bigmem_long, cpu, bigmem round-robin), 2026-11-11. Compare: `compareYawPitch.py --pitch P --sequence X --speed U --run-dir <run>`. Route: inline (Slurm). Commit: n/a
- T4 (S3): H5/H6/H8 runs: H5 11725946 (sequana_cpu); H6/H8 first jobs 11725947/8 FAILED at render (H kinematics lacked 6/8; fixed 5a25acd, 66 tests pass), resubmitted from frozen .worktrees/g2-runs at 5a25acd: H6 11726051 (sequana_cpu), H8 11726052 (sequana_cpu_long); compare with `--experiment data/experiment/uae6-archive`. Original jobs, submitted 2026-11-11 from `.worktrees/v15b-runs` (02651dd), LIB_DIR runs/lib-neartip-6f27aad, label var-tip-pitch-dag-sorensen-total-neartip. Route: inline. Commit: n/a
- T5 [done, L2] (S4): `scripts/compareProbeInflow.py` (probe 5HPxxA local flow angle vs ALM blade-averaged `alpha_deg`); 6 tests pass; written test-after (no RED). Owed: `tools/analysis_gap.py` TOOL_COVERAGE + CHANGELOG Tooling entry. Route: writer W2 (isolated wip/w2-probe). Commit: 6824f0e
- T6 [done, L3] (S5): `scripts/compareRootMoment.py`; 14 tests pass (RED then GREEN). Owed: tools README row + analysis_gap TOOL_COVERAGE + CHANGELOG. Route: writer W3 (isolated wip/w3-root). Commit: 287f378
- T7 (S6): stall runs: nt S13 11725949, v1.3 S25 11725950 (sequana_cpu); v1.3 S13 11725951, nt S20 11725952, v1.3 S20 11725953, nt S25 11725954 (sequana_cpu_bigmem); same worktree/lib as T4. Then the limitations table. Route: inline. Commit: -
- T8 (S2-S6): judge all results, record, docs. Route: inline. Commit: -

## Log

- L1 (owner, 2026-11-11): "OK vamos con B todo el paralelo" (option B = G1, G2, G3, G4 + G6 of tip-model-analysis.md L21; earlier in L20: "Si a los dos" approving F_Cl in v1.4 and the stall comparison to document method limitations).
- L2 (agent, 2026-11-11): T5 result. Probe extraction is faithful (h0500000 channel means equal the table); the speed-independent column is the spanwise angle 5HPxxF, not the local angle 5HPxxA; station 51 % is anomalously high in the raw channels. The 5HPxxA reference line/sign is undocumented in the repo; it rises with speed, so it is paired with ALM `alpha_deg` (inference). H7 v1.3+F_Cl rev 4..12, exp/ALM/delta deg: 0.34 13.89/8.63/-5.26, 0.51 15.89/8.18/-7.72, 0.67 10.04/7.04/-3.01, 0.84 9.52/6.21/-3.31, 0.91 9.13/5.91/-3.22. Probe sits 3-8 deg above ALM alpha, the sign of uncorrected leading-edge upwash, close to the uninduced `alpha_geom`. Not a validation metric until a documented probe upwash correction (NREL report text not in repo) is found.
- L3 (agent, 2026-11-11): T6 result. Fair channel EAERORFB (#817 "Estimated aerodynamic root flap bending"; teeter separate #818); B1RFB strain gauge is context only (gravity/centrifugal). Gauge radius assumed 0.5083 m (blade-root attachment, TP-500-29955 p73), not documented. ALM blade 1, rho*sum(fx*(r-r_g)), thrust closure 1.0000. v1.3+F_Cl rev window from case.yaml, EAERORFB/ALM/delta %: S5 1067.2/929.6/-12.9, S6 1396.3/1326.3/-5.0, S7 1760.0/1678.4/-4.6, S8 2063.9/1891.2/-8.4, H7 1735.9/1653.5/-4.8. B1RFB is 17-31 % below EAERORFB (experiment's own gap). Side finding: `comparePhaseVI.span_limited_blade_thrust` omits rho though documented as dimensional (not touched).
- L4 (owner, 2026-11-11): "reparte todos los trabajos solo entre sequana_cpu y sequana_cpu_long". Agent: all pending jobs moved (scontrol) and balanced over sequana_cpu / sequana_cpu_long; no job left on bigmem partitions; future submissions use only these two.
