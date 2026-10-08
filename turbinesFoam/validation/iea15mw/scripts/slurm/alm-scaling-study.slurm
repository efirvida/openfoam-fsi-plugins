#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# IEA 15 MW — ALM scaling study: cells per core for THIS physics and THIS CPU.
#
# Why: every run so far used a rank count inherited from the campaign (112) or
# from taste, never measured for this solver+physics on these nodes. The answer
# decides how the convergence series is run (and whether a rank count is buying
# anything at all), so it comes before spending queue time on M1.
#
# Method: the SAME case at several rank counts -- the validated configuration
# (polars with liftReCorrExp 0, velocitySampleRadius 3.3, nVelocitySamples 16,
# endEffects Glauert on), the medium D/48 mesh (6 508 528 cells), domain
# 3D/7D/+-3D -- for a TENTH of a revolution each (16 steps), and the wall seconds
# per time step are read from the solver's own ExecutionTime, not from a stopwatch
# around the job. Each point gets its own run dir because the decomposition cannot
# be shared across rank counts.
#
# NINE points, so the trend has a knee and not just two ends (cells/rank for the
# 6 508 528-cell case):
#
#   ranks   cells/rank   ranks   cells/rank
#    12      542 377      72       90 396
#    24      271 188      96       67 797
#    36      180 792     144       45 198
#    48      135 594     192       33 899
#                         240       27 119
#
# THIS SCRIPT IS THE PROJECT'S SIZING REFERENCE. Its output
# (`runs/iea15mw-scale-summary.csv`) is what a future run should read to choose
# ranks, instead of inheriting a number from an earlier campaign; the results are
# recorded in `odd/tasks/iea15mw-alm-convergence-series.md`, and re-running the
# study on a new node type replaces that table rather than adding folklore.
#
#   cd turbinesFoam/validation/iea15mw
#   TURBINE_LONG_QUEUE_AUTHORIZED=1 sbatch scripts/slurm/alm-scaling-study.slurm
#
# Cost: ~30 min of work on 5 nodes (40 steps per point plus the per-point
# blockMesh and decomposePar), run as slices of the development queue's
# 20-MINUTE cap with self-requeue: the sweep skips the points already in the CSV,
# so a requeued job continues where the previous slice stopped. `-p
# sequana_cpu_dev` really is a 20-minute partition (sinfo shows 20:00 = 00:20; the
# campaign's coarse-dev.slurm says "caps wall time at 20 minutes").
#
# The whole allocation is 240 tasks because the largest point needs it; the small
# points simply use part of it.
# A full-node point needs `--mem-per-cpu` BELOW the partition default: the nodes
# are CfgTRES=cpu=48,mem=375G while DefMemPerCPU=8000, so 48 tasks at the default
# ask for 384 GB and no node can satisfy it (slurm answers "Requested node
# configuration is not available"). 4 GB per task is still ~20x what a
# 135k-cells-per-rank run needs, and it keeps the sweep on WHOLE nodes, without
# the co-tenancy of half-node placement.
#SBATCH -p sequana_cpu_dev
#SBATCH --ntasks=240
#SBATCH --ntasks-per-node=48
#SBATCH --mem-per-cpu=4G
#SBATCH --time=00:20:00
#SBATCH --requeue
#SBATCH -J iea15mw-scale
#SBATCH -e %j.err
#SBATCH -o %j.out

set -u
cd "${SLURM_SUBMIT_DIR:-$PWD}"

PHASES="${TURBINE_SCALE_RANKS:-240 192 144 96 72 48 36 24 12}"
CELLS="${TURBINE_SCALE_CELLS:-6508528}"
SUMMARY="runs/iea15mw-scale-summary.csv"
PYTHON="${PYTHON:-/scratch/leahk/eduardo.donestevez/venv/bin/python}"

# --- which CPU are we actually measuring on --------------------------------
echo "=== nodos: $(scontrol show hostnames "$SLURM_JOB_NODELIST" | tr '\n' ' ')"
lscpu | grep -E "^Model name|^CPU\(s\)|^Thread|^Core\(s\)|^Socket|^NUMA node\(s\)"
echo "=== puntos: ${PHASES} (celdas del caso: ${CELLS}) ==="
mkdir -p runs
# The header only on the first slice: a requeued job resumes the same CSV.
[ -f "$SUMMARY" ] || echo "ranks,cells_per_rank,steps,median_step_s,total_s,speedup,efficiency" > "$SUMMARY"

