"""Contracts for the Phase VI mesh pipeline.

The refinement ladder meshes one shared directory per (`mesh`, `domain`,
refinement level). These tests pin the properties that, if they broke, would make
a convergence run silently use the wrong mesh rather than fail.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
TURBINESFOAM = TESTS_DIR.parent
PACKAGE = TURBINESFOAM / "validation" / "phaseVI"
MESH_SH = PACKAGE / "scripts" / "mesh.sh"
RUNNER = PACKAGE / "scripts" / "runPhaseVI.sh"


def test_mesh_directory_encodes_the_refinement_level():
    """The shared mesh directory must carry the refinement level.

    Without it a level-3 run finds the level-0 mesh, `mesh.sh` takes its re-use
    path and `checkMesh` reports "Mesh OK" because it *is* a valid mesh. The run
    then uses the wrong mesh and nothing anywhere says so. Level 0 keeps the
    historical name; above it the level is appended, which makes the collision
    impossible rather than merely unlikely.
    """
    mesh = MESH_SH.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    for script in (mesh, runner):
        assert 'mesh-$mesh' in script
        assert 'if [ "$refine_level" -gt 0 ]; then' in script
        assert '-r$refine_level' in script
        assert "--refine-level" in script
    assert "--delta-t" in runner


def test_snappy_runs_before_toposet():
    """Order matters: `snappyHexMesh -overwrite` rewrites polyMesh.

    A cellSet created before it would be lost, and fvOptions selects its cells
    with `selectionMode cellSet`, so the actuator line would silently act on
    nothing.
    """
    mesh = MESH_SH.read_text(encoding="utf-8")
    assert "snappyHexMesh -overwrite" in mesh
    assert mesh.index("snappyHexMesh -overwrite") < mesh.index("topoSet > log.topoSet")


def test_level_0_is_the_base_block_mesh():
    """Level 0 must not invoke snappy at all."""
    mesh = MESH_SH.read_text(encoding="utf-8")
    assert 'if [ "$refine_level" -gt 0 ]; then\n        echo "Refining' in mesh


def test_invalid_levels_and_steps_are_refused_before_any_render():
    """A bad level or step exits 2 during validation, not halfway through meshing."""
    rejected = (
        ["sh", str(MESH_SH), "coarse", "--refine-level", "x"],
        ["sh", str(MESH_SH), "coarse", "--refine-level", "-1"],
        ["sh", str(RUNNER), "-m", "alm", "-u", "7", "--refine-level", "-1"],
        ["sh", str(RUNNER), "-m", "alm", "-u", "7", "--delta-t", "0"],
    )
    for command in rejected:
        result = subprocess.run(command, capture_output=True, text=True)
        assert result.returncode == 2, (
            f"{command} returned {result.returncode}: "
            f"{result.stdout}{result.stderr}"
        )
