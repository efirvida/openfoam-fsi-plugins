#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the IEA-22 OpenFAST v5.0.0 input templates (BEM and OLAF share them).

The v5.0.0 file *layout* comes from the committed IEA-15 templates
(``iea15mw/data/openfast-v5-templates``, validated against the v5.0.0 binary);
the *values* come from the read-only IEA-22-280-RWT repository
(``OpenFAST/IEA-22-280-RWT-Monopile`` + ``OpenFAST/IEA-22-280-RWT``). The source
files are untrusted data: they are only read, never executed, and the tower
table and the ElastoDyn tower file are copied as text.

What is set here (and why) is listed in ``data/openfast-v5-templates/README.md``;
what ``scripts/openfast_iea22.py`` rewrites per case (rotor speed, pitch, wind
speed, time step, OLAF sizing) is only a placeholder in the templates.

    python -I build_openfast_templates.py [--source-root DIR] [--out DIR] [--check]
"""
from __future__ import annotations

import argparse
import difflib
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
IEA15_TEMPLATES = PACKAGE.parent / "iea15mw" / "data" / "openfast-v5-templates"
DEFAULT_OUT = PACKAGE / "data" / "openfast-v5-templates"
DEFAULT_SOURCE = Path(
    os.environ.get("IEA22MW_SOURCE_ROOT", "/scratch/leahk/eduardo.donestevez/simulations/tmp/iea22-src/repo")
)

BASE15 = "IEA-15-240-RWT-OLAF_rated"
ROOT = "IEA-22-280-RWT-OLAF_rated"

#: Rated operating point (PROVENANCE.md, WISDEM rated row).
RATED_U = 11.134927
RATED_RPM = 6.853997
RATED_PITCH = 4.127462
HUB_HEIGHT = 170.0
ROTOR_RADIUS = 142.0
N_STATIONS = 59

#: ElastoDyn keys whose value is the IEA-22 monopile value (geometry, mass, drivetrain).
ED_SOURCE_KEYS = (
    "TipRad", "HubRad", "PreCone(1)", "PreCone(2)", "PreCone(3)", "HubCM", "OverHang", "ShftGagL",
    "ShftTilt", "NacCMxn", "NacCMyn", "NacCMzn", "Twr2Shft", "TowerHt", "TowerBsHt",
    "PtfmCMxt", "PtfmCMyt", "PtfmCMzt", "PtfmRefzt",
    "HubMass", "HubIner", "GenIner", "NacMass", "NacYIner", "YawBrMass",
    "GBRatio", "DTTorSpr", "DTTorDmp", "TwrNodes",
)

#: Blade-1 nodal outputs written to the ``.out`` file (one channel per AeroDyn node).
ROTOR_OUTLIST = (
    "RtAeroPwr", "RtAeroFxh", "RtAeroMxh", "RtAeroCp", "RtAeroCt", "RtFldCp", "RtFldCt",
    "RtArea", "RtVAvgxh", "RtSpeed", "RtTSR",
)
BLADE_OUT_NODES = (8, 15, 22, 30, 38, 45, 50, 55, 59)


def set_value(text: str, key: str, value: str) -> str:
    """Replace the leading value of the input line that documents ``key``."""
    pattern = re.compile(rf"^(\s*)\S+(\s+{re.escape(key)}(?!\w))", re.M)
    new, count = pattern.subn(lambda m: f"{m.group(1)}{value}{m.group(2)}", text, count=1)
    if count != 1:
        raise KeyError(key)
    return new


def get_value(text: str, key: str) -> str:
    match = re.search(rf"^\s*(\S+)\s+{re.escape(key)}(?!\w)", text, re.M)
    if match is None:
        raise KeyError(key)
    return match.group(1)


def _lines_between(text: str, start_pattern: str, stop_pattern: str) -> tuple[int, int, list[str]]:
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if re.search(start_pattern, l))
    stop = next(i for i in range(start + 1, len(lines)) if re.search(stop_pattern, lines[i]))
    return start, stop, lines


def build_elastodyn(base: str, src: str) -> str:
    text = base
    text = set_value(text, "RotSpeed", f"{RATED_RPM}")
    for blade in (1, 2, 3):
        text = set_value(text, f"BlPitch({blade})", f"{RATED_PITCH}")
    for key in ED_SOURCE_KEYS:
        text = set_value(text, key, get_value(src, key))
    # Rigid-rotor reference (the turbinesFoam ALM/ASM blades are rigid): no structural DOF.
    for dof in ("FlapDOF1", "FlapDOF2", "EdgeDOF"):
        text = set_value(text, dof, "False")
    for blade in (1, 2, 3):
        text = set_value(text, f"BldFile{blade}", f'"{ROOT}_ElastoDyn_blade.dat"')
    text = set_value(text, "TwrFile", f'"{ROOT}_ElastoDyn_tower.dat"')
    text = set_value(text, "SumPrint", "False")
    return text.replace("IEA 15 MW offshore reference model monopile configuration",
                        "IEA 22 MW offshore reference model monopile configuration (rigid rotor, fixed speed)")


def build_fst(base: str) -> str:
    text = base.replace("IEA 15 MW offshore reference model monopile configuration",
                        "IEA 22 MW offshore reference model monopile (standalone aerodynamics, rigid rotor)")
    text = set_value(text, "DT", "0.05")
    text = set_value(text, "DT_Out", "default")
    text = set_value(text, "OutFmt", '"ES15.7E2"')  # 8 significant digits: the revolution means are not rounded to 4
    text = set_value(text, "KinVisc", "1.4775510204081632e-05")
    text = set_value(text, "SpdSound", "340")
    text = set_value(text, "EDFile", f'"{ROOT}_ElastoDyn.dat"')
    for blade in (1, 2, 3):
        text = set_value(text, f"BDBldFile({blade})", '"unused"')
    text = set_value(text, "InflowFile", f'"{ROOT}_InflowFile.dat"')
    text = set_value(text, "AeroFile", f'"{ROOT}_AeroDyn15.dat"')
    return text


def build_inflow(base: str) -> str:
    text = base.replace("IEA 15 MW Offshore Reference Turbine", "IEA 22 MW Offshore Reference Turbine")
    text = set_value(text, "HWindSpeed", f"{RATED_U}")
    for key in ("WindVziList", "RefHt", "RefHt_Uni", "RefHt_Hawc"):
        text = set_value(text, key, f"{HUB_HEIGHT}")
    text = set_value(text, "RefLength", f"{2 * ROTOR_RADIUS}")
    return set_value(text, "PLexp", "0.0")


def olaf_sizing(rpm: float, speed: float, diameter: float = 2 * ROTOR_RADIUS) -> dict[str, float]:
    """Guideline sizing (v5.0.0 docs, RunningOLAF "Guidelines"; as in phaseVI)."""
    period = 60.0 / rpm
    dt = period / 60.0  # 6 deg per step
    convection = 0.5 * speed
    near = max(round(4.0 * diameter / (convection * dt)), 10 * 60)
    free = round(2.0 * diameter / (convection * dt))
    return {"dt": dt, "period": period, "near": int(near), "free": int(free), "full_circ_start": period}


def build_olaf(base: str) -> str:
    size = olaf_sizing(RATED_RPM, RATED_U)
    text = base.replace("Free wake input file for the Helix test case",
                        "IEA 22 MW rated point; guideline sizing (placeholders rewritten per case)")
    text = set_value(text, "DTfvw", f"{size['dt']:.6f}")
    text = set_value(text, "FullCircStart", f"{size['full_circ_start']:.4f}")
    text = set_value(text, "nNWPanel", f"{size['near']}")
    text = set_value(text, "nNWPanelsFree", f"{size['free']}")
    return text


def build_aerodyn(base: str, src_ad: str) -> str:
    text = base.replace("IEA 15 MW Offshore Reference Turbine", "IEA 22 MW Offshore Reference Turbine")
    text = set_value(text, "BEM_Mod", get_value(src_ad, "BEM_Mod"))  # polar BEM (IEA-22 value; IEA-15 template had 1)
    text = set_value(text, "DBEMT_Mod", "0")
    text = set_value(text, "UA_Mod", "0")  # quasi-steady, as the ALM/ASM (no dynamic stall)
    text = set_value(text, "AoA34", "False")  # AC-node angle of attack; only matters with UA
    text = set_value(text, "OLAFInputFileName", f"{ROOT}_OLAF.dat")
    text = set_value(text, "NumAFfiles", str(N_STATIONS))
    start, stop, lines = _lines_between(text, r"AFNames", r"^======\s+Rotor/Blade")
    names = [f'"Airfoils/IEA-22-280-RWT_AeroDyn15_Polar_{i:02d}.dat"' for i in range(N_STATIONS)]
    lines[start] = f"{names[0]}    AFNames            - Airfoil file names (NumAFfiles lines) (quoted strings)"
    lines[start + 1:stop] = names[1:]
    text = "\n".join(lines) + "\n"
    for blade in (1, 2, 3):
        text = set_value(text, f"ADBlFile({blade})", '"IEA-22-280-RWT_AeroDyn15_blade.dat"')
    # Tower table from the IEA-22 monopile AeroDyn file; TwrCp/TwrCa columns (v5.0.0) are zero.
    rows = []
    in_table = False
    for line in src_ad.splitlines():
        fields = line.split()
        if fields[:1] == ["TwrElev"]:
            in_table = True
            continue
        if in_table and fields[:1] == ["(m)"]:
            continue
        if in_table:
            if len(fields) != 5 or not _is_float(fields[0]):
                break
            rows.append("  ".join(f"{float(v):.6g}" if i else f"{float(v):.4f}" for i, v in enumerate(fields)) + "  0.0  0.0")
    if not rows:
        raise ValueError("IEA-22 AeroDyn tower table not found")
    text = set_value(text, "NumTwrNds", str(len(rows)))
    start, stop, lines = _lines_between(text, r"^\(m\)\s+\(m\)", r"^======\s+Outputs")
    lines[start + 1:stop] = rows
    text = "\n".join(lines) + "\n"
    text = set_value(text, "NBlOuts", str(len(BLADE_OUT_NODES)))
    text, count = re.subn(r"^.*?(\s+BlOutNd\s+-)", lambda m: ", ".join(str(n) for n in BLADE_OUT_NODES) + m.group(1), text, count=1, flags=re.M)
    if count != 1:
        raise KeyError("BlOutNd")
    start, stop, lines = _lines_between(text, r"^\s+OutList\s", r"^END of input file")
    lines[start + 1:stop] = [f'"{name}"' for name in ROTOR_OUTLIST]
    return "\n".join(lines) + "\n"


def _is_float(token: str) -> bool:
    try:
        float(token)
    except ValueError:
        return False
    return True


def build_all(source_root: Path, base_dir: Path = IEA15_TEMPLATES) -> dict[str, str]:
    monopile = source_root / "OpenFAST" / "IEA-22-280-RWT-Monopile"
    read = lambda p: p.read_text(encoding="utf-8")  # noqa: E731
    src_ed = read(monopile / "IEA-22-280-RWT_ElastoDyn.dat")
    src_ad = read(monopile / "IEA-22-280-RWT_AeroDyn15.dat")
    tower = read(monopile / "IEA-22-280-RWT_ElastoDyn_tower.dat")
    base = lambda suffix: read(base_dir / f"{BASE15}{suffix}")  # noqa: E731
    files = {
        f"{ROOT}.fst": build_fst(base(".fst")),
        f"{ROOT}_ElastoDyn.dat": build_elastodyn(base("_ElastoDyn.dat"), src_ed),
        f"{ROOT}_ElastoDyn_tower.dat": tower if tower.endswith("\n") else tower + "\n",
        f"{ROOT}_InflowFile.dat": build_inflow(base("_InflowFile.dat")),
        f"{ROOT}_AeroDyn15.dat": build_aerodyn(base("_AeroDyn15.dat"), src_ad),
        f"{ROOT}_OLAF.dat": build_olaf(base("_OLAF.dat")),
    }
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--base", type=Path, default=IEA15_TEMPLATES, help="IEA-15 v5.0.0 template directory (layout)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true", help="fail if the committed templates are stale")
    args = parser.parse_args(argv)
    files = build_all(args.source_root, args.base)
    if args.check:
        stale = 0
        for name, text in files.items():
            path = args.out / name
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != text:
                stale += 1
                diff = difflib.unified_diff(current.splitlines(), text.splitlines(), str(path), "rebuilt", lineterm="", n=0)
                print("\n".join(list(diff)[:12]), file=sys.stderr)
        print(f"{len(files) - stale}/{len(files)} templates up to date")
        return 1 if stale else 0
    args.out.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (args.out / name).write_text(text, encoding="utf-8")
    print(f"wrote {len(files)} templates to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
