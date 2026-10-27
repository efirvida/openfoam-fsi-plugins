# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure-Python contracts for the NREL Phase VI validation case package.

These tests never require OpenFOAM: they exercise the YAML single source of
truth, the derived mesh arithmetic and the rendered dictionaries in memory
(spec requirements V1-V11, design sections 4-6).
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

TESTS_DIR = Path(__file__).resolve().parent
TURBINESFOAM = TESTS_DIR.parent
PACKAGE = TURBINESFOAM / "validation" / "phaseVI"
sys.path.insert(0, str(PACKAGE / "tools"))

import generate_case  # noqa: E402
from case_config import (  # noqa: E402
    assert_tip_constraint,
    assert_tsr_matches_experiment,
    cell_count,
    hub_cell_size,
    kinematics,
    load_config,
    select_speed,
    solver_delta_t,
    speed_keys,
    tip_displacement,
    tsr_from_rpm,
    validate_config,
)
from element_data import (  # noqa: E402
    HUB_DIAMETER,
    blade_element_rows,
    hub_element_rows,
)

CONFIG = PACKAGE / "config" / "case.yaml"
EXPECTED_CELLS = {
    "coarse": 6_674_304,
    "fine": 22_525_776,
    "ultra": 53_394_432,
}
EXPECTED_HUB_CELL = {"coarse": 0.3143, "fine": 0.2095, "ultra": 0.1572}
FROZEN_TSR = {
    "7": 5.408,
    "10": 3.798,
    "13": 2.920,
    "15": 2.530,
    "20": 1.898,
    "25": 1.521,
}
#: Blade-subdictionary keys the three twins are allowed to differ in. `kernel`
#: is rendered only for the Gaussian ablation (cosine is the default and the
#: key is absent); `surfaceGeometry` is rendered for the mesh-backed variant.
BLADE_KEYS = ("elementType", "nChordwise", "surfaceGeometry", "kernel")


@pytest.fixture(scope="module")
def cfg():
    return load_config(CONFIG)


def test_config_schema(cfg):
    assert cfg["project"]["openfoam_versions"] == ["v2506", "v2412"]
    turbine = cfg["turbine"]
    assert turbine["n_blades"] == 2
    assert turbine["pitch_deg"] == 3.0
    assert turbine["diameter"] == 2.0 * turbine["radius"]
    assert turbine["hub_height"] == 12.192
    assert speed_keys(cfg) == ["5", "7", "10", "13", "15", "20", "25"]  # 5 m/s: P2.3 T13
    assert cfg["solver"]["application"] == "pimpleFoam"
    assert cfg["solver"]["turbulence_model"] == "kOmegaSST"
    assert cfg["solver"]["adjust_time_step"] is False
    solver = cfg["solver"]
    assert (solver["discard_revolutions"], solver["end_revolutions"]) == (4, 12)
    # Rotational augmentation: committed default off, paper constants only.
    augmentation = cfg["actuator"]["rotational_augmentation"]
    assert augmentation["active"] is False
    assert augmentation["model"] == "DuSelig"
    assert (augmentation["a"], augmentation["b"], augmentation["d"]) == (1, 1, 1)
    assert isinstance(cfg["actuator"]["end_effects"]["root"], bool)


def test_mesh_arithmetic_and_cell_counts(cfg):
    for mesh, expected in EXPECTED_CELLS.items():
        assert cell_count(cfg, mesh) == expected
        low, high = cfg["mesh"]["resolutions"][mesh]["target_cells"]
        assert low <= expected <= high
        assert hub_cell_size(cfg, mesh) == pytest.approx(
            EXPECTED_HUB_CELL[mesh], abs=5e-4
        )


def test_block_mesh_dict_18_hex_blocks(cfg):
    pattern = re.compile(
        r"^\s+hex \(([^)]*)\) \((\d+) (\d+) (\d+)\) simpleGrading \(",
        re.MULTILINE,
    )
    for mesh in EXPECTED_CELLS:
        text = generate_case.render_block_mesh(cfg, mesh, "long", "production")
        blocks = pattern.findall(text)
        assert len(blocks) == 18, f"{mesh}: expected 18 blocks"
        assert "poly" not in text
        total = sum(int(nx) * int(ny) * int(nz) for _, nx, ny, nz in blocks)
        assert total == EXPECTED_CELLS[mesh]
        for name in ("inlet", "outlet", "bottom", "top", "sideMinus", "sidePlus"):
            assert f"    {name}\n" in text
        assert text.count("type symmetryPlane;") == 4
        assert text.count("type patch;") == 2
    squat = generate_case.render_block_mesh(cfg, "coarse", "squat", "production")
    assert len(pattern.findall(squat)) == 18


def test_fallback_domain_extents(cfg):
    from case_config import axis_extents_D

    diameter = cfg["turbine"]["diameter"]
    hub = cfg["turbine"]["hub_height"]
    long_x = axis_extents_D(cfg, "x", "long")
    long_y = axis_extents_D(cfg, "y", "long")
    long_z = axis_extents_D(cfg, "z", "long")
    assert (long_x[0], long_x[-1]) == (-5.0 * diameter, 15.0 * diameter)
    assert (long_y[0], long_y[-1]) == (-4.0 * diameter, 4.0 * diameter)
    assert (long_z[0], long_z[-1]) == (hub - 2.5 * diameter, hub + 2.5 * diameter)

    squat_x = axis_extents_D(cfg, "x", "squat")
    squat_y = axis_extents_D(cfg, "y", "squat")
    squat_z = axis_extents_D(cfg, "z", "squat")
    assert (squat_x[0], squat_x[-1]) == (-5.0 * diameter, 10.0 * diameter)
    assert (squat_y[0], squat_y[-1]) == (-3.0 * diameter, 3.0 * diameter)
    assert (squat_z[0], squat_z[-1]) == (hub - 3.0 * diameter, hub + 3.0 * diameter)
    assert cell_count(cfg, "coarse", "squat") == EXPECTED_CELLS["coarse"]


def test_control_dict_fixed_time_step(cfg):
    for mesh, delta_t in (("coarse", 0.008), ("fine", 0.005), ("ultra", 0.004)):
        text = generate_case.render_control_dict(
            cfg, "7", mesh, "production", None, "startTime"
        )
        assert f"deltaT {delta_t:.8g};" in text
        assert "adjustTimeStep off;" in text
        values = kinematics(cfg, "7", mesh)
        assert f"endTime {values['end_time']:.8g};" in text
        assert values["end_time"] == pytest.approx(
            12.0 * values["t_rev"], rel=1e-12
        )


def block(text: str, header: str) -> str:
    """The `{ ... }` block that starts at `header` (balanced braces)."""
    start = text.index(header)
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise AssertionError(f"unterminated block {header!r}")


def test_twins_differ_only_in_blade_keys(cfg):
    case_dir = PACKAGE / "case"

    def render(element_type, **surface):
        return generate_case.render_fv_options(
            cfg, "7", "coarse", case_dir, element_type, **surface
        )

    alm = render(generate_case.ALM_ELEMENT)
    asm = render(generate_case.ASM_ELEMENT)
    asm_mesh = render(
        generate_case.ASM_ELEMENT,
        surface_geometry=generate_case.SURFACE_GEOMETRY,
    )
    gaussian = render(
        generate_case.ASM_ELEMENT,
        surface_geometry=generate_case.SURFACE_GEOMETRY,
        surface_kernel="gaussian",
    )
    assert "elementType actuatorLineElement;" in alm
    assert "elementType actuatorSurfaceElement;" in asm
    assert "nChordwise 5;" in asm
    assert "nChordwise" not in alm
    assert (
        f'surfaceGeometry "{generate_case.SURFACE_GEOMETRY}";' in asm_mesh
    )
    # Cosine is the default: the ablation key is absent unless selected.
    assert "kernel" not in asm_mesh
    assert "kernel gaussian;" in gaussian
    assert "surfaceGeometry" in block(asm_mesh, "blade1")
    # blade2 is `$blade1;` + azimuthalOffset 180, so the surface keys
    # propagate to both identical blades without a second render.
    assert "$blade1;" in block(asm_mesh, "blade2")

    def stripped(text):
        return [
            line
            for line in text.splitlines()
            if not any(key in line for key in BLADE_KEYS)
        ]

    assert stripped(alm) == stripped(asm) == stripped(asm_mesh) == stripped(gaussian)

    committed = {
        name: (case_dir / "system" / f"fvOptions.{name}").read_text()
        for name in ("ALM", "ASM", "ASM-MESH")
    }
    assert stripped(committed["ALM"]) == stripped(committed["ASM"])
    assert stripped(committed["ASM"]) == stripped(committed["ASM-MESH"])
    assert "elementType actuatorLineElement;" in committed["ALM"]
    assert "nChordwise 5;" in committed["ASM"]
    assert (
        f'surfaceGeometry "{generate_case.SURFACE_GEOMETRY}";'
        in committed["ASM-MESH"]
    )
    assert "surfaceGeometry" in block(committed["ASM-MESH"], "blade1")
    assert "$blade1;" in block(committed["ASM-MESH"], "blade2")

    # The augmentation block is present and identical in every twin and every
    # committed file: it is not a blade key, so stripping the blade keys must
    # leave it untouched and identical.
    augmentation_blocks = {
        block(text, "rotationalAugmentation")
        for text in (alm, asm, asm_mesh, gaussian)
    }
    assert len(augmentation_blocks) == 1
    assert "active off;" in augmentation_blocks.pop()
    committed_augmentation = {
        block(text, "rotationalAugmentation") for text in committed.values()
    }
    assert len(committed_augmentation) == 1


