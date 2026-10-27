#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Code verification of the installed OpenFAST AeroDyn driver against the r-test references.

Runs every r-test `modules/aerodyn/<case>` whose AeroDyn primary file has `Wake_Mod = 1` (BEMT)
with the installed `aerodyn_driver` (in a scratch copy, never in the r-test checkout) and compares
`ad_driver*.outb` with the committed reference using the OpenFAST regression rule of
`reg_tests/lib/pass_fail.py::passing_channels` and `reg_tests/executeAerodynRegressionCase.py`
(OpenFAST v5.0.0), reproduced here:

    rtol = 10**-RTOL_MAGNITUDE                         RTOL_MAGNITUDE = 2    (CTEST_RTEST_RTOL, reg_tests/CMakeLists.txt)
    atol = max(10**(max_t(floor(log10(b - min(b) + 1e-12))) - ATOL_MAGNITUDE), 1e-6)   ATOL_MAGNITUDE = 1.9
    a channel passes when every sample satisfies |t - b| <= atol + rtol |b| (numpy.isclose) and is finite;
    a case passes when every channel passes (ConvIter / ConvError / NumUJac channels are dropped first).

It also reports the regression suite's own norms and the largest relative error
`|t - b| / |b|` over the samples with `|b| > atol` (below atol the relative error is not meaningful).

Usage:
    rtestAeroDyn.py --rtest DIR/r-test --openfast-env ENV --scratch EMPTY_DIR --out TABLE.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

RTOL_MAGNITUDE = 2.0
ATOL_MAGNITUDE = 1.9
NUMEPS = 1e-12
ATOL_MIN = 1e-6
DROPPED_CHANNELS = ("ConvIter", "ConvError", "NumUJac")
#: Reference file names the regression script looks for, in its order of preference.
OUTPUT_NAMES = ("ad_driver.T2.outb", "ad_driver.4.outb", "ad_driver.outb")


def read_outb(path: Path) -> tuple[list[str], np.ndarray]:
    """Channel names (Time first) and data of an OpenFAST binary output (FileID 1-4), as `fast_io.load_binary_output`."""
    with Path(path).open("rb") as stream:
        def read(fmt: str, count: int = 1):
            size = struct.calcsize(fmt)
            return struct.unpack(f"<{count}{fmt}", stream.read(size * count))

        file_id = read("h")[0]
        len_name = read("h")[0] if file_id == 4 else 10
        n_chan = read("i")[0]
        n_time = read("i")[0]
        if file_id == 1:
            time_scale, time_offset = read("d")[0], read("d")[0]
        else:
            time_first, time_step = read("d")[0], read("d")[0]
        if file_id != 3:
            col_scale = np.array(read("f", n_chan))
            col_offset = np.array(read("f", n_chan))
        len_desc = read("i")[0]
        stream.read(len_desc)
        names = [bytes(read("B", len_name)).decode("ascii", "replace").strip() for _ in range(n_chan + 1)]
        for _ in range(n_chan + 1):
            stream.read(len_name)  # units
        packed_time = np.array(read("i", n_time)) if file_id == 1 else None
        if file_id == 3:
            data = np.array(read("d", n_time * n_chan)).reshape(n_time, n_chan)
        else:
            data = (np.array(read("h", n_time * n_chan)).reshape(n_time, n_chan) - col_offset) / col_scale
    if file_id == 1:
        times = (packed_time - time_offset) / time_scale
    else:
        times = time_first + time_step * np.arange(n_time)
    return names, np.concatenate([times.reshape(-1, 1), data], axis=1)


def drop_channels(names: list[str], data: np.ndarray) -> tuple[list[str], np.ndarray]:
    keep = [i for i, name in enumerate(names) if name not in DROPPED_CHANNELS]
    return [names[i] for i in keep], data[:, keep]


def channel_atol(baseline: np.ndarray, atol_magnitude: float = ATOL_MAGNITUDE) -> float:
    """`pass_fail.passing_channels` absolute tolerance of one channel."""
    offset = baseline - np.min(baseline)
    order = np.floor(np.log10(offset + NUMEPS))
    return max(10.0 ** (np.max(order) - atol_magnitude), ATOL_MIN)


def passing_channels(test: np.ndarray, baseline: np.ndarray, rtol_magnitude: float = RTOL_MAGNITUDE,
                     atol_magnitude: float = ATOL_MAGNITUDE) -> np.ndarray:
    """Per-channel pass flags; `test` and `baseline` are (channels, samples) arrays (as pass_fail)."""
    if test.size != baseline.size:
        return np.zeros(test.shape[0], dtype=bool)
    rtol = 10.0 ** (-rtol_magnitude)
    passing = np.zeros(test.shape[0], dtype=bool)
    for i in range(test.shape[0]):
        atol = channel_atol(baseline[i], atol_magnitude)
        close = np.isclose(test[i], baseline[i], atol=atol, rtol=rtol)
        passing[i] = bool(np.all(close & np.isfinite(test[i])))
    return passing


def max_relative_error(test: np.ndarray, baseline: np.ndarray, atol_magnitude: float = ATOL_MAGNITUDE) -> tuple[float, int]:
    """Largest |t - b| / |b| over samples with |b| > the channel atol, and the channel index (-1 if none)."""
    worst, where = 0.0, -1
    for i in range(test.shape[0]):
        atol = channel_atol(baseline[i], atol_magnitude)
        mask = np.abs(baseline[i]) > atol
        if not mask.any():
            continue
        err = float(np.max(np.abs(test[i][mask] - baseline[i][mask]) / np.abs(baseline[i][mask])))
        if err > worst:
            worst, where = err, i
    return worst, where


