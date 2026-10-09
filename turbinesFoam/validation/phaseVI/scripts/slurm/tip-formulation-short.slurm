#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# 20-minute development-queue probe of the end-effect candidate.
#
# The long-queue arms (tip-formulation.slurm) cannot start while the association
# holds its four concurrent jobs, and the question this arm answers is the
# SPANWISE one: does replacing the singular Glauert tip factor with the
# prescribed-helical-wake correction fix the 95 % span station without breaking
# the 30 % one. One revolution is enough for that, because the solution is already
# stationary by then (the per-revolution cp increments fall to 3e-4 by the third),
# and the comparison runs against the control's SAME window.
#
# 48 tasks on one dev node, because one node of 48 ranks was measurably faster per
# step than 84 ranks spread over four (1.15 s vs 1.63 s). Label `dagtipd` keeps it
# in its own directory: a 1-revolution run decomposes into processor48 and cannot
# be resumed by the 84-rank long arm.
#SBATCH --job-name=phaseVI-tipform-dev
#SBATCH --partition=sequana_cpu_dev
#SBATCH --time=00:20:00
#SBATCH --nodes=1
#SBATCH --ntasks=48
#SBATCH --output=runs/tipformd.out
#SBATCH --error=runs/tipformd.err
set -eu
cd "${SLURM_SUBMIT_DIR:?submit with sbatch}"
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
export LD_LIBRARY_PATH=$FOAM_USER_LIBBIN:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib/sys-openmpi:$LD_LIBRARY_PATH

echo "dev probe on $(hostname), $SLURM_NTASKS tasks"
exec scripts/runPhaseVI.sh -m alm -u 7 -mesh coarse --sequence H \
    --delta-t 0.001 --end-revs 1 --ranks "$SLURM_NTASKS" \
    --root-effects off --tip-effects off --tip-correction on \
    --run-label dagtipd --run
