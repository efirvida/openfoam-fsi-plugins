# Phase VI Proxy Verification Specification

## Purpose

Defines the committed short-run proxy used to verify the rotational-augmentation
fix cheaply: a 0.25-revolution D/32 case at 7 and 13 m/s on the authorized
development queue, with a control / augmentation-on / augmentation-on + root-off
variant matrix, fail-loud pass/fail criteria, and a prepared-only boundary for
the production campaign.

## ADDED Requirements

### Requirement: Committed 0.25-rev D/32 proxy harness

The package MUST include a committed harness that prepares and runs the
0.25-revolution D/32 proxy at 7 and 13 m/s on the authorized development queue,
and MUST run the variants serially because the development queue has
`MaxSubmit=1`. Each variant MUST run in a self-contained package copy.

#### Scenario: Harness present and runnable

- GIVEN the committed harness
- WHEN it is invoked in check or dry-run mode
- THEN it reports the 7 and 13 m/s, D/32, 0.25-rev configuration without submitting a production job

#### Scenario: Serial dev-queue execution

- GIVEN the `MaxSubmit=1` development queue
- WHEN the variants are launched
- THEN they are chained serially rather than submitted as a parallel array

### Requirement: Variant matrix and control gate

The harness MUST run exactly three variants — `control` (augmentation off, root
on), `augmentation-on` (root on), and `augmentation-on + root-off` — sharing all
other keys. The `control` MUST reproduce the converged U13 failure
(`cp ≈ −0.0459`) before any other variant is trusted.

#### Scenario: Three variants share all keys but the toggles

- GIVEN the harness configuration
- WHEN the three variants are rendered
- THEN they differ only in the augmentation switch and the root-effect setting

#### Scenario: Control must reproduce the failure

- GIVEN the control variant at U13
- WHEN its integrated `cp` is compared with the converged baseline (`cp ≈ −0.0459`)
- THEN it reproduces the failure within the short-window tolerance before variants are interpreted

### Requirement: Fail-loud success criteria

The primary success signal MUST be the integrated turbine `cp`/`ct`/torque over
the short window, not the spanwise `c_ref_t` magnitude. The `c_ref_t` sign MUST
be the secondary signal. At U13 augmentation-on MUST turn mid-span `c_ref_t`
clearly positive and `cp`/`ct` positive; at U7 the augmentation-on + root-off
ablation MUST shrink the −16 % power/torque deficit toward or inside the ±15 %
band. The harness MUST fail loudly when a criterion is not met.

#### Scenario: Primary integrated signal

- GIVEN the U13 augmentation-on variant
- WHEN its integrated `cp`/`ct`/torque are evaluated
- THEN they are positive and are reported as the primary signal

#### Scenario: Secondary sign signal

- GIVEN the U13 augmentation-on variant
- WHEN the spanwise `c_ref_t` sign is inspected
- THEN mid-span `c_ref_t` is clearly positive

#### Scenario: U7 deficit reduced

- GIVEN the U7 augmentation-on + root-off ablation
- WHEN its power/torque deficit is compared with the −16 % baseline
- THEN the deficit shrinks toward or inside the ±15 % band

### Requirement: Prepared-only production boundary

No automated step of this change MUST submit, cancel or modify a production job.
The production campaign MUST stay prepared-only and the suspended production
arrays MUST remain read-only baselines. The `c_ref_t` versus measured CT
definitional fix MUST remain out of scope, recorded as a documented caveat.

#### Scenario: No production submission

- GIVEN the proxy harness and the production preparation
- WHEN this change completes
- THEN no production job has been submitted, cancelled or modified

#### Scenario: Definitional mismatch documented, not fixed

- GIVEN the spanwise comparison
- WHEN the ≈2× `c_ref_t` versus measured CT mismatch is inspected
- THEN it is recorded as a documented comparison caveat and no definitional fix is applied by this change
