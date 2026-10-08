#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# IEA 15 MW — decomposition-METHOD comparison (not a scaling study).
#
# The scaling curve does not need repeating per method: if a method is more
# efficient at three densities it is more efficient at ten, so this compares the
# methods at THREE points only -- 50k, 30k and 20k cells per core on the medium
# D/48 mesh (6 508 528 cells):
#
#   ranks   cells/core    n (x y z) for `simple` (domain aspect 6:10:2.5)
#    128      50 848      4 8 4
#    216      30 132      6 9 4
#    324      20 088      6 9 6
#
# Methods: scotch (graph cell balance) and the two coordinate splitters simple and
# hierarchical, BOTH of which require the initial n (x y z) -- passing no n to
# hierarchical is a decomposePar failure, which is why the first pass has no
# hierarchical rows. `n` is validated to multiply to the
# rank count by the generator, so a typo is a generation error and not a silently
# bad decomposition.
#
# Why it is worth measuring: the mesh is a STRUCTURED but graded blockMesh, and the
# coordinate splitters usually give contiguous subdomains with less halo and better
# cache locality there, while scotch pays for balancing an irregular graph. Neither
# dominates in advance -- and scotch was never chosen, it was hardcoded.
#
# Metrics per (method, density): the SAME median of the ExecutionTime deltas as the
# scaling study (16 steps = 0.1 revolution), the decomposePar seconds (read from
# its own log) and the wall seconds. The mesh is built once and symlinked into
# every run dir, because decomposePar is the only rank-dependent step.
#
#   cd turbinesFoam/validation/iea15mw
#   sbatch scripts/slurm/decomp-method-study.slurm
#
# ONLY --ntasks, so Slurm packs it into whatever holes exist. Slices of the
# development queue's 20-minute cap with self-requeue: the sweep skips the pairs
# already in the CSV, so a requeued job continues where the previous slice stopped.
#SBATCH -p sequana_cpu
#SBATCH --ntasks=324
# The 20-minute cap belonged to the development queue and is gone: the runs stay
# on sequana_cpu, whose limit is the association's (4 days), so they finish in one
# allocation instead of slicing and waiting for a requeue between slices. --requeue
# and the safety requeue at <240 s stay only so a slow slice cannot be killed
# mid-point; in a four-hour allocation they should never fire.
#SBATCH --time=04:00:00
#SBATCH --requeue
#SBATCH -J iea15mw-decomp
#SBATCH -e %j.err
#SBATCH -o %j.out

set -u
cd "${SLURM_SUBMIT_DIR:-$PWD}"

# method ranks n
# GROUPED BY DENSITY, not by method: the allocation (and therefore the placement)
# changes between slices, so a density's three methods must be measured inside the
# same slice or their ratio carries the placement difference instead of the method
# difference. With a four-hour limit they all fit in one allocation anyway.
PAIRS="${TURBINE_DECOMP_PAIRS:-\
scotch 128 - | simple 128 4x8x4 | hierarchical 128 4x8x4 | \
scotch 216 - | simple 216 6x9x4 | hierarchical 216 6x9x4 | \
scotch 324 - | simple 324 6x9x6 | hierarchical 324 6x9x6}"
SUMMARY="runs/iea15mw-decomp-summary.csv"
TEMPLATE="runs/iea15mw-decomp-mesh"
PYTHON="${PYTHON:-/scratch/leahk/eduardo.donestevez/venv/bin/python}"
CELLS=6508528

echo "=== nodos: $(scontrol show hostnames "$SLURM_JOB_NODELIST" | tr '\n' ' ')"
lscpu | grep -E "^Model name|^CPU\(s\)|^Core\(s\)|^Thread"
echo "=== pares metodo/densidad: ${PAIRS} ==="
mkdir -p runs
[ -f "$SUMMARY" ] || echo "method,ranks,cells_per_rank,steps,median_step_s,total_s,decompose_s" > "$SUMMARY"

left_s() {
    local e s
    e=$(scontrol show job "$SLURM_JOB_ID" 2>/dev/null | tr ' ' '\n' | sed -n 's/^EndTime=//p' | head -1)
    s=$(date -d "$e" +%s 2>/dev/null) || { echo 0; return; }
    echo $(( s - $(date +%s) ))
}

# validated configuration, identical in every pair
export TURBINE_MODEL=alm TURBINE_REQUEUE=0 TURBINE_RPM=7.518
export TURBINE_VELOCITY_SAMPLE_RADIUS=3.3 TURBINE_N_VELOCITY_SAMPLES=16
export TURBINE_END_EFFECTS=on
export TURBINE_UPSTREAM=3 TURBINE_DOWNSTREAM=7 TURBINE_LATERAL=3
export TURBINE_MESH=medium
export TURBINE_TOTAL_REVS=0.1
# Smaller than the point: the runner verifies the solver advanced by reading the
# WRITTEN time directories.
export TURBINE_WRITE_DEG=30

