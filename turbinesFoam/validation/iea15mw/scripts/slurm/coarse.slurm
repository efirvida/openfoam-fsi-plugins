#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# P3 — first physics run of the IEA 15-240-RWT turbinesFoam case (production).
#
# Neutral baseline: ALM with endEffects OFF, no tipCorrection, no rotational
# augmentation, no dynamic stall. Rated operating point V = 10.659 m/s,
# Omega = 7.518 rpm (collective 0), coarse D/32 (6,674,304 cells), 48 ranks,
# 3 revolutions. The heavy lifting lives in scripts/run_iea15mw_case.sh.
#
#   cd turbinesFoam/validation/iea15mw
#   PHASEVI_LONG_QUEUE_AUTHORIZED=1 sbatch scripts/slurm/coarse.slurm
#
# Cores only: no --nodes and no --mem.
#SBATCH -p sequana_cpu
#SBATCH --ntasks=48
#SBATCH -J iea15mw-p3
#SBATCH --time=96:00:00
#SBATCH --no-requeue
#SBATCH -e %j.err
#SBATCH -o %j.out

set -eu

if [ "${PHASEVI_LONG_QUEUE_AUTHORIZED:-0}" != "1" ]; then
    echo "ERROR: long-queue authorization not granted." >&2
    exit 5
fi

pkg_dir="${PHASEVI_PKG_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}"
if [ ! -f "${pkg_dir}/scripts/run_iea15mw_case.sh" ]; then
    echo "ERROR: submit from turbinesFoam/validation/iea15mw (or set PHASEVI_PKG_DIR)." >&2
    exit 3
fi

export PHASEVI_PKG_DIR="$pkg_dir"
# 96 h fits the whole run in one allocation.
export PHASEVI_REQUEUE=0
exec bash "${pkg_dir}/scripts/run_iea15mw_case.sh"
