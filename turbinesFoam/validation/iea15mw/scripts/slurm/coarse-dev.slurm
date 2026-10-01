#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# P3 — IEA 15-240-RWT rated-point run on the 20-minute development queue.
#
# The development queue caps wall time at 20 minutes, so the run is executed in
# 0.5-revolution slices: each slice stops cleanly at its endTime, writes, and
# requeues itself (scontrol requeue) to continue from the last written time.
# 3 revolutions ≈ 6 slices. See scripts/run_iea15mw_case.sh.
#
#   cd turbinesFoam/validation/iea15mw
#   sbatch scripts/slurm/coarse-dev.slurm
#
# Cores only: no --nodes and no --mem.
#SBATCH -p sequana_cpu_dev
#SBATCH --ntasks=48
#SBATCH -J iea15mw-p3-dev
#SBATCH --time=00:20:00
#SBATCH --requeue
#SBATCH -e %j.err
#SBATCH -o %j.out

set -eu

pkg_dir="${PHASEVI_PKG_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}"
if [ ! -f "${pkg_dir}/scripts/run_iea15mw_case.sh" ]; then
    echo "ERROR: submit from turbinesFoam/validation/iea15mw (or set PHASEVI_PKG_DIR)." >&2
    exit 3
fi

export PHASEVI_PKG_DIR="$pkg_dir"
export PHASEVI_SLURM_SCRIPT="${pkg_dir}/scripts/slurm/coarse-dev.slurm"
export PHASEVI_REQUEUE=1
export PHASEVI_SLICE_REVS="${PHASEVI_SLICE_REVS:-0.5}"
exec bash "${pkg_dir}/scripts/run_iea15mw_case.sh"