IFS='|' read -ra ITEMS <<< "$PAIRS"
for item in "${ITEMS[@]}"; do
    # shellcheck disable=SC2086
    set -- $item
    [ "$#" -ge 2 ] || continue
    method="$1" ranks="$2" nspec="${3:--}"
    if grep -q "^${method},${ranks}," "$SUMMARY" 2>/dev/null; then
        echo "=== ${method} ${ranks} ya medido: lo salteo ==="
        continue
    fi
    if [ "$(left_s)" -lt 240 ]; then
        echo "=== quedan $(left_s) s: reencolo para seguir ==="
        scontrol requeue "$SLURM_JOB_ID"
        exit 0
    fi

    export TURBINE_RANKS="$ranks"
    export TURBINE_DECOMP_METHOD="$method"
    if [ "$nspec" = "-" ]; then
        unset TURBINE_DECOMP_N
    else
        export TURBINE_DECOMP_N="$(echo "$nspec" | tr 'x' ' ')"
    fi
    export TURBINE_RUN_DIR="runs/iea15mw-decomp-${method}-${ranks}"

    if [ -d "$TEMPLATE/constant/polyMesh" ] && [ ! -e "${TURBINE_RUN_DIR}/constant/polyMesh" ]; then
        mkdir -p "${TURBINE_RUN_DIR}/constant"
        ln -s "$(cd "$TEMPLATE/constant" && pwd)/polyMesh" \
              "${TURBINE_RUN_DIR}/constant/polyMesh" 2>/dev/null \
            || cp -r "$TEMPLATE/constant/polyMesh" "${TURBINE_RUN_DIR}/constant/" || true
    fi

    echo "=== ${method} ${ranks} ($(( CELLS / ranks )) celdas/core, n=${nspec}) ($(date '+%H:%M:%S')) ==="
    start=$(date +%s)
    if ! bash scripts/run_iea15mw_case.sh; then
        echo "=== FALLO ${method} ${ranks}: sigo con el proximo ==="
        continue
    fi
    wall=$(( $(date +%s) - start ))
    if [ ! -d "$TEMPLATE/constant/polyMesh" ] && [ -d "${TURBINE_RUN_DIR}/constant/polyMesh" ]; then
        mkdir -p "$TEMPLATE/constant"
        cp -r "${TURBINE_RUN_DIR}/constant/polyMesh" "$TEMPLATE/constant/" || true
        echo "    (malla guardada como template)"
    fi

    "$PYTHON" - "$method" "$ranks" "$CELLS" "$wall" "$SUMMARY" \
        "${TURBINE_RUN_DIR}/log.pimpleFoam" "${TURBINE_RUN_DIR}/log.decomposePar" <<'PY'
import re, statistics, sys

method, ranks, cells, wall, summary, plog, dlog = (
    sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]),
    sys.argv[5], sys.argv[6], sys.argv[7],
)
times = []
with open(plog) as fh:
    for line in fh:
        if line.startswith("ExecutionTime = "):
            times.append(float(line.split("=")[1].split("s")[0]))
deltas = [b - a for a, b in zip(times, times[1:]) if b > a]
step = statistics.median(deltas) if deltas else float("nan")
decompose = ""
try:
    match = re.search(r"Finished decomposition in ([0-9.]+) s", open(dlog).read())
    if match:
        decompose = match.group(1)
except OSError:
    pass
with open(summary, "a") as fh:
    fh.write(f"{method},{ranks},{cells // ranks},{len(deltas)},{step:.4f},{wall},{decompose}\n")
print(f"    pasos={len(deltas)}  mediana por paso={step:.3f} s  decomposePar={decompose} s")
PY
done

"$PYTHON" - "$SUMMARY" <<'PY'
import csv, sys

rows = list(csv.DictReader(open(sys.argv[1])))
if not rows:
    raise SystemExit("no pairs measured yet")
rows.sort(key=lambda r: (-int(r["cells_per_rank"]), r["method"]))
ref = {}
for r in rows:
    ref.setdefault(r["ranks"], r)  # first method listed per density is the base
base = {r["ranks"]: r for r in rows if r["method"] == "scotch"} or ref
print()
print("=== por metodo y densidad (segundos por paso; ratio contra scotch) ===")
print(f"  {'metodo':<14}{'ranks':>6}{'celdas/core':>13}{'step_s':>9}{'decompose_s':>13}{'vs scotch':>11}")
for r in rows:
    b = base.get(r["ranks"])
    ratio = ""
    if b is not None and float(r["median_step_s"]) and float(b["median_step_s"]):
        ratio = f"{float(r['median_step_s']) / float(b['median_step_s']):.2f}x"
    print(f"  {r['method']:<14}{r['ranks']:>6}{r['cells_per_rank']:>13}"
          f"{r['median_step_s']:>9}{r['decompose_s']:>13}{ratio:>11}")
PY

echo "=== estudio terminado; CSV en ${SUMMARY} ==="
