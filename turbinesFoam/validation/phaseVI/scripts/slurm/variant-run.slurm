#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# A/B arm of v1.2. Run from phaseVI; VARIANT is required, LABEL defaults var-<variant>.
# MODEL, SPEED, SEQUENCE required; REFINE_LEVEL, DELTA_T, END_REVS, POLAR as v1-2-run.slurm.
# Preflight without allocation: VARIANT=ring-sampling sh scripts/slurm/variant-run.slurm --check
# Then: sbatch --export=ALL,VARIANT=ring-sampling,MODEL=alm,SPEED=7,SEQUENCE=S scripts/slurm/variant-run.slurm
# --check validates only the registry; never submits or prepares a case.
# Optional LIB_DIR prepends a run-local library directory (e.g. $PWD/runs/lib-flags).
#SBATCH --job-name=phaseVI-variant
#SBATCH --partition=sequana_cpu
#SBATCH --time=12:00:00
#SBATCH --ntasks=84
set -eu
cd "${SLURM_SUBMIT_DIR:-.}"
: "${VARIANT:?set VARIANT}"
# Refuse unknown arms before modules, environment checks or run-directory work.
flags=$(python3 scripts/checkModelDefinition.py --variant "$VARIANT" --renderer-flags) || exit $?
if [ "${1:-}" = --check ]; then exit 0; fi
: "${MODEL:?set MODEL}"
: "${SPEED:?set SPEED}"
: "${SEQUENCE:?set SEQUENCE}"
LABEL=${LABEL:-var-$VARIANT}
REFINE_LEVEL=${REFINE_LEVEL:-0}
DELTA_T=${DELTA_T:-0.001}
END_REVS=${END_REVS:-12}
POLAR=${POLAR:-S809_OSU_Re1M_pressure.dat}
module purge
module load openfoam/v2506_openmpi-4.1.4_gnu gcc
export WM_ARCH=linux64 WM_COMPILER=Gcc WM_COMPILE_OPTION=Opt
export WM_PRECISION_OPTION=DP WM_LABEL_SIZE=64 WM_OPTIONS=linux64GccDPInt64Opt
set +eu
. "$WM_PROJECT_DIR/etc/bashrc"
set -eu
export FOAM_USER_LIBBIN=$WM_PROJECT_USER_DIR/platforms/$WM_OPTIONS/lib
export LD_LIBRARY_PATH=$FOAM_USER_LIBBIN:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib/sys-openmpi:$LD_LIBRARY_PATH
if [ -n "${LIB_DIR:-}" ]; then
    test -f "$LIB_DIR/libturbinesFoam.so" || { echo "missing $LIB_DIR/libturbinesFoam.so" >&2; exit 3; }
    export LD_LIBRARY_PATH=$LIB_DIR:$LD_LIBRARY_PATH
fi
# Registry validation admits only known flags and scalar enum/numeric values.
# Deliberately split token-per-line output, with pathname expansion disabled.
set -f
set -- $flags
exec scripts/runPhaseVI.sh -m "$MODEL" -u "$SPEED" -mesh coarse --sequence "$SEQUENCE" \
    --refine-level "$REFINE_LEVEL" --delta-t "$DELTA_T" --end-revs "$END_REVS" --ranks "$SLURM_NTASKS" \
    --blade-dz 0.05 --polar "$POLAR" --tip-effects on --tip-correction off \
    --root-effects on --rotational-augmentation off "$@" --run-label "$LABEL" --restart --run
