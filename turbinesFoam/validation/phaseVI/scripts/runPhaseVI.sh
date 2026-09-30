#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Prepare (and optionally run or submit) one Phase VI run variant.
#
# Usage:
#   runPhaseVI.sh -m alm|asm|asm-mesh -u <wind-speed> [-mesh coarse|fine|ultra]
#                 [--domain long|squat] [-s H|S] [--solver urans|iddes]
#                 [--div-phi-u "bounded Gauss linear"] [--polar FILE.dat]
#                 [--nchordwise N] [--n-elements N] [--ranks N]
#                 [--run-label WORD] [--stage0]
#                 [--restart] [--rotational-augmentation on|off]
#                 [--root-effects on|off] [--run] [--submit]
#
# -m/-u select the model and the per-speed measured TSR from config/case.yaml.
# -mesh selects the mesh (default coarse = D/32); -s S selects the Sequence S
# 7 m/s repeat (s0700000). The case is rendered into runs/<id>/ (the committed
# case/ skeleton is never modified), the matching fvOptions twin is installed
# as system/fvOptions, the shared mesh is hardlinked in and run.json is written.
#
# -m asm-mesh installs the fvOptions.ASM-MESH twin and stages the committed
# blade STL into constant/triSurface/ through tools/stage_blade_stl.py, which
# checks it against the geometry metadata sha256 and aborts (exit 3) on a
# mismatch. Its --submit is refused (exit 2): the prepared array
# scripts/slurm/asm-mesh.slurm is prepared-only and no ASM-mesh job may be
# submitted by this change.
#
# --solver iddes renders the Stage 3 LES kOmegaSSTIDDES variant (fixed 0.0025 s
# step) and appends -iddes to the run id. --nchordwise N overrides the ASM
# chordwise strip count (ASM family only; appends -ncN) and --ranks N overrides
# the configured decomposition (rendered into decomposeParDict and used for
# mpirun); inside a Slurm allocation --ranks must match SLURM_NTASKS.
# --n-elements N overrides the configured blade spanwise element count (every
# model; rendered as `nElements` in the blade subdicts). It is validated as a
# positive integer (exit 2 otherwise) and forwarded to the renderer when set.
# --run-label WORD appends -WORD to the run id (`runs/<id>-WORD`) and records it
# in run.json, so two render variants of the same (model, speed, mesh) live in
# separate, independently restartable directories (the two-arm campaign uses it
# to keep the augmentation/root arms apart).
#
# --stage0 caps the run at 0.25 revolutions (spec bound 0.3) for the authorized
# development queue. --restart resumes from the latest written time (falls back
# to startTime when no time has been written yet). --rotational-augmentation
# on|off overrides config/case.yaml for this render; when the flag is absent the
# YAML `actuator.rotational_augmentation.active` value governs unchanged.
# --root-effects on|off likewise overrides `actuator.end_effects.root` for this
# render (the Glauert root-effect ablation); absent, the YAML value governs.
# --run executes decomposePar and mpirun (inside a Slurm allocation); --submit
# hands the run to Slurm.
#
# Exit codes:
#   2  unsupported input (model, speed, mesh, domain, sequence, flag
#      combination or a --ranks value that differs from SLURM_NTASKS)
#   3  environment, blockMesh/checkMesh, solver or STL staging failure
#   4  generated case stale
#   5  long-queue authorization gate (PHASEVI_LONG_QUEUE_AUTHORIZED=1 required)
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$here/.." && pwd)

usage() {
    sed -n '2,50p' "$0" | sed 's/^# \{0,1\}//'
}

model=""
speed=""
mesh=coarse
domain=long
sequence=H
solver=urans
nchordwise=""
n_elements=""
ranks_override=""
rotational_augmentation=""
root_effects=""
tip_effects=""
tip_correction=""
div_phi_u=""
polar=""
run_label=""
stage0=0
restart=0
run=0
submit=0
while [ $# -gt 0 ]; do
    case "$1" in
        -m) model="$2"; shift ;;
        -u) speed="$2"; shift ;;
        -mesh|--mesh) mesh="$2"; shift ;;
        --domain) domain="$2"; shift ;;
        -s|--sequence) sequence="$2"; shift ;;
        --solver) solver="$2"; shift ;;
        --nchordwise) nchordwise="$2"; shift ;;
        --n-elements) n_elements="$2"; shift ;;
        --ranks) ranks_override="$2"; shift ;;
        --rotational-augmentation) rotational_augmentation="$2"; shift ;;
        --root-effects) root_effects="$2"; shift ;;
        --tip-effects) tip_effects="$2"; shift ;;
        --tip-correction) tip_correction="$2"; shift ;;
        --div-phi-u) div_phi_u="$2"; shift ;;
        --polar) polar="$2"; shift ;;
        --run-label) run_label="$2"; shift ;;
        --stage0) stage0=1 ;;
        --restart) restart=1 ;;
        --run) run=1 ;;
        --submit) submit=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "ERROR: unsupported argument: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

