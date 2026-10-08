#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# IEA 15 MW — ALM convergence series, STAGE 1: the mesh axis.
#
# Why a series and not "one more mesh": generate_case.delta_t() derives deltaT
# from the finest cell the rotor sees (0.95*cell/tip_speed), so a series of
# meshes at their own derived steps moves BOTH axes at once. The three points on
# the record show the confound: coarse 7.50 m / 0.075 s / 106 steps-per-rev ->
# cp 0.5591, medium 4.98 m / 0.0498 s / 160 -> 0.5490, castellated L3 0.94 m /
# 0.00937 s / 852 -> 0.5370. The drops do NOT shrink under refinement (-0.0101
# then -0.0121 over a 5.3x finer mesh, no single order fits cp(h) = cpinf +
# C*h**p) and the medium point is 4x less converged in time than its neighbours
# (-0.239 %/rev vs -0.057 %/rev). The axis is confounded with the transient.
#
# STAGE 1 asks one question: does the spatial series converge SANELY at a common,
# temporally converged horizon? It runs M1, M2 and M3 IN SERIES in this one job,
# with the validated configuration and 20 revolutions each:
#
#   M1  medium D/48        4.98 m   160 steps/rev  20 rev   ~6 h
#   M2  fine uniform D/64  3.75 m   213 steps/rev  20 rev  ~13 h
#   M3  snappy L2          1.87 m   427 steps/rev  20 rev  ~11 h
#
# plus the coarse point that already exists (runs/iea15mw-alm-20rev, 20 rev,
# same configuration): a FOUR-point spatial series, enough to fit a single order
# p and see whether the loads settle inside the reference band (0.5312 free wake
# to 0.4910 CCBlade/BEM) instead of wandering.
#
# M4 (snappy L3, 0.94 m) and M5 (L3 with dt/2, the temporal check) are DEFINED
# BUT HELD: they are the expensive half (~26 h and ~10 h at 112 ranks), and there
# is no point spending the queue on them until this stage says the series is
# worth extending. Run them explicitly with TURBINE_MCONV_PHASES=M4 / M5 once the
# verdict exists.
#
# SIZE, deliberately small: 112 ranks (5 nodes at 24 CPUs) rather than one big
# concurrent allocation. Measured on this cluster: five 112-rank jobs started in
# seconds, while a single 360-CPU job sat at position #132 of 199 pending jobs
# with a 2-day estimate, because it needed 15 nodes with >=24 CPUs free
# SIMULTANEOUSLY while the 131 jobs ahead of it ask for 24 CPUs each and fit any
# fragment. The phases here are cheap enough that the queue wait dominates.
#
#   cd turbinesFoam/validation/iea15mw
#   TURBINE_LONG_QUEUE_AUTHORIZED=1 sbatch scripts/slurm/mesh-convergence.slurm
#
#   112 ranks is also what M1 already holds (0.5 rev written), so M1 resumes.
#   A resubmitted phase must keep its rank count: a decomposed case cannot be
#   reused with a different decomposition.
#SBATCH -p sequana_cpu
#SBATCH --ntasks=112
#SBATCH --ntasks-per-node=24
#SBATCH -J iea15mw-mconv
#SBATCH --time=48:00:00
#SBATCH --no-requeue
#SBATCH -e %j.err
#SBATCH -o %j.out

set -u
cd "${SLURM_SUBMIT_DIR:-$PWD}"

# --- validated configuration, identical in every phase ----------------------
export TURBINE_MODEL=alm TURBINE_RANKS=112 TURBINE_REQUEUE=0 TURBINE_RPM=7.518
export TURBINE_VELOCITY_SAMPLE_RADIUS=3.3 TURBINE_N_VELOCITY_SAMPLES=16
export TURBINE_END_EFFECTS=on
export TURBINE_UPSTREAM=3 TURBINE_DOWNSTREAM=7 TURBINE_LATERAL=3
export TURBINE_WRITE_DEG=60

left_h() {
    local e s
    e=$(scontrol show job "$SLURM_JOB_ID" 2>/dev/null | tr ' ' '\n' | sed -n 's/^EndTime=//p' | head -1)
    s=$(date -d "$e" +%s 2>/dev/null) || { echo 0; return; }
    echo $(( (s - $(date +%s)) / 3600 ))
}

# A phase starts only if the remaining wall time covers it: each phase ends with
# a real field write, so a skipped one is named here and resumable later.
run_phase() {
    local label="$1" need="$2" lh
    lh=$(left_h)
    if [ "$lh" -lt "$need" ]; then
        echo "=== SALTEO ${label}: quedan ${lh} h, necesita ${need} h ==="
        return 0
    fi
    echo "=== ${label}: arranco con ${lh} h disponibles ==="
    bash scripts/run_iea15mw_case.sh || echo "=== FALLO ${label} (sigo con la proxima fase) ==="
}

M1() {
    export TURBINE_MESH=medium TURBINE_TOTAL_REVS=20
    export TURBINE_RUN_DIR=runs/iea15mw-mconv-medium
    run_phase "M1 medium D/48 (4.98 m, 160 pasos/rev) 20 rev" 9
}
M2() {
    export TURBINE_MESH=fine TURBINE_TOTAL_REVS=20
    export TURBINE_RUN_DIR=runs/iea15mw-mconv-fine
    run_phase "M2 fine uniforme D/64 (3.75 m, 213 pasos/rev) 20 rev" 17
}
M3() {
    export TURBINE_MESH=coarse TURBINE_SNAPPY=on TURBINE_SNAPPY_LEVEL=2
    export TURBINE_TOTAL_REVS=20 TURBINE_RUN_DIR=runs/iea15mw-mconv-l2
    run_phase "M3 snappy L2 (1.87 m, 427 pasos/rev) 20 rev" 15
}
# HELD until stage 1 reports: the L3 point (where the recorded 0.5366 lives) and
# the temporal check at a fixed mesh.
M4() {
    export TURBINE_MESH=coarse TURBINE_SNAPPY=on TURBINE_SNAPPY_LEVEL=3
    export TURBINE_TOTAL_REVS=20 TURBINE_RUN_DIR=runs/iea15mw-mconv-l3
    run_phase "M4 snappy L3 (0.94 m, 852 pasos/rev) 20 rev" 30
}
M5() {
    export TURBINE_MESH=coarse TURBINE_SNAPPY=on TURBINE_SNAPPY_LEVEL=3
    export TURBINE_TOTAL_REVS=8 TURBINE_DT_FACTOR=0.5
    export TURBINE_RUN_DIR=runs/iea15mw-mconv-l3dt
    run_phase "M5 snappy L3 con dt/2 (0.94 m, 1704 pasos/rev) 8 rev" 16
}

# Default is STAGE 1. M4/M5 run only when asked for explicitly.
phases="${TURBINE_MCONV_PHASES:-M1 M2 M3}"
echo "=== fases solicitadas: ${phases} ==="
for phase in $phases; do
    case "$phase" in
        M1|M2|M3|M4|M5) "$phase" ;;
        *) echo "ERROR: unknown phase '${phase}' (M1 M2 M3 M4 M5)" >&2; exit 2 ;;
    esac
done
echo "=== terminado; resultados en runs/iea15mw-mconv-* ==="
