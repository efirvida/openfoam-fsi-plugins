# Dynamic Stall Singularity Guard Specification

## Purpose

Defines a minimal guard for the Leishman–Beddoes dynamic-stall fit so that a
singular normal-equation matrix no longer aborts the run. The guard is confined
to `calcK1K2`; it makes the optional high-speed dynamic-stall path runnable and
records the fallback, while the deeper fit-input review remains a separate
change.

## ADDED Requirements

### Requirement: No abort on a singular fit matrix

The system MUST NOT abort with `Singular Matrix` when the Leishman–Beddoes
`calcK1K2` 2×2 normal-equation matrix is singular. The guard MUST detect the
singular or ill-conditioned case and apply a documented fallback instead of
calling `simpleMatrix::solve()` unguarded.

#### Scenario: Guarded run passes the former crash point

- GIVEN a case with `dynamicStall active on` and `LeishmanBeddoesCoeffs`
- WHEN the run reaches the first PIMPLE iteration at `t = 0.008 s`
- THEN the run continues past it without `FOAM FATAL ERROR: Singular Matrix`

#### Scenario: Well-conditioned fit preserved

- GIVEN a well-conditioned fit matrix
- WHEN `calcK1K2` is evaluated
- THEN it returns the same `K1`/`K2` as the unguarded solve

### Requirement: Documented, recorded fallback

The fallback MUST be documented and MUST record which path was taken (the fitted
`K1`/`K2` or the fallback) with a non-fatal warning. The guard MUST be confined
to `calcK1K2`; the other dynamic-stall models MUST be unchanged.

#### Scenario: Fallback recorded

- GIVEN a singular matrix
- WHEN the guard applies the fallback
- THEN a `WarningInFunction` is emitted and the fallback path is recorded

#### Scenario: Blast radius is one method

- GIVEN the change
- WHEN the dynamic-stall models are inspected
- THEN only `LeishmanBeddoes::calcK1K2` is modified and the other models are untouched

### Requirement: Fit-input review remains out of scope

Reviewing the `K1`/`K2` fit inputs (`cm` data, `cmFitExponent_`) MUST remain a
separate follow-up; this change MUST make the path runnable and MUST NOT retune
the fit.

#### Scenario: No fit retuning

- GIVEN the guard
- WHEN it is inspected
- THEN it does not alter the fit inputs and the review is recorded as a follow-up
