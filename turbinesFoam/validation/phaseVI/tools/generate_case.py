#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Adapted from mttbrbr/single-actuator-line (main 8284be8c...), GPL-3.0-or-later; see README.md "Attribution and license".
"""Render the NREL Phase VI uniform-inflow case from `config/case.yaml`.

Every generated file carries a "Generated from config/case.yaml" banner and
`--check` re-renders in memory and fails when a file on disk is missing or
stale, without writing anything.

Usage:
    generate_case.py [--mesh coarse|fine|ultra] [--speed 7|10|13|15|20|25]
                     [--domain long|squat] [--profile production|smoke]
                     [--solver urans|iddes] [--n-chordwise N] [--n-elements N]
                     [--ranks N]
                     [--surface-kernel cosine|gaussian]
                     [--rotational-augmentation on|off] [--root-effects on|off]
                     [--case-dir DIR] [--end-revs FLOAT]
                     [--start-from startTime|latestTime] [--check]

Adapted from `mttbrbr/single-actuator-line` (main 8284be8c..., GPL-3.0-or-later).
"""

from __future__ import annotations

import argparse
import difflib
import os
import sys
from pathlib import Path
from typing import Any

from case_config import (
    DEFAULT_CASE_DIR,
    DEFAULT_CONFIG,
    POLARS_DIR,
    ROOT,
    SOLVER_CHOICES,
    axis_extents_D,
    foam_header,
    foam_vector,
    inflow_fields,
    kinematics,
    load_config,
    turbine_origin,
)
from element_data import (
    blade_element_profiles,
    hub_element_rows,
    render_blade_element_data,
)

MESH_CHOICES = ("coarse", "fine", "ultra")
DOMAIN_CHOICES = ("long", "squat")
PROFILE_CHOICES = ("production", "smoke")
START_FROM_CHOICES = ("startTime", "latestTime")

ALM_ELEMENT = "actuatorLineElement"
ASM_ELEMENT = "actuatorSurfaceElement"

# Case-relative path the ASM-mesh twin references; `runPhaseVI.sh -m asm-mesh`
# stages the committed STL there (tools/stage_blade_stl.py).
SURFACE_GEOMETRY = "constant/triSurface/phaseVI_blade.stl"
# Paper cosine kernel (default) and the Gaussian ablation (design D7).
SURFACE_KERNELS = ("cosine", "gaussian")

PATCH_NAMES = ("inlet", "outlet", "bottom", "top", "sideMinus", "sidePlus")


def render_block_mesh(cfg: dict[str, Any], mesh: str, domain: str, profile: str) -> str:
    """18-block hexahedral blockMeshDict with six far-field patches."""
    resolution = cfg["mesh"]["resolutions"][mesh]
    breaks = {axis: axis_extents_D(cfg, axis, domain) for axis in ("x", "y", "z")}
    cells = {
        axis: [int(value) for value in resolution[axis]["cells"]]
        for axis in ("x", "y", "z")
    }
    grading = {
        axis: [float(value) for value in resolution[axis]["grading"]]
        for axis in ("x", "y", "z")
    }
    if profile == "smoke":
        cells = {
            axis: [max(1, round(value / 4)) for value in cells[axis]]
            for axis in ("x", "y", "z")
        }
    nx, ny, nz = (len(breaks[axis]) for axis in ("x", "y", "z"))

    def vertex(ix: int, iy: int, iz: int) -> int:
        return (iz * ny + iy) * nx + ix

    vertices = []
    for z in breaks["z"]:
        for y in breaks["y"]:
            for x in breaks["x"]:
                vertices.append(f"    ({x:.9g} {y:.9g} {z:.9g})")

    blocks = []
    faces: dict[str, list[str]] = {name: [] for name in PATCH_NAMES}
    for iz in range(nz - 1):
        for iy in range(ny - 1):
            for ix in range(nx - 1):
                v000 = vertex(ix, iy, iz)
                v100 = vertex(ix + 1, iy, iz)
                v110 = vertex(ix + 1, iy + 1, iz)
                v010 = vertex(ix, iy + 1, iz)
                v001 = vertex(ix, iy, iz + 1)
                v101 = vertex(ix + 1, iy, iz + 1)
                v111 = vertex(ix + 1, iy + 1, iz + 1)
                v011 = vertex(ix, iy + 1, iz + 1)
                blocks.append(
                    "    hex "
                    f"({v000} {v100} {v110} {v010} {v001} {v101} {v111} {v011}) "
                    f"({cells['x'][ix]} {cells['y'][iy]} {cells['z'][iz]}) "
                    f"simpleGrading ({grading['x'][ix]:.9g} "
                    f"{grading['y'][iy]:.9g} {grading['z'][iz]:.9g})"
                )
                if ix == 0:
                    faces["inlet"].append(f"            ({v000} {v001} {v011} {v010})")
                if ix == nx - 2:
                    faces["outlet"].append(f"            ({v100} {v110} {v111} {v101})")
                if iz == 0:
                    faces["bottom"].append(f"            ({v000} {v010} {v110} {v100})")
                if iz == nz - 2:
                    faces["top"].append(f"            ({v001} {v101} {v111} {v011})")
                if iy == 0:
                    faces["sideMinus"].append(f"            ({v000} {v100} {v101} {v001})")
                if iy == ny - 2:
                    faces["sidePlus"].append(f"            ({v010} {v011} {v111} {v110})")

    patch_types = {
        "inlet": "patch",
        "outlet": "patch",
        "bottom": "symmetryPlane",
        "top": "symmetryPlane",
        "sideMinus": "symmetryPlane",
        "sidePlus": "symmetryPlane",
    }

    def patch(name: str) -> str:
        return (
            f"    {name}\n"
            "    {\n"
            f"        type {patch_types[name]};\n"
            "        faces\n"
            "        (\n"
            + "\n".join(faces[name])
            + "\n        );\n"
            "    }"
        )

    return (
        foam_header("blockMeshDict")
        + "scale 1;\n\nvertices\n(\n"
        + "\n".join(vertices)
        + "\n);\n\nblocks\n(\n"
        + "\n".join(blocks)
        + "\n);\n\nedges ();\n\nboundary\n(\n"
        + "\n".join(patch(name) for name in PATCH_NAMES)
        + "\n);\n\nmergePatchPairs ();\n"
    )


