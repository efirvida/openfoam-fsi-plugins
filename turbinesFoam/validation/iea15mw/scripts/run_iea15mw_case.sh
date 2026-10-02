#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# IEA 15-240-RWT rated-point run body, shared by the production wrapper
# (slurm/coarse.slurm) and the development wrapper (slurm/coarse-dev.slurm).
#
# The run is split into slices of TURBINE_SLICE_REVS revolutions. Each slice
# sets the OpenFOAM endTime to the slice end and stops *cleanly* there (OpenFOAM
# always writes the final time), so a requeue resumes from a written, consistent
# time directory. This avoids killing the solver mid-write on the 20-minute
# development queue.
#
# Environment:
#   TURBINE_PKG_DIR            package dir (default $SLURM_SUBMIT_DIR)
#   TURBINE_RUN_DIR            run dir (default runs/iea15mw-rated-<mesh>)
#   TURBINE_MESH               coarse | medium | fine (default coarse)
#   TURBINE_UPSTREAM           upstream extent [D] (default 5)
#   TURBINE_DOWNSTREAM         downstream extent [D] (default 15)
#   TURBINE_LATERAL            lateral half-extent [D] (default 4)
#   TURBINE_FINE_MAX           refined region downstream end [D] (default 8)
#   TURBINE_FINE_LAT           refined region lateral half-width [D] (default 1.5)
#   TURBINE_DOMAIN_TOP         domain top [m] above the rotor (default 2.5D)
#   TURBINE_RANKS              ranks (default 48)
#   TURBINE_TOTAL_REVS         total revolutions (default 3)
#   TURBINE_SLICE_REVS         revolutions per allocation (default 0.5)
#   TURBINE_REQUEUE            1 = requeue to continue a long run (default 1)
#   TURBINE_SOLVER_TIME_BUDGET safety wall timeout in seconds (default: Slurm)
#   TURBINE_MPI_MCA            override the mpirun MCA flags
#
# Submit from the package directory so $SLURM_SUBMIT_DIR resolves the package.
set -eu

module purge
module load openfoam/v2506_openmpi-4.1.4_gnu gcc

export WM_ARCH=linux64
export WM_COMPILER=Gcc
export WM_COMPILE_OPTION=Opt
export WM_PRECISION_OPTION=DP
export WM_LABEL_SIZE=64
export WM_OPTIONS=linux64GccDPInt64Opt
set +eu
. "$WM_PROJECT_DIR/etc/bashrc"
set -eu

export FOAM_USER_LIBBIN=$WM_PROJECT_USER_DIR/platforms/$WM_OPTIONS/lib
export LD_LIBRARY_PATH=/scratch/app/gcc/14.2.0/lib64:$FOAM_USER_LIBBIN:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib/sys-openmpi:$LD_LIBRARY_PATH
export PYTHON=${PYTHON:-/scratch/leahk/eduardo.donestevez/venv/bin/python}

pkg_dir="${TURBINE_PKG_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}"
if [ ! -f "${pkg_dir}/tools/generate_case.py" ]; then
    echo "ERROR: submit from turbinesFoam/validation/iea15mw (or set TURBINE_PKG_DIR)." >&2
    exit 3
fi
cd "$pkg_dir"

run_dir="${TURBINE_RUN_DIR:-runs/iea15mw-rated-${TURBINE_MESH:-coarse}}"
mesh="${TURBINE_MESH:-coarse}"
ranks="${TURBINE_RANKS:-48}"

model="${TURBINE_MODEL:-alm}"
# Castellate the rotor disk? Defaults to "on iff the model is asm-mesh", matching
# tools/generate_case.py. The model comparison (ALM vs ASM vs ASM-mesh) forces it
# on so all three share one mesh, and passing --snappy keeps the generator's
# deltaT in sync with the mesh actually built.
snappy="${TURBINE_SNAPPY:-}"
if [ -z "$snappy" ]; then
    if [ "$model" = "asm-mesh" ]; then snappy=on; else snappy=off; fi
fi
domain_args=(--mesh "$mesh" --ranks "$ranks" --model "$model" --snappy "$snappy")
if [ -n "${TURBINE_N_CHORDWISE:-}" ]; then
    domain_args+=(--n-chordwise "$TURBINE_N_CHORDWISE")
fi
if [ -n "${TURBINE_SNAPPY_LEVEL:-}" ]; then
    domain_args+=(--snappy-level "$TURBINE_SNAPPY_LEVEL")