if [ -z "$model" ] || [ -z "$speed" ]; then
    echo "ERROR: -m alm|asm|asm-mesh and -u <wind-speed> are required" >&2
    usage >&2
    exit 2
fi
case "$model" in
    alm|asm|asm-mesh) ;;
    *) echo "ERROR: unsupported model: $model" >&2; exit 2 ;;
esac
case "$mesh" in
    coarse|fine|ultra) ;;
    *) echo "ERROR: unsupported mesh: $mesh" >&2; exit 2 ;;
esac
case "$domain" in
    long|squat) ;;
    *) echo "ERROR: unsupported domain: $domain" >&2; exit 2 ;;
esac
case "$sequence" in
    h|H) sequence=H ;;
    s|S) sequence=S ;;
    *) echo "ERROR: unsupported sequence: $sequence" >&2; exit 2 ;;
esac
case "$solver" in
    urans|iddes) ;;
    *) echo "ERROR: unsupported solver: $solver (choose urans or iddes)" >&2; exit 2 ;;
esac
if [ -n "$nchordwise" ]; then
    if [ "$model" = "alm" ]; then
        echo "ERROR: --nchordwise is ASM-family-only (-m asm or -m asm-mesh)" >&2
        exit 2
    fi
    case "$nchordwise" in
        *[!0-9]*) echo "ERROR: --nchordwise must be a positive integer" >&2; exit 2 ;;
    esac
    if [ "$nchordwise" -le 0 ]; then
        echo "ERROR: --nchordwise must be a positive integer" >&2
        exit 2
    fi
fi
if [ -n "$n_elements" ]; then
    case "$n_elements" in
        *[!0-9]*) echo "ERROR: --n-elements must be a positive integer" >&2; exit 2 ;;
    esac
    if [ "$n_elements" -le 0 ]; then
        echo "ERROR: --n-elements must be a positive integer" >&2
        exit 2
    fi
fi
if [ -n "$ranks_override" ]; then
    case "$ranks_override" in
        *[!0-9]*) echo "ERROR: --ranks must be a positive integer" >&2; exit 2 ;;
    esac
    if [ "$ranks_override" -le 0 ]; then
        echo "ERROR: --ranks must be a positive integer" >&2
        exit 2
    fi
fi
if [ -n "$rotational_augmentation" ]; then
    case "$rotational_augmentation" in
        on|off) ;;
        *) echo "ERROR: --rotational-augmentation must be on or off" >&2; exit 2 ;;
    esac
fi
if [ -n "$root_effects" ]; then
    case "$root_effects" in
        on|off) ;;
        *) echo "ERROR: --root-effects must be on or off" >&2; exit 2 ;;
    esac
fi
if [ -n "$tip_effects" ]; then
    case "$tip_effects" in
        on|off) ;;
        *) echo "ERROR: --tip-effects must be on or off" >&2; exit 2 ;;
    esac
fi
if [ -n "$tip_correction" ]; then
    case "$tip_correction" in
        on|off) ;;
        *) echo "ERROR: --tip-correction must be on or off" >&2; exit 2 ;;
    esac
fi
if [ -n "$div_phi_u" ]; then
    # Scheme-sensitivity ablation: must be a div(phi,U) scheme token, never an
    # arbitrary string (it is rendered into fvSchemes).
    case "$div_phi_u" in
        *Gauss*linear*) ;;
        *) echo "ERROR: --div-phi-u must be a Gauss-linear scheme (e.g. 'bounded Gauss linear')" >&2; exit 2 ;;
    esac
