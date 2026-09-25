#!/usr/bin/env python3
"""Wire the ASM FSI layer into a rendered Phase VI ASM-MESH run directory.

The base case (rendered by phaseVI/scripts/runPhaseVI.sh -m asm-mesh) has no
FSI layer. This tool adds it, reproducibly, for the three smoke cases:

    --blades 1 [--static]     one blade, no rotation
    --blades 2 [--static]     two blades, no rotation
    --blades 2                two blades, rotor spinning

It modifies the run directory in place:

    system/fvOptions     add the 'fsi' block per blade (distinct field names)
    system/preciceDict   one pointCloud interface per blade
    system/controlDict   load the adapter, add the function object
    <case>/precice-config.xml   copied from the harness
    solid-meshes.dat     the dummy's mesh list (mesh name + coordinates file)

The blade subdictionaries carry 'surface<i>Coords' etc.; the sampler writes
the reference cloud to 'coords-blade<i>.dat' at FSI init (coordinateFile), so
the dummy registers exactly the fluid point cloud.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]


def find_block(text: str, name: str) -> tuple[int, int, int] | None:
    """(headerStart, bracePos, end) of the '{ ... }' block named `name`.

    `headerStart` is the beginning of the header line, `bracePos` the opening
    brace and `end` the position just after the matching closing brace.
    """
    m = re.search(
        r"(?m)^[ \t]*" + re.escape(name) + r"\s*\{", text
    )
    if not m:
        return None

    brace = text.index("{", m.start())
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return (m.start(), brace, i + 1)
    return None


def insert_after_open(text: str, name: str, payload: str) -> str:
    """Insert `payload` right after the opening brace of the `name` block."""
    block = find_block(text, name)
    if block is None:
        raise SystemExit(f"wire_case: block '{name}' not found")
    _, brace, _ = block
    return text[: brace + 1] + payload + text[brace + 1 :]


def insert_after_inheritance(text: str, name: str, payload: str) -> str:
    """Insert `payload` after the '$otherDict;' entry inside the `name` block.

    A subdictionary that inherits with '$blade1;' must override the inherited
    entries AFTER the inclusion: OpenFOAM applies the inclusion in place, so an
    entry written before it would be overwritten by the inherited one.
    """
    block = find_block(text, name)
    if block is None:
        raise SystemExit(f"wire_case: block '{name}' not found")
    _, brace, end = block

    m = re.search(r"\$[A-Za-z0-9_]+;", text[brace:end])
    if not m:
        # no inheritance: fall back to right after the opening brace
        return text[: brace + 1] + payload + text[brace + 1 :]

    pos = brace + m.end()
    return text[:pos] + payload + text[pos:]


def remove_block(text: str, name: str) -> str:
    """Remove the whole `name` block, header line included."""
    block = find_block(text, name)
    if block is None:
        raise SystemExit(f"wire_case: block '{name}' not found")
    header_start, _, end = block
    return text[:header_start] + text[end:].lstrip("\n")


def fsi_block(blade_index: int) -> str:
    return (
        "\n            fsi\n"
        "            {\n"
        f"                coordinateField   surface{blade_index}Coords;\n"
        f"                forceField        surface{blade_index}Forces;\n"
        f"                displacementField surface{blade_index}Displacement;\n"
        f'                coordinateFile    "coords-blade{blade_index}.dat";\n'
        "            }\n"
    )


def write_precice_dict(run: Path, blades: list[int]) -> None:
    interfaces = []
    for i in blades:
        interfaces.append(
            f"""    Blade{i}
    {{
        mesh            Blade{i}-Fluid;
        locations       pointCloud;
        coordinateField surface{i}Coords;

        writeData
        (
            Force
            {{
                name        Force;
                solver_name surface{i}Forces;
            }}
        );

        readData
        (
            Displacement
            {{
                name        Displacement;
                solver_name surface{i}Displacement;
            }}
        );
    }};"""
        )

    text = (
        '/*--------------------------------*- C++ -*----------------------------------*\\\n'
        "| =========                 |                                                 |\n"
        "| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |\n"
        "|  \\\\    /   O peration     | Website:  www.openfoam.com                      |\n"
        "|   \\\\  /    A nd           | Version:  v2506                                 |\n"
        "|    \\\\/     M anipulation  |                                                 |\n"
        "\\*---------------------------------------------------------------------------*/\n"
        "FoamFile\n"
        "{\n"
        "    version     2.0;\n"
        "    format      ascii;\n"
        "    class       dictionary;\n"
        "    object      preciceDict;\n"
        "}\n"
        "// Generated by fsi-smoke/scripts/wire_case.py\n\n"
        'preciceConfig "precice-config.xml";\n'
        "participant        Fluid;\n"
        "modules            (generic);\n\n"
        "interfaces\n"
        "{\n"
        + "\n".join(interfaces)
        + "\n};\n"
    )

    (run / "system" / "preciceDict").write_text(text)


def patch_control_dict(run: Path) -> None:
    path = run / "system" / "controlDict"
    text = path.read_text()

    if "libpreciceAdapterFunctionObject.so" not in text:
        text = text.replace(
            'libs\n(\n    "libturbinesFoam.so"\n);',
            'libs\n(\n    "libturbinesFoam.so"\n'
            '    "libpreciceAdapterFunctionObject.so"\n);',
        )

    if "preCICE_Adapter" not in text:
        text += (
            "\nfunctions\n"
            "{\n"
            "    preCICE_Adapter\n"
            "    {\n"
            "        type preciceAdapterFunctionObject;\n"
            "    }\n"
            "}\n"
        )

    path.write_text(text)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--blades", type=int, choices=(1, 2), required=True)
    parser.add_argument("--static", action="store_true",
                        help="zero the tip-speed ratio (no rotation)")
    parser.add_argument("--config", type=Path, default=None,
                        help="preCICE config to install (default per blade count)")
    args = parser.parse_args(argv[1:])

    run = args.run_dir.resolve()
    fvopts = run / "system" / "fvOptions"
    if not fvopts.is_file():
        raise SystemExit(f"wire_case: {fvopts} not found (render the base case)")

    blades = list(range(1, args.blades + 1))

    # ---- fvOptions ---------------------------------------------------------
    text = fvopts.read_text()

    if args.blades == 1:
        text = remove_block(text, "blade2")

    # blade2 inherits blade1 with '$blade1'; the fsi payload is inserted into
    # blade1, then blade2's explicit override is inserted first so the
    # inheritance does not copy blade1's field names
    text = insert_after_open(text, "blade1", fsi_block(1))
    if args.blades == 2:
        text = insert_after_inheritance(text, "blade2", fsi_block(2))

    if args.static:
        text = re.sub(r"tipSpeedRatio\s+[0-9.eE+-]+", "tipSpeedRatio 0", text)

    fvopts.write_text(text)

    # ---- preciceDict, controlDict, config ---------------------------------
    write_precice_dict(run, blades)
    patch_control_dict(run)

    config = args.config
    if config is None:
        config = HARNESS / ("precice-config.xml" if args.blades == 1
                            else "precice-config-2blade.xml")
    shutil.copyfile(config, run / "precice-config.xml")

    # ---- dummy mesh list ---------------------------------------------------
    with (run / "solid-meshes.dat").open("w") as fh:
        fh.write("# meshName coordinatesFile\n")
        for i in blades:
            fh.write(f"Blade{i}-Solid coords-blade{i}.dat\n")

    print(f"wire_case: wired {args.blades} blade(s)"
          f"{' (static)' if args.static else ''} into {run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
