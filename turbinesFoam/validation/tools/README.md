# Shared validation tools

Tools here serve more than one campaign. Tools used by a single campaign live in
that campaign's own `tools/` directory (`phaseVI/tools/`, `iea15mw/tools/`, ...),
and runner/analysis scripts live in `scripts/`.

Before writing a new analysis, check this list and run
`python3 tools/analysis_gap.py --min-count 3` from the repository root, which
reports which analyses keep being re-derived inline.

## The boundary that matters

Two kinds of code exist here, and they must not be mixed:

| Kind | Owns | Must not |
| --- | --- | --- |
| **Reader** | what a run wrote: rows, time span, raw column values | compute or reinterpret any calibrated quantity |
| **Metric producer** | a quantity defined against a reference | exist in two places |

`phaseVI/scripts/comparePhaseVI.py` owns every quantity calibrated against the
NREL report (`q_dyn`, `Q`, `P`, `cp`, `ct`, `T_blade`, the spanwise
`c_ref_n`/`c_ref_t` comparison) and documents its exit codes. `compare_spanwise.py`
and `compareNacelle.py` own theirs. **A reader never re-derives those.** A second
definition that drifts silently is worse than no tool.

## Tools

### `case_state.py` — how far did a run get?

```sh
python3 turbinesFoam/validation/tools/case_state.py runs/alm-U7-coarse-s0
python3 turbinesFoam/validation/tools/case_state.py --mean-last 400 --rpm 71.878 runs/*
python3 turbinesFoam/validation/tools/case_state.py --json runs/alm-U7-coarse-s0
```

Reports the `postProcessing` source used, its row count, the first and last
`time`, revolutions when `--rpm` is supplied, and the mean of the last
`--mean-last` rows of each numeric column present. `angle_deg` is excluded from
means because it is a wrapping azimuth.

Deliberately a pure reader: no `cp`, `P`, `Q` or `T`, no experimental reference
data, absent columns omitted rather than synthesised, and the run is never
modified (there is a test that verifies this byte for byte).

Exit codes: `1` run directory missing, `2` no `postProcessing` output yet.

Related tools outside this directory:

| tool | answers |
| --- | --- |
| `phaseVI/scripts/comparePhaseVI.py` | simulation vs measured WDH data, with metric definitions fixed against the NREL report |
| `iea15mw/scripts/compare_spanwise.py` | spanwise diagnosis of an IEA 15 MW ALM run, and a two-run per-band comparison (`--compare-with`); `--references` adds each reference model's band stations/means and its `cn`/`ct` ratios **to run A** (`--reference-source`, `analysis/spanwise-references.csv`) |
| `iea15mw/scripts/station_ratio.py` | ratio of two `compare_spanwise.py --out` profiles pooled in r/R bands, including the root and tip bands that `--compare-with` leaves out |
| `iea15mw/scripts/import_olaf_reference.py` | the `olaf-fvw` OLAF free-vortex-wake spanwise block in `analysis/spanwise-references.csv` (`alpha_deg`/`cn`/`ct` per node), regenerated from the gitignored OpenFAST CSV |
| `nacelle-asn/scripts/compareNacelle.py` | nacelle actuator-surface comparison |
| `phaseVI/tools/generate_case.py` | renders the committed case; `--check` is non-destructive |
| `phaseVI/tools/case_config.py` | loads and validates `config/case.yaml` |
| [`phaseVI/paper-yaw-2021/prepare.py`](../phaseVI/paper-yaw-2021/README.md) | preparation-only `--prepare` / read-only `--check` / `--report`, all with required `--output DIR`; four matched 7/13 m/s control/paper-like ALM dictionaries, input/dictionary hashes and nominal mesh/timestep arithmetic; never execution approval or a P/Q/Cp producer |

### `window_response.py` — what did a model switched on at a restart do, window by window?

```sh
python3 turbinesFoam/validation/tools/window_response.py --from-deg 7200 --to-deg 7330 \
    --window-deg 60 runs/iea15mw-screen-m3-l2 runs/iea15mw-l2-ds
```

Mean `cp`/`cd`/`ct` of each run in windows of the cumulative `angle_deg`, so
runs that share a restart state line up window by window (`--window-deg 120` is
one blade-passing period of a three-bladed rotor). Use it where
`rev_history.py` is too coarse: a tip or end-effect model judged over a fraction
of a revolution. Reader only: the columns are the module's own.

### `run_parallel_steps.sh` — several single-node steps inside one job

```sh
run_parallel_steps.sh -n 48 -- "cmd for step 0" -- "cmd for step 1"
```

Runs each command concurrently on its own node of the Slurm allocation and
returns the number of failed steps. A step sees `STEP_NODE`, `STEP_RANKS` and a
`TURBINE_MPI_MCA` that confines its `mpirun` to that node (multi-node
`MPI_Init` was intermittent on this cluster). `parallel_steps_smoke.slurm` is
the development-partition check of the pattern.

### `rev_history.py` — what did the run converge to, revolution by revolution?

```sh
python3 turbinesFoam/validation/tools/rev_history.py runs/iea15mw-screen-m3-l2
python3 turbinesFoam/validation/tools/rev_history.py --window 2 --csv /tmp/dt2.csv runs/iea15mw-screen-m3-l2
python3 turbinesFoam/validation/tools/rev_history.py runs/iea15mw-screen-m3-l2 runs/iea15mw-l2-ra
```