def regression_norm(test: np.ndarray, baseline: np.ndarray) -> float:
    """Largest over channels of `calculate_max_norm_over_range` (samples x channels input)."""
    ranges = np.abs(baseline.max(axis=0) - baseline.min(axis=0))
    diff = np.abs(test - baseline)
    norm = np.max(diff, axis=0)
    wide = ranges >= 1
    norm[wide] = np.max(diff[:, wide] / ranges[wide], axis=0)
    return float(np.max(norm))


# --- case selection --------------------------------------------------------

_QUOTED = re.compile(r'^\s*"([^"]+)"')


def aero_file(driver: Path) -> Path | None:
    for line in driver.read_text(errors="replace").splitlines():
        if re.search(r"\bAeroFile\b", line):
            match = _QUOTED.match(line)
            if match:
                return (driver.parent / match.group(1)).resolve()
    return None


def wake_mod(aero: Path) -> int | None:
    for line in aero.read_text(errors="replace").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "Wake_Mod":
            try:
                return int(parts[0])
            except ValueError:
                return None
    return None


def reference_output(case: Path) -> Path | None:
    for name in OUTPUT_NAMES:
        if (case / name).is_file():
            return case / name
    return None


def select_cases(module_dir: Path) -> tuple[list[dict], list[dict]]:
    """(BEM cases, skipped cases with reason) among `ad_*` directories."""
    run, skipped = [], []
    for case in sorted(module_dir.glob("ad_*")):
        driver = case / "ad_driver.dvr"
        if not driver.is_file():
            skipped.append({"case": case.name, "reason": "no ad_driver.dvr"})
            continue
        aero = aero_file(driver)
        mod = wake_mod(aero) if aero is not None and aero.is_file() else None
        if mod != 1:
            skipped.append({"case": case.name, "reason": f"Wake_Mod {mod} (not BEMT)"})
        elif reference_output(case) is None:
            skipped.append({"case": case.name, "reason": "no reference .outb"})
        else:
            run.append({"case": case.name, "driver": driver, "reference": reference_output(case)})
    return run, skipped


def run_case(entry: dict, module_dir: Path, driver_exe: Path, timeout: float) -> dict:
    """Run one case in place inside the scratch copy of the r-test tree (relative input paths such as
    `../BAR_Baseline` and `../../../glue-codes` resolve as in the r-test layout)."""
    case = entry["case"]
    work = module_dir / case
    reference = work / entry["reference"].name
    renamed = work / (reference.stem + "_ref.outb")
    reference.rename(renamed)
    started = time.time()
    try:
        done = subprocess.run([str(driver_exe), "ad_driver.dvr"], cwd=work, capture_output=True, text=True, timeout=timeout)
        returncode = done.returncode
        tail = (done.stdout + done.stderr).replace("\r", "\n").strip().splitlines()[-1:]
    except subprocess.TimeoutExpired:
        return {"case": case, "status": "timeout", "wall_s": time.time() - started}
    wall = time.time() - started
    if returncode != 0 or not reference.is_file():
        return {"case": case, "status": f"driver rc={returncode}", "wall_s": wall, "note": " ".join(tail)}
    names_t, test = drop_channels(*read_outb(reference))
    names_b, base = drop_channels(*read_outb(renamed))
    if test.shape != base.shape or names_t != names_b:
        return {"case": case, "status": "FAIL (shape)", "wall_s": wall, "note": f"{test.shape} vs {base.shape}"}
    passing = passing_channels(test.T, base.T)
    worst, index = max_relative_error(test.T, base.T)
    return {
        "case": case,
        "status": "PASS" if passing.all() else "FAIL",
        "channels": len(names_b),
        "failing_channels": int((~passing).sum()),
        "samples": base.shape[0],
        "max_rel_err": worst,
        "max_rel_err_channel": names_b[index] if index >= 0 else "",
        "max_norm_over_range": regression_norm(test, base),
        "wall_s": wall,
        "note": ",".join(names_b[i] for i in np.flatnonzero(~passing)[:5]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rtest", type=Path, required=True, help="r-test checkout at tag v5.0.0")
    parser.add_argument("--openfast-env", type=Path, required=True, help="conda env prefix holding bin/aerodyn_driver")
    parser.add_argument("--scratch", type=Path, required=True, help="new empty scratch directory outside the repository (receives a copy of the r-test tree)")
    parser.add_argument("--out", type=Path, required=True, help="result CSV")
    parser.add_argument("--timeout", type=float, default=900.0, help="per-case wall limit in s (default 900)")
    args = parser.parse_args(argv)
    if args.scratch.exists() and any(args.scratch.iterdir()):
        parser.error(f"{args.scratch} is not empty")
    args.scratch.mkdir(parents=True, exist_ok=True)
    shutil.copytree(args.rtest, args.scratch / "r-test", ignore=shutil.ignore_patterns(".git"))
    module_dir = args.scratch / "r-test" / "modules" / "aerodyn"
    cases, skipped = select_cases(module_dir)
    rows = []
    for entry in cases:
        row = run_case(entry, module_dir, args.openfast_env / "bin" / "aerodyn_driver", args.timeout)
        rows.append(row)
        print(f"{row['case']:<34}{row['status']:<10} max_rel_err {row.get('max_rel_err', float('nan')):.3e}  {row['wall_s']:.1f} s", flush=True)
    fields = ["case", "status", "channels", "failing_channels", "samples", "max_rel_err", "max_rel_err_channel",
              "max_norm_over_range", "wall_s", "note"]
    with args.out.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, restval="")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: (f"{value:.6g}" if isinstance(value, float) else value) for key, value in row.items()})
    for item in skipped:
        print(f"skipped {item['case']}: {item['reason']}")
    return 0 if all(row["status"] == "PASS" for row in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
