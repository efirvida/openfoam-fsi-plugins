#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# S6 arm: rotational augmentation, the last untested model lever.
#
# Same configuration as the `hubfix` arm (coarse level 0, delta t = 0.001 s, four
# revolutions, 84 tasks) so the two are directly comparable. The ONLY change is
# `actuator.rotational_augmentation.active`, rendered as
#
#     rotationalAugmentation { active on; model DuSelig; a 1; b 1; d 1; }
#
# DuSelig with a = b = d = 1 is the uncalibrated form; nothing is fitted. It is
# the lever that edits the INBOARD lift relation, which is where the spanwise
# comparison locates the surplus: `scripts/compareSectionLoads.py` measures the
# frame-free resultant R at +12.6 % at r/R = 0.30, +0.2/+0.5 % mid-span and
# -14.2 % at 0.95. A lever that raises inboard lift would worsen the inboard
# surplus, so a null or negative power response is a real answer, not a failure.
#SBATCH --job-name=phaseVI-s6
#SBATCH --partition=sequana_cpu
#SBATCH --time=06:00:00
#SBATCH --nodes=1-4
#SBATCH --ntasks=84
#SBATCH --output=runs/s6-rot-aug.out
#SBATCH --error=runs/s6-rot-aug.err
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
echo "rotational augmentation (DuSelig, a=b=d=1) on $(hostname), $SLURM_NTASKS tasks"
exec scripts/runPhaseVI.sh -m alm -u 7 -mesh coarse --sequence H \
    --delta-t 0.001 --end-revs 4 --ranks "$SLURM_NTASKS" \
    --rotational-augmentation on \
    --run-label s6-rot-aug --restart --run