def render_toposet(cfg: dict[str, Any]) -> str:
    """One cellSet box enclosing the rotor disk and hub."""
    diameter = float(cfg["turbine"]["diameter"])
    origin = turbine_origin(cfg)
    minimum = (
        origin[0] - 0.5 * diameter,
        origin[1] - 1.0 * diameter,
        origin[2] - 1.0 * diameter,
    )
    maximum = (
        origin[0] + 0.5 * diameter,
        origin[1] + 1.0 * diameter,
        origin[2] + 1.0 * diameter,
    )
    return foam_header("topoSetDict") + f"""actions
(
    {{
        name turbine;
        type cellSet;
        action new;
        source boxToCell;
        box {foam_vector(minimum)} {foam_vector(maximum)};
    }}
);
"""


def render_control_dict(
    cfg: dict[str, Any],
    speed: str,
    mesh: str,
    profile: str,
    end_revs: float | None,
    start_from: str,
    sequence: str = "H",
    solver: str = "urans",
) -> str:
    values = kinematics(cfg, speed, mesh, sequence, solver)
    solver_cfg = cfg["solver"]
    if profile == "smoke":
        end_time = 2.0 * values["t_rev"]
        purge_write = 4
    else:
        end_time = (end_revs if end_revs is not None else float(solver_cfg["end_revolutions"])) * values["t_rev"]
        purge_write = int(solver_cfg["purge_write"])
    return foam_header("controlDict") + f"""application {solver_cfg['application']};
startFrom {start_from};
startTime 0;
stopAt endTime;
endTime {end_time:.8g};
deltaT {values['delta_t']:.8g};
writeControl runTime;
writeInterval {values['write_interval']:.8g};
purgeWrite {purge_write};
writeFormat ascii;
writePrecision 10;
writeCompression off;
timeFormat general;
timePrecision 8;
runTimeModifiable true;
adjustTimeStep off;

libs
(
    "libturbinesFoam.so"
);
"""


def render_fv_schemes(
    cfg: dict[str, Any], solver: str = "urans", div_phi_u: str | None = None
) -> str:
    """Cartesian-mesh schemes; backward ddt, linearUpwind for U.

    The IDDES variant switches U convection to the configured (non-dissipative)
    scheme and asks `wallDist` for the wall-normal vectors up front, because
    `IDDESDelta` reads `wallDist::n()`.

    `div_phi_u` overrides the convection scheme for a scheme-sensitivity
    ablation (e.g. `bounded Gauss linear`). Absent, the committed default
    `bounded Gauss linearUpwind grad(U)` is used. It is an ablation switch, not
    a physics default: the committed case never sets it.
    """
    scheme = "bounded Gauss linearUpwind grad(U)"
    wall_dist = "    method          meshWave;"
    if solver == "iddes":
        iddes = cfg["iddes"]
        scheme = str(iddes["div_phi_U"])
        if bool(iddes["wall_dist_n_required"]):
            wall_dist = "    method          meshWave;\n    nRequired       true;"
    if div_phi_u is not None:
        scheme = div_phi_u
    return foam_header("fvSchemes") + f"""ddtSchemes
{{
    default         backward;
}}

gradSchemes
{{
    default         Gauss linear;
    grad(U)         cellLimited Gauss linear 1;
}}

divSchemes
{{
    default         none;
    div(phi,U)      {scheme};
    div(phi,k)      bounded Gauss upwind;
    div(phi,omega)  bounded Gauss upwind;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}}

laplacianSchemes
{{
    default         Gauss linear orthogonal;
}}

interpolationSchemes
{{
    default         linear;
}}

snGradSchemes
{{
    default         orthogonal;
}}

wallDist
{{
{wall_dist}
}}
"""


def render_fv_solution(cfg: dict[str, Any]) -> str:
    """GAMG pressure, smoothSolver for the transported fields."""
    del cfg
    return foam_header("fvSolution") + """solvers
{
    p
    {
        solver          GAMG;
        tolerance       1e-7;
        relTol          0.05;
        smoother        DICGaussSeidel;
        cacheAgglomeration true;
        agglomerator    faceAreaPair;
        mergeLevels     1;
    }

    pFinal
    {
        $p;
        tolerance       1e-8;
        relTol          0;
    }

    "(U|k|omega)"
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-7;
        relTol          0.05;
    }

    "(U|k|omega)Final"
    {
        $U;
        tolerance       1e-8;
        relTol          0;
    }
}

PIMPLE
{
    momentumPredictor          yes;
    nOuterCorrectors           1;
    nCorrectors                2;
    nNonOrthogonalCorrectors   0;
    pRefCell                   0;
    pRefValue                  0;
}

relaxationFactors
{
    equations
    {
        U       0.9;
        k       0.7;
        omega   0.7;
    }
}
"""


