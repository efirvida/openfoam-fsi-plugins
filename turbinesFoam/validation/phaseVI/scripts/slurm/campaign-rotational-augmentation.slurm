#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Phase VI rotational-augmentation power-curve campaign, REDESIGNED as a
# two-arm matrix grouped into few array tasks so it fits the association
# submit limit. Each array task runs a documented list of runs sequentially,
# 48 ranks on one node, at most 96 h wall time (maintainer-authorized,
# mirroring production.slurm), restarting every run from its latest written
# time.
#
# Two physics arms (option b) so each model is evaluated at both root-effect
# settings with data:
#   arm A  `--rotational-augmentation on  --root-effects off`  (the candidate)
#   arm B  `--rotational-augmentation on  --root-effects on`   (root-on)
# plus the committed control for the ASM-mesh baseline gap:
#   control `--rotational-augmentation off --root-effects on`  (committed default)
# These three variants mirror the committed 0.25-rev proxy matrix. Arms A/B
# isolate the Glauert root effect at augmentation-on; arm B vs control isolates
# the augmentation at root-on. Everything else is the committed case (dynamic
# stall off, tip effects on, Du-Selig a=b=d=1).
#
# Run matrix (47 runs, all Sequence H): D/32 coarse 3 models x 5 speeds
# (7/10/13/15/25) x 2 arms + D/48 fine 3 models x 2 speeds (7/13) x 2 arms,
# plus the 5 ASM-mesh coarse control runs that complete the three-way at the
# committed physics (the ALM/ASM control baselines already exist, 2026-09-21).
# 20 m/s is deliberately absent (renderable but not staged).
#
# Task -> runs mapping (SLURM_ARRAY_TASK_ID -> model, arm, runs in order):
#   id  model      arm                runs (model:U<meta>-<arm label>)
#   0   alm        aug-on-root-off    7c,10c,13c,15c,25c,7f,13f   -> 7 runs
#   1   alm        aug-on-root-on     7c,10c,13c,15c,25c,7f,13f   -> 7 runs
#   2   asm        aug-on-root-off    7c,10c,13c,15c,25c,7f,13f   -> 7 runs
#   3   asm        aug-on-root-on     7c,10c,13c,15c,25c,7f,13f   -> 7 runs
#   4   asm-mesh   aug-on-root-off    7c,10c,13c,15c,25c,7f,13f   -> 7 runs
#   5   asm-mesh   aug-on-root-on     7c,10c,13c,15c,25c,7f,13f   -> 7 runs
#   6   asm-mesh   aug-off-root-on    7c,10c,13c,15c,25c           -> 5 runs
# ("c" = coarse D/32, "f" = fine D/48; speeds ascending, coarse before fine.)
#
# Per-task invocation:
#   runPhaseVI.sh -m <model> -u <speed> -mesh <coarse|fine> -s H \
#       --rotational-augmentation <on|off> --root-effects <on|off> \
#       --run-label <arm label> --restart --run
# The `--run-label` keeps each arm in its own restartable directory
# (runs/<model>-U<speed>-<mesh>-<arm label>); without it the two arms would
# overwrite each other's run directory and `--restart` would continue from the
# wrong physics. The arm label is recorded in run.json.
#
# Resource sizing (30k cells/core heuristic, `--ntasks=48` kept):
#   coarse D/32 = 382 x 168 x 104 = 6,674,304 cells  -> 139,048 cells/rank
#   fine   D/48 = 573 x 252 x 156 = 22,525,776 cells -> 469,287 cells/rank
#   30k cells/core would ask for ceil(6674304/30000)=223 ranks (coarse) and
#   ceil(22525776/30000)=751 ranks (fine), i.e. 5 and 16 nodes. The array runs
#   both meshes in the same task, so a single --ntasks must cover the fine
#   need; 48 ranks is kept because it is the committed 48-way decomposition
#   (`config/case.yaml`), the runner requires --ranks == SLURM_NTASKS, both
#   meshes already converged at 48 ranks in Stage 1+2 / the 2026-09-21
#   mesh-insensitivity check, and matching the baseline decomposition keeps the
#   physics delta attributable to the model, not the partition. See CAMPAIGN.md.
#
# Failure policy: continue-on-error. A failed run is logged and the task keeps
# going so the remaining independent runs still produce data; the task exits 1
# with a per-task summary listing every failed run (see run_one below).
#
# Compare into a separate --out (campaign-results/<arm>/U<speed>-H) so the
# preserved 2026-09-21 baselines under results/U*-H/ are never overwritten.
#
# PREPARED ONLY. This file refuses to run without
# PHASEVI_LONG_QUEUE_AUTHORIZED=1 and is never submitted by the preparing
# change. `runPhaseVI.sh --submit` does not launch this array.
#
# Dry-run listing (no Slurm, no OpenFOAM; prints every task->run mapping):
#   PHASEVI_CAMPAIGN_DRY_RUN=1 sh scripts/slurm/campaign-rotational-augmentation.slurm
#
# Submit from the validation package directory (Slurm spools the script, so the
# package is resolved from $SLURM_SUBMIT_DIR):
#   cd turbinesFoam/validation/phaseVI
#   PHASEVI_LONG_QUEUE_AUTHORIZED=1 sbatch scripts/slurm/campaign-rotational-augmentation.slurm
#SBATCH -p sequana_cpu
#SBATCH --ntasks=48
#SBATCH --nodes=1
# Memory: the partition default DefMemPerCPU=8000 makes 48 ranks request 375 GB
# (the whole node, 384 GB), so each task needed a fully empty node to schedule.
# Cap it explicitly; the fine mesh (22.5 M cells / 48 ranks) needs well under this.
#SBATCH --mem=192G
#SBATCH -J phaseVI-ra-campaign
#SBATCH --time=96:00:00
#SBATCH --array=0-6
#SBATCH -e %j.err
#SBATCH -o %j.out

