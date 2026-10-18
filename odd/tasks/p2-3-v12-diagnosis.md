# P2.3 — Model Definition v1.2: evaluation on Sequence S and diagnosis of the remaining normal-force residuals
Phase VI, attached regime (7 m/s). v1.2 = Glauert tip + Prandtl hub, D&S off, OSU Re 1e6 pressure-drag polar
(`validation-model-definition.md`). Residuals on H (`alm-U7-coarse-d1-pdrag`): c_n +13 % at r/R 0.30, -14 % at 0.95.

## HANDOFF — resume here (written 2026-10-17, end of session 3)

Read this section, then `## Specs`, then the last ~6 Log entries (L10 holds the PRE-REGISTERED predictions and
decision rules: judge every result against them, do not re-derive them). Model Definition is **v1.2**
(`validation-model-definition.md`, top note: Glauert tip + Prandtl hub, D&S off, pressure-drag polar, POINT
velocity sampling); production-readiness criterion R1-R6 is APPROVED (same file). Candidate levers:
`model-improvements-register.md` (I1-I17).

### 1. Jobs (check first)
`sacct -j 11618033,11618034,11618035,11618046,11618055,11618056,11618057,11618058,11618059,11618060,11618061 -X --format=JobID,JobName%16,State,Elapsed,NNodes,Partition`
All run from `turbinesFoam/validation/phaseVI`; run dirs under `runs/`; logs `runs/<label>-*.out|err`.
| job | purpose | run dir | partition / limit |
|---|---|---|---|
| 11618033 | T1/R2 S 7 ALM v1.2 (record) | `alm-U7-coarse-seqS-v12` | bigmem 12 h |
| 11618034 | T1/R2 S 7 ASM | `asm-U7-coarse-seqS-v12` | bigmem 12 h |
| 11618035 | T1/R2 S 7 ASM-mesh | `asm-mesh-U7-coarse-seqS-v12` | bigmem 12 h |
| 11618046 | T5/R4 eps 0.31 m (H 7, refine 1, meshFactor 1; NON-CONFORMING by design) | `alm-U7-coarse-r1-v12-eps1` | bigmem 12 h |
| 11618055 | R1 ladder level 1 (eps fixed) | `alm-U7-coarse-r1-v12-l1` | sequana_cpu 12 h |
| 11618056 -> 11618422 | R1 ladder level 2 (TIMEOUT at 6.9 rev; resubmitted 2026-10-18 with --restart, --open-mode=append) | `alm-U7-coarse-r2-v12-l2` | bigmem 12 h |
| 11618057 | R1 dt 0.0005, level 0 | `alm-U7-coarse-v12-dt05` | sequana_cpu 20 h |
| 11618058-60 | R2 S ALM 5 / 6 / 8 m/s | `alm-U{5,6,8}-coarse-seqS-v12` | sequana_cpu 12 h |
| 11618061 | T4 Glauert lag + regression, 4 rev, loads `runs/lib-p23` | `alm-U7-coarse-v12-lag` | sequana_cpu 12 h |
Reference arm for H 7 v1.2 = `runs/alm-U7-coarse-d1-pdrag` (CONFORMS; level 0, dt 0.001).
- If a job hit its time limit before 12 rev: resubmit the SAME launcher line (all restartable, `--restart`); lines are in the
  launcher headers (`scripts/slurm/v1-2-{evaluation,small-eps,run,lag}.slurm`); add `--partition=sequana_cpu_bigmem` if
  `sinfo` shows idle bigmem nodes (owner approved bigmem; account limit 4 jobs there + 4 on sequana_cpu).
- If a job FAILED: read the `.err` first (InfiniBand/UCX errors are infrastructure: resubmit unchanged).
- First, for every finished run: `python3 scripts/checkModelDefinition.py runs/<dir>` (all CONFORM except eps1).

### 2. Analysis per job (tools exist; write no inline analysis)
- **T1/R2 S 7 (033-035)**: `python3 scripts/comparePhaseVI.py --run-dir runs/<dir> --speed 7 --sequence S --experiment data/experiment/uae6-archive --out /tmp/cmpS_<dir>`; `python3 scripts/summarizeBands.py /tmp/cmpS_<dir>`;
  `python3 scripts/compareSectionLoads.py --alm-dir runs/<dir> --sequence S` (force x arm; enriched S data exist only at 7 m/s);
  `python3 scripts/quantifyUncertainty.py --run-dir runs/<dir> --sequence S --speed 7`. Baseline to compare: `alm-U7-coarse-seqS-p22`
  (v1.1 polar: P -11.0 %, T -0.7 %, c_n +15.1/+1.8/+2.4/-0.3/-12.1 %). Prediction L10: ALM/ASM ~ -2 %, ASM-mesh ~ -5 %; ALM must gain >= ~6 points.
