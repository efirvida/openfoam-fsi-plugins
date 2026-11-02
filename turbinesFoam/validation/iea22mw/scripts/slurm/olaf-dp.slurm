#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# IEA 22-280-RWT -- OpenFAST + OLAF (double precision) production reference at the rated
# point: the guideline setup `openfast_iea22.py setup --wake olaf` builds (1399 near-wake
# panels, 699 free, 23.3 wake revolutions + 4 revolutions averaged, dt 0.1459 s = 1640 steps,
# no shaft tilt, tower on). Submitted by `submit_iea22.sh` (sequana_cpu, --ntasks only).
#
# One task: the OpenFAST build is serial (no OpenMP, OLAF uses the particle tree) so extra
# cores would idle. Time: sized from the measured trace, see the README "Slurm sizing".
#
#   cd turbinesFoam/validation/iea22mw
#   OLAF_RUN_DIR=runs/iea22mw-olaf-dp sbatch scripts/slurm/olaf-dp.slurm
#
# Smoke/sizing: OLAF_TMAX_STEPS=N stops after N steps (not a result, never imported).
#SBATCH -p sequana_cpu
#SBATCH --ntasks=1
#SBATCH --time=12:00:00
#SBATCH --no-requeue
#SBATCH -J iea22mw-olaf-dp
#SBATCH -e %j.err
#SBATCH -o %j.out

set -eu
cd "${SLURM_SUBMIT_DIR:-$PWD}"

PYTHON=${PYTHON:-/scratch/leahk/eduardo.donestevez/venv/bin/python}
: "${OLAF_RUN_DIR:?run directory, e.g. runs/iea22mw-olaf-dp}"
if [ -e "$OLAF_RUN_DIR" ]; then
    echo "ERROR: $OLAF_RUN_DIR exists; the reference starts from scratch" >&2
    exit 2
fi
export OPENFAST_BIN="${OPENFAST_BIN:-/scratch/leahk/eduardo.donestevez/openfast-5.0.0-dp/bin/openfast}"
if [ ! -x "$OPENFAST_BIN" ]; then
    echo "ERROR: OpenFAST binary not found/executable: $OPENFAST_BIN" >&2
    exit 3
fi
export OMP_NUM_THREADS=1
# gfortran buffers stdout when redirected; unbuffered, run.log carries the "Time: t of tmax" progress.
export GFORTRAN_UNBUFFERED_PRECONNECTED=y

parent="$(dirname "$OLAF_RUN_DIR")"
name="$(basename "$OLAF_RUN_DIR")"
"$PYTHON" -I scripts/openfast_iea22.py setup "$parent" --wake olaf --name "$name"
if [ -n "${OLAF_TMAX_STEPS:-}" ]; then
    "$PYTHON" -I scripts/olaf_trace.py truncate "$OLAF_RUN_DIR" "$OLAF_TMAX_STEPS"
fi

echo "=== IEA-22 OLAF-DP in ${OLAF_RUN_DIR} ($(date '+%H:%M:%S')) ==="
rc=0
if [ -n "${OLAF_TMAX_STEPS:-}" ]; then
    # Sizing run: OpenFAST only (a truncated run has nothing to extract).
    (cd "$OLAF_RUN_DIR" && exec "$OPENFAST_BIN" ./*.fst > run.log 2>&1) &
else
    # `run` executes OpenFAST, then extracts metrics.json / spanwise.csv.
    "$PYTHON" -I scripts/openfast_iea22.py run "$OLAF_RUN_DIR" --openfast "$OPENFAST_BIN" &
fi
pid=$!
"$PYTHON" -I scripts/olaf_trace.py sample "$OLAF_RUN_DIR/run.log" "$OLAF_RUN_DIR/wall-trace.csv" "$pid" &
sampler=$!
wait "$pid" || rc=$?
kill "$sampler" 2>/dev/null || true
echo "=== terminado con rc=${rc} ($(date '+%H:%M:%S')) ==="
exit "$rc"