fi
if [ -n "$polar" ]; then
    # Reynolds-sensitivity ablation: a bare committed filename in data/polars/,
    # never a path (it is rendered into the fvOptions #include).
    case "$polar" in
        */*|.*|*" ") echo "ERROR: --polar must be a bare filename in data/polars/ (e.g. S809_CSU_Re0.65M_total.dat)" >&2; exit 2 ;;
        *.dat) ;;
        *) echo "ERROR: --polar must end in .dat" >&2; exit 2 ;;
    esac
    if [ ! -f "$root/data/polars/$polar" ]; then
        echo "ERROR: --polar file not found: data/polars/$polar" >&2; exit 2
    fi
fi
if [ -n "$run_label" ]; then
    # A path-safe token: letters, digits, dot, underscore, hyphen; no leading
    # dot/hyphen, so the appended `-<label>` cannot escape the runs/ directory.
    case "$run_label" in
        *[!A-Za-z0-9._-]*|.*|-*)
            echo "ERROR: --run-label must match [A-Za-z0-9._-]+ and not start with '.' or '-'" >&2
            exit 2
            ;;
    esac
fi
if [ "$submit" -eq 1 ] && { [ "$solver" = "iddes" ] || [ -n "$nchordwise" ] \
        || [ -n "$n_elements" ] || [ -n "$ranks_override" ] \
        || [ -n "$run_label" ]; }; then
    echo "ERROR: --submit cannot carry --solver iddes, --nchordwise, --n-elements," >&2
    echo "  --ranks or --run-label;" >&2
    echo "  Stage 3 is submitted through its prepared arrays:" >&2
    echo "  scripts/slurm/stage3.slurm and scripts/slurm/stage3-d64.slurm." >&2
    exit 2
fi
if [ "$submit" -eq 1 ] && [ "$model" = "asm-mesh" ]; then
    echo "ERROR: --submit is not available for -m asm-mesh;" >&2
    echo "  the ASM-mesh runs are prepared through scripts/slurm/asm-mesh.slurm," >&2
    echo "  which is prepared-only and must not be submitted by this change." >&2
    exit 2
fi

# Validates the (speed, mesh, model, sequence, solver) combination and the
# tip-displacement constraint of the selected time step; rejects unsupported
# values with exit 2.
if ! python3 "$root/tools/case_config.py" --select "$speed" "$mesh" "$model" \
        "$sequence" --solver "$solver" >/dev/null; then
    echo "ERROR: unsupported (model, speed, mesh, sequence, solver) combination" >&2
    exit 2
fi

config_ranks=$(python3 -c "import sys; sys.path.insert(0, '$root/tools'); import case_config; print(case_config.load_config()['decomposition']['number_of_subdomains'])")
ranks="$config_ranks"
if [ -n "$ranks_override" ]; then
    ranks="$ranks_override"
fi
# Inside a Slurm allocation the rendered decomposeParDict and `mpirun -np` must
# not ask for more ranks than sbatch allocated.
if [ -n "${SLURM_NTASKS:-}" ]; then
    case "$SLURM_NTASKS" in
        *[!0-9]*)
            echo "ERROR: SLURM_NTASKS is not a positive integer: $SLURM_NTASKS" >&2
            exit 2
            ;;
    esac
    if [ "$ranks" -ne "$SLURM_NTASKS" ]; then
        echo "ERROR: --ranks $ranks does not match SLURM_NTASKS=$SLURM_NTASKS." >&2
        echo "  Re-run with --ranks $SLURM_NTASKS or fix the allocation." >&2
        exit 2
    fi
fi

# Propagate the environment (3) / stale-case (4) exit code.
"$here/check_environment.sh" || exit $?

speed_token=$(printf '%g' "$speed")
run_id="$model-U${speed_token}-$mesh"
if [ "$sequence" = "S" ]; then
    run_id="$run_id-seqS"
fi
if [ "$solver" = "iddes" ]; then
    run_id="$run_id-iddes"
fi
if [ -n "$nchordwise" ]; then
    run_id="$run_id-nc$nchordwise"
fi
if [ "$stage0" -eq 1 ]; then
    run_id="$run_id-s0"
fi
if [ -n "$run_label" ]; then
    run_id="$run_id-$run_label"
fi
run_dir="$root/runs/$run_id"

echo "Preparing $run_id in $run_dir"
render_args=(--mesh "$mesh" --speed "$speed" --domain "$domain" --sequence "$sequence" --case-dir "$run_dir" --solver "$solver" --ranks "$ranks")
if [ -n "$nchordwise" ]; then
    render_args+=(--n-chordwise "$nchordwise")
fi
if [ -n "$n_elements" ]; then
    render_args+=(--n-elements "$n_elements")
fi
if [ -n "$rotational_augmentation" ]; then
    render_args+=(--rotational-augmentation "$rotational_augmentation")
fi
if [ -n "$root_effects" ]; then
    render_args+=(--root-effects "$root_effects")
fi
if [ -n "$tip_effects" ]; then
    render_args+=(--tip-effects "$tip_effects")
fi
if [ -n "$tip_correction" ]; then
    render_args+=(--tip-correction "$tip_correction")
fi
if [ -n "$div_phi_u" ]; then
    render_args+=(--div-phi-u "$div_phi_u")
fi
if [ -n "$polar" ]; then
    render_args+=(--polar "$polar")
fi
if [ "$stage0" -eq 1 ]; then
    render_args+=(--end-revs 0.25)
fi
if [ "$restart" -eq 1 ]; then
    written_time=""
    if [ -d "$run_dir" ]; then
        # Any positive numeric time directory, including fractional times below
        # 1 s (e.g. 0.417) that a `[1-9]*` glob would miss; `processor*/<time>`
        # directories are covered by the depth-2 search.
        written_time=$(find "$run_dir" -maxdepth 2 -type d -name '[0-9]*' \
            2>/dev/null | awk -F/ '$NF + 0 > 0 {print; exit}')
    fi
    if [ -n "$written_time" ]; then
        render_args+=(--start-from latestTime)
    else
        echo "WARNING: --restart requested but no written time exists; using startTime" >&2
    fi
fi
# shellcheck disable=SC2086
python3 "$root/tools/generate_case.py" "${render_args[@]}"

# Initial condition: the committed skeleton keeps 0.org so that `--check`
# stays clean; the run directory gets a real 0/ time directory.
rm -rf "$run_dir/0"
cp -r "$run_dir/0.org" "$run_dir/0"

case "$model" in
    alm) twin="fvOptions.ALM" ;;
    asm) twin="fvOptions.ASM" ;;
    asm-mesh) twin="fvOptions.ASM-MESH" ;;
esac
cp "$run_dir/system/$twin" "$run_dir/system/fvOptions"
echo "Installed $twin as system/fvOptions"

# The ASM-mesh twin references the imported surface case-relatively; stage the
# committed STL (sha256-checked against the geometry metadata) so the run
# directory is self-contained for restarts and relocation.
staged_stl_sha256=""
if [ "$model" = "asm-mesh" ]; then
    stl_src="$root/../../geometry/stl/phaseVI_blade.stl"
    meta="$root/../../geometry/metadata/phaseVI_blade.json"
    if ! staged_stl_sha256=$(python3 "$root/tools/stage_blade_stl.py" \
            --run-dir "$run_dir" --stl "$stl_src" --metadata "$meta"); then
        echo "ERROR: failed to stage the blade STL into $run_dir" >&2
        exit 3
    fi
    echo "Staged blade STL sha256 $staged_stl_sha256"
fi

mesh_dir="$root/runs/mesh-$mesh"
if [ "$domain" = "squat" ]; then
    mesh_dir="$mesh_dir-squat"
fi
if [ ! -d "$mesh_dir/constant/polyMesh" ]; then
    echo "Shared $mesh mesh not found; generating it"
    "$here/mesh.sh" "$mesh" --domain "$domain"
fi
rm -rf "$run_dir/constant/polyMesh"
cp -al "$mesh_dir/constant/polyMesh" "$run_dir/constant/polyMesh"
echo "Linked shared $mesh mesh from $mesh_dir"

python3 - "$run_dir" "$root" "$model" "$speed_token" "$mesh" "$domain" "$sequence" \
    "$stage0" "$solver" "$nchordwise" "$ranks" "$staged_stl_sha256" "$run_label" <<'PY'
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

(
    run_dir,
    root,
    model,
    speed,
    mesh,
    domain,
    sequence,
    stage0,
    solver,
    nchordwise,
    ranks,
    staged_stl_sha256,
    run_label,
) = sys.argv[1:14]
run_dir = Path(run_dir)
root = Path(root)


def git_commit():
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


config = root / "config" / "case.yaml"
payload = {
    "git_commit": git_commit(),
    "openfoam_version": __import__("os").environ.get("WM_PROJECT_VERSION", "unknown"),
    "config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
    "model": model,
    "wind_speed_m_s": float(speed),
    "mesh": mesh,
    "domain": domain,
    "sequence": sequence,
    "solver": solver,
    "n_chordwise": int(nchordwise) if nchordwise else None,
    "ranks": int(ranks),
    "run_label": run_label or None,
    "stage0": stage0 == "1",
    "run_dir": str(run_dir),
    "start_time_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
if model == "asm-mesh":
    # Fair-comparison input hash of the staged surface (W3.2); the comparison
    # records it in metrics.json (W3.3).
    payload["staged_stl_sha256"] = staged_stl_sha256
(run_dir / "run.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
print(f"Wrote {run_dir / 'run.json'}")
PY

if [ "$run" -eq 1 ]; then
    cd "$run_dir"
    echo "Decomposing into $ranks subdomains"
    if ! decomposePar -force > log.decomposePar 2>&1; then
        tail -30 log.decomposePar >&2
        echo "ERROR: decomposePar failed" >&2
        exit 3
    fi
    echo "Running pimpleFoam on $ranks ranks"
    # OpenMPI 4.1.4 on SDumont can segfault inside MPI_Init_thread when the ranks
    # span many nodes: the trace is
    #   MPI_Init_thread -> ompi_mpi_init -> mca_bml_base_init
    #     -> btl_openib_component_init -> btl_openib_connect_udcm
    #     -> ibv_create_comp_channel -> ibv_cmd_reg_dm_mr  (signal 11)
    # i.e. the LEGACY openib BTL, selected by the ob1 PML, races in its device-
    # memory registration. The fabric transport on this cluster is UCX, so force
    # the UCX PML and exclude the openib BTL. A 7-node, 48-rank probe (job
    # 11603591) ran all three of {baseline, pml ucx, btl ^openib} successfully,
    # which is why the failure is intermittent rather than node-count
    # deterministic -- but excluding the crashing BTL removes the possibility.
    # Override with PHASEVI_MPI_MCA (space-separated --mca flags); set it empty
    # to fall back to the site default.
    mpi_mca="${PHASEVI_MPI_MCA---mca pml ucx --mca btl ^openib}"
    # shellcheck disable=SC2086
    if ! mpirun $mpi_mca -np "$ranks" pimpleFoam -parallel > log.pimpleFoam 2>&1; then
        tail -40 log.pimpleFoam >&2
        echo "ERROR: pimpleFoam failed; inspect $run_dir/log.pimpleFoam" >&2
        exit 3
    fi
    echo "Solver finished; log: $run_dir/log.pimpleFoam"
elif [ "$submit" -eq 1 ]; then
    if [ "$stage0" -eq 1 ]; then
        echo "Submitting the Stage 0 job (development queue)"
        sbatch "$here/slurm/stage0.slurm"
    else
        if [ "${PHASEVI_LONG_QUEUE_AUTHORIZED:-0}" != "1" ]; then
            echo "ERROR: production submission is gated; export" >&2
            echo "  PHASEVI_LONG_QUEUE_AUTHORIZED=1 to submit to the long queue." >&2
            exit 5
        fi
        # Production is blocked until the 7 m/s sign gate has passed (design
        # section 6). The gate file is produced by `comparePhaseVI.py
        # --sign-gate` on the Stage 0 D/32 7 m/s runs.
        gate_file="$root/results/U7-H/sign_gate.json"
        if ! python3 - "$gate_file" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.is_file():
    raise SystemExit(1)
