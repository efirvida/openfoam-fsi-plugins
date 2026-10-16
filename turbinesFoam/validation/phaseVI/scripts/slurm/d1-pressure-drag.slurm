#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# DIAGNOSTIC arm D1: Sequence H, ALM 7 m/s, pressure-drag polar (--polar S809_OSU_Re1M_pressure.dat),
# otherwise identical to P2.1 (alm-U7-coarse-p21). Not the frozen definition. One run per
# submission, set by the environment:
#     MODEL       alm | asm | asm-mesh
#     SPEED       7 | 10  [m/s]
#     sbatch --export=ALL,MODEL=asm-mesh,SPEED=7 \
#            --output=runs/p22-asm-mesh-U7.out --error=runs/p22-asm-mesh-U7.err \
#            scripts/slurm/p2-2-sequence-s.slurm
# Coarse level 0, delta t = 0.001 s, 12 revolutions, 84 tasks, blade dz 0.05 m (rule
# min(0.05, h/2) on the coarse mesh). Restartable: resubmit the same line to continue.
# Do not rebuild libturbinesFoam while a run is queued or running.
#SBATCH --job-name=phaseVI-d1pdrag
#SBATCH --partition=sequana_cpu
#SBATCH --time=07:00:00
#SBATCH --ntasks=84
set -eu
cd "${SLURM_SUBMIT_DIR:?submit with sbatch}"
: "${MODEL:?set MODEL (export it through sbatch --export)}"
: "${SPEED:?set SPEED (export it through sbatch --export)}"
RUN_LABEL=d1-pdrag
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
echo "$MODEL U$SPEED p22 on $(hostname), $SLURM_NTASKS tasks"
exec scripts/runPhaseVI.sh -m "$MODEL" -u "$SPEED" -mesh coarse --sequence H \
    --polar S809_OSU_Re1M_pressure.dat \
    --delta-t 0.001 --end-revs 12 --ranks "$SLURM_NTASKS" \
    --blade-dz 0.05 --run-label "$RUN_LABEL" --restart --run
