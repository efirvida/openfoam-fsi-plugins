#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Install FLOWUnsteady (https://github.com/byuflowlab/FLOWUnsteady) in a private Julia
# environment on SDumont, as verified on 2026-10-16 (login node, no module needed).
#
# Facts that cost attempts:
#  - module julia/1.11.4 and 1.10.7: the Pkg stdlib directory is not readable ("Package Pkg not found");
#    1.10.6 has no Pkg. Only /scratch/app/julia/1.11.3 works. FLOWUnsteady documents support up to 1.10.
#  - JULIA_DEPOT_PATH must end with ':' so the installation's own depot (stdlib) stays on the path.
#  - FLOWUnsteady and its BYU dependencies are not in the General registry: add by URL, with the
#    names of the official docs (FLOWNoise, BPM.jl, not FLOWNoise.jl / BroadbandBPM.jl: 404).
#  - FLOWVPM (default branch) needs FastMultipole master (metadata_per_body); registered 2.0.4 fails.
#  - PyPlot/PyCall take the Python in $PYTHON (needs matplotlib, mpmath, scipy).
set -eu
JULIA_HOME=${JULIA_HOME:-/scratch/app/julia/1.11.3}
ENV_DIR=${1:-/scratch/leahk/eduardo.donestevez/flowunsteady-env}
export LD_LIBRARY_PATH="$JULIA_HOME/lib:${LD_LIBRARY_PATH:-}"
export JULIA_DEPOT_PATH="${JULIA_DEPOT_PATH:-/scratch/leahk/eduardo.donestevez/julia-depot}:"
export PYTHON="${PYTHON:-/scratch/leahk/eduardo.donestevez/venv/bin/python3}"
mkdir -p "$ENV_DIR"
cd "$ENV_DIR"
"$JULIA_HOME/bin/julia" --project=. -e '
using Pkg
Pkg.add(["GeometricTools", "VSPGeom", "PyCall", "PyPlot"])
url = "https://github.com/byuflowlab/"
names = ["AirfoilPrep.jl", "FLOWVLM", "FLOWNoise", "BPM.jl", "FLOWVPM.jl", "FLOWUnsteady"]
Pkg.add([Pkg.PackageSpec(; url=url*n) for n in names])
Pkg.add(url=url*"FastMultipole.jl")
Pkg.precompile()
import FLOWUnsteady
println("INSTALL_OK")'
