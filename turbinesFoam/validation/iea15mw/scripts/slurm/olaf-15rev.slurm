#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# OpenFAST + OLAF 15-rev rated-point reference for the IEA 15 MW tip comparison.
#
# The first attempt (job 11605326) hit the 4 h wall at t = 98 s of the 120 s
# run, i.e. 12.3 of the 15 revolutions. The case sets ChkptTime 99999 and wrote
# no .chkp, so there is no restart: the run has to be redone from zero. TMax
# 120 s needs ~5 h at that rate, so allow 12 h for margin.
#
#   cd turbinesFoam/validation/iea15mw
#   sbatch scripts/slurm/olaf-15rev.slurm
#
# Single core: OLAF's free vortex wake is not MPI-parallel in this setup.
#SBATCH -p sequana_cpu
#SBATCH --ntasks=1
#SBATCH -J olaf-15rev
#SBATCH --time=12:00:00
#SBATCH -e %j.err
#SBATCH -o %j.out

set -eu

# $0 points at Slurm's spool copy, so resolve from the submission dir.
cd "${SLURM_SUBMIT_DIR:-$PWD}/reference/olaf-15rev"

openfast="${OPENFAST_BIN:-/scratch/leahk/eduardo.donestevez/conda-envs/openfast/bin/openfast}"
if [ ! -x "$openfast" ]; then
    echo "ERROR: OpenFAST binary not found/executable: $openfast" >&2
    exit 3
fi

export OMP_NUM_THREADS=1

"$openfast" IEA-15-240-RWT-OLAF_rated.fst > run_olaf.log 2>&1
