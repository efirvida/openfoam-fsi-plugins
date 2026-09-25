#!/bin/sh
# Build the mock structural participant.
#
# preCICE is built with GCC 14 (see the venv), so the dummy must link with a
# matching libstdc++: the default system g++ (8.5) is too old. Override GXX and
# VENV if your toolchain lives elsewhere.
set -e -u

cd "${0%/*}" || exit

GXX="${GXX:-/scratch/app/gcc/14.2.0/bin/g++}"
VENV="${VENV:-/scratch/leahk/eduardo.donestevez/venv}"
GCC_LIB="${GCC_LIB:-/scratch/app/gcc/14.2.0/lib64}"

if [ ! -x "$GXX" ]; then
    echo "build.sh: compiler not found: $GXX (set GXX=...)" >&2
    exit 2
fi

if [ ! -f "$VENV/include/precice/precice.hpp" ]; then
    echo "build.sh: preCICE headers not found under $VENV (set VENV=...)" >&2
    exit 2
fi

"$GXX" -std=c++17 -O2 \
    -I"$VENV/include" \
    -L"$VENV/lib64" \
    -L"$GCC_LIB" \
    -Wl,-rpath,"$GCC_LIB" \
    -Wl,-rpath,"$VENV/lib64" \
    -o solverdummy solverdummy.cpp -lprecice

echo "build.sh: built $PWD/solverdummy"