def _simple_factors(nproc: int, extents: tuple[float, ...]) -> tuple[int, int, int]:
    """Split `nproc` along x/y/z so the subdomains stay as compact as possible.

    `simple` cuts the domain into `n` equal parts per axis, so the three factors
    must multiply to `nproc`, and a split that ignores the domain's shape produces
    slabs (86 = 2*43 forces 43 slices along x). The winner minimises the ratio of
    the longest to the shortest subdomain edge. `(nproc, 1, 1)` is always
    available, so a prime rank count is handled rather than rejected.
    """
    best: tuple[float, tuple[int, int, int]] | None = None
    for nx in range(1, nproc + 1):
        if nproc % nx:
            continue
        rest = nproc // nx
        for ny in range(1, rest + 1):
            if rest % ny:
                continue
            nz = rest // ny
            edges = [float(extents[0]) / nx, float(extents[1]) / ny,
                     float(extents[2]) / nz]
            score = max(edges) / min(edges)
            if best is None or score < best[0]:
                best = (score, (nx, ny, nz))
    assert best is not None
    return best[1]


def render_decompose_par(cfg: dict[str, Any], ranks: int | None = None) -> str:
    nproc = int(ranks) if ranks is not None else int(
        cfg["decomposition"]["number_of_subdomains"]
    )
    # `simple` rather than `scotch`: the mesh is a structured blockMesh, so a
    # geometric split keeps the subdomains axis-aligned and contiguous, which the
    # cost/benefit measurement on this cluster found best. The config can override
    # it for an experiment that wants the graph partitioner, which is how the IEA
    # 15 MW package exposes the same choice.
    method = cfg["decomposition"].get("method", "simple")
    # `simple` reads its factors from `simpleCoeffs`; a bare `n` at the top level of
    # decomposeParDict is ignored and the split then contradicts
    # numberOfSubdomains, which is how a run failed at `decomposePar`.
    coeffs = ""
    if method == "simple":
        breaks = cfg["mesh"]["breaks_D"]
        extents = tuple(
            float(breaks[axis][-1]) - float(breaks[axis][0])
            for axis in ("x", "y", "z")
        )
        nx, ny, nz = _simple_factors(nproc, extents)
        coeffs = (
            "\nsimpleCoeffs\n{\n"
            f"    n               ({nx} {ny} {nz});\n"
            "    delta           0.001;\n"
            "}\n"
        )
    return (
        foam_header("decomposeParDict")
        + f"""numberOfSubdomains {nproc};
method {method};
"""
        + coeffs
    )


def render_transport_properties(cfg: dict[str, Any]) -> str:
    nu = float(cfg["inflow"]["kinematic_viscosity"])
    return foam_header("transportProperties") + f"""transportModel Newtonian;

nu              nu [0 2 -1 0 0 0 0] {nu:.8g};
"""


def render_turbulence_properties(cfg: dict[str, Any], solver: str = "urans") -> str:
    """RAS kOmegaSST by default; LES kOmegaSSTIDDES for the Stage 3 variant.

    `kOmegaSSTIDDES::setDelta()` accepts only an IDDESDelta-based delta model
    (validated in `case_config.validate_config`), configured here as
    `delta IDDESDelta` with its `IDDESDeltaCoeffs` sub-dictionary.
    """
    if solver == "iddes":
        iddes = cfg["iddes"]
        model = cfg["solver"]["iddes_model"]
        return foam_header("turbulenceProperties") + f"""simulationType LES;

LES
{{
    LESModel {model};
    turbulence on;
    printCoeffs on;
    delta {iddes['delta']};

    {iddes['delta']}Coeffs
    {{
        Cw {float(iddes['delta_Cw']):.8g};
    }}
}}
"""
    model = cfg["solver"]["turbulence_model"]
    return foam_header("turbulenceProperties") + f"""simulationType RAS;

RAS
{{
    RASModel {model};
    turbulence on;
    printCoeffs on;
}}
"""


def render_field_uniform(cfg: dict[str, Any], speed: str, field: str) -> str:
    """0.org field dictionaries (uniform inflow, symmetry far field)."""
    velocity = float(speed)
    fields = inflow_fields(cfg, speed)
    far = "        type symmetryPlane;"
    if field == "U":
        dims = "[0 1 -1 0 0 0 0]"
        header = "volVectorField"
        internal = f"uniform ({velocity:.8g} 0 0)"
        inlet = f"type fixedValue;\n        value uniform ({velocity:.8g} 0 0);"
        outlet = (
            "type inletOutlet;\n"
            "        inletValue uniform (0 0 0);\n"
            f"        value uniform ({velocity:.8g} 0 0);"
        )
    elif field == "p":
        dims = "[0 2 -2 0 0 0 0]"
        header = "volScalarField"
        internal = "uniform 0"
        inlet = "type zeroGradient;"
        outlet = "type fixedValue;\n        value uniform 0;"
    elif field == "k":
        dims = "[0 2 -2 0 0 0 0]"
        header = "volScalarField"
        value = fields["k"]
        internal = f"uniform {value:.8g}"
        inlet = f"type fixedValue;\n        value uniform {value:.8g};"
        outlet = (
            "type inletOutlet;\n"
            "        inletValue uniform 0;\n"
            f"        value uniform {value:.8g};"
        )
    elif field == "omega":
        dims = "[0 0 -1 0 0 0 0]"
        header = "volScalarField"
        value = fields["omega"]
        internal = f"uniform {value:.8g}"
        inlet = f"type fixedValue;\n        value uniform {value:.8g};"
        outlet = (
            "type inletOutlet;\n"
            "        inletValue uniform 0;\n"
            f"        value uniform {value:.8g};"
        )
    elif field == "nut":
        dims = "[0 2 -1 0 0 0 0]"
        header = "volScalarField"
        internal = "uniform 0"
        inlet = "type fixedValue;\n        value uniform 0;"
        outlet = (
            "type inletOutlet;\n"
            "        inletValue uniform 0;\n"
            "        value uniform 0;"
        )
    else:
        raise ValueError(f"unknown field {field!r}")

    far_block = "\n".join(
        f"    {name}\n    {{\n{far}\n    }}"
        for name in ("bottom", "top", "sideMinus", "sidePlus")
    )
    return foam_header(field, header) + f"""dimensions      {dims};

internalField   {internal};

boundaryField
{{
    inlet
    {{
        {inlet}
    }}

    outlet
    {{
        {outlet}
    }}

{far_block}
}}
"""


