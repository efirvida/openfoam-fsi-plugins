#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# IEA 15 MW — convergence plan, STEP 1: the long L2 run.
#
# The 4-revolution screen closed the MESH axis at L2: its steps were -2.59 %,
# -0.95 % and -0.29 % (7.50 -> 4.98 -> 3.75 -> 1.87 m), the fit cp(h) = cpinf +
# C*h**p gave p = 2.82 with cpinf = 0.5770 and left a mesh residual of +0.14 % at
# L2, so L3 would buy about 0.1 % for roughly 50 h. What the screen did NOT
# establish is the TEMPORAL axis: delta_t() derives the step from the cell, so its
# four points refined space and time together, and at 4 revolutions the
# per-revolution drift is -3.0 % on every mesh.
#
# This run therefore extends the SAME L2 case the screen produced
# (runs/iea15mw-screen-m3-l2, 4 revolutions already written, 96 ranks, the
# measured simple 4 6 4 decomposition) to a horizon where the drift falls below
# the campaign criterion (<0.2 %/rev sustained). Resuming keeps one continuous
# history -- so the drift curve is read from a single file, the screening
# revolutions are not thrown away, and the decomposition is reused.
#
#   cd turbinesFoam/validation/iea15mw
#   sbatch scripts/slurm/l2-long.slurm
#
# STAGED on purpose: 20 revolutions first (~6 h at the measured 3.4 rev/h), then
# read the drift curve and extend only if it has not fallen below the criterion.
# Extending is the same command with a higher total:
#
#   TURBINE_TOTAL_REVS=40 sbatch scripts/slurm/l2-long.slurm
#
# The configuration is FROZEN and written down, because mesh convergence is a
# property of this configuration: polars with liftReCorrExp 0, sampling
# velocitySampleRadius 3.3 / nVelocitySamples 16, endEffects Glauert with
# tipEffects + rootEffects on, domain 3D/7D/+-3D. Changing any of it invalidates
# both axes and the validation.
#SBATCH -p sequana_cpu
#SBATCH --ntasks=96
#SBATCH --time=10:00:00
#SBATCH --no-requeue
#SBATCH -J iea15mw-l2-long
#SBATCH -e %j.err
#SBATCH -o %j.out

set -u
cd "${SLURM_SUBMIT_DIR:-$PWD}"

export TURBINE_MODEL=alm TURBINE_RANKS=96 TURBINE_REQUEUE=0 TURBINE_RPM=7.518
export TURBINE_VELOCITY_SAMPLE_RADIUS=3.3 TURBINE_N_VELOCITY_SAMPLES=16
export TURBINE_END_EFFECTS=on
export TURBINE_UPSTREAM=3 TURBINE_DOWNSTREAM=7 TURBINE_LATERAL=3
export TURBINE_WRITE_DEG=60
export TURBINE_DECOMP_METHOD=simple TURBINE_DECOMP_N="4 6 4"

export TURBINE_MESH=coarse TURBINE_SNAPPY=on TURBINE_SNAPPY_LEVEL=2
export TURBINE_RUN_DIR=runs/iea15mw-screen-m3-l2
export TURBINE_TOTAL_REVS="${TURBINE_TOTAL_REVS:-20}"

echo "=== L2 largo: hasta ${TURBINE_TOTAL_REVS} revs, retomando ${TURBINE_RUN_DIR} ($(date '+%H:%M:%S')) ==="
bash scripts/run_iea15mw_case.sh
echo "=== L2 largo terminado con rc=$? ($(date '+%H:%M:%S')) ==="
