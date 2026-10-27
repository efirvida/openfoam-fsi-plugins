#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# One OpenFAST AeroDyn-driver case of the NREL Phase VI code-to-code arbiter (T9/T10 of
# odd/tasks/v13-adoption-asm.md): build the case, run aerodyn_driver, compare with the
# experiment. Serial (the v5.0.0 build has no OpenMP); requests tasks only, no node or memory options.
#
# BEM runs take seconds; the default partition is the 20 min development queue. An OLAF
# production case needs the standard queue and a wall time (~1 h at 7 m/s, 1.5 h at 5 m/s):
#   cd turbinesFoam/validation/phaseVI
#   SEQUENCE=S SPEED=7 WAKE=bem sbatch scripts/slurm/aerodyn.slurm
#   SEQUENCE=S SPEED=7 WAKE=olaf sbatch -p sequana_cpu -t 03:00:00 scripts/slurm/aerodyn.slurm
# Environment: SEQUENCE (S|H), SPEED (m/s), WAKE (bem|olaf), CASE_DIR (default
# runs/aerodyn-<wake>-<sequence>U<speed>; must not exist), OPENFAST_ENV (conda env prefix),
# TURBINE_PKG_DIR (package dir; defaults to $SLURM_SUBMIT_DIR).
#SBATCH --job-name=phaseVI-aerodyn
#SBATCH --partition=sequana_cpu_dev
#SBATCH --time=00:20:00
#SBATCH --ntasks=1
#SBATCH --output=runs/%x-%j.out
#SBATCH --error=runs/%x-%j.err

set -eu

: "${SEQUENCE:?set SEQUENCE=S|H}"
: "${SPEED:?set SPEED=<m/s>}"
: "${WAKE:?set WAKE=bem|olaf}"
OPENFAST_ENV="${OPENFAST_ENV:-/scratch/leahk/eduardo.donestevez/conda-envs/openfast}"
pkg_dir="${TURBINE_PKG_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}"
case_dir="${CASE_DIR:-$pkg_dir/runs/aerodyn-${WAKE}-${SEQUENCE}U${SPEED}}"

cd "$pkg_dir"
export OMP_NUM_THREADS=1

python3 scripts/buildAeroDynCase.py --sequence "$SEQUENCE" --speed "$SPEED" --wake "$WAKE" --out "$case_dir"

cd "$case_dir"
# The driver redraws a progress line with carriage returns; keep the log readable.
"$OPENFAST_ENV/bin/aerodyn_driver" ad_driver.dvr 2>&1 | tr '\r' '\n' | grep -v '^ *Time: ' > aerodyn_driver.log
grep -q 'terminated normally' aerodyn_driver.log

cd "$pkg_dir"
python3 scripts/compareAeroDyn.py --case "$case_dir" | tee "$case_dir/compare.txt"
