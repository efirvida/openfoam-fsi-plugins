---
name: validation-analysis-tools
description: Promote a repeated inline analysis into a reusable, tested repository tool. Use when a quantity from run output or reference data is needed and no existing tool produces it, or when about to type `python3 -c`, a heredoc, or an `awk` one-liner over `postProcessing`, `data/experiment`, or a paper PDF.
---

# Promoting an inline analysis into a repository tool

`of-plugins` is validated against reference data, so an analysis that exists only
as a throwaway snippet is a reproducibility defect: it re-types constants that
already live in `data/experiment/`, it cannot be reviewed, and it cannot be
tested. It is also retained in the agent's context for the rest of the session.

## The rule

**Never compute an analysis inline.** If a needed quantity has no producer
already, write a script, run the script, keep the script.

`python3 -c ...`, `python3 - <<'PY'`, `awk '...'`, and scratch files under `/tmp`
are all inline for this purpose. Running a committed script is not.

## Step 1 — Check what already exists

Before writing anything:

```sh
python3 tools/analysis_gap.py --min-count 3    # what keeps being re-derived
```

It groups recurring inline shapes by the evidence they touch and marks the ones
an existing tool already answers. Then read `turbinesFoam/validation/tools/README.md`
for the current tool list.

If a listed tool nearly fits, **extend it** — a new flag on an existing reader is
worth more than a second reader that partially overlaps.

## Step 2 — Decide which kind of tool it is

This decision is the whole point. There are two kinds, and mixing them is how
wrong physics gets published:

| Kind | Owns | Must not |
| --- | --- | --- |
| **Reader** | echo what a run wrote: rows, time span, raw column values | compute or reinterpret any calibrated quantity |
| **Metric producer** | a quantity defined against a reference (NREL report, BEM, experiment) | exist in two places |

Calibrated quantities — `cp`, `ct`, `P`, `Q`, the spanwise `c_ref_n`/`c_ref_t`
comparison — are already defined once against the NREL report in
`turbinesFoam/validation/phaseVI/scripts/comparePhaseVI.py`. That file is the
single source. A reader must **not** re-derive them; a second definition that
drifts silently is worse than no tool.

If you think a metric definition is wrong, fix it there, with the reference in
hand — do not add a second one.

## Step 3 — Write the test first

Tools live next to the cases they serve, tests live in `turbinesFoam/tests/`, and
they are loaded by path per the existing convention:

```python
case_state = _load("case_state", PACKAGE / "validation" / "tools" / "case_state.py")
```

Observe the test fail before the module exists. `tools/` scripts are tested
separately: `python3 -m pytest turbinesFoam/tests tools/tests -q`.

Cover the properties that keep a reader honest, not just the happy path:

- the arithmetic (windowing, averaging, clamping);
- **omission**: an absent column is reported absent, never synthesised;
- **non-mutation**: the run directory is byte-identical after a read;
- typed errors with distinct exit codes (missing directory vs nothing written yet);
- the CLI contract (`--json` parses).

## Step 4 — Implement it small

- Read-only. A reader that can write to a run directory is a liability.
- Open with `csv.DictReader`, print the run's own column names; do not rename them.
- Report a mean only over a window you can name; never average a wrapping
  quantity (compare `UNSUMMARISED_COLUMNS` in `case_state.py`).
- Fail loudly and early: `FatalErrorInFunction`-style typed errors, not `None`.
- No network, no state between runs, no cached results. The inputs change during
  a campaign.

## Step 5 — Register it, then verify it against a real run

A tool nobody finds does not exist. Three places, all required:

1. `turbinesFoam/validation/tools/README.md` — one row: what it answers.
2. `TOOL_COVERAGE` in `tools/analysis_gap.py` — the evidence tags it now answers,
   **kept narrow**. Over-claiming coverage hides the next real gap.
3. `CHANGELOG.md` — a `### Tooling` entry in `Files:` / `Problem:` / `Fix:` form.

Then run it against a real run directory and put the observed numbers in the
changelog entry. "Tests pass" is not evidence that the numbers are right.

## Anti-patterns

- Reaching for `python3 -c` "just to check one value". Write the reader, run the
  reader — the second time you need it, it already exists.
- Copying `meas = {7: (5.9458, 789.8572, ...)}` into a new script. Those literals
  belong to `data/experiment/`; load them.
- Adding a metric to a reader because it was convenient. See Step 2.
- Making the tool clever enough to infer what to report. Explicit flags beat
  inference when the output justifies a physical claim.
