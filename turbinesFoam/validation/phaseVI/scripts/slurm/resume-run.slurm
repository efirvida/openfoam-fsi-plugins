#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Continue an interrupted pimpleFoam run from its latest written time.
# runPhaseVI.sh has no resume (--restart refuses written state because --run re-decomposes with
# decomposePar -force and truncates the CSVs), so this script bypasses the runner: it does NOT
# decompose, re-render or touch the case; it only sets startFrom latestTime and re-launches the solver.
#     RUN_DIR  run directory (absolute, or relative to the submit directory), required
# Put the original partition/time on the command line, e.g.
#     sbatch --partition=sequana_cpu_bigmem --time=12:00:00 --export=ALL,RUN_DIR=runs/alm-U5-coarse-seqS-v12 \
#            --output=runs/resume-v12-alm-S-U5.out --error=runs/resume-v12-alm-S-U5.err scripts/slurm/resume-run.slurm
# The solver log is appended to log.pimpleFoam; the CSV functionObjects write the new segment to
# postProcessing/<object>/<resume time>/ (the original postProcessing/<object>/0/ stays intact).
# Optional LIB_DIR prepends the run-local library directory the run started with (e.g. runs/lib-flags
# for an A/B arm): resume with the same library, never the installed one.
# Do not rebuild libturbinesFoam while a run is queued or running.
#SBATCH --job-name=phaseVI-resume
#SBATCH --partition=sequana_cpu
#SBATCH --time=12:00:00
#SBATCH --ntasks=84
set -eu
cd "${SLURM_SUBMIT_DIR:?submit with sbatch}"
: "${RUN_DIR:?set RUN_DIR}"
test -f "$RUN_DIR/system/controlDict" || { echo "ERROR: $RUN_DIR is not a case directory" >&2; exit 2; }
test -d "$RUN_DIR/processor0" || { echo "ERROR: $RUN_DIR has no processor0 (nothing to resume)" >&2; exit 2; }
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
    LIB_DIR=$(cd "$LIB_DIR" && pwd)
    export LD_LIBRARY_PATH=$LIB_DIR:$LD_LIBRARY_PATH
    echo "Using run-local library $LIB_DIR"
fi
cd "$RUN_DIR"
decomposed=$(find . -maxdepth 1 -type d -name 'processor[0-9]*' | wc -l)
if [ "$decomposed" -ne "$SLURM_NTASKS" ]; then
    echo "ERROR: $decomposed processor directories but SLURM_NTASKS=$SLURM_NTASKS" >&2
    exit 2
fi
# Latest numeric time directory of processor0 (fractional times included).
latest=$(ls processor0 | awk '$1 + 0 > 0 {print $1 + 0, $1}' | sort -g | tail -n 1 | cut -d' ' -f2)
test -n "$latest" || { echo "ERROR: processor0 holds no written time" >&2; exit 2; }
cp -n system/controlDict system/controlDict.beforeResume
foamDictionary -entry startFrom -set latestTime system/controlDict >/dev/null
echo "Resuming $RUN_DIR from $latest on $SLURM_NTASKS ranks ($(hostname), $(date -u +%FT%TZ))"
printf '\n===== RESUME from %s at %s (job %s) =====\n' "$latest" "$(date -u +%FT%TZ)" "${SLURM_JOB_ID:-?}" >> log.pimpleFoam
echo "$latest $(date -u +%FT%TZ) ${SLURM_JOB_ID:-?}" >> resume.log
mpi_mca="${TURBINE_MPI_MCA---mca pml ucx --mca btl ^openib}"
# shellcheck disable=SC2086
mpirun $mpi_mca -np "$SLURM_NTASKS" pimpleFoam -parallel >> log.pimpleFoam 2>&1 \
    || { tail -40 log.pimpleFoam >&2; echo "ERROR: pimpleFoam failed; inspect $RUN_DIR/log.pimpleFoam" >&2; exit 3; }
echo "Solver finished; log: $RUN_DIR/log.pimpleFoam"