# Source defaults of `axialFlowTurbineALSource` (`velocitySampleRadius` 0.0,
# `nVelocitySamples` 20) and of `profileData::updateRe` (`liftReCorrExp` 0.23).
# `config/case.yaml` carries the same values, so the committed render omits the
# three keys and stays byte-identical; the matching flags override them.
SAMPLE_RADIUS_DEFAULT = 0.0
SAMPLE_COUNT_DEFAULT = 20
LIFT_RE_CORR_EXP_DEFAULT = 0.23


def render_fv_options(
    cfg: dict[str, Any],
    speed: str,
    mesh: str,
    case_dir: Path,
    element_type: str,
    sequence: str = "H",
    n_chordwise: int | None = None,
    n_elements: int | None = None,
    surface_geometry: str | None = None,
    surface_kernel: str | None = None,
    rotational_augmentation: dict[str, Any] | None = None,
    root_effects: bool | None = None,
    tip_effects: bool | None = None,
    tip_correction: bool | None = None,
    hub_radius: float | None = None,
    polar: str | None = None,
    velocity_sample_radius: float | None = None,
    n_velocity_samples: int | None = None,
    lift_re_corr_exp: float | None = None,
) -> str:
    """ALM/ASM/ASM-mesh twins rendered from one function.

    The twins differ only in the blade keys: `elementType`, for the surface
    element `nChordwise`, and, when `surface_geometry` is set, the mesh-backed
    surface keys `surfaceGeometry` and, for the Gaussian ablation only,
    `kernel`. Path targets are found by
    `test_twins_differ_only_in_blade_keys`. `n_chordwise` overrides the
    configured ASM strip count (the ALM has no such key). `n_elements` overrides
    the configured blade spanwise element count (`nElements`) in every twin.
    `surface_kernel` defaults to the paper cosine kernel and only `gaussian`
    renders a `kernel` key. `projectElementForce` is never rendered: the blade source injects it
    into the element dicts when a surface is configured (design D3).

    `rotational_augmentation` defaults to the `actuator.rotational_augmentation`
    block; when configured (always, for the committed case) the
    `rotationalAugmentation` block is rendered identically in all three twins at
    the rotor-coeffs level (mirroring `dynamicStall`), so the twins stay
    identical except for the blade keys and AFTAL forwards the block with the
    radial geometry the element needs. `root_effects` defaults to
    `actuator.end_effects.root` and is the render-time ablation toggle (design
    D5, §6.2). `tip_effects` mirrors it and defaults to
    `actuator.end_effects.tip`. `hub_radius` overrides `actuator.hub_radius` and
    renders `hubRadius` at the rotor-coeffs level, beside `rotorRadius`, whenever
    it is configured, independent of the root-effect toggle; an absent value
    renders no key, and the source refuses a root effect with no hub radius.
    `tip_correction` renders the Dag &
    Sorensen `tipCorrection` block beside `endEffects` and defaults to
    `actuator.tip_correction.active` (off for the committed case).

    `velocity_sample_radius` and `n_velocity_samples` override the
    `actuator.velocity_sampling` block and render the two keys at the
    rotor-coeffs level, where `axialFlowTurbineALSource` reads them. The source
    defaults (0.0 and 20, i.e. no sampling) render no key, so the committed case
    stays byte-identical. `lift_re_corr_exp` overrides `profile.lift_re_corr_exp`
    and renders `liftReCorrExp` inside the `profileData/S809` subdict, beside the
    `Re` statement it modifies; the 0.23 source default renders no key.
    """
    values = kinematics(cfg, speed, mesh, sequence)
    turbine = cfg["turbine"]
    actuator = cfg["actuator"]
    origin = turbine_origin(cfg)
    # Reynolds-sensitivity ablation: `polar` selects another committed polar in
    # data/polars/ (e.g. S809_CSU_Re0.65M_total.dat). Absent, the committed
    # single-Re OSU Re = 1e6 baseline is used.
    polar_name = polar or "S809_OSU_Re1M_total.dat"
    polars = os.path.relpath(POLARS_DIR / polar_name, case_dir / "system")
    sampling = actuator.get("velocity_sampling") or {}
    sample_radius = (
        float(sampling.get("velocity_sample_radius", SAMPLE_RADIUS_DEFAULT))
        if velocity_sample_radius is None
        else float(velocity_sample_radius)
    )
    n_samples = (
        int(sampling.get("n_velocity_samples", SAMPLE_COUNT_DEFAULT))
        if n_velocity_samples is None
        else int(n_velocity_samples)
    )
    if sample_radius < 0.0:
        raise ValueError("velocitySampleRadius must be zero or positive")
    if n_samples <= 0:
        raise ValueError("nVelocitySamples must be a positive integer")
    sampling_block = ""
    if sample_radius != SAMPLE_RADIUS_DEFAULT or n_samples != SAMPLE_COUNT_DEFAULT:
        sampling_block = (
            f"\n        velocitySampleRadius {sample_radius:.8g};"
            f"\n        nVelocitySamples {n_samples};"
        )
    # `profileData` reads the exponent from its own subdict; the source default is
    # 0.23, so the committed render stays byte-identical.
    re_corr_cfg = cfg.get("profile") or {}
    lift_exp = (
        float(re_corr_cfg.get("lift_re_corr_exp", LIFT_RE_CORR_EXP_DEFAULT))
        if lift_re_corr_exp is None
        else float(lift_re_corr_exp)
    )
    re_corr_line = (
        ""
        if lift_exp == LIFT_RE_CORR_EXP_DEFAULT
        else f"\n                liftReCorrExp {lift_exp:.8g};"
    )
    profiles = " ".join(blade_element_profiles(cfg))
    if n_chordwise is None:
        n_chordwise = int(actuator["n_chordwise"])
    elif int(n_chordwise) <= 0:
        raise ValueError("nChordwise must be a positive integer")
    else:
        n_chordwise = int(n_chordwise)
    if n_elements is None:
        n_elements = int(actuator["n_elements"])
    elif int(n_elements) <= 0:
        raise ValueError("nElements must be a positive integer")
    else:
        n_elements = int(n_elements)
    if surface_kernel is not None and surface_kernel not in SURFACE_KERNELS:
        raise ValueError(
            f"unknown surface kernel {surface_kernel!r}; choose from "
            f"{list(SURFACE_KERNELS)}"
        )
    if surface_kernel is not None and surface_geometry is None:
        raise ValueError("surface_kernel requires surface_geometry")
    blade_keys = f"                elementType {element_type};\n"
    if element_type == ASM_ELEMENT:
        blade_keys += f"                nChordwise {n_chordwise};\n"
    if surface_geometry is not None:
        blade_keys += f'                surfaceGeometry "{surface_geometry}";\n'
        if surface_kernel == "gaussian":
            blade_keys += "                kernel gaussian;\n"
    dynamic = actuator["dynamic_stall"]
    end_effects = actuator["end_effects"]
    augmentation = (
        actuator.get("rotational_augmentation")
        if rotational_augmentation is None
        else rotational_augmentation
    )
    # Mirror `dynamicStall`: render the augmentation block at the rotor-coeffs
    # level so AFTAL forwards it into each blade subdict together with the
    # `rotorRadius`/`rootRadius` the element needs. Rendering it inside a blade
    # subdict bypasses that forwarding and the correction is silently skipped.
    if augmentation is None:
        augmentation_block = ""
    else:
        active = bool(augmentation["active"])
        augmentation_block = (
            "\n\n        rotationalAugmentation\n"
            "        {\n"
            f"            active {'on' if active else 'off'};\n"
            f"            model {augmentation['model']};\n"
            f"            a {float(augmentation['a']):.8g};\n"
            f"            b {float(augmentation['b']):.8g};\n"
            f"            d {float(augmentation['d']):.8g};\n"
            "        }"
        )
    root = bool(end_effects["root"]) if root_effects is None else bool(root_effects)
    tip = bool(end_effects["tip"]) if tip_effects is None else bool(tip_effects)
    # The Prandtl hub loss is built from the hub surface radius. `hubRadius`
    # is a property of the rotor, so it renders whenever it is configured,
    # independent of the root-effect toggle; a case that sets no value renders
    # no key (the source then refuses a root effect rather than invent one).
    hub_radius_value = (
        hub_radius if hub_radius is not None else actuator.get("hub_radius")
    )
    if hub_radius_value is not None:
        hub_radius_value = float(hub_radius_value)
        if hub_radius_value <= 0.0:
            raise ValueError("hubRadius must be positive")
    hub_radius_line = (
        f"\n        hubRadius {hub_radius_value:.8g};"
        if hub_radius_value is not None
        else ""
    )
    # Mirror `endEffects`: render the tip-correction switch at the rotor-coeffs
    # level (AFTAL reads it from `coeffs_`). Absent from the config, the block
    # falls back to the paper defaults with the switch off.
    correction = actuator.get("tip_correction") or {
        "active": False,
        "model": "DagSorensen",
        "wake_turns": 2,
        "wake_azimuthal_step": 2,
        "epsilon": 0,
    }
    correction_active = (
        bool(correction["active"])
        if tip_correction is None
        else bool(tip_correction)
    )
    tip_correction_block = (
        "\n\n        tipCorrection\n"
        "        {\n"
        f"            active {'on' if correction_active else 'off'};\n"
        f"            model {correction['model']};\n"
        f"            wakeTurns {int(correction['wake_turns'])};\n"
        "            wakeAzimuthalStep "
        f"{float(correction['wake_azimuthal_step']):.8g};\n"
        f"            epsilon {float(correction['epsilon']):.8g};\n"
        "        }"
    )
    hub_rows = "\n".join(
        "                (" + " ".join(f"{value:.9g}" for value in row) + ")"
        for row in hub_element_rows()
    )
    return foam_header("fvOptions") + f"""turbine
{{
    type axialFlowTurbineALSource;
    active on;

    axialFlowTurbineALSourceCoeffs
    {{
        fieldNames (U);
        selectionMode cellSet;
        cellSet turbine;
        origin {foam_vector(origin)};
        axis {foam_vector(turbine['axis'])};
        verticalDirection {foam_vector(turbine['vertical_direction'])};
        freeStreamVelocity ({values['speed']:.8g} 0 0);
        tipSpeedRatio {values['tsr']:.8g};
        rotorRadius {float(turbine['radius']):.8g};{hub_radius_line}
        azimuthalOffset 0;{sampling_block}

        dynamicStall
        {{
            active {'on' if dynamic['active'] else 'off'};
            dynamicStallModel {dynamic['model']};
        }}{augmentation_block}

        endEffects
        {{
            active {'on' if end_effects['active'] else 'off'};
            endEffectsModel {end_effects['model']};
            GlauertCoeffs
            {{
                tipEffects {'on' if tip else 'off'};
                rootEffects {'on' if root else 'off'};
            }}
        }}{tip_correction_block}

        blades
        {{
            blade1
            {{
                writePerf true;
                writeElementPerf true;
{blade_keys.rstrip()}
                nElements {n_elements};
                elementProfiles
                (
                    {profiles}
                );
                elementData
                (
{render_blade_element_data(cfg)}
                );
            }}
            blade2
            {{
                $blade1;
                writePerf false;
                writeElementPerf false;
                azimuthalOffset 180;
            }}
        }}

        hub
        {{
            nElements 4;
            elementProfiles (cylinder);
            elementData
            (
{hub_rows}
            );
        }}

        profileData
        {{
            S809
            {{
                Re 1e6;{re_corr_line}
                GaussianCoeffs
                {{
                    chordFactor 0.25;
                    dragFactor 1.0;
                    meshFactor {float(turbine['gaussian_mesh_factor']):.8g};
                }}
                data (#include "{polars}");
            }}
            cylinder {{ data ((-180 0 1.1 0) (180 0 1.1 0)); }}
        }}
    }}
}}
"""


