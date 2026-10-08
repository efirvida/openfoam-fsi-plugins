#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# IEA 15 MW — mesh-convergence SCREENING: 4 revolutions per mesh, in series.
#
# Goal: decide WHICH mesh, not to validate. What matters is how much the rotor
# behaviour changes with the mesh, so every mesh runs the SAME 4-revolution
# horizon; the production number later comes from a long run of the mesh this
# screening selects. Cost is ~5x lower than 20 revolutions, which is what makes a
# four-point series affordable.
#
# Caveat carried in from the record, because it is the whole risk: at 4 revolutions
# the transient drift is order-% per revolution against ~2 % steps between meshes,
# so signal and noise are the same size. This selects candidates, it does not close
# the number -- and every value must be read next to its per-revolution drift, and
# against the SAME 4-revolution window extracted from the 20-revolution coarse run
# that is already on disk (runs/iea15mw-alm-20rev).
#
# Configuration comes from the two studies that just ran:
#   method simple    won at all three densities (-14 / -25 / -14 % per step, and
#                    13-21x faster decomposePar) on this structured blockMesh
#   ranks  96        the knee of the scaling curve (80 % efficiency, 67.8k
#                    cells/rank); three meshes fit in about four hours
#   n (4 6 4)        96 = 4x6x4, matching the domain's 6:10:2.5 aspect
#
#   cd turbinesFoam/validation/iea15mw
#   sbatch scripts/slurm/mesh-screening.slurm
#
# M4 (snappy L3, where the recorded 0.5366 lives) stays HELD: it is ~7 h at this
# rank count and there is nothing to learn from it until this screening says the
# series is monotone. M5 (the temporal check) likewise.
#SBATCH -p sequana_cpu
#SBATCH --ntasks=96
#SBATCH --time=08:00:00
#SBATCH --requeue
#SBATCH -J iea15mw-screen
#SBATCH -e %j.err
#SBATCH -o %j.out

set -u
cd "${SLURM_SUBMIT_DIR:-$PWD}"

# Validated configuration, identical in every mesh: only the resolution changes.
export TURBINE_MODEL=alm TURBINE_RANKS=96 TURBINE_REQUEUE=0 TURBINE_RPM=7.518
export TURBINE_VELOCITY_SAMPLE_RADIUS=3.3 TURBINE_N_VELOCITY_SAMPLES=16
export TURBINE_END_EFFECTS=on
export TURBINE_UPSTREAM=3 TURBINE_DOWNSTREAM=7 TURBINE_LATERAL=3
export TURBINE_TOTAL_REVS=4
export TURBINE_WRITE_DEG=60
# The winning decomposition, from the method study.
export TURBINE_DECOMP_METHOD=simple
export TURBINE_DECOMP_N="4 6 4"

# screen <tag> <mesh> <snappy on|off> [level]
screen() {
    local tag="$1" mesh="$2" snappy="$3" level="${4:-0}"
    export TURBINE_MESH="$mesh"
    export TURBINE_RUN_DIR="runs/iea15mw-screen-${tag}"
    if [ "$snappy" = "on" ]; then
        export TURBINE_SNAPPY=on TURBINE_SNAPPY_LEVEL="$level"
    else
        unset TURBINE_SNAPPY TURBINE_SNAPPY_LEVEL || true
    fi
    echo "=== ${tag}: ${mesh}${snappy:+ snappy L${level}} 4 rev, 96 rangos ($(date '+%H:%M:%S')) ==="
    bash scripts/run_iea15mw_case.sh || echo "=== FALLO ${tag} (sigo con el proximo) ==="
}

screen m1-medium medium off
screen m2-fine fine off
screen m3-l2 coarse on 2

echo "=== tamiz terminado; resultados en runs/iea15mw-screen-* ==="
