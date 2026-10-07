#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# IEA 15 MW — ALM convergence series: the mesh axis AND the time-step axis.
#
# Why a series and not "one more mesh": generate_case.delta_t() derives deltaT
# from the finest cell the rotor sees (0.95*cell/tip_speed), so a series of
# meshes at their own derived steps moves BOTH axes at once. The three points
# available today show exactly that confound: coarse 7.50 m / 0.075 s / 106
# steps-per-rev -> cp 0.5591, medium 4.98 m / 0.0498 s / 160 -> 0.5490,
# castellated L3 0.94 m / 0.00937 s / 852 -> 0.5370. The drops do NOT shrink
# under refinement (-0.0101 then -0.0121 over a 5.3x finer mesh, no single order
# fits cp(h) = cpinf + C*h**p) and the medium point is 4x less converged in time
# than its neighbours (-0.239 %/rev vs -0.057 %/rev), so the three points are
# neither a converging series nor comparable with each other.
#
# Every phase uses the VALIDATED configuration (polars with liftReCorrExp 0,
# velocitySampleRadius 3.3, nVelocitySamples 16, endEffects Glauert on), the
# SAME domain (3D/7D/+-3D), 112 ranks and the SAME 20-revolution horizon, so the
# phases differ only in resolution. M5 holds the mesh fixed and refines deltaT,
# which is the only way to show the temporal axis is converged before attributing
# a load change to the mesh.
#
# TWO SUBMISSION MODES
#
#   Parallel (preferred: the phases are independent, so the wall clock is the
#   longest phase instead of the sum, and each phase survives on its own):
#
#     cd turbinesFoam/validation/iea15mw
#     for p in M1 M2 M3 M4 M5; do
#       TURBINE_LONG_QUEUE_AUTHORIZED=1 \
#       sbatch --time=<per-phase> --export=ALL,TURBINE_MCONV_PHASE=$p \
#         scripts/slurm/mesh-convergence.slurm
#     done
#
#   Serial in one allocation (fallback when the queue is tight):
#
#     TURBINE_LONG_QUEUE_AUTHORIZED=1 sbatch scripts/slurm/mesh-convergence.slurm
#
#   Both modes are submitted from turbinesFoam/validation/iea15mw.
#
# Phases (also the per-phase wall limits used in parallel mode):
#   M1  medium D/48        4.98 m   160 steps/rev  20 rev   12 h limit
#   M2  fine uniform D/64  3.75 m   213 steps/rev  20 rev   20 h limit
#   M3  snappy L2          1.87 m   427 steps/rev  20 rev   20 h limit
#   M4  snappy L3          0.94 m   852 steps/rev  20 rev   72 h limit
#   M5  snappy L3, dt/2    0.94 m  1704 steps/rev   8 rev   24 h limit
#
# M1..M3 plus the existing coarse point (runs/iea15mw-alm-20rev, 20 rev, same
# configuration) complete a four-point spatial series. M4 puts the point where
# the recorded 0.5366 lives -- also a reproducibility check on it -- and M5 is
# the temporal check against M4's own 8-revolution window.
#
# In serial mode each phase runs only if enough wall time is left, so a
# truncated allocation still ends with written state; in parallel mode the single
# selected phase always runs and its wall budget is the runner's own
# (TURBINE_SOLVER_TIME_BUDGET), which stops it cleanly before the limit and
# leaves the run dir resumable.
#SBATCH -p sequana_cpu
#SBATCH --ntasks=112
#SBATCH -J iea15mw-mconv
#SBATCH --time=72:00:00
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

# A phase runs in serial mode only when the remaining wall time covers it; in
# parallel mode the phase owns its allocation, so the guard is a no-op.
phase="${TURBINE_MCONV_PHASE:-all}"
guard() {
    if [ "$phase" = "all" ]; then echo "$1"; else echo 0; fi
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

# Validated configuration, identical in every phase: only the resolution changes
export TURBINE_MODEL=alm TURBINE_RANKS=112 TURBINE_REQUEUE=0 TURBINE_RPM=7.518
export TURBINE_VELOCITY_SAMPLE_RADIUS=3.3 TURBINE_N_VELOCITY_SAMPLES=16
export TURBINE_END_EFFECTS=on
export TURBINE_UPSTREAM=3 TURBINE_DOWNSTREAM=7 TURBINE_LATERAL=3
export TURBINE_WRITE_DEG=60
export TURBINE_TOTAL_REVS=20

M1() {
    export TURBINE_MESH=medium TURBINE_RUN_DIR=runs/iea15mw-mconv-medium
    run_phase "M1 medium D/48 (4.98 m, 160 pasos/rev) 20 rev" "$(guard 6)"
}
M2() {
    export TURBINE_MESH=fine TURBINE_RUN_DIR=runs/iea15mw-mconv-fine
    run_phase "M2 fine uniforme D/64 (3.75 m, 213 pasos/rev) 20 rev" "$(guard 10)"
}
M3() {
    export TURBINE_MESH=coarse TURBINE_SNAPPY=on TURBINE_SNAPPY_LEVEL=2
    export TURBINE_RUN_DIR=runs/iea15mw-mconv-l2
    run_phase "M3 snappy L2 (1.87 m, 427 pasos/rev) 20 rev" "$(guard 10)"
}
M4() {
    export TURBINE_SNAPPY_LEVEL=3 TURBINE_RUN_DIR=runs/iea15mw-mconv-l3
    run_phase "M4 snappy L3 (0.94 m, 852 pasos/rev) 20 rev" "$(guard 40)"
}
M5() {
    export TURBINE_TOTAL_REVS=8 TURBINE_DT_FACTOR=0.5
    export TURBINE_RUN_DIR=runs/iea15mw-mconv-l3dt
    run_phase "M5 snappy L3 con dt/2 (0.94 m, 1704 pasos/rev) 8 rev" "$(guard 14)"
}

case "$phase" in
    all) M1; M2; M3; M4; M5 ;;
    M1|M2|M3|M4|M5) "$phase" ;;
    *)
        echo "ERROR: TURBINE_MCONV_PHASE must be M1 M2 M3 M4 M5 or all (got '${phase}')" >&2
        exit 2
        ;;
esac

echo "=== fase(s) ${phase} terminada(s); estado escrito en los run dirs ==="
