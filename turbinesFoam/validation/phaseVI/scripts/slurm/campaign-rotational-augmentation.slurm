#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Phase VI validation power-curve campaign: the converged run of the
# rotational-augmentation candidate. One array task per (model, speed, mesh)
# combination, 48 ranks on one node, at most 96 h wall time
# (maintainer-authorized), restarting from the latest written time.
#
# Candidate configuration (single arm for clean comparability):
#   rotational augmentation ON + Glauert root effects OFF
#   (`--rotational-augmentation on --root-effects off`), i.e. the YAML keys
#   `actuator.rotational_augmentation.active = true` and
#   `actuator.end_effects.root = false` for this render. Everything else is the
#   committed case (dynamic stall off, tip effects on, Du-Selig a=b=d=1).
#
# Matrix: 21 tasks = 3 models x 5 speeds on D/32 (coarse)
#                     + 3 models x 2 speeds on D/48 (fine spot-check).
#   coarse D/32, full curve: alm / asm / asm-mesh at 7, 10, 13, 15, 25 m/s
#   fine   D/48, spot-check: alm / asm / asm-mesh at 7 and 13 m/s
# 20 m/s is deliberately absent (renderable but not staged).
#
# Baseline: the ALM/ASM `aug off` Stage 1+2 results (2026-09-21), preserved
# under results/U*-H/. The ASM-MESH baseline is NOT part of this matrix - the
# candidate is the arm being launched. Compare the candidate outputs into a
# separate `--out` directory so the baseline results are not overwritten
# (see CAMPAIGN.md).
#
# PREPARED ONLY. This file refuses to run without
# PHASEVI_LONG_QUEUE_AUTHORIZED=1 and is never submitted by the preparing
# change. `runPhaseVI.sh --submit` does not launch this array.
#
# Submit from the validation package directory (Slurm spools the script, so the
# package is resolved from $SLURM_SUBMIT_DIR):
#   cd turbinesFoam/validation/phaseVI
#   PHASEVI_LONG_QUEUE_AUTHORIZED=1 sbatch scripts/slurm/campaign-rotational-augmentation.slurm
#SBATCH -p sequana_cpu
#SBATCH --ntasks=48
#SBATCH --nodes=1
#SBATCH -J phaseVI-ra-campaign
#SBATCH --time=96:00:00
#SBATCH --array=0-20
#SBATCH -e %j.err
#SBATCH -o %j.out

set -eu

if [ "${PHASEVI_LONG_QUEUE_AUTHORIZED:-0}" != "1" ]; then
    echo "ERROR: long-queue authorization not granted; this file is prepared only." >&2
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
# (WM_PROJECT_SITE on SDumont) and can return non-zero, so `set -eu` aborts the
# job while sourcing it. Disable both while sourcing, then restore them.
set +eu
. "$WM_PROJECT_DIR/etc/bashrc"
set -eu

export FOAM_USER_LIBBIN=$WM_PROJECT_USER_DIR/platforms/$WM_OPTIONS/lib
# libturbinesFoam.so is built with the GCC-14 toolchain: prepend its libstdc++
# (GLIBCXX_3.4.32 / CXXABI_1.3.15) or the built library fails to load. The
# OpenFOAM Int64 lib and the openmpi sys dir stay on the search path.
export LD_LIBRARY_PATH=/scratch/app/gcc/14.2.0/lib64:$FOAM_USER_LIBBIN:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib/sys-openmpi:$LD_LIBRARY_PATH

# Slurm executes a spooled copy of this script (/var/spool/slurmd/...), so
# BASH_SOURCE does not point into the repository; resolve the package from the
# submission directory instead (same fix as production.slurm/asm-mesh.slurm).
pkg_dir="${PHASEVI_PKG_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}"
if [ ! -x "${pkg_dir}/scripts/runPhaseVI.sh" ]; then
    echo "ERROR: ${pkg_dir}/scripts/runPhaseVI.sh not found; submit from the package directory or set PHASEVI_PKG_DIR." >&2
    exit 3
fi

# Task table (SLURM_ARRAY_TASK_ID -> "model:speed:mesh"):
#   0-4    alm       7,10,13,15,25  coarse   full curve, D/32
#   5-9    asm       7,10,13,15,25  coarse   full curve, D/32
#   10-14  asm-mesh  7,10,13,15,25  coarse   full curve, D/32
#   15-16  alm       7,13           fine     D/48 spot-check
#   17-18  asm       7,13           fine     D/48 spot-check
#   19-20  asm-mesh  7,13           fine     D/48 spot-check
combos=(
    "alm:7:coarse"
    "alm:10:coarse"
    "alm:13:coarse"
    "alm:15:coarse"
    "alm:25:coarse"
    "asm:7:coarse"
    "asm:10:coarse"
    "asm:13:coarse"
    "asm:15:coarse"
    "asm:25:coarse"
    "asm-mesh:7:coarse"
    "asm-mesh:10:coarse"
    "asm-mesh:13:coarse"
    "asm-mesh:15:coarse"
    "asm-mesh:25:coarse"
    "alm:7:fine"
    "alm:13:fine"
    "asm:7:fine"
    "asm:13:fine"
    "asm-mesh:7:fine"
    "asm-mesh:13:fine"
)

combo="${combos[${SLURM_ARRAY_TASK_ID:?array task id missing}]}"
IFS=':' read -r model speed mesh <<< "$combo"

echo "Array task ${SLURM_ARRAY_TASK_ID}: $combo (aug on, root off) on $(hostname)"

"${pkg_dir}/scripts/runPhaseVI.sh" -m "$model" -u "$speed" -mesh "$mesh" \
    -s H --rotational-augmentation on --root-effects off --restart --run

echo "Array task ${SLURM_ARRAY_TASK_ID} finished"
