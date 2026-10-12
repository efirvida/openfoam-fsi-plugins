#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Run several independent commands ("steps") concurrently inside ONE Slurm
# allocation, one step per node, and report the exit code of each.
#
# Why: the account runs a few jobs at once, so a campaign of N cases is cheaper
# on the queue as one job with N parallel steps than as N jobs. One step is one
# node on purpose: multi-node MPI_Init failed intermittently on this cluster
# (phaseVI/campaign-results/RESULTS.md, operational notes), so a step never
# spans nodes.
#
# Usage (inside an sbatch script that allocated --nodes=N):
#
#   run_parallel_steps.sh [-n RANKS] -- CMD1 -- CMD2 -- CMD3 ...
#
# Each CMD is run through `bash -c` with these variables set:
#   STEP_INDEX   0-based position of the step
#   STEP_NODE    the node it is confined to
#   STEP_RANKS   ranks per step (default: SLURM_CPUS_ON_NODE or 48)
#   TURBINE_MPI_MCA  "--host $STEP_NODE:$STEP_RANKS --map-by ppr:$STEP_RANKS:node -mca pml
#                    ucx --mca btl ^openib", the flags the runners pass to
#                    mpirun (run_iea15mw_case.sh reads this variable), so a step
#                    that calls mpirun stays on its own node
# Exit status: 0 when every step returned 0, otherwise the number of failed
# steps. More steps than nodes is an error (a step would share a node).

set -u

ranks="${SLURM_CPUS_ON_NODE:-48}"
if [ "${1:-}" = "-n" ]; then
    ranks="$2"
    shift 2
fi
if [ "${1:-}" != "--" ]; then
    echo "usage: $0 [-n RANKS] -- CMD1 -- CMD2 ..." >&2
    exit 2
fi

# Split the arguments at each `--` into one command string per step.
cmds=()
current=""
shift
for arg in "$@"; do
    if [ "$arg" = "--" ]; then
        cmds+=("$current")
        current=""
    else
        current="${current:+$current }$arg"
    fi
done
cmds+=("$current")

if [ -z "${SLURM_JOB_NODELIST:-}" ]; then
    echo "ERROR: run inside a Slurm allocation (SLURM_JOB_NODELIST is empty)" >&2
    exit 2
fi
mapfile -t nodes < <(scontrol show hostnames "$SLURM_JOB_NODELIST")
if [ "${#cmds[@]}" -gt "${#nodes[@]}" ]; then
    echo "ERROR: ${#cmds[@]} steps but only ${#nodes[@]} nodes allocated" >&2
    exit 2
fi

pids=()
for i in "${!cmds[@]}"; do
    node="${nodes[$i]}"
    mca="--host ${node}:${ranks} --map-by ppr:${ranks}:node -mca pml ucx --mca btl ^openib"
    echo "step ${i}: node ${node}, ${ranks} ranks: ${cmds[$i]}"
    STEP_INDEX="$i" STEP_NODE="$node" STEP_RANKS="$ranks" TURBINE_MPI_MCA="$mca" \
        bash -c "${cmds[$i]}" &
    pids+=("$!")
done

failed=0
for i in "${!pids[@]}"; do
    if wait "${pids[$i]}"; then
        echo "step ${i}: rc=0"
    else
        rc=$?
        echo "step ${i}: rc=${rc}"
        failed=$((failed + 1))
    fi
done
exit "$failed"
