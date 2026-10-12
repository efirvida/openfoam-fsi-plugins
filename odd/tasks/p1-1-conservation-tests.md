# P1.1 — Conservation tests per method

Plan: `odd/tasks/validation-master-plan.md` (P1.1). Scout map: Engram `odd/p1-1-conservation-tests/tasks`.

Gap (from the scout, 2026-10-12): ASM+mesh force conservation is covered in
`tests/test_blade_surface.py`; the three assertions below are missing.
Deposited field integral = `volFieldValue volIntegrate` on `force.<name>`;
sign: the field is the force on the flow, so `integral = -sum(element forces)`.

- [x] **T1** Baseline: confirm OpenFOAM runs in this env and the existing
      `test_blade_surface.py` / `test_asm.py` pass before any change (observed, not assumed).
      Result: 13 passed; the 2 `parallel` tests fail because `decomposePar` loads `libkahipDecomp.so`
      and `libkahip.so` is not installed in this module (environment, not the repo). Env file: `/tmp/ofenv.sh`
      (Int64 `WM_OPTIONS`, `PATH` with the Int64 bin, `FOAM_USER_APPBIN` for `test_asm_prefilter`).
- [x] **T2** ALM: `|integral(force.<name>)| / sum(element f)` = 1 within 1e-3 for a
      multi-element Gaussian-strip case (existing coverage is one cylinder element).
- [x] **T3** ASM: same identity for `elementType actuatorSurfaceElement`, `nChordwise 5`
      (RED check: the P0.1 truncation bug must make it fail).
      Result (tests `test_multi_element_{alm,asm}_conserves_force`, 4 lifting elements on the
      `bladeSurface` fixture, serial): integral/sum = 0.999795 (ALM), 0.999574 (ASM), rtol 1e-3.
      RED observed: reverting the P0.1 fix gives 0.2303 for ASM (ALM unchanged 0.9998).
- [ ] **T4** ASM+mesh: moment about the rotor axis of the deposited field vs node
      moment / torque. Measure the first-moment tolerance first, then fix it.
- [ ] **T5** Changelog entry, mark P1.1 in the master plan, full relevant suite green.
