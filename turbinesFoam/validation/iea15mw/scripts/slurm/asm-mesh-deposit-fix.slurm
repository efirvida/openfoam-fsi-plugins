#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Issue #5 re-validation: the ASM+mesh with the current-position deposit fix.
#
# 0.2 revolution (endTime 1.5961692) on the validated operating point, one
# allocation, 48 ranks: the same mesh, domain, snappy configuration and ranks as
# the 12-step diagnostic run `runs/iea15mw-asm-mesh-nodedump`, verified by
# diffing system/blockMeshDict and system/snappyHexMeshDict against a fresh
# `generate_case.py --model asm-mesh --ranks 48`. The only intended difference is
# the library, so the two runs are an A/B on the deposit fix.
#
#   cd turbinesFoam/validation/iea15mw
#   sbatch scripts/slurm/asm-mesh-deposit-fix.slurm
#
# What the run must show: `cp` and the element angles of attack tracking the ALM
# at every azimuth. Before the fix the flow received 0 % of the blade force from
# the third time step on (the per-node receiving cells were cached at the
# construction azimuth), so the induction never developed and `cp` climbed to
# 1.15 at 5.07 deg of azimuth while the ALM decayed to 0.63.
#
# The mesh is cast by a SERIAL snappyHexMesh before decomposePar, so its peak
# lands on one node: the diagnostic mesh is 4.3 M cells initially (against the
# 6.9 M of the 20-rev comparison mesh), which the 48-rank nodedump run already
# built without an OOM at the partition default.
#SBATCH -p sequana_cpu
#SBATCH --ntasks=48
#SBATCH -J iea15mw-asm-mesh-fix
#SBATCH --time=02:00:00
#SBATCH --no-requeue
#SBATCH -e %j.err
#SBATCH -o %j.out

set -eu

pkg_dir="${TURBINE_PKG_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}"
if [ ! -f "${pkg_dir}/scripts/run_iea15mw_case.sh" ]; then
    echo "ERROR: submit from turbinesFoam/validation/iea15mw (or set TURBINE_PKG_DIR)." >&2
    exit 3
fi

export TURBINE_PKG_DIR="$pkg_dir"
export TURBINE_MODEL=asm-mesh
export TURBINE_RUN_DIR=runs/iea15mw-asm-mesh-fix
export TURBINE_RANKS=48
# One slice, no requeue: the whole 0.2 rev must fit in this allocation, so the
# slice length is the total length and the case keeps the reference run's endTime
export TURBINE_TOTAL_REVS=0.2
export TURBINE_REQUEUE=0

exec bash "${pkg_dir}/scripts/run_iea15mw_case.sh"
