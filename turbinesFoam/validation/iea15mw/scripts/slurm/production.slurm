#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# IEA 15-240-RWT production run for a given mesh/domain.
#
# The finer meshes (medium D/48, fine D/64) do not fit the 20-minute
# development queue, so they run whole on the production queue (96 h). The
# mesh and domain extents come from the environment and are forwarded to
# tools/generate_case.py by scripts/run_iea15mw_case.sh:
#
#   PHASEVI_MESH        coarse | medium | fine        (default coarse)
#   PHASEVI_UPSTREAM    upstream extent [D]           (default 5)
#   PHASEVI_DOWNSTREAM  downstream extent [D]         (default 15)
#   PHASEVI_LATERAL     lateral half-extent [D]       (default 4)
#   PHASEVI_FINE_MAX    refined region downstream [D] (default 8)
#   PHASEVI_FINE_LAT    refined region lateral [D]    (default 1.5)
#   PHASEVI_DOMAIN_TOP  domain top [m] above the rotor (default 2.5D)
#   PHASEVI_RUN_DIR     run dir (default runs/iea15mw-rated-<mesh>)
#
# Example: a compact medium mesh, 10D x 6D around the rotor (P5 mesh sweep):
#
#   cd turbinesFoam/validation/iea15mw
#   PHASEVI_MESH=medium PHASEVI_UPSTREAM=2.5 PHASEVI_DOWNSTREAM=7.5 \
#   PHASEVI_LATERAL=3.0 PHASEVI_LONG_QUEUE_AUTHORIZED=1 \
#   sbatch scripts/slurm/production.slurm
#
# Cores only: no --nodes and no --mem.
#SBATCH -p sequana_cpu
#SBATCH --ntasks=48
#SBATCH -J iea15mw-prod
#SBATCH --time=96:00:00
#SBATCH -e %j.err
#SBATCH -o %j.out

set -eu

if [ "${PHASEVI_LONG_QUEUE_AUTHORIZED:-0}" != "1" ]; then
    echo "ERROR: long-queue authorization not granted." >&2
    exit 5
fi

pkg_dir="${PHASEVI_PKG_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}"
if [ ! -f "${pkg_dir}/scripts/run_iea15mw_case.sh" ]; then
    echo "ERROR: submit from turbinesFoam/validation/iea15mw (or set PHASEVI_PKG_DIR)." >&2
    exit 3
fi

export PHASEVI_PKG_DIR="$pkg_dir"
# 96 h fits the whole run in one allocation (no slicing/requeue needed).
export PHASEVI_REQUEUE=0
exec bash "${pkg_dir}/scripts/run_iea15mw_case.sh"
