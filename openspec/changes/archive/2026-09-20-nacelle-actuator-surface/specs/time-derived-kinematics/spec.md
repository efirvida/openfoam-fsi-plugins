# Time-Derived Kinematics Specification

## Purpose

Defines the idempotent, time-derived rotor kinematics that replace the
incremental `angleDeg_ += omega*dt` accumulator in `turbineALSource`. The rotor
azimuth becomes a pure function of the omega law integrated over `[t0, t]`
(`omega*t` for constant TSR, a closed form for the `tsrAmplitude` oscillation),
with an optional omega override and registry persistence so that
`startFrom latestTime` restarts and preCICE rollbacks resume the correct
azimuth. The default path stays byte-identical: for existing cases with no
override, the CSV output is unchanged from the accumulator.

## Requirements

### Requirement: Time-derived azimuth, not an accumulator

The system MUST compute `angleDeg_` as an integral of the omega law over
`[t0, t]` — `omega*t` for constant TSR, a closed form for the `tsrAmplitude`
oscillation — and MUST NOT accumulate `angleDeg_ += omega*dt`. The azimuth MUST
be a pure function of time and initial state.

#### Scenario: Constant TSR azimuth

- GIVEN a rotor at constant TSR with angular velocity `omega` from time `t0`
- WHEN the azimuth is evaluated at time `t`
- THEN `angleDeg_` equals the integral `omega*(t − t0)` (modulo 360°)

#### Scenario: TSR oscillation closed form

- GIVEN a rotor configured with the `tsrAmplitude`/`tsrPhase` oscillation
- WHEN the azimuth is evaluated at time `t`
- THEN it matches the closed-form integral of the oscillating omega law

### Requirement: CSV output identical to the accumulator for existing cases

For existing cases with no omega override and the existing TSR law, the
time-derived computation MUST produce CSV output identical to the current
accumulator (to floating point), so no behavior change is observable in
existing results.

#### Scenario: Existing-case CSV unchanged

- GIVEN an existing case run against the baseline accumulator and against the new library with no override
- WHEN the two CSV outputs are compared
- THEN the `angle_deg` column (and all other output) matches to floating point

### Requirement: Optional omega override

The system MUST accept an optional omega override source — a `Function1` or a
registry `uniformDimensionedScalarField` (mirroring `fsiOmega/preciceOmega`) —
defaulting to the existing TSR law so results are identical when unset. When an
override is set, the azimuth integral MUST follow the override.

#### Scenario: Default TSR law when unset

- GIVEN a rotor with no omega override
- WHEN the azimuth is evaluated
- THEN it follows the existing TSR law, identical to the baseline

#### Scenario: Override drives the azimuth

- GIVEN a rotor with an omega override set
- WHEN the azimuth is evaluated
- THEN it follows the integral of the override omega law

### Requirement: Registry persistence for restart and rollback idempotency

The system MUST register `angleDeg_` (and the omega override field, when used)
as a `uniformDimensionedScalarField` written to the time directories, so a
`startFrom latestTime` restart and a preCICE rollback restore the azimuth
idempotently.

#### Scenario: Angle field written

- GIVEN a running rotor
- WHEN a time step writes output
- THEN an `angleDeg_` `uniformDimensionedScalarField` is present in the time directory

#### Scenario: Restart resumes the same azimuth

- GIVEN a case that was interrupted and restarted with `startFrom latestTime`
- WHEN the rotor resumes
- THEN the azimuth continues from the persisted value, not from zero

#### Scenario: Rollback idempotency

- GIVEN a coupled run that rolls back to a previous time
- WHEN the rotor state is re-read
- THEN `angleDeg_` returns to the value persisted at that time

### Requirement: `angleDeg()` accessor

The system MUST expose an `angleDeg()` accessor returning the current azimuth in
degrees, for downstream consumers (the S3 FSI seam).

#### Scenario: Accessor returns the azimuth

- GIVEN a rotor with a known azimuth
- WHEN `angleDeg()` is called
- THEN it returns the current azimuth in degrees

### Requirement: Existing suite regression gate

The kinematics refactor MUST leave the existing pytest suite passing unchanged.
The acceptance is idempotency, not a behavior change.

#### Scenario: Existing tests pass unchanged

- GIVEN the new library with the time-derived kinematics
- WHEN the existing pytest suite runs
- THEN it passes unchanged (CSV columns match the baseline)