- **R2 S 5/6/8 (058-060)**: same comparePhaseVI + summarizeBands + quantifyUncertainty with `--speed 5|6|8`. ASM/ASM-mesh at those speeds are submitted only if ALM passes (decision recorded in R2 row).
- **T5 eps (046)**: `comparePhaseVI.py --run-dir runs/alm-U7-coarse-r1-v12-eps1 --speed 7 --out /tmp/cmpH_eps1`; `summarizeBands.py --allow-nonconforming /tmp/cmpH_eps1 /tmp/cmpH_d1`
  (rebuild /tmp/cmpH_d1 from d1-pdrag if /tmp was cleaned); `compareSectionLoads.py --alm-dir ...` both; apply the L10 rule on tip c_n 0.95
  (|change| < 2 points: eps not the lever; drop > 2: double counting -> I5/I6 reopen, owner; rise > 2: under-resolution). Update I4/I5/I6/I17.
- **R1 ladder (055-057)**: criterion = P, T and F'n at r/R 0.47-0.95 change < 2 % between level 1 and level 2, and between d1-pdrag and dt05.
  NO tool exists yet for the side-by-side: write `scripts/compareLadder.py` (reads comparePhaseVI metrics.json + compareSectionLoads profiles of N runs, prints % change per quantity; tests first) before reading the numbers.
- **T4 lag (061)**: 4 revolutions only. `comparePhaseVI.py --run-dir runs/alm-U7-coarse-v12-lag --speed 7 --revolutions 2 4 --allow-short-window` and the same on d1-pdrag with `--revolutions 2 4`: they must agree (regression of commit 0c723e4: the change only adds CSV columns).
  Check the element CSV header ends with `end_effect_phi_deg,inflow_ref_angle_deg`. `diagnoseElementResiduals.py` has NO `--revolutions` option yet and its window is revs 4-12: add `--revolutions`/`--allow-drift` (pass-through to `converged_window`) before running block (b). Prediction: lag ~0, factor difference < 0.5 %.

### 3. Open owner decisions (do not act without them)
1. **VTUN**: simulation runs at nominal 7.0 m/s; measured tunnel speed h0700000 7.049 (+0.7 % U, ~+2 % power), s0700000 7.016 (+0.2 %, ~+0.7 %). Recommended: deterministic comparison-side correction (BEM sensitivity, as the blockage term) reported explicitly; alternative: simulate at measured U (resubmissions).
2. **c_n band at r/R 0.30**: judge on dimensional force or with the same reference pressure (QNORM vs 0.5 rho W^2 explains ~9 of the +13 points; T3(c)).
3. **Delivery**: branch `fix/compare-phasevi-surface-stations` has 341 commits not pushed vs origin/main; push/PR is the owner's decision.
4. After T5 (DONE, L19: eps not the lever): the tip deficit is in the Glauert factor itself; any further tip lever is a literature correction -> owner decision (none implemented).
5. **R2 failed (L19)**: v1.2 ALM misses S 5/6/8 m/s (P +28/+14/-20 %), 7 m/s is a crossing point. Owner chooses the next diagnostic (session 4 proposals: extend S5/S6 beyond 12 rev so the window is quasi-steady; a v1.1 total-drag run at S 5 m/s to separate drag from angle/induction; an H 5 m/s run to compare the inflow angle with the probes, since S has no probes; extract qnorm/cth/ctq for S 5/6/8 from the archive so the dimensional tools run there).
6. Tool fix proposed (not done): summarizeBands should mark drifting windows not of record (S4).