set -eu

# Number of array tasks (must match --array=0-<n_tasks-1> above).
n_tasks=7

# Phase VI campaign arms. map_task sets task_model / task_arm for a task id;
# task_runs prints one "model speed mesh aug root label" row per run.
task_model=""
task_arm=""
map_task() {
    case "$1" in
        0) task_model=alm;      task_arm=aug-on-root-off ;;
        1) task_model=alm;      task_arm=aug-on-root-on ;;
        2) task_model=asm;      task_arm=aug-on-root-off ;;
        3) task_model=asm;      task_arm=aug-on-root-on ;;
        4) task_model=asm-mesh; task_arm=aug-on-root-off ;;
        5) task_model=asm-mesh; task_arm=aug-on-root-on ;;
        6) task_model=asm-mesh; task_arm=aug-off-root-on ;;
        *) return 2 ;;
    esac
    return 0
}

task_runs() {
    map_task "$1" || return 2
    case "$task_arm" in
        aug-on-root-off) aug=on;  root=off; fine_speeds="7 13" ;;
        aug-on-root-on)  aug=on;  root=on;  fine_speeds="7 13" ;;
        aug-off-root-on) aug=off; root=on;  fine_speeds="" ;;
    esac
    for speed in 7 10 13 15 25; do
        printf '%s %s coarse %s %s %s\n' \
            "$task_model" "$speed" "$aug" "$root" "$task_arm"
    done
    for speed in $fine_speeds; do
        printf '%s %s fine %s %s %s\n' \
            "$task_model" "$speed" "$aug" "$root" "$task_arm"
    done
}

# Dry-run: print the whole task -> run map and exit 0, before touching Slurm or
# OpenFOAM. Used by the verification and documentation.
if [ "${PHASEVI_CAMPAIGN_DRY_RUN:-0}" = "1" ]; then
    task_id=0
    while [ "$task_id" -lt "$n_tasks" ]; do
        map_task "$task_id"
        echo "array task ${task_id}: model=${task_model} arm=${task_arm}"
        task_runs "$task_id" | while IFS= read -r row; do
            # shellcheck disable=SC2086
            set -- $row
            run_token="$1-U$2-$3-$6"
            echo "  runs/${run_token}"
            echo "    runPhaseVI.sh -m $1 -u $2 -mesh $3 -s H --rotational-augmentation $4 --root-effects $5 --run-label $6 --restart --run"
        done
        task_id=$((task_id + 1))
    done
    exit 0
fi

if [ "${PHASEVI_LONG_QUEUE_AUTHORIZED:-0}" != "1" ]; then
    echo "ERROR: long-queue authorization not granted; this file is prepared only." >&2
    exit 5
fi

module purge
module load openfoam/v2506_openmpi-4.1.4_gnu gcc

