#!/bin/sh
# Run one ASM FSI smoke case: the fluid (OpenFOAM + adapter) and the mock
# structural participant concurrently.
#
# Usage:
#   run_case.sh <run-dir> [max-time]
#
# <run-dir> is a rendered + wired run directory (see wire_case.py). The mesh is
# generated here if it is missing. The fluid is launched first; the script waits
# for the sampler to write the reference cloud (coords-blade<i>.dat) before
# starting the dummy, so both register the same point cloud.
set -e -u

CASE="${1:?usage: run_case.sh <run-dir> [max-time]}"
MAXTIME="${2:-}"

HARNESS="${HARNESS:-$(cd "${0%/*}/.." && pwd)}"
DUMMY="$HARNESS/dummy-solid/solverdummy"

if [ ! -x "$DUMMY" ]; then
    echo "run_case.sh: dummy not built: $DUMMY (run dummy-solid/build.sh)" >&2
    exit 2
fi

cd "$CASE"

# ---- Mesh and initial fields ----------------------------------------------
if [ ! -d constant/polyMesh ] || [ ! -f constant/polyMesh/faces ]; then
    echo "run_case.sh: generating the mesh"
    blockMesh > log.blockMesh 2>&1
    topoSet > log.topoSet 2>&1
fi

rm -rf 0
cp -r 0.org 0

# Optional short run: cap endTime and keep the preCICE window count in sync
if [ -n "$MAXTIME" ]; then
    DT=$(sed -n 's/^deltaT \([0-9.eE+-]*\);.*/\1/p' system/controlDict)
    WINDOWS=$(awk -v t="$MAXTIME" -v dt="$DT" 'BEGIN { print int(t/dt + 0.5) }')

    sed -i "s/^endTime .*/endTime ${MAXTIME};/" system/controlDict
    sed -i "s/<max-time-windows value=\"[0-9]*\" \/>/<max-time-windows value=\"${WINDOWS}\" \/>/" precice-config.xml

    echo "run_case.sh: endTime ${MAXTIME} s = ${WINDOWS} windows (dt ${DT})"
fi

# Remove stale reference clouds so the wait below is meaningful
rm -f coords-blade*.dat

# ---- Launch the fluid -----------------------------------------------------
echo "run_case.sh: starting the fluid (pimpleFoam)"
pimpleFoam > log.pimpleFoam 2>&1 &
FLUID=$!

# ---- Wait for the reference cloud -----------------------------------------
echo "run_case.sh: waiting for the reference cloud"
i=0
while [ "$i" -lt 120 ] && [ ! -f coords-blade1.dat ]; do
    if ! kill -0 "$FLUID" 2>/dev/null; then
        echo "run_case.sh: the fluid exited before writing the reference cloud" >&2
        tail -30 log.pimpleFoam >&2
        exit 3
    fi
    sleep 5
    i=$((i + 1))
done

if [ ! -f coords-blade1.dat ]; then
    echo "run_case.sh: timed out waiting for coords-blade1.dat" >&2
    kill "$FLUID" 2>/dev/null || true
    exit 4
fi

# ---- Launch the solid -----------------------------------------------------
echo "run_case.sh: starting the dummy solid"
"$DUMMY" precice-config.xml Solid solid-meshes.dat > log.solid 2>&1 &
SOLID=$!

# ---- Wait for both --------------------------------------------------------
FLUID_STATUS=0
wait "$FLUID" || FLUID_STATUS=$?
wait "$SOLID" || true

echo "run_case.sh: fluid exit=$FLUID_STATUS"
echo "run_case.sh: last fluid lines:"
tail -12 log.pimpleFoam || true
echo "run_case.sh: last solid lines:"
tail -12 log.solid || true

exit "$FLUID_STATUS"
