#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# IEA 15 MW — ALM convergence series: the mesh axis AND the time-step axis,
# as ONE job that runs its phases CONCURRENTLY in two waves.
#
# Why a series and not "one more mesh": generate_case.delta_t() derives deltaT
# from the finest cell the rotor sees (0.95*cell/tip_speed), so a series of
# meshes at their own derived steps moves BOTH axes at once. The three points on
# the record show the confound: coarse 7.50 m / 0.075 s / 106 steps-per-rev ->
# cp 0.5591, medium 4.98 m / 0.0498 s / 160 -> 0.5490, castellated L3 0.94 m /
# 0.00937 s / 852 -> 0.5370. The drops do NOT shrink under refinement (-0.0101
# then -0.0121 over a 5.3x finer mesh, no single order fits cp(h) = cpinf +
# C*h**p) and the medium point is 4x less converged in time than its neighbours
# (-0.239 %/rev vs -0.057 %/rev). M5 holds the mesh fixed and refines deltaT,
# which is the only way to show the temporal axis is converged before
# attributing a load change to the mesh.
#
# One queue entry, phases concurrent inside it. The phases are independent (own
# run dirs, no shared output), so the job's 15 nodes are split into DISJOINT
# groups and each phase's mpirun is confined to its group with its own
# TURBINE_MPI_MCA ("--host <group> --map-by ppr:24:node"). Nothing floods the
# queue: one job, 15 of the partition's 240 nodes.
#
#   cd turbinesFoam/validation/iea15mw
#   TURBINE_LONG_QUEUE_AUTHORIZED=1 sbatch scripts/slurm/mesh-convergence.slurm
#
# Waves:
#   wave 1   M1 (medium D/48) || M2 (fine D/64) || M3 (snappy L2)   112 ranks each
#   wave 2   M4 (snappy L3)   || M5 (snappy L3, dt/2)               168 ranks each
#
# The per-phase rank counts are part of each phase's identity: a decomposed case
# cannot be reused with a different rank count, so a resubmitted phase must keep
# the same one (M1/M2/M3 = 112, M4/M5 = 168). M1 was already at 112 with 0.5 rev
# written, so it resumes.
#
# The two castellated phases in wave 2 build their mesh with a SERIAL
# snappyHexMesh whose peak lands on one node (15.5 GB for the 11.6 M-cell
# castellation), and the batch script runs on one node: M5's launch waits for
# M4's mesh so the two peaks never overlap. Wave 1 has a single castellated
# phase, so no stagger is needed there.
#
# Single-phase mode for a targeted resubmission (uses the whole allocation):
#   TURBINE_MCONV_PHASE=M4 TURBINE_LONG_QUEUE_AUTHORIZED=1 sbatch ...
#SBATCH -p sequana_cpu
#SBATCH --ntasks=360
#SBATCH --ntasks-per-node=24
#SBATCH -J iea15mw-mconv
#SBATCH --time=48:00:00
#SBATCH --no-requeue
#SBATCH -e %j.err
#SBATCH -o %j.out

set -u
cd "${SLURM_SUBMIT_DIR:-$PWD}"
export TURBINE_LONG_QUEUE_AUTHORIZED="${TURBINE_LONG_QUEUE_AUTHORIZED:-0}"

# --- validated configuration, identical in every phase ----------------------
# Only the resolution changes (and, in M5, the time step at a fixed mesh).
export TURBINE_MODEL=alm TURBINE_REQUEUE=0 TURBINE_RPM=7.518
export TURBINE_VELOCITY_SAMPLE_RADIUS=3.3 TURBINE_N_VELOCITY_SAMPLES=16
export TURBINE_END_EFFECTS=on
export TURBINE_UPSTREAM=3 TURBINE_DOWNSTREAM=7 TURBINE_LATERAL=3
export TURBINE_WRITE_DEG=60

run_dir_of() {
    case "$1" in
        M1) echo runs/iea15mw-mconv-medium ;;
        M2) echo runs/iea15mw-mconv-fine ;;
        M3) echo runs/iea15mw-mconv-l2 ;;
        M4) echo runs/iea15mw-mconv-l3 ;;
        M5) echo runs/iea15mw-mconv-l3dt ;;
        *)  echo "ERROR: unknown phase '$1'" >&2; exit 2 ;;
    esac
}

phase_env_of() {
    case "$1" in
        M1) echo "TURBINE_MESH=medium TURBINE_TOTAL_REVS=20" ;;
        M2) echo "TURBINE_MESH=fine TURBINE_TOTAL_REVS=20" ;;
        M3) echo "TURBINE_MESH=coarse TURBINE_SNAPPY=on TURBINE_SNAPPY_LEVEL=2 TURBINE_TOTAL_REVS=20" ;;
        M4) echo "TURBINE_MESH=coarse TURBINE_SNAPPY=on TURBINE_SNAPPY_LEVEL=3 TURBINE_TOTAL_REVS=20" ;;
        M5) echo "TURBINE_MESH=coarse TURBINE_SNAPPY=on TURBINE_SNAPPY_LEVEL=3 TURBINE_TOTAL_REVS=8 TURBINE_DT_FACTOR=0.5" ;;
    esac
}