### 3b. Disk cleanup done at the end of session 3 (owner-approved)
Kept FULL (restartable): all `*-v12*` runs, `alm-U7-coarse-d1-pdrag`, `mesh-coarse`, `mesh-coarse-r1`, `mesh-coarse-r2`, `lib-p23`,
IEA `iea15mw-screen-m3-l2` (L2 production state) and `iea15mw-l2-ctrl` (R3 starting point).
DELETED: `alm-U7-coarse-dagtipd`, `alm-U7-coarse-r3`, `mesh-coarse-r3` (refine level 3 must be re-meshed if ever needed), FLOWUnsteady `*pfield*` particle fields.
SLIMMED (43 dirs: every other Phase VI and IEA run, incl. p21, seqS-p22, U10, B, rootoff, nacon, dagtip, eqb-*, asm-mf*, IEA D&S/RA/ASM variants, `_archive`):
`processor*/`, `constant/polyMesh`, `0/` removed; `postProcessing/`, `system/`, `run.json`, logs kept, so every analysis tool and every
documented number still reproduces, but those runs CANNOT be restarted, extended or field-sampled. Path list: `phaseVI/runs/CLEANUP-2026-10-17-paths.txt`.

### 4. Next work after the analysis
R2 extension (ASM/ASM-mesh at 5/6/8 if ALM passes), R3 (IEA 15 MW v1.2: P0.4 Glauert control cp 0.5461 vs OLAF 0.5312; I14 polar Re), R4 closure, T6 limits chapter.
Do NOT rebuild/install `libturbinesFoam` into `$FOAM_USER_LIBBIN` while any job runs; `runs/lib-p23` holds the build of 0c723e4+ (only the lag job loads it).

## Specs
- S1 (owner, 2026-10-17): "ok no utilizarlo si no da buenos resultados vs resultados experimentales." (FLOWUnsteady)
- S2: "Si es la que mejor resultado ha dado, lo adoptamos por el momento, pero no quiero detenerme ahi quiero continuar el diagnostico" (pressure-drag polar)
- S3: "Creo que no, no vamos a gastar mas tiempo de simulacion en regimen de perdida. Luego cuando el regimen normal validado, documentamos las restricciones d elos metodos, basados en esos resultados"
- S4: "lo que entiendas correcto, siempre que ya este en regimen convergido "quasi estacionadrio"" (averaging window)
- S5 (answer to the tip-model question): "Glauert en ambos pilares (Recomendado)"
- Standing rules: no literature method implemented without the owner; no fitted coefficient (definition rules); Slurm: `--ntasks` only.

## Tasks
- T1 (S2,S5): DONE 2026-10-18 (L19). v1.2 on S 7 m/s, all CONFORM: ALM P -2.1 % T -0.8 %, ASM P -2.1 % T -0.8 %, ASM-mesh P -8.2 % T -2.9 % (all PASS bands); c_n 0.30/0.47/0.63/0.80/0.95 ALM +14.5/+1.3/+2.1/-0.4/-12.4 %. ALM gained 8.9 points vs p22, ASM-mesh 6.2 (p22 -14.4 %). Dimensional F'n 0.30 +3.8 % (QNORM effect, as on H). Jobs 11618033/34/35.
- T2 (S2): R2 nacelle (`alm-U7-coarse-nacon` vs `p21`): DONE, no effect (c_n 0.30 +13.6 % both, 0.95 -14.0 % both, P -10.9 vs -11.0 %). Discarded.
- T3 (S2): DONE (`scripts/diagnoseElementResiduals.py`). Offline element-level tool on `d1-pdrag`: (a) station interpolation vs element values at 0.95 and 0.30 (steep F gradient, elements 45/46); (b) Glauert factor recomputed from the same-step sampled velocity vs the written `end_effect_factor` (one-iteration lag); (c) QNORM vs 0.5 rho W^2 normalisation at 0.30 (4.3 % reported); (d) first-order Re effect at r/R 0.30 from the CSU 0.65e6 / multi-Re tables at the run's alpha. PENDING.
- T4 (S2, revised by L7 and L13): DONE 2026-10-18 (L19). Job 11618061: revs 2-4 metrics identical to d1-pdrag on every banded quantity (regression of 0c723e4 passes); element CSV header ends with end_effect_phi_deg,inflow_ref_angle_deg; block (b) one-step Glauert lag 6e-5..9e-5 deg, delta F <= 2e-6 on tip elements 69-83 -> H3b closed. Tools: diagnoseElementResiduals --revolutions/--allow-drift/--allow-short-window; compareSectionLoads.converged_window(allow_short_window=).
- T5 (S2): DONE 2026-10-18 (L19). Job 11618046 (eps 0.31 m, NON-CONFORMING by design): tip c_n 0.95 -14.3 -> -14.1 % (+0.2 points), tip F'n 139.3 N/m in both -> L10 rule: eps is NOT the lever; deficit is in the Glauert factor itself; remaining options are literature corrections (owner decision). Power -2.2 -> -4.1 %, thrust -0.8 -> -1.4 %, c_n 0.47-0.80 move <= 0.6 points, 0.30 +13.0 -> +11.8 %. Register: I4/I17 not triggered, I5 stays NO-GO, I6 premise refuted.
- T6 (S3): model-limits chapter from existing stall results (after the attached regime is validated). PENDING.
- T7 (L11): single improvements register `odd/tasks/model-improvements-register.md` (I1-I16, status and reopen condition). DONE.
- T8 (L11): production-readiness criterion R1-R6 in `validation-model-definition.md`: APPROVED (L13). R1: dt05 vs d1 PASS (max |change| 0.11 %, `scripts/compareLadder.py`); level 0 -> 1 max 1.23 % (P, informative); level 1 -> 2 PENDING: 11618056 TIMEOUT at 6.9 rev, resubmitted with --restart as 11618422 (bigmem). R2 ALM S 5/6/8: FAIL (L19): P +28.3/+14.2/-19.9 %, outside the R6 uncertainty at all three; 5 and 6 m/s also drift (cp 2.9/1.4 % > 1 %, not of record under S4); ASM/ASM-mesh at 5/6/8 NOT submitted (rule: only if ALM passes).
- T9 (L11): evidence register status rows updated to 2026-10-17. DONE.
- T10 (L11, R5): DONE. `config/model-definition.yaml` (effective values; absent key = cited solver default) + `scripts/checkModelDefinition.py`; `summarizeBands.py` labels non-conforming/unknown runs `[not of record]` and exits 1 unless `--allow-nonconforming`. d1-pdrag CONFORMS; p21/seqS-p22 non-conforming on the polar only; T5 run non-conforming on meshFactor by design (diagnostic). runPhaseVI.sh hook point: line 575 (not wired).