# The module exports Int32 paths; set the Int64 identity first and re-source the
# OpenFOAM bashrc so PATH points at the installed linux64GccDPInt64Opt binaries.
export WM_ARCH=linux64
export WM_COMPILER=Gcc
export WM_COMPILE_OPTION=Opt
export WM_PRECISION_OPTION=DP
export WM_LABEL_SIZE=64
export WM_OPTIONS=linux64GccDPInt64Opt
# etc/bashrc is not written for strict mode: it dereferences optional variables
# (WM_PROJECT_SITE on SDumont) and can return non-zero, so `set -eu` aborts the
# job while sourcing it. Disable both while sourcing, then restore them.
set +eu
. "$WM_PROJECT_DIR/etc/bashrc"
set -eu

export FOAM_USER_LIBBIN=$WM_PROJECT_USER_DIR/platforms/$WM_OPTIONS/lib
# libturbinesFoam.so is built with the GCC-14 toolchain: prepend its libstdc++
# (GLIBCXX_3.4.32 / CXXABI_1.3.15) or the built library fails to load. The
# OpenFOAM Int64 lib and the openmpi sys dir stay on the search path.
export LD_LIBRARY_PATH=/scratch/app/gcc/14.2.0/lib64:$FOAM_USER_LIBBIN:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib/sys-openmpi:$LD_LIBRARY_PATH

# Slurm executes a spooled copy of this script (/var/spool/slurmd/...), so
# BASH_SOURCE does not point into the repository; resolve the package from the
# submission directory instead (same fix as production.slurm/asm-mesh.slurm).
pkg_dir="${PHASEVI_PKG_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}"
if [ ! -x "${pkg_dir}/scripts/runPhaseVI.sh" ]; then
    echo "ERROR: ${pkg_dir}/scripts/runPhaseVI.sh not found; submit from the package directory or set PHASEVI_PKG_DIR." >&2
    exit 3
fi

task_id="${SLURM_ARRAY_TASK_ID:?array task id missing}"
if ! map_task "$task_id"; then
    echo "ERROR: no run list for array task ${task_id}" >&2
    exit 2
fi
echo "Array task ${task_id}: model=${task_model} arm=${task_arm} on $(hostname)"

# Continue-on-error: each run is independent, so a failure is recorded and the
# task proceeds. The task exits 1 after the loop if any run failed.
failed=0
total=0
failed_runs=""

run_one() {
    run_model=$1
    run_speed=$2
    run_mesh=$3
    run_aug=$4
    run_root=$5
    run_label=$6
    run_token="${run_model}-U${run_speed}-${run_mesh}-${run_label}"
    log_dir="${pkg_dir}/runs/campaign-logs"
    mkdir -p "$log_dir"
    log="${log_dir}/${SLURM_ARRAY_JOB_ID:-local}.${task_id}.${run_token}.log"
    total=$((total + 1))
    echo "=== run ${run_token}: rotational-augmentation=${run_aug} root-effects=${run_root} ===" | tee -a "$log"
    if "${pkg_dir}/scripts/runPhaseVI.sh" -m "$run_model" -u "$run_speed" -mesh "$run_mesh" \
            -s H --rotational-augmentation "$run_aug" --root-effects "$run_root" \
            --run-label "$run_label" --restart --run >>"$log" 2>&1; then
        echo "OK   ${run_token} (log: ${log})" | tee -a "$log"
    else
        rc=$?
        echo "FAIL ${run_token} (exit ${rc}; log: ${log})" | tee -a "$log"
        failed=$((failed + 1))
        failed_runs="${failed_runs} ${run_token}"
    fi
}

# The here-doc (not a pipe) keeps the counters in this shell: a pipe would run
# the loop in a subshell and lose `total`/`failed`.
while IFS= read -r row; do
    [ -n "$row" ] || continue
    read -r run_model run_speed run_mesh run_aug run_root run_label <<<"$row"
    run_one "$run_model" "$run_speed" "$run_mesh" "$run_aug" "$run_root" "$run_label"
done <<EOF
$(task_runs "$task_id")
EOF

if [ "$failed" -gt 0 ]; then
    echo "Array task ${task_id} summary: ${failed}/${total} run(s) failed:${failed_runs}" >&2
    exit 1
fi
echo "Array task ${task_id} summary: all ${total} run(s) completed"