# launch_phase <tag> <ranks> <comma-separated host group>
# The MPI flags confine this phase to its own nodes: without --host, three
# concurrent mpiruns inside one allocation each see the whole allocation and
# oversubscribe the same nodes.
launch_phase() {
    local tag="$1" ranks="$2" hosts="$3"
    local run_dir log
    run_dir=$(run_dir_of "$tag")
    log="runs/mconv-${tag}.log"
    mkdir -p runs
    (
        echo "=== ${tag}: ${ranks} rangos en ${hosts} ($(date '+%H:%M:%S')) ==="
        # shellcheck disable=SC2086
        env TURBINE_RANKS="$ranks" \
            TURBINE_RUN_DIR="$run_dir" \
            TURBINE_MPI_MCA="--host $hosts --map-by ppr:24:node -mca pml ucx --mca btl ^openib" \
            $(phase_env_of "$tag") \
            bash scripts/run_iea15mw_case.sh
        echo "=== ${tag}: rc=$? ($(date '+%H:%M:%S')) ==="
    ) > "$log" 2>&1
}

# --- one phase resubmission, using the whole allocation ---------------------
phase="${TURBINE_MCONV_PHASE:-waves}"
if [ "$phase" != "waves" ]; then
    launch_phase "$phase" "${TURBINE_RANKS:-112}" "${TURBINE_HOSTS:-}"
    tail -5 "runs/mconv-${phase}.log"
    exit 0
fi

# --- node groups ------------------------------------------------------------
mapfile -t nodes < <(scontrol show hostnames "$SLURM_JOB_NODELIST")
echo "nodos de la asignación (${#nodes[@]}): ${nodes[*]}"

# group <first index> <count> -> comma-separated host list
group() {
    local from="$1" count="$2" i out=()
    for ((i = from; i < from + count; i++)); do out+=("${nodes[i]}"); done
    (IFS=,; echo "${out[*]}")
}

if [ "${#nodes[@]}" -lt 13 ]; then
    echo "ERROR: need at least 13 nodes for the two waves, got ${#nodes[@]}" >&2
    exit 3
fi
# Wave 1: three 5-node groups (112 ranks + slack on the fifth node).
# Wave 2: two 7-node groups (168 ranks).
W1A=$(group 0 5); W1B=$(group 5 5); W1C=$(group 10 5)
W2A=$(group 0 7); W2B=$(group 7 7)

# --- MPI smoke test ---------------------------------------------------------
# The whole design rests on confining a phase's mpirun to its own hosts, so
# prove it works before spending hours: one task per node on one group.
source /etc/profile.d/modules.sh 2>/dev/null
module purge >/dev/null 2>&1
module load openfoam/v2506_openmpi-4.1.4_gnu gcc >/dev/null 2>&1
if ! mpirun --host "$W1A" --map-by ppr:1:node -np 5 hostname >/dev/null 2>&1; then
    echo "ERROR: mpirun --host cannot be confined to a node group; the" >&2
    echo "       concurrent-wave design is not usable on this cluster." >&2
    exit 4
fi

# --- wave 1 -----------------------------------------------------------------
echo "=== ola 1: M1 || M2 || M3 (112 rangos cada una) ==="
launch_phase M1 112 "$W1A" &
launch_phase M2 112 "$W1B" &
launch_phase M3 112 "$W1C" &
wait
echo "=== ola 1 terminada; estados ==="
for t in M1 M2 M3; do tail -2 "runs/mconv-${t}.log"; done

# --- wave 2 -----------------------------------------------------------------
echo "=== ola 2: M4 || M5 (168 rangos cada una) ==="
launch_phase M4 168 "$W2A" &
# Stagger M5's launch behind M4's mesh: both castellations peak on the batch
# node, and the two peaks must not overlap (the asmcmp note measured 15.5 GB for
# the 11.6 M-cell castellation). log.topoSet appears right after snappyHexMesh.
for _ in $(seq 1 240); do
    [ -f runs/iea15mw-mconv-l3/log.topoSet ] && break
    [ -f "runs/mconv-M4.log" ] && grep -q "rc=" "runs/mconv-M4.log" && break
    sleep 15
done
echo "=== M4 construyó su malla; arranco M5 ==="
launch_phase M5 168 "$W2B" &
wait
echo "=== ola 2 terminada; estados ==="
for t in M4 M5; do tail -2 "runs/mconv-${t}.log"; done

echo "=== serie de convergencia terminada; resultados en runs/iea15mw-mconv-* ==="
