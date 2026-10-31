#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# The 10 AeroDyn-driver cases of the Phase VI code-to-code arbiter: BEM and OLAF at
# Sequence S 5, 6, 7, 8 m/s and Sequence H 7 m/s. Prints the sbatch commands by default;
# --submit runs them. BEM cases (seconds) go to the 20 min development queue; OLAF cases
# alternate sequana_cpu / sequana_cpu_bigmem so both partition job limits are used.
#   sh openfast/submit_matrix.sh            # dry run
#   sh openfast/submit_matrix.sh --submit   # from turbinesFoam/validation/phaseVI
cd "$(dirname "$0")/.." || exit 1

submit=0
case "${1:-}" in
    "") ;;
    --submit) submit=1 ;;
    *) echo "usage: $0 [--submit]" >&2; exit 2 ;;
esac

olaf_partition=sequana_cpu
for point in S:5 S:6 S:7 S:8 H:7; do
    sequence=${point%%:*}
    speed=${point#*:}
    for wake in bem olaf; do
        if [ "$wake" = bem ]; then
            options="-p sequana_cpu_dev -t 00:20:00"
        else
            options="-p $olaf_partition -t 03:00:00"
            if [ "$olaf_partition" = sequana_cpu ]; then olaf_partition=sequana_cpu_bigmem; else olaf_partition=sequana_cpu; fi
        fi
        command="SEQUENCE=$sequence SPEED=$speed WAKE=$wake sbatch $options -J aerodyn-$wake-$sequence$speed scripts/slurm/aerodyn.slurm"
        if [ "$submit" -eq 1 ]; then
            echo "$command"
            eval "$command"
        else
            echo "$command"
        fi
    done
done
