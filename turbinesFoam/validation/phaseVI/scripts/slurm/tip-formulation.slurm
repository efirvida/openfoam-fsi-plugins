#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Which end-effect formulation represents this rotor, at refinement level 0.
#
# The two-switch ablation located the problem: the Glauert tip factor is singular
# at r = R (it multiplies the lift by 0.09 on the outermost elements) and removing
# it entirely overshoots the tip station from -15.5 % to +69.5 %. The Glauert root
# factor over-corrects too but removing it improves BOTH the integral and the
# 30 % span station, so it is off in the candidate.
#
#   task 0  --tip-effects off --root-effects off                 -> bothoff
#   task 1  --tip-correction on --tip-effects off --root-effects off -> dagtip
#
# Task 0 completes the 2x2 (the control, rootoff and tipoff arms are already
# measured) and task 1 is the candidate: replace the singular Glauert tip factor
# with the prescribed-helical-wake correction the package already implements.
# Both are judged on the integral AND the five span stations, because the integral
# alone would have approved the tipoff arm.
#
# 84 tasks: one core per ~80,000 cells, and 84 = 2^2*3*7 splits near-cubically.
#SBATCH --job-name=phaseVI-tipform
#SBATCH --partition=sequana_cpu
#SBATCH --time=06:00:00
#SBATCH --nodes=1-4
#SBATCH --ntasks=84
#SBATCH --array=0-1
#SBATCH --output=runs/tipform-r%a.out
#SBATCH --error=runs/tipform-r%a.err
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
case "${SLURM_ARRAY_TASK_ID}" in
    0) arm="--root-effects off --tip-effects off";                             label=bothoff ;;
    1) arm="--root-effects off --tip-effects off --tip-correction on";         label=dagtip ;;
    *) exit 2 ;;
esac
echo "arm: $label ($arm) on $(hostname), $SLURM_NTASKS tasks"
# shellcheck disable=SC2086
exec scripts/runPhaseVI.sh -m alm -u 7 -mesh coarse --sequence H \
    --delta-t 0.001 --end-revs 4 --ranks "$SLURM_NTASKS" \
    $arm --run-label "$label" --restart --run
