#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# External FLOWUnsteady Phase VI reference, shared-memory Julia (not MPI).
# Submit from repository root; database and output must live under flowunsteady/runs:
# sbatch --output=turbinesFoam/validation/phaseVI/flowunsteady/runs/%j.out \
#   --error=turbinesFoam/validation/phaseVI/flowunsteady/runs/%j.err \
#   turbinesFoam/validation/phaseVI/scripts/slurm/flowunsteady.slurm \
#   turbinesFoam/validation/phaseVI/flowunsteady/runs/db-total ds=on 2 smoke-total-ds
# Arguments: database directory, ds=on|off, revolutions, unique tag.
# The 18-minute dev allocation is for smoke tests only, NOT a production estimate.
#SBATCH --job-name=phaseVI-flowunsteady
#SBATCH --partition=sequana_cpu_dev
#SBATCH --time=00:18:00
#SBATCH --ntasks=48
set -eu
cd "${SLURM_SUBMIT_DIR:?submit from the repository root}"
[ "$#" -eq 4 ] || { echo 'Expected DB_DIR ds=on|off NREVS TAG' >&2; exit 2; }
[ "${SLURM_JOB_NUM_NODES:?}" -eq 1 ] || {
    echo 'Julia requires one shared-memory node; refusing a multi-node allocation' >&2
    exit 2
}
echo "Job $SLURM_JOB_ID: ntasks=$SLURM_NTASKS NodeList=$SLURM_JOB_NODELIST host=$(hostname)"
export LD_LIBRARY_PATH=/scratch/app/julia/1.11.3/lib
export JULIA_DEPOT_PATH=/scratch/leahk/eduardo.donestevez/julia-depot:
export MPLBACKEND=Agg
export OPENBLAS_NUM_THREADS=1
exec /scratch/app/julia/1.11.3/bin/julia \
    --project=/scratch/leahk/eduardo.donestevez/flowunsteady-env \
    -t "$SLURM_NTASKS" turbinesFoam/validation/phaseVI/flowunsteady/phaseVI.jl "$@"
