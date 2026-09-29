#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Diagnostic: run the pre-rendered 7 m/s coarse arm-A tip-correction case with
# the tipCorrection debug dump ON, for a very short window, on the authorized
# development queue. The case directory is rendered and patched by hand
# (`debug true;` in the tipCorrection block, endTime 0.30 s) so it is NOT
# re-rendered here. Cores only: no --nodes, no --mem.
#
#   cd turbinesFoam/validation/phaseVI
#   sbatch scripts/slurm/tip-correction-diag.slurm
#SBATCH -p sequana_cpu_dev
#SBATCH --ntasks=48
#SBATCH -J phaseVI-tipcorr-diag
#SBATCH --time=00:20:00
#SBATCH -e %j.err
#SBATCH -o %j.out

set -eu

module purge
module load openfoam/v2506_openmpi-4.1.4_gnu gcc

export WM_ARCH=linux64
export WM_COMPILER=Gcc
export WM_COMPILE_OPTION=Opt
export WM_PRECISION_OPTION=DP
export WM_LABEL_SIZE=64
export WM_OPTIONS=linux64GccDPInt64Opt
set +eu
. "$WM_PROJECT_DIR/etc/bashrc"
set -eu

export FOAM_USER_LIBBIN=$WM_PROJECT_USER_DIR/platforms/$WM_OPTIONS/lib
export LD_LIBRARY_PATH=/scratch/app/gcc/14.2.0/lib64:$FOAM_USER_LIBBIN:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib/sys-openmpi:$LD_LIBRARY_PATH

pkg_dir="${PHASEVI_PKG_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}"
run_dir="$pkg_dir/runs/alm-U7-coarse-tipcorr-diag"
if [ ! -d "$run_dir" ]; then
    echo "ERROR: diagnostic case not found: $run_dir" >&2
    exit 3
fi
cd "$run_dir"

echo "tip-correction diagnostic on $(hostname); $run_dir"

rm -rf processor*
if ! decomposePar -force > log.decomposePar 2>&1; then
    tail -30 log.decomposePar >&2
    echo "ERROR: decomposePar failed" >&2
    exit 3
fi

mpi_mca="${PHASEVI_MPI_MCA---mca pml ucx --mca btl ^openib}"
# shellcheck disable=SC2086
if ! mpirun $mpi_mca -np 48 pimpleFoam -parallel > log.pimpleFoam 2>&1; then
    echo "SOLVER FAILED (expected: this diagnostic captures the failure)"
    tail -30 log.pimpleFoam >&2
fi

echo "=== tipCorrectionDebug lines ==="
grep "tipCorrectionDebug" log.pimpleFoam || echo "(none)"
echo "=== diagnostic finished ==="
