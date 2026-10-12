#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# P1.5 E3: equispaced blade A/B (odd/tasks/p1-5-equispaced-blade.md). One arm per submission,
# set by the environment:
#     MODEL       alm | asm | asm-mesh
#     RUN_LABEL   run directory suffix (a run id does not carry the layout)
#     BLADE_DZ    optional; equispaced spacing [m] (rule min(0.05, h/2)); absent = committed layout
#     sbatch --export=ALL,MODEL=asm-mesh,BLADE_DZ=0.05,RUN_LABEL=eqb-mesh-dz05 \
#            --output=runs/eqb-mesh-dz05.out --error=runs/eqb-mesh-dz05.err \
#            scripts/slurm/equispaced-blade.slurm
# Same configuration as `hubfix` / `s6` / the P1.4 arms: coarse level 0, delta t = 0.001 s, four
# revolutions, 84 tasks. Four revolutions are not converged: compare arms with each other.
# Do not rebuild libturbinesFoam while an arm is queued or running.
#SBATCH --job-name=phaseVI-eqb
#SBATCH --partition=sequana_cpu
#SBATCH --time=12:00:00
#SBATCH --ntasks=84
set -eu
cd "${SLURM_SUBMIT_DIR:?submit with sbatch}"
: "${MODEL:?set MODEL (export it through sbatch --export)}"
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
echo "$MODEL blade-dz ${BLADE_DZ:-committed} (label $RUN_LABEL) on $(hostname), $SLURM_NTASKS tasks"
if [ -n "${BLADE_DZ:-}" ]; then
    exec scripts/runPhaseVI.sh -m "$MODEL" -u 7 -mesh coarse --sequence H \
        --delta-t 0.001 --end-revs 4 --ranks "$SLURM_NTASKS" \
        --blade-dz "$BLADE_DZ" --run-label "$RUN_LABEL" --restart --run
fi
exec scripts/runPhaseVI.sh -m "$MODEL" -u 7 -mesh coarse --sequence H \
    --delta-t 0.001 --end-revs 4 --ranks "$SLURM_NTASKS" \
    --run-label "$RUN_LABEL" --restart --run