# Seconds left in this slice, so the sweep requeues instead of being killed
# mid-point (a killed point leaves a half-written run dir and no CSV row).
left_s() {
    local e s
    e=$(scontrol show job "$SLURM_JOB_ID" 2>/dev/null | tr ' ' '\n' | sed -n 's/^EndTime=//p' | head -1)
    s=$(date -d "$e" +%s 2>/dev/null) || { echo 0; return; }
    echo $(( s - $(date +%s) ))
}

# --- validated configuration, identical at every point ---------------------
export TURBINE_MODEL=alm TURBINE_REQUEUE=0 TURBINE_RPM=7.518
export TURBINE_VELOCITY_SAMPLE_RADIUS=3.3 TURBINE_N_VELOCITY_SAMPLES=16
export TURBINE_END_EFFECTS=on
export TURBINE_UPSTREAM=3 TURBINE_DOWNSTREAM=7 TURBINE_LATERAL=3
export TURBINE_MESH=medium
export TURBINE_TOTAL_REVS=0.1
# One write per point keeps the disk tiny; the study measures the solver.
export TURBINE_WRITE_DEG=90

for ranks in $PHASES; do
    if grep -q "^${ranks}," "$SUMMARY" 2>/dev/null; then
        echo "=== punto ${ranks} ya medido en esta serie: lo salteo ==="
        continue
    fi
    if [ "$(left_s)" -lt 300 ]; then
        echo "=== quedan $(left_s) s: reencolo para seguir con los puntos que faltan ==="
        scontrol requeue "$SLURM_JOB_ID"
        exit 0
    fi
    export TURBINE_RANKS="$ranks"
    export TURBINE_RUN_DIR="runs/iea15mw-scale-${ranks}"
    echo "=== punto: ${ranks} rangos ($(( CELLS / ranks )) celdas/rank) ($(date '+%H:%M:%S')) ==="
    start=$(date +%s)
    if ! bash scripts/run_iea15mw_case.sh; then
        echo "=== FALLO el punto ${ranks}: sigo con el proximo ==="
        continue
    fi
    wall=$(( $(date +%s) - start ))
    "$PYTHON" - "$ranks" "$CELLS" "$wall" "$SUMMARY" "runs/iea15mw-scale-${ranks}/log.pimpleFoam" <<'PY'
import statistics, sys

ranks, cells, wall, summary, log = (
    int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]),
    sys.argv[4], sys.argv[5],
)
times = []
with open(log) as fh:
    for line in fh:
        # OpenFOAM prints one ExecutionTime per time step (and once at the end)
        if line.startswith("ExecutionTime = "):
            times.append(float(line.split("=")[1].split("s")[0]))
deltas = [b - a for a, b in zip(times, times[1:]) if b > a]
step = statistics.median(deltas) if deltas else float("nan")
with open(summary, "a") as fh:
    fh.write(f"{ranks},{cells // ranks},{len(deltas)},{step:.4f},{wall},,\n")
print(f"    pasos={len(deltas)}  mediana por paso={step:.3f} s  ({step * 160 / 60:.2f} min por revolucion)")
PY
done

# --- summary: speedup and efficiency against the cheapest point ------------
"$PYTHON" - "$SUMMARY" <<'PY'
import csv, sys

rows = list(csv.DictReader(open(sys.argv[1])))
if not rows:
    raise SystemExit("no points")
rows.sort(key=lambda r: int(r["ranks"]))
base = max(rows, key=lambda r: float(r["median_step_s"]))
t1, n1 = float(base["median_step_s"]), int(base["ranks"])
out = [("ranks", "celdas/rank", "Mpasos", "step_s", "min/rev", "speedup", "eficiencia")]
for r in rows:
    n = int(r["ranks"]); t = float(r["median_step_s"])
    speedup = t1 / t
    out.append((n, int(r["cells_per_rank"]), r["steps"], f"{t:.3f}",
                f"{t * 160 / 60:.2f}", f"{speedup:.2f}x",
                f"{speedup * n1 / n:.0%}"))
width = [max(len(str(row[i])) for row in out) for i in range(len(out[0]))]
print()
print("=== resumen del escalado (eficiencia relativa a", n1, "rangos) ===")
for row in out:
    print("  ".join(str(c).ljust(w) for c, w in zip(row, width)))
PY

echo "=== estudio terminado; CSV en ${SUMMARY} ==="
