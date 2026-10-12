#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# P1.4: epsilon/h sensitivity of the ASM kernel (odd/tasks/p1-4-asm-epsilon-sensitivity.md).
# One arm per submission; the arm is set by the environment, not by editing this file:
#     MESH_FACTOR   the ASM projection width factor, eps = 2*cbrt(V)*MESH_FACTOR
#     RUN_LABEL     run directory suffix (a run id does not carry the factor)
#     sbatch --export=ALL,MESH_FACTOR=0.5,RUN_LABEL=asm-mf0p5 \
#            --output=runs/asm-mf0p5.out --error=runs/asm-mf0p5.err \
#            scripts/slurm/asm-epsilon-sensitivity.slurm
# Same configuration as the `hubfix` (ALM) and `s6` arms: coarse level 0, delta t = 0.001 s,
# four revolutions, 84 tasks, so the arms compare directly with each other and with
# `runs/alm-U7-coarse-hubfix`. Four revolutions are not a converged state (cp drifts about
# 0.7 %/rev): compare arms with each other, do not quote an absolute level.
# Do not rebuild libturbinesFoam while an arm is queued or running: the job loads it at start.
#SBATCH --job-name=phaseVI-asm-eps
#SBATCH --partition=sequana_cpu
#SBATCH --time=06:00:00
#SBATCH --nodes=1-4
#SBATCH --ntasks=84
set -eu
cd "${SLURM_SUBMIT_DIR:?submit with sbatch}"
: "${MESH_FACTOR:?set MESH_FACTOR (export it through sbatch --export)}"
: "${RUN_LABEL:?set RUN_LABEL (export it through sbatch --export)}"
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
echo "ASM meshFactor $MESH_FACTOR (label $RUN_LABEL) on $(hostname), $SLURM_NTASKS tasks"
exec scripts/runPhaseVI.sh -m asm -u 7 -mesh coarse --sequence H \
    --delta-t 0.001 --end-revs 4 --ranks "$SLURM_NTASKS" \
    --mesh-factor "$MESH_FACTOR" \
    --run-label "$RUN_LABEL" --restart --run
