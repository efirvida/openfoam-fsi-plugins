#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Two arms that decompose the ~16 % power deficit: same committed case at
# refinement level 0, same four revolutions and same delta-t, differing only in
# which end-effect switch is off.
#
#   task 0  --root-effects off  -> alm-U7-coarse-rootoff
#   task 1  --tip-effects  off  -> alm-U7-coarse-tipoff
#
# The control arm is the ladder's own level 0 (alm-U7-coarse), so no third task is
# needed. 84 tasks for the same reason as the ladder: one core per ~80,000 cells,
# and 84 = 2^2*3*7 factorises to a near-cubic (7 4 3) split.
#SBATCH --job-name=phaseVI-ablation
#SBATCH --partition=sequana_cpu
#SBATCH --time=06:00:00
#SBATCH --nodes=1-4
#SBATCH --ntasks=84
#SBATCH --array=0-1
#SBATCH --output=runs/ablation-r%a.out
#SBATCH --error=runs/ablation-r%a.err
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
    0) arm="--root-effects off"; label=rootoff ;;
    1) arm="--tip-effects off";  label=tipoff ;;
    *) exit 2 ;;
esac
echo "arm: $label ($arm) on $(hostname), $SLURM_NTASKS tasks"
# shellcheck disable=SC2086
exec scripts/runPhaseVI.sh -m alm -u 7 -mesh coarse --sequence H \
    --delta-t 0.001 --end-revs 4 --ranks "$SLURM_NTASKS" \
    $arm --run-label "$label" --restart --run
