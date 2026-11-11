#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# IEA 22-280-RWT rated-point run body. A wrapper, not a copy, of the IEA-15 runner
# (../../iea15mw/scripts/run_iea15mw_case.sh): the runner takes the package from
# TURBINE_PKG_DIR and calls <package>/tools/generate_case.py, which for IEA-22 is the
# IEA-15 generator rebound to the IEA-22 geometry, rated point (R = 142 m, 6.853997 rpm,
# pitch 4.127462 deg) and R-proportional castellated extents. Every TURBINE_* variable
# of the IEA-15 runner therefore works unchanged (see its header).
#
# Platform quantities that are NOT passed here (rpm, speed, domain, snappy extents) take
# the generator defaults, which are the IEA-22 values. The ones the Slurm scripts must
# pass (ranks, decomposition, sampling radius, snappy level) come from
# scripts/platform_derive.py, so none is typed twice.
#
# Defaults set here: TURBINE_PKG_DIR = the IEA-22 package, TURBINE_RUN_DIR =
# runs/iea22mw-rated-<mesh> (relative to the package).
set -eu
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pkg_dir="${TURBINE_PKG_DIR:-$(dirname "$here")}"
if [ ! -f "${pkg_dir}/tools/generate_case.py" ] || ! grep -q iea22mw "${pkg_dir}/tools/generate_case.py"; then
    echo "ERROR: TURBINE_PKG_DIR is not the IEA-22 package: ${pkg_dir}" >&2
    exit 3
fi
export TURBINE_PKG_DIR="$pkg_dir"
export TURBINE_RUN_DIR="${TURBINE_RUN_DIR:-runs/iea22mw-rated-${TURBINE_MESH:-coarse}}"
exec bash "${pkg_dir}/../iea15mw/scripts/run_iea15mw_case.sh" "$@"