def render_snappy_dict(cfg: dict[str, Any], level: int) -> str:
    """Castellated rotor-disk refinement, local to the rotor.

    `snappyHexMesh` refines one cylinder around the rotor and leaves the base
    `blockMesh` alone, so meshing stays cheap and the far field is never
    re-meshed. `snap` and `addLayers` are off: an actuator line has no surface to
    snap to or to grow layers on.

    The cylinder is sized by the actuator line's inflow sampling sphere at the
    tip, not by the chord, and `meshFactor` is scaled by `2**level` by the caller
    so that width stays fixed in metres.

    Level 0 still renders the dictionary, with `castellatedMesh false`, so every
    run directory states its refinement level instead of leaving it implicit.
    """
    refinement = cfg["mesh"]["refinement"]
    if level < 0:
        raise ValueError("refine level must be zero or positive")
    if level > int(refinement["max_level"]):
        raise ValueError(
            f"refine level {level} exceeds the configured maximum "
            f"{refinement['max_level']}"
        )
    hub = turbine_origin(cfg)
    half = float(refinement["disk_half_thickness_m"])
    regions = ""
    if level > 0:
        regions = (
            "\n        rotorDisk\n"
            "        {\n"
            "            mode inside;\n"
            f"            levels ((1e15 {level}));\n"
            "        }\n"
        )
    return (
        foam_header("snappyHexMeshDict")
        + f"""castellatedMesh {'true' if level > 0 else 'false'};
snap false;
addLayers false;

geometry
{{
    rotorDisk
    {{
        type searchableCylinder;
        point1 ({hub[0] - half:.9g} {hub[1]:.9g} {hub[2]:.9g});
        point2 ({hub[0] + half:.9g} {hub[1]:.9g} {hub[2]:.9g});
        radius {float(refinement['disk_radius_m']):.9g};
    }}
}}

castellatedMeshControls
{{
    maxLocalCells 40000000;
    maxGlobalCells 60000000;
    minRefinementCells 0;
    nCellsBetweenLevels 2;

    features ();

    refinementSurfaces
    {{
    }}

    resolveFeatureAngle 30;

    refinementRegions
    {{{regions}}}

    locationInMesh (0 0 0);
    allowFreeStandingZoneFaces true;
}}

snapControls
{{
    nSmoothPatch 3;
    tolerance 2.0;
    nSolveIter 30;
    nRelaxIter 5;
}}

addLayersControls
{{
    relativeSizes true;
    layers {{}}
    expansionRatio 1.0;
    finalLayerThickness 0.3;
    minThickness 0.1;
    nGrow 0;
    featureAngle 60;
    slipFeatureAngle 30;
    nRelaxIter 5;
    nSmoothSurfaceNormals 1;
    nSmoothNormals 3;
    nSmoothThickness 10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedianAxisAngle 90;
    nBufferCellsNoExtrude 0;
    nLayerIter 50;
}}

meshQualityControls
{{
    maxNonOrtho 65;
    maxBoundarySkewness 20;
    maxInternalSkewness 4;
    maxConcave 80;
    minVol 1e-13;
    minTetQuality 1e-15;
    minArea -1;
    minTwist 0.02;
    minDeterminant 0.001;
    minFaceWeight 0.02;
    minVolRatio 0.01;
    minTriangleTwist -1;
    nSmoothScale 4;
    errorReduction 0.75;
    relaxed {{}}
}}

debug 0;
mergeTolerance 1e-6;
"""
    )


