#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Phase VI arm-A tip-correction verification, 7 m/s coarse D/32.
#
# Arm A physics: rotational augmentation on (Du-Selig a=b=d=1), Glauert root
# effect off, Glauert TIP loss off, and the Dag & Sorensen 2020 induced-velocity
# tip correction ON. This is the candidate that should close the 7 m/s
# power/torque gap: arm A' (tip loss off, no correction) measured +19.5 % (OSU)
# and +16.8 % (CSU); the correction must bring it back toward the measured
# 5.95 kW / 789.9 Nm / 1132 N.
#
# Two runs, sequentially on one 48-rank allocation:
#   1. committed default polar (OSU Re=1e6)
#   2. CSU Re=0.65e6 ablation polar (the closer base: arm A' +16.8 %)
# Both are Sequence H, coarse D/32, revs 0 -> ~12 (the full comparison window),
# restartable, at the committed 48-way decomposition.
#
# Cores only: no --nodes and no --mem (project policy; Slurm places the ranks
# and the partition DefMemPerCPU governs). The MPI openib-BTL workaround lives
# in runPhaseVI.sh.
#
# Submit from the validation package directory (Slurm spools the script, so the
# package is resolved from $SLURM_SUBMIT_DIR):
#   cd turbinesFoam/validation/phaseVI
#   PHASEVI_LONG_QUEUE_AUTHORIZED=1 sbatch scripts/slurm/tip-correction-arm.slurm
#SBATCH -p sequana_cpu
#SBATCH --ntasks=48
#SBATCH -J phaseVI-tipcorr
#SBATCH --time=96:00:00
#SBATCH -e %j.err
#SBATCH -o %j.out

set -eu

if [ "${PHASEVI_LONG_QUEUE_AUTHORIZED:-0}" != "1" ]; then
    echo "ERROR: long-queue authorization not granted; export" >&2
    echo "  PHASEVI_LONG_QUEUE_AUTHORIZED=1 to submit." >&2
    exit 5
fi

module purge
module load openfoam/v2506_openmpi-4.1.4_gnu gcc

# The module exports Int32 paths; set the Int64 identity first and re-source the
# OpenFOAM bashrc so PATH points at the installed linux64GccDPInt64Opt binaries.
export WM_ARCH=linux64
export WM_COMPILER=Gcc
export WM_COMPILE_OPTION=Opt
export WM_PRECISION_OPTION=DP
export WM_LABEL_SIZE=64
export WM_OPTIONS=linux64GccDPInt64Opt
# etc/bashrc is not written for strict mode: it dereferences optional variables
# and can return non-zero, so `set -eu` aborts the job while sourcing it.
# Disable both while sourcing, then restore them.
set +eu
. "$WM_PROJECT_DIR/etc/bashrc"
set -eu

export FOAM_USER_LIBBIN=$WM_PROJECT_USER_DIR/platforms/$WM_OPTIONS/lib
# libturbinesFoam.so is built with the GCC-14 toolchain: prepend its libstdc++
# (GLIBCXX_3.4.32 / CXXABI_1.3.15) or the built library fails to load.
export LD_LIBRARY_PATH=/scratch/app/gcc/14.2.0/lib64:$FOAM_USER_LIBBIN:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib/sys-openmpi:$LD_LIBRARY_PATH

# Slurm executes a spooled copy, so BASH_SOURCE does not point into the
# repository; resolve the package from the submission directory instead.
pkg_dir="${PHASEVI_PKG_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}"
if [ ! -x "${pkg_dir}/scripts/runPhaseVI.sh" ]; then
    echo "ERROR: ${pkg_dir}/scripts/runPhaseVI.sh not found; submit from the" >&2
    echo "  package directory or set PHASEVI_PKG_DIR." >&2
    exit 3
fi
cd "$pkg_dir"

echo "Tip-correction arm A on $(hostname); package: $pkg_dir"

# Continue-on-error across the two independent runs; exit 1 if either failed.
failed=0

run_one() {
    label="$1"
    polar="$2"
    echo "=== ${label} (polar=${polar:-default}) ==="
    # shellcheck disable=SC2086
    if scripts/runPhaseVI.sh -m alm -u 7 -mesh coarse -s H \
        --rotational-augmentation on --root-effects off \
        --tip-effects off --tip-correction on \
        ${polar:+--polar "$polar"} \
        --run-label "$label" --restart --run
    then
        echo "=== ${label} finished ==="
        # Reclaim quota: the reconstructed time directories are kept, the
        # per-rank decomposition is regenerable and is removed (project policy).
        rm -rf "runs/alm-U7-coarse-${label}/processor"*
    else
        echo "ERROR: ${label} failed" >&2
        failed=1
    fi
}

run_one tipcorr ""
run_one tipcorr-csu "S809_CSU_Re0.65M_total.dat"

if [ "$failed" -ne 0 ]; then
    echo "ERROR: at least one tip-correction arm run failed" >&2
    exit 1
fi
echo "Tip-correction arm A finished"
