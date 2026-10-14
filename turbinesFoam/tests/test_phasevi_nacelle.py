"""Contracts for the opt-in Phase VI nacelle (`--nacelle on|off`)."""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

import yaml

TESTS_DIR = Path(__file__).resolve().parent
PACKAGE = TESTS_DIR.parent / "validation" / "phaseVI"
GENERATOR = PACKAGE / "tools" / "generate_case.py"
RUNNER = PACKAGE / "scripts" / "runPhaseVI.sh"
NACELLE_CFG = PACKAGE / "config" / "nacelle.yaml"

# sha256 (polar include path normalised) of the files rendered by the generator BEFORE the --nacelle option
# existed (mesh coarse, 7 m/s, long domain, Sequence H, urans, 84 ranks).
FROZEN = {
    "system/fvOptions.ALM": "f8daa995e4320e204d7564fa1df5068d231abba333ce221a88decc956c5d7ec8",
    "system/fvOptions.ASM": "470d6495816f17236d512d766e50242d80a40851b3e66f52775c867b824206e1",
    "system/fvOptions.ASM-MESH": "4b69de50fc88fe6f35de20f89de03b3b44ec19d4c2fedb2bda5a058c917276dc",
    "system/topoSetDict": "0f50b3621b2fc4c0c0aa8b42f2c77bfd8d1e66fd6aa3e30505dc675ad6fc82ca",
    "system/snappyHexMeshDict": "7abef0c957ac87d6064e0a4d6e37c646cb84779abcd1b42f4b62d6c84e8ffcfd",
}


def render(tmp_path: Path, *extra: str) -> Path:
    case = tmp_path / "case"
    subprocess.run(
        [sys.executable, str(GENERATOR), "--mesh", "coarse", "--speed", "7",
         "--domain", "long", "--sequence", "H", "--case-dir", str(case),
         "--solver", "urans", "--ranks", "84", *extra],
        check=True, capture_output=True, text=True,
    )
    return case


def normalised(path: Path) -> str:
    """Text with the case-location-dependent polar include path neutralised."""
    return re.sub(r'#include "[^"]*/data/polars/', '#include "POLARS/', path.read_text())


def sha(path: Path) -> str:
    return hashlib.sha256(normalised(path).encode()).hexdigest()


def test_default_and_off_renders_are_byte_identical_to_the_frozen_baseline(tmp_path):
    default = render(tmp_path / "a")
    off = render(tmp_path / "b", "--nacelle", "off")
    for name, digest in FROZEN.items():
        assert sha(default / name) == digest, name
        assert sha(off / name) == digest, name
    assert "nacelle" not in normalised(off / "system/fvOptions.ALM")


def test_on_adds_the_nacelle_subdict_with_the_stl_path(tmp_path):
    case = render(tmp_path, "--nacelle", "on")
    for twin in ("ALM", "ASM", "ASM-MESH"):
        text = (case / f"system/fvOptions.{twin}").read_text()
        assert re.search(r"nacelle\s*\{", text), twin
        assert 'geometry "constant/triSurface/phaseVI_nacelle.stl";' in text
        assert "bodyAxis (1 0 0);" in text
    alm = normalised(case / "system/fvOptions.ALM")
    off = render(tmp_path / "off", "--nacelle", "off")
    off_alm = normalised(off / "system/fvOptions.ALM")
    start = alm.index("\n\n        nacelle\n")
    end = alm.index("        }", start + 40) + len("        }")
    assert alm[:start] + alm[end:] == off_alm   # only the nacelle block differs


def test_committed_stl_sits_downstream_of_the_rotor_inside_the_cell_set():
    import struct
    cfg = yaml.safe_load(NACELLE_CFG.read_text())["nacelle"]
    data = (PACKAGE / cfg["stl"]).read_bytes()
    (count,) = struct.unpack("<I", data[80:84])
    xs, ys, zs = [], [], []
    for i in range(count):
        values = struct.unpack("<12f", data[84 + 50 * i:84 + 50 * i + 48])
        for k in range(3):
            xs.append(values[3 + 3 * k]); ys.append(values[4 + 3 * k]); zs.append(values[5 + 3 * k])
    case = yaml.safe_load((PACKAGE / "config" / "case.yaml").read_text())["turbine"]
    half = 0.5 * case["diameter"]
    assert min(xs) > 0.0                       # downstream of the rotor plane (x = 0)
    assert abs(min(xs) - cfg["front_offset_m"]) < 1e-5
    assert max(xs) < half                      # inside the `turbine` cellSet box
    assert abs((max(zs) + min(zs)) / 2 - case["hub_height"]) < 1e-4
    assert abs((max(ys) - min(ys)) / 2 - cfg["radius_m"]) < 1e-4


def test_runner_exposes_nacelle_and_records_it_in_run_json():
    text = RUNNER.read_text()
    assert "--nacelle)" in text
    assert '"nacelle":' in text
    assert "phaseVI_nacelle.stl" in text
    assert "--nacelle on|off" in text