def test_rotational_augmentation_rendered(cfg, tmp_path):
    """The switch renders on/off identically across the twins; default off."""
    constants = {"active": True, "model": "DuSelig", "a": 1, "b": 1, "d": 1}

    def render(element_type, **kwargs):
        return generate_case.render_fv_options(
            cfg,
            "7",
            "coarse",
            PACKAGE / "case",
            element_type,
            rotational_augmentation=constants,
            **kwargs,
        )

    alm = block(render(generate_case.ALM_ELEMENT), "rotationalAugmentation")
    asm = block(render(generate_case.ASM_ELEMENT), "rotationalAugmentation")
    asm_mesh = block(
        render(
            generate_case.ASM_ELEMENT,
            surface_geometry=generate_case.SURFACE_GEOMETRY,
        ),
        "rotationalAugmentation",
    )
    assert alm == asm == asm_mesh
    for key in ("active on;", "model DuSelig;", "a 1;", "b 1;", "d 1;"):
        assert key in alm

    # The block must sit at the rotor-coeffs level (mirroring `dynamicStall`),
    # never inside a blade subdict: only the rotor-level block is forwarded by
    # AFTAL together with `rotorRadius`/`rootRadius`, so a blade-level block
    # makes the element skip the correction (the proxy matrix caught this).
    coeffs = block(
        render(generate_case.ALM_ELEMENT), "axialFlowTurbineALSourceCoeffs"
    )
    assert "rotationalAugmentation" in coeffs
    assert "rotationalAugmentation" not in block(coeffs, "blade1")

    # The committed default renders the same block with the switch off.
    committed = (PACKAGE / "case" / "system" / "fvOptions.ALM").read_text()
    default = block(committed, "rotationalAugmentation")
    assert "active off;" in default
    assert "model DuSelig;" in default
    for key in ("a 1;", "b 1;", "d 1;"):
        assert key in default

    # The CLI toggle reaches every rendered twin.
    case_dir = tmp_path / "case"
    result = subprocess.run(
        [
            sys.executable,
            str(PACKAGE / "tools" / "generate_case.py"),
            "--rotational-augmentation", "on",
            "--case-dir", str(case_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    for name in ("ALM", "ASM", "ASM-MESH"):
        rendered = (case_dir / "system" / f"fvOptions.{name}").read_text()
        assert "active on;" in block(rendered, "rotationalAugmentation")


def test_rotational_augmentation_yaml_governs_and_flag_overrides(cfg, tmp_path):
    """The YAML `active` value drives the render; the CLI flag overrides it.

    Mirrors the `--root-effects` contract: an absent flag leaves the YAML value
    (`config/case.yaml`) in charge; a present flag wins in both directions.
    """
    def run(config, *flags, tag):
        case_dir = tmp_path / tag
        result = subprocess.run(
            [
                sys.executable,
                str(PACKAGE / "tools" / "generate_case.py"),
                "--config", str(config),
                *flags,
                "--case-dir", str(case_dir),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        blocks = {
            name: block(
                (case_dir / "system" / f"fvOptions.{name}").read_text(),
                "rotationalAugmentation",
            )
            for name in ("ALM", "ASM", "ASM-MESH")
        }
        return blocks

    def yaml_with(active):
        variant = copy.deepcopy(cfg)
        variant["actuator"]["rotational_augmentation"]["active"] = active
        path = tmp_path / f"case-active-{active}.yaml"
        path.write_text(yaml.safe_dump(variant, sort_keys=False))
        return path

    # YAML active: true, no CLI flag -> the switch renders on in every twin.
    for twin, text in run(yaml_with(True), tag="yaml-on").items():
        assert "active on;" in text, twin

    # YAML active: false, no CLI flag -> unchanged default (off).
    for twin, text in run(yaml_with(False), tag="yaml-off").items():
        assert "active off;" in text, twin

    # The flag overrides the YAML in both directions.
    for twin, text in run(
        yaml_with(True), "--rotational-augmentation", "off", tag="flag-off"
    ).items():
        assert "active off;" in text, twin
    for twin, text in run(
        yaml_with(False), "--rotational-augmentation", "on", tag="flag-on"
    ).items():
        assert "active on;" in text, twin


def test_runner_lets_yaml_govern_rotational_augmentation(tmp_path):
    """The runner forces no augmentation value; the YAML governs.

    `--rotational-augmentation` is forwarded only when requested. With the YAML
    set to `true`, a prepare-only run renders `active on;`; an explicit
    `--rotational-augmentation off` overrides it; an invalid value is rejected
    before any render. The same runner contract forwards `--root-effects off`
    (the augmented candidate `--rotational-augmentation on --root-effects off`)
    to the renderer.
    """
    sandbox = tmp_path / "sandbox"
    package = sandbox / "validation" / "phaseVI"
    package.parent.mkdir(parents=True)
    shutil.copytree(
        PACKAGE,
        package,
        ignore=shutil.ignore_patterns(
            "runs", "results", "polyMesh", "__pycache__"
        ),
    )
    (sandbox / "geometry").symlink_to(TURBINESFOAM / "geometry")
    environment = package / "scripts" / "check_environment.sh"
    environment.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    environment.chmod(0o755)
    mesh = package / "runs" / "mesh-coarse" / "constant" / "polyMesh"
    mesh.mkdir(parents=True)
    (mesh / ".keep").write_text("", encoding="utf-8")

    # The sandbox YAML drives the render through the runner.
    config = package / "config" / "case.yaml"
    variant = yaml.safe_load(config.read_text(encoding="utf-8"))
    variant["actuator"]["rotational_augmentation"]["active"] = True
    config.write_text(yaml.safe_dump(variant, sort_keys=False), encoding="utf-8")

    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "python3").symlink_to(sys.executable)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("SLURM_")
    }
    env["PATH"] = str(shim) + os.pathsep + env.get("PATH", "")

    def prepare(*flags):
        return subprocess.run(
            [
                "sh", str(package / "scripts" / "runPhaseVI.sh"),
                "-m", "alm", "-u", "7", "-mesh", "coarse",
                *flags,
            ],
            cwd=package,
            capture_output=True,
            text=True,
            env=env,
        )

    prepared = prepare()
    assert prepared.returncode == 0, prepared.stderr
    run_dir = package / "runs" / "alm-U7-coarse"
    rendered = (run_dir / "system" / "fvOptions").read_text(encoding="utf-8")
    assert "active on;" in block(rendered, "rotationalAugmentation")

    # An explicit flag overrides the YAML.
    overridden = prepare("--rotational-augmentation", "off")
    assert overridden.returncode == 0, overridden.stderr
    rendered = (run_dir / "system" / "fvOptions").read_text(encoding="utf-8")
    assert "active off;" in block(rendered, "rotationalAugmentation")

    # An invalid value is rejected before any render.
    rejected = prepare("--rotational-augmentation", "bogus")
    assert rejected.returncode == 2
    assert "on or off" in rejected.stderr

    # `--root-effects off` is forwarded to the renderer (the augmented
    # candidate); an invalid value is rejected before any render.
    root_off = prepare("--root-effects", "off")
    assert root_off.returncode == 0, root_off.stderr
    rendered = (run_dir / "system" / "fvOptions").read_text(encoding="utf-8")
    assert "rootEffects off;" in block(rendered, "GlauertCoeffs")
    bad_root = prepare("--root-effects", "bogus")
    assert bad_root.returncode == 2
    assert "on or off" in bad_root.stderr


def test_runner_run_label_isolates_arms(tmp_path):
    """`--run-label` gives each render variant its own restartable run dir.

    The two-arm campaign runs the same (model, speed, mesh) with a different
    augmentation/root setting per arm; without the label both arms render into
    the same `runs/<id>` directory and `--restart` would continue from the other
    arm's physics. The label is appended to the run id and recorded in run.json.
    """
    sandbox = tmp_path / "sandbox"
    package = sandbox / "validation" / "phaseVI"
    package.parent.mkdir(parents=True)
    shutil.copytree(
        PACKAGE,
        package,
        ignore=shutil.ignore_patterns("runs", "results", "polyMesh", "__pycache__"),
    )
    (sandbox / "geometry").symlink_to(TURBINESFOAM / "geometry")
    environment = package / "scripts" / "check_environment.sh"
    environment.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    environment.chmod(0o755)
    mesh = package / "runs" / "mesh-coarse" / "constant" / "polyMesh"
    mesh.mkdir(parents=True)
    (mesh / ".keep").write_text("", encoding="utf-8")

    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "python3").symlink_to(sys.executable)
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("SLURM_")
    }
    env["PATH"] = str(shim) + os.pathsep + env.get("PATH", "")

    def prepare(*flags):
        return subprocess.run(
            [
                "sh", str(package / "scripts" / "runPhaseVI.sh"),
                "-m", "alm", "-u", "7", "-mesh", "coarse",
                *flags,
            ],
            cwd=package,
            capture_output=True,
            text=True,
            env=env,
        )

    arm_a = prepare(
        "--rotational-augmentation", "on", "--root-effects", "off",
        "--run-label", "aug-on-root-off",
    )
    assert arm_a.returncode == 0, arm_a.stderr
    arm_b = prepare(
        "--rotational-augmentation", "on", "--root-effects", "on",
        "--run-label", "aug-on-root-on",
    )
    assert arm_b.returncode == 0, arm_b.stderr

    dir_a = package / "runs" / "alm-U7-coarse-aug-on-root-off"
    dir_b = package / "runs" / "alm-U7-coarse-aug-on-root-on"
    assert dir_a.is_dir() and dir_b.is_dir()
    # The two arms do not alias each other; each records its own label.
    assert (
        json.loads((dir_a / "run.json").read_text(encoding="utf-8"))["run_label"]
        == "aug-on-root-off"
    )
    assert (
        json.loads((dir_b / "run.json").read_text(encoding="utf-8"))["run_label"]
        == "aug-on-root-on"
    )
    assert "rootEffects off;" in block(
        (dir_a / "system" / "fvOptions").read_text(encoding="utf-8"), "GlauertCoeffs"
    )
    assert "rootEffects on;" in block(
        (dir_b / "system" / "fvOptions").read_text(encoding="utf-8"), "GlauertCoeffs"
    )

    # A path-unsafe label is rejected before any render.
    bad = prepare("--run-label", "bad/slash")
    assert bad.returncode == 2
    assert "run-label" in bad.stderr


def test_root_effect_ablation_rendered(cfg, tmp_path):
    """The root-effect ablation is render-time; the committed default keeps on (v1.3 too)."""
    committed = (PACKAGE / "case" / "system" / "fvOptions.ALM").read_text()
    assert "rootEffects on;" in block(committed, "GlauertCoeffs")

    ablation = generate_case.render_fv_options(
        cfg,
        "7",
        "coarse",
        PACKAGE / "case",
        generate_case.ALM_ELEMENT,
        root_effects=False,
    )
    assert "rootEffects off;" in block(ablation, "GlauertCoeffs")
    assert "rootEffects on;" not in ablation
    # The tip effect is not part of the ablation (v1.3: the Glauert tip factor is off).
    assert "tipEffects off;" in ablation

    case_dir = tmp_path / "case"
    result = subprocess.run(
        [
            sys.executable,
            str(PACKAGE / "tools" / "generate_case.py"),
            "--root-effects", "off",
            "--case-dir", str(case_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    rendered = (case_dir / "system" / "fvOptions.ALM").read_text()
    assert "rootEffects off;" in block(rendered, "GlauertCoeffs")


def test_tip_effect_ablation_rendered(cfg, tmp_path):
    """The Glauert tip factor toggles at render time; the committed default is off (v1.3)."""
    committed = (PACKAGE / "case" / "system" / "fvOptions.ALM").read_text()
    assert "tipEffects off;" in block(committed, "GlauertCoeffs")

    v12 = generate_case.render_fv_options(
        cfg,
        "7",
        "coarse",
        PACKAGE / "case",
        generate_case.ALM_ELEMENT,
        tip_effects=True,
    )
    assert "tipEffects on;" in block(v12, "GlauertCoeffs")
    assert "tipEffects off;" not in v12
    ablation = generate_case.render_fv_options(
        cfg,
        "7",
        "coarse",
        PACKAGE / "case",
        generate_case.ALM_ELEMENT,
        tip_effects=False,
    )
    assert "tipEffects off;" in block(ablation, "GlauertCoeffs")
    assert "tipEffects on;" not in ablation
    # The root effect is not part of the ablation.
    assert "rootEffects on;" in ablation

    case_dir = tmp_path / "case"
    result = subprocess.run(
        [
            sys.executable,
            str(PACKAGE / "tools" / "generate_case.py"),
            "--tip-effects", "off",
            "--case-dir", str(case_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    rendered = (case_dir / "system" / "fvOptions.ALM").read_text()
    assert "tipEffects off;" in block(rendered, "GlauertCoeffs")


def test_tip_correction_rendered(cfg, tmp_path):
    """The Dag & Sorensen tip correction renders beside `endEffects`, on (v1.3).

    Mirrors the `endEffects`/`rotationalAugmentation` contract: the committed
    YAML default is on (v1.2: off), the block always renders with the keys AFTAL reads,
    and the `--tip-correction` flag overrides the default in both directions.
    """
    def render(element_type, **kwargs):
        return generate_case.render_fv_options(
            cfg, "7", "coarse", PACKAGE / "case", element_type, **kwargs
        )

    default = block(render(generate_case.ALM_ELEMENT), "tipCorrection")
    assert default == block(render(generate_case.ASM_ELEMENT), "tipCorrection")
    assert default == block(
        render(
            generate_case.ASM_ELEMENT,
            surface_geometry=generate_case.SURFACE_GEOMETRY,
        ),
        "tipCorrection",
    )
    assert "active on;" in default
    for key in (
        "model DagSorensen;",
        "wakeTurns 2;",
        "wakeAzimuthalStep 2;",
        "epsilon 0;",
    ):
        assert key in default

    # The block sits at the rotor-coeffs level, beside `endEffects`, never
    # inside a blade subdict (AFTAL reads it from `coeffs_`).
    coeffs = block(
        render(generate_case.ALM_ELEMENT), "axialFlowTurbineALSourceCoeffs"
    )
    assert "tipCorrection" in coeffs
    assert "tipCorrection" not in block(coeffs, "blade1")

    # The committed default is `active on;`.
    committed = (PACKAGE / "case" / "system" / "fvOptions.ALM").read_text()
    assert "active on;" in block(committed, "tipCorrection")

    # The CLI toggle reaches every rendered twin.
    case_dir = tmp_path / "case-on"
    result = subprocess.run(
        [
            sys.executable,
            str(PACKAGE / "tools" / "generate_case.py"),
            "--tip-correction", "on",
            "--case-dir", str(case_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    for name in ("ALM", "ASM", "ASM-MESH"):
        rendered = (case_dir / "system" / f"fvOptions.{name}").read_text()
        assert "active on;" in block(rendered, "tipCorrection")

    # An explicit `off` restores the v1.2 setting.
    off_dir = tmp_path / "case-off"
    off = subprocess.run(
        [
            sys.executable,
            str(PACKAGE / "tools" / "generate_case.py"),
            "--tip-correction", "off",
            "--case-dir", str(off_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert off.returncode == 0, off.stderr
    for name in ("ALM", "ASM", "ASM-MESH"):
        rendered = (off_dir / "system" / f"fvOptions.{name}").read_text()
        assert "active off;" in block(rendered, "tipCorrection")


def test_validated_sampling_and_re_correction_render_at_the_source_levels(cfg):
    """The validated Phase VI method renders where the C++ reads it.

    `velocitySampleRadius`/`nVelocitySamples` are read from
    `axialFlowTurbineALSource::coeffs_`, and `liftReCorrExp` is read by
    `profileData` from its own `profileData/S809` subdict, beside the `Re`
    statement it modifies. The sampling values equal the source defaults
    (0.0/20), so they render no key; `config/case.yaml` sets
    `lift_re_corr_exp: 0.0`, so the committed render disables the rescaling.
    """
    def render(element_type, **kwargs):
        return generate_case.render_fv_options(
            cfg, "7", "coarse", PACKAGE / "case", element_type, **kwargs
        )

    # The committed render disables the Reynolds rescaling in every twin; the
    # sampling keys stay at the source defaults and are omitted.
    for name in ("ALM", "ASM", "ASM-MESH"):
        committed = (
            PACKAGE / "case" / "system" / f"fvOptions.{name}"
        ).read_text(encoding="utf-8")
        assert "velocitySampleRadius" not in committed
        assert "nVelocitySamples" not in committed
        assert "liftReCorrExp 0;" in committed

    alm = render(generate_case.ALM_ELEMENT)
    assert "velocitySampleRadius" not in alm
    assert "nVelocitySamples" not in alm
    assert "liftReCorrExp 0;" in alm

    # The validated Phase VI method: sampling at the rotor-coeffs level, the
    # Reynolds rescaling disabled inside the S809 profile subdict.
    validated = render(
        generate_case.ALM_ELEMENT,
        velocity_sample_radius=3.3,
        n_velocity_samples=16,
        lift_re_corr_exp=0,
    )
    coeffs = block(validated, "axialFlowTurbineALSourceCoeffs")
    assert "velocitySampleRadius 3.3;" in coeffs
    assert "nVelocitySamples 16;" in coeffs
    # Not inside a blade subdict, where the source never looks for them.
    assert "velocitySampleRadius" not in block(coeffs, "blade1")
    assert "nVelocitySamples" not in block(coeffs, "blade1")
    s809 = block(block(coeffs, "profileData"), "S809")
    assert "liftReCorrExp 0;" in s809
    assert s809.index("Re 1e6;") < s809.index("liftReCorrExp 0;")
    # `liftReCorrExp` is a profileData key, never a blade or rotor key.
    assert "liftReCorrExp" not in block(coeffs, "blade1")
    assert "liftReCorrExp" not in block(coeffs, "dynamicStall")

    # Every twin carries the same keys: they differ only in the blade keys.
    twins = (
        (generate_case.ALM_ELEMENT, {}),
        (generate_case.ASM_ELEMENT, {}),
        (
            generate_case.ASM_ELEMENT,
            {"surface_geometry": generate_case.SURFACE_GEOMETRY},
        ),
    )
    for element_type, surface in twins:
        twin = block(
            render(
                element_type,
                velocity_sample_radius=3.3,
                n_velocity_samples=16,
                lift_re_corr_exp=0,
                **surface,
            ),
            "axialFlowTurbineALSourceCoeffs",
        )
        assert "velocitySampleRadius 3.3;" in twin
        assert "nVelocitySamples 16;" in twin
        assert "liftReCorrExp 0;" in block(block(twin, "profileData"), "S809")

    # A non-physical radius is rejected before any render.
    with pytest.raises(ValueError, match="zero or positive"):
        render(generate_case.ALM_ELEMENT, velocity_sample_radius=-1.0)


def test_hub_radius_rendered_at_rotor_level(cfg, tmp_path):
    """The Prandtl hub loss renders `hubRadius` at the rotor-coeffs level.

    `axialFlowTurbineALSource` reads `hubRadius` from its rotor-level `coeffs_`
    and refuses a Glauert root effect without it. The radius is a property of
    the rotor, so the key rides with `hub_radius`, not with the `rootEffects`
    toggle: the committed case renders it, and the root-off ablation keeps it.
    A case that sets no `hub_radius` renders no key.
    """
    assert cfg["actuator"]["hub_radius"] == pytest.approx(0.5083)

    def render(element_type, **kwargs):
        return generate_case.render_fv_options(
            cfg, "7", "coarse", PACKAGE / "case", element_type, **kwargs
        )

    twins = (
        (generate_case.ALM_ELEMENT, {}),
        (generate_case.ASM_ELEMENT, {}),
        (
            generate_case.ASM_ELEMENT,
            {"surface_geometry": generate_case.SURFACE_GEOMETRY},
        ),
    )
    for element_type, surface in twins:
        coeffs = block(
            render(element_type, **surface), "axialFlowTurbineALSourceCoeffs"
        )
        assert "hubRadius 0.5083;" in coeffs
        # At the rotor-coeffs level, beside `rotorRadius`, never inside the
        # `endEffects` subdict or a blade subdict (the source reads `coeffs_`).
        assert "hubRadius" not in block(coeffs, "endEffects")
        assert "hubRadius" not in block(coeffs, "blade1")
        assert coeffs.index("rotorRadius 5.029;") < coeffs.index(
            "hubRadius 0.5083;"
        )

    # The committed twins carry the same key, and all three render the
    # disabled Reynolds rescaling.
    for name in ("ALM", "ASM", "ASM-MESH"):
        committed = (
            PACKAGE / "case" / "system" / f"fvOptions.{name}"
        ).read_text(encoding="utf-8")
        assert "hubRadius 0.5083;" in block(
            committed, "axialFlowTurbineALSourceCoeffs"
        )
        assert "liftReCorrExp 0;" in committed

    # `hubRadius` is a rotor property, not part of the root toggle: the root-off
    # ablation still renders it.
    ablation = render(generate_case.ALM_ELEMENT, root_effects=False)
    assert "rootEffects off;" in block(ablation, "GlauertCoeffs")
    assert "hubRadius 0.5083;" in block(
        ablation, "axialFlowTurbineALSourceCoeffs"
    )

    # A case that sets no `hub_radius` renders no key at all, byte-identical to
    # the pre-change default render.
    no_hub = copy.deepcopy(cfg)
    del no_hub["actuator"]["hub_radius"]
    no_hub_text = generate_case.render_fv_options(
        no_hub, "7", "coarse", PACKAGE / "case", generate_case.ALM_ELEMENT
    )
    assert "hubRadius" not in no_hub_text
    # With no key the interpolation degenerates to the pre-change template:
    # `rotorRadius` is immediately followed by `azimuthalOffset`.
    assert "rotorRadius 5.029;\n        azimuthalOffset 0;" in no_hub_text

    # A render-time override and the CLI flag both reach the rendered key.
    overridden = render(generate_case.ALM_ELEMENT, hub_radius=0.6)
    assert "hubRadius 0.6;" in block(
        overridden, "axialFlowTurbineALSourceCoeffs"
    )
    case_dir = tmp_path / "case"
    result = subprocess.run(
        [
            sys.executable,
            str(PACKAGE / "tools" / "generate_case.py"),
            "--hub-radius", "0.55",
            "--case-dir", str(case_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    rendered = (case_dir / "system" / "fvOptions.ALM").read_text(
        encoding="utf-8"
    )
    assert "hubRadius 0.55;" in block(
        rendered, "axialFlowTurbineALSourceCoeffs"
    )

    # A non-positive radius is rejected before any render (exit 2).
    negative = subprocess.run(
        [
            sys.executable,
            str(PACKAGE / "tools" / "generate_case.py"),
            "--hub-radius", "-1",
        ],
        capture_output=True,
        text=True,
    )
    assert negative.returncode == 2
    assert "must be positive" in negative.stderr


def test_sampling_config_and_flags_drive_the_render(cfg, tmp_path):
    """The YAML governs the three keys and the matching flags override it."""
    def generate(*flags):
        return subprocess.run(
            [sys.executable, str(PACKAGE / "tools" / "generate_case.py"), *flags],
            capture_output=True,
            text=True,
        )

    case_dir = tmp_path / "case-cli"
    cli = generate(
        "--velocity-sample-radius", "3.3",
        "--n-velocity-samples", "16",
        "--lift-re-corr-exp", "0",
        "--case-dir", str(case_dir),
    )
    assert cli.returncode == 0, cli.stderr
    for name in ("ALM", "ASM", "ASM-MESH"):
        rendered = (case_dir / "system" / f"fvOptions.{name}").read_text(
            encoding="utf-8"
        )
        assert "velocitySampleRadius 3.3;" in rendered
        assert "nVelocitySamples 16;" in rendered
        assert "liftReCorrExp 0;" in rendered

    # The YAML carries the same three values and renders without any flag.
    config = tmp_path / "case.yaml"
    variant = yaml.safe_load(
        (PACKAGE / "config" / "case.yaml").read_text(encoding="utf-8")
    )
    variant["actuator"]["velocity_sampling"]["velocity_sample_radius"] = 2.5
    variant["actuator"]["velocity_sampling"]["n_velocity_samples"] = 8
    variant["profile"]["lift_re_corr_exp"] = 0.5
    config.write_text(yaml.safe_dump(variant, sort_keys=False), encoding="utf-8")
    from_yaml = tmp_path / "case-yaml"
    yaml_run = generate("--config", str(config), "--case-dir", str(from_yaml))
    assert yaml_run.returncode == 0, yaml_run.stderr
    rendered = (from_yaml / "system" / "fvOptions.ALM").read_text(encoding="utf-8")
    assert "velocitySampleRadius 2.5;" in rendered
    assert "nVelocitySamples 8;" in rendered
    assert "liftReCorrExp 0.5;" in rendered

    # An explicit flag overrides the YAML.
    overridden = tmp_path / "case-yaml-override"
    yaml_override = generate(
        "--config", str(config),
        "--velocity-sample-radius", "3.3",
        "--case-dir", str(overridden),
    )
    assert yaml_override.returncode == 0, yaml_override.stderr
    rendered = (overridden / "system" / "fvOptions.ALM").read_text(encoding="utf-8")
    assert "velocitySampleRadius 3.3;" in rendered
    assert "nVelocitySamples 8;" in rendered

    # Non-physical inputs are rejected before any render (exit 2).
    negative = generate("--velocity-sample-radius", "-1")
    assert negative.returncode == 2
    assert "zero or positive" in negative.stderr
    zero_samples = generate("--n-velocity-samples", "0")
    assert zero_samples.returncode == 2
    assert "positive integer" in zero_samples.stderr


def test_asm_mesh_selection(cfg, tmp_path):
    """`asm-mesh` is selectable end-to-end and its runs are prepared-only."""
    selected = subprocess.run(
        [
            sys.executable,
            str(PACKAGE / "tools" / "case_config.py"),
            "--select", "7", "coarse", "asm-mesh",
        ],
        capture_output=True,
        text=True,
    )
    assert selected.returncode == 0, selected.stderr
    payload = json.loads(selected.stdout)
    assert payload["model"] == "asm-mesh"
    assert payload["tsr"] == pytest.approx(5.408, abs=1e-9)

    rejected = subprocess.run(
        [
            sys.executable,
            str(PACKAGE / "tools" / "case_config.py"),
            "--select", "7", "coarse", "bogus",
        ],
        capture_output=True,
        text=True,
    )
    assert rejected.returncode == 2
    assert "['alm', 'asm', 'asm-mesh']" in rejected.stderr

    # The runner refuses --submit for the model before any environment check:
    # the ASM-mesh array is prepared-only and must not be submitted.
    refused = subprocess.run(
        [
            "sh", str(PACKAGE / "scripts" / "runPhaseVI.sh"),
            "-m", "asm-mesh", "-u", "7", "-mesh", "coarse", "--submit",
        ],
        capture_output=True,
        text=True,
    )
    assert refused.returncode == 2
    assert "scripts/slurm/asm-mesh.slurm" in refused.stderr
    assert "prepared-only" in refused.stderr

    # A prepare-only invocation (no --run/--submit) renders the run directory
    # `runs/asm-mesh-U7-coarse` without OpenFOAM. `check_environment.sh` is
    # stubbed in a sandbox copy and the shared mesh is pre-created so the
    # runner stops after preparation, exactly like the W3 gate rehearsal.
    sandbox = tmp_path / "sandbox"
    package = sandbox / "validation" / "phaseVI"
    package.parent.mkdir(parents=True)
    # `runs/`, `results/` and any generated `polyMesh` are gitignored
    # working-tree state (the committed package is small); the sandbox only
    # needs the rendered skeleton, the tooling and the data.
    shutil.copytree(
        PACKAGE,
        package,
        ignore=shutil.ignore_patterns(
            "runs", "results", "polyMesh", "__pycache__"
        ),
    )
    (sandbox / "geometry").symlink_to(TURBINESFOAM / "geometry")
    environment = package / "scripts" / "check_environment.sh"
    environment.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    environment.chmod(0o755)
    mesh = package / "runs" / "mesh-coarse" / "constant" / "polyMesh"
    mesh.mkdir(parents=True)
    (mesh / ".keep").write_text("", encoding="utf-8")

    # The runner calls `python3` from PATH; the test's interpreter is the one
    # that must be used (a `python3` shim, so the test does not depend on the
    # invoking environment's PATH order).
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "python3").symlink_to(sys.executable)
    # The sandbox must be isolated from an ambient Slurm allocation: the runner
    # enforces --ranks == SLURM_NTASKS when SLURM_NTASKS is set, so inheriting
    # the batch job's SLURM_* would make this test fail inside a compute node.
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("SLURM_")
    }
    env["PATH"] = str(shim) + os.pathsep + env.get("PATH", "")

    prepared = subprocess.run(
        [
            "sh", str(package / "scripts" / "runPhaseVI.sh"),
            "-m", "asm-mesh", "-u", "7", "-mesh", "coarse",
        ],
        cwd=package,
        capture_output=True,
        text=True,
        env=env,
    )
    assert prepared.returncode == 0, prepared.stderr
    run_dir = package / "runs" / "asm-mesh-U7-coarse"
    assert run_dir.is_dir()
    committed_stl = TURBINESFOAM / "geometry" / "stl" / "phaseVI_blade.stl"
    staged = run_dir / "constant" / "triSurface" / "phaseVI_blade.stl"
    # The default pitch reference is `tip` (v1.3): the staged surface is lofted for it, so it
    # is NOT the committed twist-zero STL; `--pitch-reference twist-zero` stages that one.
    assert staged.read_bytes() != committed_stl.read_bytes()
    lofted = tmp_path / "lofted"
    subprocess.run(
        [sys.executable, str(PACKAGE / "tools" / "make_equispaced_blade.py"),
         "--pitch-reference", "tip", "--out-dir", str(lofted)],
        check=True, capture_output=True,
    )
    assert staged.read_bytes() == (lofted / "phaseVI_blade.stl").read_bytes()
    twist_zero = subprocess.run(
        [
            "sh", str(package / "scripts" / "runPhaseVI.sh"),
            "-m", "asm-mesh", "-u", "7", "-mesh", "coarse",
            "--pitch-reference", "twist-zero", "--run-label", "tz",
        ],
        cwd=package, capture_output=True, text=True, env=env,
    )
    assert twist_zero.returncode == 0, twist_zero.stderr
    assert (
        package / "runs" / "asm-mesh-U7-coarse-tz" / "constant" / "triSurface" / "phaseVI_blade.stl"
    ).read_bytes() == committed_stl.read_bytes()
    payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["model"] == "asm-mesh"
    assert payload["staged_stl_sha256"] == hashlib.sha256(
        staged.read_bytes()
    ).hexdigest()
    # The installed twin is the committed ASM-MESH render; only the
    # case-relative polars `#include` differs (the run directory sits
    # elsewhere in the tree), exactly as for the committed skeleton render.
    def without_polars_include(text):
        return re.sub(r'#include "[^"]*"', '#include "POLARS"', text)

    installed = (run_dir / "system" / "fvOptions").read_text(encoding="utf-8")
    committed_twin = (
        PACKAGE / "case" / "system" / "fvOptions.ASM-MESH"
    ).read_text(encoding="utf-8")
    assert without_polars_include(installed) == without_polars_include(committed_twin)


def test_per_speed_measured_tsr(cfg):
    assert_tsr_matches_experiment(cfg)
    for speed, tsr in FROZEN_TSR.items():
        entry = select_speed(cfg, speed)
        assert entry["tsr"] == tsr
        text = generate_case.render_fv_options(
            cfg, speed, "coarse", PACKAGE / "case", generate_case.ALM_ELEMENT
        )
        assert f"tipSpeedRatio {tsr:.8g};" in text
        if speed != "7":
            # the scaffold's fixed 5.3894 must not be used globally
            assert abs(entry["tsr"] - 5.3894) > 0.1
    assert select_speed(cfg, "7", "S")["tsr"] == 5.407


def test_tip_displacement_constraint(cfg):
    for speed in speed_keys(cfg):
        for mesh in EXPECTED_CELLS:
            assert_tip_constraint(cfg, speed, mesh)
            assert tip_displacement(cfg, speed, mesh) < hub_cell_size(cfg, mesh)
    displacement = tip_displacement(cfg, "7", "coarse")
    assert displacement == pytest.approx(0.3028, abs=5e-4)
    assert displacement < EXPECTED_HUB_CELL["coarse"]

    invalid = copy.deepcopy(cfg)
    invalid["mesh"]["resolutions"]["coarse"]["delta_t"] = 0.03
    with pytest.raises(ValueError, match="0.03"):
        validate_config(invalid)


def test_element_data_convention(cfg):
    """Model Definition v1.2 (twist-zero) mounting; the v1.3 tip reference is tested in test_phasevi_pitch_reference."""
    cfg = copy.deepcopy(cfg)
    cfg["turbine"]["pitch_reference"] = "twist-zero"
    blade = blade_element_rows(cfg)
    assert len(blade) == 26
    assert blade[0][1] == pytest.approx(0.5083)
    assert blade[-1][1] == pytest.approx(5.029)
    for station, row in zip(
        [(0.5083, 0.0), (1.0085, 6.7), (5.029, -1.815)],
        (blade[0], blade[3], blade[-1]),
        strict=True,
    ):
        radius, twist = station
        assert row[1] == pytest.approx(radius)
        assert row[5] == pytest.approx(-(twist + 3.0))
    hub = hub_element_rows()
    assert pytest.approx(1.0166) == HUB_DIAMETER
    assert hub[0][1] == pytest.approx(0.5083)
    assert hub[1][1] == pytest.approx(-0.5083)


def _scalar(text: str, key: str) -> float:
    """Parse a rendered OpenFOAM scalar, e.g. `tipSpeedRatio 5.408;`."""
    match = re.search(rf"\b{key}\s+([-+0-9.eE]+)\s*;", text)
    assert match is not None, f"{key} not found"
    return float(match.group(1))


def _vector(text: str, key: str) -> tuple[float, float, float]:
    """Parse a rendered OpenFOAM vector, e.g. `axis (-1 0 0);`."""
    match = re.search(rf"\b{key}\s+\(([^)]*)\)", text)
    assert match is not None, f"{key} not found"
    values = tuple(float(value) for value in match.group(1).split())
    assert len(values) == 3, f"{key} is not a 3-vector: {values}"
    return values


def test_rotor_orientation_chain_is_pinned(cfg):
    """Pin the pair that turns the domain orientation into a rotation sense.

    `axialFlowTurbineALSource` builds the azimuthal direction as
    `axis ^ verticalDirection` (`axialFlowTurbineALSource.C:67`), puts the blade
    along `verticalDirection` at azimuth 0 and gives it the tangential velocity
    `azimuthalDirection * omega * r` (`:179`). Nothing else checks that pair
    against the inflow, so swapping `vertical_direction` mirrors the whole rotor
    and every load with it, **silently**: a mirrored rotor still extracts
    positive power and still produces a plausible spanwise shape, so neither the
    sign gate nor the band check would notice. This is the failure that already
    cost the IEA 15 MW case a diagnosis, and the reason its generator carries a
    `flow_axis` plus a `_role_to_physical` rotation.
    """
    rendered = (PACKAGE / "case" / "system" / "fvOptions.ALM").read_text(
        encoding="utf-8"
    )
    axis = _vector(rendered, "axis")
    vertical = _vector(rendered, "verticalDirection")
    inflow = _vector(rendered, "freeStreamVelocity")

    # The committed artifact must carry exactly the configured orientation, so
    # the config stays the single source and the render cannot drift from it.
    assert axis == pytest.approx(tuple(cfg["turbine"]["axis"]), abs=0.0)
    assert vertical == pytest.approx(
        tuple(cfg["turbine"]["vertical_direction"]), abs=0.0
    )
    assert sum(c * c for c in axis) ** 0.5 == pytest.approx(1.0, abs=1e-12)
    assert sum(c * c for c in vertical) ** 0.5 == pytest.approx(1.0, abs=1e-12)
    assert sum(a * b for a, b in zip(axis, vertical, strict=True)) == pytest.approx(
        0.0, abs=1e-9
    )

    azimuthal = (
        axis[1] * vertical[2] - axis[2] * vertical[1],
        axis[2] * vertical[0] - axis[0] * vertical[2],
        axis[0] * vertical[1] - axis[1] * vertical[0],
    )
    # Deliberate value. Flipping it reverses the blade's tangential velocity,
    # hence the sign of every section's angle of attack: the rotor mirrors.
    assert azimuthal == pytest.approx((0.0, 1.0, 0.0), abs=1e-12)
    # Upwind: the flow arrives against the axis, not along it.
    assert sum(a * b for a, b in zip(axis, inflow, strict=True)) < 0.0
    # Blade 2 is blade 1 rotated by half a turn.
    assert "azimuthalOffset 180;" in block(rendered, "blade2")

    # AFTAL places azimuth 0 on `verticalDirection`, so every blade-1 element sits
    # at azimuth 0 and reaches its span position through its own radius.
    blade = blade_element_rows(cfg)
    assert {float(row[2]) for row in blade} == {0.0}
    assert blade[0][1] < blade[-1][1]

    # Kinematic invariant, computed from the rendered TSR: tan(phi) = U/(omega r).
    # The inflow angle must fall from root to tip, and both ends must sit in
    # plausible bands. A reversed or rescaled TSR, or a radius in the wrong unit,
    # breaks the bands without breaking any sign check, so the magnitude is
    # pinned here and not only the sense.
    speed = float(inflow[0])
    tsr = _scalar(rendered, "tipSpeedRatio")
    assert tsr > 0.0
    omega = tsr * speed / float(cfg["turbine"]["radius"])
    assert omega > 0.0
    phis = [
        math.degrees(math.atan(speed / (omega * float(row[1])))) for row in blade
    ]
    assert phis == sorted(phis, reverse=True)
    assert 5.0 < phis[-1] < 20.0
    assert 40.0 < phis[0] < 80.0


def test_rotor_refinement_dict_and_level_scaling(cfg):
    """The castellated refinement is local, level-driven and always declared.

    Level 0 renders the dictionary with `castellatedMesh false`, so a run
    directory states its refinement level instead of leaving it implicit and the
    committed case keeps the base `blockMesh` only.
    """
    base = generate_case.render_snappy_dict(cfg, 0)
    assert "castellatedMesh false;" in base
    assert "snap false;" in base
    assert "addLayers false;" in base
    assert "rotorDisk" in base
    assert "levels ((1e15" not in base

    refined = generate_case.render_snappy_dict(cfg, 2)
    assert "castellatedMesh true;" in refined
    assert "type searchableCylinder;" in refined
    assert "levels ((1e15 2));" in refined
    assert "mode inside;" in refined

    # The cylinder spans the hub plus/minus the half thickness along the axis and
    # its radius is set by the tip sampling sphere, not by the chord.
    hub = generate_case.turbine_origin(cfg)
    half = float(cfg["mesh"]["refinement"]["disk_half_thickness_m"])
    radius = float(cfg["mesh"]["refinement"]["disk_radius_m"])
    assert f"point1 ({hub[0] - half:.9g} {hub[1]:.9g} {hub[2]:.9g});" in refined
    assert f"point2 ({hub[0] + half:.9g} {hub[1]:.9g} {hub[2]:.9g});" in refined
    assert f"radius {radius:.9g};" in refined
    assert radius > float(cfg["turbine"]["radius"]) + 2.0

    # Out-of-range levels fail loudly instead of rendering something wrong.
    highest = int(cfg["mesh"]["refinement"]["max_level"])
    with pytest.raises(ValueError, match="exceeds the configured maximum"):
        generate_case.render_snappy_dict(cfg, highest + 1)
    with pytest.raises(ValueError, match="zero or positive"):
        generate_case.render_snappy_dict(cfg, -1)

    # The committed skeleton carries the level-0 dictionary.
    committed = (PACKAGE / "case" / "system" / "snappyHexMeshDict").read_text(
        encoding="utf-8"
    )
    assert committed == base


def test_refine_level_and_delta_t_overrides(cfg, tmp_path):
    """`--refine-level` holds epsilon fixed; `--delta-t` pins the step.

    The ladder must move the mesh and nothing else, so the projection width stays
    fixed in metres by scaling `gaussian_mesh_factor` by `2**level`, and the time
    step is fixed at the finest level's requirement at every level.
    """
    def render(*flags):
        return subprocess.run(
            [
                sys.executable,
                str(PACKAGE / "tools" / "generate_case.py"),
                "--case-dir", str(tmp_path),
                *flags,
            ],
            capture_output=True,
            text=True,
        )

    assert render().returncode == 0
    baseline_factor = float(cfg["turbine"]["gaussian_mesh_factor"])
    baseline_mesh = (tmp_path / "system" / "fvOptions.ALM").read_text(encoding="utf-8")
    baseline_control = (tmp_path / "system" / "controlDict").read_text(
        encoding="utf-8"
    )

    assert render("--refine-level", "2").returncode == 0
    refined = (tmp_path / "system" / "fvOptions.ALM").read_text(encoding="utf-8")
    assert f"meshFactor {baseline_factor * 4.0:.8g};" in refined
    assert "levels ((1e15 2));" in (tmp_path / "system" / "snappyHexMeshDict").read_text(
        encoding="utf-8"
    )

    assert render("--delta-t", "0.001").returncode == 0
    assert "deltaT 0.001;" in (tmp_path / "system" / "controlDict").read_text(
        encoding="utf-8"
    )

    # Neither flag changes the default render.
    assert render().returncode == 0
    assert (tmp_path / "system" / "controlDict").read_text(encoding="utf-8") == baseline_control
    assert (tmp_path / "system" / "fvOptions.ALM").read_text(encoding="utf-8") == baseline_mesh

    # Non-physical inputs are rejected before any render (argparse exit 2).
    assert render("--delta-t", "0").returncode == 2
    assert render("--refine-level", "-1").returncode == 2


def test_stage_matrix(cfg):
    stages = cfg["stages"]
    executing = [name for name, stage in stages.items() if stage.get("executes")]
    assert executing == ["stage0"]
    stage0 = stages["stage0"]
    assert stage0["queue"] == "sequana_cpu_dev"
    assert stage0["max_revolutions"] <= 0.3
    assert stage0["speeds"] == [7]
    assert stage0["meshes"] == ["coarse", "fine"]

    assert stages["stage1"]["meshes"] == ["coarse", "fine"]
    assert stages["stage1"]["speeds"] == [7]
    assert sorted(stages["stage2"]["speeds"]) == [10, 13, 15, 25]
    assert stages["stage2"]["sequence_s"] is True
    stage3 = stages["stage3"]
    assert stage3["optional"] is True
    assert stage3["iddes"] is True
    assert stage3["n_chordwise"] == [1, 3, 5]
    assert stage3["n_chordwise_mesh"] == "fine"
    assert "ultra" in stage3["meshes"]

    # The ASM-mesh third variant is prepared, never executed by the plan.
    asm_mesh = stages["asm-mesh"]
    assert asm_mesh["queue"] == "sequana_cpu_long"
    assert asm_mesh["models"] == ["asm-mesh"]
    assert asm_mesh["meshes"] == ["coarse", "fine"]
    assert asm_mesh["speeds"] == [7]
    assert asm_mesh["executes"] is False

    for stage in stages.values():
        assert 20.0 not in [float(value) for value in stage.get("speeds", [])]

    invalid = copy.deepcopy(cfg)
    invalid["stages"]["stage2"]["speeds"] = [10, 20]
    with pytest.raises(ValueError, match="20 m/s"):
        validate_config(invalid)


def test_decomposition_rendered(cfg):
    text = generate_case.render_decompose_par(cfg)
    assert "numberOfSubdomains 48;" in text
    override = generate_case.render_decompose_par(cfg, ranks=192)
    assert "numberOfSubdomains 192;" in override
    assert "numberOfSubdomains 48;" not in override


def test_iddes_variant(cfg):
    assert cfg["solver"]["iddes_model"] == "kOmegaSSTIDDES"
    iddes = cfg["iddes"]
    assert iddes["delta"] == "IDDESDelta"
    assert iddes["delta_t"] == 0.0025

    les = generate_case.render_turbulence_properties(cfg, "iddes")
    assert "simulationType LES;" in les
    assert "LESModel kOmegaSSTIDDES;" in les
    assert "delta IDDESDelta;" in les
    assert "IDDESDeltaCoeffs" in les
    assert "Cw 0.15;" in les
    assert "RASModel" not in les

    ras = generate_case.render_turbulence_properties(cfg)
    assert "simulationType RAS;" in ras
    assert "RASModel kOmegaSST;" in ras
    assert "LESModel" not in ras

    schemes = generate_case.render_fv_schemes(cfg, "iddes")
    assert "div(phi,U)      Gauss linear;" in schemes
    assert "nRequired       true;" in schemes
    assert "bounded Gauss linearUpwind grad(U)" not in schemes
    urans_schemes = generate_case.render_fv_schemes(cfg)
    assert "div(phi,U)      bounded Gauss linearUpwind grad(U);" in urans_schemes
    assert "nRequired" not in urans_schemes

    for mesh in EXPECTED_CELLS:
        assert solver_delta_t(cfg, mesh, "iddes") == 0.0025
        control = generate_case.render_control_dict(
            cfg, "7", mesh, "production", None, "startTime", solver="iddes"
        )
        assert "deltaT 0.0025;" in control
        assert "adjustTimeStep off;" in control
        assert_tip_constraint(cfg, "7", mesh, "iddes")
        assert tip_displacement(cfg, "7", mesh, "iddes") < hub_cell_size(cfg, mesh)
    assert tip_displacement(cfg, "7", "fine", "iddes") == pytest.approx(
        5.408 * 7.0 * 0.0025, rel=1e-12
    )
    assert kinematics(cfg, "7", "fine", "H", "iddes")["delta_t"] == 0.0025
    assert kinematics(cfg, "7", "fine")["delta_t"] == 0.005

    invalid = copy.deepcopy(cfg)
    invalid["iddes"]["delta"] = "cubeRootVol"
    with pytest.raises(ValueError, match="IDDESDelta"):
        validate_config(invalid)
    invalid = copy.deepcopy(cfg)
    invalid["iddes"]["delta_t"] = 0.0
    with pytest.raises(ValueError, match="delta_t"):
        validate_config(invalid)


def test_n_chordwise_override(cfg):
    asm = generate_case.render_fv_options(
        cfg, "7", "fine", PACKAGE / "case", generate_case.ASM_ELEMENT,
        n_chordwise=1,
    )
    assert "nChordwise 1;" in asm
    assert "nChordwise 5;" not in asm
    # The override reaches the ASM twin only; the ALM twin has no such key.
    alm = generate_case.render_fv_options(
        cfg, "7", "fine", PACKAGE / "case", generate_case.ALM_ELEMENT,
        n_chordwise=1,
    )
    assert "nChordwise" not in alm
    with pytest.raises(ValueError, match="positive"):
        generate_case.render_fv_options(
            cfg, "7", "fine", PACKAGE / "case", generate_case.ASM_ELEMENT,
            n_chordwise=0,
        )


def test_n_elements_override(cfg, tmp_path):
    """The spanwise element count defaults to 50 and is render-time overridable.

    The committed default is 50, so the committed twins are unchanged; the Dag
    & Sorensen `nrAero = 11` ablation renders `nElements 11;` through the same
    `actuator.n_elements` plumbing as `--n-chordwise`.
    """
    # The committed default renders `nElements 50` in every twin's blade1.
    for name in ("ALM", "ASM", "ASM-MESH"):
        committed = (
            PACKAGE / "case" / "system" / f"fvOptions.{name}"
        ).read_text()
        assert "nElements 50;" in block(committed, "blade1")

    overridden = generate_case.render_fv_options(
        cfg, "7", "coarse", PACKAGE / "case", generate_case.ALM_ELEMENT,
        n_elements=11,
    )
    assert "nElements 11;" in block(overridden, "blade1")
    assert "nElements 50;" not in overridden
    # The override reaches the other twins through the shared render function.
    asm = generate_case.render_fv_options(
        cfg, "7", "coarse", PACKAGE / "case", generate_case.ASM_ELEMENT,
        n_elements=11,
    )
    assert "nElements 11;" in block(asm, "blade1")

    # The CLI flag renders every twin at the coarser resolution.
    case_dir = tmp_path / "case"
    result = subprocess.run(
        [
            sys.executable,
            str(PACKAGE / "tools" / "generate_case.py"),
            "--n-elements", "11",
            "--case-dir", str(case_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    for name in ("ALM", "ASM", "ASM-MESH"):
        rendered = (case_dir / "system" / f"fvOptions.{name}").read_text()
        assert "nElements 11;" in block(rendered, "blade1")

    with pytest.raises(ValueError, match="positive"):
        generate_case.render_fv_options(
            cfg, "7", "coarse", PACKAGE / "case", generate_case.ALM_ELEMENT,
            n_elements=0,
        )

    # The CLI rejects a zero/negative value before writing anything.
    rejected = subprocess.run(
        [
            sys.executable,
            str(PACKAGE / "tools" / "generate_case.py"),
            "--n-elements", "0",
            "--case-dir", str(tmp_path / "rejected"),
        ],
        capture_output=True,
        text=True,
    )
    assert rejected.returncode == 2


def test_cli_variant_render(cfg, tmp_path):
    """The CLI renders IDDES + nChordwise/ranks overrides in one pass."""
    case_dir = tmp_path / "case"
    result = subprocess.run(
        [
            sys.executable,
            str(PACKAGE / "tools" / "generate_case.py"),
            "--mesh", "fine",
            "--solver", "iddes",
            "--n-chordwise", "1",
            "--ranks", "192",
            "--case-dir", str(case_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    turbulence = (case_dir / "constant" / "turbulenceProperties").read_text()
    assert "simulationType LES;" in turbulence
    assert "LESModel kOmegaSSTIDDES;" in turbulence
    assert "delta IDDESDelta;" in turbulence
    control = (case_dir / "system" / "controlDict").read_text()
    assert "deltaT 0.0025;" in control
    assert "nChordwise 1;" in (case_dir / "system" / "fvOptions.ASM").read_text()
    assert "numberOfSubdomains 192;" in (
        case_dir / "system" / "decomposeParDict"
    ).read_text()


def test_generated_case_is_current(cfg):
    # The committed third twin is exactly the in-memory render (so `--check`
    # covers it and the committed file is the documented renderer output).
    rendered = generate_case.render_fv_options(
        cfg,
        "7",
        "coarse",
        PACKAGE / "case",
        generate_case.ASM_ELEMENT,
        surface_geometry=generate_case.SURFACE_GEOMETRY,
    )
    committed = (PACKAGE / "case" / "system" / "fvOptions.ASM-MESH").read_text()
    assert committed == rendered

    # The other two committed twins are their in-memory renders too.
    for name, element_type in (
        ("ALM", generate_case.ALM_ELEMENT),
        ("ASM", generate_case.ASM_ELEMENT),
    ):
        rendered_twin = generate_case.render_fv_options(
            cfg, "7", "coarse", PACKAGE / "case", element_type
        )
        committed_twin = (
            PACKAGE / "case" / "system" / f"fvOptions.{name}"
        ).read_text()
        assert committed_twin == rendered_twin

    result = subprocess.run(
        [sys.executable, str(PACKAGE / "tools" / "generate_case.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


S_ARCHIVE_PERFORMANCE = (
    PACKAGE / "data" / "experiment" / "uae6-archive" / "sequence_S_performance.csv"
)


def _sequence_s_archive_rows():
    import csv

    with S_ARCHIVE_PERFORMANCE.open(encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def test_sequence_s_covers_the_21_zero_yaw_speeds(cfg):
    """`-s S` accepts every 0 deg yaw speed of the archive, not just 7 m/s."""
    rows = _sequence_s_archive_rows()
    assert len(rows) == 21
    for row in rows:
        speed = float(row["wind_speed_m_s"])
        entry = select_speed(cfg, speed, "S")
        assert entry["row"] == row["file_name"]
        derived = tsr_from_rpm(
            float(row["rpm"]), speed, float(cfg["turbine"]["radius"])
        )
        assert abs(entry["tsr"] - derived) <= 0.002
        assert abs(entry["rotor_speed_rpm"] - float(row["rpm"])) <= 0.001


def test_sequence_s_keeps_the_7_ms_default_row(cfg):
    entry = select_speed(cfg, "7", "S")
    assert (entry["tsr"], entry["rotor_speed_rpm"], entry["row"]) == (
        5.407,
        71.867,
        "s0700000",
    )


def test_sequence_s_rejects_a_speed_outside_the_archive(cfg):
    with pytest.raises(KeyError):
        select_speed(cfg, "30", "S")


def test_sequence_h_selection_is_unchanged_by_the_s_table(cfg):
    assert speed_keys(cfg) == ["5", "7", "10", "13", "15", "20", "25"]  # 5 m/s: P2.3 T13
    with pytest.raises(KeyError):
        select_speed(cfg, "9", "H")


def test_sequence_s_kinematics_render_for_every_archive_speed(cfg):
    """The renderer path (kinematics + tip constraint) accepts all 21 speeds."""
    for row in _sequence_s_archive_rows():
        speed = float(row["wind_speed_m_s"])
        for mesh in EXPECTED_CELLS:
            values = kinematics(cfg, speed, mesh, "S")
            assert values["rpm"] == pytest.approx(float(row["rpm"]), abs=0.001)
            assert values["tsr"] == pytest.approx(
                tsr_from_rpm(float(row["rpm"]), speed, float(cfg["turbine"]["radius"])),
                abs=0.002,
            )


def _render_cli(case_dir, *extra):
    return subprocess.run(
        [
            sys.executable,
            str(PACKAGE / "tools" / "generate_case.py"),
            *extra,
            "--case-dir", str(case_dir),
        ],
        capture_output=True,
        text=True,
    )


def _mesh_factors(case_dir):
    values = {}
    for name in ("fvOptions.ALM", "fvOptions.ASM", "fvOptions.ASM-MESH"):
        text = (case_dir / "system" / name).read_text()
        values[name] = re.findall(r"meshFactor\s+([^;]+);", text)
    return values


def test_cli_mesh_factor_override_reaches_every_fvoptions_variant(tmp_path):
    """--mesh-factor F renders F as meshFactor in ALM, ASM and ASM-MESH."""
    result = _render_cli(tmp_path / "case", "--mesh-factor", "2.5")
    assert result.returncode == 0, result.stderr
    factors = _mesh_factors(tmp_path / "case")
    for name, found in factors.items():
        assert found, name
        assert set(found) == {"2.5"}, (name, found)


def test_cli_mesh_factor_is_applied_before_refine_level(tmp_path):
    """--mesh-factor 2 --refine-level 1 renders 4 (override first, then 2**N)."""
    result = _render_cli(
        tmp_path / "case", "--mesh-factor", "2", "--refine-level", "1"
    )
    assert result.returncode == 0, result.stderr
    for name, found in _mesh_factors(tmp_path / "case").items():
        assert found and set(found) == {"4"}, (name, found)


@pytest.mark.parametrize("bad", ["0", "-1", "abc"])
def test_cli_mesh_factor_rejects_invalid_values(tmp_path, bad):
    result = _render_cli(tmp_path / "case", "--mesh-factor", bad)
    assert result.returncode == 2
    assert "--mesh-factor" in result.stderr
    assert not (tmp_path / "case" / "system" / "fvOptions.ALM").exists()


def test_cli_mesh_factor_absent_or_default_leaves_render_unchanged(tmp_path):
    """No flag and the configured value (1.0) render byte-identical files."""
    plain = _render_cli(tmp_path / "plain")
    explicit = _render_cli(tmp_path / "explicit", "--mesh-factor", "1.0")
    assert plain.returncode == 0, plain.stderr
    assert explicit.returncode == 0, explicit.stderr
    plain_files = sorted(p.relative_to(tmp_path / "plain")
                         for p in (tmp_path / "plain").rglob("*") if p.is_file())
    explicit_files = sorted(p.relative_to(tmp_path / "explicit")
                            for p in (tmp_path / "explicit").rglob("*") if p.is_file())
    assert plain_files == explicit_files and plain_files
    for rel in plain_files:
        assert (tmp_path / "plain" / rel).read_bytes() == (
            tmp_path / "explicit" / rel
        ).read_bytes(), rel


def _prepare_sandbox(tmp_path):
    sandbox = tmp_path / "sandbox"
    package = sandbox / "validation" / "phaseVI"
    package.parent.mkdir(parents=True)
    shutil.copytree(
        PACKAGE,
        package,
        ignore=shutil.ignore_patterns("runs", "results", "polyMesh", "__pycache__"),
    )
    (sandbox / "geometry").symlink_to(TURBINESFOAM / "geometry")
    environment = package / "scripts" / "check_environment.sh"
    environment.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    environment.chmod(0o755)
    for level in ("", "-r1"):
        mesh = package / "runs" / f"mesh-coarse{level}" / "constant" / "polyMesh"
        mesh.mkdir(parents=True)
        (mesh / ".keep").write_text("", encoding="utf-8")
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "python3").symlink_to(sys.executable)
    env = {k: v for k, v in os.environ.items() if not k.startswith("SLURM_")}
    env["PATH"] = str(shim) + os.pathsep + env.get("PATH", "")
    return package, env


def test_runner_mesh_factor_validation_and_run_json(tmp_path):
    """runPhaseVI.sh validates --mesh-factor and records the effective value."""
    package, env = _prepare_sandbox(tmp_path)
    script = str(package / "scripts" / "runPhaseVI.sh")
    base = ["sh", script, "-m", "alm", "-u", "7", "-mesh", "coarse"]

    for bad in ("0", "-1", "abc", "0.0"):
        refused = subprocess.run(
            [*base, "--mesh-factor", bad],
            cwd=package, capture_output=True, text=True, env=env,
        )
        assert refused.returncode == 2, bad
        assert "--mesh-factor" in refused.stderr

    absent = subprocess.run(
        [*base, "--run-label", "mf-absent"],
        cwd=package, capture_output=True, text=True, env=env,
    )
    assert absent.returncode == 0, absent.stderr
    payload = json.loads(
        (package / "runs" / "alm-U7-coarse-mf-absent" / "run.json").read_text()
    )
    assert payload["mesh_factor"] == 1.0

    prepared = subprocess.run(
        [*base, "--mesh-factor", "2", "--refine-level", "1", "--run-label", "mf"],
        cwd=package, capture_output=True, text=True, env=env,
    )
    assert prepared.returncode == 0, prepared.stderr
    run_dir = package / "runs" / "alm-U7-coarse-r1-mf"
    payload = json.loads((run_dir / "run.json").read_text())
    assert payload["mesh_factor"] == 4.0
    assert set(re.findall(
        r"meshFactor\s+([^;]+);", (run_dir / "system" / "fvOptions").read_text()
    )) == {"4"}


def test_model_definition_v1_3_defaults(cfg):
    """v1.3: total-drag OSU polar, Glauert tip off + Prandtl hub on, D&S on."""
    text = generate_case.render_fv_options(
        cfg, "7", "coarse", PACKAGE / "case", generate_case.ALM_ELEMENT
    )
    assert "data/polars/S809_OSU_Re1M_total.dat" in text
    assert "S809_OSU_Re1M_pressure.dat" not in text
    glauert = block(text, "GlauertCoeffs")
    assert "tipEffects off;" in glauert and "rootEffects on;" in glauert
    assert "active on;" in block(text, "tipCorrection")


def test_model_definition_v1_2_knobs_stay_reproducible(cfg):
    """v1.2 is the frozen base: every knob passed explicitly renders it."""
    cfg = copy.deepcopy(cfg)
    cfg["turbine"]["pitch_reference"] = "twist-zero"
    text = generate_case.render_fv_options(
        cfg, "7", "coarse", PACKAGE / "case", generate_case.ALM_ELEMENT,
        tip_effects=True, tip_correction=False, polar="S809_OSU_Re1M_pressure.dat",
    )
    assert "data/polars/S809_OSU_Re1M_pressure.dat" in text
    assert "S809_OSU_Re1M_total.dat" not in text
    glauert = block(text, "GlauertCoeffs")
    assert "tipEffects on;" in glauert and "rootEffects on;" in glauert
    assert "active off;" in block(text, "tipCorrection")
    assert "(0 5.029 0 0.3551 0.3 -1.185)" in text


def test_polar_override_still_selects_the_named_file(cfg):
    text = generate_case.render_fv_options(
        cfg, "7", "coarse", PACKAGE / "case", generate_case.ALM_ELEMENT,
        polar="S809_OSU_Re1M_total.dat",
    )
    assert "data/polars/S809_OSU_Re1M_total.dat" in text
    assert "S809_OSU_Re1M_pressure.dat" not in text


def test_runner_restart_refuses_instead_of_wiping_written_state(tmp_path):
    """`--restart` must never silently restart from 0.

    The --run path re-decomposes with `decomposePar -force` (deleting the
    processor* time directories) and the CSV writers open
    postProcessing/<...>/<start time>/ again, which truncated the turbine and
    element CSVs of the first segment (P2.3 session 4: S 5/6 m/s and R1 level 2
    lost their written state). Until a real resume exists, a run directory with
    written state is refused untouched; a fresh one still starts from startTime.
    """
    sandbox = tmp_path / "sandbox"
    package = sandbox / "validation" / "phaseVI"
    package.parent.mkdir(parents=True)
    shutil.copytree(
        PACKAGE,
        package,
        ignore=shutil.ignore_patterns("runs", "results", "polyMesh", "__pycache__"),
    )
    (sandbox / "geometry").symlink_to(TURBINESFOAM / "geometry")
    environment = package / "scripts" / "check_environment.sh"
    environment.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    environment.chmod(0o755)
    mesh = package / "runs" / "mesh-coarse" / "constant" / "polyMesh"
    mesh.mkdir(parents=True)
    (mesh / ".keep").write_text("", encoding="utf-8")
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "python3").symlink_to(sys.executable)
    env = {key: value for key, value in os.environ.items() if not key.startswith("SLURM_")}
    env["PATH"] = str(shim) + os.pathsep + env.get("PATH", "")

    def prepare(*flags):
        return subprocess.run(
            ["sh", str(package / "scripts" / "runPhaseVI.sh"),
             "-m", "alm", "-u", "7", "-mesh", "coarse", "--run-label", "rs", *flags],
            cwd=package, capture_output=True, text=True, env=env,
        )

    fresh = prepare("--restart")
    assert fresh.returncode == 0, fresh.stderr
    assert "no written time exists; using startTime" in fresh.stderr
    run_dir = package / "runs" / "alm-U7-coarse-rs"
    written = run_dir / "processor0" / "10.044"
    written.mkdir(parents=True)
    csv = run_dir / "postProcessing" / "turbines" / "0" / "turbine.csv"
    csv.parent.mkdir(parents=True)
    csv.write_text("time,cp\n10.044,0.4\n", encoding="utf-8")
    snapshot = {p: p.read_bytes() for p in run_dir.rglob("*") if p.is_file()}

    refused = prepare("--restart")
    assert refused.returncode == 2
    assert "Wrote" not in refused.stdout  # refused before the render
    assert "--restart cannot resume" in refused.stderr
    assert "processor0/10.044" in refused.stderr
    assert written.is_dir()
    assert {p: p.read_bytes() for p in run_dir.rglob("*") if p.is_file()} == snapshot


def test_h_speeds_accept_optional_archive_5ms_and_keep_the_required_set():
    """H 5 m/s (P2.3 T13) is an optional, archive-validated speed; the six
    required speeds stay mandatory and unknown speeds stay rejected."""
    import copy
    from case_config import assert_tsr_matches_experiment, validate_config

    cfg = load_config()
    validate_config(cfg)
    assert_tsr_matches_experiment(cfg)  # 5 m/s checked against the archive H table
    missing = copy.deepcopy(cfg)
    del missing["kinematics"]["speeds"][7]
    with pytest.raises(ValueError, match="must define 7/10/13/15/20/25 m/s"):
        validate_config(missing)
    unknown = copy.deepcopy(cfg)
    unknown["kinematics"]["speeds"][6] = dict(cfg["kinematics"]["speeds"][5])
    with pytest.raises(ValueError, match="must define 7/10/13/15/20/25 m/s"):
        validate_config(unknown)
    wrong = copy.deepcopy(cfg)
    wrong["kinematics"]["speeds"][5]["tsr"] = 7.0
    with pytest.raises(ValueError, match="5 m/s: configured TSR 7.0 differs"):
        assert_tsr_matches_experiment(wrong)