def outputs(
    cfg: dict[str, Any],
    mesh: str,
    speed: str,
    domain: str,
    profile: str,
    case_dir: Path,
    end_revs: float | None,
    start_from: str,
    sequence: str = "H",
    solver: str = "urans",
    div_phi_u: str | None = None,
    n_chordwise: int | None = None,
    n_elements: int | None = None,
    ranks: int | None = None,
    surface_kernel: str = "cosine",
    rotational_augmentation: dict[str, Any] | None = None,
    root_effects: bool | None = None,
    tip_effects: bool | None = None,
    tip_correction: bool | None = None,
    hub_radius: float | None = None,
    polar: str | None = None,
    velocity_sample_radius: float | None = None,
    n_velocity_samples: int | None = None,
    lift_re_corr_exp: float | None = None,
    refine_level: int = 0,
) -> dict[Path, str]:
    system = case_dir / "system"
    constant = case_dir / "constant"
    zero = case_dir / "0.org"
    rendered: dict[Path, str] = {
        system / "blockMeshDict": render_block_mesh(cfg, mesh, domain, profile),
        system / "topoSetDict": render_toposet(cfg),
        system / "controlDict": render_control_dict(
            cfg, speed, mesh, profile, end_revs, start_from, sequence, solver
        ),
        system / "decomposeParDict": render_decompose_par(cfg, ranks),
        system / "fvSchemes": render_fv_schemes(cfg, solver, div_phi_u),
        system / "fvSolution": render_fv_solution(cfg),
        system / "fvOptions.ALM": render_fv_options(
            cfg, speed, mesh, case_dir, ALM_ELEMENT, sequence, n_chordwise,
            n_elements=n_elements,
            rotational_augmentation=rotational_augmentation,
            root_effects=root_effects,
            tip_effects=tip_effects,
            tip_correction=tip_correction,
            hub_radius=hub_radius,
            polar=polar,
            velocity_sample_radius=velocity_sample_radius,
            n_velocity_samples=n_velocity_samples,
            lift_re_corr_exp=lift_re_corr_exp,
        ),
        system / "fvOptions.ASM": render_fv_options(
            cfg, speed, mesh, case_dir, ASM_ELEMENT, sequence, n_chordwise,
            n_elements=n_elements,
            rotational_augmentation=rotational_augmentation,
            root_effects=root_effects,
            tip_effects=tip_effects,
            tip_correction=tip_correction,
            hub_radius=hub_radius,
            polar=polar,
            velocity_sample_radius=velocity_sample_radius,
            n_velocity_samples=n_velocity_samples,
            lift_re_corr_exp=lift_re_corr_exp,
        ),
        system / "fvOptions.ASM-MESH": render_fv_options(
            cfg,
            speed,
            mesh,
            case_dir,
            ASM_ELEMENT,
            sequence,
            n_chordwise,
            n_elements=n_elements,
            surface_geometry=SURFACE_GEOMETRY,
            surface_kernel=surface_kernel,
            rotational_augmentation=rotational_augmentation,
            root_effects=root_effects,
            tip_effects=tip_effects,
            tip_correction=tip_correction,
            hub_radius=hub_radius,
            velocity_sample_radius=velocity_sample_radius,
            n_velocity_samples=n_velocity_samples,
            lift_re_corr_exp=lift_re_corr_exp,
        ),
        system / "snappyHexMeshDict": render_snappy_dict(cfg, refine_level),
        constant / "transportProperties": render_transport_properties(cfg),
        constant / "turbulenceProperties": render_turbulence_properties(cfg, solver),
    }
    for field in ("U", "p", "k", "omega", "nut"):
        rendered[zero / field] = render_field_uniform(cfg, speed, field)
    return rendered


