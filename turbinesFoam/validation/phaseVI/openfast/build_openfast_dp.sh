#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Build OpenFAST v5.0.0 in DOUBLE precision (aerodyn_driver, openfast) on SDumont and install it
# with an RPATH, so the binaries run on compute nodes without any module or LD_LIBRARY_PATH.
#
# Why: the conda-forge OpenFAST v5.0.0 is built with -DDOUBLE_PRECISION=OFF and passes 2/9 of the
# r-test AeroDyn-driver BEM cases; the same source in double precision passes 9/9
# (odd/tasks/v13-adoption-asm.md, S8). Environment overrides (defaults in brackets):
#   OPENFAST_TAG     [v5.0.0]
#   BUILD_ROOT       [/scratch/leahk/eduardo.donestevez/build]    source + build tree
#   PREFIX           [/scratch/leahk/eduardo.donestevez/openfast-5.0.0-dp]
#   GCC_HOME         [/scratch/app/gcc/14.2.0]                    GCC 14.2 (gcc, g++, gfortran)
#   BLAS_LIB         [/scratch/leahk/eduardo.donestevez/venv/lib/libfblas.a]     static reference BLAS (gfortran)
#   LAPACK_LIB       [/scratch/leahk/eduardo.donestevez/venv/lib/libflapack.a]   static reference LAPACK (gfortran)
#   The site OpenBLAS (/scratch/app/mathlibs/netlib/openblas/0.3.29_gcc-9.3_gnu) cannot be used: it
#   carries Intel runtime symbols (__intel_cpu_features_init_x, for_exponent8_v) and fails to link.
#   CMAKE_BIN        [cmake, or /scratch/app/cmake/3.30.3/bin/cmake when present]
#   JOBS             [8]
# Usage: sh turbinesFoam/validation/phaseVI/openfast/build_openfast_dp.sh   (any path with a "/"; network for the first clone)
cd "${0%/*}" || exit 1

OPENFAST_TAG=${OPENFAST_TAG:-v5.0.0}
BUILD_ROOT=${BUILD_ROOT:-/scratch/leahk/eduardo.donestevez/build}
PREFIX=${PREFIX:-/scratch/leahk/eduardo.donestevez/openfast-5.0.0-dp}
GCC_HOME=${GCC_HOME:-/scratch/app/gcc/14.2.0}
BLAS_LIB=${BLAS_LIB:-/scratch/leahk/eduardo.donestevez/venv/lib/libfblas.a}
LAPACK_LIB=${LAPACK_LIB:-/scratch/leahk/eduardo.donestevez/venv/lib/libflapack.a}
JOBS=${JOBS:-8}
if [ -z "${CMAKE_BIN:-}" ]; then
    if [ -x /scratch/app/cmake/3.30.3/bin/cmake ]; then CMAKE_BIN=/scratch/app/cmake/3.30.3/bin/cmake; else CMAKE_BIN=cmake; fi
fi

set -eu

for tool in gcc g++ gfortran; do
    [ -x "$GCC_HOME/bin/$tool" ] || { echo "missing $GCC_HOME/bin/$tool" >&2; exit 1; }
done
for lib in "$BLAS_LIB" "$LAPACK_LIB"; do
    [ -e "$lib" ] || { echo "missing $lib" >&2; exit 1; }
done

src="$BUILD_ROOT/openfast-$OPENFAST_TAG"
build="$src-build-dp"
mkdir -p "$BUILD_ROOT"
if [ ! -d "$src/.git" ]; then
    git clone --depth 1 --branch "$OPENFAST_TAG" https://github.com/OpenFAST/openfast.git "$src"
fi
commit=$(git -C "$src" rev-parse HEAD)

PATH="$GCC_HOME/bin:$PATH"
export PATH
LD_LIBRARY_PATH="$GCC_HOME/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export LD_LIBRARY_PATH
CC="$GCC_HOME/bin/gcc"; CXX="$GCC_HOME/bin/g++"; FC="$GCC_HOME/bin/gfortran"
export CC CXX FC

started=$(date +%s)
"$CMAKE_BIN" -S "$src" -B "$build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DDOUBLE_PRECISION=ON \
    -DOPENMP=OFF \
    -DBUILD_TESTING=OFF \
    -DBUILD_OPENFAST_CPP_API=OFF \
    -DBUILD_SHARED_LIBS=OFF \
    -DCMAKE_INSTALL_PREFIX="$PREFIX" \
    -DBLAS_LIBRARIES="$BLAS_LIB" \
    -DLAPACK_LIBRARIES="$LAPACK_LIB;$BLAS_LIB;gfortran" \
    -DCMAKE_SKIP_INSTALL_RPATH=OFF \
    -DCMAKE_INSTALL_RPATH="$GCC_HOME/lib64" \
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
    -DCMAKE_EXE_LINKER_FLAGS="-Wl,-rpath,$GCC_HOME/lib64" \
    -DCMAKE_INSTALL_RPATH_USE_LINK_PATH=ON
# Relink every time so the RPATH flags always reach the executables (CMake does not relink an
# up-to-date target after a cache-only change).
rm -f "$build/glue-codes/openfast/openfast" "$build/modules/aerodyn/aerodyn_driver"
"$CMAKE_BIN" --build "$build" --target openfast aerodyn_driver -j "$JOBS"
# Only these two targets are built, so `cmake --install` (which needs every target) is not used:
# the binaries already carry the install RPATH (CMAKE_BUILD_WITH_INSTALL_RPATH).
mkdir -p "$PREFIX/bin"
cp "$build/glue-codes/openfast/openfast" "$build/modules/aerodyn/aerodyn_driver" "$PREFIX/bin/"
elapsed=$(( $(date +%s) - started ))

precision=$(grep -E '^DOUBLE_PRECISION:' "$build/CMakeCache.txt")
flags=$(grep -E '^CMAKE_Fortran_FLAGS(_RELEASE)?:' "$build/CMakeCache.txt" | tr '\n' ' ')
{
    echo "OpenFAST $OPENFAST_TAG double precision"
    echo "git tag/commit : $OPENFAST_TAG / $commit"
    echo "built          : $(date -u +%Y-%m-%dT%H:%MZ) on $(hostname), $elapsed s, -j $JOBS"
    echo "compiler       : $("$FC" --version | head -n 1)"
    echo "cmake          : $("$CMAKE_BIN" --version | head -n 1)"
    echo "BLAS/LAPACK    : $BLAS_LIB ; $LAPACK_LIB (static)"
    echo "CMake cache    : $precision"
    echo "Fortran flags  : $flags"
    echo "RPATH          : $GCC_HOME/lib64"
    echo "recipe         : sh turbinesFoam/validation/phaseVI/openfast/build_openfast_dp.sh"
} > "$PREFIX/BUILD-INFO.txt"
cat "$PREFIX/BUILD-INFO.txt"
# The binaries must run with an empty environment (compute nodes load no module).
for exe in aerodyn_driver openfast; do
    if env -i "$PREFIX/bin/$exe" -h 2>&1 | grep -q "not found"; then
        echo "ERROR: $PREFIX/bin/$exe does not run without LD_LIBRARY_PATH" >&2
        exit 1
    fi
done
