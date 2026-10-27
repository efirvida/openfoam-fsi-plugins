#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Model Definition v1.2 evaluation (owner, 2026-10-17): Glauert tip + Prandtl hub on, D&S off, OSU Re 1e6
# pressure-drag polar. Every v1.2 knob is passed explicitly so the run never depends on renderer defaults
# (the P2 runs silently used the case.yaml tip default instead of the v1.1 D&S). One run per
# submission, set by the environment:
#     MODEL       alm | asm | asm-mesh
#     SPEED       7 | 10  [m/s]
#     sbatch --export=ALL,MODEL=asm-mesh,SPEED=7 \
#            --output=runs/v12-asm-mesh-U7.out --error=runs/v12-asm-mesh-U7.err \
#            scripts/slurm/v1-2-evaluation.slurm
# Coarse level 0, delta t = 0.001 s, 12 revolutions, 84 tasks, blade dz 0.05 m (rule
# min(0.05, h/2) on the coarse mesh). NOT restartable: runPhaseVI.sh refuses --restart on written state; give --time for the full length.
# Do not rebuild libturbinesFoam while a run is queued or running.
#SBATCH --job-name=phaseVI-v12
#SBATCH --partition=sequana_cpu
#SBATCH --time=12:00:00
#SBATCH --ntasks=84
set -eu
cd "${SLURM_SUBMIT_DIR:?submit with sbatch}"
: "${MODEL:?set MODEL (export it through sbatch --export)}"
: "${SPEED:?set SPEED (export it through sbatch --export)}"
RUN_LABEL=v12
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
echo "$MODEL U$SPEED v12 on $(hostname), $SLURM_NTASKS tasks"
exec scripts/runPhaseVI.sh -m "$MODEL" -u "$SPEED" -mesh coarse --sequence S \
    --delta-t 0.001 --end-revs 12 --ranks "$SLURM_NTASKS" \
    --blade-dz 0.05 --polar S809_OSU_Re1M_pressure.dat --tip-effects on --tip-correction off --pitch-reference twist-zero \
    --root-effects on --rotational-augmentation off --run-label "$RUN_LABEL" --restart --run
