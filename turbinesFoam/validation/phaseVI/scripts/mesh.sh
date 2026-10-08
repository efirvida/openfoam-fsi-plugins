#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Generate and validate one Phase VI mesh.
#
# Usage: mesh.sh <coarse|fine|ultra> [--domain long|squat] [--speed 7]
#                [--refine-level N] [--dir DIR]
#
# The case skeleton is rendered into runs/mesh-<mesh>[-r<N>][-<domain>]/, where
# the level suffix appears above 0, and meshed with blockMesh, snappyHexMesh
# (level > 0 only), topoSet and checkMesh. The directory name carries the
# refinement level on purpose: without it a level-3 run would find the level-0
# mesh, checkMesh would report "Mesh OK" because it is a valid mesh, and the run
# would silently use the wrong one.
#
# The order matters: snappyHexMesh rewrites polyMesh, so topoSet runs after it or
# the cellSet it created would be lost.
#
# Exit codes:
#   0  mesh generated and accepted
#   2  unsupported argument
#   3  blockMesh/checkMesh failed or the mesh is outside the accepted band
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$here/.." && pwd)

usage() {
    sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
}

mesh=""
domain=long
speed=7
dir=""
refine_level=0
while [ $# -gt 0 ]; do
    case "$1" in
        coarse|fine|ultra) mesh="$1" ;;
        --domain) domain="$2"; shift ;;
        --speed) speed="$2"; shift ;;
        --refine-level) refine_level="$2"; shift ;;
        --dir) dir="$2"; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "ERROR: unsupported argument: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

if [ -z "$mesh" ]; then
    echo "ERROR: mesh resolution required (coarse|fine|ultra)" >&2
    usage >&2
    exit 2
fi
case "$domain" in
    long|squat) ;;
    *) echo "ERROR: unsupported domain: $domain" >&2; exit 2 ;;
esac
case "$refine_level" in
    ''|*[!0-9]*) echo "ERROR: --refine-level takes a non-negative integer" >&2; exit 2 ;;
esac

if [ -z "$dir" ]; then
    # Level 0 keeps the historical name; above it the level is appended so two
    # levels can never share a directory and borrow each other's mesh.
    dir="$root/runs/mesh-$mesh"
    if [ "$refine_level" -gt 0 ]; then
        dir="$dir-r$refine_level"
    fi
    if [ "$domain" = "squat" ]; then
        dir="$dir-squat"
    fi
fi

echo "Rendering $mesh case ($domain domain, refinement level $refine_level) into $dir"
python3 "$root/tools/generate_case.py" \
    --mesh "$mesh" --speed "$speed" --domain "$domain" \
    --refine-level "$refine_level" --case-dir "$dir"

cd "$dir"

built=0
if [ -d constant/polyMesh ] && grep -q "Mesh OK" log.checkMesh 2>/dev/null; then
    echo "Existing mesh found in $dir; skipping blockMesh and re-validating"
else
    built=1
    if ! blockMesh > log.blockMesh 2>&1; then
        cat log.blockMesh >&2
        echo "ERROR: blockMesh failed ($dir)" >&2
        exit 3
    fi
    if [ "$refine_level" -gt 0 ]; then
        echo "Refining the rotor-disk cylinder at level $refine_level"
        if ! snappyHexMesh -overwrite > log.snappyHexMesh 2>&1; then
            tail -40 log.snappyHexMesh >&2
            echo "ERROR: snappyHexMesh failed ($dir)" >&2
            exit 3
        fi
    fi
fi
# topoSet runs after snappyHexMesh: `-overwrite` rewrites polyMesh, so a cellSet
# created before it would be gone and fvOptions' `selectionMode cellSet` would
# silently select nothing.
if [ "$built" -eq 1 ] || [ ! -f log.topoSet ] || [ system/topoSetDict -nt log.topoSet ]; then
    if [ "$built" -eq 0 ]; then
        echo "topoSetDict changed since the last topoSet run; refreshing the cellSet"
    fi
    if ! topoSet > log.topoSet 2>&1; then
        cat log.topoSet >&2
        echo "ERROR: topoSet failed ($dir)" >&2
        exit 3
    fi
fi
if ! checkMesh > log.checkMesh 2>&1; then
    cat log.checkMesh >&2
    echo "ERROR: checkMesh failed ($dir)" >&2
    exit 3
fi

grep -q "Mesh OK" log.checkMesh || {
    echo "ERROR: checkMesh did not report 'Mesh OK' ($dir)" >&2
    exit 3
}

cells=$(awk '/cells:/ {print $2; exit}' log.checkMesh)
hexes=$(awk '/hexahedra:/ {print $2; exit}' log.checkMesh)
polyhedra=$(awk '/polyhedra:/ {print $2; exit}' log.checkMesh)
nonortho=$(awk '/Mesh non-orthogonality Max:/ {print $4; exit}' log.checkMesh)

if [ -z "$cells" ] || [ -z "$hexes" ] || [ -z "$polyhedra" ] || [ -z "$nonortho" ]; then
    echo "ERROR: could not read the mesh statistics from $dir/log.checkMesh" >&2
    exit 3
fi
if [ "$refine_level" -eq 0 ]; then
    # The base blockMesh is pure hexahedral by construction, so the strict rule
    # still holds where it can.
    if [ "$hexes" != "$cells" ] || [ "$polyhedra" != "0" ]; then
        echo "ERROR: mesh is not 100% hexahedral ($hexes/$cells hexes, $polyhedra polyhedra)" >&2
        exit 3
    fi
else
    # snappyHexMesh castellated always creates polyhedral transition cells at the
    # refinement boundaries: 5,832 at level 1 and 29,320 at level 2, i.e. 0.09 %
    # and 0.36 % of the mesh, and checkMesh accepts both. Requiring pure hex here
    # rejected meshes OpenFOAM solves on happily. The bound below is a sanity limit
    # against a mesh that is mostly polyhedra, not a quality claim.
    if ! awk -v hexes="$hexes" -v cells="$cells" 'BEGIN { exit !(hexes >= 0.99 * cells) }'; then
        echo "ERROR: refined mesh is only $hexes/$cells hexahedral" >&2
        exit 3
    fi
    echo "Refined level $refine_level: $hexes/$cells hexahedra, $polyhedra polyhedral transition cells"
fi
if ! awk -v value="$nonortho" 'BEGIN { exit !(value <= 1e-10) }'; then
    echo "ERROR: max non-orthogonality $nonortho exceeds the Cartesian tolerance" >&2
    exit 3
fi

band=$(python3 "$root/tools/case_config.py" --target-cells "$mesh")
low=${band% *}
high=${band#* }
if [ "$refine_level" -gt 0 ]; then
    # Refinement cannot shrink the mesh, so the lower bound is real. The upper
    # bound stays open until the first build of each level reports its count,
    # which is printed here for the record.
    if [ "$cells" -lt "$low" ]; then
        echo "ERROR: refined mesh has $cells cells, below the base band $low..$high" >&2
        exit 3
    fi
    echo "Refined level $refine_level: $cells cells (base band $low..$high, upper"
    echo "bound pending the first measured build of this level)"
else
    if [ "$cells" -lt "$low" ] || [ "$cells" -gt "$high" ]; then
        echo "ERROR: $cells cells is outside the configured band $low..$high" >&2
        exit 3
    fi
fi

echo "Mesh accepted: $cells cells, $hexes hexahedra, max non-orthogonality $nonortho"