fi
write_deg="${TURBINE_WRITE_DEG:-}"
if [ -n "$write_deg" ]; then
    domain_args+=(--write-interval-deg "$write_deg")
fi
for pair in \
    "TURBINE_UPSTREAM:--domain-upstream" \
    "TURBINE_DOWNSTREAM:--domain-downstream" \
    "TURBINE_LATERAL:--domain-lateral" \
    "TURBINE_FINE_MAX:--domain-fine-max" \
    "TURBINE_FINE_LAT:--domain-fine-lat" \
    "TURBINE_DOMAIN_TOP:--domain-top"; do
    var="${pair%%:*}"
    flag="${pair##*:}"
    value="${!var:-}"
    if [ -n "$value" ]; then
        domain_args+=("$flag" "$value")
    fi
done
total_revs="${TURBINE_TOTAL_REVS:-3}"
requeue="${TURBINE_REQUEUE:-1}"

# The ALM writes a per-step `angleDeg.<name>` into the current time directory,
# creating field-less time dirs that `startFrom latestTime` would pick (and,
# without a write time, purgeWrite never removes them). Drop them so the resume
# uses a directory that actually has the fields. The slice length equals the
# write interval, so every slice ends with a real field write to resume from.
if [ -d "${run_dir}/processor0" ]; then
    for d in "${run_dir}"/processor*/[0-9]*; do
        [ -e "$d" ] || continue
        [ -f "$d/p" ] || rm -rf "$d"
    done
fi
# Without requeue the whole run must fit in one allocation.
if [ "$requeue" = "1" ]; then
    slice_revs="${TURBINE_SLICE_REVS:-0.5}"
else
    slice_revs="$total_revs"
fi

# Latest written processor time (0 => fresh case).
latest=0
if [ -d "${run_dir}/processor0" ]; then
    latest=$("$PYTHON" - "$run_dir/processor0" <<'PY'
import os
import sys

times = []
for name in os.listdir(sys.argv[1]):
    try:
        times.append(float(name))
    except ValueError:
        pass
print(f"{max(times):.10g}" if times else "0")
PY
)
fi

t_rev=$("$PYTHON" -c "import sys; sys.path.insert(0, '${pkg_dir}/tools'); import generate_case as g; print(f'{g.revolution_period(g.RATED_RPM):.10g}')")
latest_revs=$("$PYTHON" -c "print(f'{${latest} / ${t_rev}:.10g}')")
slice_end_revs=$("$PYTHON" -c "print(f'{min(${total_revs}, ${latest_revs} + ${slice_revs}):.10g}')")

if [ "$latest" = "0" ]; then
    resume=0
else
    resume=1
fi

echo "IEA 15 MW P3 on $(hostname): latest=${latest} s (${latest_revs} rev); slice end=${slice_end_revs} rev; mesh=${mesh}; ranks=${ranks}"

if [ "$resume" -eq 1 ]; then
    "$PYTHON" tools/generate_case.py --case-dir "$run_dir" "${domain_args[@]}" \
        --end-revs "$slice_end_revs" --start-from latestTime
else
    "$PYTHON" tools/generate_case.py --case-dir "$run_dir" "${domain_args[@]}" \
        --end-revs "$slice_end_revs"
fi

# ASM-mesh: stage the committed blade STL the twin references as surfaceGeometry
# so restarts/relocated runs resolve their own surface (sha256-checked).
if [ "$model" = "asm-mesh" ]; then
    if ! "$PYTHON" tools/stage_blade_stl.py --run-dir "$run_dir" > "$run_dir/log.stage-blade-stl" 2>&1; then
        cat "$run_dir/log.stage-blade-stl" >&2
        echo "ERROR: staging the blade STL for asm-mesh failed" >&2
        exit 3
    fi
fi

cd "$run_dir"

if [ ! -d constant/polyMesh ]; then
    if ! blockMesh > log.blockMesh 2>&1; then
        tail -30 log.blockMesh >&2
        echo "ERROR: blockMesh failed" >&2
        exit 3
    fi
fi
# ASM-mesh: castellate the rotor-disk cylinder so the local cell resolves the
# blade chord. --overwrite replaces blockMesh's polyMesh in place, and the guard
# above means a resumed run (polyMesh already snapped) skips both.
if [ "$snappy" = "on" ]; then
    if ! snappyHexMesh -overwrite > log.snappyHexMesh 2>&1; then
        tail -40 log.snappyHexMesh >&2
        echo "ERROR: snappyHexMesh failed" >&2
        exit 3
    fi