try:
    passed = json.loads(path.read_text(encoding="utf-8")).get("pass") is True
except ValueError:
    passed = False
raise SystemExit(0 if passed else 1)
PY
        then
            echo "ERROR: production submission is blocked without a passing" >&2
            echo "  7 m/s sign gate ($gate_file)." >&2
            echo "  Run comparePhaseVI.py --sign-gate on the Stage 0 ALM/ASM" >&2
            echo "  D/32 7 m/s runs first." >&2
            exit 5
        fi
        echo "Long-queue authorization and sign gate present; submitting the production array"
        sbatch "$here/slurm/production.slurm"
    fi
else
    suggestion="$0 -m $model -u $speed_token -mesh $mesh --sequence $sequence --solver $solver --ranks $ranks"
    if [ -n "$nchordwise" ]; then
        suggestion="$suggestion --nchordwise $nchordwise"
    fi
    if [ -n "$n_elements" ]; then
        suggestion="$suggestion --n-elements $n_elements"
    fi
    if [ -n "$run_label" ]; then
        suggestion="$suggestion --run-label $run_label"
    fi
    if [ -n "$rotational_augmentation" ]; then
        suggestion="$suggestion --rotational-augmentation $rotational_augmentation"
    fi
    if [ -n "$root_effects" ]; then
        suggestion="$suggestion --root-effects $root_effects"
    fi
    if [ -n "$tip_effects" ]; then
        suggestion="$suggestion --tip-effects $tip_effects"
    fi
    if [ -n "$tip_correction" ]; then
        suggestion="$suggestion --tip-correction $tip_correction"
    fi
    if [ -n "$div_phi_u" ]; then
        suggestion="$suggestion --div-phi-u \"$div_phi_u\""
    fi
    if [ -n "$polar" ]; then
        suggestion="$suggestion --polar $polar"
    fi
    echo "Prepared $run_id. Run the solver with:"
    echo "  $suggestion --run"
fi
