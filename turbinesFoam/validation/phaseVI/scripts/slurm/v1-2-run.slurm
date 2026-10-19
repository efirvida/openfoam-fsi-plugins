#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Generic Model Definition v1.2 run (production-readiness campaign R1/R2, owner-approved 2026-10-17).
# Every v1.2 knob is passed explicitly; check the rendered case with scripts/checkModelDefinition.py.
# Set by the environment:
#     MODEL        alm | asm | asm-mesh
#     SPEED        wind speed token of config/case.yaml for SEQUENCE
#     SEQUENCE     H | S
#     LABEL        run label (run dir: runs/<model>-U<speed>-coarse[-r<level>]-<label>)
#     REFINE_LEVEL optional, default 0 (meshFactor scaled by 2**level: eps fixed in metres, R1 ladder)
#     DELTA_T      optional, default 0.001 s
#     END_REVS     optional, default 12 (a larger value with the same line extends a finished run)
#     POLAR        optional, default S809_OSU_Re1M_pressure.dat (any other polar is NOT of record)
#     sbatch --export=ALL,MODEL=alm,SPEED=5,SEQUENCE=S,LABEL=v12 \
#            --output=runs/v12-alm-S-U5.out --error=runs/v12-alm-S-U5.err scripts/slurm/v1-2-run.slurm
# 12 revolutions by default, 84 tasks, blade dz 0.05 m. NOT restartable: runPhaseVI.sh refuses --restart on written state; give --time for the full length.
# Do not rebuild libturbinesFoam while a run is queued or running.
#SBATCH --job-name=phaseVI-v12run
#SBATCH --partition=sequana_cpu
#SBATCH --time=12:00:00
#SBATCH --ntasks=84
set -eu
cd "${SLURM_SUBMIT_DIR:?submit with sbatch}"
: "${MODEL:?set MODEL}"
: "${SPEED:?set SPEED}"
: "${SEQUENCE:?set SEQUENCE}"
: "${LABEL:?set LABEL}"
REFINE_LEVEL=${REFINE_LEVEL:-0}
DELTA_T=${DELTA_T:-0.001}
END_REVS=${END_REVS:-12}
POLAR=${POLAR:-S809_OSU_Re1M_pressure.dat}
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
echo "$MODEL $SEQUENCE U$SPEED level $REFINE_LEVEL dt $DELTA_T revs $END_REVS polar $POLAR label $LABEL on $(hostname), $SLURM_NTASKS tasks"
exec scripts/runPhaseVI.sh -m "$MODEL" -u "$SPEED" -mesh coarse --sequence "$SEQUENCE" \
    --refine-level "$REFINE_LEVEL" --delta-t "$DELTA_T" --end-revs "$END_REVS" --ranks "$SLURM_NTASKS" \
    --blade-dz 0.05 --polar "$POLAR" --tip-effects on --tip-correction off \
    --root-effects on --rotational-augmentation off --run-label "$LABEL" --restart --run