## Log
- L1 (user, 2026-10-17): "1- ok no utilizarlo si no da buenos resultados vs resultados experimentales. 2- Si es la que mejor resultado ha dado, lo adoptamos por el momento, pero no quiero detenerme ahi quiero continuar el diagnostico 3- Creo que no, no vamos a gastar mas tiempo de simulacion en regimen de perdida. Luego cuando el regimen normal validado, documentamos las restricciones d elos metodos, basados en esos resultados 4- lo que entiendas correcto, siempre que ya este en regimen convergido "quasi estacionadrio""
- L2 (user): "Glauert en ambos pilares (Recomendado)"
- L3 (agent): window done (`400fc9d`); v1.2 applied (generate_case default polar, definition doc, master-plan log, launcher); diagnostic history in `p2-2-next-cycle-plan.md` and the explorer map: tip already tried = Glauert/A'/D&S variants/FLLT NO-GO/fitted f forbidden; Glauert tip never run at eps < 0.63 m on the current platform; hub loss is not the 0.30 lever (p21-rootoff +14.7 vs +13.6 %).
- L4 (agent, T3 results on `d1-pdrag`, window rev 4-12, no drift): (a) station interpolation: factor-free interpolation moves c_n by +0.007 % at 0.30 and +0.13 % at 0.95 -> not a cause. (b) Glauert lag: NOT measurable, the element CSV has |W| only, no velocity components (needs a new output column or field re-sampling, T4). (c) **Normalisation explains most of the 0.30 residual**: the experiment's QNORM is 8.7 % above 0.5 rho W^2 of the run at 0.30 (1.023 at 0.47-0.63, 1.002 at 0.95); with the same reference the 0.30 residual is +4.0 % (dimensional F'n 63 vs 60 N/m, +5 %), the tip stays -14.5 %. So the inboard "c_n +13 %" is mostly a coefficient-reference difference; the tip deficit is a real force deficit. (d) Re at 0.30 is 0.62e6 vs polar 1e6: CSU 0.65e6 would lower c_n 9 % (facility change too), OSU multi-Re 0.75e6 only 1.2 %; sensitivity, not proof; not additive with (c).
- L5 (agent): bug found and fixed: `generate_case.py` dropped `--polar` for the ASM-MESH twin (always the default polar). No past asm-mesh run requested a polar (all run.json without it), so no result is contaminated; the v1.2 asm-mesh job 11618035 gets the pressure polar via the new default. `test_phasevi_nacelle` frozen baseline now pins the v1.1 polar explicitly.
- L6 (agent): next for the tip: T4 (field re-sampling) or a cheap solver output change (write the sampled velocity components per element) to measure (b); then T5 (smaller eps) only if (b)/T4 do not explain -14 %.
- L7 (user, 2026-10-17): "si aplica tus recomendaciones" -> T5: smaller-eps v1.2 ALM on H (refine-level 1, meshFactor 1) after a short cost smoke; (b): per-element sampled velocity components in the solver output, installed only after the v1.2 jobs finish.
- L8 (agent): T5 submitted as job 11618046 (no cost smoke: level-1 mesh is only +2.4 % cells). Solver change for (b) compile-checked out of tree (wmake exit 0, only OpenFOAM NamedEnum deprecation warnings; installed lib mtime 2026-10-12 09:04:58 unchanged). Lag defined from consecutive `end_effect_phi_deg` rows (same rotor-plane definition); `inflowRefAngle()` is a 3-D angle against the chord reference, not comparable. Prediction: in quasi-steady axial flow the one-step lag is ~0 (azimuth step 0.43 deg), so (b) is expected to be negligible.
- L9 (user, 2026-10-17): "q esperamos de estas simulaciones?"
- L10 (agent) PRE-REGISTERED PREDICTIONS, written before any result of jobs 11618033-35/11618046:
  T1 (S 7 m/s, v1.2): ALM power ~ -2 % (range -4..0), ASM ~ -2 %, ASM-mesh ~ -5 % (-7..-3); thrust unchanged +-1 point; c_n unchanged
  (0.30 ~ +15 %, 0.95 ~ -12 %). Check: ALM power must rise >= ~6 points vs p22 (-11.0 %), else suspect the render/setup before anything else.
  Open question to raise: judge the 0.30 band on dimensional force or same-reference q (QNORM vs 0.5 rho W^2 explains ~9 points).
  T5 (eps 0.31 m, H): favoured (medium confidence) double counting: tip c_n 0.95 from -14 to -17..-20 %, power -2 -> -3..-4 %;
  stations 0.47-0.80 move < 2 %, thrust < 1 %. Decision rule: |change of tip c_n| < 2 points -> eps is not the lever (deficit is in the
  Glauert factor itself; remaining options are literature corrections, owner decision); drop > 2 points -> double counting confirmed
  (eps-aware correction, owner decision); rise > 2 points -> under-resolution (mesh/eps path).
  T4 (lag): ~0; factor difference < 0.5 %; closes H3b.
