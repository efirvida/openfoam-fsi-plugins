# P1.3 — `meshFactor` is inert in the ASM+mesh cosine kernel: decision

Plan: `odd/tasks/validation-master-plan.md` (P1.3). Issue: `odd/issues/asm-mesh-residual-vs-alm.md`.

**Decision (agent, physical judgment, reversible): keep it inert and say so; do not honour it.**
The default ASM+mesh kernel is the four-point cosine kernel of Yang & Sotiropoulos (support
`2.5*h`, `h = cbrt(V)` of the node's cell, `bladeSurfaceSampler::nodeSupport`). The paper
gives no free width for it. Honouring `meshFactor` would add a tuning parameter to a method
the Model Definition defines without one ("one definition", no calibration), and would
silently change every frozen result that already renders `meshFactor 2` (mesh ladder,
IEA). `kernel gaussian` stays the documented ablation where `meshFactor` acts.
The code already prints `meshFactor` only in gaussian mode; the defect is the claim around it.

- [x] **M1** Pin the design with a test: in `kernel cosine` the deposited field is identical for
      `meshFactor` 1 and 3 (rtol 1e-12); in `kernel gaussian` it differs. RED is not available
      (behaviour does not change); state the defect class it catches instead.
- [x] **M2** Say it where the knob is advertised: `--mesh-factor` help and docstring in
      `validation/iea15mw/tools/generate_case.py`, the matching text in
      `validation/phaseVI/tools/generate_case.py`, and `turbinesFoam/README.md`.
- [x] **M3** Record the decision in the Model Definition and the master plan; close the side
      defect in the issue.

Result: `test_mesh_factor_acts_only_in_gaussian_kernel` (4 serial runs): max relative difference of the
deposited field, `meshFactor` 3 vs 1: cosine 0 (bit-identical), gaussian 0.953. Docs fixed in the two
case generators and in `turbinesFoam/README.md`; 194 tests pass (`-k "not parallel"`).
