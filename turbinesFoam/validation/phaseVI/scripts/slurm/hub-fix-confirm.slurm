#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Confirmation run for the Prandtl hub-loss fix (see CHANGELOG entry 19).
#
# Same configuration as the `alm-U7-coarse` control arm the ablation measured
# (level 0, delta t = 0.001 s, four revolutions, 84 tasks), so the two are
# comparable directly. Two changes with respect to that arm: the root factor is
# now AeroDyn's hub loss, and the polar Reynolds rescaling is off. Both are
# expected to raise the load inboard: the ablation's `--root-effects off` arm
# measured the first at +4.5 points of cp, and the rescaling measurement is
# +5.8 % of lift on the mean.
#SBATCH --job-name=phaseVI-hubfix
#SBATCH --partition=sequana_cpu
#SBATCH --time=06:00:00
#SBATCH --nodes=1-4
#SBATCH --ntasks=84
#SBATCH --output=runs/hubfix.out
#SBATCH --error=runs/hubfix.err
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
echo "hub-loss confirmation on $(hostname), $SLURM_NTASKS tasks"
exec scripts/runPhaseVI.sh -m alm -u 7 -mesh coarse --sequence H \
    --delta-t 0.001 --end-revs 4 --ranks "$SLURM_NTASKS" \
    --run-label hubfix --restart --run