fi
if ! topoSet > log.topoSet 2>&1; then
    tail -30 log.topoSet >&2
    echo "ERROR: topoSet failed" >&2
    exit 3
fi
if ! checkMesh > log.checkMesh 2>&1; then
    echo "WARNING: checkMesh reported problems (continuing)" >&2
fi

if [ "$resume" -eq 0 ]; then
    # The renderer keeps 0.org so --check is clean; the run dir gets a real 0/.
    rm -rf 0 processor*
    cp -r 0.org 0
    if ! decomposePar -force > log.decomposePar 2>&1; then
        tail -30 log.decomposePar >&2
        echo "ERROR: decomposePar failed" >&2
        exit 3
    fi
fi

# MPI: the legacy openib BTL races in device-memory registration, so force the
# UCX PML and exclude it. Pack the ranks onto the nodes Slurm actually
# allocated (ppr = ceil(ranks / SLURM_NNODES)): a fixed ppr:8:node failed job
# 11604860 with "requested more processes than the ppr for this topology can
# support" when Slurm granted only 3 nodes. The project policy forbids capping
# --nodes, so the mapping follows the allocation instead.
if [ "${TURBINE_MPI_MCA+x}" = "x" ]; then
    mpi_mca="$TURBINE_MPI_MCA"
else
    mpi_mca="-mca pml ucx --mca btl ^openib"
    # Do NOT force --map-by ppr:N:node: OpenMPI then requires exactly N slots on
    # EVERY allocated node, and an uneven allocation (48 ranks over 7 nodes
    # leaves one node with 6 slots) aborts with "not enough slots available".
    # The default mapping is slot-aware and honours whatever Slurm granted.
fi

# Safety wall budget: the slice endTime normally stops the solver first.
budget="${TURBINE_SOLVER_TIME_BUDGET:-}"
if [ -z "$budget" ] && [ -n "${SLURM_JOB_ID:-}" ]; then
    end=$(scontrol show job "$SLURM_JOB_ID" 2>/dev/null | tr ' ' '\n' | sed -n 's/^EndTime=//p' | head -1)
    if [ -n "$end" ] && end_s=$(date -d "$end" +%s 2>/dev/null); then
        left=$(( end_s - $(date +%s) - 150 ))
        if [ "$left" -ge 120 ]; then
            budget=$left
        fi
    fi
fi
: "${budget:=900}"

rc=0
# shellcheck disable=SC2086
if ! timeout -k 120 -s INT "$budget" mpirun $mpi_mca -np "$ranks" pimpleFoam -parallel > log.pimpleFoam 2>&1; then
    rc=$?
fi

if [ "$rc" -ne 0 ] && [ "$rc" -ne 124 ]; then
    tail -40 log.pimpleFoam >&2
    echo "ERROR: pimpleFoam failed (rc=$rc)" >&2
    exit 3
fi

# The solver must actually have advanced the written time; a launch that fails
# (e.g. an MPI slot error) exits 0 from mpirun but leaves the run at `latest`.
new_latest=$("$PYTHON" - processor0 <<'PY'
import os
import sys

times = []
for name in os.listdir(sys.argv[1]):
    try:
        times.append(float(name))
    except ValueError:
        pass
print(f"{max(times):.10g}" if times else "0")
PY
)
advanced=$("$PYTHON" -c "print(1 if ${new_latest} > ${latest} else 0)")

if [ "$advanced" != "1" ]; then
    tail -40 log.pimpleFoam >&2
    echo "ERROR: solver exited (rc=$rc) without advancing past ${latest} s" >&2
    exit 3
fi

if [ "$slice_end_revs" = "$total_revs" ] && [ "$rc" -eq 0 ]; then
    echo "IEA 15 MW run complete: ${run_dir}"
    exit 0
fi

if [ "$requeue" = "1" ] && [ -n "${SLURM_JOB_ID:-}" ]; then
    # Requeue the same job (does not consume a new submission, unlike sbatch):
    # the accounting association is at its job-submit limit. This needs
    # --requeue (Requeue=1); --no-requeue makes scontrol reject it. A genuine
    # solver failure exits non-zero and is NOT auto-requeued on this cluster, so
    # the failure path cannot loop.
    echo "Slice reached ${new_latest} s (${slice_end_revs} rev); requeueing ${SLURM_JOB_ID}"
    scontrol requeue "$SLURM_JOB_ID"
    exit 0
fi

echo "ERROR: slice ended before the total without a continuation mechanism (rc=$rc)" >&2
exit 3
