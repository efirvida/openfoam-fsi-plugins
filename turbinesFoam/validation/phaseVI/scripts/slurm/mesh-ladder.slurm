#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Build the Phase VI refinement-ladder meshes.
#
# Usage (from the validation/phaseVI directory):
#   sbatch scripts/slurm/mesh-ladder.slurm
#
# One job, two array tasks, two levels each: task 0 builds levels 0 and 1, task 1
# builds levels 2 and 3. Meshing is serial (blockMesh and snappyHexMesh are both
# single-threaded), so two tasks is the whole available speedup, and a single
# sbatch keeps the submit footprint small on purpose. `sequana_cpu` allows
# MaxSubmitJobs 24 / MaxJobs 4, and concurrent IEA 15 MW work uses some of it, so
# this leaves slots free for short tests.
#
# The development queue cannot be used: `sequana_cpu_dev` allows exactly one
# submitted job, which an array with more than one task exceeds.
#
# The base `blockMesh` is never refined; levels above 0 add the castellated
# rotor-disk refinement and land in their own `runs/mesh-coarse-r<N>` directory,
# so no level can borrow another's mesh. `mesh.sh` records the accepted cell count
# of every level in its own Slurm log.
#
# Slurm spools this script, so BASH_SOURCE is not usable; the package root is
# resolved from the submission directory instead.
#SBATCH --job-name=phaseVI-mesh
#SBATCH --partition=sequana_cpu
#SBATCH --time=24:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --array=0-1
#SBATCH --output=runs/mesh-ladder-r%a.out
#SBATCH --error=runs/mesh-ladder-r%a.err
set -eu

if [ -z "${SLURM_SUBMIT_DIR:-}" ]; then
    echo "ERROR: SLURM_SUBMIT_DIR is unset; submit this script with sbatch" >&2
    exit 2
fi
cd "$SLURM_SUBMIT_DIR"

module purge
module load openfoam/v2506_openmpi-4.1.4_gnu gcc

# The module exports Int32 paths; set the Int64 identity first and re-source the
# OpenFOAM bashrc so PATH points at the installed linux64GccDPInt64Opt binaries.
# Without this `blockMesh: command not found`, which is how the first submission
# of this job failed.
export WM_ARCH=linux64
export WM_COMPILER=Gcc
export WM_COMPILE_OPTION=Opt
export WM_PRECISION_OPTION=DP
export WM_LABEL_SIZE=64
export WM_OPTIONS=linux64GccDPInt64Opt
# etc/bashrc is not written for strict mode: it dereferences optional variables
# (WM_PROJECT_SITE on SDumont) and can return non-zero, so `set -eu` aborts the
# job while sourcing it. Disable both while sourcing, then restore them.
set +eu
. "$WM_PROJECT_DIR/etc/bashrc"
set -eu

export FOAM_USER_LIBBIN=$WM_PROJECT_USER_DIR/platforms/$WM_OPTIONS/lib
export LD_LIBRARY_PATH=$FOAM_USER_LIBBIN:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib/sys-openmpi:$LD_LIBRARY_PATH

case "${SLURM_ARRAY_TASK_ID:?array task id required}" in
    0) levels="0 1" ;;
    1) levels="2 3" ;;
    *) echo "ERROR: unexpected array task ${SLURM_ARRAY_TASK_ID}" >&2; exit 2 ;;
esac

echo "OpenFOAM ${WM_PROJECT_VERSION:-unknown} on $(hostname)"
echo "blockMesh: $(command -v blockMesh || echo MISSING)"
echo "snappyHexMesh: $(command -v snappyHexMesh || echo MISSING)"
echo "Building coarse meshes at refinement levels: $levels"

status=0
for level in $levels; do
    echo "=== coarse mesh, refinement level $level ==="
    # Continue across levels: three good meshes and one failure is worth more
    # than stopping at the first, and the exit status still reports the failure.
    if ! scripts/mesh.sh coarse --refine-level "$level"; then
        echo "ERROR: refinement level $level failed" >&2
        status=1
    fi
done
exit $status
