#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Run the Phase VI mesh-convergence ladder on the four built meshes.
#
# Usage (from the validation/phaseVI directory):
#   sbatch scripts/slurm/convergence-ladder.slurm
#
# One job, two array tasks, two levels each: task 0 runs levels 0 and 1, task 1
# runs levels 2 and 3, each at 7 m/s Sequence H over the full 12 revolutions. The
# array is what buys wall time by running on two nodes at once; the 48 tasks exist
# because the case is decomposed into 48 subdomains and because this cluster grants
# 8000 MB per CPU (`DefMemPerCPU`), so the task count is also the memory request.
#
# The point of the ladder is that the MESH is the only variable, so two couplings
# are deliberately pinned instead of being allowed to follow the refinement:
#
#   * `--delta-t 0.001` on every level, the value the finest level requires (the
#     tip may not move further than the refined hub-adjacent cell in one step). If
#     the step shrank with the mesh, the temporal error would shrink in lockstep
#     with the spatial one and a monotone trend could not be attributed to the
#     mesh.
#   * `gaussian_mesh_factor` is scaled by `2**level` inside the generator, which
#     holds the actuator line's projection width at 0.629 m. Otherwise eps would
#     halve per level and the ladder would measure the model, not the discretisation.
#
# `--restart` is set so a task can be resumed if the 24 h wall time is exhausted.
#
# Slurm spools this script, so BASH_SOURCE is not usable; the package root is
# resolved from the submission directory instead.
# Only `--ntasks` is a resource decision: this cluster grants 8000 MB per CPU
# (`DefMemPerCPU`), so the task count is also the memory request, and Slurm places
# the nodes. `--nodes` is left as a range rather than 1 because the levels need
# very different rank counts and pinning one node capped the job at 48.
#
# The rank count is one core per ~80,000 cells, measured on this cluster as the
# best cost/benefit point (80k per CORE, so one task per core):
#
#   level 0  6,674,304 cells ->  84 tasks
#   level 1  6,832,896 cells ->  86 tasks
#   level 2  8,137,584 cells -> 102 tasks
#   level 3 18,454,156 cells -> 231 tasks
#
# Two levels share one array task, so the submitted `--ntasks` is the larger of
# the two and the smaller level runs slightly over-parallel rather than under.
#SBATCH --job-name=phaseVI-ladder
#SBATCH --partition=sequana_cpu
#SBATCH --time=24:00:00
#SBATCH --nodes=1-8
#SBATCH --ntasks=86
#SBATCH --array=0-1
#SBATCH --output=runs/ladder-r%a.out
#SBATCH --error=runs/ladder-r%a.err
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
echo "pimpleFoam: $(command -v pimpleFoam || echo MISSING)"
echo "tasks: $SLURM_NTASKS"
echo "Running the convergence ladder at refinement levels: $levels"

status=0
for level in $levels; do
    echo "=== ladder level $level ==="
    # Four complete revolutions, not the production twelve. The convergence
    # question is where the per-revolution behaviour stops changing, and the
    # comparison reads that from the per-revolution drift table: four revolutions
    # are enough to see it, and they cut the ladder's cost threefold. The
    # comparison has to match this window, so it is run with
    # `--revolutions 1 4 --allow-short-window`.
    # Continue across levels so one failure still leaves the other meshes measured.
    if ! scripts/runPhaseVI.sh -m alm -u 7 -mesh coarse --sequence H \
            --refine-level "$level" --delta-t 0.001 --end-revs 4 \
            --ranks "$SLURM_NTASKS" --restart --run; then
        echo "ERROR: ladder level $level failed" >&2
        status=1
    fi
done
exit $status
