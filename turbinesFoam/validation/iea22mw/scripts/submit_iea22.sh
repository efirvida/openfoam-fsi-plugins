#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# IEA 22-280-RWT production submission (odd/tasks/iea22-case-readiness.md T4).
# Usage: submit_iea22.sh [--apply] [alm|olaf|all]      (default: dry run, all)
#   alm   iea22mw-l2-ds     ALM D&S, L2 platform, sequana_cpu_bigmem, ranks from platform_derive.py
#   olaf  iea22mw-olaf-dp   OpenFAST OLAF double precision, guideline setup, sequana_cpu, 1 task
# Dry run prints the sbatch commands; --apply submits them. `--ntasks` only (no --nodes, no
# --mem), failed nodes excluded. A run directory that already exists is refused (both runs
# start from scratch). Run from anywhere; runs are created under iea22mw/runs.
set -eu
cd "$(dirname "$0")/.." || exit
apply=no
what=all
for arg in "$@"; do
    case "$arg" in
        --apply) apply=yes ;;
        alm | olaf | all) what=$arg ;;
        *) echo "usage: $0 [--apply] [alm|olaf|all]" >&2; exit 2 ;;
    esac
done
EXCLUDE=sdumont6006,sdumont6009,sdumont6029
# Wall times: ALM from the measured seconds/step of the dev smoke, OLAF from the wall trace
# of a sizing run (README, "Slurm sizing"); both with the margin stated there.
TIME_ALM=${TIME_ALM:-36:00:00}
TIME_OLAF=${TIME_OLAF:-12:00:00}
PYTHON=${PYTHON:-/scratch/leahk/eduardo.donestevez/venv/bin/python}
runs=${IEA22_RUNS_DIR:-runs}
ranks=$("$PYTHON" -I scripts/platform_derive.py --get ranks)

status=0
submit() { # label partition ntasks time script env-var
    label=$1 part=$2 ntasks=$3 wall=$4 script=$5 var=$6
    dir=$runs/$label
    if [ -e "$dir" ]; then
        echo "EXISTS $dir: refused" >&2
        status=1
        return
    fi
    cmd="sbatch --partition=$part --ntasks=$ntasks --time=$wall --exclude=$EXCLUDE --job-name=$label --export=ALL,$var=$dir $script"
    if [ "$apply" = yes ]; then
        echo "$(eval "$cmd") $label $part"
    else
        echo "$cmd"
    fi
}

case "$what" in alm | all) submit iea22mw-l2-ds sequana_cpu_bigmem "$ranks" "$TIME_ALM" scripts/slurm/l2-ds.slurm TURBINE_RUN_DIR ;; esac
case "$what" in olaf | all) submit iea22mw-olaf-dp sequana_cpu 1 "$TIME_OLAF" scripts/slurm/olaf-dp.slurm OLAF_RUN_DIR ;; esac
exit "$status"
