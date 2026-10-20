# Phase VI paper-like ALM pilot preparation
Prepare isolated control/paper-like ALM cases and a documented reconstruction of the article mesh; do not submit or simulate.
Branch: `feat/phasevi-paper-yaw-pilot`; delivery: `single-pr` (forecast ~650 authored lines; explicit user choice, no publishing authorized); checks: `python3 -m pytest turbinesFoam/tests tools/tests -q`.

## Specs
S1. User: "recomiendo eso, ademas recomiendo utilizar tambien su misma configuracion de malla, para que ese dt sea valido". Prepare the accepted comparison using the article's reported mesh criteria and check timestep compatibility rather than transplanting its timestep onto the existing mesh.
S2. User context, verbatim:

> es verdad q no hay datos como para comparar todo, pero creo que si esta todo lo necesario para comparar formulaciones, sabiendo que el del articulo presenta una curva de potencia bastante proxima a la experimental, aunque sin saber cual experimento. mis preguntas:
>
> 1- tenemos implementado elmismo modelo de ALM?
> 2- podemos lanzar unas corridas con la misma configuracion?

Accepted proposal: isolated ALM at 7 and 13 m/s, paired aerodynamic control versus Shen + LeishmanBeddoesSGC + 16-point sampling, otherwise matched numerical conditions; preparation only, no Slurm submission.
S3. Human selected "Simetría, siguiendo la figura — recomendado" (answer token `paper_mesh_follow_figure_symmetry`). Apply symmetry to the lateral, upper and lower boundaries; disclose contradiction with no-slip prose.

### Engineering boundaries and explicit assumptions
- Reference: Arabgolarcheh et al. (2021), DOI 10.1155/2021/9978134, local PDF `turbinesFoam/articles/Numerical_Study_of_a_Horizontal_Wind_Turbine_under.pdf`.
- Reported: four successive dyadic mesh zones, cubic/hexahedral cells, rotor spacing <0.125 m, section 24.4 x 36.6 m, inlet/outlet 2D/8D, approximately 400k cells, dt=0.001 s, Sequence S, 71.63 rpm, pitch3 degrees. Exact zone bounds and selected exact spacing are unpublished; reconstruction geometry must be explicit and must not be fitted merely to400k.
- Keep `config/case.yaml`, generated baseline `case/`, v1.2 definition, existing shared Python/C++ implementation and unrelated untracked files unchanged. New standalone preparation package, focused public-interface tests, README and root changelog only.
- Reuse existing configuration, geometry and renderer helpers without modifying their semantics. Document missing epsilon/polar/Reynolds/SGC coefficients as assumptions; distinguish physical sampling radius from units of epsilon.
- Do not claim an exact paper mesh. If the available mesh-generation route changes nonconformal topology or introduces transition cells, say so prominently and record planned versus actual resolution separately.
- Preparation is not execution readiness. Preserve the cylinder profile and flag its active-SGC compatibility risk; no invented per-profile override or untested solver fix. No automatic mesh execution, solver calls, environment setup, job submission, or destructive overwrite.
- Include timestep displacement/rotor-cell ratio, angular step and nominal advective-Courant estimates, explicitly not measured Co or temporal-convergence proof. These calculations belong to a retained tool, never ad-hoc analysis.
- Public preparation/check/report interface should fail clearly on invalid/conflicting inputs, preserve baseline files, and make identical mesh/numerics across all four cases auditable. Tests cover requested behaviors and read-only/rejected-operation effects.

## Tasks
T1 | S1-S3 | delegated: context-backstop; one coherent preparation unit with tests/docs | done | commit: 629445b | Implemented four-case v2 preparation, mesh/report/provenance and public-interface tests; correction RED 6 failed/10 passed, GREEN 16 passed in14.56s; public prepare/check/report exit0.
T2 | S1-S3 | inline parent: structural readback, spot check, native assessment and work-unit commit | done | commit: 629445b (evidence closed in following tracking commit) | Parent corrected-output --check exit0; diff checks clean; base-only suite failures reproduced; committed-range native assessment unavailable, medium writer-self-verification plan retained. No job submission or execution approval.

## Log
L1. User request, verbatim: "recomiendo eso, ademas recomiendo utilizar tambien su misma configuracion de malla, para que ese dt sea valido".
L2. Prior accepted question, verbatim:

