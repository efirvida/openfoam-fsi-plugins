#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Build the Phase VI refinement-ladder meshes on the authorized development queue.
#
# Usage (from the validation/phaseVI directory):
#   sbatch scripts/slurm/mesh-ladder.slurm
#
# One task per refinement level (array 0-2). Level 0 is the base `blockMesh`;
# levels 1 and 2 add the castellated rotor-disk refinement. Level 3 is left out
# on purpose: at ~23 M cells it does not fit the 20-minute development limit and
# belongs in the long queue with the rest of the ladder.
#
# Each task writes runs/mesh-coarse[-r<N>]/ and its own Slurm log, so the cell
# count of every level is recorded by `mesh.sh` as it accepts the mesh. The
# refined levels keep the lower cell-count bound only: the upper bound is set once
# the first build of each level reports its count.
#
# Slurm spools this script, so BASH_SOURCE is not usable; the package root is
# resolved from the submission directory instead.
#SBATCH --job-name=phaseVI-mesh
#SBATCH --partition=sequana_cpu_dev
#SBATCH --time=00:20:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --array=0-2
#SBATCH --output=runs/mesh-ladder-r%a.out
#SBATCH --error=runs/mesh-ladder-r%a.err
set -eu

if [ -z "${SLURM_SUBMIT_DIR:-}" ]; then
    echo "ERROR: SLURM_SUBMIT_DIR is unset; submit this script with sbatch" >&2
    exit 2
fi
cd "$SLURM_SUBMIT_DIR"

# Slurm runs batch scripts as non-login shells, so the `module` function has to be
# sourced explicitly before it can be used.
if ! command -v module >/dev/null 2>&1; then
    for init in /etc/profile.d/modules.sh /usr/share/Modules/init/sh; do
        if [ -r "$init" ]; then
            . "$init"
            break
        fi
    done
fi

# The SDumont module does not export the wmake identity variables and its
# LD_LIBRARY_PATH points at a dead Int32 directory (see the root AGENTS.md).
module load openfoam/v2506_openmpi-4.1.4_gnu
export WM_ARCH=linux64
export WM_COMPILER=Gcc
export WM_COMPILE_OPTION=Opt
export WM_PRECISION_OPTION=DP
export WM_LABEL_SIZE=64
export WM_OPTIONS=linux64GccDPInt64Opt
export FOAM_USER_LIBBIN=$WM_PROJECT_USER_DIR/platforms/$WM_OPTIONS/lib
export LD_LIBRARY_PATH=$FOAM_USER_LIBBIN:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib/sys-openmpi:${LD_LIBRARY_PATH:-}

level=${SLURM_ARRAY_TASK_ID:?array task id required}
echo "Building the coarse mesh at refinement level $level"
echo "OpenFOAM ${WM_PROJECT_VERSION:-unknown} on $(hostname)"

exec scripts/mesh.sh coarse --refine-level "$level"
