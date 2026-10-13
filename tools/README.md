# Repository tooling

Helper scripts for working on this repository. They are not part of any plugin
build and are not installed anywhere.

## `session_cost.py` — what an agent session actually costs

```sh
python3 tools/session_cost.py            # current repository, human report
python3 tools/session_cost.py --json     # machine-readable
python3 tools/session_cost.py --session 2026-10-01T09-04
```

Reads the Pi session transcripts recorded for this project
(`$PI_CODING_AGENT_DIR/sessions`) and reports the real token and cost footprint:
per-session and total input/output/cache tokens, the cost split, how much of the
input is concentrated in full prompt-cache misses, and what occupies the largest
session's context. Read-only.

The point is that raw token counts are not the cost. In the recorded baseline,
1.18 B cache-read tokens cost $3.59, while 303 of 3292 calls carried 96.4 % of
the uncached input tokens and 70 % of the bill: those are whole contexts
re-billed at full price after the provider cache expired. Retained reasoning
blocks and repeatedly re-sent context drive that, not tool output volume.

Exit codes: `1` no transcript found for the project, `2` transcripts found but
no `usage` records (schema drift — no measurement is claimed).

## Where the domain tools live

Campaign-state reading and comparison live next to the cases they serve:

- `turbinesFoam/validation/tools/case_state.py` — how far a run got: rows,
  time span, revolutions, last-window means of the run's own columns. Read-only,
  no reference data, no metric redefinition.
- `turbinesFoam/validation/*/scripts/compare*.py` — every quantity calibrated
  against the experimental data. Use these for anything you intend to report.
- `turbinesFoam/validation/*/tools/generate_case.py` — case rendering, with a
  non-destructive `--check`.
