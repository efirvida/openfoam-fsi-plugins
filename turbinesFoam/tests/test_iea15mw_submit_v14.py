# SPDX-License-Identifier: GPL-3.0-or-later
"""The v1.4 IEA ASM / ASM+mesh D&S submit script: dry run by default, one rule set per run."""

from __future__ import annotations

import subprocess
from pathlib import Path

IEA = Path(__file__).resolve().parents[1] / "validation" / "iea15mw"
SUBMIT = IEA / "scripts" / "submit_v14_asm_ds.sh"
SLURM = IEA / "scripts" / "slurm" / "l2-ds-surface.slurm"


def dry_run() -> list[str]:
    result = subprocess.run(["sh", str(SUBMIT)], capture_output=True, text=True, check=True, cwd="/")
    return result.stdout.splitlines()


def test_dry_run_prints_two_sbatch_commands_and_submits_nothing():
    lines = dry_run()
    assert len(lines) == 2
    assert all(line.startswith("sbatch ") for line in lines)


def test_partitions_are_balanced_and_labels_match():
    asm, mesh = dry_run()
    assert "--partition=sequana_cpu " in asm and "--job-name=iea15mw-asm-l2-ds " in asm
    assert "--partition=sequana_cpu_bigmem " in mesh and "--job-name=iea15mw-asm-mesh-l2-ds " in mesh
    assert "TURBINE_MODEL=asm," in asm and "TURBINE_MODEL=asm-mesh," in mesh


def test_commands_follow_the_slurm_rules():
    for line in dry_run():
        assert "--exclude=sdumont6006,sdumont6009,sdumont6029" in line
        assert "--time=36:00:00" in line
        assert "--nodes" not in line and "--mem" not in line


def test_slurm_script_carries_the_ds_arm_and_96_ranks():
    text = SLURM.read_text(encoding="utf-8")
    assert "#SBATCH --ntasks=96" in text
    assert "--nodes" not in text and "--mem" not in text
    for knob in ("TURBINE_TIP_EFFECTS=off", "TURBINE_TIP_CORRECTION=on", "TURBINE_ROOT_EFFECTS=on",
                 "TURBINE_REQUEUE=0", "TURBINE_WRITE_DEG=120"):
        assert knob in text
