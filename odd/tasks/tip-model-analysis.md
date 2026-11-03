# Tip model analysis (ALM / ASM / ASM+mesh) before any new run

Read-only analysis of the blade-tip treatment: methods, implementation, prior repository evidence and state of the art.
No Slurm runs, no solver changes. Output: a decision-ready report for the owner.

## Specs
- S1: "vamos a analizar con detenimiento los modelos de la punta, sin lanzar nada todavia" (owner, L1).
- S2: "creo que deberiamos analizar la literatura, la implementacion, tal vez buscar mas literatura" (owner, L1).
- S3: "por lo que veo el asm+mesh esta bastante mejor que los demas, pero mucho peor en la punta, todos los demas tambien estan mal en el modelo de la punta, entonces la prioridad es la punta" (owner, L1).
- S4: "la base es fundammentalmente rigida" (owner, L1): the root residual (r/R 0.30) is out of scope for this analysis; it is documented, not chased.
- S5: "un analisis detallado de los metodos la implementacion el estado del arte, antes de volver a lanzar nuevas simulaciones" (owner, L1).
- S6 (standing, L28 of v13-adoption-asm): "No ajustar coeficientes"; the 0.95 station needs "una precision aceptable y justificable" because structural torque and deformation peak there.

## Tasks
- T1 (S2, S5): implementation map of every tip path (ALM end effects Glauert/Shen/liftingLine, D&S tipCorrection, tipEffects, projection epsilon, velocity sampling, ASM chordwise strips, ASM+mesh deposit/staging) with path:line. Route: gentle-ai-explore. Commit: n/a.
- T2 (S3, S5): repository evidence: what each prior tip study tested, its numbers at r/R 0.95 and its conclusion (odd/tasks tip/end-effect/D&S/FLLT/Lindenburg docs, run comparisons, OLAF/BEM at 0.95). Route: gentle-ai-explore. Commit: n/a.
- T3 (S2, S5): literature and state of the art: ALM/ASM tip corrections and smearing corrections, Phase VI r/R 0.95 measurement and resolved-CFD reference values. Route: gentle-ai-explore (web). Commit: n/a.
- T4 (S1-S6): synthesis: mechanism per model, which effects are physics vs numerics vs reference, ranked options with predicted effect and cost, owner decision. Route: inline. Commit: pending.

## Log
- L1 (owner, 2026-11-03): "ok entonces vamos a analizar con detenimiento los modelos de la punta, sin lanzar nada todavia, creo que deberiamos analizar la literatura, la implementacion, tal vez buscar mas literatura, porque por lo que veo el asm+mesh esta bastante mejor que los demas, pero mucho peor en la punta, todos los demas tambien estan mal en el modelo de la punta, entonces la prioridad es la punta, porque la diferencia mayor es la base, y para FSI no es tan importante, porue la base es fundammentalmente rigida. ENtonces vams con un analisis detallado de los metodos la implementacion el estado del arte, antes de volver a lanzar nuevas simulaciones"
- L2 (agent, 2026-11-03): starting point, S U7 v1.3, rev 4..12, c_n error vs experiment at r/R 0.95: ALM +26.2 %, ASM (T16 fix) +26.2 %, ASM+mesh (T16 fix) +45.6 %; 0.47-0.80 ALM/ASM within 3 %, ASM+mesh within 5 %. Earlier preliminary OLAF SP S U8 at 0.95: +16.5 % (ALM +25.4, BEM +19.1). IEA-22: ALM vs OLAF c_n 0.95-1.0 ratio 1.006, vs BEM 1.202.
- L3 (agent, 2026-11-03): T1-T3 explorer reports received. Verified inline: (1) DEFECT, ASM+mesh D&S still inert after 3ed889b: `actuatorLineSource.C:407-415` forces `projectElementForce false` whenever `surfaceGeometry` is set; `actuatorLineElement.C:1487,1532` then skip `applyForceField`, the only `calcProjectionEpsilon()` caller active in v1.3 (`:725`; `:780` needs velocitySampleRadius > 0, `:1580` needs k/omega fields), so `projectionEpsilon_` stays -VGREAT and `axialFlowTurbineALSource.C:806-808` hands D&S a negative epsilon (stationValid false, correction zero). Data agree: ASM+mesh S U7 0.95 +45.6 % both before (V14) and after (job 11637164) the fix. CORRECTION of v13-adoption-asm L30: the ASM+mesh tip is NOT "deposit form, not the epsilon defect"; it is the same inert-D&S defect, and job 11637164 did not test the fix. `turbinesFoam/README.md:186-190` claims the fix covers ASM+mesh: wrong. (2) The 0.95 station sits 0.251 m from the tip, 0.66 of the local chord (0.381 m at r 4.778 m, `phaseVI_blade.csv`). (3) Arbiters at S U7 0.95: OLAF-DP +19.7 %, AeroDyn BEM +20.0 %, ALM +26.2 % (v13 L26): about three quarters of the tip error is shared by every lifting-line-class model with the same polar, ALM-specific residual 6.4-8.9 pp.
