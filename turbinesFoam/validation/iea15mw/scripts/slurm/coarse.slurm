#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# P3 — first physics run of the IEA 15-240-RWT turbinesFoam case.
#
# Neutral baseline: ALM with endEffects OFF, no tipCorrection, no rotational
# augmentation, no dynamic stall. Rated operating point V = 10.659 m/s,
# Omega = 7.518 rpm (collective 0), coarse D/32 (6,674,304 cells), 48 ranks.
#
#   cd turbinesFoam/validation/iea15mw
#   PHASEVI_LONG_QUEUE_AUTHORIZED=1 sbatch scripts/slurm/coarse.slurm
#
# Cores only: no --nodes and no --mem.
#SBATCH -p sequana_cpu
#SBATCH --ntasks=48
#SBATCH -J iea15mw-p3
#SBATCH --time=96:00:00
#SBATCH -e %j.err
#SBATCH -o %j.out

set -eu

if [ "${PHASEVI_LONG_QUEUE_AUTHORIZED:-0}" != "1" ]; then
    echo "ERROR: long-queue authorization not granted." >&2
    exit 5
fi

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
export PYTHON=${PYTHON:-/scratch/leahk/eduardo.donestevez/venv/bin/python}

pkg_dir="${PHASEVI_PKG_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}"
if [ ! -x "${pkg_dir}/tools/generate_case.py" ] && [ ! -f "${pkg_dir}/tools/generate_case.py" ]; then
    echo "ERROR: submit from turbinesFoam/validation/iea15mw (or set PHASEVI_PKG_DIR)." >&2
    exit 3
fi
cd "$pkg_dir"

run_dir="runs/iea15mw-rated-coarse"
mesh="${MESH:-coarse}"

echo "IEA 15 MW P3 on $(hostname); render $run_dir (mesh $mesh)"
"$PYTHON" tools/generate_case.py --case-dir "$run_dir" --mesh "$mesh"

cd "$run_dir"

if [ ! -d constant/polyMesh ]; then
    if ! blockMesh > log.blockMesh 2>&1; then
        tail -30 log.blockMesh >&2; echo "ERROR: blockMesh failed" >&2; exit 3
    fi
fi
if ! topoSet > log.topoSet 2>&1; then
    tail -30 log.topoSet >&2; echo "ERROR: topoSet failed" >&2; exit 3
fi
if ! checkMesh > log.checkMesh 2>&1; then
    tail -20 log.checkMesh >&2; echo "WARNING: checkMesh reported problems (continuing)"
fi

rm -rf processor*
if ! decomposePar -force > log.decomposePar 2>&1; then
    tail -30 log.decomposePar >&2; echo "ERROR: decomposePar failed" >&2; exit 3
fi

mpi_mca="${PHASEVI_MPI_MCA---mca pml ucx --mca btl ^openib}"
# shellcheck disable=SC2086
if ! mpirun $mpi_mca -np 48 pimpleFoam -parallel > log.pimpleFoam 2>&1; then
    tail -40 log.pimpleFoam >&2
    echo "ERROR: pimpleFoam failed" >&2
    exit 3
fi

echo "IEA 15 MW P3 finished: $run_dir"
grep -E "^Time = " log.pimpleFoam | tail -1
