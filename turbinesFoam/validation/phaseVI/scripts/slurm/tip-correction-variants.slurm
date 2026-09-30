#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Phase VI tip-correction variant runs, 7 m/s coarse D/32, one variant per
# submission so several can run concurrently:
#
#   cd turbinesFoam/validation/phaseVI
#   PHASEVI_LONG_QUEUE_AUTHORIZED=1 sbatch scripts/slurm/tip-correction-variants.slurm <variant>
#
# Variants (all keep arm A's physics: rotational augmentation on, Glauert tip
# loss off, tip correction on; they differ only in the named switch):
#   multire  --polar S809_multiRe.dat   (multi-Re base loading)
#   rooton   --root-effects on          (Glauert root effect back on)
#   csu      --polar S809_CSU_Re0.65M_total.dat  (repeat of the arm-A CSU run)
#
# Cores only: no --nodes and no --mem.
#SBATCH -p sequana_cpu
#SBATCH --ntasks=48
#SBATCH -J phaseVI-tipvar
#SBATCH --time=96:00:00
#SBATCH -e %j.err
#SBATCH -o %j.out

set -eu

variant="${1:?usage: sbatch tip-correction-variants.slurm <multire|rooton|csu|n25> [speed]}"
speed="${2:-7}"

case "$variant" in
    multire) label="tipcorr-multire"; polar="S809_multiRe.dat";  root="off"; n_elems="" ;;
    rooton)  label="tipcorr-rooton";  polar="";                   root="on";  n_elems="" ;;
    csu)     label="tipcorr-csu";     polar="S809_CSU_Re0.65M_total.dat"; root="off"; n_elems="" ;;
    # nElements must be a multiple of the elementData geometry segments (25), so
    # 25 is the coarsest valid arm -- the paper's nrAero = 11 needs a geometry
    # resample, a separate change. n25 halves the spanwise resolution.
    n25)     label="tipcorr-n25";     polar="";                   root="off"; n_elems="--n-elements 25" ;;
    *) echo "ERROR: unknown variant '$variant'" >&2; exit 2 ;;
esac

if [ "${PHASEVI_LONG_QUEUE_AUTHORIZED:-0}" != "1" ]; then
    echo "ERROR: long-queue authorization not granted; export" >&2
    echo "  PHASEVI_LONG_QUEUE_AUTHORIZED=1 to submit." >&2
    exit 5
fi

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
export LD_LIBRARY_PATH=/scratch/app/gcc/14.2.0/lib64:$FOAM_USER_LIBBIN:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib/sys-openmpi:$LD_LIBRARY_PATH

pkg_dir="${PHASEVI_PKG_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}"
if [ ! -x "${pkg_dir}/scripts/runPhaseVI.sh" ]; then
    echo "ERROR: ${pkg_dir}/scripts/runPhaseVI.sh not found; submit from the" >&2
    echo "  package directory or set PHASEVI_PKG_DIR." >&2
    exit 3
fi
cd "$pkg_dir"

echo "Tip-correction variant '${variant}' (label ${label}) at U${speed} m/s on $(hostname)"

# shellcheck disable=SC2086
scripts/runPhaseVI.sh -m alm -u "$speed" -mesh coarse -s H \
    --rotational-augmentation on --root-effects "$root" \
    --tip-effects off --tip-correction on \
    ${polar:+--polar "$polar"} ${n_elems:-} \
    --run-label "$label" --restart --run

rm -rf "runs/alm-U${speed}-coarse-${label}/processor"*
echo "Variant ${variant} finished"