def check_outputs(rendered: dict[Path, str], case_dir: Path) -> bool:
    clean = True
    for path, expected in rendered.items():
        if not path.exists():
            print(f"missing generated file: {_display(path, case_dir)}", file=sys.stderr)
            clean = False
            continue
        current = path.read_text(encoding="utf-8")
        if current != expected:
            print(f"stale generated file: {_display(path, case_dir)}", file=sys.stderr)
            diff = difflib.unified_diff(
                current.splitlines(),
                expected.splitlines(),
                fromfile="current",
                tofile="expected",
                n=2,
            )
            print("\n".join(list(diff)[:40]), file=sys.stderr)
            clean = False
    return clean


def _display(path: Path, case_dir: Path) -> str:
    try:
        return str(path.relative_to(case_dir))
    except ValueError:
        return str(path)


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def _non_negative_float(value: str) -> float:
    number = float(value)
    if number < 0.0:
        raise argparse.ArgumentTypeError("must be zero or positive")
    return number


def _positive_float(value: str) -> float:
    number = float(value)
    if number <= 0.0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def _non_negative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or positive")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--mesh", choices=MESH_CHOICES, default="coarse")
    parser.add_argument("--speed", default="7")
    parser.add_argument("--sequence", choices=("H", "S"), default="H",
                        help="Sequence H headline or the Sequence S 7 m/s repeat")
    parser.add_argument("--domain", choices=DOMAIN_CHOICES, default="long")
    parser.add_argument("--profile", choices=PROFILE_CHOICES, default="production")
    parser.add_argument(
        "--solver",
        choices=SOLVER_CHOICES,
        default="urans",
        help="urans renders RAS kOmegaSST; iddes renders the Stage 3 LES "
             "kOmegaSSTIDDES variant with its own fixed time step",
    )
    parser.add_argument(
        "--polar",
        default=None,
        metavar="FILE",
        help="override the data/polars/ polar file for a Reynolds-sensitivity "
             "ablation (e.g. S809_CSU_Re0.65M_total.dat). Absent, the committed "
             "S809_OSU_Re1M_total.dat baseline is used",
    )
    parser.add_argument(
        "--div-phi-u",
        default=None,
        metavar="SCHEME",
        help="override the div(phi,U) convection scheme for a scheme-sensitivity "
             "ablation (e.g. 'bounded Gauss linear'). Absent, the committed "
             "'bounded Gauss linearUpwind grad(U)' is used; for --solver iddes "
             "the configured iddes.div_phi_U applies unless overridden",
    )
    parser.add_argument(
        "--n-chordwise",
        type=_positive_int,
        default=None,
        metavar="N",
        help="override the configured ASM chordwise strip count (ASM twin only)",
    )
    parser.add_argument(
        "--n-elements",
        type=_positive_int,
        default=None,
        metavar="N",
        help="override the configured blade spanwise element count (all twins)",
    )
    parser.add_argument(
        "--ranks",
        type=_positive_int,
        default=None,
        metavar="N",
        help="override decomposition.number_of_subdomains in decomposeParDict",
    )
    parser.add_argument(
        "--surface-kernel",
        choices=SURFACE_KERNELS,
        default="cosine",
        help="kernel of the ASM-mesh twin: cosine is the paper kernel "
             "(the default; no key is rendered), gaussian is the ablation "
             "and renders `kernel gaussian;`",
    )
    parser.add_argument(
        "--rotational-augmentation",
        choices=("on", "off"),
        default=None,
        help="render the Du-Selig rotational-augmentation switch; the default "
             "comes from config/case.yaml (off). `on`/`off` overrides it",
    )
    parser.add_argument(
        "--root-effects",
        choices=("on", "off"),
        default=None,
        help="render the Glauert root-effect setting; default from "
             "config/case.yaml (on). `off` is the render-time ablation",
    )
    parser.add_argument(
        "--tip-effects",
        choices=("on", "off"),
        default=None,
        help="render the Glauert tip-effect setting; default from "
             "config/case.yaml (on). `off` is the render-time ablation",
    )
    parser.add_argument(
        "--hub-radius",
        type=_positive_float,
        default=None,
        metavar="R",
        help="override the hub surface radius rendered as `hubRadius` for the "
             "Glauert Prandtl hub loss; the config/case.yaml value applies "
             "unless overridden. Rendered only while the root effect is on",
    )
    parser.add_argument(
        "--tip-correction",
        choices=("on", "off"),
        default=None,
        help="render the Dag & Sorensen tip-correction switch; default from "
             "config/case.yaml (off). `on` is the campaign arm",
    )
    parser.add_argument(
        "--velocity-sample-radius",
        type=_non_negative_float,
        default=None,
        metavar="R",
        help="override the actuator element inflow sampling radius, in units "
             "of the element projection epsilon; the config/case.yaml value "
             "(0.0, the source default, renders no key) applies unless "
             "overridden. The validated Phase VI method uses 3.3",
    )
    parser.add_argument(
        "--n-velocity-samples",
        type=_positive_int,
        default=None,
        metavar="N",
        help="override the number of inflow samples per element; the "
             "config/case.yaml value (20, the source default, renders no key) "
             "applies unless overridden. The validated Phase VI method uses 16",
    )
    parser.add_argument(
        "--lift-re-corr-exp",
        type=_non_negative_float,
        default=None,
        metavar="N",
        help="override the profileData Reynolds-rescaling exponent; the "
             "config/case.yaml value (0.23, the source default, renders no key) "
             "applies unless overridden. The Phase VI validation uses 0 to "
             "disable the rescaling that the declared `Re 1e6` would apply",
    )
    parser.add_argument(
        "--refine-level",
        type=_non_negative_int,
        default=0,
        metavar="N",
        help="castellated snappyHexMesh refinement level of the rotor-disk "
             "cylinder; 0 renders the dictionary with no refinement. Each level "
             "halves the cell in the rotor region, and gaussian_mesh_factor is "
             "scaled by 2**N so the actuator line's projection width stays fixed "
             "in metres and the mesh is the only variable",
    )
    parser.add_argument(
        "--delta-t",
        type=_positive_float,
        default=None,
        metavar="T",
        help="override the configured fixed time step. The mesh-convergence "
             "ladder fixes it at the finest level's requirement so that the time "
             "discretisation does not shrink with the mesh",
    )
    parser.add_argument("--case-dir", type=Path, default=DEFAULT_CASE_DIR)
    parser.add_argument("--end-revs", type=float, default=None)
    parser.add_argument("--start-from", choices=START_FROM_CHOICES, default="startTime")
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail (exit 1) if generated files are missing or stale; never writes",
    )
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
        case_dir = args.case_dir.resolve()
        # Campaign overrides for the mesh-convergence ladder. Both leave the
        # committed default render byte-identical: level 0 scales by 2**0 = 1, and
        # an absent --delta-t changes nothing.
        if args.refine_level:
            cfg["turbine"]["gaussian_mesh_factor"] = float(
                cfg["turbine"]["gaussian_mesh_factor"]
            ) * 2.0 ** int(args.refine_level)
        if args.delta_t is not None:
            cfg["mesh"]["resolutions"][args.mesh]["delta_t"] = float(args.delta_t)
        augmentation = dict(cfg["actuator"]["rotational_augmentation"])
        if args.rotational_augmentation is not None:
            augmentation["active"] = args.rotational_augmentation == "on"
        root_effects = (
            None if args.root_effects is None else args.root_effects == "on"
        )
        tip_effects = (
            None if args.tip_effects is None else args.tip_effects == "on"
        )
        tip_correction = (
            None if args.tip_correction is None else args.tip_correction == "on"
        )
        rendered = outputs(
            cfg,
            args.mesh,
            args.speed,
            args.domain,
            args.profile,
            case_dir,
            args.end_revs,
            args.start_from,
            args.sequence,
            solver=args.solver,
            div_phi_u=args.div_phi_u,
            n_chordwise=args.n_chordwise,
            n_elements=args.n_elements,
            ranks=args.ranks,
            surface_kernel=args.surface_kernel,
            rotational_augmentation=augmentation,
            root_effects=root_effects,
            tip_effects=tip_effects,
            tip_correction=tip_correction,
            hub_radius=args.hub_radius,
            polar=args.polar,
            velocity_sample_radius=args.velocity_sample_radius,
            n_velocity_samples=args.n_velocity_samples,
            lift_re_corr_exp=args.lift_re_corr_exp,
            refine_level=args.refine_level,
        )
    except (KeyError, ValueError) as exc:
        print(f"case generation error: {exc}", file=sys.stderr)
        return 2

    if args.check:
        return 0 if check_outputs(rendered, case_dir) else 1

    for path, content in rendered.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(_display(path, ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
