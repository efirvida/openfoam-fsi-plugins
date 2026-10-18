#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# P2.3 T4: measure the one-step lag of the Glauert factor. Loads the NOT-installed library built from commit
# 0c723e4+ into runs/lib-p23 (element CSV gains end_effect_phi_deg, inflow_ref_angle_deg) by prepending it to
# LD_LIBRARY_PATH; every other job keeps the installed library. Also a regression check: with the same v1.2
# knobs it must reproduce runs/alm-U7-coarse-d1-pdrag over the same revolutions (the change only adds columns).
# Diagnostic, 4 revolutions; not of record.
# Set by the environment:
#     MODEL        alm | asm | asm-mesh
#     SPEED        wind speed token of config/case.yaml for SEQUENCE
#     SEQUENCE     H | S
#     LABEL        run label (run dir: runs/<model>-U<speed>-coarse[-r<level>]-<label>)
#     REFINE_LEVEL optional, default 0 (meshFactor scaled by 2**level: eps fixed in metres, R1 ladder)
#     DELTA_T      optional, default 0.001 s
#     sbatch --export=ALL,MODEL=alm,SPEED=5,SEQUENCE=S,LABEL=v12 \
#            --output=runs/v12-alm-S-U5.out --error=runs/v12-alm-S-U5.err scripts/slurm/v1-2-run.slurm
# 12 revolutions, 84 tasks, blade dz 0.05 m. Restartable: resubmit the same line to continue.
# Do not rebuild libturbinesFoam while a run is queued or running.
#SBATCH --job-name=phaseVI-v12lag
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
LIB_P23=$PWD/runs/lib-p23
test -f "$LIB_P23/libturbinesFoam.so" || { echo "missing $LIB_P23/libturbinesFoam.so" >&2; exit 3; }
cat "$LIB_P23/BUILD_INFO"
export LD_LIBRARY_PATH=$LIB_P23:$FOAM_USER_LIBBIN:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib/sys-openmpi:$LD_LIBRARY_PATH
echo "$MODEL $SEQUENCE U$SPEED level $REFINE_LEVEL dt $DELTA_T label $LABEL on $(hostname), $SLURM_NTASKS tasks"
exec scripts/runPhaseVI.sh -m "$MODEL" -u "$SPEED" -mesh coarse --sequence "$SEQUENCE" \
    --refine-level "$REFINE_LEVEL" --delta-t "$DELTA_T" --end-revs 4 --ranks "$SLURM_NTASKS" \
    --blade-dz 0.05 --polar S809_OSU_Re1M_pressure.dat --tip-effects on --tip-correction off \
    --root-effects on --rotational-augmentation off --run-label "$LABEL" --restart --run