> es verdad q no hay datos como para comparar todo, pero creo que si esta todo lo necesario para comparar formulaciones, sabiendo que el del articulo presenta una curva de potencia bastante proxima a la experimental, aunque sin saber cual experimento. mis preguntas:
>
> 1- tenemos implementado elmismo modelo de ALM?
> 2- podemos lanzar unas corridas con la misma configuracion?

L3. Boundary decision: user selected "Simetría, siguiendo la figura — recomendado" via `paper_mesh_follow_figure_symmetry`.
L4. Mapping: task mvgsn2uc-3-cdff established unpublished zone bounds and unresolved figure/prose wall conditions. Assumption challenge mvgsy261-4-0vpe found unsafe cylinder static-fit paths under active SGC but no reproduced runtime failure; preparation requires no shared-source edits. Isolated readiness must remain explicit. Module load exposed wmake but not pimpleFoam; no builds/meshes/simulations performed.
L5. Initial Git: main, unrelated untracked `tools/__pycache__/`, `tools/tests/__pycache__/`, `turbinesFoam/validation/phaseVI/scripts/slurm/resume-run.slurm`. Created feature branch; preserve these files.
L6. Human selected "Un solo PR — menos recomendado" (`single-pr`) for oversized delivery. This resolves organization only, not push/PR/merge authority; suppress further chain prompts.
L7. Worker mvgt8di0-5-fayu initially passed11focusedtests. Parent readback found avoidable published-setting mismatches; one correction batch mvgu1t3y-6-1e6v changed calcAlphaEquiv=true, PBiCG/DILU, nu1.46e-5, rhoRef1.23 metadata and nine-input provenance. RED6failed10passed; GREEN16passed14.56s. Corrected output `runs/paper-yaw-2021-v2/`; old output preserved as superseded. No baseline/shared-code edits.
L8. Fullsuite job-1 exited1:643passed,3skipped,2failed in696.95s. Both yaw/pitch header failures at test_phasevi_yaw_pitch_reference.py:107 reproduced on pristine base b017413306d7d7429a87812a874b0f4e88ce1e57 (2failed0.37s,exit1), in runs/paper-base-check.OXgLLV. Unrelated reference tables remain unchanged. Fullsuite not rerun after isolated correction; focused suite covers corrected code.
L9. Planned rotor widths(0.099781746,0.098387097,0.099456522)m; nominal3,811,364cells, not paper400k or measured. dt.001s gives step.42978deg, tip displacement.037722912m, displacement/minh.383413199 and nominalCo.071147541/.132131148 at7/13m/s. Conformal transition topology differs from paper. execution_ready=false: actualmesh/checkMesh, measuredCo/time and rootSGC compatibility unproved. No meshes or simulations executed.
L10. Initial native assessment could not assess untracked scope; returned medium self-verification plan with no independent verifier. Assess committed normalized candidate after the work-unit commit; do not infer approval.
L11. Source work unit committed as629445b (`feat(phasevi): prepare isolated paper-like ALM pilot`):7files,807insertions, one coherent additive preparation behavior with tests/docs; user-selected single-pr accepts the review workload, no artificial code split. Parent reran corrected-output --check exit0 and git diff checks passed. Baseline/shared code and unrelated untracked paths unchanged. Risk: none (isolated additive preparation; no existing command/parser/helper changed).
L12. Post-commit ASSESS with baseRef=b017413306d7d7429a87812a874b0f4e88ce1e57 and committedOnly=true remained unassessable because native requires an explicit untracked declaration. Returned plan:medium, writerSelfVerification=true, independentVerifier=false, RDDon. No reviewDue/approval/receipt supplied; no ordinary review started or authority consumed. Shell mode-status command also unavailable(exit127). Preserve unrelated files rather than deleting them or inventing review authority. Native assessment unavailability is disclosed, not a pass.
L13. Preparation scope is closed; execution remains outside authorization and blocked on actual mesh quality/spacing, measuredCo/time evidence and rootSGC compatibility. Final output is runs/paper-yaw-2021-v2; no mesh generated, Slurm submitted, push or PR created. Fullsuite remains2knownbasefailures/643passed/3skipped; correctedfocused16passed. Tracking-only closure commit follows629445b.