Reads **every** split history of each run and reports the mean `cp`/`ct` per
revolution, the change from the previous revolution, and the plateau and mean
drift of the tail; `--csv` writes the series and several runs are compared at the
end, which is what a model or mesh A/B needs.

Why the union: a resumed run writes a *new* `postProcessing/turbines/<timeName>/`
named after its start time, so one continuous run lands in several folders whose
names sort wrongly as text (`"31.9209"` after `"159.6232"`) and whose rows per
revolution differ when the time step changes. The revolution is rebuilt from the
cumulative `angle_deg`, which keeps growing across a restart; reading one folder
alone reports a fraction of the run, and that is the mistake this removes.

A revolution whose row count falls below half the median is a **stub** -- the
single row a finished run leaves at `endTime`: it is marked `parcial` and kept out
of the plateau and the drift, because averaging it in invents a level and a
change the run never held.

Exit codes: `1` no `postProcessing/turbines` under the run dir, or a `turbine.csv`
missing a column.

### `induction_closure.py` — how far is the applied thrust from `2 rho U² a (1-a)`?

```sh
python3 turbinesFoam/validation/tools/induction_closure.py write-dict \
    --origin 0 0 12.192 --axis 1 0 0 --wind 1 0 0 --radius 5.029 --out system/inductionClosureSample
postProcess -func inductionClosureSample -latestTime
python3 turbinesFoam/validation/tools/induction_closure.py analyse \
    runs/X/postProcessing/inductionClosureSample runs/X \
    --rho 1 --u-inf 7 --radius 5.029 --wind 1 0 0 --origin 0 0 12.192 --axis -1 0 0 --t-from 2.9 --t-to 3.339 --json --csv /tmp/closure.csv
```

Momentum closure of an actuator rotor (Madsen 1988). `write-dict` writes a
`sample` dictionary of `circle` sets (uniform `dTheta`, raw format) at N radii
between 0.05 R and 1.3 R on planes at signed offsets along the wind (default 0,
-0.25, -1 R; negative = upstream). `analyse` takes the azimuthal mean of the
axial velocity per ring (`a = 1 - u/U_inf`) and compares, per element radius, the
thrust the blades applied per unit radius (sum over blades of the time-mean
`fx` / `dr`, element histories united in numeric folder order; the element
radius is its distance from the rotor axis, from the `x y z` columns, since
`root_dist` is a 0..1 span fraction and never read) with
`2 rho U_inf² a (1-a) 2 pi r`. It reports a ratio per radius and per plane plus
the integrated ratio, **never a pass/fail**: the relation degrades with loading,
and rows with `a >= 0.4` are flagged as outside its validity. Without
`--t-from`/`--t-to` the last half of the available span is used and the output
says so.

The elements are not uniformly spaced (the blade is a list of geometry nodes,
some 13 mm apart, each segment holding `nElementsPerSegment` equal elements), so
pass `--elements-per-segment n` (Phase VI: 2): the width of each element comes
from its own segment, and a tiling self-check (outer edge of segment k = inner
edge of segment k+1, in R) warns if `n` is wrong. The default `n = 1` falls back
to neighbour midpoints and warns that this is unreliable. The output also prints
the sum of element forces over blades without `dr`.

Not every blade writes element CSVs (Phase VI: only blade1), so pass
`--n-blades N` (Phase VI: 2): the force is the mean over the blade files found
times N (valid for an axisymmetric time-average over whole revolutions), and the
number found is printed next to N. If it is omitted and only one blade file is
found, a WARNING says the result covers one blade only.

`--rho` is required. The incompressible solver writes kinematic forces
(N/rho), so the Phase VI case uses `--rho 1`; a physical density applies only
to compressible runs whose CSV forces are in newtons.

Exit codes: `1` a sample directory, run directory, ring file or element CSV is
missing; `2` usage error (e.g. `--rho` omitted); `3` unusable data (empty time
window, malformed file); `4` element count not a multiple of `--elements-per-segment`; `5` more blade files than `--n-blades`.

## Adding a tool

Follow the `validation-analysis-tools` skill. The short form: check what exists,
decide reader vs metric producer, write the test first in `turbinesFoam/tests/`,
implement it read-only with typed errors, then register it here, in
`TOOL_COVERAGE` inside `tools/analysis_gap.py`, and in the root `CHANGELOG.md`
with the numbers observed on a real run.

### `pdf_find.py` — what does the reference say?

```sh
python3 turbinesFoam/validation/tools/pdf_find.py turbinesFoam/articles/29955.pdf "Sequence [A-Z]\b" --context 1
python3 turbinesFoam/validation/tools/pdf_find.py turbinesFoam/articles/29955.pdf --page 27
```

Searches the text layer of a reference PDF (case-insensitive regular expression) and prints
each match with its 1-based page and line, or prints one whole page. It reads text only: a
scanned PDF (for example the Madsen 1988 chapter) has no text layer and exits 1 instead of
guessing. Exit codes: 0 match or page printed, 1 unreadable / no text layer / page out of
range, 2 no match.
