#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Phase VI rotational-augmentation power-curve campaign, REDESIGNED as a
# two-arm matrix grouped into few array tasks so it fits the association
# submit limit. Each array task runs a documented list of runs sequentially,
# 48 ranks on one node, at most 96 h wall time (maintainer-authorized,
# mirroring production.slurm), restarting every run from its latest written
# time.
#
# Physics arms so each model is evaluated at both root-effect settings with data:
#   arm A   `--rotational-augmentation on  --root-effects off --tip-effects on`   (the candidate)
#   arm B   `--rotational-augmentation on  --root-effects on  --tip-effects on`   (root-on)
#   arm A'  `--rotational-augmentation on  --root-effects off --tip-effects off`  (tip-off diagnostic)
#   arm C'  `--rotational-augmentation off --root-effects off --tip-effects off`  (augmentation isolation)
# plus the committed control for the ASM-mesh baseline gap:
#   control `--rotational-augmentation off --root-effects on  --tip-effects on`   (committed default)
# These variants mirror the committed 0.25-rev proxy matrix. Arms A/B isolate the
# Glauert root effect at augmentation-on; arm B vs control isolates the
# augmentation at root-on; arm A' vs arm A isolates the Glauert tip effect at
# augmentation-on. Everything else is the committed case (dynamic stall off,
# Du-Selig a=b=d=1).
#
# Arm A' is the end-effect diagnostic: the modern ALM literature (Meyer Forsting
# 2019/2020; Kim 2015; Jha 2014; Mohammadi 2024) holds that a BEM tip/root loss
# corrects a disc, not a line, and is invalid for an actuator line. See
# `campaign-results/formulation-review.md` §2. Result (2026-09-28): the tip loss
# is worth 27-62 points and deleting it OVER-corrects (+19.5% at 7 m/s), i.e. it
# was cancelling the epsilon over-smearing bias rather than correcting anything.
# Arm A' therefore also carries the 7 m/s D/48 fine run, to test whether the
# over-shoot shrinks as epsilon drops (0.63 m -> 0.42 m). Arm C' isolates how
# much of the over-shoot is the Du-Selig augmentation (A' vs C' differ only in
# the augmentation flag).
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
# No --nodes and no --mem: request only the 48 cores and let Slurm place them.
# HISTORY: a `--nodes=1-2` cap used to sit here because, without any cap, Slurm
# spread the 48 ranks over 7+ nodes and the OpenMPI/PMIx startup failed
# intermittently (MPI_Init_thread NULL-communicator aborts with
# OPAL/pmix3x_client.c errors, and segfaults inside MPI_Init_thread); a 3-node
# allocation had zero such failures. The cap is removed per the project policy
# (cores only, Slurm decides placement). If the MPI startup failures return, fix
# them with --distribution / --ntasks-per-node or an MPI/PMIx fix, NOT with a
# hard node cap.
# No --mem is set: the partition default DefMemPerCPU=8000 applies per CPU and
# OpenFOAM only needs the rank count to match the decomposition.
#SBATCH -J phaseVI-ra-campaign
#SBATCH --time=96:00:00
#SBATCH --array=0-12
#SBATCH -e %j.err
#SBATCH -o %j.out

set -eu

# Number of array tasks (must match --array=0-<n_tasks-1> above).
n_tasks=13

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
        7) task_model=alm;      task_arm=aug-on-tip-off-root-off ;;
        8) task_model=alm;      task_arm=aug-off-tip-off-root-off ;;
        9) task_model=alm;      task_arm=aug-off-tip-off-root-off-scheme-linear ;;
        10) task_model=alm;     task_arm=aug-off-tip-off-root-off-polar-csu065 ;;
        11) task_model=alm;     task_arm=aug-on-root-off-polar-csu065 ;;
        12) task_model=alm;     task_arm=aug-on-tip-off-root-off-polar-csu065 ;;
        *) return 2 ;;
    esac
    return 0
}

task_runs() {
    map_task "$1" || return 2
    tip=on
    scheme=default
    polar=default
    coarse_speeds="7 10 13 15 25"
    case "$task_arm" in
        aug-on-root-off)         aug=on;  root=off; fine_speeds="7 13" ;;
        aug-on-root-on)          aug=on;  root=on;  fine_speeds="7 13" ;;
        aug-on-tip-off-root-off) aug=on;  root=off; tip=off; coarse_speeds="7 10 13"; fine_speeds="7" ;;
        aug-off-tip-off-root-off) aug=off; root=off; tip=off; coarse_speeds="7"; fine_speeds="" ;;
        aug-off-tip-off-root-off-scheme-linear)
                                 aug=off; root=off; tip=off; scheme=linear; coarse_speeds="7"; fine_speeds="" ;;
        aug-off-tip-off-root-off-polar-csu065)
                                 aug=off; root=off; tip=off; polar=csu065; coarse_speeds="7"; fine_speeds="" ;;
        aug-on-root-off-polar-csu065)
                                 aug=on;  root=off; tip=on;  polar=csu065; coarse_speeds="7"; fine_speeds="" ;;
        aug-on-tip-off-root-off-polar-csu065)
                                 aug=on;  root=off; tip=off; polar=csu065; coarse_speeds="7"; fine_speeds="" ;;
        aug-off-root-on)         aug=off; root=on;  fine_speeds="" ;;
    esac
    for speed in $coarse_speeds; do
        printf '%s %s coarse %s %s %s %s %s %s\n' \
            "$task_model" "$speed" "$aug" "$root" "$tip" "$scheme" "$polar" "$task_arm"
    done
    for speed in $fine_speeds; do
        printf '%s %s fine %s %s %s %s %s %s\n' \
            "$task_model" "$speed" "$aug" "$root" "$tip" "$scheme" "$polar" "$task_arm"
    done
}

