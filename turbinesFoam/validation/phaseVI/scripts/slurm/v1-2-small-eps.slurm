#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# P2.3 T5 (owner, 2026-10-17): Model Definition v1.2 ALM on Sequence H 7 m/s at a SMALLER projection width.
# Refine level 1 (rotor disk h/2) with --mesh-factor 0.5, so the effective meshFactor is 1 and
# eps = 2*cbrt(V) = 0.31 m instead of 0.63 m (the sampling ring shrinks with it, 3.3 eps). Reference arm:
# runs/alm-U7-coarse-d1-pdrag (same v1.2 knobs, level 0). Tip c_n falling further = double counting of the
# Glauert factor over a better-resolved tip vortex; rising toward the experiment = under-resolution. One run per
# submission, set by the environment:
#     MODEL       alm | asm | asm-mesh
#     SPEED       7 | 10  [m/s]
#     sbatch --export=ALL,MODEL=alm,SPEED=7 \
#            --output=runs/v12eps-alm-U7.out --error=runs/v12eps-alm-U7.err \
#            scripts/slurm/v1-2-small-eps.slurm
# Coarse base + refine level 1 (6.83 M cells vs 6.67 M), delta t = 0.001 s, 12 revolutions, 84 tasks, blade dz 0.05 m (rule
# min(0.05, h/2), h/2 = 0.078 m at level 1). NOT restartable: runPhaseVI.sh refuses --restart on written state; give --time for the full length.
# Do not rebuild libturbinesFoam while a run is queued or running.
#SBATCH --job-name=phaseVI-v12eps
#SBATCH --partition=sequana_cpu
#SBATCH --time=12:00:00
#SBATCH --ntasks=84
set -eu
cd "${SLURM_SUBMIT_DIR:?submit with sbatch}"
: "${MODEL:?set MODEL (export it through sbatch --export)}"
: "${SPEED:?set SPEED (export it through sbatch --export)}"
RUN_LABEL=v12-eps1
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
echo "$MODEL U$SPEED v12-eps1 on $(hostname), $SLURM_NTASKS tasks"
exec scripts/runPhaseVI.sh -m "$MODEL" -u "$SPEED" -mesh coarse --sequence H --refine-level 1 --mesh-factor 0.5 \
    --delta-t 0.001 --end-revs 12 --ranks "$SLURM_NTASKS" \
    --blade-dz 0.05 --polar S809_OSU_Re1M_pressure.dat --tip-effects on --tip-correction off \
    --root-effects on --rotational-augmentation off --run-label "$RUN_LABEL" --restart --run
