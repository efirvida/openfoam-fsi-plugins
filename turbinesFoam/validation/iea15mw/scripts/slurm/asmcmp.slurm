#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# IEA 15-240-RWT actuator-model comparison (alm | asm | asm-mesh).
#
# The three cases are the SAME mesh and domain: it is the comparison trio of
# correction #4 (rotorWake refinement), so the ONLY difference between them is
# TURBINE_MODEL, hence the only difference is the force model. Each occupies
# its own run dir, runs/iea15mw-asmcmp-<model>, and the 20-rev run must fit one
# 96 h allocation (--no-requeue, no slicing).
#
#   cd turbinesFoam/validation/iea15mw
#   TURBINE_MODEL=alm      TURBINE_LONG_QUEUE_AUTHORIZED=1 sbatch -J iea15mw-asmcmp-alm      scripts/slurm/asmcmp.slurm
#   TURBINE_MODEL=asm      TURBINE_LONG_QUEUE_AUTHORIZED=1 sbatch -J iea15mw-asmcmp-asm      scripts/slurm/asmcmp.slurm
#   TURBINE_MODEL=asm-mesh TURBINE_LONG_QUEUE_AUTHORIZED=1 sbatch -J iea15mw-asmcmp-asm-mesh scripts/slurm/asmcmp.slurm
#
# -J is passed at submit time (an #SBATCH directive cannot read the environment),
# so the three jobs stay distinguishable in squeue.
#
# The comparison conditions below are overridable defaults; 56 cores, no
# --nodes and no --mem.
#SBATCH -p sequana_cpu
#SBATCH --ntasks=56
#SBATCH -J iea15mw-asmcmp
#SBATCH --time=96:00:00
#SBATCH --no-requeue
#SBATCH -e %j.err
#SBATCH -o %j.out

set -eu

if [ "${TURBINE_LONG_QUEUE_AUTHORIZED:-0}" != "1" ]; then
    echo "ERROR: long-queue authorization not granted." >&2
    exit 5
fi

pkg_dir="${TURBINE_PKG_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}"
if [ ! -f "${pkg_dir}/scripts/run_iea15mw_case.sh" ]; then
    echo "ERROR: submit from turbinesFoam/validation/iea15mw (or set TURBINE_PKG_DIR)." >&2
    exit 3
fi

case "${TURBINE_MODEL:-}" in
    alm|asm|asm-mesh) ;;
    *)
        echo "ERROR: set TURBINE_MODEL to one of alm|asm|asm-mesh (got '${TURBINE_MODEL:-}')." >&2
        exit 2
        ;;
esac

export TURBINE_PKG_DIR="$pkg_dir"
export TURBINE_RUN_DIR="${TURBINE_RUN_DIR:-runs/iea15mw-asmcmp-${TURBINE_MODEL}}"
# One mesh and domain for the trio; only TURBINE_MODEL varies between runs.
export TURBINE_UPSTREAM="${TURBINE_UPSTREAM:-3}"
export TURBINE_DOWNSTREAM="${TURBINE_DOWNSTREAM:-7}"
export TURBINE_LATERAL="${TURBINE_LATERAL:-3}"
export TURBINE_SNAPPY="${TURBINE_SNAPPY:-on}"
export TURBINE_SNAPPY_LEVEL="${TURBINE_SNAPPY_LEVEL:-3}"
export TURBINE_TOTAL_REVS="${TURBINE_TOTAL_REVS:-20}"
export TURBINE_WRITE_DEG="${TURBINE_WRITE_DEG:-60}"
export TURBINE_RANKS="${TURBINE_RANKS:-56}"
# 96 h fits the whole 20-rev run in one allocation (no slicing/requeue needed).
export TURBINE_REQUEUE="${TURBINE_REQUEUE:-0}"
exec bash "${pkg_dir}/scripts/run_iea15mw_case.sh"
