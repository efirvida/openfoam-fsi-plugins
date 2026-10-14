#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Nacelle on/off study, Phase VI ALM 7 m/s Sequence H (odd/tasks/nacelle-onoff-study.md, N1).
# One run per submission, set by the environment:
#     NACELLE     on | off
#     sbatch --export=ALL,NACELLE=off --output=runs/nacelle-U7-off.out \
#            --error=runs/nacelle-U7-off.err scripts/slurm/nacelle-onoff.slurm
#     sbatch --export=ALL,NACELLE=on  --output=runs/nacelle-U7-on.out \
#            --error=runs/nacelle-U7-on.err  scripts/slurm/nacelle-onoff.slurm
# Same options as the p21 ALM 7 m/s run (coarse level 0, delta t = 0.001 s, 12 revolutions,
# 84 tasks, blade dz 0.05 m); the only difference between the pair is --nacelle. Runs are
# alm-U7-coarse-nacoff / alm-U7-coarse-nacon. Restartable: resubmit the same line to continue.
# Do not rebuild libturbinesFoam while a run is queued or running.
#SBATCH --job-name=phaseVI-nacelle
#SBATCH --partition=sequana_cpu
#SBATCH --time=24:00:00
#SBATCH --ntasks=84
set -eu
cd "${SLURM_SUBMIT_DIR:?submit with sbatch}"
: "${NACELLE:?set NACELLE=on|off (export it through sbatch --export)}"
case "$NACELLE" in
    on|off) ;;
    *) echo "NACELLE must be on or off" >&2; exit 2 ;;
esac
RUN_LABEL=nac$NACELLE
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
echo "ALM U7 nacelle $NACELLE on $(hostname), $SLURM_NTASKS tasks"
exec scripts/runPhaseVI.sh -m alm -u 7 -mesh coarse --sequence H \
    --delta-t 0.001 --end-revs 12 --ranks "$SLURM_NTASKS" \
    --blade-dz 0.05 --nacelle "$NACELLE" --run-label "$RUN_LABEL" --restart --run
