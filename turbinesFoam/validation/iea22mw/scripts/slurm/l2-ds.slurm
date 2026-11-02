#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# IEA 22-280-RWT -- ALM on the Dag & Sorensen tip arm, L2 platform: the counterpart of
# the IEA-15 reference `iea15mw-l2-ds` (iea15mw/scripts/slurm/l2-long.slurm,
# l2-ds-gate.slurm, l2-ds-surface.slurm). Submitted by `submit_iea22.sh`
# (sequana_cpu_bigmem, --ntasks only, node exclusion).
#
# The IEA-15 platform is not retyped: every platform quantity (ranks, decomposition,
# domain, snappy level, sample radius, write interval) comes from
# `scripts/platform_derive.py`, which reads the IEA-15 files and carries each value by a
# rule that depends only on the geometry (see the table that script prints). The rotor
# speed, pitch and the castellated extents are the IEA-22 generator defaults.
#
# Model: Glauert tip loss off, root kept as the Prandtl hub loss, Dag & Sorensen tip
# correction on, output every 120 deg, fresh start from 0.org, 23 revolutions, no requeue
# (a resume restores the azimuth counter without rotating the blades).
#
#   cd turbinesFoam/validation/iea22mw
#   TURBINE_RUN_DIR=runs/iea22mw-l2-ds sbatch scripts/slurm/l2-ds.slurm
#
# Smoke (development partition, 20 min): TURBINE_TOTAL_REVS=0.1 and a scratch run dir.
#SBATCH -p sequana_cpu_bigmem
#SBATCH --ntasks=96
#SBATCH --time=36:00:00
#SBATCH --no-requeue
#SBATCH -J iea22mw-l2-ds
#SBATCH -e %j.err
#SBATCH -o %j.out

set -u
cd "${SLURM_SUBMIT_DIR:-$PWD}"

PYTHON=${PYTHON:-/scratch/leahk/eduardo.donestevez/venv/bin/python}
export PYTHON
: "${TURBINE_RUN_DIR:?run directory, e.g. runs/iea22mw-l2-ds}"
if [ -e "$TURBINE_RUN_DIR" ]; then
    echo "ERROR: $TURBINE_RUN_DIR exists; this run starts from scratch" >&2
    exit 2
fi

eval "$("$PYTHON" -I scripts/platform_derive.py --env)" || exit 2
# SLURM_NTASKS is what mpirun gets: it must be the derived rank count.
if [ -n "${SLURM_NTASKS:-}" ] && [ "$SLURM_NTASKS" != "$TURBINE_RANKS" ]; then
    echo "ERROR: --ntasks $SLURM_NTASKS != derived ranks $TURBINE_RANKS" >&2
    exit 2
fi
export TURBINE_MODEL=alm
# The D&S arm: Glauert tip off, root kept as the Prandtl hub loss, correction on.
export TURBINE_END_EFFECTS=on TURBINE_ROOT_EFFECTS=on TURBINE_TIP_EFFECTS=off TURBINE_TIP_CORRECTION=on
export TURBINE_DT_FACTOR=1.0
export TURBINE_TOTAL_REVS="${TURBINE_TOTAL_REVS:-23}"

echo "=== IEA-22 L2 ALM D&S: ${TURBINE_TOTAL_REVS} revs from scratch in ${TURBINE_RUN_DIR}, ${TURBINE_RANKS} ranks ($(date '+%H:%M:%S')) ==="
bash scripts/run_iea22mw_case.sh
rc=$?
echo "=== terminado con rc=${rc} ($(date '+%H:%M:%S')) ==="
exit "$rc"