- L11 (user, 2026-10-17): "si por favor. ademas recuerda que habiamos hablado de algunas posible mejoras no se si se estan teniend oen cuenta o se olvidaron" (answer to: propose a production-readiness criterion, build the definition-conformance check, update the evidence register).
- L12 (user): "Punto, corregir la definición (Recomendado)" -> v1.2 velocity sampling = point (radius 0); ring = I17. Second definition/default mismatch found while building T10 (v1.1 froze a 3.3/16 ring that no run on disk used, both pillars default 0.0).
- L13 (user, 2026-10-17): "si lo apruebo" (R1-R6). Submitted R1 (level 1/2 at fixed eps, dt 0.0005) and R2 ALM S 5/6/8 m/s with the generic `v1-2-run.slurm`. T4 re-planned: the new library is built into `runs/lib-p23` (inside the repo, git-ignored) and loaded only by `scripts/slurm/v1-2-lag.slurm` (LD_LIBRARY_PATH prepend), so no job has to wait for an install; that 4-rev H run doubles as a regression check against d1-pdrag.
- L14 (agent): R6 tool `scripts/quantifyUncertainty.py` (repeatability from the gitignored Parquet archive turbinesFoam/articles/uae6/parquet: H 7 has 4 files at 0 deg, S 7 has 2; window sensitivity; BEM blockage +1/+2 %). d1-pdrag H 7: power -2.2 % +- 4.0 % (agrees), thrust -0.8 +- 1.6 % (agrees), c_n 0.47/0.80 agree, 0.30 (+13 %) and 0.95 (-14 %) outside, 0.63 (+1.9 %) marginally outside. S 7 p22 (v1.1 polar): power -11.0 +- 3.7 % (outside). Finding: the simulation runs at nominal U = 7.0 m/s while the measured tunnel speed (VTUN) is 7.049 m/s for h0700000 (+0.7 % U, ~+2 % power) and 7.016 for s0700000 (+0.2 %, ~+0.7 % power); rpm and rho are already the measured values. Not in the budget yet: owner decision (deterministic comparison-side correction vs simulating at measured U).
- L15 (user, 2026-10-17): "ok revisa pq no se ejecutan los jobs. q recursos pediste?" -> all PENDING (Priority): sequana_cpu full (0 idle, 236 pending), est. start 19/10 01:08; requests were --ntasks=84 (no --nodes, Slurm places; past runs spread over 2-14 nodes) x 24 h. Owner chose: 11618033/34/35/46 moved to sequana_cpu_bigmem (26 idle nodes, own limit 4 jobs / 846 cpu) and every time limit cut to 12 h (11618057 dt/2: 20 h) via scontrol update. Result within a minute: 4 running on bigmem, 11618055/56 started by backfill on sequana_cpu. Launchers now default to --time=12:00:00. Real run dirs checked: v12 S7 ALM/ASM/ASM-mesh, l1, l2 CONFORM; eps1 non-conforming on meshFactor by design.
- L16 (user, 2026-10-17): "ok deja todo preparado para hacer el analisis en otra sesion" -> HANDOFF section written at the top of this file.
- L17 (user, 2026-10-17): "para terminar esta sesion quiero que elimines todos los resultados y simulaciones que ya no necesitemos para ahorrar espacio" -> inventory 206 GB in 68 run dirs; owner approved the plan (delete 3, slim 43, FLOWUnsteady particle fields); recorded in HANDOFF 3b.
- L18 (user, 2026-10-18): "Continuá P2.3. Leé solo la sección "HANDOFF — resume here" de odd/tasks/p2-3-v12-diagnosis.md (con sed/grep, no el archivo entero) y después las entradas L10-L16 del Log. Primero comprobá el estado de los jobs y la conformidad de cada corrida; analizá contra las predicciones pre-registradas. No implementes nada de la literatura sin mi decisión. Slurm: solo --ntasks."
- L19 (agent, session 4) results vs L10. Jobs: 10 COMPLETED, 11618056 TIMEOUT (resubmitted 11618422). Conformity as expected (eps1 non-conforming by design).
  T1: ALM -2.1 % (pred -2, range -4..0) HIT; ASM -2.1 % HIT; ASM-mesh -8.2 % (pred -5, range -7..-3) MISS by 1.2 points: its polar gain is 6.2 points vs 8.9 for ALM (ASM-mesh spanwise rows are plane-referenced, a known comparison caveat); thrust within +-1 point for ALM/ASM HIT; c_n unchanged HIT; ALM gain >= 6 points HIT.
  T5: prediction (double counting, tip to -17..-20 %) WRONG; tip +0.2 points -> rule "eps not the lever". Power drop -1.9 points fell in the predicted -3..-4 % range but not via the tip (tip F'n unchanged; edgewise force fell inboard, 0.80 Ft -3.5 %).
  T4: HIT (lag ~0, delta F << 0.5 %).
  R2 (no pre-registered prediction): S 5/6/7/8 power error +28.3/+14.2/-2.1/-19.9 %, c_n 0.47-0.80 about +17/+14/+1/-12 %: a monotonic trend with wind speed (alpha), with 7 m/s as the crossing point. Setup checked: freeStreamVelocity, TSR, rpm, rho are the measured ones (archive table), pitch 3 deg for all S files, VTUN only +0.5..+0.8 % above nominal. 5/6 m/s drift but the window trend (S5 P 2.823/2.810/2.802 kW for 4-12/6-12/8-12) moves < 1 point. Experiment cp is the same at 5 and 7 m/s (P scales with U^3) while the run's cp falls 0.452 -> 0.346. At 8 m/s the run's c_n at 0.63-0.80 stops rising (2-D polar saturation; experiment keeps rising). Implication: the 7 m/s agreement of v1.2 is a crossing point, not yet evidence of a correct model across the attached range.
  Tool gaps found: summarizeBands prints PASS/FAIL for drifting windows (comparePhaseVI flags drift, the verdict ignores it: conflicts with S4); the uae6-archive S tables have no qnorm_pa/cth/ctq, so compareSectionLoads/diagnoseElementResiduals cannot run at S 5/6/8; the HANDOFF quantifyUncertainty line for S 5/6/8 needs --experiment-dir data/experiment/uae6-archive.
