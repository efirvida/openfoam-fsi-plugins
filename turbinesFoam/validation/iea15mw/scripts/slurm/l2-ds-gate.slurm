#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# IEA 15 MW -- Phase 0 gate P0.4: the Dag & Sorensen tip correction on the
# frozen L2 platform, short horizon.
#
# The Model Definition freezes the tip correction as Dag & Sorensen with the
# Glauert tip loss off. The correction is resolution dependent and diverged once
# at the hub transition on Phase VI; the IEA blade has 147 elements, so it is
# exercised here before it is frozen.
#
# Design: resume the CONVERGED frozen state (rev 20, t = 159.6232 s of the
# Glauert run) with the correction switched on, so that what is observed is the
# model, not the spin-up. The run directory is a copy that holds only the mesh,
# the case dictionaries and processor*/159.6232 (see the preparation line below);
# the source run is never touched.
#
#   cd turbinesFoam/validation/iea15mw
#   S=runs/iea15mw-screen-m3-l2; D=runs/iea15mw-l2-ds
#   mkdir -p $D && cp -r $S/constant $S/system $S/0.org $D/
#   for p in $S/processor*; do n=$(basename $p); mkdir -p $D/$n; \
#     cp -r $p/constant $p/159.6232 $D/$n/; done
#   sbatch scripts/slurm/l2-ds-gate.slurm
#
# 0.5 revolution at the measured 3.4 rev/h of the 96-rank L2 is about 9 minutes,
# which fits the 20-minute development partition with the start-up.
#SBATCH -p sequana_cpu_dev
#SBATCH --ntasks=96
#SBATCH --time=00:20:00
#SBATCH --no-requeue
#SBATCH -J iea15mw-l2-ds
#SBATCH -e %j.err
#SBATCH -o %j.out

set -u
cd "${SLURM_SUBMIT_DIR:-$PWD}"

# The frozen platform of l2-long.slurm, restated: changing any of it invalidates
# the comparison with the Glauert run this one resumes from.
export TURBINE_MODEL=alm TURBINE_RANKS=96 TURBINE_REQUEUE=0 TURBINE_RPM=7.518
export TURBINE_VELOCITY_SAMPLE_RADIUS=3.3 TURBINE_N_VELOCITY_SAMPLES=16
export TURBINE_UPSTREAM=3 TURBINE_DOWNSTREAM=7 TURBINE_LATERAL=3
export TURBINE_WRITE_DEG=60
export TURBINE_DECOMP_METHOD=simple TURBINE_DECOMP_N="4 6 4"
export TURBINE_MESH=coarse TURBINE_SNAPPY=on TURBINE_SNAPPY_LEVEL=2
export TURBINE_DT_FACTOR=1.0

# The arm under test: Dag & Sorensen on, Glauert tip loss off, root kept as the
# Prandtl hub loss. The CONTROL arm (same restart, same library, Glauert tip and
# root on, no correction) separates the tip model from the root-factor change of
# 4c49dc3, which postdates the frozen run:
#
#   TURBINE_RUN_DIR=runs/iea15mw-l2-ctrl TURBINE_TIP_EFFECTS=on \
#     TURBINE_TIP_CORRECTION=off sbatch -J iea15mw-l2-ctrl scripts/slurm/l2-ds-gate.slurm
export TURBINE_END_EFFECTS=on TURBINE_ROOT_EFFECTS=on
export TURBINE_TIP_EFFECTS="${TURBINE_TIP_EFFECTS:-off}"
export TURBINE_TIP_CORRECTION="${TURBINE_TIP_CORRECTION:-on}"

export TURBINE_RUN_DIR="${TURBINE_RUN_DIR:-runs/iea15mw-l2-ds}"
export TURBINE_TOTAL_REVS="${TURBINE_TOTAL_REVS:-20.5}"

echo "=== L2 gate (tip effects ${TURBINE_TIP_EFFECTS}, correction ${TURBINE_TIP_CORRECTION}): hasta ${TURBINE_TOTAL_REVS} revs, retomando ${TURBINE_RUN_DIR} ($(date '+%H:%M:%S')) ==="
bash scripts/run_iea15mw_case.sh
echo "=== terminado con rc=$? ($(date '+%H:%M:%S')) ==="
