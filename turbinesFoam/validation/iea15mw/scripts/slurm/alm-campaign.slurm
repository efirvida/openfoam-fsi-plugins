#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# IEA 15 MW — the three ALM characterisation runs of the validated configuration,
# in ONE 96 h allocation, in series, each guarded by the remaining wall time.
#
# Phases (each uses the validated configuration: polars with liftReCorrExp 0,
# velocitySampleRadius 3.3 / nVelocitySamples 16, endEffects Glauert on):
#   P1  20 revolutions on the coarse castellated mesh  -> the ASYMPTOTE, measured
#   P2  TSR sweep, low point  (TSR 7.5  -> 6.33 rpm)   12 rev
#   P3  TSR sweep, high point (TSR 10.5 -> 8.86 rpm)   12 rev
#   P4  medium mesh (D/48)                             12 rev -> the MESH axis
# A phase starts only if enough wall time is left; otherwise it is skipped and
# named in the log, so the job always ends with clean, written state.
#
#   cd turbinesFoam/validation/iea15mw
#   TURBINE_LONG_QUEUE_AUTHORIZED=1 sbatch scripts/slurm/alm-campaign.slurm
#SBATCH -p sequana_cpu
#SBATCH --ntasks=112
#SBATCH -J iea15mw-alm3
#SBATCH --time=96:00:00
#SBATCH --no-requeue
#SBATCH -e %j.err
#SBATCH -o %j.out

set -u
cd "${SLURM_SUBMIT_DIR:-$PWD}"
export TURBINE_LONG_QUEUE_AUTHORIZED="${TURBINE_LONG_QUEUE_AUTHORIZED:-0}"

left_h() {
    local e s
    e=$(scontrol show job "$SLURM_JOB_ID" 2>/dev/null | tr ' ' '\n' | sed -n 's/^EndTime=//p' | head -1)
    s=$(date -d "$e" +%s 2>/dev/null) || { echo 0; return; }
    echo $(( (s - $(date +%s)) / 3600 ))
}

run_phase() {
    local label="$1" need="$2"
    local lh
    lh=$(left_h)
    if [ "$lh" -lt "$need" ]; then
        echo "=== SALTEO ${label}: quedan ${lh} h, necesita ${need} h ==="
        return 0
    fi
    echo "=== ${label}: arranco con ${lh} h disponibles ==="
    bash scripts/run_iea15mw_case.sh || echo "=== FALLO ${label} (sigo con la proxima fase) ==="
}

# common validated configuration
export TURBINE_MESH=coarse TURBINE_RANKS=112 TURBINE_REQUEUE=0
export TURBINE_VELOCITY_SAMPLE_RADIUS=3.3 TURBINE_N_VELOCITY_SAMPLES=16
export TURBINE_END_EFFECTS=on
export TURBINE_UPSTREAM=3 TURBINE_DOWNSTREAM=7 TURBINE_LATERAL=3 TURBINE_WRITE_DEG=60

export TURBINE_MODEL=alm TURBINE_TOTAL_REVS=20 TURBINE_RPM=7.518
export TURBINE_RUN_DIR=runs/iea15mw-alm-20rev
run_phase "P1 20 rev (asintota de la configuracion validada)" 12

export TURBINE_TOTAL_REVS=12 TURBINE_RPM=6.33 TURBINE_RUN_DIR=runs/iea15mw-alm-tsr75
run_phase "P2 TSR 7.5 (rpm 6.33)" 10

export TURBINE_RPM=8.86 TURBINE_RUN_DIR=runs/iea15mw-alm-tsr105
run_phase "P3 TSR 10.5 (rpm 8.86)" 10

export TURBINE_MESH=medium TURBINE_RPM=7.518 TURBINE_RUN_DIR=runs/iea15mw-alm-medium
run_phase "P4 malla medium D/48 (eje de malla)" 16

echo "=== campana ALM terminada; fases completadas: ver los run dirs ==="
