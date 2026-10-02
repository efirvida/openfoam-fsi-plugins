#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Run the Lindenburg bounded rotational-augmentation model under the D&S tip
# correction, 7 m/s (default) coarse D/32 Sequence H.
#
# Why a dedicated script: runPhaseVI.sh selects rotationalAugmentation by
# `active on|off` only -- the MODEL comes from config/case.yaml and is rendered
# into each fvOptions twin. Rather than edit runPhaseVI.sh (arm jobs are running
# and read it live), this script renders the case, patches the rendered
# system/fvOptions model DuSelig -> model Lindenburg, then runs it.
#
#   cd turbinesFoam/validation/phaseVI
#   TURBINE_LONG_QUEUE_AUTHORIZED=1 sbatch scripts/slurm/tip-correction-lindenburg.slurm [speed]
#SBATCH -p sequana_cpu
#SBATCH --ntasks=48
#SBATCH -J phaseVI-linden
#SBATCH --time=96:00:00
#SBATCH -e %j.err
#SBATCH -o %j.out

set -eu

speed="${1:-7}"
label="tipcorr-lindenburg"

if [ "${TURBINE_LONG_QUEUE_AUTHORIZED:-0}" != "1" ]; then
    echo "ERROR: long-queue authorization not granted." >&2
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

pkg_dir="${TURBINE_PKG_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}"
if [ ! -x "${pkg_dir}/scripts/runPhaseVI.sh" ]; then
    echo "ERROR: submit from the package directory (or set TURBINE_PKG_DIR)." >&2
    exit 3
fi
cd "$pkg_dir"

run_dir="runs/alm-U${speed}-coarse-${label}"

# 1. Render only (no --run / --submit).
scripts/runPhaseVI.sh -m alm -u "$speed" -mesh coarse -s H \
    --rotational-augmentation on --root-effects on \
    --tip-effects off --tip-correction on \
    --run-label "$label"

# 2. Switch the model inside the rendered rotationalAugmentation block.
python3 - "$run_dir/system/fvOptions" <<'PY'
import re, sys
p = sys.argv[1]
s = open(p).read()
m = re.search(r"(rotationalAugmentation\s*\{)(.*?)(\n\s*\})", s, re.S)
if not m:
    raise SystemExit("no rotationalAugmentation block in " + p)
body = m.group(2)
if "model" not in body:
    raise SystemExit("no model key in the block")
new = body.replace("DuSelig", "Lindenburg")
if new == body:
    raise SystemExit("model DuSelig not found to patch")
s = s[:m.start(2)] + new + s[m.end(2):]
open(p, "w").write(s)
print("patched model -> Lindenburg in", p)
PY
grep -A4 rotationalAugmentation "$run_dir/system/fvOptions" | head -6

# 3. Run in place (same decompose/mpirun path as runPhaseVI.sh --run).
cd "$run_dir"
rm -rf processor*
if ! decomposePar -force > log.decomposePar 2>&1; then
    tail -30 log.decomposePar >&2; echo "ERROR: decomposePar failed" >&2; exit 3
fi
mpi_mca="${TURBINE_MPI_MCA---mca pml ucx --mca btl ^openib}"
# shellcheck disable=SC2086
if ! mpirun $mpi_mca -np 48 pimpleFoam -parallel > log.pimpleFoam 2>&1; then
    tail -40 log.pimpleFoam >&2
    echo "ERROR: pimpleFoam failed" >&2
    exit 3
fi
cd "$pkg_dir"
rm -rf "$run_dir/processor"*
echo "Lindenburg U${speed} finished"
