#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# IEA 15 MW -- v1.4 ASM and ASM+mesh on the Dag & Sorensen tip arm (T6 of
# odd/tasks/v13-adoption-asm.md). Submitted by `submit_v14_asm_ds.sh`, which sets
# TURBINE_MODEL, TURBINE_RUN_DIR and the job name.
#
# The pair of `iea15mw-l2-ds` (ALM, Glauert root kept, Glauert tip off, D&S on,
# cp 0.5666) on the same frozen L2 platform; only the element type changes. Fresh
# start from 0.org, like `iea15mw-asm-l2`, for 23 revolutions so that the averaging
# window (revs 22-23) is the one of the ALM ds run. No requeue: the run must fit one
# allocation, because a resume restores the azimuth counter without rotating the
# blades (record "IEA regression replay"), a blade/wake mismatch unless
# angle0 mod 120 deg is 0. Output every 120 deg so any state that is ever resumed
# satisfies that.
#SBATCH --ntasks=96
#SBATCH --no-requeue
#SBATCH -e %j.err
#SBATCH -o %j.out

set -u
cd "${SLURM_SUBMIT_DIR:-$PWD}"

: "${TURBINE_MODEL:?asm or asm-mesh}"
case "$TURBINE_MODEL" in asm | asm-mesh) ;; *) echo "ERROR: TURBINE_MODEL must be asm or asm-mesh" >&2; exit 2 ;; esac
: "${TURBINE_RUN_DIR:?run directory}"
if [ -e "$TURBINE_RUN_DIR" ]; then
    echo "ERROR: $TURBINE_RUN_DIR exists; a surface run starts from scratch" >&2
    exit 2
fi

# The frozen platform of l2-long.slurm / l2-ds-gate.slurm, restated.
export TURBINE_RANKS=96 TURBINE_REQUEUE=0 TURBINE_RPM=7.518
export TURBINE_VELOCITY_SAMPLE_RADIUS=3.3 TURBINE_N_VELOCITY_SAMPLES=16
export TURBINE_UPSTREAM=3 TURBINE_DOWNSTREAM=7 TURBINE_LATERAL=3
export TURBINE_DECOMP_METHOD=simple TURBINE_DECOMP_N="4 6 4"
export TURBINE_MESH=coarse TURBINE_SNAPPY=on TURBINE_SNAPPY_LEVEL=2
export TURBINE_DT_FACTOR=1.0 TURBINE_N_CHORDWISE=5
# The D&S arm: Glauert tip off, root kept as the Prandtl hub loss, correction on.
export TURBINE_END_EFFECTS=on TURBINE_ROOT_EFFECTS=on TURBINE_TIP_EFFECTS=off TURBINE_TIP_CORRECTION=on
export TURBINE_WRITE_DEG=120
export TURBINE_TOTAL_REVS="${TURBINE_TOTAL_REVS:-23}"

echo "=== L2 ${TURBINE_MODEL} D&S: ${TURBINE_TOTAL_REVS} revs from scratch in ${TURBINE_RUN_DIR} ($(date '+%H:%M:%S')) ==="
bash scripts/run_iea15mw_case.sh
echo "=== terminado con rc=$? ($(date '+%H:%M:%S')) ==="