# Expand a row polar token to the committed polar filename. Prints nothing for
# the committed default. Returns 2 for an unknown token. Defined before the
# dry-run block, which also uses it.
expand_polar() {
    case "$1" in
        default) ;;
        csu065) printf '%s' "S809_CSU_Re0.65M_total.dat" ;;
        *) return 2 ;;
    esac
}

# Expand a row scheme token to the full div(phi,U) scheme string. Prints
# nothing for the committed default. Returns 2 for an unknown token. Defined
# before the dry-run block, which also uses it.
expand_scheme() {
    case "$1" in
        default) ;;
        linear) printf '%s' "bounded Gauss linear" ;;
        linearUpwind) printf '%s' "bounded Gauss linearUpwind grad(U)" ;;
        *) return 2 ;;
    esac
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
            run_token="$1-U$2-$3-$9"
            dry_scheme=$(expand_scheme "$7") || dry_scheme="$7"
            dry_polar=$(expand_polar "$8") || dry_polar="$8"
            echo "  runs/${run_token}"
            echo "    runPhaseVI.sh -m $1 -u $2 -mesh $3 -s H --rotational-augmentation $4 --root-effects $5 --tip-effects $6${dry_scheme:+ --div-phi-u \"$dry_scheme\"}${dry_polar:+ --polar $dry_polar} --run-label $9 --restart --run"
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
skipped=0
failed_runs=""

run_one() {
    run_model=$1
    run_speed=$2
    run_mesh=$3
    run_aug=$4
    run_root=$5
    run_tip=$6
    run_scheme=$7
    run_polar=$8
    run_label=$9
    run_token="${run_model}-U${run_speed}-${run_mesh}-${run_label}"
    log_dir="${pkg_dir}/runs/campaign-logs"
    mkdir -p "$log_dir"
    log="${log_dir}/${SLURM_ARRAY_JOB_ID:-local}.${task_id}.${run_token}.log"
    # Idempotent resubmission: a run recorded OK in any campaign log already
    # reached endTime, so skip it instead of re-rendering, re-running
    # decomposePar and launching the solver again.
    if grep -qE "^OK +${run_token} " "${log_dir}/"*.log 2>/dev/null; then
        echo "SKIP ${run_token} (already completed)"
        skipped=$((skipped + 1))
        return 0
    fi
    total=$((total + 1))
    # Scheme ablation: the row carries a short token (empty = the committed
    # default) so the whitespace-separated row stays parseable; expand it to the
    # full div(phi,U) scheme here. See runPhaseVI.sh --div-phi-u.
    div_phi=""
    if ! div_phi=$(expand_scheme "$run_scheme"); then
        echo "ERROR: unknown scheme token '$run_scheme'" >&2
        return 2
    fi
    div_phi_args=()
    if [ -n "$div_phi" ]; then
        div_phi_args=(--div-phi-u "$div_phi")
    fi
    polar_file=""
    if ! polar_file=$(expand_polar "$run_polar"); then
        echo "ERROR: unknown polar token '$run_polar'" >&2
        return 2
    fi
    polar_args=()
    if [ -n "$polar_file" ]; then
        polar_args=(--polar "$polar_file")
    fi
    echo "=== run ${run_token}: rotational-augmentation=${run_aug} root-effects=${run_root} tip-effects=${run_tip} div-phi-u=${div_phi:-default} polar=${polar_file:-default} ===" | tee -a "$log"
    if "${pkg_dir}/scripts/runPhaseVI.sh" -m "$run_model" -u "$run_speed" -mesh "$run_mesh" \
            -s H --rotational-augmentation "$run_aug" --root-effects "$run_root" \
            --tip-effects "$run_tip" ${div_phi_args[@]+"${div_phi_args[@]}"} \
            ${polar_args[@]+"${polar_args[@]}"} \
            --run-label "$run_label" --restart --run >>"$log" 2>&1; then
        echo "OK   ${run_token} (log: ${log})" | tee -a "$log"
        # Free the bulk field data.  The rotor-power/torque/thrust history and
        # the element loads live in postProcessing/ (written every time step,
        # never purged by purgeWrite) and are all the validation needs, so the
        # decomposed fields under processor*/ are dead weight once the run
        # reached endTime.  Dropping them keeps the shared group quota bounded
        # as runs accumulate.  Set PHASEVI_KEEP_FIELDS=1 to keep them.
        if [ "${PHASEVI_KEEP_FIELDS:-0}" != "1" ]; then
            rm -rf "${pkg_dir}/runs/${run_token}"/processor*
        fi
    else
        rc=$?
        echo "FAIL ${run_token} (exit ${rc}; log: ${log})" | tee -a "$log"
        failed=$((failed + 1))
        failed_runs="${failed_runs} ${run_token}"
    fi
}

# Read the run list into an array first, then iterate.  A pipe would run the
# loop in a subshell and lose `total`/`failed`; a here-doc with $(...) is
# fragile under `set -e` in some bash versions, so mapfile + process
# substitution is the robust alternative.
mapfile -t run_list < <(task_runs "$task_id")
for row in "${run_list[@]}"; do
    [ -n "$row" ] || continue
    read -r run_model run_speed run_mesh run_aug run_root run_tip run_scheme run_polar run_label <<<"$row"
    run_one "$run_model" "$run_speed" "$run_mesh" "$run_aug" "$run_root" "$run_tip" "$run_scheme" "$run_polar" "$run_label"
done

if [ "$failed" -gt 0 ]; then
    echo "Array task ${task_id} summary: ${failed}/${total} run(s) failed:${failed_runs} (skipped ${skipped} already-complete)" >&2
    exit 1
fi
echo "Array task ${task_id} summary: all ${total} run(s) completed (skipped ${skipped} already-complete)"
