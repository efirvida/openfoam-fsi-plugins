#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# v1.4 IEA 15 MW ASM and ASM+mesh on the Dag & Sorensen tip arm (odd/tasks/v13-adoption-asm.md T6).
# Run from turbinesFoam/validation/iea15mw. Usage: submit_v14_asm_ds.sh [--apply]   (default: dry run)
# Runs are created under ./runs of the submit directory. `--ntasks` only (in the slurm), balanced partitions.
set -eu
cd "$(dirname "$0")/.." || exit
apply=${1:-}
EXCLUDE=sdumont6006,sdumont6009,sdumont6029
TIME=36:00:00
# partition model label
while read -r part model label; do
    [ -n "$part" ] || continue
    dir=runs/$label
    [ -e "$dir" ] && { echo "EXISTS $dir: skipped" >&2; continue; }
    cmd="sbatch --partition=$part --time=$TIME --exclude=$EXCLUDE --job-name=$label \
--export=ALL,TURBINE_MODEL=$model,TURBINE_RUN_DIR=$dir scripts/slurm/l2-ds-surface.slurm"
    if [ "$apply" = --apply ]; then echo "$(eval "$cmd") $label $part"; else echo "$cmd"; fi
done <<EOF
sequana_cpu asm iea15mw-asm-l2-ds
sequana_cpu_bigmem asm-mesh iea15mw-asm-mesh-l2-ds
EOF
