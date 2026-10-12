#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Smoke test of run_parallel_steps.sh: two 48-rank MPI steps, one node each,
# running at the same time inside one allocation on the development partition.
#
#   cd turbinesFoam/validation/tools && sbatch parallel_steps_smoke.slurm
#
# Passes when both steps return 0, every rank of a step reports the node the
# step was confined to, and the two steps ran at overlapping times.
#SBATCH -p sequana_cpu_dev
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=48
#SBATCH --time=00:10:00
#SBATCH --no-requeue
#SBATCH -J parallel-steps-smoke
#SBATCH -e %j.err
#SBATCH -o %j.out

set -u
here="${SLURM_SUBMIT_DIR:-$PWD}"
module purge
module load openfoam/v2506_openmpi-4.1.4_gnu

work="${TMPDIR:-/tmp}/parallel-steps-smoke.$$"
mkdir -p "$work"
cat > "$work/mpi_smoke.c" <<'CSRC'
#include <mpi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

/* MPI_Init, a collective over the step, and a check that every rank sits on the
   node the launcher assigned. Rank 0 prints one summary line. */
int main(int argc, char** argv)
{
    MPI_Init(&argc, &argv);
    int rank, size;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &size);
    char host[256];
    gethostname(host, sizeof host);
    const char* want = getenv("STEP_NODE");
    int onNode = (want != NULL && strncmp(host, want, strlen(want)) == 0);
    int nOnNode = 0;
    MPI_Allreduce(&onNode, &nOnNode, 1, MPI_INT, MPI_SUM, MPI_COMM_WORLD);
    time_t t0 = time(NULL);
    for (int i = 0; i < 8; i++)
    {
        MPI_Barrier(MPI_COMM_WORLD);
        sleep(2);
    }
    time_t t1 = time(NULL);
    if (rank == 0)
    {
        printf("SMOKE step=%s node=%s ranks=%d onNode=%d start=%ld end=%ld\n",
               getenv("STEP_INDEX"), host, size, nOnNode, (long)t0, (long)t1);
    }
    MPI_Finalize();
    return (nOnNode == size) ? 0 : 1;
}
CSRC
mpicc -O1 -o "$work/mpi_smoke" "$work/mpi_smoke.c" || exit 3

step='mpirun $TURBINE_MPI_MCA -np $STEP_RANKS '"$work"'/mpi_smoke'
bash "$here/run_parallel_steps.sh" -n 48 -- "$step" -- "$step" | tee "$work/out.txt"
rc=${PIPESTATUS[0]}

# Overlap: the later start must precede the earlier end.
python3 - "$work/out.txt" <<'PY'
import re
import sys

rows = [
    tuple(int(x) for x in re.search(r"start=(\d+) end=(\d+)", line).groups())
    for line in open(sys.argv[1])
    if line.startswith("SMOKE")
]
ok = len(rows) == 2 and max(r[0] for r in rows) < min(r[1] for r in rows)
print("OVERLAP", "yes" if ok else "NO", rows)
sys.exit(0 if ok else 1)
PY
overlap=$?
echo "=== smoke rc=${rc} overlap_rc=${overlap} ==="
rm -rf "$work"
exit $((rc + overlap))
