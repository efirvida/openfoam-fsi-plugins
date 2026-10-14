#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# IEA 15 MW -- nacelle on/off study (odd/tasks/nacelle-onoff-study.md, N2/A3).
#
# Neither the OLAF/AeroDyn reference (NacelleDrag=False) nor our runs carry a
# nacelle, so this pair is a purely numerical sensitivity: does a nacelle move
# the inboard loading the way the Phase VI root error would need?
#
# Design: both arms resume the SAME converged state, the Model Definition D&S
# arm at rev 23 (runs/iea15mw-l2-ds, t = 183.5592 s), and run 3 more
# revolutions on the same library; only TURBINE_NACELLE differs. The source run
# is never touched: each arm is a copy holding the mesh, the case dictionaries
# and processor*/183.5592.
#
#   cd turbinesFoam/validation/iea15mw
#   S=runs/iea15mw-l2-ds
#   for D in runs/iea15mw-l2-ds-nac-on runs/iea15mw-l2-ds-nac-off; do
#     mkdir -p $D && cp -r $S/constant $S/system $S/0.org $D/
#     for p in $S/processor*; do n=$(basename $p); mkdir -p $D/$n; \
#       cp -r $p/constant $p/183.5592 $D/$n/; done
#   done
#   TURBINE_NACELLE=on  TURBINE_RUN_DIR=runs/iea15mw-l2-ds-nac-on  sbatch -J iea-nac-on  scripts/slurm/nacelle-onoff.slurm
#   TURBINE_NACELLE=off TURBINE_RUN_DIR=runs/iea15mw-l2-ds-nac-off sbatch -J iea-nac-off scripts/slurm/nacelle-onoff.slurm
#
# 3 revolutions at the measured 3.4 rev/h of the 96-rank L2 is about 53 minutes.
#SBATCH -p sequana_cpu
#SBATCH --ntasks=96
#SBATCH --time=02:30:00
#SBATCH --no-requeue
#SBATCH -e %j.err
#SBATCH -o %j.out
set -u
cd "${SLURM_SUBMIT_DIR:-$PWD}"
: "${TURBINE_RUN_DIR:?set TURBINE_RUN_DIR (a copy of runs/iea15mw-l2-ds at rev 23)}"
: "${TURBINE_NACELLE:?set TURBINE_NACELLE to on or off}"
# The frozen platform of l2-ds-gate.slurm, restated: changing any of it
# invalidates the comparison with the state both arms resume from.
export TURBINE_MODEL=alm TURBINE_RANKS=96 TURBINE_REQUEUE=0 TURBINE_RPM=7.518
export TURBINE_VELOCITY_SAMPLE_RADIUS=3.3 TURBINE_N_VELOCITY_SAMPLES=16
export TURBINE_UPSTREAM=3 TURBINE_DOWNSTREAM=7 TURBINE_LATERAL=3
export TURBINE_WRITE_DEG=60
export TURBINE_DECOMP_METHOD=simple TURBINE_DECOMP_N="4 6 4"
export TURBINE_MESH=coarse TURBINE_SNAPPY=on TURBINE_SNAPPY_LEVEL=2
export TURBINE_DT_FACTOR=1.0
export TURBINE_END_EFFECTS=on TURBINE_ROOT_EFFECTS=on
export TURBINE_TIP_EFFECTS=off TURBINE_TIP_CORRECTION=on
export TURBINE_TOTAL_REVS="${TURBINE_TOTAL_REVS:-26}"
echo "=== nacelle ${TURBINE_NACELLE}: to ${TURBINE_TOTAL_REVS} revs, resuming ${TURBINE_RUN_DIR} ($(date '+%H:%M:%S')) ==="
bash scripts/run_iea15mw_case.sh
echo "=== finished rc=$? ($(date '+%H:%M:%S')) ==="
